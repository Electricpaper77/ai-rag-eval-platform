from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
GCP = ROOT / "infra" / "terraform" / "gcp"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gate4_module_tree_and_provider_pins_exist():
    required = [
        "versions.tf",
        "providers.tf",
        "variables.tf",
        "main.tf",
        "outputs.tf",
        "terraform.tfvars.example",
        "README.md",
        "modules/network/main.tf",
        "modules/gke/main.tf",
        "modules/artifact_registry/main.tf",
        "modules/workload_identity/main.tf",
    ]
    assert all((GCP / item).is_file() for item in required)
    versions = _text(GCP / "versions.tf")
    assert 'version = "= 6.12.0"' in versions
    assert 'required_version = ">= 1.9.8, < 1.10.0"' in versions


def test_gpu_pool_is_disabled_by_default_and_optional():
    variables = _text(GCP / "variables.tf")
    gke = _text(GCP / "modules/gke/main.tf")
    assert re.search(r'variable "gpu_enabled"[\s\S]*?default\s*=\s*false', variables)
    assert 'count = var.gpu_enabled ? 1 : 0' in gke
    assert "guest_accelerator" in gke


def test_private_cluster_workload_identity_and_autoscaling_are_declared():
    gke = _text(GCP / "modules/gke/main.tf")
    assert "enable_private_nodes    = true" in gke
    assert "workload_identity_config" in gke
    assert "workload_pool = \"${var.project_id}.svc.id.goog\"" in gke
    assert "autoscaling" in gke
    assert "auto_repair  = true" in gke
    assert "auto_upgrade = true" in gke


def test_network_secondary_ranges_and_private_google_access_exist():
    network = _text(GCP / "modules/network/main.tf")
    assert "private_ip_google_access = true" in network
    assert network.count("secondary_ip_range") >= 2
    assert 'purpose = "PRIVATE_RFC_1918"' in network


def test_artifact_registry_and_secret_integration_are_scoped():
    registry = _text(GCP / "modules/artifact_registry/main.tf")
    identity = _text(GCP / "modules/workload_identity/main.tf")
    combined = "\n".join(_text(path) for path in GCP.rglob("*.tf"))
    assert "google_artifact_registry_repository" in registry
    assert "google_service_account_iam_member" in identity
    assert "roles/iam.workloadIdentityUser" in identity
    assert "roles/secretmanager.secretAccessor" in identity
    assert not re.search(r'roles/(owner|editor)\b', combined)


def test_project_and_secret_values_are_not_hardcoded():
    combined = "\n".join(_text(path) for path in GCP.rglob("*.tf"))
    assert "project = var.project_id" in combined
    assert "-----BEGIN PRIVATE KEY-----" not in combined
    assert 'project = "ai-rag-eval-prod"' not in combined
