"""Local cooperative agent execution with explicit cancellation checkpoints.

This module intentionally exposes a service interface, not an HTTP endpoint.
The cancellation controller is process-local and is not a fleet-wide kill
switch. Each model or tool dispatch requires a controller claim. The successful
state check under the controller lock is the linearization point: a cancellation
that wins before the check prevents invocation, while a check that wins first
makes the operation in flight. An in-flight operation may complete; completed
external effects cannot be rolled back by this module.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sqlite3
import stat
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol, get_args, get_origin

from pydantic import BaseModel, ConfigDict, ValidationError

from app.models import ChatCompletionRequest
from app.adapters.base import BaseAdapter
from .tool_outcome_store import (
    REPOSITORY_ROOT, SQLiteToolOutcomeStore, ToolOutcomeStore,
    local_database_process_lock,
)


DEFAULT_AUDIT_PATH = Path(os.getenv(
    "AGENT_EXECUTION_AUDIT_LOG",
    str(REPOSITORY_ROOT / "artifacts/agent_execution/cancellation.jsonl"),
))
DEFAULT_AUDIT_OUTBOX_PATH = Path(os.getenv(
    "AGENT_EXECUTION_AUDIT_OUTBOX_DB",
    str(REPOSITORY_ROOT / "artifacts/agent_execution/audit_outbox/cancellation.sqlite3"),
))
MAX_ACTION_BYTES = 64 * 1024
MAX_TOOL_RESULT_BYTES = 64 * 1024
_REASON_CODES = {
    "operator_requested",
    "policy_violation",
    "cost_limit",
    "security_incident",
}
_TOOL_REJECTION_REASONS = {
    "invalid_tool_arguments",
    "tool_validation_error",
    "tool_policy_denied",
    "approval_required",
    "tool_policy_error",
}
_TOOL_POLICY_DENIAL_REASONS = {
    "tool_policy_denied",
    "approval_required",
    "tool_policy_error",
}
_TOOL_EXECUTION_REASONS = {
    "tool_dispatch_already_recorded",
    "tool_outcome_store_error",
    "tool_outcome_unknown",
    "tool_result_not_serializable",
    "tool_result_too_large",
}


class AgentRunCancelled(RuntimeError):
    """Raised at a dispatch boundary after cancellation has been requested."""


class AgentRunRejected(RuntimeError):
    """Raised when a run starts while the local kill switch is disabled."""


class AgentToolRejected(RuntimeError):
    """Raised when tool arguments or policy fail closed before dispatch."""

    def __init__(self, reason_code: str) -> None:
        if reason_code not in _TOOL_REJECTION_REASONS:
            raise ValueError("unsupported tool rejection reason code")
        self.reason_code = reason_code
        super().__init__(f"tool action rejected: {reason_code}")


class AgentToolExecutionError(RuntimeError):
    """Sanitized tool failure that preserves the dispatched step record."""

    def __init__(self, run_id: str, reason_code: str, steps: list[dict[str, Any]]) -> None:
        if reason_code not in _TOOL_EXECUTION_REASONS:
            raise ValueError("unsupported tool execution reason code")
        self.run_id = run_id
        self.reason_code = reason_code
        self.steps = [dict(step) for step in steps]
        super().__init__(f"tool execution stopped: {reason_code}")


class AgentToolExecutionCancelled(asyncio.CancelledError):
    """Task cancellation carrying the dispatched tool's sanitized outcome."""

    def __init__(self, run_id: str, steps: list[dict[str, Any]],
                 reason_code: str = "tool_outcome_unknown") -> None:
        if reason_code not in _TOOL_EXECUTION_REASONS:
            raise ValueError("unsupported tool execution reason code")
        self.run_id = run_id
        self.reason_code = reason_code
        self.steps = [dict(step) for step in steps]
        super().__init__("tool execution cancelled; outcome unknown")


class AgentModel(Protocol):
    async def complete(self, messages: list[dict[str, str]]) -> str: ...


