"""Tests for T-305: load_skill POST /validate flow and MASTER_KEY/API_KEY split."""
from __future__ import annotations

import io
import json
import os
import sys
import urllib.error
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


def _validate_mock_200(cek: bytes) -> MagicMock:
    """Mock urlopen context manager that returns 200 + {"key": "<hex>"}."""
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps({"key": cek.hex()}).encode()
    return mock_resp


def _validate_mock_401(error_code: str) -> urllib.error.HTTPError:
    """Build an HTTPError with 401 status and JSON error body."""
    body = json.dumps({"error": error_code}).encode()
    return urllib.error.HTTPError(
        url="http://fake/validate",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


# ---------------------------------------------------------------------------
# _get_key_from_env — AGENTFLOW_MASTER_KEY is the only direct-key override
# ---------------------------------------------------------------------------

class TestGetKeyFromEnv:
    def test_master_key_hex_returns_bytes(self, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip.load_skill import _get_key_from_env
        key = os.urandom(32)
        monkeypatch.setenv("AGENTFLOW_MASTER_KEY", key.hex())
        monkeypatch.delenv("AGENTFLOW_KEY", raising=False)
        result = _get_key_from_env()
        assert result == key

    def test_master_key_passphrase_hashed(self, monkeypatch: pytest.MonkeyPatch):
        import hashlib
        from agentflow.ip.load_skill import _get_key_from_env
        monkeypatch.setenv("AGENTFLOW_MASTER_KEY", "mypassphrase")
        monkeypatch.delenv("AGENTFLOW_KEY", raising=False)
        result = _get_key_from_env()
        assert result == hashlib.sha256(b"mypassphrase").digest()

    def test_no_master_key_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip.load_skill import _get_key_from_env
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)
        monkeypatch.delenv("AGENTFLOW_KEY", raising=False)
        assert _get_key_from_env() is None

    def test_agentflow_key_alone_does_not_bypass_server(self, monkeypatch: pytest.MonkeyPatch):
        """AGENTFLOW_KEY is the license key, not a direct key override."""
        from agentflow.ip.load_skill import _get_key_from_env
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)
        monkeypatch.setenv("AGENTFLOW_KEY", os.urandom(32).hex())
        # _get_key_from_env must return None — AGENTFLOW_KEY goes to /validate, not here
        assert _get_key_from_env() is None


# ---------------------------------------------------------------------------
# _fetch_key_from_server — POST /validate with {api_key: ...} body
# ---------------------------------------------------------------------------

class TestFetchKeyFromServer:
    def test_200_returns_cek_bytes(self, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip.load_skill import _fetch_key_from_server
        cek = os.urandom(32)
        with patch("urllib.request.urlopen", return_value=_validate_mock_200(cek)):
            result = _fetch_key_from_server("http://fake", "my-license-key")
        assert result == cek

    def test_posts_to_validate_endpoint(self):
        from agentflow.ip.load_skill import _fetch_key_from_server
        cek = os.urandom(32)
        captured_req = {}

        def fake_urlopen(req):
            captured_req["url"] = req.full_url
            captured_req["data"] = req.data
            captured_req["method"] = req.get_method()
            return _validate_mock_200(cek)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _fetch_key_from_server("http://fake-server", "abc123")

        assert captured_req["url"] == "http://fake-server/validate"
        assert captured_req["method"] == "POST"
        body = json.loads(captured_req["data"])
        assert body == {"api_key": "abc123"}

    def test_401_license_revoked_exits_1(self, capsys):
        from agentflow.ip.load_skill import _fetch_key_from_server
        exc = _validate_mock_401("license_revoked")
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(SystemExit) as e:
                _fetch_key_from_server("http://fake", "revoked-key")
        assert e.value.code == 1
        assert "License invalid" in capsys.readouterr().err

    def test_401_invalid_key_exits_1(self, capsys):
        from agentflow.ip.load_skill import _fetch_key_from_server
        exc = _validate_mock_401("invalid_key")
        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(SystemExit) as e:
                _fetch_key_from_server("http://fake", "unknown-key")
        assert e.value.code == 1
        assert "License invalid" in capsys.readouterr().err

    def test_url_error_unreachable_exits_1(self, capsys):
        from agentflow.ip.load_skill import _fetch_key_from_server
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(SystemExit) as e:
                _fetch_key_from_server("http://unreachable", "key")
        assert e.value.code == 1
        err = capsys.readouterr().err
        assert len(err) > 0

    def test_generic_exception_exits_1(self, capsys):
        from agentflow.ip.load_skill import _fetch_key_from_server
        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as e:
                _fetch_key_from_server("http://fake", "key")
        assert e.value.code == 1


# ---------------------------------------------------------------------------
# _get_key — MASTER_KEY takes priority; AGENTFLOW_KEY goes to /validate
# ---------------------------------------------------------------------------

class TestGetKey:
    def test_master_key_bypasses_server(self, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip.load_skill import _get_key
        key = os.urandom(32)
        monkeypatch.setenv("AGENTFLOW_MASTER_KEY", key.hex())
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = _get_key("http://fake", "license-key")
        mock_urlopen.assert_not_called()
        assert result == key

    def test_api_key_calls_server(self, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip.load_skill import _get_key
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)
        cek = os.urandom(32)
        with patch("urllib.request.urlopen", return_value=_validate_mock_200(cek)):
            result = _get_key("http://fake", "my-api-key")
        assert result == cek

    def test_neither_set_exits_1(self, monkeypatch: pytest.MonkeyPatch, capsys):
        from agentflow.ip.load_skill import _get_key
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)
        with pytest.raises(SystemExit) as e:
            _get_key("http://fake", "")
        assert e.value.code == 1
        assert len(capsys.readouterr().err) > 0

    def test_no_url_no_key_exits_1(self, monkeypatch: pytest.MonkeyPatch, capsys):
        from agentflow.ip.load_skill import _get_key
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)
        with pytest.raises(SystemExit) as e:
            _get_key("", "")
        assert e.value.code == 1


