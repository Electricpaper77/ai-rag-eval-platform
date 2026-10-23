import hashlib
from pathlib import Path
import pytest

from saas import postgres_repository as repository

def test_migration_manifest_is_versioned_and_checksumable():
    versions = [int(path.stem.split("_")[0]) for path in repository.MIGRATIONS]
    assert versions == sorted(set(versions))
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() for path in repository.MIGRATIONS)

def test_backup_restore_requires_source_url(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTTRUST_POSTGRES_URL", raising=False)
    with pytest.raises(SystemExit, match="AGENTTRUST_POSTGRES_URL"):
        from scripts.postgres_backup_restore import main
        monkeypatch.setattr("sys.argv", ["backup", "--backup", str(tmp_path / "a.dump"), "--restore-url", "postgresql://restore"])
        main()
