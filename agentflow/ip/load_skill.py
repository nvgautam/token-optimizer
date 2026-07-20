"""Load a skill: plaintext fallback or decrypted bundle, gated by AGENTFLOW_ENCRYPT."""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _skill_name_to_path(skill_name: str) -> str:
    """Convert 'oracle' → 'oracle.md' and 'oracle:checklist' → 'oracle/checklist.md'."""
    parts = skill_name.split(":", 1)
    if len(parts) == 1:
        return f"{parts[0]}.md"
    return f"{parts[0]}/{parts[1]}.md"


def _is_encrypt_enabled() -> bool:
    return os.environ.get("AGENTFLOW_ENCRYPT", "false").lower() == "true"


def _read_plaintext(skill_name: str, skills_dir: str) -> bytes:
    """Read plaintext .md file for the given skill name."""
    rel_path = _skill_name_to_path(skill_name)
    full_path = Path(skills_dir) / rel_path
    if not full_path.is_file():
        sys.stderr.write(
            f"Error: skill file not found: {full_path}\n"
        )
        sys.exit(1)
    return full_path.read_bytes()


def _get_key_from_env() -> bytes | None:
    """Return key bytes if AGENTFLOW_KEY or AGENTFLOW_MASTER_KEY is set."""
    raw = os.environ.get("AGENTFLOW_KEY") or os.environ.get("AGENTFLOW_MASTER_KEY")
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _fetch_key_from_server(key_server_url: str, token: str) -> bytes:
    """Fetch decryption key from key server; exits 1 on network failure."""
    req = urllib.request.Request(
        f"{key_server_url}/key",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return bytes.fromhex(data["key"])
    except urllib.error.URLError as exc:
        sys.stderr.write(f"Error: key server unreachable at {key_server_url}: {exc}\n")
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"Error fetching key from server: {exc}\n")
        sys.exit(1)


def _get_key(key_server_url: str, token: str) -> bytes:
    """Resolve the decryption key: env var takes priority over key server."""
    direct = _get_key_from_env()
    if direct is not None:
        return direct
    if not key_server_url:
        sys.stderr.write(
            "Error: AGENTFLOW_KEY_SERVER_URL not set and no key in AGENTFLOW_KEY / "
            "AGENTFLOW_MASTER_KEY.\n"
        )
        sys.exit(1)
    return _fetch_key_from_server(key_server_url, token)


def _decrypt_from_bundle(skill_name: str, bundle_path: str, key: bytes) -> bytes:
    """Extract and decrypt the skill entry from the bundle ZIP.

    No decrypted content is written to disk.
    """
    entry_name = _skill_name_to_path(skill_name)

    if not Path(bundle_path).is_file():
        sys.stderr.write(
            f"Error: encrypted bundle not found: {bundle_path}\n"
            "Set AGENTFLOW_BUNDLE_PATH or run 'agentflow update-skills'.\n"
        )
        sys.exit(1)

    try:
        with zipfile.ZipFile(bundle_path, "r") as zf:
            if entry_name not in zf.namelist():
                sys.stderr.write(
                    f"Error: skill '{skill_name}' (entry '{entry_name}') not found in bundle.\n"
                )
                sys.exit(1)
            raw = zf.read(entry_name)
    except zipfile.BadZipFile as exc:
        sys.stderr.write(f"Error: bundle is corrupt or invalid: {exc}\n")
        sys.exit(1)

    nonce, ciphertext = raw[:12], raw[12:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as exc:
        sys.stderr.write(f"Error: decryption failed (wrong key?): {exc}\n")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point: load_skill <skill_name>"""
    import argparse

    parser = argparse.ArgumentParser(description="Load a skill by name.")
    parser.add_argument("skill_name", help="Skill name (e.g. 'oracle', 'oracle:checklist')")
    args = parser.parse_args()

    if _is_encrypt_enabled():
        bundle_path = os.environ.get(
            "AGENTFLOW_BUNDLE_PATH",
            os.path.expanduser("~/.agentflow/skills/bundle-v1.enc"),
        )
        key_server_url = os.environ.get("AGENTFLOW_KEY_SERVER_URL", "")
        token = os.environ.get("AGENTFLOW_KEY_SERVER_TOKEN", "")
        key = _get_key(key_server_url, token)
        content = _decrypt_from_bundle(args.skill_name, bundle_path, key)
        # Decode and write to stdout; never write to disk
        sys.stdout.write(content.decode("utf-8"))
    else:
        skills_dir = os.environ.get(
            "AGENTFLOW_SKILLS_DIR",
            os.path.join(os.getcwd(), "commands", "claude"),
        )
        content = _read_plaintext(args.skill_name, skills_dir)
        sys.stdout.write(content.decode("utf-8"))


if __name__ == "__main__":
    main()
