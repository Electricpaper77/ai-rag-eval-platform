resource "google_container_cluster" "this" {
  project  = var.project_id
  name     = var.cluster_name
  location = var.region

  network    = var.network_name
  subnetwork = var.subnetwork_name

  remove_default_node_pool = true
  initial_node_count       = 1
  networking_mode          = "VPC_NATIVE"

  min_master_version = var.min_master_version

  release_channel {
    channel = var.release_channel
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pod_range_name
    services_secondary_range_name = var.service_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"

    master_global_access_config {
      enabled = false
    }
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]

    managed_prometheus {
      enabled = var.enable_managed_prometheus
    }
  }

  resource_labels     = var.resource_labels
  deletion_protection = false
}

resource "google_container_node_pool" "cpu" {
  project  = var.project_id
  name     = "${var.cluster_name}-cpu"
  location = var.region
  cluster  = google_container_cluster.this.name

  autoscaling {
    min_node_count = var.cpu_min_nodes
    max_node_count = var.cpu_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type    = var.cpu_machine_type
    disk_type       = var.node_disk_type
    disk_size_gb    = var.node_disk_size_gb
    service_account = var.node_service_account
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = merge(var.resource_labels, { "agenttrust-pool" = "cpu" })

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

resource "google_container_node_pool" "gpu" {
  count = var.gpu_enabled ? 1 : 0

  project  = var.project_id
  name     = "${var.cluster_name}-gpu"
  location = var.region
  cluster  = google_container_cluster.this.name

  autoscaling {
    min_node_count = var.gpu_min_nodes
    max_node_count = var.gpu_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type    = var.gpu_machine_type
    service_account = var.node_service_account
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = merge(var.resource_labels, var.gpu_node_labels, { "agenttrust-pool" = "gpu" })

    guest_accelerator {
      type  = var.gpu_accelerator_type
      count = var.gpu_accelerator_count
    }

    dynamic "taint" {
      for_each = var.gpu_node_taints
      content {
        key    = taint.value.key
        value  = taint.value.value
        effect = taint.value.effect
      }
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}
