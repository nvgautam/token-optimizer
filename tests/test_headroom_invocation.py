"""Static assertion tests for T-093: ProxyShell owned proxy integration in cmd_shell."""

import ast
import inspect

from agentflow.cli import cmd_shell


def _cmd_shell_source() -> str:
    return inspect.getsource(cmd_shell)


def test_cmd_shell_source_uses_proxyshell():
    """cmd_shell must instantiate and start ProxyShell instead of headroom wrap."""
    source = _cmd_shell_source()
    assert "ProxyShell" in source
    assert "proxy.start()" in source
    assert "proxy.stop()" in source


def test_cmd_shell_does_not_use_headroom_wrap():
    """cmd_shell must not wrap the command in headroom wrap anymore (T-093)."""
    source = _cmd_shell_source()
    # Should not be building cmd_args with headroom wrap
    assert "headroom" not in source or "shutil.which" not in source
