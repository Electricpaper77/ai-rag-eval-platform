from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import sqlite3
import sys
import threading
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, field_validator

from backend.app.agent_execution import (
    AgentExecutionService,
    AgentToolExecutionCancelled,
    AgentToolExecutionError,
    AgentToolRejected,
    AgentRunRejected,
    CancellationController,
    RuntimeAgentModel,
    Tool,
    ToolArguments,
    ToolPolicyContext,
    ToolPolicyDecision,
)
from backend.app.tool_outcome_store import (
    SQLiteToolOutcomeStore,
    ToolOutcomeStoreError,
)
from backend.app import tool_outcome_store as tool_outcome_store_module


@pytest.fixture(autouse=True)
def isolate_default_outcome_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", str(tmp_path / "outcomes.sqlite3"))


class ScriptedModel:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self.responses.pop(0)


class EmptyToolArgs(ToolArguments):
    pass


class LookupToolArgs(ToolArguments):
    key: str


class SecretToolArgs(ToolArguments):
    secret: str


def allow_tool(_context: ToolPolicyContext) -> ToolPolicyDecision:
    return ToolPolicyDecision(allowed=True)


def test_agent_executes_model_tool_model_sequence_and_returns_final_answer():
    model = ScriptedModel(
        '{"kind":"tool","name":"lookup","arguments":{"key":"refund"}}',
        '{"kind":"final","content":"Policy says review within two business days."}',
    )
    calls: list[str] = []
    service = AgentExecutionService(
        model=model,
        tools=[Tool("lookup", lambda key: calls.append(key) or {"text": "two business days"}, LookupToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
    )

    result = asyncio.run(service.run("What is the refund review period?", run_id="run-sequence"))

    assert result["status"] == "completed"
    assert result["answer"] == "Policy says review within two business days."
    assert calls == ["refund"]
    assert len(model.calls) == 2
    assert result["steps"] == [{"step": 1, "type": "tool", "name": "lookup", "status": "completed"}]
    assert "two business days" in model.calls[1][-1]["content"]


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"key": 42},
        {"key": "safe", "extra": "do-not-log"},
    ],
)
def test_invalid_tool_arguments_are_audited_and_never_dispatched(arguments: dict):
    events: list[dict] = []
    policy_calls: list[ToolPolicyContext] = []
    handler_calls: list[dict] = []
    model = ScriptedModel(json.dumps({
        "kind": "tool", "name": "lookup", "arguments": arguments,
    }))
    service = AgentExecutionService(
        model=model,
        tools=[Tool("lookup", lambda **kwargs: handler_calls.append(kwargs), LookupToolArgs)],
        cancellation=CancellationController(audit_writer=events.append),
        tool_policy=lambda context: policy_calls.append(context) or ToolPolicyDecision(True),
    )
    task = "private lookup task"

    with pytest.raises(AgentToolRejected) as rejected:
        asyncio.run(service.run(task, run_id="invalid-arguments", actor_id="operator-3", scope="team"))

    assert rejected.value.reason_code == "invalid_tool_arguments"
    assert policy_calls == []
    assert handler_calls == []
    assert len(events) == 1
    assert events[0]["event"] == "agent_tool_rejected"
    assert events[0]["reason_code"] == "invalid_tool_arguments"
    assert events[0]["actor_id"] == "operator-3"
    assert events[0]["scope"] == "team"
    assert task not in json.dumps(events)
    assert "do-not-log" not in json.dumps(events)


def test_nested_extra_tool_argument_is_rejected_and_audited():
    class NestedLookupArgs(ToolArguments):
        key: str

    class LookupEnvelope(ToolArguments):
        query: NestedLookupArgs

    events: list[dict] = []
    policy_calls: list[ToolPolicyContext] = []
    handler_calls: list[dict] = []
    model = ScriptedModel(
        '{"kind":"tool","name":"lookup","arguments":'
        '{"query":{"key":"safe","unexpected":"private-value"}}}'
    )
    service = AgentExecutionService(
        model=model,
        tools=[Tool("lookup", lambda **kwargs: handler_calls.append(kwargs), LookupEnvelope)],
        cancellation=CancellationController(audit_writer=events.append),
        tool_policy=lambda context: policy_calls.append(context) or ToolPolicyDecision(True),
    )

    with pytest.raises(AgentToolRejected) as rejected:
        asyncio.run(service.run("private prompt", run_id="nested-extra"))

    assert rejected.value.reason_code == "invalid_tool_arguments"
    assert policy_calls == []
    assert handler_calls == []
    assert events[0]["reason_code"] == "invalid_tool_arguments"
    assert "private-value" not in json.dumps(events)
    assert "private prompt" not in json.dumps(events)


def test_schema_registration_rejects_permissive_nested_model():
    class PermissiveNested(BaseModel):
        key: str

    class LookupEnvelope(ToolArguments):
        query: PermissiveNested

    with pytest.raises(TypeError, match="nested Pydantic"):
        AgentExecutionService(
            model=ScriptedModel(),
            tools=[Tool("lookup", lambda **kwargs: kwargs, LookupEnvelope)],
            cancellation=CancellationController(audit_writer=lambda _: None),
        )


