"""Tests for skill bundle encryption and load_skill AGENTFLOW_ENCRYPT gate."""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bundle(skills: dict[str, str], key: bytes, tmp_path: Path) -> Path:
    bundle_path = tmp_path / "bundle-v1.enc"
    aesgcm = AESGCM(key)
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_STORED) as zf:
        for entry_name, plaintext in skills.items():
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
            zf.writestr(entry_name, nonce + ciphertext)
    return bundle_path


def _key_server_mock(key: bytes) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = f'{{"key": "{key.hex()}"}}'.encode()
    return mock_resp


# ---------------------------------------------------------------------------
# models.py — encrypt_skills field
# ---------------------------------------------------------------------------

class TestOrchestratorConfigEncryptField:
    def test_default_false(self):
        from agentflow.config.models import OrchestratorConfig
        assert OrchestratorConfig().encrypt_skills is False

    def test_can_set_true(self):
        from agentflow.config.models import OrchestratorConfig
        assert OrchestratorConfig(encrypt_skills=True).encrypt_skills is True

    def test_oracle_threshold_still_present(self):
        from agentflow.config.models import OrchestratorConfig
        assert OrchestratorConfig().oracle_threshold_tokens == 50000


# ---------------------------------------------------------------------------
# build_bundle.py
# ---------------------------------------------------------------------------

class TestBuildBundle:
    def test_creates_bundle_with_all_md_files(self, tmp_path: Path):
        from agentflow.ip.build_bundle import build_bundle
        src = tmp_path / "claude"
        src.mkdir()
        (src / "oracle.md").write_text("oracle content")
        (src / "oracle").mkdir()
        (src / "oracle" / "checklist.md").write_text("checklist content")
        out = tmp_path / "bundle-v1.enc"
        build_bundle(key=os.urandom(32), source_dir=str(src), output_path=str(out))
        with zipfile.ZipFile(out, "r") as zf:
            names = set(zf.namelist())
        assert "oracle.md" in names
        assert "oracle/checklist.md" in names

    def test_bundle_entries_are_encrypted(self, tmp_path: Path):
        from agentflow.ip.build_bundle import build_bundle
        src = tmp_path / "claude"
        src.mkdir()
        (src / "oracle.md").write_text("oracle content")
        key = os.urandom(32)
        out = tmp_path / "bundle-v1.enc"
        build_bundle(key=key, source_dir=str(src), output_path=str(out))
        aesgcm = AESGCM(key)
        with zipfile.ZipFile(out, "r") as zf:
            raw = zf.read("oracle.md")
        assert aesgcm.decrypt(raw[:12], raw[12:], None) == b"oracle content"

    def test_bundle_is_not_readable_as_plaintext(self, tmp_path: Path):
        from agentflow.ip.build_bundle import build_bundle
        src = tmp_path / "claude"
        src.mkdir()
        (src / "oracle.md").write_text("super secret oracle content")
        out = tmp_path / "bundle-v1.enc"
        build_bundle(key=os.urandom(32), source_dir=str(src), output_path=str(out))
        assert b"super secret oracle content" not in out.read_bytes()

    def test_build_bundle_idempotent(self, tmp_path: Path):
        from agentflow.ip.build_bundle import build_bundle
        src = tmp_path / "claude"
        src.mkdir()
        (src / "skill.md").write_text("skill content")
        key = os.urandom(32)
        out = tmp_path / "bundle-v1.enc"
        build_bundle(key=key, source_dir=str(src), output_path=str(out))
        build_bundle(key=key, source_dir=str(src), output_path=str(out))
        assert out.exists()

    def test_output_dir_created_if_missing(self, tmp_path: Path):
        from agentflow.ip.build_bundle import build_bundle
        src = tmp_path / "claude"
        src.mkdir()
        (src / "skill.md").write_text("x")
        out = tmp_path / "deep" / "nested" / "bundle-v1.enc"
        build_bundle(key=os.urandom(32), source_dir=str(src), output_path=str(out))
        assert out.exists()


# ---------------------------------------------------------------------------
# load_skill.py — AGENTFLOW_ENCRYPT=false (plaintext path)
# ---------------------------------------------------------------------------

