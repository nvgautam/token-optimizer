"""Build an encrypted skill bundle (ZIP archive) from commands/claude/**/*.md."""
from __future__ import annotations

import os
import sys
import argparse
import hashlib
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def build_bundle(
    key: bytes,
    source_dir: str = "commands/claude",
    output_path: str = "~/.agentflow/skills/bundle-v1.enc",
) -> None:
    """Encrypt all .md files under source_dir into a ZIP bundle at output_path.

    Each ZIP entry name is the relative path of the .md file within source_dir
    (e.g. ``oracle.md``, ``oracle/checklist.md``).  Entry content is raw bytes:
    ``12-byte nonce || AES-256-GCM ciphertext``.

    The function is idempotent: calling it twice replaces the existing bundle.
    """
    if len(key) != 32:
        raise ValueError("Encryption key must be exactly 32 bytes (256-bit)")

    aesgcm = AESGCM(key)
    src = Path(source_dir).resolve()
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as zf:
        for md_file in sorted(src.rglob("*.md")):
            if not md_file.is_file():
                continue
            rel = md_file.relative_to(src)
            # Normalise to forward slashes (ZIP spec)
            entry_name = rel.as_posix()
            plaintext = md_file.read_bytes()
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            zf.writestr(entry_name, nonce + ciphertext)


def derive_key(key_str: str) -> bytes:
    """Derive a 32-byte key from a hex string or passphrase."""
    if len(key_str) == 64:
        try:
            return bytes.fromhex(key_str)
        except ValueError:
            pass
    return hashlib.sha256(key_str.encode("utf-8")).digest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an encrypted skill bundle.")
    parser.add_argument("--key", help="32-byte key as 64-char hex or passphrase")
    parser.add_argument(
        "--source-dir",
        default=os.getenv("AGENTFLOW_SKILLS_SRC", "commands/claude"),
        help="Directory containing .md skill files (default: commands/claude)",
    )
    parser.add_argument(
        "--output",
        default=os.path.expanduser(
            os.getenv("AGENTFLOW_BUNDLE_PATH", "~/.agentflow/skills/bundle-v1.enc")
        ),
        help="Output bundle path",
    )
    args = parser.parse_args()

    key_input = (
        args.key
        or os.environ.get("AGENTFLOW_KEY")
        or os.environ.get("AGENTFLOW_MASTER_KEY")
    )
    if not key_input:
        sys.stderr.write(
            "Error: no encryption key provided via --key, AGENTFLOW_KEY, "
            "or AGENTFLOW_MASTER_KEY.\n"
        )
        sys.exit(1)

    key_bytes = derive_key(key_input)
    try:
        build_bundle(key=key_bytes, source_dir=args.source_dir, output_path=args.output)
        print(f"Bundle written to {args.output}")
    except Exception as exc:
        sys.stderr.write(f"Error building bundle: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
