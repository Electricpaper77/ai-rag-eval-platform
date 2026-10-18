resource "google_service_account" "agenttrust" {
  project      = var.project_id
  account_id   = "agenttrust-workload"
  display_name = "AgentTrust IQ workload identity"
  description  = "Least-privilege identity for the AgentTrust Kubernetes workload."
}

resource "google_service_account_iam_member" "workload_identity_user" {
  service_account_id = google_service_account.agenttrust.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.kubernetes_namespace}/${var.kubernetes_service_account}]"
}

resource "google_secret_manager_secret_iam_member" "secret_accessor" {
  count = var.secret_manager_secret_id == null ? 0 : 1

  project   = var.project_id
  secret_id = var.secret_manager_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agenttrust.email}"
}
