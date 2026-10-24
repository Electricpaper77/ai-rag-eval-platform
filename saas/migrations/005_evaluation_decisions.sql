-- Gate 23C: immutable, tenant-scoped evaluation policies and decisions.
CREATE TABLE IF NOT EXISTS evaluation_policies (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    metrics_json JSONB NOT NULL,
    require_baseline BOOLEAN NOT NULL DEFAULT TRUE,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, project_id, name, version)
);
CREATE INDEX IF NOT EXISTS evaluation_policies_scope_idx
    ON evaluation_policies (organization_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evaluation_decisions (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    current_run_id TEXT NOT NULL REFERENCES evaluation_runs(id),
    baseline_run_id TEXT REFERENCES evaluation_runs(id),
    policy_id TEXT NOT NULL REFERENCES evaluation_policies(id),
    policy_version INTEGER NOT NULL,
    idempotency_key TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('PASS','HOLD','INSUFFICIENT_EVIDENCE')),
    rationale_json JSONB NOT NULL,
    evidence_refs_json JSONB NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (organization_id, current_run_id, policy_id)
);
CREATE INDEX IF NOT EXISTS evaluation_decisions_scope_idx
    ON evaluation_decisions (organization_id, project_id, created_at DESC);