# ---------------------------------------------------------------------------
# main() — ENCRYPT=true: full flow with mocked server
# ---------------------------------------------------------------------------

class TestMainEncryptTrue:
    def test_full_flow_with_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod

        cek = os.urandom(32)
        bundle = _make_bundle({"oracle.md": "secret oracle skill"}, cek, tmp_path)

        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(bundle))
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_URL", "http://fake")
        monkeypatch.setenv("AGENTFLOW_KEY", "valid-license-key-123")
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)

        captured = io.StringIO()
        with patch("urllib.request.urlopen", return_value=_validate_mock_200(cek)):
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stdout", captured):
                    ls_mod.main()
        assert "secret oracle skill" in captured.getvalue()

    def test_revoked_key_exits_1(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod

        cek = os.urandom(32)
        bundle = _make_bundle({"oracle.md": "skill"}, cek, tmp_path)

        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(bundle))
        monkeypatch.setenv("AGENTFLOW_KEY_SERVER_URL", "http://fake")
        monkeypatch.setenv("AGENTFLOW_KEY", "revoked-key")
        monkeypatch.delenv("AGENTFLOW_MASTER_KEY", raising=False)

        exc = _validate_mock_401("license_revoked")
        err_out = io.StringIO()
        with patch("urllib.request.urlopen", side_effect=exc):
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stderr", err_out):
                    with pytest.raises(SystemExit) as e:
                        ls_mod.main()
        assert e.value.code == 1
        assert "License invalid" in err_out.getvalue()

    def test_master_key_override_skips_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod

        cek = os.urandom(32)
        bundle = _make_bundle({"oracle.md": "master key content"}, cek, tmp_path)

        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_PATH", str(bundle))
        monkeypatch.setenv("AGENTFLOW_MASTER_KEY", cek.hex())
        monkeypatch.delenv("AGENTFLOW_KEY", raising=False)

        captured = io.StringIO()
        with patch("urllib.request.urlopen") as mock_urlopen:
            with patch.object(sys, "argv", ["load_skill", "oracle"]):
                with patch("sys.stdout", captured):
                    ls_mod.main()
        mock_urlopen.assert_not_called()
        assert "master key content" in captured.getvalue()


# ---------------------------------------------------------------------------
# main() — ENCRYPT=false: plaintext path (smoke test, covered by test_skill_bundle too)
# ---------------------------------------------------------------------------

class TestMainEncryptFalse:
    def test_plaintext_skill(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from agentflow.ip import load_skill as ls_mod

        skill_dir = tmp_path / "commands" / "claude"
        skill_dir.mkdir(parents=True)
        (skill_dir / "oracle.md").write_text("oracle content")

        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "false")
        monkeypatch.setenv("AGENTFLOW_SKILLS_DIR", str(skill_dir))

        captured = io.StringIO()
        with patch.object(sys, "argv", ["load_skill", "oracle"]):
            with patch("sys.stdout", captured):
                ls_mod.main()
        assert "oracle content" in captured.getvalue()
