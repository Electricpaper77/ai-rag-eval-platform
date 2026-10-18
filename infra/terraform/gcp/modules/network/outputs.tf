output "network_id" {
  description = "VPC self-link."
  value       = google_compute_network.this.id
}

output "network_name" {
  description = "VPC name."
  value       = google_compute_network.this.name
}

output "subnet_id" {
  description = "Subnet self-link."
  value       = google_compute_subnetwork.this.id
}

output "subnet_name" {
  description = "Subnet name."
  value       = google_compute_subnetwork.this.name
}

output "pod_range_name" {
  description = "Secondary pod range name."
  value       = google_compute_subnetwork.this.secondary_ip_range[0].range_name
}

output "service_range_name" {
  description = "Secondary service range name."
  value       = google_compute_subnetwork.this.secondary_ip_range[1].range_name
}
