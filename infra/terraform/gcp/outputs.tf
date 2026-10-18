output "network_id" {
  description = "Dedicated VPC self-link."
  value       = module.network.network_id
}

output "subnet_id" {
  description = "GKE subnet self-link."
  value       = module.network.subnet_id
}

output "gke_cluster_name" {
  description = "GKE cluster name."
  value       = module.gke.cluster_name
}

output "artifact_registry_repository_id" {
  description = "Artifact Registry repository ID."
  value       = module.artifact_registry.repository_id
}

output "artifact_registry_repository_url" {
  description = "Artifact Registry repository URL."
  value       = module.artifact_registry.repository_url
}

output "workload_identity_service_account" {
  description = "Google service account mapped to the AgentTrust Kubernetes service account."
  value       = module.workload_identity.google_service_account_email
}