def test_custom_validator_exception_is_audited_without_exception_details():
    class ValidatorFailureArgs(ToolArguments):
        key: str

        @field_validator("key")
        @classmethod
        def reject_with_internal_detail(cls, value: str) -> str:
            raise RuntimeError(f"validator failure for {value}")

    events: list[dict] = []
    handler_calls: list[dict] = []
    policy_calls: list[ToolPolicyContext] = []
    service = AgentExecutionService(
        model=ScriptedModel(
            '{"kind":"tool","name":"lookup","arguments":{"key":"private-value"}}'
        ),
        tools=[Tool("lookup", lambda **kwargs: handler_calls.append(kwargs), ValidatorFailureArgs)],
        cancellation=CancellationController(audit_writer=events.append),
        tool_policy=lambda context: policy_calls.append(context) or ToolPolicyDecision(True),
    )

    with pytest.raises(AgentToolRejected) as rejected:
        asyncio.run(service.run("private prompt", run_id="validator-error"))

    assert rejected.value.reason_code == "tool_validation_error"
    assert policy_calls == []
    assert handler_calls == []
    assert len(events) == 1
    assert events[0] == {
        "event": "agent_tool_rejected",
        "run_id": "validator-error",
        "actor_id": "local_operator",
        "scope": "local",
        "reason_code": "tool_validation_error",
        "timestamp": events[0]["timestamp"],
    }
    assert "private-value" not in json.dumps(events)
    assert "private prompt" not in json.dumps(events)
    assert "validator failure" not in json.dumps(events)


def test_policy_denial_is_audited_and_never_dispatches_tool():
    events: list[dict] = []
    handler_calls: list[str] = []
    policy_contexts: list[ToolPolicyContext] = []
    model = ScriptedModel('{"kind":"tool","name":"lookup","arguments":{"key":"private-key"}}')

    def deny(context: ToolPolicyContext) -> ToolPolicyDecision:
        policy_contexts.append(context)
        return ToolPolicyDecision(False, "approval_required")

    service = AgentExecutionService(
        model=model,
        tools=[Tool("lookup", lambda key: handler_calls.append(key), LookupToolArgs)],
        cancellation=CancellationController(audit_writer=events.append),
        tool_policy=deny,
    )

    with pytest.raises(AgentToolRejected) as rejected:
        asyncio.run(service.run("private prompt", run_id="policy-denied", actor_id="operator-4"))

    assert rejected.value.reason_code == "approval_required"
    assert len(policy_contexts) == 1
    assert policy_contexts[0].arguments.key == "private-key"
    assert handler_calls == []
    assert len(events) == 1
    assert events[0]["event"] == "agent_tool_rejected"
    assert events[0]["reason_code"] == "approval_required"
    assert "private-key" not in json.dumps(events)
    assert "private prompt" not in json.dumps(events)


def test_tools_fail_closed_when_no_policy_is_configured():
    events: list[dict] = []
    handler_calls: list[str] = []
    service = AgentExecutionService(
        model=ScriptedModel('{"kind":"tool","name":"lookup","arguments":{"key":"safe"}}'),
        tools=[Tool("lookup", lambda key: handler_calls.append(key), LookupToolArgs)],
        cancellation=CancellationController(audit_writer=events.append),
    )

    with pytest.raises(AgentToolRejected) as rejected:
        asyncio.run(service.run("lookup", run_id="no-policy"))

    assert rejected.value.reason_code == "tool_policy_denied"
    assert handler_calls == []
    assert events[0]["reason_code"] == "tool_policy_denied"


def test_tool_schema_must_forbid_extra_fields_at_registration():
    class PermissiveArgs(ToolArguments):
        model_config = ConfigDict(extra="ignore")
        key: str

    with pytest.raises(TypeError, match="forbid extra fields"):
        AgentExecutionService(
            model=ScriptedModel(),
            tools=[Tool("lookup", lambda key: key, PermissiveArgs)],
            cancellation=CancellationController(audit_writer=lambda _: None),
        )


def test_cancellation_during_allow_policy_blocks_tool_at_final_claim():
    handler_calls: list[str] = []
    cancellation = CancellationController(audit_writer=lambda _: None)

    def allow_then_cancel(context: ToolPolicyContext) -> ToolPolicyDecision:
        cancellation.cancel_run(context.run_id, reason_code="policy_violation")
        return ToolPolicyDecision(True)

    service = AgentExecutionService(
        model=ScriptedModel('{"kind":"tool","name":"lookup","arguments":{"key":"safe"}}'),
        tools=[Tool("lookup", lambda key: handler_calls.append(key), LookupToolArgs)],
        cancellation=cancellation,
        tool_policy=allow_then_cancel,
    )

    result = asyncio.run(service.run("lookup", run_id="cancel-during-policy"))

    assert result["status"] == "cancelled"
    assert handler_calls == []


