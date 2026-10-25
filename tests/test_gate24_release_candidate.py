"""Gate 24 release-candidate evidence contract.

Gate 23G performs the real HTTP/PostgreSQL/Chromium journey. These checks run
after it and validate that the release package is complete, provenance-labeled,
sanitized, and reproducible without duplicating product behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.release_candidate
ROOT = Path(__file__).parents[1]
ARTIFACTS = ROOT / "artifacts" / "gate23g"
RELEASE_ARTIFACTS = ROOT / "artifacts" / "gate24"


def _json(path: Path) -> dict:
    assert path.is_file(), f"missing required evidence: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_gate24_scope_docs_and_workflow_are_release_safe() -> None:
    docs = (ROOT / "docs" / "GATE24_MVP_RELEASE_CANDIDATE.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "gate24-mvp-release-candidate.yml").read_text(encoding="utf-8")
    for required in ("synthetic_test", "fixture-only", "PASS", "HOLD", "INSUFFICIENT_EVIDENCE", "MISSING_EVIDENCE", "physical NVIDIA DCGM"):
        assert required in docs
    for required in ("GATE23G_REQUIRED", "AGENTTRUST_SAAS_BACKEND", "postgres_integration", "if-no-files-found: error", "timeout 600s"):
        assert required in workflow
    assert "pytest.skip" not in workflow
    assert "customer data" in docs.lower()


def test_gate24_gate23g_evidence_is_complete_and_sanitized() -> None:
    http = _json(ARTIFACTS / "http-acceptance.json")
    browser = _json(ARTIFACTS / "browser-acceptance.json")
    assert http["synthetic_only"] is True
    assert http["fixture_case_provenance"].startswith("synthetic_test;")
    assert http["security_statuses"] == {
        "cross_tenant": "403_or_404",
        "missing_csrf": 403,
        "quarantine": 503,
        "stale_revision": 409,
        "unauthorized": 401,
    }
    assert browser["synthetic_only"] is True
    assert browser["axe"] == []
    assert browser["keyboard"] is True
    assert browser["refresh"] is True
    assert {item["width"] for item in browser["viewports"]} == {320, 390, 768, 1440}
    assert all(item["scroll_width"] <= item["width"] for item in browser["viewports"])
    for path in ARTIFACTS.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert "synthetic_test" in text or "gate23g" in path.name
        assert "begin private key" not in text
        assert "postgresql://" not in text
        assert not re.search(r"(bearer\s+eyj|password\s*[:=])", text)


def test_gate24_writes_versioned_release_manifest() -> None:
    required = [
        ARTIFACTS / "http-acceptance.json",
        ARTIFACTS / "browser-acceptance.json",
        ARTIFACTS / "pytest.exit",
        *sorted(ARTIFACTS.glob("gate23g-*.png")),
    ]
    assert len(required) == 7, required
    assert (ARTIFACTS / "pytest.exit").read_text(encoding="utf-8").strip() == "0"
    RELEASE_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    files = {}
    for path in required:
        files[str(path.relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "schema": "gate24-mvp-release-candidate-v1",
        "synthetic_only": True,
        "baseline_sha": os.environ.get("GATE24_BASELINE_SHA", "unknown"),
        "commit_sha": os.environ.get("GATE24_EVIDENCE_SHA", "unknown"),
        "gate23g_test_exit": 0,
        "evidence_files": files,
        "limitations": [
            "disposable PostgreSQL and Chromium only",
            "fixture-labeled synthetic evidence only",
            "no production RPO/RTO or physical GPU/DCGM measurement",
        ],
    }
    (RELEASE_ARTIFACTS / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
