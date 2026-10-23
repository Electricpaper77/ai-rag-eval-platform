"""Encrypted disposable PostgreSQL backup artifact with secret-safe manifest."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile
from pathlib import Path
from cryptography.fernet import Fernet

def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def create_backup(source: str, output: Path, key: bytes, key_id: str = "v1") -> dict[str, object]:
    fernet = Fernet(key); output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        plain = Path(temp) / "backup.dump"
        subprocess.run(["pg_dump", "--format=custom", "--file", str(plain), source], check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ciphertext = fernet.encrypt(plain.read_bytes()); output.write_bytes(ciphertext)
    manifest = {"format": "agenttrust-encrypted-backup-v1", "key_id": key_id, "ciphertext_sha256": digest(ciphertext), "encrypted": True}
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
def decrypt_for_restore(artifact: Path, manifest_path: Path, key: bytes, destination: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); ciphertext = artifact.read_bytes()
    if manifest.get("format") != "agenttrust-encrypted-backup-v1" or manifest.get("ciphertext_sha256") != digest(ciphertext): raise RuntimeError("backup integrity verification failed")
    destination.write_bytes(Fernet(key).decrypt(ciphertext))
def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--backup", type=Path, required=True); parser.add_argument("--source", default=os.getenv("AGENTTRUST_POSTGRES_URL", "")); parser.add_argument("--key", default=os.getenv("AGENTTRUST_BACKUP_ENCRYPTION_KEY", "")); args = parser.parse_args()
    if not args.source or not args.key: raise SystemExit("source and encryption key are required")
    create_backup(args.source, args.backup, args.key.encode())
if __name__ == "__main__": main()
