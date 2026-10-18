"""Render Gate 2 workload manifests through the self-service builders."""
from pathlib import Path
import argparse
import yaml
from backend.app.workload_platform import WorkloadRequest, build_workload_request, network_policy


def render(output: Path) -> None:
    requests = [
        WorkloadRequest(name="gate2-dev", workload_type="dev-pod"),
        WorkloadRequest(name="gate2-ci", workload_type="ci-job"),
        WorkloadRequest(name="gate2-benchmark", workload_type="benchmark-job"),
        WorkloadRequest(name="gate2-inference", workload_type="inference-service"),
    ]
    objects = [{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "agenttrust-gate2"}}]
    for request in requests:
        for item in build_workload_request(request):
            item.setdefault("metadata", {})["namespace"] = "agenttrust-gate2"
            objects.append(item)
        policy = network_policy(request.name)
        policy["metadata"]["namespace"] = "agenttrust-gate2"
        objects.append(policy)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("---\n".join(yaml.safe_dump(item, sort_keys=False) for item in objects), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    render(parser.parse_args().output)
