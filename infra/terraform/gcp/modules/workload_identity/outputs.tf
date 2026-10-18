output "google_service_account_email" {
  description = "Google service account email mapped to the Kubernetes service account."
  value       = google_service_account.agenttrust.email
}

output "kubernetes_service_account_member" {
  description = "Workload Identity member string."
  value       = google_service_account_iam_member.workload_identity_user.member
}
