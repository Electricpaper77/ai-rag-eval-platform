from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import textwrap
import threading
import time
import gc
from contextlib import asynccontextmanager

import pytest

from backend.app.agent_execution import (
    AgentExecutionService,
    CancellationController,
    AgentRunRejected,
    Tool,
    ToolArguments,
    ToolPolicyDecision,
)
from backend.app.tool_outcome_store import (
    SQLiteToolOutcomeStore,
    ToolOutcomeLockError,
    ToolOutcomeStoreError,
)
from backend.app import tool_outcome_store as tool_outcome_store_module
from scripts import agent_execution_store_admin as admin_cli
from scripts.agent_execution_store_admin import main, plan_retention


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path, 0o700)
    return path


def _run_agent_execution_child(
    code: str, *args: str, env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    repository_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code), *args],
        cwd=repository_root, env=env, check=True, capture_output=True,
        text=True, timeout=15,
    )


def _valid_database(path: Path) -> SQLiteToolOutcomeStore:
    store = SQLiteToolOutcomeStore(path)
    store.record_dispatch("cli-run", 1, "lookup")
    store.record_terminal("cli-run", 1, "lookup", "completed")
    return store


def _backup_name(instant: datetime) -> str:
    return f"agent-exec-outcomes-{instant.strftime('%Y%m%dT%H%M%SZ')}.sqlite3"


def _invalid_schema_backup(directory: Path, schema_error: str) -> Path:
    template = _valid_database(directory.parent / "schema-template" / "base.sqlite3")
    with sqlite3.connect(template.path) as connection:
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='tool_outcome_events'"
        ).fetchone()[0]
    if schema_error == "missing_column":
        ddl = ddl.replace("occurred_at TEXT NOT NULL,", "", 1)
    elif schema_error == "wrong_type":
        ddl = ddl.replace("run_id TEXT NOT NULL", "run_id BLOB NOT NULL", 1)
    elif schema_error == "wrong_nullability":
        ddl = ddl.replace("tool_name TEXT NOT NULL", "tool_name TEXT", 1)
    elif schema_error == "missing_unique":
        ddl = ddl.replace("UNIQUE (run_id, step_number, event_type),", "", 1)
    elif schema_error == "wrong_status_check":
        ddl = ddl.replace("'completed'", "'finished'")
    else:
        raise AssertionError(f"unknown test schema variant: {schema_error}")

    backup = directory / _backup_name(datetime(2025, 1, 6, 12, tzinfo=timezone.utc))
    with sqlite3.connect(backup) as connection:
        connection.execute(ddl)
    if os.name == "posix":
        os.chmod(backup, 0o600)
    return backup


def _track_temporary_directories(monkeypatch, tmp_path: Path) -> list[Path]:
    created: list[Path] = []
    original = admin_cli.tempfile.TemporaryDirectory

    def tracked(*args, **kwargs):
        kwargs.setdefault("dir", str(tmp_path))
        result = original(*args, **kwargs)
        created.append(Path(result.name))
        return result

    monkeypatch.setattr(admin_cli.tempfile, "TemporaryDirectory", tracked)
    return created


