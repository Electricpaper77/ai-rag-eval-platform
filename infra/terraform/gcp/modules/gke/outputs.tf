output "cluster_name" {
  description = "GKE cluster name."
  value       = google_container_cluster.this.name
}

output "cluster_id" {
  description = "GKE cluster self-link."
  value       = google_container_cluster.this.id
}

output "cpu_node_pool_name" {
  description = "Default CPU node-pool name."
  value       = google_container_node_pool.cpu.name
}

output "gpu_node_pool_name" {
  description = "Optional GPU node-pool name, or null when disabled."
  value       = var.gpu_enabled ? google_container_node_pool.gpu[0].name : null
}
