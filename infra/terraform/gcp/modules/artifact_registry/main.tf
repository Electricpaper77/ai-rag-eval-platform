resource "google_artifact_registry_repository" "this" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker images for AgentTrust IQ workloads."
  format        = "DOCKER"
  labels        = var.resource_labels
}
