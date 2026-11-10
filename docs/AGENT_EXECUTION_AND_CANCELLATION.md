# Local Agent Execution and Cooperative Cancellation

`backend.app.agent_execution.AgentExecutionService` is a bounded, model-agnostic
multi-step runner. It calls an existing `BaseAdapter` through
`RuntimeAgentModel`, accepts only strict JSON `tool` or `final` actions, and
dispatches tools from an explicit allowlist. Every tool has a `ToolArguments`
Pydantic schema; every nested Pydantic model must also forbid extra fields, so
unknown fields are rejected throughout the schema. A policy callback must
allow the validated action. If no callback is configured, tool actions are denied.
`CancellationController` claims each model and tool dispatch under the same
lock used by cancellation requests. Tool outcome events are persisted locally
by `SQLiteToolOutcomeStore` before and after tool handler execution.

## Local usage

Construct the service inside trusted application code with an existing model
adapter, an explicit tool allowlist, and a controller:

```python
controller = CancellationController()
model = RuntimeAgentModel(adapter, model="your-configured-model")

class LookupPolicyArguments(ToolArguments):
    policy_id: str

def authorize_tool(context: ToolPolicyContext) -> ToolPolicyDecision:
    if context.tool_name == "lookup_policy" and context.scope == "local":
        return ToolPolicyDecision(allowed=True)
    return ToolPolicyDecision(allowed=False, reason_code="tool_policy_denied")

agent = AgentExecutionService(
    model=model,
    tools=[Tool("lookup_policy", lookup_policy, LookupPolicyArguments)],
    cancellation=controller,
    max_steps=4,
    tool_policy=authorize_tool,
)
result = await agent.run("Find the refund review period", actor_id="local-operator")
```

There is intentionally no public HTTP control endpoint in this change. The
repository's API-key middleware is optional, and there is no separate durable
admin authorization or shared cancellation store. Call `cancel_run` or
`disable` only from trusted local application code. Audit records contain the
run ID, actor label, scope, reason code, event, and UTC timestamp. They omit
prompts, model output, tool arguments, and tool output.

## Exact guarantee and limits

- The successful cancellation-state check inside `claim_dispatch`, while
  holding the controller lock, is the linearization point. Model dispatches
  check immediately before calling the model. Tool dispatches first acquire the
  per-database process lock, then claim dispatch immediately before persisting
  its intent. A run cancelled while waiting for that lock does not persist a
  dispatch or invoke its tool. If the dispatch check wins first, the operation
  is considered in flight; later cancellation does not retract it, even if
  provider/tool code has not started yet. A new run is rejected while the
  process-local switch is disabled.
- Runs are registered with the controller before awaiting default-store
  initialization. A `cancel_run()` or `disable()` request wakes a run waiting
  on that initialization and returns it as cancelled before model dispatch.
  The shared store-initialization task continues for other waiters; cancelling
  one run does not cancel initialization needed by another run.
- Cancellation is cooperative. A provider call or tool call already invoked
  may finish; this service does not interrupt remote work or roll back external
  side effects. Completed tool calls remain recorded as completed in the
  returned run steps.
- After a tool dispatch claim, the step is recorded as `in_flight`. If its
  handler raises, the service raises a sanitized `AgentToolExecutionError`
  carrying an `outcome_unknown` step because the handler may have performed a
  partial side effect. If the handler returns but the result is non-JSON or too
  large, the step is `completed_result_unavailable`; no further model/tool
  dispatch occurs. `completed` means the handler returned successfully, not
  that a remote system independently confirmed durable state.
- Async task cancellation during a tool handler still propagates as task
  cancellation and carries a sanitized `outcome_unknown` step. The service
  cannot determine or reverse a partial external effect.
- Tool outcome errors carry only run ID, safe reason codes, and step metadata.
  They omit raw arguments, results, and exception messages.
