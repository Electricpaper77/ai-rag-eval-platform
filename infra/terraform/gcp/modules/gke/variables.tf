variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Regional GKE location."
  type        = string
}

variable "cluster_name" {
  description = "GKE cluster name."
  type        = string
}

variable "network_name" {
  description = "VPC name."
  type        = string
}

variable "subnetwork_name" {
  description = "Subnet name."
  type        = string
}

variable "pod_range_name" {
  description = "Secondary pod range name."
  type        = string
}

variable "service_range_name" {
  description = "Secondary service range name."
  type        = string
}

variable "release_channel" {
  description = "GKE release channel."
  type        = string
}

variable "min_master_version" {
  description = "Optional minimum control-plane version."
  type        = string
  default     = null
  nullable    = true
}

variable "cpu_machine_type" {
  description = "CPU node-pool machine type."
  type        = string
}

variable "cpu_min_nodes" {
  description = "CPU node-pool minimum nodes."
  type        = number
}

variable "cpu_max_nodes" {
  description = "CPU node-pool maximum nodes."
  type        = number
}

variable "node_disk_type" {
  description = "Node boot disk type."
  type        = string
}

variable "node_disk_size_gb" {
  description = "Node boot disk size in GB."
  type        = number
}

variable "node_service_account" {
  description = "Optional node service account email."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_enabled" {
  description = "Declare the optional GPU pool. No GPU resources are provisioned by validation."
  type        = bool
  default     = false
}

variable "gpu_machine_type" {
  description = "Optional GPU node-pool machine type."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_accelerator_type" {
  description = "Optional GCP accelerator type."
  type        = string
  default     = null
  nullable    = true
}

variable "gpu_accelerator_count" {
  description = "Optional accelerator count per GPU node."
  type        = number
  default     = 1
}

variable "gpu_min_nodes" {
  description = "Optional GPU pool minimum nodes."
  type        = number
  default     = 0
}

variable "gpu_max_nodes" {
  description = "Optional GPU pool maximum nodes."
  type        = number
  default     = 1
}

variable "gpu_node_labels" {
  description = "Optional GPU node labels."
  type        = map(string)
  default     = {}
}

variable "gpu_node_taints" {
  description = "Optional GPU node taints."
  type = list(object({
    key    = string
    value  = string
    effect = string
  }))
  default = []
}

variable "enable_managed_prometheus" {
  description = "Enable GKE managed Prometheus collection."
  type        = bool
  default     = false
}

variable "resource_labels" {
  description = "Labels applied to GKE resources."
  type        = map(string)
  default     = {}
}
