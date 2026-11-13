#!/usr/bin/env python3
"""Bounded, fail-closed CISA KEV dependency gate."""
from __future__ import annotations
import argparse, json, re, subprocess, sys, time, urllib.error, urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

CISA_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
OSV_URL = "https://api.osv.dev/v1/vulns/{identifier}"
TIMEOUT_SECONDS = 15
MAX_CATALOG_ENTRIES = 2000

class ScanUnavailable(RuntimeError):
    """Mandatory evidence could not be retrieved or validated."""

@dataclass(frozen=True)
class Package:
    name: str
    version: str
    source: str
    direct: bool

def _get_json(url: str, timeout: int = TIMEOUT_SECONDS) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "AgentTrust-IQ-KEV-Gate/1.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200: raise ScanUnavailable(f"HTTP {response.status} from {url}")
            value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict): raise ScanUnavailable(f"invalid JSON object from {url}")
            return value
    except ScanUnavailable: raise
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ScanUnavailable(f"unable to retrieve {url}: {exc}") from exc

def fetch_catalog(url: str = CISA_URL) -> dict:
    catalog = _get_json(url)
    if not isinstance(catalog.get("vulnerabilities"), list): raise ScanUnavailable("CISA catalog is missing vulnerabilities")
    if len(catalog["vulnerabilities"]) > MAX_CATALOG_ENTRIES: raise ScanUnavailable("CISA catalog exceeds bounded entry limit")
    return catalog

def _normalise(value: str) -> str: return value.lower().replace("_", "-")

def inventory_packages(root: Path) -> list[Package]:
    direct: set[str] = set()
    for filename in ("requirements.txt", "requirements-lite.txt"):
        path = root / filename
        if not path.exists(): continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*([A-Za-z0-9_.-]+)", line.split("#", 1)[0])
            if match: direct.add(_normalise(match.group(1)))
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "list", "--format=json"], cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS, check=True)
        installed = json.loads(result.stdout)
        if not isinstance(installed, list): raise ValueError("pip list did not return a list")
        return [Package(item["name"], item["version"], "pip list", _normalise(item["name"]) in direct) for item in installed]
    except (subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
        raise ScanUnavailable(f"unable to inventory installed packages: {exc}") from exc

def _version_tuple(version: str) -> tuple[int, ...] | None:
    match = re.match(r"^(\d+(?:\.\d+)*)", version)
    return tuple(int(part) for part in match.group(1).split(".")) if match else None

def version_in_range(version: str, events: list[dict]) -> bool | None:
    actual = _version_tuple(version)
    if actual is None: return None
    introduced = None
    evaluated = False
    for event in events:
        if event.get("introduced") is not None:
            introduced = _version_tuple(event["introduced"])
        if event.get("fixed") is not None:
            fixed = _version_tuple(event["fixed"])
            if introduced is None or fixed is None:
                return None
            evaluated = True
            if introduced <= actual < fixed:
                return True
            introduced = None
    if not evaluated or introduced is not None:
        return None
    return False

def _aliases(advisory: dict) -> set[str]: return {a for a in advisory.get("aliases", []) if isinstance(a, str)}

def advisory_match(package: Package, advisory: dict, expected_cve: str | None = None) -> bool | None:
    if expected_cve and expected_cve not in _aliases(advisory): return None
    for affected in advisory.get("affected", []):
        identity = affected.get("package", {})
        if identity.get("ecosystem") != "PyPI" or _normalise(identity.get("name", "")) != _normalise(package.name): continue
        for version_range in affected.get("ranges", []):
            if version_range.get("type") == "ECOSYSTEM": return version_in_range(package.version, version_range.get("events", []))
    return None

def _package_is_in_advisory(package: Package, advisory: dict) -> bool:
    return any(item.get("package", {}).get("ecosystem") == "PyPI" and _normalise(item.get("package", {}).get("name", "")) == _normalise(package.name) for item in advisory.get("affected", []))

def scan(root: Path, catalog: dict, advisory_loader: Callable[[str], dict] = _get_json, commit_sha: str = "unknown") -> dict:
    started = time.perf_counter(); packages = inventory_packages(root); vulnerabilities = catalog.get("vulnerabilities")
    if not isinstance(vulnerabilities, list): raise ScanUnavailable("catalog vulnerabilities are unavailable")
    findings, errors, seen = [], [], {}
    for entry in vulnerabilities:
        cve = entry.get("cveID")
        if not cve: errors.append({"type": "catalog_entry_invalid", "entry": entry}); continue
        try: advisory = seen.setdefault(cve, advisory_loader(OSV_URL.format(identifier=cve)))
        except ScanUnavailable as exc: errors.append({"type": "advisory_unavailable", "cve": cve, "error": str(exc)}); continue
        if cve not in _aliases(advisory): errors.append({"type": "advisory_mismatch", "cve": cve}); continue
        for package in packages:
            if not _package_is_in_advisory(package, advisory): continue
            matched = advisory_match(package, advisory, expected_cve=cve)
            status = "confirmed_affected" if matched is True else "confirmed_unaffected" if matched is False else "unknown"
            findings.append({"cve": cve, "package": package.name, "version": package.version, "direct": package.direct, "status": status,
                "catalog_evidence": {"vendor": entry.get("vendorProject"), "product": entry.get("product"), "date_added": entry.get("dateAdded")},
                "advisory_evidence": {"aliases": sorted(_aliases(advisory)), "source": OSV_URL.format(identifier=cve)},
                "remediation": "Consult the authoritative advisory."})
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    status = "unavailable" if errors else "affected" if any(f["status"] == "confirmed_affected" for f in findings) else "unknown" if any(f["status"] == "unknown" for f in findings) else "pass"
    return {"schema_version": 2, "scanned_commit_sha": commit_sha, "scan_status": status, "catalog_source": CISA_URL,
            "catalog_timestamp": catalog.get("catalogVersion"), "elapsed_ms": elapsed_ms, "packages": [asdict(p) for p in packages], "findings": findings, "errors": errors}

def _exit_code(report: dict) -> int: return 1 if report["scan_status"] == "affected" else 2 if report["scan_status"] in {"unavailable", "unknown"} else 0

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", type=Path, default=Path.cwd()); parser.add_argument("--output", type=Path, default=Path("artifacts/kev/kev_report.json")); parser.add_argument("--commit-sha", default="unknown"); args = parser.parse_args()
    try: report = scan(args.root, fetch_catalog(), commit_sha=args.commit_sha)
    except ScanUnavailable as exc: report = {"schema_version": 2, "scanned_commit_sha": args.commit_sha, "scan_status": "unavailable", "catalog_source": CISA_URL, "catalog_timestamp": None, "elapsed_ms": None, "packages": [], "findings": [], "errors": [{"type": "mandatory_scan_failure", "error": str(exc)}]}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8"); print(json.dumps(report, indent=2)); return _exit_code(report)

if __name__ == "__main__": raise SystemExit(main())

