terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_artifact_registry_repository" "inference" {
  project       = var.project_id
  location      = var.region
  repository_id = "inference-service"
  description   = "Container images for inference service"
  format        = "DOCKER"
}

resource "google_cloud_run_service" "inference" {
  name     = "inference-service"
  location = var.region
  project  = var.project_id

  template {
    spec {
      containers {
        image = var.image_name
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  autogenerate_revision_name = true
}
