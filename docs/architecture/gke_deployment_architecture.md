# GKE Deployment Architecture

Client
  ↓
Google Cloud LoadBalancer
  ↓
Kubernetes Service :80
  ↓
Pod :8080
  ↓
FastAPI GenAI Evaluation API

Components

- Containerized FastAPI service
- Docker image stored in Artifact Registry
- CI/CD via Cloud Build
- Deployment to Google Kubernetes Engine
- Public LoadBalancer exposing the API endpoint

External endpoint:
http://34.121.205.47/docs
