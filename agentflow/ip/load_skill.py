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
    """Return key bytes if AGENTFLOW_MASTER_KEY is set (dev override only).

    NOTE: AGENTFLOW_KEY is the license/API key sent to /validate — it is NOT
    a direct key override. Only AGENTFLOW_MASTER_KEY bypasses the key server.
    """
    raw = os.environ.get("AGENTFLOW_MASTER_KEY")
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


def _fetch_key_from_server(key_server_url: str, api_key: str) -> bytes:
    """POST api_key to /validate; returns CEK bytes on 200, exits 1 on 401 or error."""
    req = urllib.request.Request(
        f"{key_server_url}/validate",
        data=json.dumps({"api_key": api_key}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return bytes.fromhex(data["key"])
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            body = exc.read()
            try:
                err = json.loads(body).get("error", "")
            except Exception:
                err = ""
            if err in ("license_revoked", "invalid_key"):
                sys.stderr.write("License invalid\n")
            else:
                sys.stderr.write("License invalid\n")
            sys.exit(1)
        sys.stderr.write(f"Error: key server returned {exc.code}: {exc}\n")
        sys.exit(1)
    except urllib.error.URLError as exc:
        sys.stderr.write(f"Error: key server unreachable at {key_server_url}: {exc}\n")
        sys.exit(1)
    except Exception as exc:
        sys.stderr.write(f"Error fetching key from server: {exc}\n")
        sys.exit(1)


def _get_key(key_server_url: str, api_key: str) -> bytes:
    """Resolve the decryption key: AGENTFLOW_MASTER_KEY takes priority over key server."""
    direct = _get_key_from_env()
    if direct is not None:
        return direct
    if not key_server_url or not api_key:
        sys.stderr.write(
            "Error: AGENTFLOW_KEY_SERVER_URL and AGENTFLOW_KEY must be set "
            "when AGENTFLOW_ENCRYPT=true.\n"
        )
        sys.exit(1)
    return _fetch_key_from_server(key_server_url, api_key)


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
        api_key = os.environ.get("AGENTFLOW_KEY", "")
        key = _get_key(key_server_url, api_key)
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
