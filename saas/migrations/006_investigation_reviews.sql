-- Gate 23D: persisted case evidence, append-only review revisions and release reviews.
-- These records are evidence references, not a deployment authorization mechanism.
CREATE TABLE IF NOT EXISTS evaluation_cases (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    run_id TEXT NOT NULL REFERENCES evaluation_runs(id),
    case_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed','failed','insufficient_evidence')),
    failure_category TEXT NULL,
    score NUMERIC NULL,
    evidence_json JSONB NULL,
    evidence_digest TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance IN ('independently_computed','synthetic_test')),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (run_id, case_key)
);
CREATE INDEX IF NOT EXISTS evaluation_cases_scope_idx
    ON evaluation_cases (organization_id, project_id, run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evaluation_case_review_revisions (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES evaluation_cases(id),
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    run_id TEXT NOT NULL REFERENCES evaluation_runs(id),
    revision INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open','confirmed','rejected','hold')),
    comment TEXT NOT NULL,
    provenance TEXT NOT NULL CHECK (provenance = 'reviewer_confirmed'),
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (case_id, revision),
    UNIQUE (organization_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS evaluation_case_reviews_scope_idx
    ON evaluation_case_review_revisions (organization_id, case_id, revision DESC);

CREATE TABLE IF NOT EXISTS release_reviews (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    project_id TEXT NOT NULL REFERENCES projects(id),
    decision_id TEXT NOT NULL REFERENCES evaluation_decisions(id),
    policy_id TEXT NOT NULL REFERENCES evaluation_policies(id),
    policy_version INTEGER NOT NULL,
    current_run_id TEXT NOT NULL REFERENCES evaluation_runs(id),
    baseline_run_id TEXT NULL REFERENCES evaluation_runs(id),
    recommendation TEXT NOT NULL CHECK (recommendation IN ('acknowledge','hold')),
    decision_status TEXT NOT NULL CHECK (decision_status IN ('PASS','HOLD','INSUFFICIENT_EVIDENCE')),
    rationale_json JSONB NOT NULL,
    evidence_refs_json JSONB NOT NULL,
    evidence_digest TEXT NOT NULL,
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS release_reviews_scope_idx
    ON release_reviews (organization_id, project_id, created_at DESC);

