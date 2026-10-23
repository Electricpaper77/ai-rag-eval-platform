-- Gate 22C: forward-only tenant lifecycle metadata. Never rewrite applied migrations.
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;
CREATE TABLE IF NOT EXISTS tenant_lifecycle_audit (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    actor_user_id TEXT,
    action TEXT NOT NULL CHECK (action IN ('export.requested','export.completed','retention.cleanup','deletion.requested','deletion.completed')),
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS tenant_lifecycle_audit_org_idx ON tenant_lifecycle_audit (organization_id, created_at);