- Tool step outcomes (`in_flight`, `outcome_unknown`, `completed`, and
  `completed_result_unavailable`) are persisted as an append-only sequence in
  the SQLite tool-outcome database. The default path is
  `artifacts/agent_execution/outcome_store/tool_outcomes.sqlite3`; set
  `AGENT_EXECUTION_OUTCOME_DB` or pass an explicit store to choose another file.
  The default is anchored to the repository root; configured relative paths are
  also resolved from that root, independent of process working directory.
  Production-like local deployments should configure an absolute path on
  persistent storage. On POSIX, the store requires its dedicated parent
  directory to have mode `0700` and restricts the database, backup, and SQLite
  sidecar files to `0600`. On Windows, equivalent protection must be provided
  and verified through filesystem ACLs; POSIX mode-bit tests do not establish
  Windows ACL behavior. On supported POSIX systems, each database has a
  persistent sibling `<database>.lock` file protected by advisory `flock`.
  Executor coroutines wait by polling the OS lock asynchronously, without
  blocking the event loop, and hold it from before dispatch persistence through
  handler completion and terminal-event persistence. Same-database tool
  dispatches therefore run one at a time. No FIFO fairness is promised.
  Synchronous store initialization from a thread without a running event loop
  waits for this lock before opening the database, so a newly starting executor
  process waits for an active dispatch to finish instead of failing on ordinary
  contention. `AgentExecutionService` initializes its default store lazily on
  the first `run()` and performs that synchronous startup in a worker thread,
  keeping the event loop responsive while it waits. Direct synchronous store
  construction on an event-loop thread uses nonblocking lock acquisition and
  fails closed on contention; async callers can use
  `await SQLiteToolOutcomeStore.create_async(path)` to wait off-loop. Recovery
  continues to acquire the lock nonblocking.
  Cancellation is checked while waiting and again after acquisition before
  dispatch persistence. Recovery takes the same lock nonblocking before its
  database preflight; if a cooperating executor holds it, recovery fails with
  `executor_active` without opening the database. The lock file is not deleted
  during normal operation because replacing a locked inode could split
  coordination. Unsupported platforms fail closed. Each tool dispatch event is
  committed before the
  handler runs. If that write fails or the same run/step dispatch already
  exists, the handler is not invoked. A terminal event is committed after the
  handler outcome is known. If that write fails, the run stops and the
  persisted dispatch remains unresolved.
- After confirming the prior executor has stopped, call
  `SQLiteToolOutcomeStore.recover_incomplete()` during local startup/recovery.
  It appends `outcome_unknown` for each dispatch without a terminal event. Do
  not call recovery while an executor using that database may still be active.
  The recovered status is conservative: a side effect may have happened, and
  the store cannot reverse it.
- `backup_to(path)` and `restore_from(backup, destination)` first write a
  sibling temporary SQLite file, close it, and check the backup or source
  integrity. They then publish it with an atomic same-filesystem hard-link
  operation that fails if the destination already exists. The destination is
  either absent or a complete database; an unsupported hard-link filesystem
  fails closed. An abrupt process stop can leave a private `.*.tmp` sibling;
  inspect and remove stale temporary files only after the executor is stopped
  and the intended backup/restore result is identified. These APIs do not
  schedule backups, encrypt them, rotate them, or prove a deployment restore.
- Store initialization, backup creation, restore installation, CLI verification,
  retention planning, and restore drills use one event-schema validator. It
  checks the ordered columns, declared SQLite types, nullability, primary key,
  unique `(run_id, step_number, event_type)` key, and the canonical table DDL
  that defines `AUTOINCREMENT` and the status/reason `CHECK` constraints.
  A schema with matching column names but missing or altered constraints is
  rejected. The validator intentionally requires the canonical DDL form;
  equivalent schemas with different SQL formatting require an explicit
  migration rather than being accepted implicitly. This detects schema drift,
  not malicious database tampering or incorrect external event contents.
- Store initialization rejects a symlinked database path before resolving or
  opening it. Each later store connection uses `lstat` to require that the
  database path still names an existing regular file, so a missing path or an
  observable symlink/special-file replacement fails before SQLite can open or
  create it. These checks are point-in-time only: a same-identity process
  could still replace the database path between `lstat` and SQLite open. The
  per-database cooperative lock serializes executor-managed dispatch and
  recovery operations, but does not make this check atomic or eliminate that
  race.
- Before opening a database, the store and operator CLI inspect existing
  `-wal` and `-shm` entries with `lstat` and reject symlinks (including dangling
  links) and non-regular files. POSIX sidecar permission updates use
  `O_NOFOLLOW` and a file descriptor; if safe no-follow permission handling is
  unavailable, the operation fails closed. Regular WAL files remain supported
  for online backup. These checks do not prevent a malicious process running
  under the same identity from racing to replace a sidecar between preflight
  and SQLite open, so the database directory must remain private to the
  executor and recovery operators.

## Backup retention and operator recovery

The following is the minimum proposed local operating policy; it is not
automated or configured by this repository:

- Create one backup daily and before a database or executor upgrade.
- Retain the newest backup on each of the latest 7 distinct UTC dates, plus
  the newest backup from each of the 4 most recently completed UTC ISO weeks.
  The oldest selected weekly backup may be around a month old depending on
  when it was created.
- Store backups encrypted at rest in a directory restricted to the executor
  service identity and designated recovery operators. Keep the backup outside
  the database directory and filesystem failure domain where the deployment
  supports that safely.
- Verify SQLite integrity after each backup. Perform and record a restore drill
  at least monthly. Delete an expired backup only after a newer backup passes
  integrity verification and a restore drill has succeeded.
