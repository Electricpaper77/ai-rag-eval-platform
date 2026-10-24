"""Encrypted disposable PostgreSQL backup artifact with secret-safe manifest."""
from __future__ import annotations
import argparse, hashlib, json, os, secrets, struct, subprocess, tempfile
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
CHUNK = 1024 * 1024
def _aes(key: bytes) -> AESGCM: return AESGCM(hashlib.sha256(key).digest())
def create_backup(source: str, output: Path, key: bytes, key_id: str = "v1") -> dict[str, object]:
    if not key or not key_id or output.exists() and output.is_dir(): raise RuntimeError("invalid backup parameters")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        plain = Path(temp) / "backup.dump"
        subprocess.run(["pg_dump", "--format=custom", "--file", str(plain), source], check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        tmp = output.with_suffix(output.suffix + ".tmp")
        with tmp.open("wb") as dst, plain.open("rb") as src:
            dst.write(b"ATB1")
            for index in range(0, plain.stat().st_size, CHUNK):
                block = src.read(CHUNK); nonce = secrets.token_bytes(12); encrypted = _aes(key).encrypt(nonce, block, str(index).encode())
                dst.write(struct.pack("!I", len(encrypted))); dst.write(nonce); dst.write(encrypted)
        os.chmod(tmp, 0o600); os.replace(tmp, output)
    manifest = {"format": "agenttrust-encrypted-backup-v1", "key_id": key_id, "ciphertext_sha256": digest(output.read_bytes()), "encrypted": True, "chunk_bytes": CHUNK}
    output.with_suffix(output.suffix + ".json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
def decrypt_for_restore(artifact: Path, manifest_path: Path, key: bytes, destination: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); ciphertext = artifact.read_bytes()
    if manifest.get("format") != "agenttrust-encrypted-backup-v1" or manifest.get("ciphertext_sha256") != digest(ciphertext): raise RuntimeError("backup integrity verification failed")
    if not ciphertext.startswith(b"ATB1"): raise RuntimeError("unsupported backup format")
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with tmp.open("wb") as out:
            offset = 4; index = 0
            while offset < len(ciphertext):
                if offset + 4 > len(ciphertext): raise RuntimeError("truncated backup")
                size = struct.unpack("!I", ciphertext[offset:offset+4])[0]; offset += 4
                if offset + 12 + size > len(ciphertext): raise RuntimeError("truncated backup")
                nonce = ciphertext[offset:offset+12]; offset += 12; block = ciphertext[offset:offset+size]; offset += size
                out.write(_aes(key).decrypt(nonce, block, str(index).encode())); index += CHUNK
        os.chmod(tmp, 0o600); os.replace(tmp, destination)
    except Exception:
        tmp.unlink(missing_ok=True); destination.unlink(missing_ok=True); raise
def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--backup", type=Path, required=True); parser.add_argument("--source", default=os.getenv("AGENTTRUST_POSTGRES_URL", "")); parser.add_argument("--key", default=os.getenv("AGENTTRUST_BACKUP_ENCRYPTION_KEY", "")); args = parser.parse_args()
    if not args.source or not args.key: raise SystemExit("source and encryption key are required")
    create_backup(args.source, args.backup, args.key.encode())
if __name__ == "__main__": main()
