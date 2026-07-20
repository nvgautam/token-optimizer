import os
import sys
import json
import argparse
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def map_path(input_path: Path, source_root: Path, output_root: Path) -> Path:
    """
    Maps an input skill path under source_root to its output path under output_root.
    For Gemini skills, strips the 'skills' folder component.
    """
    rel_path = Path(input_path).resolve().relative_to(Path(source_root).resolve())
    parts = list(rel_path.parts)
    if parts[0] == "gemini" and len(parts) > 1 and parts[1] == "skills":
        parts.pop(1)
    return Path(output_root).resolve() / Path(*parts)

def encrypt_skills(key: bytes, source_dir: str | Path = "commands", output_dir: str | Path = "agentflow/skills/providers") -> None:
    """
    Encrypts all markdown files under source_dir/claude/ and source_dir/gemini/
    using AES-256-GCM with the provided 32-byte key.
    """
    if len(key) != 32:
        raise ValueError("Encryption key must be exactly 32 bytes (256-bit)")

    source_path = Path(source_dir).resolve()
    output_path = Path(output_dir).resolve()
    aesgcm = AESGCM(key)

    for provider in ["claude", "gemini"]:
        provider_src = source_path / provider
        if not provider_src.exists():
            continue

        for md_file in provider_src.rglob("*.md"):
            if not md_file.is_file():
                continue

            content = md_file.read_bytes()
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, content, None)

            mapped_dest = map_path(md_file, source_path, output_path)
            mapped_dest.parent.mkdir(parents=True, exist_ok=True)
            bundle = {"nonce": nonce.hex(), "ciphertext": ciphertext.hex()}
            mapped_dest.write_text(json.dumps(bundle), encoding="utf-8")

def derive_key(key_str: str) -> bytes:
    """
    Derives a 32-byte key from a string. If the string is a 64-char hex string,
    decodes it. Otherwise, hashes it using SHA-256.
    """
    if len(key_str) == 64:
        try:
            return bytes.fromhex(key_str)
        except ValueError:
            pass
    return hashlib.sha256(key_str.encode("utf-8")).digest()

def main() -> None:
    parser = argparse.ArgumentParser(description="Skill Encryption Pipeline")
    parser.add_argument("--key", help="Encryption key (hex or string passphrase)")
    parser.add_argument("--source-dir", default="commands", help="Source directory containing plaintext skills")
    parser.add_argument("--output-dir", default="agentflow/skills/providers", help="Output directory for encrypted skills")
    args = parser.parse_args()

    key_input = args.key or os.environ.get("AGENTFLOW_MASTER_KEY") or os.environ.get("SKILL_ENCRYPTION_KEY")
    if not key_input:
        print("Error: No encryption key provided. Please set AGENTFLOW_MASTER_KEY or provide --key.", file=sys.stderr)
        sys.exit(1)

    key_bytes = derive_key(key_input)
    try:
        encrypt_skills(key_bytes, source_dir=args.source_dir, output_dir=args.output_dir)
        print("Skill encryption pipeline completed successfully.")
    except Exception as e:
        print(f"Error during skill encryption: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
