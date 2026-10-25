# Gate 23F — Product hardening and recruiter demo evidence

Gate 23F hardens the existing Gate 23E authenticated workspace without changing
the FastAPI authorization boundary. The browser still uses same-origin session
cookies, CSRF/origin headers, tenant-scoped PostgreSQL routes and restore
quarantine.

## Baseline defects and acceptance criteria

The Gate 23E baseline had four material usability gaps: API parse/network errors
were not actionable, the generic retry button could reload the wrong view,
repeated evaluation submissions generated a new idempotency key, and navigation
state could race an organization/project switch. Gate 23F requires actionable
401/403/503/malformed/network states, same-key retry behavior, no stale
cross-scope rendering, keyboard-reachable controls, no document overflow at
320/390/768/1440px, and no serious/critical automated accessibility findings.

## Reproducible local demo

Use a fresh clone, Python 3.11, Node 20, Docker, disposable PostgreSQL and the
controlled test identity fixtures already used by `tests/test_gate23d_browser.py`.
The CI-equivalent commands are:

```text
python -m pip install -r requirements-test.txt playwright
python -m playwright install --with-deps chromium
npm install --no-save --ignore-scripts axe-core@4.10.2
python -c "from saas.postgres_repository import migrate; migrate()"
python -m pytest -q tests/test_gate23f_contract.py
python -m pytest -q tests/test_gate23f_browser.py -m postgres_integration --maxfail=1
```

The browser path is synthetic only: organization → project → evaluation →
persisted result → policy decision → investigation → reviewer annotation →
release review → sanitized export. The case-evidence row used by the fixture is
inserted directly by the test and is explicitly labeled `synthetic_test`; it is
not presented as organically generated provider evidence.

## Evidence boundaries

The Gate 23F artifact contains the exact feature SHA, environment metadata,
accessibility report, four viewport screenshots and sanitized test output. The
accessibility test is an axe-core WCAG 2A/2AA scan plus viewport, target-size,
keyboard and accessible-name assertions. CI fails on serious/critical findings,
missing screenshots, missing manifests or skipped browser dependencies.

This is local disposable PostgreSQL/Chromium evidence. It does not establish
managed OIDC, customer hosting, cloud retention, billing, production RPO/RTO,
GPU/DCGM measurements or production security certification. Evaluation metrics
remain labeled synthetic, provider-reported, independently computed or
`MISSING_EVIDENCE` according to persisted provenance; the UI does not invent
quality or performance values.
