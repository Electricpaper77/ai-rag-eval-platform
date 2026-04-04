provider "google" {
  project = "ai-rag-eval-prod"
  region  = "us-central1"
}

resource "google_cloud_run_v2_service" "gpu_inference_api" {
  name     = "gpu-inference-api"
  location = "us-central1"

  template {
    containers {
      image = "us-central1-docker.pkg.dev/project/repo/gpu-inference:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }
    }
  }
}
