# AgentTrust IQ SaaS architecture

Production shape: external OIDC identity → FastAPI authorization → managed PostgreSQL → bounded evaluation execution → tenant-scoped JSON/JSONL evidence. The local slice keeps the existing FastAPI process and uses SQLite only for reproducible tests. Its configured bearer identity map is LOCAL/TEST ONLY and is not production authentication. No Kubernetes, microservice, Redis, or broker is justified by current measured requirements.

Entities are organizations, memberships, projects, evaluation_runs, evaluation_results, usage_events, and audit_events. `saas/migrations/001_initial.sql` is an additive migration; production requires reviewed down migration, backups, and restore testing. Cost drivers are estimates only: managed database, API compute, evidence storage, identity MAU, and model-provider usage. No paid infrastructure was deployed.