def _start_blocked_agent_executor(database: Path, directory: Path):
    _private_directory(directory)
    started = directory / "executor-handler-started.marker"
    release = directory / "executor-release.marker"
    repository_root = Path(__file__).resolve().parents[1]
    child_code = textwrap.dedent("""
        import asyncio
        import sqlite3
        import sys
        from pathlib import Path
        from backend.app.agent_execution import (
            AgentExecutionService, CancellationController, Tool,
            ToolArguments, ToolPolicyDecision,
        )
        from backend.app.tool_outcome_store import (
            SQLiteToolOutcomeStore, local_database_process_lock,
        )

        database, started, release = map(Path, sys.argv[1:4])

        class EmptyArguments(ToolArguments):
            pass

        class ScriptedModel:
            def __init__(self):
                self.responses = iter((
                    '{"kind":"tool","name":"write","arguments":{}}',
                    '{"kind":"final","content":"done"}',
                ))

            async def complete(self, _messages):
                return next(self.responses)

        async def handler():
            started.write_text("handler active", encoding="utf-8")
            while not release.exists():
                await asyncio.sleep(0.01)
            return {"ok": True}

        service = AgentExecutionService(
            model=ScriptedModel(),
            tools=[Tool("write", handler, EmptyArguments)],
            cancellation=CancellationController(audit_writer=lambda _event: None),
            tool_policy=lambda _context: ToolPolicyDecision(True),
            outcome_store=SQLiteToolOutcomeStore(database),
        )
        asyncio.run(service.run("private prompt", run_id="private-lock-run"))
        # Keep this test-helper checkpoint in the same cooperative lock domain
        # as executor initialization and dispatch; otherwise SQLite may race
        # a fresh process opening the WAL while it is being truncated.
        with local_database_process_lock(database, nonblocking=False):
            connection = sqlite3.connect(database, timeout=5.0)
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                connection.close()
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, str(database), str(started), str(release)],
        cwd=repository_root, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    return child, started, release


def _start_prepared_queued_executor(
    database: Path, directory: Path,
):
    """Start a real executor with its store initialized before lock contention."""
    _private_directory(directory)
    ready = directory / "queued-executor-ready.marker"
    start = directory / "queued-executor-start.marker"
    waiting = directory / "queued-executor-lock-contended.marker"
    handler_started = directory / "queued-executor-handler-started.marker"
    repository_root = Path(__file__).resolve().parents[1]
    child_code = textwrap.dedent("""
        import asyncio
        import fcntl
        import sys
        import time
        from pathlib import Path
        from backend.app.agent_execution import (
            AgentExecutionService, CancellationController, Tool,
            ToolArguments, ToolPolicyDecision,
        )
        from backend.app import tool_outcome_store as store_module
        from backend.app.tool_outcome_store import SQLiteToolOutcomeStore

        database, ready, start, waiting, handler_started = map(Path, sys.argv[1:6])
        store = SQLiteToolOutcomeStore(database)
        original_flock = store_module.fcntl.flock

        def observed_flock(descriptor, operation):
            try:
                return original_flock(descriptor, operation)
            except BlockingIOError:
                if operation & fcntl.LOCK_NB and not waiting.exists():
                    waiting.write_text("lock is held", encoding="utf-8")
                raise

        store_module.fcntl.flock = observed_flock

        class EmptyArguments(ToolArguments):
            pass

        class ScriptedModel:
            def __init__(self):
                self.responses = iter((
                    '{"kind":"tool","name":"write","arguments":{}}',
                    '{"kind":"final","content":"done"}',
                ))

            async def complete(self, _messages):
                return next(self.responses)

        async def handler():
            handler_started.write_text("handler active", encoding="utf-8")
            return {"ok": True}

        service = AgentExecutionService(
            model=ScriptedModel(),
            tools=[Tool("write", handler, EmptyArguments)],
            cancellation=CancellationController(audit_writer=lambda _event: None),
            tool_policy=lambda _context: ToolPolicyDecision(True),
            outcome_store=store,
        )
        ready.write_text("store initialized", encoding="utf-8")
        deadline = time.monotonic() + 20
        while not start.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("executor start marker not received")
            time.sleep(0.01)
        asyncio.run(service.run("task", run_id="cross-process-run"))
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.Popen(
        [
            sys.executable, "-c", child_code, str(database), str(ready), str(start),
            str(waiting), str(handler_started),
        ],
        cwd=repository_root, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    return child, ready, start, waiting, handler_started


def _start_fresh_executor_while_database_lock_is_held(
    database: Path, directory: Path,
):
    """Start a process whose store initialization contends with an active run."""
    _private_directory(directory)
    init_lock_attempt = directory / "store-init-lock-attempt.marker"
    store_ready = directory / "store-init-ready.marker"
    handler_started = directory / "store-init-handler-started.marker"
    repository_root = Path(__file__).resolve().parents[1]
    child_code = textwrap.dedent("""
        import asyncio
        import fcntl
        import sys
        from pathlib import Path
        from backend.app.agent_execution import (
            AgentExecutionService, CancellationController, Tool,
            ToolArguments, ToolPolicyDecision,
        )
        from backend.app import tool_outcome_store as store_module
        from backend.app.tool_outcome_store import SQLiteToolOutcomeStore

        database, attempt, ready, handler_started = map(Path, sys.argv[1:5])
        original_flock = store_module.fcntl.flock

        def mark_store_init_lock_attempt(descriptor, operation):
            if operation & fcntl.LOCK_EX and not attempt.exists():
                attempt.write_text("initialization locking", encoding="utf-8")
            return original_flock(descriptor, operation)

        store_module.fcntl.flock = mark_store_init_lock_attempt
        store = SQLiteToolOutcomeStore(database)
        ready.write_text("store initialized", encoding="utf-8")

        class EmptyArguments(ToolArguments):
            pass

        class ScriptedModel:
            def __init__(self):
                self.responses = iter((
                    '{"kind":"tool","name":"write","arguments":{}}',
                    '{"kind":"final","content":"done"}',
                ))

            async def complete(self, _messages):
                return next(self.responses)

        async def handler():
            handler_started.write_text("handler active", encoding="utf-8")
            return {"ok": True}

        service = AgentExecutionService(
            model=ScriptedModel(),
            tools=[Tool("write", handler, EmptyArguments)],
            cancellation=CancellationController(audit_writer=lambda _event: None),
            tool_policy=lambda _context: ToolPolicyDecision(True),
            outcome_store=store,
        )
        asyncio.run(service.run("task", run_id="fresh-process-run"))
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.Popen(
        [
            sys.executable, "-c", child_code, str(database), str(init_lock_attempt),
            str(store_ready), str(handler_started),
        ],
        cwd=repository_root, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    return child, init_lock_attempt, store_ready, handler_started


def _wait_for_marker(child: subprocess.Popen, marker: Path) -> None:
    _wait_for_marker_content(child, marker, "handler active")


def _wait_for_marker_content(
    child: subprocess.Popen, marker: Path, expected_content: str,
) -> None:
    deadline = time.monotonic() + 10
    while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.is_file(), "executor did not reach its handler synchronization point"
    assert marker.read_text(encoding="utf-8") == expected_content


def _drain_child(child: subprocess.Popen, *, timeout: float = 5) -> tuple[str, str]:
    """Boundedly terminate if needed, always draining pipes and reaping the child."""
    if child.poll() is None:
        child.terminate()
    try:
        return child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if child.poll() is None:
            child.kill()
        return child.communicate(timeout=timeout)


def test_cli_backup_verify_and_restore_report_metadata_only(tmp_path, capsys):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup_dir = _private_directory(tmp_path / "backups")
    backup = backup_dir / _backup_name(datetime.now(timezone.utc))

    assert main(["backup", "--database", str(source.path), "--destination", str(backup)]) == 0
    backup_output = json.loads(capsys.readouterr().out)
    assert backup_output["status"] == "OK"
    assert backup_output["integrity"] == "ok"
    assert backup_output["event_count"] == 2
    assert "cli-run" not in json.dumps(backup_output)

    assert main(["verify", "--database", str(backup)]) == 0
    assert json.loads(capsys.readouterr().out)["integrity"] == "ok"

    restored_path = tmp_path / "restored" / "outcomes.sqlite3"
    assert main(["restore", "--backup", str(backup), "--destination",
                 str(restored_path)]) == 0
    restored_output = json.loads(capsys.readouterr().out)
    assert restored_output["operation"] == "restore"
    assert restored_output["event_count"] == 2
    assert SQLiteToolOutcomeStore(restored_path).events("cli-run") == source.events("cli-run")


@pytest.mark.parametrize("contents", [b"not a sqlite database", b""])
def test_cli_rejects_corrupt_or_incomplete_database_without_details(
    tmp_path, capsys, contents: bytes,
):
    directory = _private_directory(tmp_path / "candidate")
    candidate = directory / "candidate.sqlite3"
    if contents:
        candidate.write_bytes(contents)
    else:
        with sqlite3.connect(candidate):
            pass
    if os.name == "posix":
        os.chmod(candidate, 0o600)

    assert main(["verify", "--database", str(candidate)]) == 2
    report = capsys.readouterr().out
    assert json.loads(report)["status"] == "ERROR"
    assert "not a sqlite database" not in report
    assert "candidate.sqlite3" not in report


@pytest.mark.parametrize(
    "schema_error",
    ["missing_column", "wrong_type", "wrong_nullability", "missing_unique",
     "wrong_status_check"],
)
def test_schema_contract_is_shared_by_verify_restore_retention_and_drill(
    tmp_path, capsys, schema_error: str,
):
    backup_directory = _private_directory(tmp_path / "schema-backups")
    invalid_backup = _invalid_schema_backup(backup_directory, schema_error)
    now = datetime(2025, 1, 7, tzinfo=timezone.utc)

    assert main(["verify", "--database", str(invalid_backup)]) == 2
    verify_report = json.loads(capsys.readouterr().out)
    assert verify_report["reason"] == "schema_invalid"

    destination = _private_directory(tmp_path / "schema-restore") / "restored.sqlite3"
    assert main(["restore", "--backup", str(invalid_backup),
                 "--destination", str(destination)]) == 2
    restore_report = json.loads(capsys.readouterr().out)
    assert restore_report["reason"] == "schema_invalid"
    assert not destination.exists()

    plan = plan_retention(backup_directory, now)
    assert plan["expiration_candidates"] == []
    assert plan["unverified"] == [{
        "name": invalid_backup.name,
        "reason": "schema_invalid",
    }]

    assert main(["restore-drill", "--backup", str(invalid_backup)]) == 2
    drill_report = json.loads(capsys.readouterr().out)
    assert drill_report["status"] == "FAIL"
    assert drill_report["reason"] == "schema_invalid"


def test_cli_verify_fails_closed_for_nonempty_wal_without_mutating_it(tmp_path, capsys):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    wal = Path(f"{store.path}-wal")
    wal.write_bytes(b"uncheckpointed-wal-marker")
    before = wal.read_bytes()

    assert main(["verify", "--database", str(store.path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason"] == "writer_must_be_stopped"
    assert wal.read_bytes() == before


def _recovery_input_snapshot(database: Path) -> dict[str, tuple[str, int, int, int] | None]:
    """Capture database and sidecar identity/content without following links."""
    snapshot = {}
    for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        try:
            info = path.lstat()
        except FileNotFoundError:
            snapshot[str(path)] = None
            continue
        digest = ""
        if stat.S_ISREG(info.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISLNK(info.st_mode):
            digest = os.readlink(path)
        snapshot[str(path)] = (
            digest, stat.S_IMODE(info.st_mode), info.st_size, info.st_mtime_ns
        )
    return snapshot


def test_recover_incomplete_cli_marks_unknown_and_is_idempotent(
    tmp_path, capsys,
):
    store = SQLiteToolOutcomeStore(tmp_path / "recovery" / "outcomes.sqlite3")
    assert store.record_dispatch("private-recovery-run", 1, "private-tool")
    # Use a standalone SQLite backup to represent a stopped executor with a
    # checkpointed dispatch and no live writer sidecars.
    database = store.backup_to(tmp_path / "recovery-copy" / "recovery.sqlite3")

    args = ["recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped"]
    assert main(args) == 0
    first_output = capsys.readouterr().out
    assert json.loads(first_output) == {
        "operation": "recover-incomplete", "recovered_count": 1, "status": "OK"
    }
    assert "private-recovery-run" not in first_output
    assert "private-tool" not in first_output
    recovered_store = SQLiteToolOutcomeStore(database)
    terminal_events = [
        event for event in recovered_store.events("private-recovery-run")
        if event["event_type"] == "terminal"
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0]["status"] == "outcome_unknown"
    assert terminal_events[0]["reason_code"] == "tool_outcome_unknown"

    assert main(args) == 0
    second_output = capsys.readouterr().out
    assert json.loads(second_output) == {
        "operation": "recover-incomplete", "recovered_count": 0, "status": "OK"
    }
    assert "private-recovery-run" not in second_output
    assert "private-tool" not in second_output


def test_recover_incomplete_requires_explicit_operator_confirmation_without_mutation(
    tmp_path, capsys,
):
    store = SQLiteToolOutcomeStore(tmp_path / "recovery" / "outcomes.sqlite3")
    assert store.record_dispatch("private-recovery-run", 1, "private-tool")
    database = store.backup_to(tmp_path / "recovery-copy" / "recovery.sqlite3")
    before = _recovery_input_snapshot(database)

    assert main(["recover-incomplete", "--database", str(database)]) == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "operation": "recover-incomplete", "reason": "executor_stop_not_confirmed",
        "status": "ERROR",
    }
    assert "private-recovery-run" not in output
    assert "private-tool" not in output
    assert _recovery_input_snapshot(database) == before


def test_recover_incomplete_requires_absolute_database_path(capsys):
    assert main([
        "recover-incomplete", "--database", "relative/outcomes.sqlite3",
        "--confirm-executor-stopped",
    ]) == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "operation": "recover-incomplete", "reason": "path_must_be_absolute",
        "status": "ERROR",
    }
    assert "outcomes.sqlite3" not in output


@pytest.mark.skipif(os.name != "posix", reason="local fcntl lock is POSIX-only")
def test_recovery_is_rejected_while_real_executor_holds_process_lock_then_succeeds(
    tmp_path, capsys,
):
    database = _valid_database(tmp_path / "locked-executor" / "outcomes.sqlite3").path
    child, started, release = _start_blocked_agent_executor(database, tmp_path)
    try:
        _wait_for_marker(child, started)
        before = _recovery_input_snapshot(database)
        assert main([
            "recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped",
        ]) == 2
        output = capsys.readouterr().out
        assert json.loads(output) == {
            "operation": "recover-incomplete", "reason": "executor_active",
            "status": "ERROR",
        }
        assert "private-lock-run" not in output
        assert "write" not in output
        assert _recovery_input_snapshot(database) == before

        release.write_text("continue", encoding="utf-8")
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, stderr
        assert "private-lock-run" not in stdout
        assert "private prompt" not in stdout
    finally:
        _drain_child(child)

    assert main([
        "recover-incomplete", "--database", str(database),
        "--confirm-executor-stopped",
    ]) == 0
    output = capsys.readouterr().out
    assert json.loads(output) == {
        "operation": "recover-incomplete", "recovered_count": 0, "status": "OK"
    }


@pytest.mark.skipif(os.name != "posix", reason="local fcntl lock is POSIX-only")
def test_process_termination_releases_executor_lock_for_guarded_recovery(
    tmp_path, capsys,
):
    database = tmp_path / "terminated-executor" / "outcomes.sqlite3"
    child, started, _release = _start_blocked_agent_executor(
        database, tmp_path / "child-files"
    )
    try:
        _wait_for_marker(child, started)
        child.terminate()
        _stdout, _stderr = child.communicate(timeout=5)
        assert child.returncode != 0
    finally:
        _drain_child(child)

    # The dead process releases flock. Reopen and checkpoint its committed
    # dispatch before the CLI's deliberate nonempty-WAL refusal check.
    connection = sqlite3.connect(database, timeout=5.0)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute(
            "SELECT count(*) FROM tool_outcome_events WHERE event_type='dispatch'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM tool_outcome_events WHERE event_type='terminal'"
        ).fetchone()[0] == 0
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()

    args = ["recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped"]
    assert main(args) == 0
    first_output = capsys.readouterr().out
    assert json.loads(first_output) == {
        "operation": "recover-incomplete", "recovered_count": 1, "status": "OK"
    }
    assert main(args) == 0
    second_output = capsys.readouterr().out
    assert json.loads(second_output) == {
        "operation": "recover-incomplete", "recovered_count": 0, "status": "OK"
    }
    for output in (first_output, second_output):
        assert "private-lock-run" not in output
        assert "write" not in output


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_separate_executor_processes_queue_dispatches_through_terminal_write(
    tmp_path, capsys,
):
    database = _private_directory(tmp_path / "cross-process-store") / "outcomes.sqlite3"
    # Initialize the shared schema before either child begins its run.
    SQLiteToolOutcomeStore(database)
    queued_child, ready, start_queued, lock_waiting, queued_handler_started = (
        _start_prepared_queued_executor(database, tmp_path / "queued-child")
    )
    first_child = None
    first_started = tmp_path / "first-child" / "executor-handler-started.marker"
    first_release = tmp_path / "first-child" / "executor-release.marker"
    try:
        _wait_for_marker_content(queued_child, ready, "store initialized")
        first_child, first_started, first_release = _start_blocked_agent_executor(
            database, tmp_path / "first-child"
        )
        _wait_for_marker(first_child, first_started)

        start_queued.write_text("run", encoding="utf-8")
        _wait_for_marker_content(queued_child, lock_waiting, "lock is held")
        assert not queued_handler_started.exists()

        assert main([
            "recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped",
        ]) == 2
        recovery_output = capsys.readouterr().out
        assert json.loads(recovery_output) == {
            "operation": "recover-incomplete", "reason": "executor_active",
            "status": "ERROR",
        }
        assert "private-lock-run" not in recovery_output
        assert "cross-process-run" not in recovery_output

        first_release.write_text("continue", encoding="utf-8")
        _wait_for_marker_content(queued_child, queued_handler_started, "handler active")
        first_stdout, first_stderr = first_child.communicate(timeout=10)
        queued_stdout, queued_stderr = queued_child.communicate(timeout=10)
        assert first_child.returncode == 0, first_stderr
        assert queued_child.returncode == 0, queued_stderr
        assert "private-lock-run" not in first_stdout
        assert "cross-process-run" not in queued_stdout

        # Inspect event ordering only; do not print database rows or contents.
        with sqlite3.connect(database, timeout=5.0) as connection:
            ordered_events = connection.execute(
                "SELECT run_id, event_type, status "
                "FROM tool_outcome_events ORDER BY sequence"
            ).fetchall()
        assert ordered_events == [
            ("private-lock-run", "dispatch", "in_flight"),
            ("private-lock-run", "terminal", "completed"),
            ("cross-process-run", "dispatch", "in_flight"),
            ("cross-process-run", "terminal", "completed"),
        ]
    finally:
        first_release.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        first_release.write_text("cleanup", encoding="utf-8")
        start_queued.write_text("cleanup", encoding="utf-8")
        for child in (first_child, queued_child):
            if child is not None:
                _drain_child(child)


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_fresh_executor_store_initialization_waits_for_active_dispatch(
    tmp_path, capsys,
):
    database = _private_directory(tmp_path / "fresh-process-store") / "outcomes.sqlite3"
    SQLiteToolOutcomeStore(database)
    first_child, first_started, first_release = _start_blocked_agent_executor(
        database, tmp_path / "active-child"
    )
    second_child = None
    try:
        _wait_for_marker(first_child, first_started)
        second_child, init_attempt, store_ready, second_handler_started = (
            _start_fresh_executor_while_database_lock_is_held(
                database, tmp_path / "fresh-child"
            )
        )
        _wait_for_marker_content(second_child, init_attempt, "initialization locking")

        assert main([
            "recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped",
        ]) == 2
        recovery_output = capsys.readouterr().out
        assert json.loads(recovery_output) == {
            "operation": "recover-incomplete", "reason": "executor_active",
            "status": "ERROR",
        }
        assert "private-lock-run" not in recovery_output
        assert "fresh-process-run" not in recovery_output
        assert not store_ready.exists()
        assert not second_handler_started.exists()
        assert second_child.poll() is None

        first_release.write_text("continue", encoding="utf-8")
        _wait_for_marker_content(second_child, store_ready, "store initialized")
        _wait_for_marker_content(
            second_child, second_handler_started, "handler active"
        )
        first_stdout, first_stderr = first_child.communicate(timeout=10)
        second_stdout, second_stderr = second_child.communicate(timeout=10)
        assert first_child.returncode == 0, first_stderr
        assert second_child.returncode == 0, second_stderr
        assert "private-lock-run" not in first_stdout
        assert "fresh-process-run" not in second_stdout

        with sqlite3.connect(database, timeout=5.0) as connection:
            ordered_events = connection.execute(
                "SELECT run_id, event_type, status "
                "FROM tool_outcome_events ORDER BY sequence"
            ).fetchall()
        assert ordered_events == [
            ("private-lock-run", "dispatch", "in_flight"),
            ("private-lock-run", "terminal", "completed"),
            ("fresh-process-run", "dispatch", "in_flight"),
            ("fresh-process-run", "terminal", "completed"),
        ]
    finally:
        first_release.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        first_release.write_text("cleanup", encoding="utf-8")
        for child in (first_child, second_child):
            if child is not None:
                _drain_child(child)


@pytest.mark.skipif(os.name != "posix", reason="local fcntl lock is POSIX-only")
@pytest.mark.parametrize("lock_kind", ["symlink", "unsafe_permissions"])
def test_process_lock_rejects_symlink_and_unsafe_permissions_without_mutation(
    tmp_path, capsys, lock_kind: str,
):
    store = SQLiteToolOutcomeStore(tmp_path / "lock-safety" / "outcomes.sqlite3")
    connection = sqlite3.connect(store.path, timeout=5.0)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    Path(f"{store.path}-wal").unlink(missing_ok=True)
    Path(f"{store.path}-shm").unlink(missing_ok=True)
    lock_path = Path(f"{store.path}.lock")
    lock_path.unlink()
    sentinel = tmp_path / "private-lock-sentinel"
    sentinel.write_bytes(b"sentinel-lock-bytes")
    if os.name == "posix":
        os.chmod(sentinel, 0o640)
    sentinel_before = (
        sentinel.read_bytes(), stat.S_IMODE(sentinel.stat().st_mode),
        sentinel.stat().st_mtime_ns,
    )
    if lock_kind == "symlink":
        lock_path.symlink_to(sentinel)
    else:
        lock_path.write_bytes(b"existing lock data")
        os.chmod(lock_path, 0o644)
    lock_before = (
        os.readlink(lock_path) if lock_path.is_symlink() else lock_path.read_bytes(),
        stat.S_IMODE(lock_path.lstat().st_mode), lock_path.lstat().st_mtime_ns,
    )
    database_before = _recovery_input_snapshot(store.path)

    with pytest.raises(ToolOutcomeLockError) as error:
        with store.execution_lock():
            pytest.fail("unsafe lock path must not be acquired")
    assert error.value.reason == "lock_path_unsafe"
    assert main([
        "recover-incomplete", "--database", str(store.path),
        "--confirm-executor-stopped",
    ]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report == {
        "operation": "recover-incomplete", "reason": "lock_path_unsafe",
        "status": "ERROR",
    }
    assert str(sentinel) not in json.dumps(report)
    assert "sentinel-lock-bytes" not in json.dumps(report)
    assert _recovery_input_snapshot(store.path) == database_before
    assert (
        os.readlink(lock_path) if lock_path.is_symlink() else lock_path.read_bytes(),
        stat.S_IMODE(lock_path.lstat().st_mode), lock_path.lstat().st_mtime_ns,
    ) == lock_before
    assert (
        sentinel.read_bytes(), stat.S_IMODE(sentinel.stat().st_mode),
        sentinel.stat().st_mtime_ns,
    ) == sentinel_before


def test_recover_incomplete_rejects_live_nonempty_wal_without_mutation(
    tmp_path, capsys,
):
    store = _valid_database(tmp_path / "live-recovery" / "outcomes.sqlite3")
    database = store.path
    writer = sqlite3.connect(database, timeout=5.0)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute(
            "INSERT INTO tool_outcome_events "
            "(run_id, step_number, tool_name, event_type, status, reason_code, occurred_at) "
            "VALUES (?, 1, ?, 'dispatch', 'in_flight', NULL, ?)",
            ("private-live-recovery-run", "private-tool", "2026-11-06T00:00:00+00:00"),
        )
        writer.commit()
        wal = Path(f"{database}-wal")
        shm = Path(f"{database}-shm")
        assert wal.is_file() and wal.stat().st_size > 0
        assert shm.is_file()
        if os.name == "posix":
            for path in (database, wal, shm):
                os.chmod(path, 0o600)
        before = _recovery_input_snapshot(database)

        assert main([
            "recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped",
        ]) == 2
        output = capsys.readouterr().out
        assert json.loads(output) == {
            "operation": "recover-incomplete", "reason": "writer_must_be_stopped",
            "status": "ERROR",
        }
        assert "private-live-recovery-run" not in output
        assert "private-tool" not in output
        assert _recovery_input_snapshot(database) == before
        assert writer.execute(
            "SELECT 1 FROM tool_outcome_events WHERE run_id=? "
            "AND event_type='dispatch'", ("private-live-recovery-run",),
        ).fetchone() is not None
    finally:
        writer.close()


@pytest.mark.parametrize("database_kind", [
    "missing", "symlink", "corrupt", "schema_invalid", "nonempty_wal",
    "unsafe_sidecar",
])
def test_recover_incomplete_rejects_invalid_database_before_mutation(
    tmp_path, capsys, database_kind: str,
):
    directory = _private_directory(tmp_path / "recovery-input")
    sentinel = tmp_path / "private-recovery-sentinel.sqlite3"
    if database_kind == "missing":
        database = directory / "missing.sqlite3"
        expected_reason = "not_a_regular_file"
    elif database_kind == "symlink":
        valid = _valid_database(directory / "valid.sqlite3")
        sentinel.write_bytes(valid.path.read_bytes())
        if os.name == "posix":
            os.chmod(sentinel, 0o600)
        database = directory / "linked.sqlite3"
        database.symlink_to(sentinel)
        expected_reason = "not_a_regular_file"
    elif database_kind == "corrupt":
        database = directory / "corrupt.sqlite3"
        database.write_bytes(b"private-corruption-marker")
        if os.name == "posix":
            os.chmod(database, 0o600)
        expected_reason = "database_unreadable"
    elif database_kind == "schema_invalid":
        database = _invalid_schema_backup(directory, "missing_column")
        expected_reason = "schema_invalid"
    else:
        store = _valid_database(directory / f"{database_kind}-seed.sqlite3")
        database = store.backup_to(directory / f"{database_kind}.sqlite3")
        if database_kind == "nonempty_wal":
            wal = Path(f"{database}-wal")
            wal.write_bytes(b"private-uncheckpointed-wal-marker")
            if os.name == "posix":
                os.chmod(wal, 0o600)
            expected_reason = "writer_must_be_stopped"
        else:
            wal = Path(f"{database}-wal")
            wal.unlink(missing_ok=True)
            sentinel.write_bytes(b"private-sidecar-sentinel-marker")
            if os.name == "posix":
                os.chmod(sentinel, 0o640)
            wal.symlink_to(sentinel)
            expected_reason = "sidecar_path_unsafe"

    before = _recovery_input_snapshot(database)
    sentinel_before = (
        (sentinel.read_bytes(), stat.S_IMODE(sentinel.stat().st_mode),
         sentinel.stat().st_mtime_ns)
        if sentinel.exists() and not sentinel.is_symlink() else None
    )
    assert main([
        "recover-incomplete", "--database", str(database),
        "--confirm-executor-stopped",
    ]) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report == {
        "operation": "recover-incomplete", "reason": expected_reason,
        "status": "ERROR",
    }
    assert "private-recovery-sentinel" not in output
    assert "private-corruption-marker" not in output
    assert "private-uncheckpointed-wal-marker" not in output
    assert "private-sidecar-sentinel-marker" not in output
    assert "cli-run" not in output
    assert "lookup" not in output
    assert _recovery_input_snapshot(database) == before
    if sentinel_before is not None:
        assert (
            sentinel.read_bytes(), stat.S_IMODE(sentinel.stat().st_mode),
            sentinel.stat().st_mtime_ns
        ) == sentinel_before


def test_recover_incomplete_cli_termination_before_commit_is_atomic(
    tmp_path, capsys,
):
    seed = SQLiteToolOutcomeStore(tmp_path / "seed" / "outcomes.sqlite3")
    run_ids = ("crash-recovery-a", "crash-recovery-b", "crash-recovery-c")
    for run_id in run_ids:
        assert seed.record_dispatch(run_id, 1, "private-tool")
    database = seed.backup_to(tmp_path / "crash-database" / "outcomes.sqlite3")
    marker = tmp_path / "recovery-commit-reached.marker"
    repository_root = Path(__file__).resolve().parents[1]
    child_code = textwrap.dedent("""
        import sqlite3
        import sys
        import time
        from pathlib import Path

        database, marker = Path(sys.argv[1]), Path(sys.argv[2])
        original_connect = sqlite3.connect

        def traced_connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            saw_recovery_insert = False

            def trace(statement):
                nonlocal saw_recovery_insert
                normalized = " ".join(statement.upper().split())
                if normalized.startswith("INSERT INTO TOOL_OUTCOME_EVENTS"):
                    saw_recovery_insert = True
                elif saw_recovery_insert and normalized == "COMMIT":
                    marker.write_text("recovery inserts executed", encoding="utf-8")
                    while True:
                        time.sleep(0.02)

            connection.set_trace_callback(trace)
            return connection

        sqlite3.connect = traced_connect
        from scripts.agent_execution_store_admin import main
        raise SystemExit(main([
            "recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped",
        ]))
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, str(database), str(marker)],
        cwd=repository_root, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.is_file(), "child did not reach the pre-commit synchronization point"
        assert marker.read_text(encoding="utf-8") == "recovery inserts executed"
        child.terminate()
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode != 0
        for sensitive in (*run_ids, "private-tool", "recovery inserts executed"):
            assert sensitive not in stdout
            assert sensitive not in stderr
    finally:
        _drain_child(child)

    # A normal SQLite reopen performs recovery of any uncommitted WAL frames.
    # Inspect the transaction result, validate schema/integrity, and checkpoint
    # before invoking the CLI, which intentionally rejects nonempty WAL input.
    connection = sqlite3.connect(database, timeout=5.0)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        admin_cli.validate_event_schema(connection)
        assert connection.execute(
            "SELECT count(*) FROM tool_outcome_events WHERE event_type='dispatch'"
        ).fetchone()[0] == len(run_ids)
        assert connection.execute(
            "SELECT count(*) FROM tool_outcome_events WHERE event_type='terminal'"
        ).fetchone()[0] == 0
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()

    args = ["recover-incomplete", "--database", str(database),
            "--confirm-executor-stopped"]
    assert main(args) == 0
    first_output = capsys.readouterr().out
    assert json.loads(first_output) == {
        "operation": "recover-incomplete", "recovered_count": len(run_ids),
        "status": "OK",
    }
    assert main(args) == 0
    second_output = capsys.readouterr().out
    assert json.loads(second_output) == {
        "operation": "recover-incomplete", "recovered_count": 0, "status": "OK"
    }
    for output in (first_output, second_output):
        for sensitive in (*run_ids, "private-tool"):
            assert sensitive not in output

    verify = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        assert verify.execute(
            "SELECT count(*) FROM tool_outcome_events "
            "WHERE event_type='terminal' AND status='outcome_unknown' "
            "AND reason_code='tool_outcome_unknown'"
        ).fetchone()[0] == len(run_ids)
    finally:
        verify.close()


def test_readiness_holds_for_live_uncheckpointed_wal_without_mutation(
    tmp_path, capsys,
):
    store = _valid_database(tmp_path / "live-store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "live-backups")
    writer = sqlite3.connect(store.path, timeout=5.0)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute(
            "INSERT INTO tool_outcome_events "
            "(run_id, step_number, tool_name, event_type, status, reason_code, occurred_at) "
            "VALUES (?, 1, ?, 'dispatch', 'in_flight', NULL, ?) ",
            ("livewal-private-run-id", "livewal-private-tool", "2026-11-06T12:00:00+00:00"),
        )
        writer.commit()

        database = store.path
        wal = Path(f"{database}-wal")
        shm = Path(f"{database}-shm")
        assert wal.is_file() and wal.stat().st_size > 0
        assert shm.is_file()
        if os.name == "posix":
            os.chmod(database, 0o600)
            os.chmod(wal, 0o600)
            os.chmod(shm, 0o600)

        def snapshot():
            files = {}
            for path in (database, wal, shm):
                info = path.lstat()
                files[path.name] = (
                    path.read_bytes(), stat.S_IMODE(info.st_mode),
                    info.st_size, info.st_mtime_ns,
                )
            directory = database.parent.stat()
            backup_directory_stat = backup_directory.stat()
            return (
                files,
                sorted(path.name for path in database.parent.iterdir()),
                stat.S_IMODE(directory.st_mode), directory.st_mtime_ns,
                sorted(path.name for path in backup_directory.iterdir()),
                stat.S_IMODE(backup_directory_stat.st_mode),
                backup_directory_stat.st_mtime_ns,
            )

        before = snapshot()
        assert main(["readiness", "--database", str(database),
                     "--backup-directory", str(backup_directory)]) == 1
        output = capsys.readouterr().out
        report = json.loads(output)
        assert report["status"] == "HOLD"
        assert report["local_status"] == "HOLD"
        assert report["deployment_status"] == "HOLD"
        assert report["checks"]["database_integrity_schema"] == {
            "reason": "writer_must_be_stopped", "status": "HOLD"
        }
        assert report["checks"]["wal_shm_sidecars"]["status"] == "PASS"
        assert report["checks"]["sqlite_sidecar_permissions"]["status"] == (
            "PASS" if os.name == "posix" else "HOLD"
        )
        assert "livewal-private-run-id" not in output
        assert "livewal-private-tool" not in output
        assert snapshot() == before
    finally:
        writer.close()


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
@pytest.mark.parametrize("dangling", [False, True])
@pytest.mark.parametrize("command", ["verify", "restore", "restore-drill"])
def test_cli_rejects_symlinked_sqlite_sidecars_without_touching_targets(
    tmp_path, capsys, monkeypatch, suffix: str, dangling: bool, command: str,
):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup_dir = _private_directory(tmp_path / "backups")
    backup = source.backup_to(
        backup_dir / _backup_name(datetime.now(timezone.utc))
    )
    target_database = backup
    sidecar = Path(f"{target_database}{suffix}")
    sidecar.unlink(missing_ok=True)
    sentinel = tmp_path / "sentinel" / "outside-target.bin"
    sentinel.parent.mkdir(mode=0o700)
    sentinel_contents = b"SENTINEL-MUST-NOT-BE-READ-OR-CHMODDED"
    if not dangling:
        sentinel.write_bytes(sentinel_contents)
        if os.name == "posix":
            os.chmod(sentinel, 0o640)
    sentinel_mode = stat.S_IMODE(sentinel.stat().st_mode) if sentinel.exists() else None
    sidecar.symlink_to(sentinel)
    assert sidecar.is_symlink()
    with pytest.raises(admin_cli.ToolOutcomeSidecarError):
        admin_cli.validate_sqlite_sidecars(target_database)
    temporary_directories = _track_temporary_directories(monkeypatch, tmp_path)
    assert sidecar.is_symlink()

    if command == "verify":
        argv = ["verify", "--database", str(backup)]
    elif command == "restore":
        destination = _private_directory(tmp_path / "restore") / "restored.sqlite3"
        argv = ["restore", "--backup", str(backup), "--destination", str(destination)]
    else:
        argv = ["restore-drill", "--backup", str(backup)]

    assert sidecar.is_symlink()
    assert main(argv) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["reason"] == "sidecar_path_unsafe"
    assert "outside-target.bin" not in output
    assert sentinel_contents.decode() not in output
    assert len(temporary_directories) == 0
    if dangling:
        assert not sentinel.exists()
    else:
        assert sentinel.read_bytes() == sentinel_contents
        if os.name == "posix":
            assert stat.S_IMODE(sentinel.stat().st_mode) == sentinel_mode


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
@pytest.mark.parametrize("dangling", [False, True])
def test_online_backup_preflight_rejects_symlinked_sidecars(
    tmp_path, suffix: str, dangling: bool,
):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    sidecar = Path(f"{source.path}{suffix}")
    sidecar.unlink(missing_ok=True)
    sentinel = tmp_path / "sentinel" / "outside-target.bin"
    sentinel.parent.mkdir(mode=0o700)
    contents = b"BACKUP-SENTINEL-MUST-NOT-CHANGE"
    if not dangling:
        sentinel.write_bytes(contents)
        if os.name == "posix":
            os.chmod(sentinel, 0o640)
    mode = stat.S_IMODE(sentinel.stat().st_mode) if sentinel.exists() else None
    sidecar.symlink_to(sentinel)

    with pytest.raises(admin_cli.OperatorCLIError) as error:
        admin_cli.verify_database(source.path, include_wal=True)

    assert error.value.reason == "sidecar_path_unsafe"
    if dangling:
        assert not sentinel.exists()
    else:
        assert sentinel.read_bytes() == contents
        if os.name == "posix":
            assert stat.S_IMODE(sentinel.stat().st_mode) == mode


def test_online_backup_accepts_regular_live_wal_and_copies_its_events(
    tmp_path, capsys,
):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup_dir = _private_directory(tmp_path / "live-wal-backups")
    destination = backup_dir / _backup_name(datetime.now(timezone.utc))
    live_connection = sqlite3.connect(source.path)
    try:
        live_connection.execute("PRAGMA journal_mode=WAL")
        live_connection.execute(
            "INSERT INTO tool_outcome_events "
            "(run_id, step_number, tool_name, event_type, status, reason_code, occurred_at) "
            "VALUES ('wal-live', 1, 'lookup', 'dispatch', 'in_flight', NULL, '2026-11-06T00:00:00+00:00')"
        )
        live_connection.commit()
        wal_path = Path(f"{source.path}-wal")
        assert wal_path.is_file() and not wal_path.is_symlink()
        assert wal_path.stat().st_size > 0

        assert main(["backup", "--database", str(source.path),
                     "--destination", str(destination)]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["status"] == "OK"
        assert report["event_count"] == 3
        assert report["unresolved_dispatch_count"] == 1
    finally:
        live_connection.close()


def test_cli_restore_refuses_destination_collision_and_preserves_file(tmp_path, capsys):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup_dir = _private_directory(tmp_path / "backups")
    backup = source.backup_to(backup_dir / _backup_name(datetime.now(timezone.utc)))
    destination = _private_directory(tmp_path / "restore") / "existing.sqlite3"
    original = b"keep existing destination"
    destination.write_bytes(original)

    assert main(["restore", "--backup", str(backup), "--destination",
                 str(destination)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["reason"] == "destination_exists"
    assert destination.read_bytes() == original


def test_retention_plan_has_deterministic_utc_daily_and_weekly_boundaries(tmp_path):
    directory = _private_directory(tmp_path / "retention")
    source = _valid_database(tmp_path / "seed" / "outcomes.sqlite3")
    seed = source.backup_to(tmp_path / "seed-backup" / _backup_name(
        datetime(2025, 1, 1, tzinfo=timezone.utc)
    ))
    timestamps = [
        "20250205T100000Z", "20250205T110000Z", "20250204T120000Z",
        "20250203T120000Z", "20250202T120000Z", "20250201T120000Z",
        "20250131T120000Z", "20250130T120000Z", "20250126T120000Z",
        "20250119T120000Z", "20250112T120000Z", "20250105T120000Z",
    ]
    for value in timestamps:
        filename = f"agent-exec-outcomes-{value}.sqlite3"
        shutil.copyfile(seed, directory / filename)
        if os.name == "posix":
            os.chmod(directory / filename, 0o600)
    corrupt = directory / "agent-exec-outcomes-20241229T120000Z.sqlite3"
    corrupt.write_bytes(b"broken")
    if os.name == "posix":
        os.chmod(corrupt, 0o600)
    (directory / "notes.txt").write_text("not a backup", encoding="utf-8")

    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir() if path.is_file()
    }
    plan = plan_retention(directory, datetime(2025, 2, 5, 12, tzinfo=timezone.utc))
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.iterdir() if path.is_file()
    }

    expected_retained = {
        "agent-exec-outcomes-20250205T110000Z.sqlite3",
        "agent-exec-outcomes-20250204T120000Z.sqlite3",
        "agent-exec-outcomes-20250203T120000Z.sqlite3",
        "agent-exec-outcomes-20250202T120000Z.sqlite3",
        "agent-exec-outcomes-20250201T120000Z.sqlite3",
        "agent-exec-outcomes-20250131T120000Z.sqlite3",
        "agent-exec-outcomes-20250130T120000Z.sqlite3",
        "agent-exec-outcomes-20250126T120000Z.sqlite3",
        "agent-exec-outcomes-20250119T120000Z.sqlite3",
        "agent-exec-outcomes-20250112T120000Z.sqlite3",
    }
    assert {Path(path).name for path in plan["retain"]} == expected_retained
    assert {Path(path).name for path in plan["expiration_candidates"]} == {
        "agent-exec-outcomes-20250205T100000Z.sqlite3",
        "agent-exec-outcomes-20250105T120000Z.sqlite3",
    }
    assert plan["unverified"] == [{
        "name": corrupt.name,
        "reason": "database_unreadable",
    }]
    assert plan["unclassified"] == ["notes.txt"]
    assert plan["deletion_performed"] is False
    assert plan["schedule_created"] is False
    assert before == after


def test_retention_cli_is_read_only_and_outputs_json(tmp_path, capsys):
    directory = _private_directory(tmp_path / "retention-cli")

    assert main(["retention-plan", "--directory", str(directory),
                 "--now", "2025-01-06T00:00:00Z"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["operation"] == "retention-plan"
    assert result["retain"] == []
    assert result["expiration_candidates"] == []
    assert result["deletion_performed"] is False
    assert list(directory.iterdir()) == []


def test_readiness_reports_local_pass_but_deployment_hold_without_mutation(
    tmp_path, capsys,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "backups")
    backup = store.backup_to(
        backup_directory / _backup_name(datetime.now(timezone.utc))
    )
    # Establish a quiescent standalone local DB before asserting the report
    # itself does not create/checkpoint SQLite files.
    with sqlite3.connect(store.path) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = {
        path.name: (path.stat().st_mode, path.stat().st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest())
        for path in [store.path, backup]
    }

    assert main(["readiness", "--database", str(store.path),
                 "--backup-directory", str(backup_directory)]) == 1
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "HOLD"
    assert report["local_status"] == "PASS"
    assert report["deployment_status"] == "HOLD"
    assert all(value == "HOLD" for value in report["deployment_evidence"].values())
    assert {key: value["status"] for key, value in report["checks"].items()} == {
        "database_exists": "PASS",
        "database_integrity_schema": "PASS",
        "wal_shm_sidecars": "PASS",
        "sqlite_sidecar_permissions": "PASS" if os.name == "posix" else "HOLD",
        "database_permissions": "PASS" if os.name == "posix" else "HOLD",
        "backup_directory": "PASS" if os.name == "posix" else "HOLD",
        "retention_plan": "PASS",
        "storage_consistency": "PASS",
    }
    for secretish in ("cli-run", "lookup", "run_id", str(store.path), str(backup)):
        assert secretish not in output
    after = {
        path.name: (path.stat().st_mode, path.stat().st_size,
                    hashlib.sha256(path.read_bytes()).hexdigest())
        for path in [store.path, backup]
    }
    assert before == after
    assert sorted(path.name for path in backup_directory.iterdir()) == [backup.name]


@pytest.mark.parametrize("condition", ["missing", "unsafe_permissions", "corrupt"])
def test_readiness_holds_for_missing_database_and_fails_unsafe_or_corrupt(
    tmp_path, capsys, condition: str,
):
    if condition == "missing":
        database = tmp_path / "missing" / "outcomes.sqlite3"
        backup_directory = _private_directory(tmp_path / "backups")
        expected_status = "HOLD"
        expected_local = "HOLD"
    elif condition == "unsafe_permissions":
        store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
        database = store.path
        backup_directory = _private_directory(tmp_path / "backups")
        if os.name != "posix":
            pytest.skip("POSIX mode-bit permission check")
        os.chmod(database.parent, 0o755)
        expected_status = "FAIL"
        expected_local = "FAIL"
    else:
        database_parent = _private_directory(tmp_path / "store")
        database = database_parent / "outcomes.sqlite3"
        database.write_bytes(b"not sqlite")
        if os.name == "posix":
            os.chmod(database, 0o600)
        backup_directory = _private_directory(tmp_path / "backups")
        expected_status = "FAIL"
        expected_local = "FAIL"

    expected_exit = 1 if expected_status == "HOLD" else 2
    assert main(["readiness", "--database", str(database),
                 "--backup-directory", str(backup_directory)]) == expected_exit
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == expected_status
    assert report["local_status"] == expected_local
    assert report["deployment_status"] == "HOLD"
    assert report["status"] != "READY"


@pytest.mark.parametrize("database_kind", ["valid", "corrupt"])
def test_readiness_holds_unavailable_observation_without_downgrading_failure(
    tmp_path, capsys, monkeypatch, database_kind: str,
):
    if database_kind == "valid":
        store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
        database = store.path
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        expected_integrity_status = "PASS"
        expected_integrity_reason = None
        expected_status = "HOLD"
        expected_exit = 1
    else:
        database_parent = _private_directory(tmp_path / "store")
        database = database_parent / "outcomes.sqlite3"
        database.write_bytes(b"RAW-DATABASE-CORRUPTION-MARKER")
        if os.name == "posix":
            os.chmod(database, 0o600)
        expected_integrity_status = "FAIL"
        expected_integrity_reason = "database_unreadable"
        expected_status = "FAIL"
        expected_exit = 2

    backup_directory = _private_directory(tmp_path / "backups")
    original_observation = admin_cli._readiness_observation
    calls = 0

    def unavailable_initial_observation(database_path, backups_path):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return original_observation(database_path, backups_path)

    monkeypatch.setattr(
        admin_cli, "_readiness_observation", unavailable_initial_observation
    )
    assert main(["readiness", "--database", str(database),
                 "--backup-directory", str(backup_directory)]) == expected_exit
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == expected_status
    assert report["local_status"] == expected_status
    assert report["deployment_status"] == "HOLD"
    assert report["checks"]["storage_consistency"] == {
        "reason": "storage_observation_unavailable", "status": "HOLD"
    }
    assert report["checks"]["database_integrity_schema"]["status"] == (
        expected_integrity_status
    )
    if expected_integrity_reason is not None:
        assert report["checks"]["database_integrity_schema"]["reason"] == (
            expected_integrity_reason
        )
    for sensitive in (
        str(database), str(backup_directory), "cli-run", "lookup",
        "RAW-DATABASE-CORRUPTION-MARKER",
    ):
        assert sensitive not in output


def test_readiness_fails_for_unsafe_sidecar_and_unverified_backup(
    tmp_path, capsys,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "backups")
    bad_backup = backup_directory / _backup_name(datetime.now(timezone.utc))
    bad_backup.write_bytes(b"corrupt backup")
    if os.name == "posix":
        os.chmod(bad_backup, 0o600)
    sidecar = Path(f"{store.path}-shm")
    sidecar.unlink(missing_ok=True)
    sidecar.mkdir()

    assert main(["readiness", "--database", str(store.path),
                 "--backup-directory", str(backup_directory)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FAIL"
    assert report["checks"]["wal_shm_sidecars"]["status"] == "FAIL"
    assert report["checks"]["retention_plan"]["status"] == "FAIL"
    assert sidecar.is_dir()


def test_readiness_does_not_downgrade_unsafe_sidecar_when_database_is_missing(
    tmp_path, capsys,
):
    database_directory = _private_directory(tmp_path / "db")
    database = database_directory / "missing.sqlite3"
    sidecar = Path(f"{database}-wal")
    sidecar.mkdir()
    backup_directory = _private_directory(tmp_path / "backups")

    assert main(["readiness", "--database", str(database),
                 "--backup-directory", str(backup_directory)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["checks"]["database_exists"] == {
        "reason": "database_missing", "status": "HOLD"
    }
    assert report["checks"]["wal_shm_sidecars"] == {
        "reason": "sidecar_path_unsafe", "status": "FAIL"
    }


def test_readiness_holds_when_database_sidecar_appears_during_report(
    tmp_path, capsys, monkeypatch,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "backups")
    original_plan = admin_cli.plan_retention
    wal = Path(f"{store.path}-wal")

    def add_wal_after_plan(directory, now=None):
        result = original_plan(directory, now)
        wal.write_bytes(b"test-only-observable-new-wal")
        if os.name == "posix":
            os.chmod(wal, 0o600)
        return result

    monkeypatch.setattr(admin_cli, "plan_retention", add_wal_after_plan)
    assert main(["readiness", "--database", str(store.path),
                 "--backup-directory", str(backup_directory)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "HOLD"
    assert report["local_status"] == "HOLD"
    assert report["checks"]["storage_consistency"] == {
        "reason": "storage_changed_during_check", "status": "HOLD"
    }
    assert report["checks"]["database_integrity_schema"]["status"] == "HOLD"
    assert report["checks"]["database_integrity_schema"]["reason"] == (
        "storage_changed_during_check"
    )
    assert report["checks"]["wal_shm_sidecars"]["status"] == "HOLD"


def test_readiness_fails_if_wal_becomes_symlink_during_report(
    tmp_path, capsys, monkeypatch,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "backups")
    wal = Path(f"{store.path}-wal")
    wal.unlink(missing_ok=True)
    sentinel = tmp_path / "private-readiness-sentinel-path"
    sentinel_bytes = b"private-readiness-sentinel-content"
    sentinel.write_bytes(sentinel_bytes)
    if os.name == "posix":
        os.chmod(sentinel, 0o640)
    sentinel_mtime = sentinel.stat().st_mtime_ns
    sentinel_mode = stat.S_IMODE(sentinel.stat().st_mode)
    original_plan = admin_cli.plan_retention

    def add_symlink_after_plan(directory, now=None):
        result = original_plan(directory, now)
        wal.symlink_to(sentinel)
        return result

    monkeypatch.setattr(admin_cli, "plan_retention", add_symlink_after_plan)
    assert main(["readiness", "--database", str(store.path),
                 "--backup-directory", str(backup_directory)]) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "FAIL"
    assert report["local_status"] == "FAIL"
    assert report["checks"]["storage_consistency"] == {
        "reason": "storage_changed_during_check", "status": "HOLD"
    }
    assert report["checks"]["wal_shm_sidecars"] == {
        "reason": "sidecar_path_unsafe", "status": "FAIL"
    }
    assert wal.is_symlink()
    assert sentinel.read_bytes() == sentinel_bytes
    assert stat.S_IMODE(sentinel.stat().st_mode) == sentinel_mode
    assert sentinel.stat().st_mtime_ns == sentinel_mtime
    for sensitive in (
        str(sentinel), sentinel_bytes.decode(), "cli-run", "lookup",
    ):
        assert sensitive not in output


def test_readiness_fails_if_database_becomes_symlink_during_report(
    tmp_path, capsys, monkeypatch,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    database = store.path
    backup_directory = _private_directory(tmp_path / "backups")
    sentinel = tmp_path / "private-database-sentinel-path"
    sentinel_bytes = b"private-database-sentinel-content"
    sentinel.write_bytes(sentinel_bytes)
    if os.name == "posix":
        os.chmod(sentinel, 0o640)
    sentinel_mtime = sentinel.stat().st_mtime_ns
    sentinel_mode = stat.S_IMODE(sentinel.stat().st_mode)
    moved_database = database.with_name("checked-database-preserved.sqlite3")
    original_plan = admin_cli.plan_retention

    def replace_database_after_plan(directory, now=None):
        result = original_plan(directory, now)
        database.rename(moved_database)
        database.symlink_to(sentinel)
        return result

    monkeypatch.setattr(admin_cli, "plan_retention", replace_database_after_plan)
    assert main(["readiness", "--database", str(database),
                 "--backup-directory", str(backup_directory)]) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "FAIL"
    assert report["local_status"] == "FAIL"
    assert report["checks"]["database_exists"] == {
        "reason": "database_path_unsafe", "status": "FAIL"
    }
    assert report["checks"]["storage_consistency"] == {
        "reason": "storage_changed_during_check", "status": "HOLD"
    }
    assert database.is_symlink()
    assert moved_database.is_file()
    assert sentinel.read_bytes() == sentinel_bytes
    assert stat.S_IMODE(sentinel.stat().st_mode) == sentinel_mode
    assert sentinel.stat().st_mtime_ns == sentinel_mtime
    for sensitive in (
        str(sentinel), str(moved_database), sentinel_bytes.decode(),
        "cli-run", "lookup",
    ):
        assert sensitive not in output


def test_readiness_holds_when_backup_directory_changes_during_retention_plan(
    tmp_path, capsys, monkeypatch,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "backups")
    original_plan = admin_cli.plan_retention

    def add_entry_after_plan(directory, now=None):
        result = original_plan(directory, now)
        (backup_directory / "operator-note.txt").write_text(
            "created by deterministic test", encoding="utf-8"
        )
        return result

    monkeypatch.setattr(admin_cli, "plan_retention", add_entry_after_plan)
    assert main(["readiness", "--database", str(store.path),
                 "--backup-directory", str(backup_directory)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "HOLD"
    assert report["local_status"] == "HOLD"
    assert report["checks"]["storage_consistency"] == {
        "reason": "storage_changed_during_check", "status": "HOLD"
    }
    assert report["checks"]["retention_plan"]["status"] == "HOLD"


def test_readiness_fails_if_backup_directory_becomes_symlink_during_report(
    tmp_path, capsys, monkeypatch,
):
    store = _valid_database(tmp_path / "store" / "outcomes.sqlite3")
    backup_directory = _private_directory(tmp_path / "backups")
    sentinel_directory = _private_directory(tmp_path / "private-backup-sentinel-path")
    sentinel = sentinel_directory / "private-backup-sentinel-file"
    sentinel_bytes = b"private-backup-sentinel-content"
    sentinel.write_bytes(sentinel_bytes)
    if os.name == "posix":
        os.chmod(sentinel, 0o640)
    sentinel_mode = stat.S_IMODE(sentinel.stat().st_mode)
    sentinel_mtime = sentinel.stat().st_mtime_ns
    sentinel_directory_mode = stat.S_IMODE(sentinel_directory.stat().st_mode)
    sentinel_directory_mtime = sentinel_directory.stat().st_mtime_ns
    moved_backup_directory = backup_directory.with_name("checked-backups-preserved")
    original_plan = admin_cli.plan_retention

    def replace_backup_directory_after_plan(directory, now=None):
        result = original_plan(directory, now)
        backup_directory.rename(moved_backup_directory)
        backup_directory.symlink_to(sentinel_directory, target_is_directory=True)
        return result

    monkeypatch.setattr(admin_cli, "plan_retention", replace_backup_directory_after_plan)
    assert main(["readiness", "--database", str(store.path),
                 "--backup-directory", str(backup_directory)]) == 2
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["status"] == "FAIL"
    assert report["local_status"] == "FAIL"
    assert report["checks"]["backup_directory"] == {
        "reason": "backup_directory_invalid", "status": "FAIL"
    }
    assert report["checks"]["storage_consistency"] == {
        "reason": "storage_changed_during_check", "status": "HOLD"
    }
    assert backup_directory.is_symlink()
    assert moved_backup_directory.is_dir()
    assert sorted(path.name for path in sentinel_directory.iterdir()) == [sentinel.name]
    assert sentinel.read_bytes() == sentinel_bytes
    assert stat.S_IMODE(sentinel.stat().st_mode) == sentinel_mode
    assert sentinel.stat().st_mtime_ns == sentinel_mtime
    assert stat.S_IMODE(sentinel_directory.stat().st_mode) == sentinel_directory_mode
    assert sentinel_directory.stat().st_mtime_ns == sentinel_directory_mtime
    for sensitive in (
        str(sentinel_directory), str(sentinel), str(moved_backup_directory),
        sentinel_bytes.decode(), "cli-run", "lookup",
    ):
        assert sensitive not in output


def test_restore_drill_restores_compares_and_cleans_private_temp_directory(
    tmp_path, capsys, monkeypatch,
):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup = source.backup_to(
        tmp_path / "backup" / _backup_name(datetime.now(timezone.utc))
    )
    before_hash = hashlib.sha256(backup.read_bytes()).hexdigest()
    temporary_directories = _track_temporary_directories(monkeypatch, tmp_path)

    assert main(["restore-drill", "--backup", str(backup)]) == 0

    report_text = capsys.readouterr().out
    report = json.loads(report_text)
    assert report == {
        "event_count": 2,
        "operation": "restore-drill",
        "records_match": True,
        "status": "PASS",
        "unresolved_dispatch_count": 0,
    }
    assert "cli-run" not in report_text
    assert "lookup" not in report_text
    assert len(temporary_directories) == 1
    assert not temporary_directories[0].exists()
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == before_hash


@pytest.mark.parametrize("backup_kind", ["corrupt", "incomplete", "symlink"])
def test_restore_drill_rejects_invalid_or_symlink_backup_before_temp_creation(
    tmp_path, capsys, monkeypatch, backup_kind: str,
):
    directory = _private_directory(tmp_path / "invalid-backups")
    backup = directory / "candidate.sqlite3"
    if backup_kind == "corrupt":
        backup.write_bytes(b"not sqlite")
    elif backup_kind == "incomplete":
        with sqlite3.connect(backup):
            pass
    else:
        target = directory / "target.sqlite3"
        _valid_database(target)
        backup.symlink_to(target)
    if os.name == "posix" and not backup.is_symlink():
        os.chmod(backup, 0o600)
    temporary_directories = _track_temporary_directories(monkeypatch, tmp_path)

    assert main(["restore-drill", "--backup", str(backup)]) == 2

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FAIL"
    assert report["event_count"] is None
    assert report["unresolved_dispatch_count"] is None
    assert report["records_match"] is False
    assert temporary_directories == []


def test_restore_drill_cleans_temp_directory_after_restore_exception(
    tmp_path, capsys, monkeypatch,
):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup = source.backup_to(
        tmp_path / "backup" / _backup_name(datetime.now(timezone.utc))
    )
    temporary_directories = _track_temporary_directories(monkeypatch, tmp_path)

    def fail_restore(cls, backup_path, destination):
        raise ToolOutcomeStoreError("restore")

    monkeypatch.setattr(
        SQLiteToolOutcomeStore, "restore_from", classmethod(fail_restore)
    )
    assert main(["restore-drill", "--backup", str(backup)]) == 2

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FAIL"
    assert report["reason"] == "restore_drill_failed"
    assert len(temporary_directories) == 1
    assert not temporary_directories[0].exists()


def test_restore_drill_reports_record_mismatch_without_disclosing_rows(
    tmp_path, capsys, monkeypatch,
):
    source = _valid_database(tmp_path / "source" / "outcomes.sqlite3")
    backup = source.backup_to(
        tmp_path / "backup" / _backup_name(datetime.now(timezone.utc))
    )
    original_fingerprint = admin_cli._event_fingerprint
    calls = 0

    def mismatched_fingerprint(path):
        nonlocal calls
        calls += 1
        value = original_fingerprint(path)
        return value if calls == 1 else "different-record-digest"

    monkeypatch.setattr(admin_cli, "_event_fingerprint", mismatched_fingerprint)

    assert main(["restore-drill", "--backup", str(backup)]) == 2

    report_text = capsys.readouterr().out
    report = json.loads(report_text)
    assert report["status"] == "FAIL"
    assert report["reason"] == "records_mismatch"
    assert report["records_match"] is False
    assert report["event_count"] == 2
    assert "cli-run" not in report_text
    assert "lookup" not in report_text
    assert "different-record-digest" not in report_text


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_concurrent_same_store_runs_wait_without_overlapping_tool_handlers(
    tmp_path, capsys, monkeypatch,
):
    store = SQLiteToolOutcomeStore(tmp_path / "concurrent-runs" / "outcomes.sqlite3")

    async def scenario():
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        second_lock_waiting = asyncio.Event()
        release_first = asyncio.Event()
        release_second = asyncio.Event()
        lock_calls = 0
        original_lock = tool_outcome_store_module.async_local_database_process_lock

        @asynccontextmanager
        async def observe_lock(path, *, poll_interval=0.01, cancel_check=None):
            nonlocal lock_calls
            lock_calls += 1
            if lock_calls == 2:
                second_lock_waiting.set()
            async with original_lock(
                path, poll_interval=poll_interval, cancel_check=cancel_check
            ):
                yield

        monkeypatch.setattr(
            tool_outcome_store_module,
            "async_local_database_process_lock",
            observe_lock,
        )

        class LabelArgs(ToolArguments):
            label: str

        class PerRunModel:
            async def complete(self, messages):
                label = next(item["content"] for item in messages if item["role"] == "user")
                if any(item["role"] == "tool" for item in messages):
                    return '{"kind":"final","content":"done"}'
                return json.dumps({
                    "kind": "tool", "name": "write",
                    "arguments": {"label": label},
                })

        active_handlers = 0
        maximum_active_handlers = 0
        handler_order: list[str] = []

        async def handler(label: str):
            nonlocal active_handlers, maximum_active_handlers
            active_handlers += 1
            maximum_active_handlers = max(maximum_active_handlers, active_handlers)
            handler_order.append(label)
            try:
                if label == "first-run":
                    first_started.set()
                    await release_first.wait()
                else:
                    second_started.set()
                    await release_second.wait()
                return {"accepted": True}
            finally:
                active_handlers -= 1

        controller = CancellationController(audit_writer=lambda _event: None)
        service = AgentExecutionService(
            model=PerRunModel(),
            tools=[Tool("write", handler, LabelArgs)],
            cancellation=controller,
            tool_policy=lambda _context: ToolPolicyDecision(True),
            outcome_store=store,
        )
        first = asyncio.create_task(service.run("first-run", run_id="first-run"))
        await asyncio.wait_for(first_started.wait(), timeout=3)
        second = asyncio.create_task(service.run("second-run", run_id="second-run"))
        await asyncio.wait_for(second_lock_waiting.wait(), timeout=3)

        assert active_handlers == 1
        assert not second_started.is_set()
        assert main([
            "recover-incomplete", "--database", str(store.path),
            "--confirm-executor-stopped",
        ]) == 2
        recovery_during_first = json.loads(capsys.readouterr().out)
        assert recovery_during_first == {
            "operation": "recover-incomplete", "reason": "executor_active",
            "status": "ERROR",
        }

        release_first.set()
        first_result = await asyncio.wait_for(first, timeout=3)
        await asyncio.wait_for(second_started.wait(), timeout=3)
        assert active_handlers == 1
        assert main([
            "recover-incomplete", "--database", str(store.path),
            "--confirm-executor-stopped",
        ]) == 2
        recovery_during_second = json.loads(capsys.readouterr().out)
        assert recovery_during_second == {
            "operation": "recover-incomplete", "reason": "executor_active",
            "status": "ERROR",
        }

        release_second.set()
        second_result = await asyncio.wait_for(second, timeout=3)
        return (first_result, second_result, maximum_active_handlers, handler_order)

    first_result, second_result, max_active, order = asyncio.run(scenario())
    assert first_result["status"] == second_result["status"] == "completed"
    assert max_active == 1
    assert order == ["first-run", "second-run"]
    assert [event["status"] for event in store.events("first-run")] == [
        "in_flight", "completed",
    ]
    assert [event["status"] for event in store.events("second-run")] == [
        "in_flight", "completed",
    ]


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_default_store_initialization_waits_off_event_loop_during_dispatch(
    tmp_path, monkeypatch,
):
    database = tmp_path / "async-store-startup" / "outcomes.sqlite3"
    store = SQLiteToolOutcomeStore(database)
    init_lock_attempted = threading.Event()

    class PerRunModel:
        async def complete(self, messages):
            label = next(item["content"] for item in messages if item["role"] == "user")
            if any(item["role"] == "tool" for item in messages):
                return '{"kind":"final","content":"done"}'
            return json.dumps({
                "kind": "tool", "name": "write",
                "arguments": {"label": label},
            })

    class LabelArgs(ToolArguments):
        label: str

    async def scenario():
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()
        loop = asyncio.get_running_loop()

        async def handler(label: str):
            if label == "first-run":
                first_started.set()
                await release_first.wait()
            else:
                second_started.set()
            return {"accepted": True}

        def build_service(*, outcome_store=None):
            return AgentExecutionService(
                model=PerRunModel(),
                tools=[Tool("write", handler, LabelArgs)],
                cancellation=CancellationController(audit_writer=lambda _event: None),
                tool_policy=lambda _context: ToolPolicyDecision(True),
                outcome_store=outcome_store,
            )

        first_service = build_service(outcome_store=store)
        first_task = asyncio.create_task(
            first_service.run("first-run", run_id="async-first")
        )
        second_task = None
        try:
            await asyncio.wait_for(first_started.wait(), timeout=3)

            original_open_lock = tool_outcome_store_module._open_local_database_lock

            def observe_init_lock(path):
                if Path(path) == database:
                    init_lock_attempted.set()
                return original_open_lock(path)

            monkeypatch.setattr(
                tool_outcome_store_module, "_open_local_database_lock", observe_init_lock
            )

            # The service is deliberately constructed on this running loop.
            # Its default store is initialized lazily by run(), off-loop.
            monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
            second_service = build_service()
            second_task = asyncio.create_task(
                second_service.run("second-run", run_id="async-second")
            )
            await asyncio.wait_for(
                asyncio.to_thread(init_lock_attempted.wait, 3), timeout=4
            )

            event_loop_thread = threading.get_ident()
            synchronous_lock_modes = []
            original_process_lock = tool_outcome_store_module.local_database_process_lock

            def reject_blocking_loop_lock(path, *, nonblocking=True):
                if threading.get_ident() == event_loop_thread:
                    synchronous_lock_modes.append(nonblocking)
                    if not nonblocking:
                        raise AssertionError("event-loop constructor attempted a blocking lock")
                return original_process_lock(path, nonblocking=nonblocking)

            monkeypatch.setattr(
                tool_outcome_store_module,
                "local_database_process_lock",
                reject_blocking_loop_lock,
            )
            with pytest.raises(ToolOutcomeStoreError) as initialization_error:
                SQLiteToolOutcomeStore(database)
            assert initialization_error.value.operation == "initialize"
            assert synchronous_lock_modes == [True]

            loop_responsive = loop.create_future()
            loop.call_soon(loop_responsive.set_result, True)
            assert await asyncio.wait_for(loop_responsive, timeout=1)
            assert not second_task.done()
            assert not second_started.is_set()
            assert store.events("async-second") == []

            release_first.set()
            first_result = await asyncio.wait_for(first_task, timeout=3)
            second_result = await asyncio.wait_for(second_task, timeout=3)
            return first_result, second_result
        finally:
            release_first.set()
            for task in (first_task, second_task):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (first_task, second_task) if task is not None),
                return_exceptions=True,
            )

    first_result, second_result = asyncio.run(scenario())
    assert first_result["status"] == second_result["status"] == "completed"
    with sqlite3.connect(database) as connection:
        order = connection.execute(
            "SELECT run_id, event_type, status FROM tool_outcome_events "
            "ORDER BY sequence"
        ).fetchall()
    assert order == [
        ("async-first", "dispatch", "in_flight"),
        ("async-first", "terminal", "completed"),
        ("async-second", "dispatch", "in_flight"),
        ("async-second", "terminal", "completed"),
    ]


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_concurrent_runs_share_one_async_store_initialization(tmp_path, monkeypatch):
    database = tmp_path / "shared-store-init" / "outcomes.sqlite3"
    _private_directory(database.parent)
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
    lock = SQLiteToolOutcomeStore.lock_for_path(database)
    lock.__enter__()
    lock_held = True
    init_lock_attempted = threading.Event()
    init_calls = 0
    original_create = SQLiteToolOutcomeStore.create_async
    original_open_lock = tool_outcome_store_module._open_local_database_lock

    async def counted_create(cls, path=None):
        nonlocal init_calls
        init_calls += 1
        return await original_create(path)

    def observe_lock_attempt(path):
        if Path(path) == database:
            init_lock_attempted.set()
        return original_open_lock(path)

    monkeypatch.setattr(SQLiteToolOutcomeStore, "create_async", classmethod(counted_create))
    monkeypatch.setattr(
        tool_outcome_store_module, "_open_local_database_lock", observe_lock_attempt
    )

    class EmptyArguments(ToolArguments):
        pass

    class ToolModel:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages):
            self.calls += 1
            if any(item["role"] == "tool" for item in messages):
                return '{"kind":"final","content":"done"}'
            return json.dumps({
                "kind": "tool", "name": "write", "arguments": {},
            })

    model = ToolModel()
    active_handlers = 0
    maximum_active_handlers = 0
    controller = CancellationController(audit_writer=lambda _event: None)

    async def handler():
        nonlocal active_handlers, maximum_active_handlers
        active_handlers += 1
        maximum_active_handlers = max(maximum_active_handlers, active_handlers)
        await asyncio.sleep(0)
        active_handlers -= 1
        return {"accepted": True}

    service = AgentExecutionService(
        model=model,
        tools=[Tool("write", handler, EmptyArguments)],
        cancellation=controller,
        tool_policy=lambda _context: ToolPolicyDecision(True),
    )
    ensure_waiters = 0
    both_waiters_entered = None
    original_ensure = AgentExecutionService._ensure_outcome_store

    async def observe_waiter(service_instance, run_id):
        nonlocal ensure_waiters
        ensure_waiters += 1
        if ensure_waiters == 2:
            both_waiters_entered.set()
        await original_ensure(service_instance, run_id)

    monkeypatch.setattr(AgentExecutionService, "_ensure_outcome_store", observe_waiter)

    async def scenario():
        nonlocal both_waiters_entered, lock_held
        both_waiters_entered = asyncio.Event()
        first = asyncio.create_task(service.run("first", run_id="init-first"))
        second = asyncio.create_task(service.run("second", run_id="init-second"))
        try:
            await asyncio.wait_for(both_waiters_entered.wait(), timeout=3)
            assert await asyncio.wait_for(
                asyncio.to_thread(init_lock_attempted.wait, 3), timeout=4
            )
            assert init_calls == 1
            assert model.calls == 0

            lock.__exit__(None, None, None)
            lock_held = False
            results = await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
            return results
        finally:
            if lock_held:
                lock.__exit__(None, None, None)
                lock_held = False
            for task in (first, second):
                if not task.done():
                    task.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
            initialization = service._outcome_store_initialization_task
            if initialization is not None:
                await asyncio.wait_for(
                    asyncio.gather(initialization, return_exceptions=True), timeout=5
                )

    results = asyncio.run(scenario())
    assert [result["status"] for result in results] == ["completed", "completed"]
    assert init_calls == 1
    assert maximum_active_handlers == 1
    assert service._outcome_store_initialization_task is not None
    assert service._outcome_store_initialization_task.done()
    assert set(service._cancellation._run_cancel_events) == set()
    store = service._outcome_store
    assert store is not None
    with sqlite3.connect(database) as connection:
        events = connection.execute(
            "SELECT run_id, event_type, status FROM tool_outcome_events "
            "ORDER BY sequence"
        ).fetchall()
    assert len(events) == 4
    assert [event_type for _run_id, event_type, _status in events] == [
        "dispatch", "terminal", "dispatch", "terminal",
    ]
    assert events[0][0] == events[1][0]
    assert events[2][0] == events[3][0]
    assert events[0][0] != events[2][0]


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_cancelled_store_initialization_waiter_does_not_cancel_shared_init(
    tmp_path, monkeypatch,
):
    database = tmp_path / "cancel-store-init" / "outcomes.sqlite3"
    _private_directory(database.parent)
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
    lock = SQLiteToolOutcomeStore.lock_for_path(database)
    lock.__enter__()
    lock_held = True
    init_lock_attempted = threading.Event()
    init_calls = 0
    original_create = SQLiteToolOutcomeStore.create_async
    original_open_lock = tool_outcome_store_module._open_local_database_lock

    async def counted_create(cls, path=None):
        nonlocal init_calls
        init_calls += 1
        return await original_create(path)

    def observe_lock_attempt(path):
        if Path(path) == database:
            init_lock_attempted.set()
        return original_open_lock(path)

    monkeypatch.setattr(SQLiteToolOutcomeStore, "create_async", classmethod(counted_create))
    monkeypatch.setattr(
        tool_outcome_store_module, "_open_local_database_lock", observe_lock_attempt
    )

    class EmptyArguments(ToolArguments):
        pass

    class FinalModel:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages):
            self.calls += 1
            if any(item["role"] == "tool" for item in messages):
                return '{"kind":"final","content":"done"}'
            return '{"kind":"tool","name":"write","arguments":{}}'

    model = FinalModel()
    handler_calls = 0

    def handler():
        nonlocal handler_calls
        handler_calls += 1
        return {"accepted": True}

    service = AgentExecutionService(
        model=model,
        tools=[Tool("write", handler, EmptyArguments)],
        cancellation=CancellationController(audit_writer=lambda _event: None),
        tool_policy=lambda _context: ToolPolicyDecision(True),
    )
    ensure_waiters = 0
    both_waiters_entered = None
    original_ensure = AgentExecutionService._ensure_outcome_store

    async def observe_waiter(service_instance, run_id):
        nonlocal ensure_waiters
        ensure_waiters += 1
        if ensure_waiters == 2:
            both_waiters_entered.set()
        await original_ensure(service_instance, run_id)

    monkeypatch.setattr(AgentExecutionService, "_ensure_outcome_store", observe_waiter)

    async def scenario():
        nonlocal both_waiters_entered, lock_held
        both_waiters_entered = asyncio.Event()
        cancelled = asyncio.create_task(service.run("cancelled", run_id="init-cancelled"))
        survivor = asyncio.create_task(service.run("survivor", run_id="init-survivor"))
        try:
            await asyncio.wait_for(both_waiters_entered.wait(), timeout=3)
            assert await asyncio.wait_for(
                asyncio.to_thread(init_lock_attempted.wait, 3), timeout=4
            )
            initialization = service._outcome_store_initialization_task
            assert initialization is not None and not initialization.cancelled()

            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(cancelled, timeout=3)
            assert not initialization.cancelled()
            assert not survivor.done()
            assert model.calls == 0

            lock.__exit__(None, None, None)
            lock_held = False
            result = await asyncio.wait_for(survivor, timeout=5)
            return result
        finally:
            if lock_held:
                lock.__exit__(None, None, None)
                lock_held = False
            for task in (cancelled, survivor):
                if not task.done():
                    task.cancel()
            await asyncio.gather(cancelled, survivor, return_exceptions=True)
            initialization = service._outcome_store_initialization_task
            if initialization is not None:
                await asyncio.wait_for(
                    asyncio.gather(initialization, return_exceptions=True), timeout=5
                )

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert init_calls == 1
    assert model.calls == 2
    assert handler_calls == 1
    store = service._outcome_store
    assert store is not None
    assert set(service._cancellation._run_cancel_events) == set()
    assert store.events("init-cancelled") == []
    assert [event["status"] for event in store.events("init-survivor")] == [
        "in_flight", "completed",
    ]


@pytest.mark.parametrize("cancel_from_worker", [False, True])
@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_controller_cancellation_interrupts_only_store_initialization_waiter(
    tmp_path, monkeypatch, cancel_from_worker,
):
    database = tmp_path / "controller-cancel-store-init" / "outcomes.sqlite3"
    _private_directory(database.parent)
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
    lock = SQLiteToolOutcomeStore.lock_for_path(database)
    lock.__enter__()
    lock_held = True
    init_lock_attempted = threading.Event()
    init_calls = 0
    original_create = SQLiteToolOutcomeStore.create_async
    original_open_lock = tool_outcome_store_module._open_local_database_lock

    async def counted_create(cls, path=None):
        nonlocal init_calls
        init_calls += 1
        return await original_create(path)

    def observe_lock_attempt(path):
        if Path(path) == database:
            init_lock_attempted.set()
        return original_open_lock(path)

    monkeypatch.setattr(SQLiteToolOutcomeStore, "create_async", classmethod(counted_create))
    monkeypatch.setattr(
        tool_outcome_store_module, "_open_local_database_lock", observe_lock_attempt
    )

    class EmptyArguments(ToolArguments):
        pass

    class ToolModel:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages):
            self.calls += 1
            if any(item["role"] == "tool" for item in messages):
                return '{"kind":"final","content":"done"}'
            return '{"kind":"tool","name":"write","arguments":{}}'

    model = ToolModel()
    handler_calls = 0
    audit_events = []

    def handler():
        nonlocal handler_calls
        handler_calls += 1
        return {"accepted": True}

    controller = CancellationController(audit_writer=audit_events.append)
    service = AgentExecutionService(
        model=model,
        tools=[Tool("write", handler, EmptyArguments)],
        cancellation=controller,
        tool_policy=lambda _context: ToolPolicyDecision(True),
    )
    entered_waiters = 0
    both_waiters_entered = None
    original_ensure = AgentExecutionService._ensure_outcome_store

    async def observe_waiter(service_instance, run_id):
        nonlocal entered_waiters
        entered_waiters += 1
        if entered_waiters == 2:
            both_waiters_entered.set()
        await original_ensure(service_instance, run_id)

    monkeypatch.setattr(AgentExecutionService, "_ensure_outcome_store", observe_waiter)

    async def scenario():
        nonlocal both_waiters_entered, lock_held
        both_waiters_entered = asyncio.Event()
        cancelled = asyncio.create_task(
            service.run("private prompt marker", run_id="controller-cancelled")
        )
        survivor = asyncio.create_task(
            service.run("survivor task", run_id="controller-survivor")
        )
        try:
            await asyncio.wait_for(both_waiters_entered.wait(), timeout=3)
            assert await asyncio.wait_for(
                asyncio.to_thread(init_lock_attempted.wait, 3), timeout=4
            )
            initialization = service._outcome_store_initialization_task
            assert initialization is not None and not initialization.done()
            assert model.calls == 0 and handler_calls == 0

            if cancel_from_worker:
                cancellation_accepted = await asyncio.to_thread(
                    controller.cancel_run, "controller-cancelled",
                    actor_id="operator", scope="local",
                )
            else:
                cancellation_accepted = controller.cancel_run(
                    "controller-cancelled", actor_id="operator", scope="local"
                )
            assert cancellation_accepted is True
            cancelled_result = await asyncio.wait_for(cancelled, timeout=2)
            assert cancelled_result == {
                "run_id": "controller-cancelled", "status": "cancelled",
                "answer": None, "steps": [],
            }
            assert not initialization.cancelled() and not initialization.done()
            assert not survivor.done()
            assert model.calls == 0 and handler_calls == 0

            lock.__exit__(None, None, None)
            lock_held = False
            survivor_result = await asyncio.wait_for(survivor, timeout=5)
            return survivor_result
        finally:
            if lock_held:
                lock.__exit__(None, None, None)
                lock_held = False
            for task in (cancelled, survivor):
                if not task.done():
                    task.cancel()
            await asyncio.gather(cancelled, survivor, return_exceptions=True)
            initialization = service._outcome_store_initialization_task
            if initialization is not None:
                await asyncio.wait_for(
                    asyncio.gather(initialization, return_exceptions=True), timeout=5
                )

    survivor_result = asyncio.run(scenario())
    assert survivor_result["status"] == "completed"
    assert init_calls == 1
    assert model.calls == 2
    assert handler_calls == 1
    assert len(audit_events) == 1
    assert {key: value for key, value in audit_events[0].items()
            if key not in {"timestamp", "audit_id"}} == {
        "event": "agent_run_cancelled", "run_id": "controller-cancelled",
        "actor_id": "operator", "scope": "local",
        "reason_code": "operator_requested",
    }
    assert isinstance(audit_events[0]["timestamp"], str)
    assert "private prompt marker" not in json.dumps(audit_events)
    store = service._outcome_store
    assert store is not None
    assert set(controller._run_cancel_events) == set()
    assert store.events("controller-cancelled") == []
    assert [event["status"] for event in store.events("controller-survivor")] == [
        "in_flight", "completed",
    ]


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
@pytest.mark.parametrize("audit_failure", [False, True])
def test_disable_wakes_all_store_initialization_waiters_and_rejects_new_runs(
    tmp_path, monkeypatch, audit_failure,
):
    database = tmp_path / "disable-store-init" / "outcomes.sqlite3"
    _private_directory(database.parent)
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
    lock = SQLiteToolOutcomeStore.lock_for_path(database)
    lock.__enter__()
    lock_held = True
    init_lock_attempted = threading.Event()
    original_open_lock = tool_outcome_store_module._open_local_database_lock

    def observe_lock_attempt(path):
        if Path(path) == database:
            init_lock_attempted.set()
        return original_open_lock(path)

    monkeypatch.setattr(
        tool_outcome_store_module, "_open_local_database_lock", observe_lock_attempt
    )

    class FinalModel:
        def __init__(self):
            self.calls = 0

        async def complete(self, _messages):
            self.calls += 1
            return '{"kind":"final","content":"done"}'

    model = FinalModel()
    audit_events = []
    cancellation_audit_attempts = []
    audit_recovered = [False]

    def audit_writer(event):
        if event["event"] == "agent_run_cancelled":
            cancellation_audit_attempts.append(dict(event))
        if (audit_failure and not audit_recovered[0]
                and event["event"] == "agent_run_cancelled"
                and event["run_id"] == "disable-first"):
            raise OSError("audit writer unavailable")
        audit_events.append(event)

    controller = CancellationController(
        audit_writer=audit_writer,
        audit_outbox_path=database.parent / "cancellation-audit.sqlite3",
    )
    service = AgentExecutionService(model=model, tools=[], cancellation=controller)
    entered_waiters = 0
    all_waiters_entered = None
    original_ensure = AgentExecutionService._ensure_outcome_store

    async def observe_waiter(service_instance, run_id):
        nonlocal entered_waiters
        entered_waiters += 1
        if entered_waiters == 2:
            all_waiters_entered.set()
        await original_ensure(service_instance, run_id)

    monkeypatch.setattr(AgentExecutionService, "_ensure_outcome_store", observe_waiter)

    async def scenario():
        nonlocal all_waiters_entered, lock_held
        all_waiters_entered = asyncio.Event()
        first = asyncio.create_task(service.run("first", run_id="disable-first"))
        second = asyncio.create_task(service.run("second", run_id="disable-second"))
        try:
            await asyncio.wait_for(all_waiters_entered.wait(), timeout=3)
            assert await asyncio.wait_for(
                asyncio.to_thread(init_lock_attempted.wait, 3), timeout=4
            )
            initialization = service._outcome_store_initialization_task
            assert initialization is not None and not initialization.done()
            assert model.calls == 0

            if audit_failure:
                with pytest.raises(OSError, match="audit writer unavailable"):
                    controller.disable(actor_id="operator")
            else:
                assert controller.disable(actor_id="operator") == [
                    "disable-first", "disable-second",
                ]
            results = await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
            assert [result["status"] for result in results] == [
                "cancelled", "cancelled",
            ]
            assert not initialization.cancelled() and not initialization.done()
            assert model.calls == 0
            assert set(controller._run_cancel_events) == set()
            with pytest.raises(AgentRunRejected, match="disabled"):
                await service.run("must not start", run_id="disabled-new-run")

            if audit_failure:
                # A later disable retries only the failed audit record; the
                # successful second-run record must not be duplicated.
                audit_recovered[0] = True
                assert controller.disable(actor_id="operator") == []

            lock.__exit__(None, None, None)
            lock_held = False
            return initialization
        finally:
            if lock_held:
                lock.__exit__(None, None, None)
                lock_held = False
            for task in (first, second):
                if not task.done():
                    task.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
            initialization = service._outcome_store_initialization_task
            if initialization is not None:
                await asyncio.wait_for(
                    asyncio.gather(initialization, return_exceptions=True), timeout=5
                )

    initialization = asyncio.run(scenario())
    assert initialization.done()
    assert model.calls == 0
    cancellation_events = [
        event for event in audit_events if event["event"] == "agent_run_cancelled"
    ]
    if audit_failure:
        assert [event["run_id"] for event in cancellation_audit_attempts] == [
            "disable-first", "disable-second", "disable-first",
        ]
        assert cancellation_audit_attempts[0] == cancellation_audit_attempts[2]
        assert {event["run_id"] for event in cancellation_events} == {
            "disable-first", "disable-second",
        }
        assert len(cancellation_events) == 2
    else:
        assert [event["run_id"] for event in cancellation_audit_attempts] == [
            "disable-first", "disable-second",
        ]
        assert len(cancellation_events) == 2
        assert {event["run_id"] for event in cancellation_events} == {
            "disable-first", "disable-second",
        }
    assert set(controller._run_cancel_events) == set()


def test_disable_recovers_pending_audit_after_process_restart(tmp_path):
    audit_directory = _private_directory(tmp_path / "restart-audit")
    audit_path = audit_directory / "cancellation.jsonl"
    outbox_path = audit_directory / "outbox.sqlite3"
    _run_agent_execution_child("""
        import sys
        from pathlib import Path
        from backend.app.agent_execution import CancellationController

        outbox = Path(sys.argv[1])
        def fail_before_write(_event):
            raise OSError("audit destination unavailable")
        controller = CancellationController(
            audit_writer=fail_before_write, audit_outbox_path=outbox,
        )
        controller.begin_run("restart-audit-run")
        try:
            controller.disable(actor_id="operator")
        except OSError as error:
            assert str(error) == "audit destination unavailable"
        else:
            raise AssertionError("expected audit writer failure")
    """, str(outbox_path))
    assert outbox_path.is_file()
    with sqlite3.connect(outbox_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM pending_cancellation_audits"
        ).fetchone()[0] == 1

    _run_agent_execution_child("""
        import sys
        from pathlib import Path
        from backend.app.agent_execution import (
            CancellationController, append_cancellation_audit,
        )

        outbox, audit_path = map(Path, sys.argv[1:3])
        controller = CancellationController(
            audit_writer=lambda event: append_cancellation_audit(event, audit_path),
            audit_outbox_path=outbox,
        )
    """, str(outbox_path), str(audit_path))
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    cancellation_events = [
        event for event in events if event["event"] == "agent_run_cancelled"
    ]
    assert len(cancellation_events) == 1
    assert cancellation_events[0]["run_id"] == "restart-audit-run"
    with sqlite3.connect(outbox_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM pending_cancellation_audits"
        ).fetchone()[0] == 0


def test_default_audit_writer_deduplicates_append_then_raise_on_restart(tmp_path):
    audit_directory = _private_directory(tmp_path / "duplicate-audit")
    audit_path = audit_directory / "cancellation.jsonl"
    outbox_path = audit_directory / "outbox.sqlite3"
    _run_agent_execution_child("""
        import sys
        from pathlib import Path
        from backend.app.agent_execution import (
            CancellationController, append_cancellation_audit,
        )

        outbox, audit_path = map(Path, sys.argv[1:3])
        def append_then_fail(event):
            append_cancellation_audit(event, audit_path)
            raise OSError("writer failed after append")
        controller = CancellationController(
            audit_writer=append_then_fail, audit_outbox_path=outbox,
        )
        controller.begin_run("duplicate-audit-run")
        try:
            controller.disable(actor_id="operator")
        except OSError as error:
            assert str(error) == "writer failed after append"
        else:
            raise AssertionError("expected audit writer failure")
    """, str(outbox_path), str(audit_path))
    first_events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    first_cancellation_events = [
        event for event in first_events if event["event"] == "agent_run_cancelled"
    ]
    assert len(first_cancellation_events) == 1
    audit_id = first_cancellation_events[0]["audit_id"]

    _run_agent_execution_child("""
        import sys
        from pathlib import Path
        from backend.app.agent_execution import (
            CancellationController, append_cancellation_audit,
        )

        outbox, audit_path = map(Path, sys.argv[1:3])
        controller = CancellationController(
            audit_writer=lambda event: append_cancellation_audit(event, audit_path),
            audit_outbox_path=outbox,
        )
    """, str(outbox_path), str(audit_path))
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    cancellation_events = [
        event for event in events if event["event"] == "agent_run_cancelled"
    ]
    assert len(cancellation_events) == 1
    assert cancellation_events[0]["audit_id"] == audit_id


def test_agent_execution_asgi_entrypoint_recovers_configured_outbox_on_restart(tmp_path):
    audit_directory = _private_directory(tmp_path / "asgi-audit")
    audit_path = audit_directory / "cancellation.jsonl"
    outbox_path = audit_directory / "outbox.sqlite3"
    env_overrides = {
        "AGENT_EXECUTION_AUDIT_LOG": str(audit_path),
        "AGENT_EXECUTION_AUDIT_OUTBOX_DB": str(outbox_path),
    }
    _run_agent_execution_child("""
        from scripts.agent_execution_app import app

        controller = app.state.agent_execution_cancellation
        controller._audit_writer = lambda _event: (_ for _ in ()).throw(
            OSError("audit destination unavailable")
        )
        controller.begin_run("asgi-restart-run")
        try:
            controller.disable(actor_id="operator")
        except OSError as error:
            assert str(error) == "audit destination unavailable"
        else:
            raise AssertionError("expected audit writer failure")
    """, env_overrides=env_overrides)

    _run_agent_execution_child("""
        from scripts.agent_execution_app import app

        assert app.state.agent_execution_cancellation.enabled is True
    """, env_overrides=env_overrides)
    events = [json.loads(line) for line in audit_path.read_text().splitlines()]
    cancellation_events = [
        event for event in events if event["event"] == "agent_run_cancelled"
    ]
    assert len(cancellation_events) == 1
    assert cancellation_events[0]["run_id"] == "asgi-restart-run"
    with sqlite3.connect(outbox_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM pending_cancellation_audits"
        ).fetchone()[0] == 0


def test_store_initialization_failure_is_sanitized_and_retryable(tmp_path, monkeypatch):
    database = tmp_path / "retry-store-init" / "outcomes.sqlite3"
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
    original_create = SQLiteToolOutcomeStore.create_async
    init_calls = 0

    async def fail_once(cls, path=None):
        nonlocal init_calls
        init_calls += 1
        if init_calls == 1:
            raise ToolOutcomeStoreError("initialize")
        return await original_create(path)

    monkeypatch.setattr(SQLiteToolOutcomeStore, "create_async", classmethod(fail_once))

    class EmptyArguments(ToolArguments):
        pass

    class ToolModel:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages):
            self.calls += 1
            if any(item["role"] == "tool" for item in messages):
                return '{"kind":"final","content":"done"}'
            return '{"kind":"tool","name":"write","arguments":{}}'

    model = ToolModel()
    handler_calls = 0

    def handler():
        nonlocal handler_calls
        handler_calls += 1
        return {"accepted": True}

    controller = CancellationController(audit_writer=lambda _event: None)
    service = AgentExecutionService(
        model=model, tools=[Tool("write", handler, EmptyArguments)],
        cancellation=controller,
        tool_policy=lambda _context: ToolPolicyDecision(True),
    )

    async def scenario():
        with pytest.raises(ToolOutcomeStoreError) as failed:
            await service.run("first attempt", run_id="init-failed")
        assert failed.value.operation == "initialize"
        assert service._outcome_store is None
        assert service._outcome_store_initialization_task is None
        assert "init-failed" not in controller._run_cancel_events
        assert model.calls == 0
        assert handler_calls == 0
        result = await service.run("retry", run_id="init-retry")
        return result

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert init_calls == 2
    assert model.calls == 2
    assert handler_calls == 1
    store = service._outcome_store
    assert store is not None
    assert set(controller._run_cancel_events) == set()
    assert store.events("init-failed") == []
    assert [event["status"] for event in store.events("init-retry")] == [
        "in_flight", "completed",
    ]


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_failed_shared_initialization_after_all_waiters_cancelled_is_cleared(
    tmp_path, monkeypatch,
):
    database = tmp_path / "cancelled-init-failure" / "outcomes.sqlite3"
    _private_directory(database.parent)
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(database))
    original_create = SQLiteToolOutcomeStore.create_async
    initialization_started = asyncio.Event()
    release_initialization_failure = asyncio.Event()
    initialization_finished = asyncio.Event()
    initialization_calls = 0

    async def fail_first_initialization(cls, path=None):
        nonlocal initialization_calls
        initialization_calls += 1
        if initialization_calls == 1:
            initialization_started.set()
            await release_initialization_failure.wait()
            raise ToolOutcomeStoreError("initialize")
        return await original_create(path)

    monkeypatch.setattr(
        SQLiteToolOutcomeStore, "create_async",
        classmethod(fail_first_initialization),
    )

    class FinalModel:
        def __init__(self):
            self.calls = 0

        async def complete(self, _messages):
            self.calls += 1
            return '{"kind":"final","content":"done"}'

    model = FinalModel()
    controller = CancellationController(
        audit_writer=lambda _event: None,
        audit_outbox_path=database.parent / "cancellation-audit.sqlite3",
    )
    service = AgentExecutionService(model=model, tools=[], cancellation=controller)
    waiters_entered = asyncio.Event()
    ensure_waiter_count = 0
    original_ensure = AgentExecutionService._ensure_outcome_store

    async def observe_waiter(service_instance, run_id):
        nonlocal ensure_waiter_count
        ensure_waiter_count += 1
        if ensure_waiter_count == 2:
            waiters_entered.set()
        await original_ensure(service_instance, run_id)

    monkeypatch.setattr(AgentExecutionService, "_ensure_outcome_store", observe_waiter)

    async def scenario():
        loop = asyncio.get_running_loop()
        unhandled_task_contexts = []
        loop.set_exception_handler(
            lambda _loop, context: unhandled_task_contexts.append(context)
        )
        first = asyncio.create_task(service.run("first", run_id="init-cancel-first"))
        second = asyncio.create_task(service.run("second", run_id="init-cancel-second"))
        initialization = None
        try:
            await asyncio.wait_for(waiters_entered.wait(), timeout=3)
            await asyncio.wait_for(initialization_started.wait(), timeout=3)
            initialization = service._outcome_store_initialization_task
            assert initialization is not None and not initialization.done()
            assert initialization_calls == 1

            assert controller.disable(actor_id="operator") == [
                "init-cancel-first", "init-cancel-second",
            ]
            cancelled_results = await asyncio.wait_for(
                asyncio.gather(first, second), timeout=2
            )
            assert [result["status"] for result in cancelled_results] == [
                "cancelled", "cancelled",
            ]
            assert not initialization.done()
            assert set(controller._run_cancel_events) == set()
            assert model.calls == 0

            controller.enable(actor_id="operator")
            release_initialization_failure.set()
            initialization.add_done_callback(
                lambda _task: loop.call_soon(initialization_finished.set)
            )
            await asyncio.wait_for(initialization_finished.wait(), timeout=3)
            # The service's failure callback is registered before this test
            # callback, so the owned slot is already cleared here.
            assert service._outcome_store_initialization_task is None
            assert service._outcome_store is None

            # Drop the final direct reference and force destruction while the
            # loop exception handler is still installed. An unobserved task
            # exception would be reported through that handler.
            del initialization
            gc.collect()
            loop_turn = loop.create_future()
            loop.call_soon(loop_turn.set_result, None)
            await asyncio.wait_for(loop_turn, timeout=1)
            assert unhandled_task_contexts == []

            result = await asyncio.wait_for(
                service.run("retry", run_id="init-retry-after-cancel"), timeout=5
            )
            assert result["status"] == "completed"
            assert initialization_calls == 2
            assert model.calls == 1
            assert set(controller._run_cancel_events) == set()
            return service._outcome_store
        finally:
            release_initialization_failure.set()
            for task in (first, second):
                if not task.done():
                    task.cancel()
            await asyncio.gather(first, second, return_exceptions=True)
            pending_initialization = service._outcome_store_initialization_task
            if pending_initialization is not None:
                await asyncio.wait_for(
                    asyncio.gather(pending_initialization, return_exceptions=True),
                    timeout=5,
                )

    store = asyncio.run(scenario())
    assert store is not None
    assert store.events("init-cancel-first") == []
    assert store.events("init-cancel-second") == []
    assert store.events("init-retry-after-cancel") == []


@pytest.mark.parametrize("completion", ["failed", "cancelled"])
def test_old_initialization_completion_does_not_clear_newer_task(completion):
    async def scenario():
        loop = asyncio.get_running_loop()
        callback_observed = asyncio.Event()
        release_old_task = asyncio.Event()
        release_new_task = asyncio.Event()
        controller = CancellationController(audit_writer=lambda _event: None)
        service = AgentExecutionService(
            model=object(), tools=[], cancellation=controller,  # type: ignore[arg-type]
        )

        async def old_initialization():
            await release_old_task.wait()
            if completion == "failed":
                raise ToolOutcomeStoreError("initialize")
            return None

        async def newer_initialization():
            await release_new_task.wait()

        old_task = asyncio.create_task(old_initialization())
        service._outcome_store_initialization_task = old_task
        old_task.add_done_callback(service._outcome_store_initialization_done)
        newer_task = asyncio.create_task(newer_initialization())
        service._outcome_store_initialization_task = newer_task
        old_task.add_done_callback(
            lambda _task: loop.call_soon(callback_observed.set)
        )

        try:
            if completion == "failed":
                release_old_task.set()
            else:
                old_task.cancel()
            await asyncio.wait_for(callback_observed.wait(), timeout=2)
            assert service._outcome_store_initialization_task is newer_task
        finally:
            release_old_task.set()
            release_new_task.set()
            for task in (old_task, newer_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(old_task, newer_task, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_cancelled_owned_store_initializer_is_cleared_without_unhandled_warning(
    tmp_path, monkeypatch,
):
    initialization_started = asyncio.Event()
    never_release_initialization = asyncio.Event()
    original_create = SQLiteToolOutcomeStore.create_async

    async def pending_initialization(cls, path=None):
        initialization_started.set()
        await never_release_initialization.wait()
        return await original_create(path)

    monkeypatch.setattr(
        SQLiteToolOutcomeStore, "create_async", classmethod(pending_initialization)
    )

    async def scenario():
        loop = asyncio.get_running_loop()
        unhandled_task_contexts = []
        loop.set_exception_handler(
            lambda _loop, context: unhandled_task_contexts.append(context)
        )
        audit_directory = _private_directory(tmp_path / "cancelled-init-audit")
        controller = CancellationController(
            audit_writer=lambda _event: None,
            audit_outbox_path=audit_directory / "outbox.sqlite3",
        )

        class IdleModel:
            def __init__(self):
                self.calls = []

            async def complete(self, messages):
                self.calls.append(messages)
                return '{"kind":"final","content":"unused"}'

        model = IdleModel()
        service = AgentExecutionService(model=model, tools=[], cancellation=controller)
        run_task = asyncio.create_task(service.run("wait", run_id="cancel-init-task"))
        initialization = None
        callback_observed = asyncio.Event()
        try:
            await asyncio.wait_for(initialization_started.wait(), timeout=2)
            initialization = service._outcome_store_initialization_task
            assert initialization is not None and not initialization.done()

            controller.disable(actor_id="operator")
            result = await asyncio.wait_for(run_task, timeout=2)
            assert result["status"] == "cancelled"
            assert model.calls == []
            assert set(controller._run_cancel_events) == set()

            initialization.add_done_callback(
                lambda _task: loop.call_soon(callback_observed.set)
            )
            initialization.cancel()
            await asyncio.wait_for(callback_observed.wait(), timeout=2)
            assert initialization.cancelled()
            assert service._outcome_store_initialization_task is None

            await asyncio.gather(initialization, return_exceptions=True)
            del initialization
            gc.collect()
            loop_turn = loop.create_future()
            loop.call_soon(loop_turn.set_result, None)
            await asyncio.wait_for(loop_turn, timeout=1)
            assert unhandled_task_contexts == []
        finally:
            never_release_initialization.set()
            if not run_task.done():
                run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
            pending_initialization = service._outcome_store_initialization_task
            if pending_initialization is not None:
                pending_initialization.cancel()
                await asyncio.gather(pending_initialization, return_exceptions=True)

    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "posix", reason="local flock is POSIX-only")
def test_cancelled_run_waiting_for_store_lock_never_records_or_invokes_tool(
    tmp_path, capsys, monkeypatch,
):
    store = SQLiteToolOutcomeStore(tmp_path / "cancelled-waiter" / "outcomes.sqlite3")

    async def scenario():
        first_started = asyncio.Event()
        queued_lock_waiting = asyncio.Event()
        release_first = asyncio.Event()
        lock_calls = 0
        original_lock = tool_outcome_store_module.async_local_database_process_lock

        @asynccontextmanager
        async def observe_lock(path, *, poll_interval=0.01, cancel_check=None):
            nonlocal lock_calls
            lock_calls += 1
            if lock_calls == 2:
                queued_lock_waiting.set()
            async with original_lock(
                path, poll_interval=poll_interval, cancel_check=cancel_check
            ):
                yield

        monkeypatch.setattr(
            tool_outcome_store_module,
            "async_local_database_process_lock",
            observe_lock,
        )

        class LabelArgs(ToolArguments):
            label: str

        class PerRunModel:
            async def complete(self, messages):
                label = next(item["content"] for item in messages if item["role"] == "user")
                if any(item["role"] == "tool" for item in messages):
                    return '{"kind":"final","content":"done"}'
                return json.dumps({
                    "kind": "tool", "name": "write",
                    "arguments": {"label": label},
                })

        calls: list[str] = []

        async def handler(label: str):
            calls.append(label)
            if label == "first-run":
                first_started.set()
                await release_first.wait()
            return {"accepted": True}

        controller = CancellationController(audit_writer=lambda _event: None)
        service = AgentExecutionService(
            model=PerRunModel(),
            tools=[Tool("write", handler, LabelArgs)],
            cancellation=controller,
            tool_policy=lambda _context: ToolPolicyDecision(True),
            outcome_store=store,
        )
        first = asyncio.create_task(service.run("first-run", run_id="first-run"))
        await asyncio.wait_for(first_started.wait(), timeout=3)
        queued = asyncio.create_task(service.run("queued-run", run_id="queued-run"))
        await asyncio.wait_for(queued_lock_waiting.wait(), timeout=3)

        assert controller.cancel_run("queued-run") is True
        queued_result = await asyncio.wait_for(queued, timeout=3)
        assert queued_result["status"] == "cancelled"
        assert queued_result["steps"] == [{
            "step": 1, "type": "tool", "name": "write", "status": "not_dispatched",
        }]
        assert calls == ["first-run"]
        assert store.events("queued-run") == []
        assert main([
            "recover-incomplete", "--database", str(store.path),
            "--confirm-executor-stopped",
        ]) == 2
        assert json.loads(capsys.readouterr().out) == {
            "operation": "recover-incomplete", "reason": "executor_active",
            "status": "ERROR",
        }

        release_first.set()
        first_result = await asyncio.wait_for(first, timeout=3)
        return first_result

    assert asyncio.run(scenario())["status"] == "completed"
    assert [event["status"] for event in store.events("first-run")] == [
        "in_flight", "completed",
    ]
