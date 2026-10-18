variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
}

variable "network_name" {
  description = "VPC name."
  type        = string
}

variable "subnet_cidr" {
  description = "Primary subnet CIDR."
  type        = string
}

variable "pod_cidr" {
  description = "Secondary pod CIDR."
  type        = string
}

variable "service_cidr" {
  description = "Secondary service CIDR."
  type        = string
}

