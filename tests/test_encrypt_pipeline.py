import os
import tempfile
import hashlib
from pathlib import Path
import pytest
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from agentflow.ip.encrypt_pipeline import encrypt_skills, map_path, derive_key, main

def test_map_path():
    source_root = Path("/src")
    output_root = Path("/out")
    
    # Claude mapping
    p1 = Path("/src/claude/oracle.md")
    assert map_path(p1, source_root, output_root) == Path("/out/claude/oracle.md")
    
    # Gemini skills mapping
    p2 = Path("/src/gemini/skills/oracle/SKILL.md")
    assert map_path(p2, source_root, output_root) == Path("/out/gemini/oracle/SKILL.md")
    
    # Gemini other mapping
    p3 = Path("/src/gemini/AGENTS.md")
    assert map_path(p3, source_root, output_root) == Path("/out/gemini/AGENTS.md")

def test_encrypt_skills_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_dir = tmp_path / "commands"
        output_dir = tmp_path / "agentflow/skills/providers"
        
        # Create directories
        (source_dir / "claude").mkdir(parents=True, exist_ok=True)
        (source_dir / "gemini/skills/oracle").mkdir(parents=True, exist_ok=True)
        (source_dir / "gemini/oracle").mkdir(parents=True, exist_ok=True)
        
        # Create test markdown files
        file1 = source_dir / "claude/oracle.md"
        file1.write_text("# Claude Oracle\nHello world", encoding="utf-8")
        
        file2 = source_dir / "gemini/skills/oracle/SKILL.md"
        file2.write_text("# Gemini Oracle Skill\nTest content", encoding="utf-8")
        
        file3 = source_dir / "gemini/oracle/generation.md"
        file3.write_text("# Gemini Generation\nMore tests", encoding="utf-8")
        
        # Key: 32 bytes (256-bit)
        key = os.urandom(32)
        
        # Run encryption pipeline
        encrypt_skills(key, source_dir=source_dir, output_dir=output_dir)
        
        # Verify output files exist at correct paths
        out1 = output_dir / "claude/oracle.md"
        out2 = output_dir / "gemini/oracle/SKILL.md"
        out3 = output_dir / "gemini/oracle/generation.md"
        
        assert out1.exists()
        assert out2.exists()
        assert out3.exists()
        
        # Verify they are encrypted and not plaintext
        data1 = out1.read_bytes()
        assert b"Claude Oracle" not in data1
        
        # Verify decrypted content matches exactly
        aesgcm = AESGCM(key)
        
        # Extracted nonce and ciphertext
        nonce1 = data1[:12]
        ciphertext1 = data1[12:]
        decrypted1 = aesgcm.decrypt(nonce1, ciphertext1, None).decode("utf-8")
        assert decrypted1 == "# Claude Oracle\nHello world"
        
        data2 = out2.read_bytes()
        nonce2 = data2[:12]
        ciphertext2 = data2[12:]
        decrypted2 = aesgcm.decrypt(nonce2, ciphertext2, None).decode("utf-8")
        assert decrypted2 == "# Gemini Oracle Skill\nTest content"
        
        data3 = out3.read_bytes()
        nonce3 = data3[:12]
        ciphertext3 = data3[12:]
        decrypted3 = aesgcm.decrypt(nonce3, ciphertext3, None).decode("utf-8")
        assert decrypted3 == "# Gemini Generation\nMore tests"

def test_derive_key():
    # Valid hex key
    hex_key = "a" * 64
    derived = derive_key(hex_key)
    assert derived == bytes.fromhex(hex_key)
    
    # Invalid hex key but length 64
    invalid_hex_key = "z" * 64
    derived_fallback = derive_key(invalid_hex_key)
    assert len(derived_fallback) == 32
    assert derived_fallback == hashlib.sha256(invalid_hex_key.encode("utf-8")).digest()
    
    # Non-hex passphrase
    passphrase = "my-secret-passphrase"
    derived_pass = derive_key(passphrase)
    assert derived_pass == hashlib.sha256(passphrase.encode("utf-8")).digest()

def test_encrypt_skills_invalid_key_length():
    with pytest.raises(ValueError, match="Encryption key must be exactly 32 bytes"):
        encrypt_skills(b"short", source_dir=".", output_dir=".")

def test_encrypt_skills_missing_source_dir():
    # Should not raise any error, just return silently
    encrypt_skills(b"a" * 32, source_dir="/non-existent-dir-12345", output_dir="/tmp/out")

def test_main_cli_arg_key(tmp_path):
    source_dir = tmp_path / "commands"
    output_dir = tmp_path / "output"
    (source_dir / "claude").mkdir(parents=True)
    (source_dir / "claude/test.md").write_text("Hello")
    
    with patch("sys.argv", ["encrypt_pipeline", "--key", "a"*64, "--source-dir", str(source_dir), "--output-dir", str(output_dir)]):
        main()
    
    assert (output_dir / "claude/test.md").exists()

def test_main_cli_env_key(tmp_path):
    source_dir = tmp_path / "commands"
    output_dir = tmp_path / "output"
    (source_dir / "claude").mkdir(parents=True)
    (source_dir / "claude/test.md").write_text("Hello")
    
    with patch("sys.argv", ["encrypt_pipeline", "--source-dir", str(source_dir), "--output-dir", str(output_dir)]), \
         patch.dict(os.environ, {"AGENTFLOW_MASTER_KEY": "passphrase123"}):
        main()
        
    assert (output_dir / "claude/test.md").exists()

def test_main_cli_env_fallback_key(tmp_path):
    source_dir = tmp_path / "commands"
    output_dir = tmp_path / "output"
    (source_dir / "claude").mkdir(parents=True)
    (source_dir / "claude/test.md").write_text("Hello")
    
    with patch("sys.argv", ["encrypt_pipeline", "--source-dir", str(source_dir), "--output-dir", str(output_dir)]), \
         patch.dict(os.environ, {"SKILL_ENCRYPTION_KEY": "passphrase456"}):
        main()
        
    assert (output_dir / "claude/test.md").exists()

def test_main_cli_missing_key():
    with patch("sys.argv", ["encrypt_pipeline"]), \
         patch.dict(os.environ, {}, clear=True), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

def test_main_cli_exception():
    with patch("sys.argv", ["encrypt_pipeline", "--key", "a"*64]), \
         patch("agentflow.ip.encrypt_pipeline.encrypt_skills", side_effect=RuntimeError("Mock error")), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