- Select and record deployment-specific RPO/RTO before shared use. The above
  schedule does not itself establish either target.

The local CLI is `scripts/agent_execution_store_admin.py`. It requires absolute
paths. Create backups with the UTC naming convention consumed by the planner:

```bash
DB="/absolute/path/to/tool_outcomes.sqlite3"
BACKUP_DIR="/absolute/path/to/private-backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="$BACKUP_DIR/agent-exec-outcomes-$STAMP.sqlite3"

python scripts/agent_execution_store_admin.py backup \
  --database "$DB" --destination "$BACKUP"
python scripts/agent_execution_store_admin.py verify --database "$BACKUP"
python scripts/agent_execution_store_admin.py restore-drill --backup "$BACKUP"
python scripts/agent_execution_store_admin.py retention-plan \
  --directory "$BACKUP_DIR"
python scripts/agent_execution_store_admin.py restore \
  --backup "$BACKUP" \
  --destination "/absolute/path/to/recovery/tool-outcomes-restored.sqlite3"
```

After the prior executor has been stopped and the database is quiescent, an
operator may explicitly close any dispatches without terminal records:

```bash
python scripts/agent_execution_store_admin.py recover-incomplete \
  --database "/absolute/path/to/tool_outcomes.sqlite3" \
  --confirm-executor-stopped
```

The absolute database path and acknowledgement flag are required. The flag is
only an operator assertion. On supported POSIX systems, the command also takes
the same local advisory lock as the executor; that excludes cooperating
executors on the same host while the lock is held. It does not detect
non-cooperating writers, remote hosts, or unsafe network-filesystem lock
semantics. Before writing, the command rejects a missing or symlinked database,
invalid integrity/schema, unsafe sidecars, and a nonempty WAL. These validation
rejections occur before the recovery store is opened for mutation. It appends `outcome_unknown` for each
dispatch with no terminal event in the store's transaction, then checkpoints
its own WAL so a repeated quiescent invocation can report zero additional
recoveries. Success output contains only operation, status, and recovered
count. A post-commit checkpoint error is reported as an error and does not
roll back outcomes already recorded; after resolving the local writer/checkpoint
condition, a repeat is safe because completed dispatches are not duplicated.
Recovered outcomes do not prove that an external tool effect was undone or
that retrying is safe; reconcile with the external system first.

This command is a local single-database recovery action. The cooperative lock
does not establish deployment access controls or prove shared-use, multi-host,
or host/power-loss durability.

Run the read-only local storage report with explicit paths:

```bash
python scripts/agent_execution_store_admin.py readiness \
  --database "$DB" --backup-directory "$BACKUP_DIR"
```

The JSON report has per-check `PASS`, `HOLD`, or `FAIL` statuses for database
presence and integrity/schema, WAL/SHM path safety and POSIX sidecar
permissions, database/directory mode bits, backup-directory safety, and the
read-only retention plan. The retention result contains counts only and never
deletes, moves, or schedules backups. A missing database or backup directory
is `HOLD`; corrupt data, unsafe paths, or unsafe POSIX permissions are `FAIL`.
A nonempty WAL is reported as a safe sidecar but holds immutable integrity
verification until the writer has stopped. On platforms without POSIX mode
bits, permission evidence is `HOLD` until native ACLs are checked separately.

`local_status` may be `PASS` when every performed local check passes. The
overall `status` remains `HOLD` because this repository has no verified
deployment target, executor/recovery identities, target ACL evidence,
configured retention scheduler, or target restore-drill record. It cannot
report deployment/shared-use `READY`. The CLI returns 0 for operations that
complete without a local failure, 1 for readiness `HOLD`, and 2 for `FAIL`.
Output contains check statuses, reason codes, and aggregate counts only; it
does not include filesystem paths or event contents. No report file is written.
This point-in-time local report cannot verify deployment ACLs, scheduler
behavior, retention in operation, or recovery on the deployment target.

Readiness also compares before/after path metadata for the database, WAL/SHM,
their containing directory, the backup directory, and its direct entries. The
metadata includes filesystem identity, file type, mode, size, and change times;
no event contents are read for this comparison. An observed change or an
unavailable comparison adds a `HOLD` consistency check and prevents local
`PASS`; unsafe paths and other existing `FAIL` checks retain `FAIL` precedence.
This is best-effort change detection, not an atomic filesystem snapshot. It
cannot prevent or reliably detect every same-identity race or an actor able to
change data and restore observable metadata, and it is not deployment evidence.

