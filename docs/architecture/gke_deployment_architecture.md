# GKE Deployment Packaging

Proposed request path:

```text
Client
  -> Google Cloud Load Balancer
  -> Kubernetes Service
  -> FastAPI pod
  -> GenAI evaluation API
```

Repository assets cover:

- FastAPI container packaging.
- Cloud Build configuration.
- Kubernetes deployment and service manifests.
- Health probes and scaling configuration.

This document describes deployment packaging. The previously recorded public IP is retired, and this repository does not claim an active GKE service or production cluster.