def test_tool_exception_after_side_effect_preserves_unknown_outcome_record():
    side_effects: list[str] = []
    model = ScriptedModel(
        '{"kind":"tool","name":"write","arguments":{}}',
        '{"kind":"final","content":"must not run"}',
    )

    def mutate_then_raise() -> dict:
        side_effects.append("written")
        raise RuntimeError("private provider detail")

    service = AgentExecutionService(
        model=model,
        tools=[Tool("write", mutate_then_raise, EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
    )

    with pytest.raises(AgentToolExecutionError) as failed:
        asyncio.run(service.run("write", run_id="tool-raised"))

    assert side_effects == ["written"]
    assert failed.value.run_id == "tool-raised"
    assert failed.value.reason_code == "tool_outcome_unknown"
    assert failed.value.steps == [{
        "step": 1,
        "type": "tool",
        "name": "write",
        "status": "outcome_unknown",
        "reason_code": "tool_outcome_unknown",
    }]
    assert "private provider detail" not in str(failed.value)
    assert len(model.calls) == 1
    persisted = SQLiteToolOutcomeStore().events("tool-raised")
    assert [event["status"] for event in persisted] == ["in_flight", "outcome_unknown"]
    assert b"private provider detail" not in SQLiteToolOutcomeStore().path.read_bytes()
    with SQLiteToolOutcomeStore().execution_lock():
        pass


def test_successful_tool_outcome_is_persisted_without_arguments_or_result():
    model = ScriptedModel(
        '{"kind":"tool","name":"lookup","arguments":{"key":"private-key"}}',
        '{"kind":"final","content":"done"}',
    )
    service = AgentExecutionService(
        model=model,
        tools=[Tool("lookup", lambda key: {"private-result": key}, LookupToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
    )

    result = asyncio.run(service.run("private prompt", run_id="persist-success"))

    assert result["status"] == "completed"
    events = SQLiteToolOutcomeStore().events("persist-success")
    assert [event["status"] for event in events] == ["in_flight", "completed"]
    assert all(set(event) == {
        "sequence", "run_id", "step_number", "tool_name", "event_type",
        "status", "reason_code", "occurred_at",
    } for event in events)
    raw_db = SQLiteToolOutcomeStore().path.read_bytes()
    assert b"private-key" not in raw_db
    assert b"private-result" not in raw_db
    assert b"private prompt" not in raw_db


def test_restart_recovery_closes_dispatch_without_terminal_as_unknown(tmp_path):
    database = tmp_path / "restart.sqlite3"
    first_process_store = SQLiteToolOutcomeStore(database)
    assert first_process_store.record_dispatch("restart-run", 2, "write") is True

    restarted_store = SQLiteToolOutcomeStore(database)
    recovered = restarted_store.recover_incomplete()

    assert recovered == [{
        "run_id": "restart-run",
        "step_number": 2,
        "tool_name": "write",
        "status": "outcome_unknown",
        "reason_code": "tool_outcome_unknown",
    }]
    events = restarted_store.events("restart-run")
    assert [event["status"] for event in events] == ["in_flight", "outcome_unknown"]
    assert restarted_store.recover_incomplete() == []


def test_relative_database_path_is_stable_across_working_directories(tmp_path, monkeypatch):
    repository_root = tmp_path / "repo"
    first_cwd = tmp_path / "first-cwd"
    second_cwd = tmp_path / "second-cwd"
    first_cwd.mkdir()
    second_cwd.mkdir()
    monkeypatch.setattr(tool_outcome_store_module, "REPOSITORY_ROOT", repository_root)
    monkeypatch.setenv("AGENT_EXECUTION_OUTCOME_DB", "state/outcomes.sqlite3")
    monkeypatch.chdir(first_cwd)

    first_store = SQLiteToolOutcomeStore()
    assert first_store.path == repository_root / "state/outcomes.sqlite3"
    assert first_store.record_dispatch("cwd-stable", 1, "lookup") is True

    monkeypatch.chdir(second_cwd)
    second_store = SQLiteToolOutcomeStore()
    assert second_store.path == first_store.path
    assert [event["status"] for event in second_store.events("cwd-stable")] == ["in_flight"]


def test_absolute_database_path_is_preserved(tmp_path, monkeypatch):
    absolute_path = tmp_path / "absolute" / "outcomes.sqlite3"
    monkeypatch.chdir(tmp_path)

    store = SQLiteToolOutcomeStore(absolute_path)

    assert store.path == absolute_path.resolve()


@pytest.mark.skipif(os.name != "posix", reason="symlink behavior requires POSIX")
def test_store_rejects_dangling_database_symlink_without_creating_target(tmp_path):
    link_directory = tmp_path / "link-directory"
    target_directory = tmp_path / "target-directory"
    link_directory.mkdir(mode=0o700)
    target_directory.mkdir(mode=0o700)
    database_link = link_directory / "outcomes.sqlite3"
    target = target_directory / "unexpected.sqlite3"
    database_link.symlink_to(target)

    with pytest.raises(ToolOutcomeStoreError) as failed:
        SQLiteToolOutcomeStore(database_link)

    assert failed.value.operation == "initialize"
    assert database_link.is_symlink()
    assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="symlink behavior requires POSIX")
def test_store_rejects_live_database_symlink_without_changing_target(tmp_path):
    target_directory = tmp_path / "existing-target"
    link_directory = tmp_path / "link-directory"
    target_directory.mkdir(mode=0o700)
    link_directory.mkdir(mode=0o700)
    target = target_directory / "outcomes.sqlite3"
    database_link = link_directory / "outcomes.sqlite3"

    SQLiteToolOutcomeStore(target)
    target_before = target.stat()
    bytes_before = target.read_bytes()
    mode_before = stat.S_IMODE(target_before.st_mode)
    mtime_before = target_before.st_mtime_ns
    database_link.symlink_to(target)

    with pytest.raises(ToolOutcomeStoreError) as failed:
        SQLiteToolOutcomeStore(database_link)

    assert failed.value.operation == "initialize"
    assert str(target) not in str(failed.value)
    assert database_link.is_symlink()
    assert target.exists()
    assert target.read_bytes() == bytes_before
    target_after = target.stat()
    assert stat.S_IMODE(target_after.st_mode) == mode_before
    assert target_after.st_mtime_ns == mtime_before

    normal_database = tmp_path / "normal" / "outcomes.sqlite3"
    normal_store = SQLiteToolOutcomeStore(normal_database)
    assert normal_database.exists()
    assert normal_store.path == normal_database.resolve()


@pytest.mark.skipif(os.name != "posix", reason="symlink behavior requires POSIX")
@pytest.mark.parametrize("target_exists", [True, False], ids=["live", "dangling"])
def test_store_connection_rejects_database_path_replaced_by_symlink(
    tmp_path, target_exists: bool,
):
    database = tmp_path / "store" / "outcomes.sqlite3"
    store = SQLiteToolOutcomeStore(database)
    target = tmp_path / "target" / "outcomes.sqlite3"
    target_before = None
    if target_exists:
        SQLiteToolOutcomeStore(target)
        target_stat = target.stat()
        target_before = (
            target.read_bytes(), stat.S_IMODE(target_stat.st_mode),
            target_stat.st_mtime_ns,
        )

    database.unlink()
    database.symlink_to(target)

    with pytest.raises(ToolOutcomeStoreError) as failed:
        store.record_dispatch("replaced-database-path", 1, "lookup")

    assert failed.value.operation == "dispatch"
    assert str(database) not in str(failed.value)
    assert str(target) not in str(failed.value)
    assert database.is_symlink()
    if target_exists:
        assert target_before is not None
        target_after = target.stat()
        assert target.read_bytes() == target_before[0]
        assert stat.S_IMODE(target_after.st_mode) == target_before[1]
        assert target_after.st_mtime_ns == target_before[2]
    else:
        assert not target.exists()


@pytest.mark.parametrize("replacement", ["missing", "directory"])
def test_store_connection_rejects_missing_or_nonregular_database_path(
    tmp_path, replacement: str,
):
    database = tmp_path / "store" / "outcomes.sqlite3"
    store = SQLiteToolOutcomeStore(database)
    database.unlink()
    if replacement == "directory":
        database.mkdir(mode=0o700)

    with pytest.raises(ToolOutcomeStoreError) as failed:
        store.record_dispatch("replaced-database-path", 1, "lookup")

    assert failed.value.operation == "dispatch"
    assert str(database) not in str(failed.value)
    if replacement == "directory":
        assert database.is_dir()
    else:
        assert not database.exists()


def test_database_and_backup_paths_are_restricted_on_posix(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX mode-bit assertions are not applicable")
    database = tmp_path / "private-db" / "outcomes.sqlite3"
    store = SQLiteToolOutcomeStore(database)

    assert stat.S_IMODE(database.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert store.record_dispatch("permissions-run", 1, "lookup") is True
    for sidecar in (Path(f"{database}-wal"), Path(f"{database}-shm")):
        if sidecar.exists():
            assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


def test_backup_restore_preserves_events_and_restricts_files(tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX mode-bit assertions are not applicable")
    store = SQLiteToolOutcomeStore(tmp_path / "source" / "outcomes.sqlite3")
    store.record_dispatch("backup-run", 1, "lookup")
    store.record_terminal("backup-run", 1, "lookup", "completed")

    backup_path = store.backup_to(tmp_path / "backup" / "outcomes.sqlite3")
    restored = SQLiteToolOutcomeStore.restore_from(
        backup_path, tmp_path / "restored" / "outcomes.sqlite3"
    )

    assert stat.S_IMODE(backup_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(restored.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(restored.path.stat().st_mode) == 0o600
    assert restored.events("backup-run") == store.events("backup-run")


@pytest.mark.parametrize("operation", ["backup", "restore"])
@pytest.mark.parametrize("interrupt_phase", ["before_link", "after_link"])
def test_backup_and_restore_installation_survives_process_interruption(
    tmp_path, operation: str, interrupt_phase: str,
):
    repository_root = Path(__file__).resolve().parents[1]
    source_path = tmp_path / "source" / "outcomes.sqlite3"
    source = SQLiteToolOutcomeStore(source_path)
    source.record_dispatch("atomic-run", 1, "lookup")
    source.record_terminal("atomic-run", 1, "lookup", "completed")
    if operation == "restore":
        backup_path = source.backup_to(tmp_path / "seed" / "backup.sqlite3")
        source_path = backup_path
    destination = tmp_path / operation / "installed.sqlite3"
    child_code = r"""
import os, sys
import backend.app.tool_outcome_store as module
from backend.app.tool_outcome_store import SQLiteToolOutcomeStore
operation, phase, source_path, destination = sys.argv[1:]
real_link = module.os.link
def interrupt_link(source, target):
    if phase == "before_link":
        os._exit(71)
    real_link(source, target)
    if phase == "after_link":
        os._exit(72)
module.os.link = interrupt_link
if operation == "backup":
    SQLiteToolOutcomeStore(source_path).backup_to(destination)
else:
    SQLiteToolOutcomeStore.restore_from(source_path, destination)
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")

    child = subprocess.run(
        [sys.executable, "-c", child_code, operation, interrupt_phase,
         str(source_path), str(destination)],
        cwd=repository_root, env=env, capture_output=True, text=True, timeout=10,
    )

    expected_exit = 71 if interrupt_phase == "before_link" else 72
    assert child.returncode == expected_exit
    if interrupt_phase == "before_link":
        assert not destination.exists()
    else:
        installed = SQLiteToolOutcomeStore(destination)
        assert installed.events("atomic-run") == source.events("atomic-run")


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_backup_and_restore_never_replace_existing_destination(tmp_path, operation: str):
    source = SQLiteToolOutcomeStore(tmp_path / "source" / "outcomes.sqlite3")
    source.record_dispatch("no-overwrite-run", 1, "lookup")
    backup_path = source.backup_to(tmp_path / "backup" / "outcomes.sqlite3")
    destination = tmp_path / operation / "destination.sqlite3"
    destination.parent.mkdir(mode=0o700, exist_ok=True)
    original = b"preserve this existing destination"
    destination.write_bytes(original)

    with pytest.raises(ToolOutcomeStoreError):
        if operation == "backup":
            source.backup_to(destination)
        else:
            SQLiteToolOutcomeStore.restore_from(backup_path, destination)

    assert destination.read_bytes() == original


def test_restore_rejects_invalid_event_schema_before_installation(tmp_path):
    invalid_backup = tmp_path / "invalid-backup" / "backup.sqlite3"
    invalid_backup.parent.mkdir(mode=0o700, parents=True)
    with sqlite3.connect(invalid_backup) as connection:
        connection.execute(
            "CREATE TABLE tool_outcome_events (run_id TEXT NOT NULL)"
        )
    destination = tmp_path / "restore-invalid" / "outcomes.sqlite3"

    with pytest.raises(ToolOutcomeStoreError):
        SQLiteToolOutcomeStore.restore_from(invalid_backup, destination)

    assert not destination.exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
@pytest.mark.parametrize("operation", ["initialize", "connection", "backup", "restore"])
def test_store_rejects_symlinked_sidecars_before_sqlite_access_or_chmod(
    tmp_path, suffix: str, operation: str,
):
    source = SQLiteToolOutcomeStore(tmp_path / "source" / "outcomes.sqlite3")
    source.record_dispatch("sidecar-run", 1, "lookup")
    backup = source.backup_to(tmp_path / "backup" / "outcomes.sqlite3")
    database = backup if operation == "restore" else source.path
    sidecar = Path(f"{database}{suffix}")
    sidecar.unlink(missing_ok=True)
    sentinel = tmp_path / "outside" / "sentinel.bin"
    sentinel.parent.mkdir(mode=0o700)
    sentinel_bytes = b"SIDE-CAR-SENTINEL"
    sentinel.write_bytes(sentinel_bytes)
    if os.name == "posix":
        os.chmod(sentinel, 0o640)
        sentinel_mode = stat.S_IMODE(sentinel.stat().st_mode)
    sidecar.symlink_to(sentinel)

    with pytest.raises(ToolOutcomeStoreError):
        if operation == "initialize":
            SQLiteToolOutcomeStore(source.path)
        elif operation == "connection":
            source.record_dispatch("sidecar-run-2", 1, "lookup")
        elif operation == "backup":
            source.backup_to(tmp_path / "second-backup" / "outcomes.sqlite3")
        else:
            SQLiteToolOutcomeStore.restore_from(
                backup, tmp_path / "restore" / "outcomes.sqlite3"
            )

    assert sentinel.read_bytes() == sentinel_bytes
    if os.name == "posix":
        assert stat.S_IMODE(sentinel.stat().st_mode) == sentinel_mode


def test_restore_collision_race_preserves_concurrent_destination(tmp_path, monkeypatch):
    source = SQLiteToolOutcomeStore(tmp_path / "source" / "outcomes.sqlite3")
    source.record_dispatch("restore-race", 1, "lookup")
    backup_path = source.backup_to(tmp_path / "backup" / "outcomes.sqlite3")
    destination = tmp_path / "restore-race" / "destination.sqlite3"
    destination.parent.mkdir(mode=0o700, parents=True)
    original = b"concurrent destination must survive"

    def concurrent_create_then_collide(_temporary, target):
        Path(target).write_bytes(original)
        raise FileExistsError("destination appeared concurrently")

    monkeypatch.setattr(tool_outcome_store_module.os, "link", concurrent_create_then_collide)

    with pytest.raises(ToolOutcomeStoreError):
        SQLiteToolOutcomeStore.restore_from(backup_path, destination)

    assert destination.read_bytes() == original


def test_store_recovery_after_real_subprocess_termination(tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    database = tmp_path / "crash-recovery" / "outcomes.sqlite3"
    child_code = (
        "import os; "
        "from backend.app.tool_outcome_store import SQLiteToolOutcomeStore; "
        "store = SQLiteToolOutcomeStore(); "
        "store.record_dispatch('subprocess-run', 3, 'write'); "
        "os._exit(23)"
    )
    env = os.environ.copy()
    env["AGENT_EXECUTION_OUTCOME_DB"] = str(database)
    env["PYTHONPATH"] = str(repository_root) + os.pathsep + env.get("PYTHONPATH", "")

    child = subprocess.run(
        [sys.executable, "-c", child_code], cwd=repository_root, env=env,
        capture_output=True, text=True, timeout=10,
    )

    assert child.returncode == 23
    store = SQLiteToolOutcomeStore(database)
    assert [event["status"] for event in store.events("subprocess-run")] == ["in_flight"]
    assert store.recover_incomplete() == [{
        "run_id": "subprocess-run",
        "step_number": 3,
        "tool_name": "write",
        "status": "outcome_unknown",
        "reason_code": "tool_outcome_unknown",
    }]
    assert [event["status"] for event in store.events("subprocess-run")] == [
        "in_flight", "outcome_unknown",
    ]


def test_duplicate_events_are_idempotent_and_conflicting_terminal_is_rejected(tmp_path):
    store = SQLiteToolOutcomeStore(tmp_path / "duplicates.sqlite3")
    assert store.record_dispatch("duplicate-run", 1, "lookup") is True
    assert store.record_dispatch("duplicate-run", 1, "lookup") is False
    assert store.record_terminal("duplicate-run", 1, "lookup", "completed") is True
    assert store.record_terminal("duplicate-run", 1, "lookup", "completed") is False
    with pytest.raises(ToolOutcomeStoreError):
        store.record_terminal("duplicate-run", 1, "lookup", "outcome_unknown",
                              "tool_outcome_unknown")


def test_reused_run_step_fails_closed_without_repeating_tool_side_effect(tmp_path):
    side_effects: list[str] = []
    model = ScriptedModel(
        '{"kind":"tool","name":"write","arguments":{}}',
        '{"kind":"final","content":"first run done"}',
        '{"kind":"tool","name":"write","arguments":{}}',
    )
    store = SQLiteToolOutcomeStore(tmp_path / "reused-run.sqlite3")
    service = AgentExecutionService(
        model=model,
        tools=[Tool("write", lambda: side_effects.append("written"), EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
        outcome_store=store,
    )

    first = asyncio.run(service.run("write", run_id="reused-run"))
    with pytest.raises(AgentToolExecutionError) as repeated:
        asyncio.run(service.run("write", run_id="reused-run"))

    assert first["status"] == "completed"
    assert repeated.value.reason_code == "tool_dispatch_already_recorded"
    assert repeated.value.steps[0]["status"] == "not_dispatched"
    assert side_effects == ["written"]
    assert [event["status"] for event in store.events("reused-run")] == [
        "in_flight", "completed",
    ]


def test_dispatch_store_failure_fails_closed_before_tool_handler():
    class BrokenDispatchStore:
        def record_dispatch(self, *_args):
            raise OSError("private database path")

        def record_terminal(self, *_args):
            raise AssertionError("terminal event must not be attempted")

    handler_calls: list[str] = []
    service = AgentExecutionService(
        model=ScriptedModel('{"kind":"tool","name":"write","arguments":{}}'),
        tools=[Tool("write", lambda: handler_calls.append("called"), EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
        outcome_store=BrokenDispatchStore(),
    )

    with pytest.raises(AgentToolExecutionError) as failed:
        asyncio.run(service.run("write", run_id="dispatch-store-fails"))

    assert failed.value.reason_code == "tool_outcome_store_error"
    assert failed.value.steps[0]["status"] == "not_dispatched"
    assert handler_calls == []
    assert "private database path" not in str(failed.value)


def test_terminal_store_failure_stops_next_dispatch_and_recovery_marks_unknown(tmp_path):
    database = tmp_path / "terminal-failure.sqlite3"

    class BrokenTerminalStore(SQLiteToolOutcomeStore):
        def record_terminal(self, *_args, **_kwargs):
            raise OSError("private database error")

    side_effects: list[str] = []
    model = ScriptedModel(
        '{"kind":"tool","name":"write","arguments":{}}',
        '{"kind":"final","content":"must not run"}',
    )
    service = AgentExecutionService(
        model=model,
        tools=[Tool("write", lambda: side_effects.append("written"), EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
        outcome_store=BrokenTerminalStore(database),
    )

    with pytest.raises(AgentToolExecutionError) as failed:
        asyncio.run(service.run("write", run_id="terminal-store-fails"))

    assert side_effects == ["written"]
    assert len(model.calls) == 1
    assert failed.value.reason_code == "tool_outcome_store_error"
    assert failed.value.steps[0]["status"] == "outcome_unknown"
    assert SQLiteToolOutcomeStore(database).recover_incomplete() == [{
        "run_id": "terminal-store-fails",
        "step_number": 1,
        "tool_name": "write",
        "status": "outcome_unknown",
        "reason_code": "tool_outcome_unknown",
    }]


def test_async_task_cancellation_preserves_unknown_tool_outcome_and_cancel_semantics():
    async def scenario() -> tuple[AgentToolExecutionCancelled, bool, list[str]]:
        entered = asyncio.Event()
        release = asyncio.Event()
        side_effects: list[str] = []

        async def tool_that_may_have_side_effect() -> dict:
            side_effects.append("started")
            entered.set()
            await release.wait()
            return {"ok": True}

        service = AgentExecutionService(
            model=ScriptedModel('{"kind":"tool","name":"write","arguments":{}}'),
            tools=[Tool("write", tool_that_may_have_side_effect, EmptyToolArgs)],
            cancellation=CancellationController(audit_writer=lambda _: None),
            tool_policy=allow_tool,
        )
        task = asyncio.create_task(service.run("write", run_id="tool-task-cancelled"))
        await entered.wait()
        task.cancel()
        with pytest.raises(AgentToolExecutionCancelled) as cancelled:
            await task
        return cancelled.value, task.cancelled(), side_effects

    cancelled, task_is_cancelled, side_effects = asyncio.run(scenario())

    assert task_is_cancelled is True
    assert side_effects == ["started"]
    assert cancelled.run_id == "tool-task-cancelled"
    assert cancelled.reason_code == "tool_outcome_unknown"
    assert cancelled.steps == [{
        "step": 1,
        "type": "tool",
        "name": "write",
        "status": "outcome_unknown",
        "reason_code": "tool_outcome_unknown",
    }]
    persisted = SQLiteToolOutcomeStore().events("tool-task-cancelled")
    assert [event["status"] for event in persisted] == ["in_flight", "outcome_unknown"]
    with SQLiteToolOutcomeStore().execution_lock():
        pass


def test_non_serializable_tool_result_preserves_completed_outcome():
    side_effects: list[str] = []

    def write_and_return_unserializable() -> object:
        side_effects.append("written")
        return object()

    service = AgentExecutionService(
        model=ScriptedModel('{"kind":"tool","name":"write","arguments":{}}'),
        tools=[Tool("write", write_and_return_unserializable, EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
    )

    with pytest.raises(AgentToolExecutionError) as failed:
        asyncio.run(service.run("write", run_id="tool-non-json"))

    assert side_effects == ["written"]
    assert failed.value.reason_code == "tool_result_not_serializable"
    assert failed.value.steps == [{
        "step": 1,
        "type": "tool",
        "name": "write",
        "status": "completed_result_unavailable",
        "reason_code": "tool_result_not_serializable",
    }]
    persisted = SQLiteToolOutcomeStore().events("tool-non-json")
    assert [event["status"] for event in persisted] == [
        "in_flight", "completed_result_unavailable",
    ]


def test_non_finite_tool_result_is_not_treated_as_json():
    service = AgentExecutionService(
        model=ScriptedModel('{"kind":"tool","name":"measure","arguments":{}}'),
        tools=[Tool("measure", lambda: float("nan"), EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
    )

    with pytest.raises(AgentToolExecutionError) as failed:
        asyncio.run(service.run("measure", run_id="tool-nan"))

    assert failed.value.reason_code == "tool_result_not_serializable"
    assert failed.value.steps[0]["status"] == "completed_result_unavailable"
    assert failed.value.steps[0]["reason_code"] == "tool_result_not_serializable"
    persisted = SQLiteToolOutcomeStore().events("tool-nan")
    assert [event["status"] for event in persisted] == [
        "in_flight", "completed_result_unavailable",
    ]


def test_oversized_tool_result_preserves_completed_outcome():
    side_effects: list[str] = []

    def write_and_return_large_result() -> str:
        side_effects.append("written")
        return "x" * (64 * 1024)

    service = AgentExecutionService(
        model=ScriptedModel('{"kind":"tool","name":"write","arguments":{}}'),
        tools=[Tool("write", write_and_return_large_result, EmptyToolArgs)],
        cancellation=CancellationController(audit_writer=lambda _: None),
        tool_policy=allow_tool,
    )

    with pytest.raises(AgentToolExecutionError) as failed:
        asyncio.run(service.run("write", run_id="tool-too-large"))

    assert side_effects == ["written"]
    assert failed.value.reason_code == "tool_result_too_large"
    assert failed.value.steps == [{
        "step": 1,
        "type": "tool",
        "name": "write",
        "status": "completed_result_unavailable",
        "reason_code": "tool_result_too_large",
    }]
    persisted = SQLiteToolOutcomeStore().events("tool-too-large")
    assert [event["status"] for event in persisted] == [
        "in_flight", "completed_result_unavailable",
    ]


def test_cancel_during_model_call_prevents_tool_dispatch_and_audit_omits_prompt():
    events: list[dict] = []
    control = CancellationController(audit_writer=events.append)

    class CancellingModel:
        calls = 0

        async def complete(self, messages: list[dict[str, str]]) -> str:
            self.calls += 1
            control.cancel_run("cancel-model", reason_code="security_incident")
            return '{"kind":"tool","name":"dangerous","arguments":{"secret":"do-not-log"}}'

    tool_calls: list[str] = []
    model = CancellingModel()
    service = AgentExecutionService(
        model=model,
        tools=[Tool("dangerous", lambda **kwargs: tool_calls.append("called"), SecretToolArgs)],
        cancellation=control,
        tool_policy=allow_tool,
    )
    task = "private user prompt that must not be logged"

    result = asyncio.run(service.run(task, run_id="cancel-model", actor_id="operator-7", scope="workspace"))

    assert result["status"] == "cancelled"
    assert model.calls == 1
    assert tool_calls == []
    assert len(events) == 1
    assert events[0]["event"] == "agent_run_cancelled"
    assert events[0]["run_id"] == "cancel-model"
    assert events[0]["actor_id"] == "operator-7"
    assert events[0]["scope"] == "workspace"
    assert events[0]["reason_code"] == "security_incident"
    assert "timestamp" in events[0]
    assert task not in json.dumps(events)
    assert "do-not-log" not in json.dumps(events)


def test_cancellation_winning_before_model_dispatch_claim_prevents_invocation():
    reached_claim = threading.Event()
    release_claim = threading.Event()

    class PausingController(CancellationController):
        def claim_dispatch(self, run_id: str, operation: str) -> None:
            if operation == "model":
                reached_claim.set()
                if not release_claim.wait(timeout=5):
                    raise AssertionError("test did not release the model dispatch claim")
            super().claim_dispatch(run_id, operation)

    control = PausingController(audit_writer=lambda _: None)
    model = ScriptedModel('{"kind":"final","content":"must not run"}')
    service = AgentExecutionService(model=model, tools=[], cancellation=control)
    results: list[dict] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(asyncio.run(service.run("task", run_id="cancel-before-claim")))
        except BaseException as exc:  # surface worker-thread failures in the test
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert reached_claim.wait(timeout=5)
        control.cancel_run("cancel-before-claim")
    finally:
        release_claim.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert errors == []
    assert results[0]["status"] == "cancelled"
    assert model.calls == []


def test_model_dispatch_claim_winning_first_makes_call_in_flight():
    claim_granted = threading.Event()
    release_dispatch = threading.Event()

    class PausingController(CancellationController):
        def claim_dispatch(self, run_id: str, operation: str) -> None:
            super().claim_dispatch(run_id, operation)
            if operation == "model":
                claim_granted.set()
                if not release_dispatch.wait(timeout=5):
                    raise AssertionError("test did not release the claimed model dispatch")

    control = PausingController(audit_writer=lambda _: None)
    model = ScriptedModel('{"kind":"final","content":"in flight"}')
    service = AgentExecutionService(model=model, tools=[], cancellation=control)
    results: list[dict] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(asyncio.run(service.run("task", run_id="cancel-after-claim")))
        except BaseException as exc:  # surface worker-thread failures in the test
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert claim_granted.wait(timeout=5)
        control.cancel_run("cancel-after-claim")
    finally:
        release_dispatch.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert errors == []
    assert results[0]["status"] == "cancelled"
    assert len(model.calls) == 1


def test_tool_dispatch_claim_winning_first_preserves_completed_side_effect():
    claim_granted = threading.Event()
    release_dispatch = threading.Event()

    class PausingController(CancellationController):
        def claim_dispatch(self, run_id: str, operation: str) -> None:
            super().claim_dispatch(run_id, operation)
            if operation == "tool":
                claim_granted.set()
                if not release_dispatch.wait(timeout=5):
                    raise AssertionError("test did not release the claimed tool dispatch")

    control = PausingController(audit_writer=lambda _: None)
    model = ScriptedModel(
        '{"kind":"tool","name":"write_ticket","arguments":{}}',
        '{"kind":"final","content":"must not run"}',
    )
    side_effects: list[str] = []
    service = AgentExecutionService(
        model=model,
        tools=[Tool("write_ticket", lambda: side_effects.append("created") or {"ok": True}, EmptyToolArgs)],
        cancellation=control,
        tool_policy=allow_tool,
    )
    results: list[dict] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            results.append(asyncio.run(service.run("create ticket", run_id="tool-claim-wins")))
        except BaseException as exc:  # surface worker-thread failures in the test
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert claim_granted.wait(timeout=5)
        control.cancel_run("tool-claim-wins")
    finally:
        release_dispatch.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert errors == []
    assert results[0]["status"] == "cancelled"
    assert side_effects == ["created"]
    assert results[0]["steps"] == [
        {"step": 1, "type": "tool", "name": "write_ticket", "status": "completed"}
    ]
    assert len(model.calls) == 1


def test_cancel_from_tool_prevents_next_model_dispatch():
    model = ScriptedModel(
        '{"kind":"tool","name":"lookup","arguments":{}}',
        '{"kind":"final","content":"must not be requested"}',
    )
    control = CancellationController(audit_writer=lambda _: None)
    service = AgentExecutionService(
        model=model,
        tools=[Tool("lookup", lambda: control.cancel_run("cancel-after-tool"), EmptyToolArgs)],
        cancellation=control,
        tool_policy=allow_tool,
    )

    result = asyncio.run(service.run("run one step", run_id="cancel-after-tool"))

    assert result["status"] == "cancelled"
    assert len(model.calls) == 1
    assert result["steps"][0]["status"] == "completed"


def test_cancel_during_inflight_tool_does_not_claim_effect_was_undone():
    async def scenario() -> tuple[dict, ScriptedModel, CancellationController]:
        entered = asyncio.Event()
        release = asyncio.Event()
        model = ScriptedModel(
            '{"kind":"tool","name":"write_ticket","arguments":{}}',
            '{"kind":"final","content":"not reached"}',
        )
        control = CancellationController(audit_writer=lambda _: None)
        side_effects: list[str] = []

        async def write_ticket() -> dict:
            entered.set()
            await release.wait()
            side_effects.append("ticket-created")
            return {"created": True}

        service = AgentExecutionService(
            model=model,
            tools=[Tool("write_ticket", write_ticket, EmptyToolArgs)],
            cancellation=control,
            tool_policy=allow_tool,
        )
        task = asyncio.create_task(service.run("create a ticket", run_id="inflight-tool"))
        await entered.wait()
        control.cancel_run("inflight-tool", reason_code="operator_requested")
        release.set()
        result = await task
        assert side_effects == ["ticket-created"]
        return result, model, control

    result, model, _ = asyncio.run(scenario())

    assert result["status"] == "cancelled"
    assert result["steps"] == [{"step": 1, "type": "tool", "name": "write_ticket", "status": "completed"}]
    assert len(model.calls) == 1


def test_global_disable_rejects_new_runs_and_reenable_does_not_revive_cancelled_id():
    events: list[dict] = []
    control = CancellationController(audit_writer=events.append)
    model = ScriptedModel('{"kind":"final","content":"unused"}')
    service = AgentExecutionService(model=model, tools=[], cancellation=control)

    control.disable(actor_id="ops", reason_code="operator_requested")
    with pytest.raises(AgentRunRejected, match="disabled"):
        asyncio.run(service.run("new work", run_id="new-run"))
    assert model.calls == []

    control.enable(actor_id="ops")
    control.begin_run("old-run")
    control.cancel_run("old-run", actor_id="ops")
    control.finish_run("old-run")
    with pytest.raises(AgentRunRejected, match="cannot be reused"):
        asyncio.run(service.run("do not resume", run_id="old-run"))
    assert len(model.calls) == 0
    assert any(event["event"] == "agent_execution_disabled" for event in events)
    assert any(event["event"] == "agent_execution_enabled" for event in events)


def test_repeated_cancellation_is_idempotent():
    events: list[dict] = []
    control = CancellationController(audit_writer=events.append)
    control.begin_run("repeat-cancel")

    assert control.cancel_run("repeat-cancel", actor_id="ops") is True
    assert control.cancel_run("repeat-cancel", actor_id="ops") is False
    assert len(events) == 1


def test_duplicate_active_run_id_is_rejected():
    control = CancellationController(audit_writer=lambda _: None)
    control.begin_run("active-run")

    with pytest.raises(AgentRunRejected, match="already active"):
        control.begin_run("active-run")


def test_runtime_adapter_bridges_existing_chat_adapter():
    class Adapter:
        async def complete(self, request):
            assert request.model == "test-model"
            assert request.messages[-1].content == "hello"

            class Message:
                content = '{"kind":"final","content":"hi"}'

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            class Result:
                response = Response()

            return Result()

    model = RuntimeAgentModel(Adapter(), model="test-model")  # type: ignore[arg-type]
    assert asyncio.run(model.complete([{"role": "user", "content": "hello"}])) == (
        '{"kind":"final","content":"hi"}'
    )
