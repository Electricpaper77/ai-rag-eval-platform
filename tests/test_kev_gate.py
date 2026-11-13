from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.kev_gate import Package, ScanUnavailable, _exit_code, advisory_match, inventory_packages, scan, version_in_range

@pytest.fixture(autouse=True)
def inventory(monkeypatch):
    monkeypatch.setattr("scripts.kev_gate.inventory_packages", lambda _: [Package("gpustack", "2.1.1", "fixture", True), Package("unrelated", "9.9.9", "fixture", False)])

def catalog(cve="CVE-2026-102895"):
    return {"catalogVersion":"fixture","vulnerabilities":[{"cveID":cve,"vendorProject":"GPUStack","product":"GPUStack","dateAdded":"2026-11-01"}]}

def advisory(aliases=None, fixed="2.2.0"):
    return {"id":"GHSA-gj9m-f8ph-pmhr","aliases":aliases or ["CVE-2026-102895"],"affected":[{"package":{"ecosystem":"PyPI","name":"gpustack"},"ranges":[{"type":"ECOSYSTEM","events":[{"introduced":"0"},{"fixed":fixed}]}]}]}

def query(_): return 200, {"vulns":[{"id":"GHSA-gj9m-f8ph-pmhr","aliases":["CVE-2026-102895"]}]}
def detail(_): return 200, advisory()

def test_vulnerable_and_patched_versions():
    report=scan(Path("."),catalog(),query,detail,"sha"); assert report["scan_status"]=="affected" and _exit_code(report)==1
    report=scan(Path("."),catalog(),query,lambda _: (200,advisory(fixed="2.1.1")),"sha"); assert report["findings"][0]["status"]=="confirmed_unaffected"

def test_unrelated_kev_without_osv_record_does_not_block():
    def no_record(payload): return (200,{}) if payload["package"]["name"]=="unrelated" else query(payload)
    report=scan(Path("."),catalog("CVE-OTHER"),no_record,detail,"sha"); assert report["scan_status"]=="pass" and not report["errors"]

def test_unexpected_http_404_and_transient_http_fail_closed():
    for status in (404, 429, 503):
        report=scan(Path("."),catalog(),lambda _: (status, None),detail,"sha")
        assert report["scan_status"]=="unavailable" and _exit_code(report)==2

def test_pagination_finds_page_two_advisory_and_rejects_bad_tokens():
    def paged(payload):
        return (200, {"vulns": [], "next_page_token": "next"}) if "page_token" not in payload else query(payload)
    report=scan(Path("."),catalog(),paged,detail,"sha")
    assert report["scan_status"]=="affected"
    for token_response in ({"vulns": [], "next_page_token": "same"}, {"vulns": [], "next_page_token": 3}):
        report=scan(Path("."),catalog(),lambda _: (200, token_response),detail,"sha")
        assert report["scan_status"]=="unavailable"

def test_relevant_advisory_mismatch_and_service_failure_fail_closed():
    report=scan(Path("."),catalog(),query,lambda _: (200,advisory(["CVE-OTHER"])),"sha"); assert report["scan_status"]=="unavailable" and _exit_code(report)==2
    report=scan(Path("."),catalog(),lambda _: (_ for _ in ()).throw(ScanUnavailable("down")),detail,"sha"); assert report["scan_status"]=="unavailable"

def test_malformed_query_and_missing_catalog_fail_closed():
    report=scan(Path("."),catalog(),lambda _: (200,{"vulns":"bad"}),detail,"sha"); assert report["scan_status"]=="unavailable"
    with pytest.raises(ScanUnavailable): scan(Path("."),{},query,detail,"sha")

def test_unknown_version_and_complex_boundary_are_not_safe():
    unknown=[Package("gpustack","unknown","fixture",True)]
    from scripts import kev_gate
    original=kev_gate.inventory_packages; kev_gate.inventory_packages=lambda _: unknown
    try:
        report=scan(Path("."),catalog(),query,detail,"sha"); assert report["findings"][0]["status"]=="unknown" and _exit_code(report)==2
    finally: kev_gate.inventory_packages=original
    events=[{"introduced":"0"},{"fixed":"2.2.0"},{"introduced":"3.0.0"},{"fixed":"3.1.0"}]
    assert version_in_range("2.2.0",events) is False and version_in_range("3.0.5",events) is True and version_in_range("2.5.0",[{"introduced":"0"}]) is None

