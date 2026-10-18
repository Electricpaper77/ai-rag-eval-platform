variable "project_id" {
  description = "Existing GCP project ID used only when an authorized plan or apply is requested."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid-looking GCP project ID."
  }
}

variable "region" {
  description = "GCP region for the regional GKE cluster and Artifact Registry repository."
  type        = string
  default     = "us-central1"
}

variable "network_name" {
  description = "Dedicated VPC name."
  type        = string
  default     = "agenttrust-vpc"
}

variable "subnet_cidr" {
  description = "Primary IPv4 range for the GKE subnet."
  type        = string
  default     = "10.20.0.0/20"
}

variable "pod_cidr" {
  description = "Secondary IPv4 range for GKE pods."
  type        = string
  default     = "10.21.0.0/16"
}

variable "service_cidr" {
  description = "Secondary IPv4 range for GKE Services."
  type        = string
  default     = "10.22.0.0/20"
}

variable "cluster_name" {
  description = "Regional private GKE cluster name."
  type        = string
  default     = "agenttrust-gke"
}

variable "release_channel" {
  description = "GKE release channel."
  type        = string
  default     = "REGULAR"

  validation {
    condition     = contains(["RAPID", "REGULAR", "STABLE"], var.release_channel)
    error_message = "release_channel must be RAPID, REGULAR, or STABLE."
  }
}

variable "min_master_version" {
  description = "Optional minimum control-plane version; leave null to use the release channel."
  type        = string
  default     = null
  nullable    = true
}

variable "cpu_machine_type" {
  description = "Default CPU node-pool machine type."
  type        = string
  default     = "e2-standard-4"
}

variable "cpu_min_nodes" {
  description = "Minimum CPU node-pool size."
  type        = number
  default     = 1
}

variable "cpu_max_nodes" {
  description = "Maximum CPU node-pool size."
  type        = number
  default     = 3
}

variable "node_disk_type" {
  description = "CPU node-pool boot disk type."
  type        = string
  default     = "pd-balanced"
}

variable "node_disk_size_gb" {
  description = "CPU node-pool boot disk size."
  type        = number
  default     = 100
}

variable "node_service_account" {
  description = "Optional pre-existing node service account email."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_enabled" {
  description = "Whether to declare an optional GPU node pool. This does not provision or verify GPU hardware."
  type        = bool
  default     = false
}

variable "gpu_machine_type" {
  description = "Machine type for the optional GPU node pool; required by the selected GCP region when enabled."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_accelerator_type" {
  description = "GCP accelerator type for the optional GPU node pool."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_accelerator_count" {
  description = "Accelerator count per optional GPU node."
  type        = number
  default     = 1
}

variable "gpu_min_nodes" {
  description = "Minimum optional GPU node-pool size."
  type        = number
  default     = 0
}

variable "gpu_max_nodes" {
  description = "Maximum optional GPU node-pool size."
  type        = number
  default     = 1
}

variable "gpu_node_labels" {
  description = "Labels for the optional GPU node pool."
  type        = map(string)
  default     = {}
}

variable "gpu_node_taints" {
  description = "Taints for the optional GPU node pool."
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  default = []
}

variable "enable_managed_prometheus" {
  description = "Enable GKE managed collection for Prometheus-compatible metrics."
  type        = bool
  default     = false
}

variable "resource_labels" {
  description = "Labels applied to GKE resources."
  type        = map(string)
  default = {
    platform = "agenttrust-iq"
    managed  = "terraform"
  }
}

variable "kubernetes_namespace" {
  description = "Kubernetes namespace used by the AgentTrust workload identity mapping."
  type        = string
  default     = "agenttrust"
}

variable "kubernetes_service_account" {
  description = "Kubernetes service account used by the AgentTrust workload identity mapping."
  type        = string
  default     = "agenttrust"
}

variable "secret_manager_secret_id" {
  description = "Optional existing Secret Manager secret ID to which the mapped identity receives accessor access. No secret value is managed here."
  type        = string
  default     = null
  nullable    = true
}
