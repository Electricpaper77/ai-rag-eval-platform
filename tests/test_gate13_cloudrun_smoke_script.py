from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/smoke_gate13_cloudrun.ps1")


def _script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_cloudrun_smoke_requires_iam_identity_token_and_app_api_key() -> None:
    text = _script_text()

    assert "[string]$IdentityToken = $env:CLOUD_RUN_IDENTITY_TOKEN" in text
    assert '"Authorization" = "Bearer $IdentityToken"' in text
    assert '"X-AgentTrust-API-Key" = $ApiKey' in text
    assert "Do not print the token" in text


def test_cloudrun_smoke_distinguishes_iam_403_from_app_401() -> None:
    text = _script_text()

    assert "Expected unauthenticated Cloud Run /health HTTP 403" in text
    assert "unauthenticated_cloud_run_options_preflight" in text
    assert "Expected 403" in text
    assert "iam_authorized_missing_api_key_metrics" in text
    assert "iam_authorized_invalid_api_key_metrics" in text
    assert "Expected 401" in text


def test_cloudrun_smoke_validates_authorized_success_paths() -> None:
    text = _script_text()

    assert "iam_authorized_valid_api_key_metrics" in text
    assert 'Invoke-RestMethod `' in text
    assert "-Headers $validHeaders" in text
    assert "evaluation_run_id=" in text


def test_cloudrun_smoke_does_not_print_credentials() -> None:
    text = _script_text()

    forbidden = [
        "Write-Host $IdentityToken",
        "Write-Host $ApiKey",
        "Write-Output $IdentityToken",
        "Write-Output $ApiKey",
    ]
    assert not any(pattern in text for pattern in forbidden)