ToolHandler = Callable[..., Any | Awaitable[Any]]
AuditWriter = Callable[[dict[str, Any]], None]


class ToolArguments(BaseModel):
    """Base class for tool schemas; unknown fields are always rejected."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolPolicyDecision:
    allowed: bool
    reason_code: str = "allowed"

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise TypeError("allowed must be a bool")
        permitted = {"allowed", *_TOOL_POLICY_DENIAL_REASONS}
        if self.reason_code not in permitted:
            raise ValueError("reason_code must be a safe tool-policy reason code")
        if self.allowed and self.reason_code != "allowed":
            raise ValueError("allowed decisions must use the allowed reason code")
        if not self.allowed and self.reason_code not in _TOOL_POLICY_DENIAL_REASONS:
            raise ValueError("denied decisions require a rejection reason code")


@dataclass(frozen=True)
class ToolPolicyContext:
    run_id: str
    actor_id: str
    scope: str
    tool_name: str
    arguments: ToolArguments


ToolPolicy = Callable[[ToolPolicyContext], ToolPolicyDecision]


def _nested_model_types(annotation: Any) -> list[type[BaseModel]]:
    """Find Pydantic model classes inside unions and common container types."""
    found: list[type[BaseModel]] = []
    origin = get_origin(annotation)
    candidate = origin or annotation
    if isinstance(candidate, type):
        try:
            if issubclass(candidate, BaseModel):
                found.append(candidate)
        except TypeError:
            pass
    for argument in get_args(annotation):
        found.extend(_nested_model_types(argument))
    return found


def _tool_model_tree_forbids_extra(input_model: type[BaseModel]) -> bool:
    """Require every nested Pydantic model to reject unrecognized fields."""
    pending = [input_model]
    visited: set[type[BaseModel]] = set()
    while pending:
        model = pending.pop()
        if model in visited:
            continue
        visited.add(model)
        if model.model_config.get("extra") != "forbid":
            return False
        for field in model.model_fields.values():
            pending.extend(_nested_model_types(field.annotation))
    return True


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded_label(value: str | None, *, default: str, limit: int = 128) -> str:
    return (str(value).strip()[:limit] if value is not None else "") or default


def _reason_code(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _REASON_CODES:
        raise ValueError(f"reason_code must be one of: {', '.join(sorted(_REASON_CODES))}")
    return normalized


def append_cancellation_audit(
    event: dict[str, Any], path: Path | None = None,
) -> None:
    """Append metadata-only audit JSONL; prompts, arguments, and tool output are omitted."""
    path = path or DEFAULT_AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    audit_id = event.get("audit_id")
    if audit_id and path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(existing, dict) and existing.get("audit_id") == audit_id:
                    return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


class CancellationAuditOutbox:
    """Private SQLite outbox for durable cancellation audit delivery."""

    _TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS pending_cancellation_audits (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        audit_id TEXT NOT NULL UNIQUE,
        event_json TEXT NOT NULL
    )
    """

    def __init__(self, path: Path | str = DEFAULT_AUDIT_OUTBOX_PATH) -> None:
        configured = Path(path)
        self.path = (configured if configured.is_absolute()
                     else REPOSITORY_ROOT / configured).absolute()

    def _prepare_parent(self) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            info = self.path.parent.stat()
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
                raise PermissionError("cancellation audit outbox directory must be private")
        if self.path.is_symlink():
            raise PermissionError("cancellation audit outbox must not be a symlink")
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
            if os.name == "posix":
                flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(self.path, flags, 0o600)
            except FileExistsError:
                info = self.path.lstat()
            else:
                os.close(descriptor)
                info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError("cancellation audit outbox path must be a regular file")
        if os.name == "posix":
            if info.st_uid != os.geteuid() or info.st_nlink != 1:
                raise PermissionError("cancellation audit outbox owner is invalid")
            os.chmod(self.path, 0o600)

    def _connect_locked(self) -> sqlite3.Connection:
        self._prepare_parent()
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(self._TABLE_DDL)
        return connection

    def enqueue(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        try:
            self._prepare_parent()
            with local_database_process_lock(self.path, nonblocking=False):
                connection = self._connect_locked()
                try:
                    with connection:
                        connection.executemany(
                            "INSERT OR IGNORE INTO pending_cancellation_audits "
                            "(audit_id, event_json) VALUES (?, ?)",
                            [
                                (record["audit_id"], json.dumps(
                                    record, sort_keys=True, separators=(",", ":")
                                ))
                                for record in records
                            ],
                        )
                finally:
                    connection.close()
        except Exception:
            raise RuntimeError("cancellation audit outbox persistence failed") from None

    def flush(self, writer: AuditWriter) -> None:
        if not self.path.exists():
            return
        first_error: Exception | None = None
        try:
            with local_database_process_lock(self.path, nonblocking=False):
                connection = self._connect_locked()
                try:
                    rows = connection.execute(
                        "SELECT audit_id, event_json FROM pending_cancellation_audits "
                        "ORDER BY sequence"
                    ).fetchall()
                    for audit_id, event_json in rows:
                        event = json.loads(event_json)
                        try:
                            writer(event)
                        except Exception as exc:
                            if first_error is None:
                                first_error = exc
                        else:
                            connection.execute(
                                "DELETE FROM pending_cancellation_audits "
                                "WHERE audit_id = ?", (audit_id,)
                            )
                    connection.commit()
                finally:
                    connection.close()
        except Exception:
            if first_error is None:
                raise RuntimeError("cancellation audit outbox recovery failed") from None
        if first_error is not None:
            raise first_error


class CancellationController:
    """Thread-safe, process-local kill switch and run cancellation registry."""

    def __init__(self, audit_writer: AuditWriter = append_cancellation_audit, *,
                 audit_outbox_path: Path | str = DEFAULT_AUDIT_OUTBOX_PATH) -> None:
        self._audit_writer = audit_writer
        self._audit_outbox = CancellationAuditOutbox(audit_outbox_path)
        self._lock = threading.RLock()
        self._enabled = True
        self._active_run_ids: set[str] = set()
        self._run_context: dict[str, tuple[str, str]] = {}
        self._run_cancel_events: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Event]
        ] = {}
        # Tombstones persist for this controller lifetime so re-enabling cannot
        # revive a cancelled run ID. Run IDs must be unique and never reused.
        self._cancelled_run_ids: set[str] = set()
        # Recover durable cancellation audits before this controller handles
        # new work. A failed recovery aborts construction and leaves the rows.
        self._audit_outbox.flush(self._audit_writer)

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def _audit(self, *, event: str, run_id: str | None, actor_id: str | None,
               scope: str, reason_code: str) -> None:
        self._audit_writer(self._audit_record(
            event=event, run_id=run_id, actor_id=actor_id, scope=scope,
            reason_code=reason_code,
        ))

    @staticmethod
    def _audit_record(*, event: str, run_id: str | None, actor_id: str | None,
                      scope: str, reason_code: str,
                      audit_id: str | None = None) -> dict[str, Any]:
        record = {
            "event": event,
            "run_id": run_id,
            "actor_id": _bounded_label(actor_id, default="local_operator"),
            "scope": _bounded_label(scope, default="process"),
            "reason_code": reason_code,
            "timestamp": _utc_now(),
        }
        if audit_id is not None:
            record["audit_id"] = audit_id
        return record

    def begin_run(self, run_id: str, *, actor_id: str | None = None,
                  scope: str = "local") -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        cancel_event = asyncio.Event() if loop is not None else None
        with self._lock:
            if not self._enabled:
                raise AgentRunRejected("agent execution is disabled")
            if run_id in self._cancelled_run_ids:
                raise AgentRunRejected("cancelled run IDs cannot be reused")
            if run_id in self._active_run_ids:
                raise AgentRunRejected("run ID is already active")
            self._active_run_ids.add(run_id)
            self._run_context[run_id] = (
                _bounded_label(actor_id, default="local_operator"),
                _bounded_label(scope, default="local"),
            )
            if loop is not None and cancel_event is not None:
                self._run_cancel_events[run_id] = (loop, cancel_event)
                if run_id in self._cancelled_run_ids or not self._enabled:
                    cancel_event.set()

    def finish_run(self, run_id: str) -> None:
        with self._lock:
            self._active_run_ids.discard(run_id)
            self._run_context.pop(run_id, None)
            self._run_cancel_events.pop(run_id, None)

    async def wait_for_run_cancellation(self, run_id: str) -> None:
        """Wait for cancellation of an active async run without polling."""
        with self._lock:
            if run_id in self._cancelled_run_ids or not self._enabled:
                return
            registered = self._run_cancel_events.get(run_id)
        if registered is None:
            # Synchronous begin_run() is used by controller-only callers; an
            # executing AgentExecutionService run always registers its loop.
            raise RuntimeError("run cancellation notifier unavailable")
        loop, event = registered
        if loop is asyncio.get_running_loop():
            await event.wait()
            return
        # Service runs stay on one event loop, but fail closed if a future
        # caller tries to await the notifier from a different loop.
        raise RuntimeError("run cancellation notifier unavailable")

    def _notify_run_cancelled_locked(self, run_id: str) -> None:
        registered = self._run_cancel_events.get(run_id)
        if registered is None:
            return
        loop, event = registered
        try:
            loop.call_soon_threadsafe(event.set)
        except RuntimeError:
            # Cancellation remains latched in _cancelled_run_ids even if the
            # event loop has already begun shutting down.
            pass

    def claim_dispatch(self, run_id: str, operation: str) -> None:
        """Atomically claim a dispatch or reject it if cancellation won first.

        The successful state check while holding the controller lock is the
        linearization point. Cancellation after that check does not retract the
        claimed operation, even if its callable has not entered provider or
        tool code yet.
        """
        with self._lock:
            self._raise_if_cancelled_locked(run_id, f"{operation} dispatch")

    def raise_if_cancelled(self, run_id: str, boundary: str) -> None:
        """Observe cancellation at a non-dispatch boundary without claiming work."""
        with self._lock:
            self._raise_if_cancelled_locked(run_id, boundary)

    def _raise_if_cancelled_locked(self, run_id: str, boundary: str) -> None:
        if run_id in self._cancelled_run_ids or not self._enabled:
            raise AgentRunCancelled(f"run cancelled before {boundary}")

    def audit_tool_rejection(self, run_id: str, reason_code: str) -> None:
        """Record only safe metadata for a tool action rejected before dispatch."""
        if reason_code not in _TOOL_REJECTION_REASONS:
            raise ValueError("unsupported tool rejection reason code")
        with self._lock:
            actor_id, scope = self._run_context.get(run_id, ("local_operator", "run"))
            self._audit(event="agent_tool_rejected", run_id=run_id, actor_id=actor_id,
                        scope=scope, reason_code=reason_code)

    def cancel_run(self, run_id: str, *, actor_id: str | None = None,
                   scope: str | None = None, reason_code: str = "operator_requested") -> bool:
        reason = _reason_code(reason_code)
        with self._lock:
            if run_id in self._cancelled_run_ids:
                return False
            self._cancelled_run_ids.add(run_id)
            self._notify_run_cancelled_locked(run_id)
            run_actor, run_scope = self._run_context.get(run_id, ("local_operator", "run"))
            self._audit(event="agent_run_cancelled", run_id=run_id, actor_id=actor_id or run_actor,
                        scope=scope or run_scope, reason_code=reason)
            return True

    def disable(self, *, actor_id: str | None = None,
                reason_code: str = "operator_requested") -> list[str]:
        """Disable new runs and latch cancellation for all active runs."""
        reason = _reason_code(reason_code)
        with self._lock:
            self._enabled = False
            active = sorted(self._active_run_ids)
            pending_records: list[dict[str, Any]] = []
            for run_id in active:
                if run_id not in self._cancelled_run_ids:
                    self._cancelled_run_ids.add(run_id)
                    self._notify_run_cancelled_locked(run_id)
                    pending_records.append(self._audit_record(
                        event="agent_run_cancelled", run_id=run_id,
                        actor_id=actor_id, scope="process", reason_code=reason,
                        audit_id=uuid.uuid4().hex,
                    ))
            # Latch and notify every active run before invoking user-configured
            # audit I/O. Failed writes remain durable for a later disable() call
            # or a newly constructed controller after process restart.
            self._audit_outbox.enqueue(pending_records)
            self._audit_outbox.flush(self._audit_writer)
            if not active:
                self._audit(event="agent_execution_disabled", run_id=None,
                            actor_id=actor_id, scope="process", reason_code=reason)
            return active

    def enable(self, *, actor_id: str | None = None,
               reason_code: str = "operator_requested") -> None:
        reason = _reason_code(reason_code)
        with self._lock:
            self._enabled = True
            # Deliberately do not clear cancelled run tombstones.
            self._audit(event="agent_execution_enabled", run_id=None, actor_id=actor_id,
                        scope="process", reason_code=reason)


