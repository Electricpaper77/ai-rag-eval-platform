"""SQLite persistence for metadata-only local tool execution outcomes.

The store is intended for a single local executor. It does not coordinate
workers or hosts. Call ``recover_incomplete`` only after the prior executor is
known to have stopped; an unclosed dispatch is then conservatively recorded as
having an unknown outcome.
"""
from __future__ import annotations

import asyncio
import errno
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    AsyncContextManager, AsyncIterator, Callable, ContextManager, Iterator, Protocol,
)

if os.name == "posix":
    import fcntl


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOL_OUTCOME_DB = (
    REPOSITORY_ROOT / "artifacts/agent_execution/outcome_store/tool_outcomes.sqlite3"
)
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_TERMINAL_REASONS = {
    "completed": {None},
    "outcome_unknown": {"tool_outcome_unknown"},
    "completed_result_unavailable": {
        "tool_result_not_serializable",
        "tool_result_too_large",
    },
}
_EVENT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS tool_outcome_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL CHECK (step_number > 0),
    tool_name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('dispatch', 'terminal')),
    status TEXT NOT NULL CHECK (status IN (
        'in_flight', 'completed', 'outcome_unknown',
        'completed_result_unavailable'
    )),
    reason_code TEXT,
    occurred_at TEXT NOT NULL,
    UNIQUE (run_id, step_number, event_type),
    CHECK (
        (event_type = 'dispatch' AND status = 'in_flight'
            AND reason_code IS NULL)
        OR
        (event_type = 'terminal' AND status = 'completed'
            AND reason_code IS NULL)
        OR
        (event_type = 'terminal' AND status = 'outcome_unknown'
            AND reason_code = 'tool_outcome_unknown')
        OR
        (event_type = 'terminal'
            AND status = 'completed_result_unavailable'
            AND reason_code IN (
                'tool_result_not_serializable', 'tool_result_too_large'
            ))
    )
)
"""
_EXPECTED_EVENT_COLUMNS = (
    ("sequence", "INTEGER", 0, 1),
    ("run_id", "TEXT", 1, 0),
    ("step_number", "INTEGER", 1, 0),
    ("tool_name", "TEXT", 1, 0),
    ("event_type", "TEXT", 1, 0),
    ("status", "TEXT", 1, 0),
    ("reason_code", "TEXT", 0, 0),
    ("occurred_at", "TEXT", 1, 0),
)
_EXPECTED_EVENT_TABLE_SQL = re.sub(
    r"\s+", " ", _EVENT_TABLE_DDL.strip()
).casefold().replace("create table if not exists ", "create table ", 1)


class ToolOutcomeSchemaError(ValueError):
    """Raised when the persisted event table differs from the supported schema."""


class ToolOutcomeSidecarError(ValueError):
    """Raised when a SQLite WAL/SHM path is not a regular file."""


class ToolOutcomeLockError(RuntimeError):
    """Sanitized process-lock error with a fixed reason code."""

    def __init__(self, reason: str) -> None:
        if reason not in {"executor_active", "lock_path_unsafe", "locking_unsupported"}:
            raise ValueError("unsupported tool outcome lock error")
        self.reason = reason
        super().__init__(reason)


@contextmanager
def local_database_process_lock(
    database_path: Path | str, *, nonblocking: bool = True
) -> Iterator[None]:
    """Take a private same-host POSIX advisory lock for one database path.

    The lock file is deliberately persistent. Removing it while any process
    may hold it would let another process lock a different inode.
    """
    descriptor = _open_local_database_lock(database_path)
    acquired = False
    try:
        operation = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        try:
            fcntl.flock(descriptor, operation)
            acquired = True
        except BlockingIOError:
            raise ToolOutcomeLockError("executor_active") from None
        except OSError as error:
            if error.errno in {errno.EAGAIN, errno.EACCES}:
                raise ToolOutcomeLockError("executor_active") from None
            raise ToolOutcomeLockError("locking_unsupported") from None
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _open_local_database_lock(database_path: Path | str) -> int:
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "O_CLOEXEC") or "fcntl" not in globals()):
        raise ToolOutcomeLockError("locking_unsupported")
    database = Path(database_path)
    if not database.is_absolute():
        raise ToolOutcomeLockError("lock_path_unsafe")
    lock_path = Path(f"{database}.lock")
    try:
        parent_info = database.parent.lstat()
        if (not stat.S_ISDIR(parent_info.st_mode)
                or stat.S_IMODE(parent_info.st_mode) & 0o077):
            raise ToolOutcomeLockError("lock_path_unsafe")
        flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            descriptor = os.open(
                lock_path, flags | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            descriptor = os.open(lock_path, flags)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise ToolOutcomeLockError("lock_path_unsafe")
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor
    except ToolOutcomeLockError:
        raise
    except OSError:
        raise ToolOutcomeLockError("lock_path_unsafe") from None


@asynccontextmanager
async def async_local_database_process_lock(
    database_path: Path | str, *, poll_interval: float = 0.01,
    cancel_check: Callable[[], None] | None = None,
) -> AsyncIterator[None]:
    """Wait asynchronously for the same cooperative per-database POSIX lock.

    Acquisition polls the OS lock without blocking the event loop. No FIFO
    fairness is promised. Cancellation of the waiting task closes its file
    descriptor; an acquired lock is always released on context exit.
    """
    descriptor = _open_local_database_lock(database_path)
    acquired = False
    try:
        while not acquired:
            if cancel_check is not None:
                cancel_check()
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                await asyncio.sleep(poll_interval)
            except OSError as error:
                if error.errno in {errno.EAGAIN, errno.EACCES}:
                    await asyncio.sleep(poll_interval)
                    continue
                raise ToolOutcomeLockError("locking_unsupported") from None
        yield
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def validate_sqlite_sidecars(path: Path | str) -> None:
    """Reject symlinked or special WAL/SHM paths before SQLite opens the DB."""
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        try:
            mode = sidecar.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            raise ToolOutcomeSidecarError("tool outcome sidecar path invalid") from None
        if not stat.S_ISREG(mode):
            raise ToolOutcomeSidecarError("tool outcome sidecar path invalid")


def validate_event_schema(connection: sqlite3.Connection) -> None:
    """Validate the exact event-table contract used by the local store.

    Column introspection checks the operations' field order, types, nullability,
    and primary key. Canonical DDL comparison also enforces AUTOINCREMENT,
    uniqueness, and status/reason CHECK constraints. Equivalent but differently
    written schemas fail closed and require an explicit migration.
    """
    columns = tuple(
        (row[1], str(row[2]).upper(), int(row[3]), int(row[5]))
        for row in connection.execute(
            "PRAGMA table_info(tool_outcome_events)"
        ).fetchall()
    )
    if columns != _EXPECTED_EVENT_COLUMNS:
        raise ToolOutcomeSchemaError("tool outcome schema invalid")

    schema_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='tool_outcome_events'"
    ).fetchone()
    if schema_row is None or not isinstance(schema_row[0], str):
        raise ToolOutcomeSchemaError("tool outcome schema invalid")
    actual_sql = re.sub(r"\s+", " ", schema_row[0].strip()).casefold()
    if actual_sql != _EXPECTED_EVENT_TABLE_SQL:
        raise ToolOutcomeSchemaError("tool outcome schema invalid")

    unique_keys: set[tuple[str, ...]] = set()
    for index in connection.execute(
        'PRAGMA index_list("tool_outcome_events")'
    ).fetchall():
        if index[2]:
            escaped_name = str(index[1]).replace('"', '""')
            unique_keys.add(tuple(
                row[2] for row in connection.execute(
                    f'PRAGMA index_info("{escaped_name}")'
                ).fetchall()
            ))
    if ("run_id", "step_number", "event_type") not in unique_keys:
        raise ToolOutcomeSchemaError("tool outcome schema invalid")


class ToolOutcomeStoreError(RuntimeError):
    """Sanitized persistence error; never includes SQLite exception details."""

    def __init__(self, operation: str) -> None:
        if operation not in {
            "initialize", "dispatch", "terminal", "recover", "backup", "restore"
        }:
            raise ValueError("unsupported tool outcome store operation")
        self.operation = operation
        super().__init__(f"tool outcome persistence failed during {operation}")


class ToolOutcomeStore(Protocol):
    def execution_lock(self) -> ContextManager[None]: ...

    def async_execution_lock(
        self, *, cancel_check: Callable[[], None] | None = None
    ) -> AsyncContextManager[None]: ...

    def record_dispatch(self, run_id: str, step_number: int, tool_name: str) -> bool: ...

    def record_terminal(self, run_id: str, step_number: int, tool_name: str,
                        status: str, reason_code: str | None = None) -> bool: ...


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_identity(run_id: str, step_number: int, tool_name: str) -> None:
    if not isinstance(run_id, str) or not _SAFE_ID.fullmatch(run_id):
        raise ValueError("run_id must be a non-secret opaque identifier")
    if type(step_number) is not int or step_number < 1:
        raise ValueError("step_number must be a positive integer")
    if not isinstance(tool_name, str) or not _SAFE_ID.fullmatch(tool_name):
        raise ValueError("tool_name must be a stable identifier")


def _private_parent(path: Path) -> None:
    """Create a dedicated private directory or reject a broadly accessible one."""
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "posix" and stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise PermissionError("tool outcome database directory must have mode 0700")


def _validate_existing_database_file(path: Path) -> None:
    """Reject a replaced, missing, or non-regular DB path before SQLite opens it."""
    try:
        mode = path.lstat().st_mode
    except OSError:
        raise PermissionError("tool outcome database path invalid") from None
    if not stat.S_ISREG(mode):
        raise PermissionError("tool outcome database path invalid")


def _restrict_file(path: Path) -> None:
    """Restrict database and backup files when POSIX mode bits are available."""
    if path.is_symlink():
        raise PermissionError("tool outcome database files must not be symlinks")
    if path.exists() and os.name == "posix":
        os.chmod(path, 0o600)


def _restrict_sidecars(path: Path) -> None:
    if os.name != "posix":
        return
    validate_sqlite_sidecars(path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    for sidecar in (Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            sidecar.lstat()
        except FileNotFoundError:
            continue
        if nofollow is None:
            raise ToolOutcomeSidecarError("safe sidecar permission handling unavailable")
        descriptor: int | None = None
        try:
            descriptor = os.open(
                sidecar, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
            )
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ToolOutcomeSidecarError("tool outcome sidecar path invalid")
            os.fchmod(descriptor, 0o600)
        except ToolOutcomeSidecarError:
            raise
        except FileNotFoundError:
            continue
        except OSError:
            raise ToolOutcomeSidecarError("tool outcome sidecar path invalid") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)


def _temporary_sibling(destination: Path) -> Path:
    """Reserve a private temporary file on the destination filesystem."""
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(name)
    if os.name == "posix":
        os.chmod(temporary, 0o600)
    return temporary


def _install_new_file(temporary: Path, destination: Path) -> None:
    """Atomically publish a complete file without replacing an existing path.

    A hard link is an atomic, same-filesystem create-if-absent operation. If
    the filesystem does not support it, fail closed and leave the destination
    untouched rather than falling back to a potentially replacing rename.
    """
    os.link(temporary, destination)
    try:
        temporary.unlink()
    except OSError:
        # The destination is already complete and visible. A leftover private
        # temporary link is safe to remove during operator housekeeping.
        pass


class SQLiteToolOutcomeStore:
    """Append-only local event store backed by SQLite's transactional commits.

    Dispatch events are written before tool invocation. A duplicate dispatch
    returns ``False`` so callers can fail closed instead of repeating a
    possibly side-effecting operation. Duplicate identical terminal events are
    idempotent; conflicting terminal events raise ``ToolOutcomeStoreError``.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        configured_path = os.getenv("AGENT_EXECUTION_OUTCOME_DB", "").strip()
        configured = Path(path) if path is not None else (
            Path(configured_path) if configured_path else DEFAULT_TOOL_OUTCOME_DB
        )
        # Resolve relative paths against the source repository, not the caller's
        # current working directory, so a restart launched elsewhere reopens
        # the same local event database.
        candidate = (configured if configured.is_absolute()
                     else REPOSITORY_ROOT / configured).absolute()
        try:
            _private_parent(candidate)
            if candidate.is_symlink():
                raise PermissionError("tool outcome database must not be a symlink")
            self._path = candidate.resolve(strict=False)
            # Store construction is synchronous startup work. Wait for a
            # cooperating executor to finish rather than failing a newly
            # starting process on ordinary lock contention. Recovery keeps
            # its separate nonblocking acquisition path.
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # Synchronous CLI/startup callers may wait for another
                # cooperating process to finish initialization or dispatch.
                nonblocking = False
            else:
                # A synchronous constructor on an event-loop thread must
                # never freeze that loop behind a dispatch handler awaiting
                # work on the same loop. Async callers should use
                # create_async() instead.
                nonblocking = True
            with local_database_process_lock(
                self._path, nonblocking=nonblocking
            ):
                _restrict_file(self._path)
                validate_sqlite_sidecars(self._path)
                with sqlite3.connect(self._path, timeout=5.0) as connection:
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.execute("PRAGMA synchronous=FULL")
                    connection.execute(_EVENT_TABLE_DDL)
                    validate_event_schema(connection)
                _restrict_file(self._path)
                _restrict_sidecars(self._path)
        except Exception:
            raise ToolOutcomeStoreError("initialize") from None

    @classmethod
    async def create_async(
        cls, path: Path | str | None = None
    ) -> "SQLiteToolOutcomeStore":
        """Initialize without blocking the caller's event loop while waiting."""
        return await asyncio.to_thread(cls, path)

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def execution_lock(self) -> Iterator[None]:
        """Nonblocking same-host lock held across a tool's full side effect."""
        with local_database_process_lock(self._path, nonblocking=True):
            yield

    @asynccontextmanager
    async def async_execution_lock(
        self, *, cancel_check: Callable[[], None] | None = None
    ) -> AsyncIterator[None]:
        """Wait asynchronously for this database's same-host process lock."""
        async with async_local_database_process_lock(
            self._path, cancel_check=cancel_check
        ):
            yield

    @classmethod
    @contextmanager
    def lock_for_path(cls, path: Path | str) -> Iterator[None]:
        """Acquire the same local lock before recovery revalidates a database."""
        with local_database_process_lock(path, nonblocking=True):
            yield

    @classmethod
    def _from_locked_path(cls, path: Path | str) -> "SQLiteToolOutcomeStore":
        """Create a store facade when the caller already owns the process lock."""
        instance = cls.__new__(cls)
        instance._path = Path(path)
        return instance

    @contextmanager
    def _connection(self):
        _validate_existing_database_file(self._path)
        _private_parent(self._path)
        validate_sqlite_sidecars(self._path)
        connection = sqlite3.connect(self._path, timeout=5.0)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            validate_event_schema(connection)
            with connection:
                yield connection
        finally:
            connection.close()
            _restrict_file(self._path)
            _restrict_sidecars(self._path)

    def record_dispatch(self, run_id: str, step_number: int, tool_name: str) -> bool:
        _validate_identity(run_id, step_number, tool_name)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT tool_name, event_type FROM tool_outcome_events "
                    "WHERE run_id=? AND step_number=?",
                    (run_id, step_number),
                ).fetchall()
                if rows:
                    if any(existing_tool != tool_name for existing_tool, _ in rows):
                        raise ToolOutcomeStoreError("dispatch")
                    return False
                connection.execute(
                    "INSERT INTO tool_outcome_events "
                    "(run_id, step_number, tool_name, event_type, status, reason_code, occurred_at) "
                    "VALUES (?, ?, ?, 'dispatch', 'in_flight', NULL, ?)",
                    (run_id, step_number, tool_name, _timestamp()),
                )
                return True
        except ToolOutcomeStoreError:
            raise
        except Exception:
            raise ToolOutcomeStoreError("dispatch") from None

    def record_terminal(self, run_id: str, step_number: int, tool_name: str,
                        status: str, reason_code: str | None = None) -> bool:
        _validate_identity(run_id, step_number, tool_name)
        if status not in _TERMINAL_REASONS or reason_code not in _TERMINAL_REASONS[status]:
            raise ValueError("invalid terminal tool outcome")
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                dispatch = connection.execute(
                    "SELECT tool_name FROM tool_outcome_events "
                    "WHERE run_id=? AND step_number=? AND event_type='dispatch'",
                    (run_id, step_number),
                ).fetchone()
                if dispatch is None or dispatch[0] != tool_name:
                    raise ToolOutcomeStoreError("terminal")
                prior = connection.execute(
                    "SELECT status, reason_code FROM tool_outcome_events "
                    "WHERE run_id=? AND step_number=? AND event_type='terminal'",
                    (run_id, step_number),
                ).fetchone()
                if prior is not None:
                    if prior == (status, reason_code):
                        return False
                    raise ToolOutcomeStoreError("terminal")
                connection.execute(
                    "INSERT INTO tool_outcome_events "
                    "(run_id, step_number, tool_name, event_type, status, reason_code, occurred_at) "
                    "VALUES (?, ?, ?, 'terminal', ?, ?, ?)",
                    (run_id, step_number, tool_name, status, reason_code, _timestamp()),
                )
                return True
        except ToolOutcomeStoreError:
            raise
        except Exception:
            raise ToolOutcomeStoreError("terminal") from None

    def events(self, run_id: str) -> list[dict[str, object]]:
        if not isinstance(run_id, str) or not _SAFE_ID.fullmatch(run_id):
            raise ValueError("run_id must be a non-secret opaque identifier")
        try:
            with self._connection() as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT sequence, run_id, step_number, tool_name, event_type, "
                    "status, reason_code, occurred_at FROM tool_outcome_events "
                    "WHERE run_id=? ORDER BY sequence",
                    (run_id,),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            raise ToolOutcomeStoreError("recover") from None

    def recover_incomplete(self) -> list[dict[str, object]]:
        """Close prior dispatches as unknown after the prior executor has stopped."""
        try:
            with self.execution_lock():
                return self._recover_incomplete_locked()
        except ToolOutcomeLockError:
            raise ToolOutcomeStoreError("recover") from None

    def _recover_incomplete_locked(self) -> list[dict[str, object]]:
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                pending = connection.execute("""
                    SELECT dispatch.run_id, dispatch.step_number, dispatch.tool_name
                    FROM tool_outcome_events AS dispatch
                    LEFT JOIN tool_outcome_events AS terminal
                      ON terminal.run_id = dispatch.run_id
                     AND terminal.step_number = dispatch.step_number
                     AND terminal.event_type = 'terminal'
                    WHERE dispatch.event_type = 'dispatch' AND terminal.sequence IS NULL
                    ORDER BY dispatch.sequence
                """).fetchall()
                recovered: list[dict[str, object]] = []
                for run_id, step_number, tool_name in pending:
                    connection.execute(
                        "INSERT INTO tool_outcome_events "
                        "(run_id, step_number, tool_name, event_type, status, reason_code, occurred_at) "
                        "VALUES (?, ?, ?, 'terminal', 'outcome_unknown', 'tool_outcome_unknown', ?)",
                        (run_id, step_number, tool_name, _timestamp()),
                    )
                    recovered.append({
                        "run_id": run_id,
                        "step_number": step_number,
                        "tool_name": tool_name,
                        "status": "outcome_unknown",
                        "reason_code": "tool_outcome_unknown",
                    })
                return recovered
        except Exception:
            raise ToolOutcomeStoreError("recover") from None

    def backup_to(self, destination: Path | str) -> Path:
        """Create and atomically install a consistent new SQLite backup."""
        backup_path = Path(destination)
        if not backup_path.is_absolute():
            backup_path = REPOSITORY_ROOT / backup_path
        backup_path = backup_path.absolute()
        temporary: Path | None = None
        try:
            _private_parent(backup_path)
            if backup_path.exists() or backup_path.is_symlink():
                raise FileExistsError("backup destination already exists")
            temporary = _temporary_sibling(backup_path)
            with self._connection() as source:
                validate_sqlite_sidecars(temporary)
                target = sqlite3.connect(temporary, timeout=5.0)
                try:
                    with target:
                        source.backup(target)
                        integrity = target.execute("PRAGMA integrity_check").fetchone()
                        if integrity is None or integrity[0] != "ok":
                            raise sqlite3.DatabaseError("backup integrity check failed")
                        validate_event_schema(target)
                finally:
                    target.close()
            _restrict_file(temporary)
            _restrict_sidecars(temporary)
            _install_new_file(temporary, backup_path)
            return backup_path
        except Exception:
            if temporary is not None:
                for candidate in (temporary, Path(f"{temporary}-wal"),
                                  Path(f"{temporary}-shm")):
                    try:
                        candidate.unlink(missing_ok=True)
                    except OSError:
                        pass
            raise ToolOutcomeStoreError("backup") from None

    @classmethod
    def restore_from(cls, backup_path: Path | str,
                     destination: Path | str) -> "SQLiteToolOutcomeStore":
        """Restore a verified backup into a new database path without overwriting."""
        source_path = Path(backup_path)
        if not source_path.is_absolute():
            source_path = REPOSITORY_ROOT / source_path
        source_path = source_path.absolute()
        target_path = Path(destination)
        if not target_path.is_absolute():
            target_path = REPOSITORY_ROOT / target_path
        target_path = target_path.absolute()
        temporary: Path | None = None
        installed_identity: tuple[int, int] | None = None
        try:
            if source_path.is_symlink() or not source_path.is_file():
                raise FileNotFoundError("backup file is missing or unsafe")
            _private_parent(source_path)
            validate_sqlite_sidecars(source_path)
            _restrict_file(source_path)
            _private_parent(target_path)
            if target_path.exists() or target_path.is_symlink():
                raise FileExistsError("restore destination already exists")
            temporary = _temporary_sibling(target_path)
            with sqlite3.connect(source_path, timeout=5.0) as source:
                integrity = source.execute("PRAGMA integrity_check").fetchone()
                has_schema = source.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='tool_outcome_events'"
                ).fetchone()
                if integrity is None or integrity[0] != "ok" or has_schema is None:
                    raise sqlite3.DatabaseError("backup is invalid")
                validate_event_schema(source)
                validate_sqlite_sidecars(temporary)
                target = sqlite3.connect(temporary, timeout=5.0)
                try:
                    with target:
                        source.backup(target)
                        validate_event_schema(target)
                finally:
                    target.close()
            _restrict_file(temporary)
            _restrict_sidecars(temporary)
            _install_new_file(temporary, target_path)
            installed = target_path.lstat()
            installed_identity = (installed.st_dev, installed.st_ino)
            return cls(target_path)
        except Exception:
            if temporary is not None:
                for candidate in (temporary, Path(f"{temporary}-wal"),
                                  Path(f"{temporary}-shm")):
                    try:
                        candidate.unlink(missing_ok=True)
                    except OSError:
                        pass
            # Remove only a destination installed by this call. A concurrent
            # creator is never replaced or deleted.
            if installed_identity is not None:
                # Only remove a destination after this call's no-overwrite
                # link succeeded, and only if the path still names that same
                # inode. A concurrent creator may win the initial link race
                # or replace our path before error cleanup runs.
                try:
                    current = target_path.lstat()
                    if (current.st_dev, current.st_ino) == installed_identity:
                        target_path.unlink()
                except OSError:
                    pass
            raise ToolOutcomeStoreError("restore") from None
