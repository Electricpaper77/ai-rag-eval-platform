"""Render Gate 2 workload manifests through the self-service builders."""
from pathlib import Path
import argparse
import yaml
from backend.app.workload_platform import WorkloadRequest, build_workload_request, network_policy


def _set_kind_image_policy(item: dict) -> None:
    """Make rendered local-kind workload containers use the preloaded image."""
    spec = item.get("spec", {})
    pod_spec = spec.get("template", {}).get("spec", spec)
    for container in pod_spec.get("containers", []):
        container["imagePullPolicy"] = "Never"


def render_objects() -> list[dict]:
    requests = [
        WorkloadRequest(name="gate2-dev", workload_type="dev-pod", image="agenttrust-iq:gate2"),
        WorkloadRequest(name="gate2-ci", workload_type="ci-job", image="agenttrust-iq:gate2"),
        WorkloadRequest(name="gate2-benchmark", workload_type="benchmark-job", image="agenttrust-iq:gate2"),
        WorkloadRequest(name="gate2-inference", workload_type="inference-service", image="agenttrust-iq:gate2"),
    ]
    objects = [{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "agenttrust-gate2"}}]
    for request in requests:
        for item in build_workload_request(request):
            item.setdefault("metadata", {})["namespace"] = "agenttrust-gate2"
            _set_kind_image_policy(item)
            objects.append(item)
        policy = network_policy(request.name)
        policy["metadata"]["namespace"] = "agenttrust-gate2"
        objects.append(policy)
    return objects


def render(output: Path) -> None:
    objects = render_objects()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("---\n".join(yaml.safe_dump(item, sort_keys=False) for item in objects), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    render(parser.parse_args().output)