class TestLoadSkillPlaintext:
    def test_reads_plaintext_skill(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        skill_dir = tmp_path / "commands" / "claude"
        skill_dir.mkdir(parents=True)
        (skill_dir / "oracle.md").write_text("oracle plaintext")
        monkeypatch.delenv("AGENTFLOW_ENCRYPT", raising=False)
        monkeypatch.setenv("AGENTFLOW_SKILLS_DIR", str(skill_dir))
        captured = io.StringIO()
        with patch.object(sys, "argv", ["load_skill", "oracle"]):
            with patch("sys.stdout", captured):
                ls_mod.main()
        assert "oracle plaintext" in captured.getvalue()

    def test_reads_plaintext_false_explicit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        skill_dir = tmp_path / "commands" / "claude"
        skill_dir.mkdir(parents=True)
        (skill_dir / "oracle.md").write_text("oracle content here")
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "false")
        monkeypatch.setenv("AGENTFLOW_SKILLS_DIR", str(skill_dir))
        captured = io.StringIO()
        with patch.object(sys, "argv", ["load_skill", "oracle"]):
            with patch("sys.stdout", captured):
                ls_mod.main()
        assert "oracle content here" in captured.getvalue()

    def test_subdirectory_skill_plaintext(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        skill_dir = tmp_path / "commands" / "claude"
        (skill_dir / "oracle").mkdir(parents=True)
        (skill_dir / "oracle" / "checklist.md").write_text("checklist content")
        monkeypatch.delenv("AGENTFLOW_ENCRYPT", raising=False)
        monkeypatch.setenv("AGENTFLOW_SKILLS_DIR", str(skill_dir))
        captured = io.StringIO()
        with patch.object(sys, "argv", ["load_skill", "oracle:checklist"]):
            with patch("sys.stdout", captured):
                ls_mod.main()
        assert "checklist content" in captured.getvalue()

    def test_missing_plaintext_exits_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        monkeypatch.delenv("AGENTFLOW_ENCRYPT", raising=False)
        monkeypatch.setenv("AGENTFLOW_SKILLS_DIR", str(tmp_path / "commands" / "claude"))
        with patch.object(sys, "argv", ["load_skill", "nonexistent"]):
            with pytest.raises(SystemExit) as exc:
                ls_mod.main()
        assert exc.value.code == 1

    def test_no_network_call_in_plaintext_mode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        skill_dir = tmp_path / "commands" / "claude"
        skill_dir.mkdir(parents=True)
        (skill_dir / "oracle.md").write_text("content")
        monkeypatch.delenv("AGENTFLOW_ENCRYPT", raising=False)
        monkeypatch.setenv("AGENTFLOW_SKILLS_DIR", str(skill_dir))
        with patch("urllib.request.urlopen") as mock_urlopen:
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stdout", io.StringIO()):
                    ls_mod.main()
            mock_urlopen.assert_not_called()


# ---------------------------------------------------------------------------
# load_skill.py — AGENTFLOW_ENCRYPT=true (bundle path)
# ---------------------------------------------------------------------------

class TestLoadSkillEncrypted:
    def test_decrypts_bundle_entry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        key = os.urandom(32)
        bundle_path = _make_bundle({"oracle.md": "secret oracle content"}, key, tmp_path)
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_URL", "http://fake-server")
        monkeypatch.setenv("AGENTFLOW_KEY", "test-license-key")
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)
        captured = io.StringIO()
        with patch("urllib.request.urlopen", return_value=_key_server_mock(key)):
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stdout", captured):
                    ls_mod.main()
        assert "secret oracle content" in captured.getvalue()

    def test_missing_bundle_exits_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(tmp_path / "nonexistent.enc"))
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_URL", "http://fake-server")
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_TOKEN", "test-token")
        err_out = io.StringIO()
        with patch.object(sys, "argv", ["load_skill", "oracle"]):
            with patch("sys.stderr", err_out):
                with pytest.raises(SystemExit) as exc:
                    ls_mod.main()
        assert exc.value.code == 1
        assert len(err_out.getvalue()) > 0

    def test_key_server_unreachable_exits_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import urllib.error
        from agentflow.ip import load_skill as ls_mod
        key = os.urandom(32)
        bundle_path = _make_bundle({"oracle.md": "content"}, key, tmp_path)
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_URL", "http://unreachable-server")
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_TOKEN", "token")
        err_out = io.StringIO()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stderr", err_out):
                    with pytest.raises(SystemExit) as exc:
                        ls_mod.main()
        assert exc.value.code == 1
        assert len(err_out.getvalue()) > 0

    def test_direct_key_env_var_skips_key_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """AGENTFLOW_MASTER_KEY is the direct-key dev override; bypasses /validate."""
        from agentflow.ip import load_skill as ls_mod
        key = os.urandom(32)
        bundle_path = _make_bundle({"oracle.md": "content"}, key, tmp_path)
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(bundle_path))
        monkeypatch.setenv("AGENTFLOW_MASTER_KEY", key.hex())
        monkeypatch.delenv("AGENTFLOW_KEY", raising=False)
        captured = io.StringIO()
        with patch("urllib.request.urlopen") as mock_urlopen:
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stdout", captured):
                    ls_mod.main()
            mock_urlopen.assert_not_called()
        assert "content" in captured.getvalue()


# ---------------------------------------------------------------------------
# scripts/build_dist.sh — presence check
# ---------------------------------------------------------------------------

class TestBuildDistSh:
    def test_script_exists(self):
        wt = Path(__file__).parent.parent
        assert (wt / "scripts" / "build_dist.sh").exists()

    def test_script_references_bundle_build(self):
        wt = Path(__file__).parent.parent
        script = (wt / "scripts" / "build_dist.sh").read_text()
        assert "build_bundle" in script or "encrypt" in script.lower()

    def test_script_references_master_key(self):
        wt = Path(__file__).parent.parent
        script = (wt / "scripts" / "build_dist.sh").read_text()
        assert "AGENTFLOW_MASTER_KEY" in script
