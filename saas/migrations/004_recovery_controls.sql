CREATE TABLE IF NOT EXISTS recovery_promotions (
    operation_id TEXT PRIMARY KEY,
    backup_digest TEXT NOT NULL,
    journal_digest TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('approved','promoted','rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at TIMESTAMPTZ NULL
);
CREATE INDEX IF NOT EXISTS recovery_promotions_expiry_idx ON recovery_promotions (expires_at);