`verify` uses SQLite immutable read-only mode so it does not create WAL/SHM
files. It rejects a nonempty WAL and must be run after the writer has stopped
or against a standalone backup; immutable verification does not include changes
that exist only in a live WAL. `backup` uses SQLite's online backup API for a
consistent source snapshot, including WAL state, and verifies its completed
output. `retention-plan` examines direct children matching the exact
UTC filename pattern, verifies database integrity/schema, and emits JSON lists
of retained files, expiration candidates, unverified files, and unclassified
files. The newest snapshot on each of the latest 7 UTC dates is retained, along
with the newest snapshot from each of the last 4 completed UTC ISO weeks. An
invalid or corrupt file is reported as unverified and is never an expiration
candidate. The planner never deletes, moves, or schedules files.

`restore-drill --backup <absolute-path>` verifies a backup, restores it into a
new private temporary directory, checks the restored database, and compares all
event rows internally. It emits only status, event count, unresolved-dispatch
count, and a records-match boolean; it never prints event rows or the internal
comparison digest. The temporary directory is removed on success and ordinary
exceptions. Abrupt process termination can leave the temporary directory for
operator inspection. This is a local process-level restore exercise only; it
does not verify deployment storage, ACLs, scheduling, backups on another host,
or host/power-loss recovery.

Recovery procedure for a single local executor:

1. Stop the executor and verify that no process can still write to its database.
   Preserve the database and any `-wal`/`-shm` sidecars together as a forensic
   snapshot; do not copy only the main database file while SQLite is active.
2. Choose a verified backup and a new, empty destination on protected storage.
   The CLI refuses to overwrite an existing destination. For example:

   ```bash
   python scripts/agent_execution_store_admin.py restore \
     --backup "/protected/backups/agent-exec-outcomes-20261105T120000Z.sqlite3" \
     --destination "/protected/recovery/tool-outcomes-restored.sqlite3"
   python scripts/agent_execution_store_admin.py verify \
     --database "/protected/recovery/tool-outcomes-restored.sqlite3"
   ```

3. Check the restored path and event sequence using approved operator access.
   Point `AGENT_EXECUTION_OUTCOME_DB` at the restored absolute path, then start
   one executor. After confirming no previous executor is active, call
   `recover_incomplete()` once. Treat every recovered dispatch as an unknown
   external outcome; reconcile with the target system before retrying work.
4. Retain the original database and backup until recovery is accepted and the
   retention policy permits deletion. Record the source backup, destination,
   operator, timestamps, integrity result, and recovery outcome without copying
   prompts, tool arguments, results, or raw exception details into the record.

The local test environment is POSIX and verifies mode bits only. No Windows
host or shared deployment target was supplied, so Windows ACLs or deployment
equivalent permissions have not been configured or verified. Before shared
use, an operator must apply least-privilege ACLs to the database, its directory,
SQLite sidecars, temporary backup files, and retained backups, then verify the
effective access list using that target's native tooling. Until that check,
backup schedule, and restore drill are completed on the actual target, shared
use and broader durability claims remain on hold.
- Events contain only the opaque run ID, step number, allowlisted tool name,
  event status, safe reason code, and UTC timestamp. Prompts, model responses,
  arguments, results, and raw exception details are not stored. Run IDs must be
  non-secret opaque identifiers.
- SQLite WAL mode and `synchronous=FULL` provide a local transactional commit
  boundary subject to the host filesystem and storage device. The POSIX lock
  coordinates only cooperating processes on one host and supported local
  filesystems. This is not a backup, replication, tamper-proof audit log,
  protection from non-cooperating processes, multi-host store, or fleet-wide
  guarantee. A subprocess-termination
  test exercises reopening a committed dispatch and recovering it as unknown;
  backup/restore interruption tests exercise atomic local file publication.
  Neither proves host/power-loss recovery. Loss or corruption of the database
  file can lose history. The retention schedule above is an operator procedure,
  not an implemented scheduler. Protect and back up the file according to the
  deployment's data-retention and access-control policy, and keep broader
  durability claims on hold until target ACLs and recovery operations are tested.
- Re-enabling the controller permits new run IDs. It does not clear cancelled
  run-ID tombstones during that controller's lifetime.
- Controller state and tombstones live only in this Python process. They are
  lost on restart and are not shared across workers or hosts. This is not a
  fleet-wide kill switch, production control plane, or hardware/runtime
  containment claim.
- The tests use scripted model responses and local tool handlers. They prove
  dispatch ordering and cooperative cancellation behavior, not provider-side
  cancellation or production effectiveness.
- Tool input validation rejects missing, malformed, and extra fields before
  policy evaluation. Policy runs before the final dispatch claim; if it allows
  an action but cancellation wins before that claim, the handler is not called.
  Policy denials and invalid arguments produce metadata-only audit events with
  safe reason codes. Unexpected custom-validator exceptions are converted to a
  generic `tool_validation_error` rejection and do not expose exception text.
  Policy callbacks should be decision-only and side-effect-free; tool handlers
  remain responsible for domain-specific authorization and safe side effects.