def test_explicit_versions_multiple_ranges_and_incomplete_range():
    explicit=advisory(); explicit["affected"][0]["versions"]=["2.1.1"]
    assert advisory_match(Package("gpustack","2.1.1","fixture",True), explicit, "CVE-2026-102895") is True
    multi=advisory(); multi["affected"][0]["ranges"]= [{"type":"ECOSYSTEM","events":[{"introduced":"0"},{"fixed":"2.0.0"}]},{"type":"ECOSYSTEM","events":[{"introduced":"3.0.0"},{"fixed":"3.1.0"}]}]
    assert advisory_match(Package("gpustack","3.0.5","fixture",True),multi,"CVE-2026-102895") is True
    incomplete=advisory(); incomplete["affected"][0]["ranges"]= [{"type":"ECOSYSTEM","events":[{"introduced":"0"}]}]
    assert advisory_match(Package("gpustack","2.1.1","fixture",True),incomplete,"CVE-2026-102895") is None

def test_catalog_correlation_schema_and_commit_sha():
    report=scan(Path("."),catalog(),query,detail,"commit-sha"); assert report["scanned_commit_sha"]=="commit-sha"; assert report["catalog_timestamp"]=="fixture"; assert {"schema_version","scan_status","catalog_source","elapsed_ms","python_version","dependency_inventory_source","dependency_inventory_scope","dependency_inventory_digest","application_package_count","scanner_test_package_count","scanner_test_dependencies","packages","findings","errors","unsupported_ecosystems","inventory_limitations"}<=report.keys()
    assert advisory_match(Package("gpustack","2.1.1","fixture",True),advisory(),"CVE-2026-102895") is True

def test_missing_runtime_requirements_fails_closed(tmp_path):
    with pytest.raises(ScanUnavailable, match="requirements.txt"):
        inventory_packages(tmp_path)

def test_inventory_scope_and_conflicting_resolved_versions_fail_closed(monkeypatch, tmp_path):
    (tmp_path / "requirements.txt").write_text("gpustack==2.1.1\npytest==8\n", encoding="utf-8")
    def resolver(args, **kwargs):
        report = Path(args[args.index("--report") + 1])
        report.write_text('{"install":[{"metadata":{"name":"gpustack","version":"2.1.1"}},{"metadata":{"name":"pytest","version":"8.3.5"}}]}', encoding="utf-8")
        return SimpleNamespace()
    monkeypatch.setattr("scripts.kev_gate.subprocess.run", resolver)
    packages=inventory_packages(tmp_path)
    assert {item.scope for item in packages} == {"application_runtime", "scanner_or_test"}
    def duplicate(args, **kwargs):
        report = Path(args[args.index("--report") + 1])
        report.write_text('{"install":[{"metadata":{"name":"gpustack","version":"2.1.1"}},{"metadata":{"name":"GPUStack","version":"2.2.0"}}]}', encoding="utf-8")
        return SimpleNamespace()
    monkeypatch.setattr("scripts.kev_gate.subprocess.run", duplicate)
    with pytest.raises(ScanUnavailable, match="conflicting"):
        inventory_packages(tmp_path)

def test_unavailable_inventory_fails_closed(monkeypatch):
    monkeypatch.setattr("scripts.kev_gate.inventory_packages", lambda _: (_ for _ in ()).throw(ScanUnavailable("resolver unavailable")))
    with pytest.raises(ScanUnavailable, match="resolver unavailable"):
        scan(Path("."), catalog(), query, detail, "commit-sha")

def test_affected_finding_is_not_hidden_by_unavailable_unrelated_evidence():
    def mixed(payload):
        if payload["package"]["name"] == "unrelated": raise ScanUnavailable("service down")
        return query(payload)
    report=scan(Path("."), catalog(), mixed, detail, "commit-sha")
    assert report["scan_status"] == "unavailable"
    assert report["findings"][0]["status"] == "confirmed_affected"
