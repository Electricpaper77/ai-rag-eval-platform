#!/usr/bin/env python3
"""Fail-closed CISA KEV gate using bounded OSV package queries."""
from __future__ import annotations
import argparse, json, re, subprocess, sys, tempfile, time, urllib.error, urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from packaging.version import InvalidVersion, Version

CISA_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"
OSV_DETAIL_URL = "https://api.osv.dev/v1/vulns/{identifier}"
TIMEOUT_SECONDS = 15
MAX_CATALOG_ENTRIES = 2000
MAX_PACKAGE_QUERIES = 500
MAX_RELEVANT_ADVISORIES = 500
SCANNER_TEST_PACKAGES = {"pytest", "packaging", "iniconfig", "pluggy"}

class ScanUnavailable(RuntimeError): pass

@dataclass(frozen=True)
class Package:
    name: str
    version: str
    source: str
    direct: bool
    scope: str = "application_runtime"

def _request_json(url: str, method: str = "GET", payload: dict | None = None, timeout: int = TIMEOUT_SECONDS) -> tuple[int, dict | None]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "AgentTrust-IQ-KEV-Gate/1.2", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict): raise ScanUnavailable(f"malformed JSON object from {url}")
            return response.status, value
    except urllib.error.HTTPError as exc:
        if exc.code == 404: return 404, None
        raise ScanUnavailable(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ScanUnavailable(f"unable to retrieve {url}: {exc}") from exc

def fetch_catalog(url: str = CISA_URL) -> dict:
    status, catalog = _request_json(url)
    if status != 200 or catalog is None or not isinstance(catalog.get("vulnerabilities"), list): raise ScanUnavailable("CISA catalog is missing or malformed")
    if len(catalog["vulnerabilities"]) > MAX_CATALOG_ENTRIES: raise ScanUnavailable("CISA catalog exceeds bounded entry limit")
    return catalog

def _normalise(value: str) -> str: return value.lower().replace("_", "-")

def inventory_packages(root: Path) -> list[Package]:
    runtime_file = root / "requirements.txt"
    if not runtime_file.exists(): raise ScanUnavailable("application runtime requirements.txt is missing")
    direct = set()
    for line in runtime_file.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)", line.split("#", 1)[0])
        if match: direct.add(_normalise(match.group(1)))
    try:
        with tempfile.TemporaryDirectory(prefix="agenttrust-kev-") as temp_dir:
            report_path = Path(temp_dir) / "pip-report.json"
            result = subprocess.run([sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--disable-pip-version-check", "--report", str(report_path), "-r", str(runtime_file)], cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS * 4, check=True)
            del result
            resolved = json.loads(report_path.read_text(encoding="utf-8"))
        installed = resolved.get("install")
        if not isinstance(installed, list) or not installed: raise ValueError("pip resolver report has no install entries")
        packages = []
        for item in installed:
            metadata = item.get("metadata", {})
            name, version = metadata.get("name"), metadata.get("version")
            if not isinstance(name, str) or not isinstance(version, str): raise ValueError("pip resolver report has incomplete package metadata")
            scope = "scanner_or_test" if _normalise(name) in SCANNER_TEST_PACKAGES else "application_runtime"
            packages.append(Package(name, version, "pip resolver: requirements.txt", _normalise(name) in direct, scope))
        return packages
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError, OSError) as exc: raise ScanUnavailable(f"unable to inventory installed packages: {exc}") from exc

def _version(value: str) -> Version | None:
    try: return Version(value)
    except (InvalidVersion, TypeError): return None

def version_in_range(version: str, events: list[dict]) -> bool | None:
    actual = _version(version)
    if actual is None: return None
    lower: Version | None = None; evaluated = False
    for event in events:
        if event.get("introduced") is not None:
            lower = _version(event["introduced"])
        if event.get("fixed") is not None:
            upper = _version(event["fixed"])
            if lower is None or upper is None: return None
            evaluated = True
            if lower <= actual < upper: return True
            lower = None
    return False if evaluated and lower is None else None

def _aliases(advisory: dict) -> set[str]: return {a for a in advisory.get("aliases", []) if isinstance(a, str)}

def advisory_match(package: Package, advisory: dict, expected_cve: str) -> bool | None:
    if expected_cve not in _aliases(advisory): return None
    matches = []
    for affected in advisory.get("affected", []):
        identity = affected.get("package", {})
        if identity.get("ecosystem") == "PyPI" and _normalise(identity.get("name", "")) == _normalise(package.name):
            for version_range in affected.get("ranges", []):
                if version_range.get("type") == "ECOSYSTEM": matches.append(version_in_range(package.version, version_range.get("events", [])))
    if not matches: return None
    if any(item is True for item in matches): return True
    if all(item is False for item in matches): return False
    return None

def _query_package(package: Package, query_loader: Callable[[dict], tuple[int, dict | None]]) -> list[dict]:
    payload = {"package": {"ecosystem": "PyPI", "name": package.name}}
    if _version(package.version) is not None: payload["version"] = package.version
    status, response = query_loader(payload)
    if status == 404: return []
    if status != 200 or response is None: raise ScanUnavailable(f"malformed OSV query response for {package.name}")
    if response == {}: return []
    if "vulns" not in response or not isinstance(response["vulns"], list): raise ScanUnavailable(f"malformed OSV query response for {package.name}")
    return response["vulns"]

def scan(root: Path, catalog: dict, query_loader: Callable[[dict], tuple[int, dict | None]] | None = None,
         advisory_loader: Callable[[str], tuple[int, dict | None]] | None = None, commit_sha: str = "unknown") -> dict:
    started = time.perf_counter(); packages = inventory_packages(root); entries = catalog.get("vulnerabilities")
    if not isinstance(entries, list): raise ScanUnavailable("catalog vulnerabilities are unavailable")
    query_loader = query_loader or (lambda payload: _request_json(OSV_QUERY_URL, "POST", payload))
    advisory_loader = advisory_loader or (lambda identifier: _request_json(OSV_DETAIL_URL.format(identifier=identifier)))
    cves = {entry.get("cveID") for entry in entries if entry.get("cveID")}; findings=[]; errors=[]; relevant=set(); details={}
    if len(packages) > MAX_PACKAGE_QUERIES: raise ScanUnavailable("package inventory exceeds bounded OSV query limit")
    for package in packages:
        try: summaries = _query_package(package, query_loader)
        except ScanUnavailable as exc: errors.append({"type": "osv_query_unavailable", "package": package.name, "error": str(exc)}); continue
        for summary in summaries:
            aliases = set(summary.get("aliases", [])) if isinstance(summary, dict) else set()
            for cve in sorted(aliases & cves): relevant.add((package.name, package.version, cve, package.direct, summary.get("id")))
    if len(relevant) > MAX_RELEVANT_ADVISORIES: raise ScanUnavailable("relevant advisory detail set exceeds bounded limit")
    for name, version, cve, direct, advisory_id in sorted(relevant):
        try:
            status, advisory = details.setdefault(advisory_id, advisory_loader(advisory_id))
            if status != 200 or advisory is None or not isinstance(advisory, dict): raise ScanUnavailable(f"missing advisory detail {advisory_id}")
            if cve not in _aliases(advisory): raise ScanUnavailable(f"advisory {advisory_id} does not match {cve}")
            package = next((item for item in packages if item.name == name and item.version == version), Package(name, version, "pip resolver: requirements.txt", direct)); matched = advisory_match(package, advisory, cve)
            state = "confirmed_affected" if matched is True else "confirmed_unaffected" if matched is False else "unknown"
            findings.append({"cve": cve, "package": name, "version": version, "direct": direct, "status": state,
                "catalog_evidence": next(({"vendor": e.get("vendorProject"), "product": e.get("product"), "date_added": e.get("dateAdded")} for e in entries if e.get("cveID") == cve), {}),
                "advisory_evidence": {"id": advisory_id, "aliases": sorted(_aliases(advisory)), "source": OSV_DETAIL_URL.format(identifier=advisory_id)}, "remediation": "Consult the authoritative advisory."})
        except ScanUnavailable as exc: errors.append({"type": "relevant_advisory_unavailable", "cve": cve, "package": name, "error": str(exc)})
    status = "unavailable" if errors else "affected" if any(f["status"] == "confirmed_affected" for f in findings) else "unknown" if any(f["status"] == "unknown" for f in findings) else "pass"
    package_rows = [asdict(p) for p in packages]
    return {"schema_version": 3, "scanned_commit_sha": commit_sha, "scan_status": status, "catalog_source": CISA_URL, "catalog_timestamp": catalog.get("catalogVersion"), "elapsed_ms": round((time.perf_counter()-started)*1000, 3), "dependency_inventory_source": "requirements.txt resolved with pip --dry-run --report", "dependency_inventory_scope": "application_runtime", "application_package_count": sum(p.scope == "application_runtime" for p in packages), "scanner_test_package_count": sum(p.scope == "scanner_or_test" for p in packages), "scanner_test_dependencies": [row for row in package_rows if row["scope"] == "scanner_or_test"], "packages": package_rows, "findings": findings, "errors": errors, "unsupported_ecosystems": ["non-PyPI packages are not inventoried"], "inventory_limitations": ["Root requirements.txt is the Docker runtime source; packages explicitly declared there are treated as runtime inputs", "Uninstalled optional/GPU ecosystems are not covered"]}

def _exit_code(report: dict) -> int: return 1 if report["scan_status"] == "affected" else 2 if report["scan_status"] in {"unavailable", "unknown"} else 0

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path.cwd()); parser.add_argument("--output", type=Path, default=Path("artifacts/kev/kev_report.json")); parser.add_argument("--commit-sha", default="unknown"); args=parser.parse_args()
    try: report=scan(args.root, fetch_catalog(), commit_sha=args.commit_sha)
    except ScanUnavailable as exc: report={"schema_version":3,"scanned_commit_sha":args.commit_sha,"scan_status":"unavailable","catalog_source":CISA_URL,"catalog_timestamp":None,"elapsed_ms":None,"dependency_inventory_source":"requirements.txt resolved with pip --dry-run --report","dependency_inventory_scope":"application_runtime","application_package_count":0,"scanner_test_package_count":0,"scanner_test_dependencies":[],"packages":[],"findings":[],"errors":[{"type":"mandatory_scan_failure","error":str(exc)}],"unsupported_ecosystems":["non-PyPI packages are not inventoried"],"inventory_limitations":["Root requirements.txt is the Docker runtime source; packages explicitly declared there are treated as runtime inputs","Uninstalled optional/GPU ecosystems are not covered"]}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8"); print(json.dumps(report, indent=2)); return _exit_code(report)

if __name__ == "__main__": raise SystemExit(main())
