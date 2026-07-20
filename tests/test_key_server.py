import os
import time
import pytest
import httpx
import tempfile
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from agentflow.ip.key_server import run_server_in_thread, generate_ephemeral_key, main

@pytest.fixture
def auth_token():
    return "test-auth-token-12345"

@pytest.fixture
def skills_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock skill file
        skill_path = Path(tmpdir) / "test_skill" / "SKILL.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text("Mock skill content here.")
        yield tmpdir

@pytest.fixture
def test_server(auth_token, skills_dir):
    server, thread, port = run_server_in_thread(
        host="127.0.0.1",
        port=0,
        token=auth_token,
        skills_dir=skills_dir
    )
    yield server, f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join()

def test_auth_validation_missing_token(test_server):
    _, url = test_server
    response = httpx.get(f"{url}/key")
    assert response.status_code == 401
    assert "Unauthorized" in response.text

def test_auth_validation_invalid_token(test_server):
    _, url = test_server
    headers = {"Authorization": "Bearer invalid-token"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 401

def test_auth_validation_bad_formats(test_server):
    _, url = test_server
    # Bad auth scheme
    headers = {"Authorization": "Basic invalid-token"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 401

    # Missing bearer token part
    headers = {"Authorization": "Bearer"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 401

    # Too many parts
    headers = {"Authorization": "Bearer token extra"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 401

def test_ephemeral_key_generation_and_issuance(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "key_id" in data
    assert "key" in data
    
    key_hex = data["key"]
    assert len(key_hex) == 64
    bytes.fromhex(key_hex)

def test_serving_encrypted_skill(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    
    # 1. Get ephemeral key
    key_resp = httpx.get(f"{url}/key", headers=headers)
    assert key_resp.status_code == 200
    key_data = key_resp.json()
    key_id = key_data["key_id"]
    key_hex = key_data["key"]
    
    # 2. Get encrypted skill content
    skill_headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Key-ID": key_id
    }
    response = httpx.get(f"{url}/skill/test_skill", headers=skill_headers)
    assert response.status_code == 200
    
    skill_data = response.json()
    assert "nonce" in skill_data
    assert "ciphertext" in skill_data
    
    # 3. Decrypt skill content
    key = bytes.fromhex(key_hex)
    nonce = bytes.fromhex(skill_data["nonce"])
    ciphertext = bytes.fromhex(skill_data["ciphertext"])
    
    aesgcm = AESGCM(key)
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    decrypted_text = decrypted_bytes.decode("utf-8")
    
    assert decrypted_text == "Mock skill content here."

def test_serving_skill_invalid_key(test_server, auth_token):
    _, url = test_server
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Key-ID": "non-existent-key-id"
    }
    response = httpx.get(f"{url}/skill/test_skill", headers=headers)
    assert response.status_code == 400
    assert "Invalid key ID" in response.text

def test_serving_nonexistent_skill(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    key_resp = httpx.get(f"{url}/key", headers=headers)
    key_id = key_resp.json()["key_id"]
    
    skill_headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Key-ID": key_id
    }
    response = httpx.get(f"{url}/skill/nonexistent", headers=skill_headers)
    assert response.status_code == 404
    assert "Skill not found" in response.text

def test_serving_skill_via_query_param(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    key_resp = httpx.get(f"{url}/key", headers=headers)
    key_id = key_resp.json()["key_id"]
    key_hex = key_resp.json()["key"]
    
    response = httpx.get(
        f"{url}/skill/test_skill?key_id={key_id}",
        headers=headers
    )
    assert response.status_code == 200
    skill_data = response.json()
    
    key = bytes.fromhex(key_hex)
    nonce = bytes.fromhex(skill_data["nonce"])
    ciphertext = bytes.fromhex(skill_data["ciphertext"])
    
    aesgcm = AESGCM(key)
    decrypted = aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    assert decrypted == "Mock skill content here."

def test_invalid_route(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = httpx.get(f"{url}/invalid_path", headers=headers)
    assert response.status_code == 404

def test_clean_expired_keys(test_server):
    server, _ = test_server
    
    # Manually insert an expired key
    with server.lock:
        server.active_keys["expired-key-1"] = (b"some-key", time.time() - 100)
        server.active_keys["valid-key-2"] = (b"some-key-2", time.time() + 100)
        
    server.clean_expired_keys()
    
    with server.lock:
        assert "expired-key-1" not in server.active_keys
        assert "valid-key-2" in server.active_keys

def test_generate_ephemeral_key_function():
    key = generate_ephemeral_key()
    assert isinstance(key, bytes)
    assert len(key) == 32

def test_serving_skill_read_error(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    key_resp = httpx.get(f"{url}/key", headers=headers)
    key_id = key_resp.json()["key_id"]

    skill_headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Key-ID": key_id
    }
    
    # Mock Path.read_bytes to raise PermissionError
    with patch.object(Path, "read_bytes", side_effect=PermissionError("Permission denied")):
        response = httpx.get(f"{url}/skill/test_skill", headers=skill_headers)
        assert response.status_code == 500
        assert "Error reading skill" in response.text

def test_serving_skill_encryption_error(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    key_resp = httpx.get(f"{url}/key", headers=headers)
    key_id = key_resp.json()["key_id"]

    skill_headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Key-ID": key_id
    }
    
    # Mock AESGCM.encrypt to raise ValueError
    with patch.object(AESGCM, "encrypt", side_effect=ValueError("Encryption error")):
        response = httpx.get(f"{url}/skill/test_skill", headers=skill_headers)
        assert response.status_code == 500
        assert "Encryption failed" in response.text

def test_serving_skill_path_traversal(test_server, auth_token):
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    key_resp = httpx.get(f"{url}/key", headers=headers)
    key_id = key_resp.json()["key_id"]
    
    skill_headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Key-ID": key_id
    }
    # 1. Direct traversal (client may normalize path to /etc/passwd -> 404)
    response = httpx.get(f"{url}/skill/../../etc/passwd", headers=skill_headers)
    assert response.status_code in (400, 404)

    # 2. Encoded traversal (decoded on server -> /skill/../../etc/passwd -> 400)
    response = httpx.get(f"{url}/skill/..%2f..%2fetc/passwd", headers=skill_headers)
    assert response.status_code == 400
    assert "Invalid skill path" in response.text

def test_main_missing_token():
    with patch("sys.argv", ["key_server"]), \
         patch.dict(os.environ, {}, clear=True), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

def test_main_runs_and_handles_keyboard_interrupt():
    with patch("sys.argv", ["key_server", "--token", "cmd-token"]), \
         patch.dict(os.environ, {}, clear=True), \
         patch("agentflow.ip.key_server.HTTPServer.serve_forever", side_effect=KeyboardInterrupt) as mock_serve:
        main()
        mock_serve.assert_called_once()


@pytest.fixture
def master_key():
    return os.urandom(32)


@pytest.fixture
def master_key_server(auth_token, skills_dir, master_key):
    server, thread, port = run_server_in_thread(
        host="127.0.0.1",
        port=0,
        token=auth_token,
        skills_dir=skills_dir,
        master_key=master_key,
    )
    yield server, f"http://127.0.0.1:{port}", master_key
    server.shutdown()
    thread.join()


def test_master_key_served_on_key_endpoint(master_key_server, auth_token):
    """When AGENTFLOW_MASTER_KEY is set, /key returns that key (no random ephemeral, no key_id)."""
    _, url, mk = master_key_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 200
    data = response.json()
    # key matches master key
    assert data["key"] == mk.hex()
    # no key_id in master-key mode
    assert "key_id" not in data


def test_master_key_revocation_via_token_rejection(master_key_server):
    """Invalid token gets 401 even when master key is set (revocation: reject the token)."""
    _, url, _ = master_key_server
    response = httpx.get(f"{url}/key", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
    assert "Unauthorized" in response.text


def test_ephemeral_key_when_no_master_key(test_server, auth_token):
    """Without master key, /key still returns ephemeral key + key_id (backward compat)."""
    _, url = test_server
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = httpx.get(f"{url}/key", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "key_id" in data
    assert "key" in data
    assert len(data["key"]) == 64
