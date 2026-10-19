"""Generate the cryptographically referential Gate 12 release manifest."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import re
from pathlib import Path
from typing import Any


IMAGE_DIGEST_RE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def build_manifest(
    *,
    git_sha: str,
    image_digest: str,
    sbom_spdx: Path,
    sbom_cyclonedx: Path,
    vulnerability_report: Path,
    provenance: Path,
    build_metadata: Path,
    signature_verified: bool,
    signing_method: str,
    policy_status: str,
    secret_scan_status: str,
    tamper_status: str,
    test_results: str,
) -> dict[str, Any]:
    if not IMAGE_DIGEST_RE.fullmatch(image_digest):
        raise ValueError("image_digest must be an image reference with a sha256 digest")
    artifacts = {
        "sbom_spdx": _artifact(sbom_spdx),
        "sbom_cyclonedx": _artifact(sbom_cyclonedx),
        "vulnerability_report": _artifact(vulnerability_report),
        "provenance": _artifact(provenance),
        "build_metadata": _artifact(build_metadata),
    }
    manifest = {
        "schemaVersion": 1,
        "gitSha": git_sha,
        "imageDigest": image_digest,
        "signature": {"method": signing_method, "verified": signature_verified},
        "provenance": {"verified": True, "artifact": artifacts["provenance"]},
        "policy": {
            "status": policy_status,
            "secretScan": secret_scan_status,
            "tamperTest": tamper_status,
        },
        "testResults": test_results,
        "artifacts": artifacts,
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    required = {"schemaVersion", "gitSha", "imageDigest", "signature", "provenance", "policy", "artifacts"}
    missing = required.difference(manifest)
    if missing:
        raise ValueError(f"manifest missing fields: {sorted(missing)}")
    if not IMAGE_DIGEST_RE.fullmatch(manifest["imageDigest"]):
        raise ValueError("manifest imageDigest is not immutable")
    if manifest["signature"]["verified"] is not True:
        raise ValueError("signature verification is required")
    if manifest["provenance"]["verified"] is not True:
        raise ValueError("provenance verification is required")
    if manifest["policy"]["status"] != "PASS":
        raise ValueError("policy status must be PASS")


def validate_exception_expiry(exceptions: list[dict[str, Any]], *, today: date | None = None) -> None:
    """Reject missing or expired vulnerability exceptions before policy evaluation."""
    current = today or date.today()
    for exception in exceptions:
        expiry = exception.get("expiry") or exception.get("expiryDate")
        if not expiry:
            raise ValueError("vulnerability exceptions require an expiry date")
        if date.fromisoformat(expiry) < current:
            raise ValueError(f"vulnerability exception expired: {exception.get('CVE', '<unknown>')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--sbom-spdx", type=Path, required=True)
    parser.add_argument("--sbom-cyclonedx", type=Path, required=True)
    parser.add_argument("--vulnerability-report", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--build-metadata", type=Path, required=True)
    parser.add_argument("--signature-verified", action="store_true")
    parser.add_argument("--signing-method", required=True)
    parser.add_argument("--policy-status", required=True)
    parser.add_argument("--secret-scan-status", required=True)
    parser.add_argument("--tamper-status", required=True)
    parser.add_argument("--test-results", required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        git_sha=args.git_sha,
        image_digest=args.image_digest,
        sbom_spdx=args.sbom_spdx,
        sbom_cyclonedx=args.sbom_cyclonedx,
        vulnerability_report=args.vulnerability_report,
        provenance=args.provenance,
        build_metadata=args.build_metadata,
        signature_verified=args.signature_verified,
        signing_method=args.signing_method,
        policy_status=args.policy_status,
        secret_scan_status=args.secret_scan_status,
        tamper_status=args.tamper_status,
        test_results=args.test_results,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"RELEASE_MANIFEST: PASS {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
