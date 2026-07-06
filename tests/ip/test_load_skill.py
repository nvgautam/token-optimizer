import os
import sys
import json
import subprocess
import tempfile
import shutil
import pytest

# Module under test
import agentflow.ip.load_skill as load_skill

META_INSTRUCTION = load_skill.META_INSTRUCTION

def _encrypt_skill(key: bytes, plaintext: bytes) -> dict:
    """Encrypt plaintext into the .enc bundle format used by load_skill."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex()}

@pytest.fixture
def temp_skill_dir():
    """Create a temporary SKILLS_DIR and clean up after the test."""
    dirpath = tempfile.mkdtemp()
    yield dirpath
    shutil.rmtree(dirpath)

def test_load_skill_success(monkeypatch, temp_skill_dir, capsys):
    """When a valid token and encrypted bundle exist, the script prints the meta instruction and the plaintext payload."""
    key = b"0" * 32  # deterministic 256‑bit key
    plaintext = json.dumps({"hello": "world"}).encode("utf-8")
    bundle = _encrypt_skill(key, plaintext)

    # Write encrypted bundle to a dummy skill directory
    skill_name = "dummy_skill"
    skill_path = os.path.join(temp_skill_dir, skill_name)
    os.makedirs(skill_path, exist_ok=True)
    enc_path = os.path.join(skill_path, "skill.enc")
    with open(enc_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f)

    # Prepare environment – monkeypatch fetch_key to return our key
    monkeypatch.setenv("SKILLS_DIR", temp_skill_dir)
    monkeypatch.setenv("KEY_SERVER_URL", "http://example.com")
    monkeypatch.setenv("KEY_SERVER_TOKEN", "dummy-token")
    monkeypatch.setattr(load_skill, "fetch_key", lambda url, token: key)

    # Call load_skill directly, capturing stdout via capsys
    import sys as _sys
    original_argv = _sys.argv
    _sys.argv = ["prog", skill_name]
    try:
        load_skill.load_skill()
    finally:
        _sys.argv = original_argv
    captured = capsys.readouterr()
    assert captured.err == ""
    output_bytes = captured.out.encode()
    # First line must be the meta instruction
    assert output_bytes.startswith(META_INSTRUCTION.encode() + b"\n")
    # Remaining bytes must match the original plaintext
    assert output_bytes[len(META_INSTRUCTION) + 1 :] == plaintext

def test_load_skill_missing_token(monkeypatch, temp_skill_dir):
    """If no token is supplied (env var missing), the script exits with an error message."""
    # Ensure token env var is absent
    monkeypatch.delenv("KEY_SERVER_TOKEN", raising=False)
    monkeypatch.setenv("SKILLS_DIR", temp_skill_dir)
    # Create a dummy skill folder so the file‑check passes
    os.makedirs(os.path.join(temp_skill_dir, "dummy_skill"), exist_ok=True)

    result = subprocess.run(
        [sys.executable, "-c", "import agentflow.ip.load_skill as m; m.load_skill()", "dummy_skill"],
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode != 0
    assert "Error: token not provided" in result.stderr
