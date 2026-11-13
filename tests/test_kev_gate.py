import json
from pathlib import Path
import pytest
from scripts.kev_gate import Package, ScanUnavailable, _exit_code, advisory_match, scan, version_in_range

@pytest.fixture(autouse=True)
def synthetic_inventory(monkeypatch):
    monkeypatch.setattr("scripts.kev_gate.inventory_packages", lambda _: [Package("gpustack", "2.1.1", "fixture", True), Package("unrelated", "9.9.9", "fixture", False)])

def advisory(name="gpustack", aliases=None, fixed="2.2.0"):
    return {"aliases": aliases or ["CVE-2026-102895"], "affected": [{"package": {"ecosystem": "PyPI", "name": name}, "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": fixed}]}]}]}

def catalog(cve="CVE-2026-102895"):
    return {"catalogVersion": "2026-11-12", "vulnerabilities": [{"cveID": cve, "vendorProject": "GPUStack", "product": "GPUStack", "dateAdded": "2026-11-01"}]}

def test_vulnerable_gpustack_is_blocked():
    report = scan(Path("."), catalog(), lambda _: advisory(), "abc123")
    assert report["scan_status"] == "affected" and _exit_code(report) == 1
    assert report["findings"][0]["status"] == "confirmed_affected"

def test_patched_gpustack_is_unaffected():
    report = scan(Path("."), catalog(), lambda _: advisory(fixed="2.1.1"), "abc123")
    assert report["findings"][0]["status"] == "confirmed_unaffected" and report["scan_status"] == "pass"

def test_unrelated_package_is_not_a_false_positive():
    report = scan(Path("."), catalog(), lambda _: advisory(), "abc123")
    assert all(item["package"] != "unrelated" for item in report["findings"])

def test_missing_package_version_is_unknown(monkeypatch):
    monkeypatch.setattr("scripts.kev_gate.inventory_packages", lambda _: [Package("gpustack", "unknown", "fixture", True)])
    report = scan(Path("."), catalog(), lambda _: advisory(), "abc123")
    assert report["findings"][0]["status"] == "unknown" and _exit_code(report) == 2

def test_missing_catalog_data_is_unavailable():
    with pytest.raises(ScanUnavailable): scan(Path("."), {}, lambda _: advisory(), "abc123")

def test_advisory_mismatch_is_unavailable():
    report = scan(Path("."), catalog(), lambda _: advisory(aliases=["CVE-OTHER"]), "abc123")
    assert report["scan_status"] == "unavailable" and _exit_code(report) == 2
    assert report["errors"][0]["type"] == "advisory_mismatch"

def test_unavailable_advisory_is_fail_closed():
    def unavailable(_): raise ScanUnavailable("service down")
    report = scan(Path("."), catalog(), unavailable, "abc123")
    assert report["scan_status"] == "unavailable" and _exit_code(report) == 2

def test_every_report_has_schema_and_commit_sha():
    report = scan(Path("."), catalog(), lambda _: advisory(), "commit-1")
    assert set(("schema_version", "scanned_commit_sha", "scan_status", "catalog_source", "catalog_timestamp", "elapsed_ms", "packages", "findings", "errors")) <= report.keys()
    assert report["scanned_commit_sha"] == "commit-1"

def test_version_matching_and_advisory_identity():
    assert version_in_range("2.1.1", advisory()["affected"][0]["ranges"][0]["events"]) is True
    assert version_in_range("2.2.0", advisory()["affected"][0]["ranges"][0]["events"]) is False
    assert advisory_match(Package("gpustack", "2.1.1", "fixture", True), advisory()) is True
    assert advisory_match(Package("gpustack", "2.1.1", "fixture", True), advisory(aliases=["CVE-OTHER"]), "CVE-2026-102895") is None

def test_incomplete_version_range_is_unknown_not_unaffected():
    incomplete = {"aliases": ["CVE-2026-102895"], "affected": [{"package": {"ecosystem": "PyPI", "name": "gpustack"}, "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}]}]}]}
    report = scan(Path("."), catalog(), lambda _: incomplete, "abc123")
    assert report["findings"][0]["status"] == "unknown" and _exit_code(report) == 2

