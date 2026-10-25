"""Build a sanitized, source-pinned Gate 25 release manifest.

The manifest is generated only from files produced by the real acceptance
workflow.  It intentionally records observed exit codes and environment
metadata, rather than asserting metrics that were not measured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[1]
EVIDENCE_ROOTS = (ROOT / "artifacts" / "gate23g", ROOT / "artifacts" / "gate24")
SECRET_PATTERNS = (
    "begin private key",
    "postgresql://",
    "bearer eyj",
    "authorization: bearer",
    "password=",
    '"password":',
)


def _env(name: str, default: str = "unknown") -> str:
    return os.environ.get(name, default)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _exit(path: Path) -> int:
    if not path.is_file():
        return 1
    return int(path.read_text(encoding="utf-8").strip())


def _evidence_files() -> dict[str, str]:
    files: dict[str, str] = {}
    for root in EVIDENCE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "release-manifest.json"):
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            text = data.decode("utf-8", errors="replace").lower()
            if any(pattern in text for pattern in SECRET_PATTERNS):
                raise ValueError(f"potential secret in evidence: {relative}")
            files[relative] = hashlib.sha256(data).hexdigest()
    return files


def build_manifest(output: Path) -> dict[str, Any]:
    source_sha = _env("GATE25_SOURCE_SHA", _git_sha())
    evidence_files = _evidence_files()
    required = {
        "artifacts/gate23g/http-acceptance.json",
        "artifacts/gate23g/browser-acceptance.json",
        "artifacts/gate23g/pytest.exit",
        "artifacts/gate24/pytest.exit",
    }
    missing = sorted(required - evidence_files.keys())
    if missing:
        raise ValueError(f"missing required evidence: {missing}")
    if _exit(ROOT / "artifacts/gate23g" / "pytest.exit") != 0:
        raise ValueError("Gate 23G acceptance did not exit 0")
    if _exit(ROOT / "artifacts/gate24" / "pytest.exit") != 0:
        raise ValueError("Gate 24 release contract did not exit 0")

    workflow_url = _env("GATE25_WORKFLOW_URL")
    manifest: dict[str, Any] = {
        "schema": "agenttrust-gate25-release-v1",
        "release": "AgentTrust IQ v1.0.0",
        "release_status": "NON_PRODUCTION_RELEASE_CANDIDATE",
        "source_sha": source_sha,
        "baseline_sha": _env("GATE25_BASELINE_SHA", source_sha),
        "workflow_url": workflow_url,
        "workflow_run_id": _env("GITHUB_RUN_ID"),
        "commands": {
            "gate23g_collection": {"exit_code": _exit(ROOT / "artifacts/gate23g/collection.exit")},
            "gate23g_acceptance": {"exit_code": _exit(ROOT / "artifacts/gate23g/pytest.exit")},
            "gate24_collection": {"exit_code": _exit(ROOT / "artifacts/gate24/collection.exit")},
            "gate24_contract": {"exit_code": _exit(ROOT / "artifacts/gate24/pytest.exit")},
        },
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "node": _env("GATE25_NODE_VERSION"),
            "postgres": _env("GATE25_POSTGRES_VERSION", "postgres:16 disposable service"),
            "browser": _env("GATE25_BROWSER", "Chromium headless"),
        },
        "evidence_files": evidence_files,
        "capabilities": {
            "implemented": ["authenticated FastAPI SaaS journey", "tenant-scoped persisted evidence"],
            "independently_tested": ["PostgreSQL HTTP routes", "Chromium UI", "axe-core", "keyboard navigation", "refresh persistence"],
            "simulated": ["OIDC provider", "evaluation provider", "GPU telemetry labels"],
            "unverified": ["managed OIDC", "production RPO/RTO", "cloud PITR", "physical NVIDIA DCGM metrics"],
        },
        "limitations": [
            "disposable PostgreSQL and local Chromium only",
            "fixture-sourced case rows are labeled synthetic_test and are not provider measurements",
            "no production deployment, billing, customer data, production RPO/RTO or physical GPU/DCGM claim",
        ],
        "synthetic_only": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build_manifest(args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"gate25 manifest error: {exc}", file=sys.stderr)
        return 1
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
