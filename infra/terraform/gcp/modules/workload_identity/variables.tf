variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "kubernetes_namespace" {
  description = "Kubernetes namespace for the mapped service account."
  type        = string
}

variable "kubernetes_service_account" {
  description = "Kubernetes service account name."
  type        = string
}

variable "secret_manager_secret_id" {
  description = "Optional existing secret ID for a narrowly scoped accessor binding."
  type        = string
  default     = null
  nullable    = true
}

