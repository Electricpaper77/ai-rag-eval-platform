module "network" {
  source = "./modules/network"

  project_id   = var.project_id
  region       = var.region
  network_name = var.network_name
  subnet_cidr  = var.subnet_cidr
  pod_cidr     = var.pod_cidr
  service_cidr = var.service_cidr
}

module "gke" {
  source = "./modules/gke"

  project_id                = var.project_id
  region                    = var.region
  cluster_name              = var.cluster_name
  network_name              = module.network.network_name
  subnetwork_name           = module.network.subnet_name
  pod_range_name            = module.network.pod_range_name
  service_range_name        = module.network.service_range_name
  release_channel           = var.release_channel
  min_master_version        = var.min_master_version
  cpu_machine_type          = var.cpu_machine_type
  cpu_min_nodes             = var.cpu_min_nodes
  cpu_max_nodes             = var.cpu_max_nodes
  node_disk_type            = var.node_disk_type
  node_disk_size_gb         = var.node_disk_size_gb
  node_service_account      = var.node_service_account
  gpu_enabled               = var.gpu_enabled
  gpu_machine_type          = var.gpu_machine_type
  gpu_accelerator_type      = var.gpu_accelerator_type
  gpu_accelerator_count     = var.gpu_accelerator_count
  gpu_min_nodes             = var.gpu_min_nodes
  gpu_max_nodes             = var.gpu_max_nodes
  gpu_node_labels           = var.gpu_node_labels
  gpu_node_taints           = var.gpu_node_taints
  enable_managed_prometheus = var.enable_managed_prometheus
  resource_labels           = var.resource_labels
}

module "artifact_registry" {
  source = "./modules/artifact_registry"

  project_id      = var.project_id
  region          = var.region
  repository_id   = "agenttrust-iq"
  resource_labels = var.resource_labels
}

module "workload_identity" {
  source = "./modules/workload_identity"

  project_id                 = var.project_id
  kubernetes_namespace       = var.kubernetes_namespace
  kubernetes_service_account = var.kubernetes_service_account
  secret_manager_secret_id   = var.secret_manager_secret_id
}
