"""Tests for agentflow/init.py — first-run initialization."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


class TestIsInitialized:
    def test_false_when_no_state_file(self, tmp_path):
        from agentflow.init import _is_initialized
        with patch("agentflow.init._STATE_FILE", tmp_path / "config.json"):
            assert _is_initialized(tmp_path) is False

    def test_false_when_key_missing(self, tmp_path):
        state = tmp_path / "config.json"
        state.write_text('{"other": true}')
        from agentflow.init import _is_initialized
        with patch("agentflow.init._STATE_FILE", state):
            assert _is_initialized(tmp_path) is False

    def test_true_when_initialized(self, tmp_path):
        state = tmp_path / "config.json"
        state.write_text('{"initialized": true}')
        from agentflow.init import _is_initialized
        with patch("agentflow.init._STATE_FILE", state):
            assert _is_initialized(tmp_path) is True


class TestMarkInitialized:
    def test_creates_state_file(self, tmp_path):
        state = tmp_path / "config.json"
        from agentflow.init import _mark_initialized
        with patch("agentflow.init._STATE_FILE", state):
            _mark_initialized(tmp_path)
        assert json.loads(state.read_text())["initialized"] is True

    def test_preserves_existing_keys(self, tmp_path):
        state = tmp_path / "config.json"
        state.write_text('{"other": "preserved"}')
        from agentflow.init import _mark_initialized
        with patch("agentflow.init._STATE_FILE", state):
            _mark_initialized(tmp_path)
        data = json.loads(state.read_text())
        assert data["initialized"] is True
        assert data["other"] == "preserved"

    def test_idempotent(self, tmp_path):
        state = tmp_path / "config.json"
        from agentflow.init import _mark_initialized
        with patch("agentflow.init._STATE_FILE", state):
            _mark_initialized(tmp_path)
            _mark_initialized(tmp_path)
        assert json.loads(state.read_text())["initialized"] is True


class TestCheckAndRun:
    def test_skips_when_already_initialized(self, tmp_path):
        state = tmp_path / "config.json"
        state.write_text('{"initialized": true}')
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch.object(init, "_run_interactive") as mock_i:
                with patch.object(init, "_run_silent") as mock_s:
                    init.check_and_run(tmp_path)
        mock_i.assert_not_called()
        mock_s.assert_not_called()

    def test_calls_interactive_when_tty(self, tmp_path):
        state = tmp_path / "config.json"
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                with patch.object(init, "_run_interactive") as mock_i:
                    init.check_and_run(tmp_path)
        mock_i.assert_called_once_with(tmp_path)

    def test_calls_silent_when_no_tty(self, tmp_path):
        state = tmp_path / "config.json"
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = False
                with patch.object(init, "_run_silent") as mock_s:
                    init.check_and_run(tmp_path)
        mock_s.assert_called_once_with(tmp_path)


class TestDeepMergeProjectSettings:
    def _global(self, tmp_path, content="{}"):
        p = tmp_path / "global.json"
        p.write_text(content)
        return p

    def test_creates_project_settings_if_missing(self, tmp_path):
        g = self._global(tmp_path)
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._deep_merge_project_settings(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "hooks" in data
        assert "autoCompactEnabled" in data

    def test_preserves_existing_user_keys(self, tmp_path):
        g = self._global(tmp_path)
        proj = tmp_path / ".claude" / "settings.json"
        proj.parent.mkdir(parents=True)
        proj.write_text('{"model": "opus", "customKey": "value"}')
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._deep_merge_project_settings(tmp_path)
        data = json.loads(proj.read_text())
        assert data["model"] == "opus"
        assert data["customKey"] == "value"

    def test_hooks_not_duplicated_on_second_call(self, tmp_path):
        g = self._global(tmp_path)
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._deep_merge_project_settings(tmp_path)
            init._deep_merge_project_settings(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        ups = data["hooks"].get("UserPromptSubmit", [])
        all_cmds = [h["command"] for entry in ups for h in entry.get("hooks", [])]
        assert len(all_cmds) == len(set(all_cmds))

    def test_moves_stop_hook_from_global(self, tmp_path):
        global_settings = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "custom-stop-cmd"}]}],
                "PreToolUse": [],
            }
        }
        g = self._global(tmp_path, json.dumps(global_settings))
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._deep_merge_project_settings(tmp_path)
        global_data = json.loads(g.read_text())
        assert "Stop" not in global_data.get("hooks", {})
        assert "PreToolUse" in global_data.get("hooks", {})

    def test_moves_autocompact_from_global(self, tmp_path):
        g = self._global(tmp_path, '{"autoCompactEnabled": false}')
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._deep_merge_project_settings(tmp_path)
        assert "autoCompactEnabled" not in json.loads(g.read_text())
        proj_data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert proj_data["autoCompactEnabled"] is False

    def test_autocompact_defaults_false_when_absent(self, tmp_path):
        g = self._global(tmp_path)
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._deep_merge_project_settings(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert data["autoCompactEnabled"] is False


class TestRegisterHeadroomMcp:
    def test_adds_headroom_when_absent(self, tmp_path):
        g = tmp_path / "settings.json"
        g.write_text('{"allowedMcpServers": [{"serverName": "other"}]}')
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._register_headroom_mcp()
        names = [s["serverName"] for s in json.loads(g.read_text())["allowedMcpServers"]]
        assert "headroom" in names
        assert "other" in names

    def test_idempotent_when_headroom_present(self, tmp_path):
        g = tmp_path / "settings.json"
        g.write_text('{"allowedMcpServers": [{"serverName": "headroom"}]}')
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._register_headroom_mcp()
            init._register_headroom_mcp()
        count = sum(1 for s in json.loads(g.read_text())["allowedMcpServers"] if s["serverName"] == "headroom")
        assert count == 1

    def test_creates_key_if_absent(self, tmp_path):
        g = tmp_path / "settings.json"
        g.write_text("{}")
        from agentflow import init
        with patch("agentflow.init._GLOBAL_SETTINGS", g):
            init._register_headroom_mcp()
        data = json.loads(g.read_text())
        assert any(s.get("serverName") == "headroom" for s in data.get("allowedMcpServers", []))


class TestRunSilent:
    def _silent(self, tmp_path):
        state = tmp_path / "config.json"
        g = tmp_path / "global.json"
        g.write_text("{}")
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("agentflow.init._GLOBAL_SETTINGS", g):
                init._run_silent(tmp_path)
        return state, g

    def test_stderr_message_and_initialized(self, tmp_path, capsys):
        state, _ = self._silent(tmp_path)
        assert capsys.readouterr().err != ""
        assert json.loads(state.read_text())["initialized"] is True

    def test_git_perms_added(self, tmp_path):
        self._silent(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        perms = data.get("permissions", {}).get("allow", [])
        assert "Bash(git push *)" in perms


class TestRunInteractive:
    def _run(self, tmp_path, answers, global_content="{}"):
        state = tmp_path / "config.json"
        g = tmp_path / "global.json"
        g.write_text(global_content)
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("agentflow.init._GLOBAL_SETTINGS", g):
                with patch("builtins.input", side_effect=answers):
                    init._run_interactive(tmp_path)
        return state, g, tmp_path / ".claude" / "settings.json"

    def test_initialized_written(self, tmp_path):
        state, _, _ = self._run(tmp_path, ["y", "y"])
        assert json.loads(state.read_text())["initialized"] is True

    def test_allow_mcp_true(self, tmp_path):
        _, g, _ = self._run(tmp_path, ["y", "y"])
        assert json.loads(g.read_text()).get("allowManagedMcpServersOnly") is True

    def test_allow_mcp_false(self, tmp_path):
        _, g, _ = self._run(tmp_path, ["n", "y"])
        assert json.loads(g.read_text()).get("allowManagedMcpServersOnly") is False

    def test_git_perms_yes(self, tmp_path):
        _, _, proj = self._run(tmp_path, ["y", "y"])
        perms = json.loads(proj.read_text()).get("permissions", {}).get("allow", [])
        assert "Bash(git push *)" in perms
        assert "Bash(gh pr create *)" in perms
        assert "Bash(gh pr merge *)" in perms

    def test_git_perms_no(self, tmp_path):
        _, _, proj = self._run(tmp_path, ["y", "n"])
        perms = json.loads(proj.read_text()).get("permissions", {}).get("allow", [])
        assert "Bash(git push *)" not in perms


class TestSkillBundleDownload:
    def test_download_attempted_when_encrypt_true(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_URL", "http://example.com/bundle.enc")
        bundle_path = tmp_path / "bundle-v1.enc"
        state = tmp_path / "config.json"
        g = tmp_path / "global.json"
        g.write_text("{}")
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"bundle-data"
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("agentflow.init._GLOBAL_SETTINGS", g):
                with patch("agentflow.init._BUNDLE_PATH", bundle_path):
                    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
                        with patch("builtins.input", side_effect=["y", "y"]):
                            init._run_interactive(tmp_path)
        mock_open.assert_called_once()

    def test_no_download_when_encrypt_false(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "false")
        state = tmp_path / "config.json"
        g = tmp_path / "global.json"
        g.write_text("{}")
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("agentflow.init._GLOBAL_SETTINGS", g):
                with patch("urllib.request.urlopen") as mock_open:
                    with patch("builtins.input", side_effect=["y", "y"]):
                        init._run_interactive(tmp_path)
        mock_open.assert_not_called()

    def test_skips_download_if_bundle_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTFLOW_ENCRYPT", "true")
        monkeypatch.setenv("AGENTFLOW_BUNDLE_URL", "http://example.com/bundle.enc")
        bundle_path = tmp_path / "bundle-v1.enc"
        bundle_path.write_bytes(b"existing")
        state = tmp_path / "config.json"
        g = tmp_path / "global.json"
        g.write_text("{}")
        from agentflow import init
        with patch("agentflow.init._STATE_FILE", state):
            with patch("agentflow.init._GLOBAL_SETTINGS", g):
                with patch("agentflow.init._BUNDLE_PATH", bundle_path):
                    with patch("urllib.request.urlopen") as mock_open:
                        with patch("builtins.input", side_effect=["y", "y"]):
                            init._run_interactive(tmp_path)
        mock_open.assert_not_called()


class TestOrchestratorConfigInitialized:
    def test_default_false(self):
        from agentflow.config.models import OrchestratorConfig
        assert OrchestratorConfig().initialized is False

    def test_can_be_set_true(self):
        from agentflow.config.models import OrchestratorConfig
        assert OrchestratorConfig(initialized=True).initialized is True


class TestProxyShellCallsInit:
    def test_check_and_run_called_before_flip_ab_arm(self, tmp_path):
        from agentflow.shell.pty_shell import ProxyShell
        from agentflow import init

        shell = ProxyShell(tmp_path)
        call_order: list = []

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "8080"
        mock_proc.poll.return_value = None

        with patch.object(init, "check_and_run", side_effect=lambda r: call_order.append("init")):
            with patch.object(shell, "_flip_ab_arm", side_effect=lambda: call_order.append("flip")):
                with patch.object(shell, "_write_model_arm"):
                    with patch("subprocess.Popen", return_value=mock_proc):
                        shell.start()

        assert call_order[0] == "init"
        assert "flip" in call_order
