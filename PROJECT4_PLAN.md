# Project 4 — Productionization Sprint

## Goal
Turn the RAG evaluation backend into a production-style service with deployment, monitoring, and automation.

## Definition of Done
- [ ] Service deployed to cloud with public URL
- [ ] CI/CD pipeline builds and deploys on push to main
- [ ] API key required for /query and /eval/run
- [ ] Latency metrics logged (p50, p95)
- [ ] Error rate and retrieval hit rate tracked
- [ ] README includes 3 command demo

## Phase 1 (This Week)
- Cloud target: GCP (Cloud Run)
- Add basic API key auth middleware
- Add structured logging for requests

## Phase 2
- CI/CD with GitHub Actions
- Metrics aggregation
- Optional lightweight dashboard
