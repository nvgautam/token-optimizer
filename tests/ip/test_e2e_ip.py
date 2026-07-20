"""
End-to-end IP spike integration test.

Flow: encrypt skill with master key (JSON format)
   → start key server with same master key
   → load_skill.fetch_key retrieves master key
   → load_skill.decrypt_skill decrypts .enc bundle in memory
   → plaintext matches original + meta-instruction prepended
"""
import os
import json
import pytest
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import agentflow.ip.load_skill as load_skill
from agentflow.ip.key_server import run_server_in_thread


def _encrypt_to_json(key: bytes, plaintext: bytes) -> dict:
    """Encrypt plaintext and return JSON-serialisable bundle (as encrypt_pipeline now writes)."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex()}


def test_e2e_ip_spike(tmp_path):
    """Encrypt skill → start key server with master key → load_skill decrypts → plaintext matches."""
    master_key = os.urandom(32)
    token = "e2e-test-token-secret"
    skill_content = b"# Oracle Skill\nThis is the oracle skill plaintext content."

    # 1. Create skill.enc in JSON format (as encrypt_pipeline now produces)
    bundle = _encrypt_to_json(master_key, skill_content)
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "oracle"
    skill_dir.mkdir(parents=True)
    enc_path = skill_dir / "skill.enc"
    enc_path.write_text(json.dumps(bundle), encoding="utf-8")

    # 2. Start key server with the same master key
    server, thread, port = run_server_in_thread(
        host="127.0.0.1",
        port=0,
        token=token,
        skills_dir=str(skills_dir),
        master_key=master_key,
    )
    try:
        key_server_url = f"http://127.0.0.1:{port}"

        # 3. load_skill fetches key from key server — must equal master key
        fetched_key = load_skill.fetch_key(key_server_url, token)
        assert fetched_key == master_key, "Fetched key must match the master key"

        # 4. Decrypt skill in memory — no disk write of plaintext
        plaintext = load_skill.decrypt_skill(str(enc_path), fetched_key)
        assert plaintext == skill_content, "Decrypted content must match original plaintext"

        # 5. Verify meta-instruction preamble (as load_skill prepends to stdout)
        output = load_skill.META_INSTRUCTION.encode("utf-8") + b"\n" + plaintext
        assert output.startswith(load_skill.META_INSTRUCTION.encode("utf-8"))
        assert output.endswith(skill_content)

    finally:
        server.shutdown()
        thread.join()


def test_e2e_wrong_key_fails_decryption(tmp_path):
    """Decryption with a different key must raise an exception (auth integrity)."""
    master_key = os.urandom(32)
    wrong_key = os.urandom(32)
    skill_content = b"# Secret skill"

    bundle = _encrypt_to_json(master_key, skill_content)
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "test_skill"
    skill_dir.mkdir(parents=True)
    enc_path = skill_dir / "skill.enc"
    enc_path.write_text(json.dumps(bundle), encoding="utf-8")

    with pytest.raises(Exception):
        load_skill.decrypt_skill(str(enc_path), wrong_key)


def test_e2e_idempotent_encrypt_decrypt(tmp_path):
    """Encrypting same skill twice with same key → both decrypt to same plaintext (different nonces OK)."""
    master_key = os.urandom(32)
    skill_content = b"# Idempotent skill content"

    bundle1 = _encrypt_to_json(master_key, skill_content)
    bundle2 = _encrypt_to_json(master_key, skill_content)

    # Different nonces are expected (randomised per call)
    # But both decrypt to the same plaintext
    aesgcm = AESGCM(master_key)
    pt1 = aesgcm.decrypt(bytes.fromhex(bundle1["nonce"]), bytes.fromhex(bundle1["ciphertext"]), None)
    pt2 = aesgcm.decrypt(bytes.fromhex(bundle2["nonce"]), bytes.fromhex(bundle2["ciphertext"]), None)
    assert pt1 == skill_content
    assert pt2 == skill_content
    assert pt1 == pt2
