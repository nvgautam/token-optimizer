"""Tests for agentflow.shell.pty_shell — ProxyShell lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call


class TestProxyShellStart:
    def test_start_sets_anthropic_base_url(self, tmp_path: Path):
        """After start(), ANTHROPIC_BASE_URL is set to proxy URL."""
        from agentflow.shell.pty_shell import ProxyShell

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.stdout.readline.return_value = "54321\n"

        with patch("agentflow.shell.pty_shell.subprocess.Popen", return_value=mock_proc):
            shell = ProxyShell(project_root=tmp_path)
            shell.start()

        assert os.environ.get("ANTHROPIC_BASE_URL") == "http://127.0.0.1:54321"
        assert shell.base_url == "http://127.0.0.1:54321"

        # Cleanup
        os.environ.pop("ANTHROPIC_BASE_URL", None)

    def test_start_graceful_on_dead_proc(self, tmp_path: Path):
        """If proxy exits immediately (headroom missing), banner() returns inactive message."""
        from agentflow.shell.pty_shell import ProxyShell

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = ""  # empty — proc died
        mock_proc.poll.return_value = 1  # exit code 1

        with patch("agentflow.shell.pty_shell.subprocess.Popen", return_value=mock_proc):
            shell = ProxyShell(project_root=tmp_path)
            shell.start()

        assert shell.base_url is None
        assert "inactive" in shell.banner()

    def test_start_graceful_on_invalid_port(self, tmp_path: Path):
        """If proxy prints non-numeric output, base_url stays None."""
        from agentflow.shell.pty_shell import ProxyShell

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "ERROR: headroom not installed\n"
        mock_proc.poll.return_value = None

        with patch("agentflow.shell.pty_shell.subprocess.Popen", return_value=mock_proc):
            shell = ProxyShell(project_root=tmp_path)
            shell.start()

        assert shell.base_url is None


class TestProxyShellStop:
    def test_stop_terminates_proc(self, tmp_path: Path):
        """stop() calls terminate() on subprocess."""
        from agentflow.shell.pty_shell import ProxyShell

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "12345\n"
        mock_proc.poll.return_value = None

        with patch("agentflow.shell.pty_shell.subprocess.Popen", return_value=mock_proc):
            shell = ProxyShell(project_root=tmp_path)
            shell.start()

        shell.stop()
        mock_proc.terminate.assert_called_once()

    def test_stop_noop_when_not_started(self, tmp_path: Path):
        """stop() does nothing if start() was never called."""
        from agentflow.shell.pty_shell import ProxyShell

        shell = ProxyShell(project_root=tmp_path)
        shell.stop()  # should not raise

    def test_stop_clears_anthropic_base_url(self, tmp_path: Path):
        """stop() removes ANTHROPIC_BASE_URL from env."""
        from agentflow.shell.pty_shell import ProxyShell

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "54321\n"
        mock_proc.poll.return_value = None

        with patch("agentflow.shell.pty_shell.subprocess.Popen", return_value=mock_proc):
            shell = ProxyShell(project_root=tmp_path)
            shell.start()

        assert "ANTHROPIC_BASE_URL" in os.environ
        shell.stop()
        assert "ANTHROPIC_BASE_URL" not in os.environ


class TestProxyShellBanner:
    def test_banner_active(self, tmp_path: Path):
        """Returns active message when proxy running."""
        from agentflow.shell.pty_shell import ProxyShell

        mock_proc = MagicMock()
        mock_proc.stdout.readline.return_value = "8080\n"
        mock_proc.poll.return_value = None

        with patch("agentflow.shell.pty_shell.subprocess.Popen", return_value=mock_proc):
            shell = ProxyShell(project_root=tmp_path)
            shell.start()

        banner = shell.banner()
        assert "active" in banner
        assert "http://127.0.0.1:8080" in banner

        os.environ.pop("ANTHROPIC_BASE_URL", None)

    def test_banner_inactive(self, tmp_path: Path):
        """Returns inactive message when proxy not started."""
        from agentflow.shell.pty_shell import ProxyShell

        shell = ProxyShell(project_root=tmp_path)
        banner = shell.banner()
        assert "inactive" in banner
