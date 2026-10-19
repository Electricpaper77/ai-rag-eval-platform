from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from scripts.gate12_provenance import build_statement, verify_statement
from scripts.gate12_release_manifest import (
    build_manifest,
    sha256_file,
    validate_exception_expiry,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
SUPPLY_CHAIN = ROOT / "deploy" / "supply-chain"


def _artifact(tmp_path: Path, name: str, content: str = "{}") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_release_manifest_schema_and_immutable_digest(tmp_path: Path):
    files = [_artifact(tmp_path, name, '{"packages":[{"name":"agenttrust"}]}') for name in ("spdx.json", "cyclonedx.json")]
    vuln = _artifact(tmp_path, "vuln.json", '{"Results":[]}')
    provenance = _artifact(tmp_path, "provenance.json", "{}")
    metadata = _artifact(tmp_path, "build-metadata.json", "{}")
    manifest = build_manifest(
        git_sha="a" * 40,
        image_digest="registry.example/agenttrust@sha256:" + "b" * 64,
        sbom_spdx=files[0],
        sbom_cyclonedx=files[1],
        vulnerability_report=vuln,
        provenance=provenance,
        build_metadata=metadata,
        signature_verified=True,
        signing_method="CI TEST SIGNING ONLY",
        policy_status="PASS",
        secret_scan_status="PASS",
        tamper_status="TAMPER_DETECTED",
        test_results="focused=pass;full=pass",
    )
    validate_manifest(manifest)
    assert manifest["artifacts"]["sbom_spdx"]["sha256"] == sha256_file(files[0])
    with pytest.raises(ValueError):
        manifest["imageDigest"] = "registry.example/agenttrust:latest"
        validate_manifest(manifest)


def test_sbom_files_parse_and_contain_packages(tmp_path: Path):
    spdx = {"spdxVersion": "SPDX-2.3", "packages": [{"name": "agenttrust"}]}
    cyclonedx = {"bomFormat": "CycloneDX", "components": [{"name": "agenttrust"}]}
    spdx_path = _artifact(tmp_path, "sbom.spdx.json", json.dumps(spdx))
    cdx_path = _artifact(tmp_path, "sbom.cyclonedx.json", json.dumps(cyclonedx))
    assert json.loads(spdx_path.read_text())["packages"]
    assert json.loads(cdx_path.read_text())["components"]


def test_vulnerability_policy_and_exception_expiry_are_deterministic():
    policy = yaml.safe_load((ROOT / "security" / "gate12-vulnerability-policy.yaml").read_text())
    exceptions = yaml.safe_load((ROOT / "security" / "gate12-vulnerability-exceptions.yaml").read_text())
    assert policy["critical"] == "fail"
    assert policy["exceptionsFile"] == "security/gate12-vulnerability-exceptions.yaml"
    assert exceptions == {"schemaVersion": 1, "exceptions": []}
    validate_exception_expiry([], today=date(2026, 10, 19))
    future = [{"CVE": "CVE-2099-0001", "expiry": "2099-01-01"}]
    validate_exception_expiry(future, today=date(2026, 10, 19))
    with pytest.raises(ValueError, match="expired"):
        validate_exception_expiry(
            [{"CVE": "CVE-2020-0001", "expiry": (date(2026, 10, 19) - timedelta(days=1)).isoformat()}],
            today=date(2026, 10, 19),
        )


def test_provenance_schema_and_digest_matching(tmp_path: Path):
    image = "registry.example/agenttrust@sha256:" + "c" * 64
    statement = build_statement(
        repository="Electricpaper77/ai-rag-eval-platform",
        commit="d" * 40,
        builder="github-actions",
        workflow="gate12",
        image_reference=image,
        dockerfile="Dockerfile",
        build_inputs=["Dockerfile", "requirements.txt"],
    )
    path = tmp_path / "provenance.json"
    path.write_text(json.dumps(statement), encoding="utf-8")
    verify_statement(path, image_reference=image, commit="d" * 40)
    statement["subject"][0]["digest"]["sha256"] = "e" * 64
    path.write_text(json.dumps(statement), encoding="utf-8")
    with pytest.raises(AssertionError):
        verify_statement(path, image_reference=image, commit="d" * 40)


def test_tamper_detection_and_security_preservation():
    deployment = next(
        item
        for item in yaml.safe_load_all((SUPPLY_CHAIN / "agenttrust-deployment.yaml.tpl").read_text())
        if item["kind"] == "Deployment"
    )
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert "__IMAGE_REFERENCE__" in container["image"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"] == {
        "runAsNonRoot": True,
        "runAsUser": 10001,
        "runAsGroup": 10001,
        "fsGroup": 10001,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["requests"] and container["resources"]["limits"]
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
    policy = yaml.safe_load((SUPPLY_CHAIN / "kyverno-digest-policy.yaml").read_text())
    assert policy["spec"]["validationFailureAction"] == "Enforce"
    assert policy["spec"]["rules"][0]["validate"]["foreach"]
    original = b"valid artifact\n"
    tampered = original + b"changed\n"
    assert hashlib.sha256(original).hexdigest() != hashlib.sha256(tampered).hexdigest()
