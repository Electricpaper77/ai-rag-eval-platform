"""Gate 25 final release-package contract.

The dedicated workflow provisions PostgreSQL and executes Gate 23G before this
contract. These tests validate only observed, sanitized evidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.gate25_release_manifest import build_manifest


pytestmark = pytest.mark.release_candidate
ROOT = Path(__file__).parents[1]


def test_gate25_docs_remove_obsolete_checkout_pins() -> None:
    gate23g = (ROOT / "docs" / "GATE23G_INDEPENDENT_ACCEPTANCE.md").read_text(encoding="utf-8")
    gate24 = (ROOT / "docs" / "GATE24_MVP_RELEASE_CANDIDATE.md").read_text(encoding="utf-8")
    for docs in (gate23g, gate24):
        assert "849fc838ee9f2d5098a0dd4a009bf28b2d4309de" not in docs
        assert "GATE25_SOURCE_SHA" in docs
        assert "docker rm -f" in docs
        assert "synthetic_test" in docs
        assert "physical NVIDIA DCGM" in docs


def test_gate25_manifest_is_observed_and_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATE25_SOURCE_SHA", "test-source-sha")
    monkeypatch.setenv("GATE25_BASELINE_SHA", "test-baseline-sha")
    manifest = build_manifest(tmp_path / "manifest.json")
    assert manifest["synthetic_only"] is True
    assert manifest["source_sha"] == "test-source-sha"
    assert manifest["commands"]["gate23g_acceptance"]["exit_code"] == 0
    assert manifest["commands"]["gate24_contract"]["exit_code"] == 0
    serialized = json.dumps(manifest).lower()
    assert "postgresql://" not in serialized
    assert "begin private key" not in serialized
    assert not re.search(r"bearer\s+eyj", serialized)


def test_gate25_capability_boundaries_are_explicit() -> None:
    docs = (ROOT / "docs" / "GATE25_V1_RELEASE_VERIFICATION.md").read_text(encoding="utf-8")
    for phrase in ("synthetic_test", "implemented", "independently tested", "simulated", "unverified", "NO-GO"):
        assert phrase.lower() in docs.lower()
