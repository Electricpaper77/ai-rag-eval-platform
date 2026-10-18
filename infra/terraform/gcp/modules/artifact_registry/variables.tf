variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Artifact Registry region."
  type        = string
}

variable "repository_id" {
  description = "Docker repository ID."
  type        = string
}

variable "resource_labels" {
  description = "Labels applied to the repository."
  type        = map(string)
  default     = {}
}