@dataclass(frozen=True)
class Tool:
    name: str
    handler: ToolHandler
    input_model: type[ToolArguments]


class RuntimeAgentModel:
    """Bridge an existing AgentTrust BaseAdapter to the agent model protocol."""

    def __init__(self, adapter: BaseAdapter, *, model: str, max_tokens: int = 512) -> None:
        if not model.strip():
            raise ValueError("model is required")
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        self._adapter = adapter
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, messages: list[dict[str, str]]) -> str:
        request = ChatCompletionRequest(
            model=self._model,
            messages=messages,
            temperature=0.0,
            max_tokens=self._max_tokens,
        )
        result = await self._adapter.complete(request)
        return result.response.choices[0].message.content


class AgentExecutionService:
    """Execute JSON-directed model/tool steps with cooperative cancellation."""

    SYSTEM_PROMPT = (
        "You are a bounded tool-using assistant. Return exactly one JSON object: "
        '{"kind":"tool","name":"ALLOWLISTED_TOOL","arguments":{...}} or '
        '{"kind":"final","content":"..."}. Use only tools listed by the caller. '
        "Do not include markdown fences."
    )

    def __init__(self, *, model: AgentModel, tools: list[Tool],
                 cancellation: CancellationController, max_steps: int = 6,
                 tool_policy: ToolPolicy | None = None,
                 outcome_store: ToolOutcomeStore | None = None) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        names = [tool.name for tool in tools]
        if any(not name.strip() for name in names) or len(names) != len(set(names)):
            raise ValueError("tool names must be non-empty and unique")
        for tool in tools:
            if (not isinstance(tool.input_model, type) or
                    not issubclass(tool.input_model, ToolArguments) or
                    not _tool_model_tree_forbids_extra(tool.input_model)):
                raise TypeError(
                    "each tool input_model must inherit ToolArguments and every nested Pydantic "
                    "model must forbid extra fields"
                )
        self._model = model
        self._tools = {tool.name: tool for tool in tools}
        self._cancellation = cancellation
        self._max_steps = max_steps
        self._tool_policy = tool_policy
        self._outcome_store = outcome_store
        self._outcome_store_initialization_task: asyncio.Task[
            SQLiteToolOutcomeStore
        ] | None = None

    def _outcome_store_initialization_done(
        self, task: asyncio.Task[SQLiteToolOutcomeStore]
    ) -> None:
        """Forget failed shared initialization and consume unobserved errors.

        All waiters may cancel while the worker continues. In that case no
        waiter remains to retrieve a later exception or clear the cached task.
        Keep successful tasks cached so a later run can adopt their store.
        """
        try:
            failed = task.cancelled() or task.exception() is not None
        except asyncio.CancelledError:
            failed = True
        if failed and self._outcome_store_initialization_task is task:
            self._outcome_store_initialization_task = None

    async def _ensure_outcome_store(self, run_id: str) -> None:
        self._cancellation.raise_if_cancelled(run_id, "store initialization")
        if self._outcome_store is not None:
            return
        task = self._outcome_store_initialization_task
        if task is None:
            # Store construction may wait on another process's active
            # dispatch. Run that synchronous initialization off-loop, and
            # share one initialization task across concurrent runs.
            task = asyncio.create_task(SQLiteToolOutcomeStore.create_async())
            self._outcome_store_initialization_task = task
            task.add_done_callback(self._outcome_store_initialization_done)
        store_waiter = asyncio.ensure_future(asyncio.shield(task))
        cancellation_waiter = asyncio.create_task(
            self._cancellation.wait_for_run_cancellation(run_id)
        )
        try:
            done, _ = await asyncio.wait(
                {store_waiter, cancellation_waiter},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation_waiter in done:
                self._cancellation.raise_if_cancelled(
                    run_id, "store initialization"
                )
                cancellation_waiter.result()
            store = await store_waiter
        except asyncio.CancelledError:
            # The shared initialization continues for other runs; do not
            # cancel its worker thread or start a duplicate initializer.
            raise
        except Exception:
            if task.done() and self._outcome_store_initialization_task is task:
                self._outcome_store_initialization_task = None
            raise
        finally:
            for waiter in (store_waiter, cancellation_waiter):
                if not waiter.done():
                    waiter.cancel()
            await asyncio.gather(
                store_waiter, cancellation_waiter, return_exceptions=True
            )
        self._outcome_store = store

    def _record_tool_terminal(self, *, run_id: str, step_number: int,
                              tool_name: str, status: str, reason_code: str | None,
                              tool_step: dict[str, Any],
                              steps: list[dict[str, Any]]) -> None:
        try:
            self._outcome_store.record_terminal(
                run_id, step_number, tool_name, status, reason_code
            )
        except Exception:
            # The durable journal contains only the earlier dispatch intent;
            # callers must treat the final outcome as unknown.
            tool_step.update({"status": "outcome_unknown",
                              "reason_code": "tool_outcome_store_error"})
            raise AgentToolExecutionError(
                run_id, "tool_outcome_store_error", steps
            ) from None

    async def _dispatch_tool_under_process_lock(
        self, *, run_id: str, step_number: int, tool: Tool,
        tool_kwargs: dict[str, Any], tool_step: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> str:
        """Hold the store's local lock from dispatch intent through terminal write."""
        if self._outcome_store is None:
            raise AgentToolExecutionError(
                run_id, "tool_outcome_store_error", steps
            )
        try:
            async with self._outcome_store.async_execution_lock(
                cancel_check=lambda: self._cancellation.raise_if_cancelled(
                    run_id, "tool process lock"
                )
            ):
                # This is the final cancellation boundary. A run may have
                # waited asynchronously for another tool dispatch to finish.
                self._cancellation.claim_dispatch(run_id, "tool")
                try:
                    dispatch_recorded = self._outcome_store.record_dispatch(
                        run_id, step_number, tool.name
                    )
                except Exception:
                    tool_step["reason_code"] = "tool_outcome_store_error"
                    raise AgentToolExecutionError(
                        run_id, "tool_outcome_store_error", steps
                    ) from None
                if not dispatch_recorded:
                    tool_step["reason_code"] = "tool_dispatch_already_recorded"
                    raise AgentToolExecutionError(
                        run_id, "tool_dispatch_already_recorded", steps
                    )
                tool_step["status"] = "in_flight"
                try:
                    result = tool.handler(**tool_kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                except asyncio.CancelledError:
                    tool_step.update({"status": "outcome_unknown",
                                      "reason_code": "tool_outcome_unknown"})
                    try:
                        self._record_tool_terminal(
                            run_id=run_id, step_number=step_number,
                            tool_name=tool.name, status="outcome_unknown",
                            reason_code="tool_outcome_unknown", tool_step=tool_step,
                            steps=steps,
                        )
                    except AgentToolExecutionError:
                        raise AgentToolExecutionCancelled(
                            run_id, steps, "tool_outcome_store_error"
                        ) from None
                    raise AgentToolExecutionCancelled(run_id, steps) from None
                except Exception:
                    # A handler may perform a partial external effect before
                    # raising, so neither success nor rollback can be asserted.
                    tool_step.update({"status": "outcome_unknown",
                                      "reason_code": "tool_outcome_unknown"})
                    self._record_tool_terminal(
                        run_id=run_id, step_number=step_number,
                        tool_name=tool.name, status="outcome_unknown",
                        reason_code="tool_outcome_unknown", tool_step=tool_step,
                        steps=steps,
                    )
                    raise AgentToolExecutionError(
                        run_id, "tool_outcome_unknown", steps
                    ) from None

                # Keep the process lock until the terminal event records the
                # handler's known outcome, including serialization failures.
                tool_step["status"] = "completed"
                try:
                    serialized_result = json.dumps(
                        result, sort_keys=True, separators=(",", ":"), allow_nan=False
                    )
                    serialized_result_size = len(serialized_result.encode("utf-8"))
                except Exception:
                    tool_step.update({"status": "completed_result_unavailable",
                                      "reason_code": "tool_result_not_serializable"})
                    self._record_tool_terminal(
                        run_id=run_id, step_number=step_number,
                        tool_name=tool.name, status="completed_result_unavailable",
                        reason_code="tool_result_not_serializable", tool_step=tool_step,
                        steps=steps,
                    )
                    raise AgentToolExecutionError(
                        run_id, "tool_result_not_serializable", steps
                    ) from None
                if serialized_result_size > MAX_TOOL_RESULT_BYTES:
                    tool_step.update({"status": "completed_result_unavailable",
                                      "reason_code": "tool_result_too_large"})
                    self._record_tool_terminal(
                        run_id=run_id, step_number=step_number,
                        tool_name=tool.name, status="completed_result_unavailable",
                        reason_code="tool_result_too_large", tool_step=tool_step,
                        steps=steps,
                    )
                    raise AgentToolExecutionError(
                        run_id, "tool_result_too_large", steps
                    )
                tool_step["status"] = "completed"
                self._record_tool_terminal(
                    run_id=run_id, step_number=step_number,
                    tool_name=tool.name, status="completed", reason_code=None,
                    tool_step=tool_step, steps=steps,
                )
                return serialized_result
        except (AgentRunCancelled, AgentToolExecutionError):
            raise
        except Exception:
            # Lock acquisition and unsupported store implementations fail
            # closed before invoking the handler.
            tool_step.update({"status": "not_dispatched",
                              "reason_code": "tool_outcome_store_error"})
            raise AgentToolExecutionError(
                run_id, "tool_outcome_store_error", steps
            ) from None

    async def run(self, task: str, *, run_id: str | None = None,
                  actor_id: str | None = None, scope: str = "local") -> dict[str, Any]:
        if not task.strip():
            raise ValueError("task is required")
        current_run_id = run_id or f"agent-{uuid.uuid4().hex}"
        self._cancellation.begin_run(current_run_id, actor_id=actor_id, scope=scope)
        step_records: list[dict[str, Any]] = []
        try:
            await self._ensure_outcome_store(current_run_id)
            allowed_tools = ", ".join(sorted(self._tools)) or "none"
            messages = [
                {"role": "system", "content": f"{self.SYSTEM_PROMPT} Allowed tool names: {allowed_tools}."},
                {"role": "user", "content": task},
            ]
            for step_number in range(1, self._max_steps + 1):
                self._cancellation.claim_dispatch(current_run_id, "model")
                raw = await self._model.complete(messages)
                self._cancellation.raise_if_cancelled(current_run_id, "action handling")
                action = self._parse_action(raw)
                if action["kind"] == "final":
                    return {"run_id": current_run_id, "status": "completed",
                            "answer": action["content"], "steps": step_records}

                tool_name = action["name"]
                tool = self._tools.get(tool_name)
                if tool is None:
                    raise ValueError(f"model requested a tool outside the allowlist: {tool_name}")
                try:
                    arguments = tool.input_model.model_validate(action["arguments"], strict=True)
                except ValidationError:
                    self._cancellation.audit_tool_rejection(current_run_id, "invalid_tool_arguments")
                    raise AgentToolRejected("invalid_tool_arguments") from None
                except Exception:
                    # Custom validators may raise non-ValidationError
                    # exceptions. Fail closed and do not persist exception
                    # details, which can contain submitted values.
                    self._cancellation.audit_tool_rejection(current_run_id, "tool_validation_error")
                    raise AgentToolRejected("tool_validation_error") from None
                try:
                    tool_kwargs = arguments.model_dump(mode="python")
                except Exception:
                    self._cancellation.audit_tool_rejection(current_run_id, "tool_validation_error")
                    raise AgentToolRejected("tool_validation_error") from None

                policy_context = ToolPolicyContext(
                    run_id=current_run_id,
                    actor_id=_bounded_label(actor_id, default="local_operator"),
                    scope=_bounded_label(scope, default="local"),
                    tool_name=tool_name,
                    arguments=arguments,
                )
                try:
                    decision = (self._tool_policy(policy_context) if self._tool_policy is not None
                                else ToolPolicyDecision(False, "tool_policy_denied"))
                    if not isinstance(decision, ToolPolicyDecision):
                        raise TypeError("tool policy must return ToolPolicyDecision")
                except Exception:
                    self._cancellation.audit_tool_rejection(current_run_id, "tool_policy_error")
                    raise AgentToolRejected("tool_policy_error") from None
                if not decision.allowed:
                    self._cancellation.audit_tool_rejection(current_run_id, decision.reason_code)
                    raise AgentToolRejected(decision.reason_code)

                # A tool run may wait for another run's per-database lock.
                # Its final cancellation claim happens after lock acquisition
                # and immediately before dispatch persistence.
                tool_step = {"step": step_number, "type": "tool",
                             "name": tool_name, "status": "not_dispatched"}
                step_records.append(tool_step)
                serialized_result = await self._dispatch_tool_under_process_lock(
                    run_id=current_run_id, step_number=step_number, tool=tool,
                    tool_kwargs=tool_kwargs, tool_step=tool_step, steps=step_records,
                )
                self._cancellation.raise_if_cancelled(current_run_id, "next model dispatch")
                messages.extend([
                    {"role": "assistant", "content": raw},
                    {"role": "tool", "content": serialized_result},
                ])
            raise RuntimeError("agent exceeded configured maximum steps")
        except AgentRunCancelled:
            return {"run_id": current_run_id, "status": "cancelled",
                    "answer": None, "steps": step_records}
        finally:
            self._cancellation.finish_run(current_run_id)

    @staticmethod
    def _parse_action(raw: str) -> dict[str, Any]:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_ACTION_BYTES:
            raise ValueError("model action is missing or exceeds configured size limit")
        try:
            action = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("model response must be a JSON action object") from exc
        if not isinstance(action, dict):
            raise ValueError("model response must be a JSON action object")
        if action.get("kind") == "final":
            if set(action) != {"kind", "content"} or not isinstance(action["content"], str):
                raise ValueError("final action must contain only string content")
            return action
        if action.get("kind") == "tool":
            if set(action) != {"kind", "name", "arguments"}:
                raise ValueError("tool action fields are invalid")
            if not isinstance(action["name"], str) or not isinstance(action["arguments"], dict):
                raise ValueError("tool action name/arguments have invalid types")
            return action
        raise ValueError("action kind must be tool or final")
