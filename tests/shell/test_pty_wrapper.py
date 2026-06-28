# Tests for agentflow.shell.pty_wrapper
import os
import signal
import time
from unittest.mock import MagicMock, call, patch

import pytest

from agentflow.shell.pty_wrapper import PTYError, PTYWrapper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wrapper(fake_pid=99999, fake_fd=42):
    """Create a PTYWrapper with pty.fork mocked — no real child process."""
    with patch("pty.fork", return_value=(fake_pid, fake_fd)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        return PTYWrapper(["echo", "hello"]), fake_pid, fake_fd


# ---------------------------------------------------------------------------
# Unit: PTYError raised when pty.fork fails
# ---------------------------------------------------------------------------

def test_ptyerror_on_fork_failure():
    """PTYError raised when pty.fork() raises OSError."""
    with patch("pty.fork", side_effect=OSError("fork failed")):
        with pytest.raises(PTYError, match="fork failed"):
            PTYWrapper(["echo", "hello"])


# ---------------------------------------------------------------------------
# Unit: write_input encodes text as UTF-8 and writes to master_fd
# ---------------------------------------------------------------------------

def test_write_input_encodes_utf8():
    """write_input encodes text as UTF-8 and calls os.write(master_fd, ...)."""
    fake_pid = 99999
    fake_fd = 42

    with patch("pty.fork", return_value=(fake_pid, fake_fd)), \
         patch("os.waitpid", return_value=(fake_pid, 0)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.write") as mock_write, \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"])
        wrapper.write_input("hello\n")

    mock_write.assert_called_once_with(fake_fd, b"hello\n")


# ---------------------------------------------------------------------------
# Unit: read_output returns empty bytes on timeout
# ---------------------------------------------------------------------------

def test_read_output_returns_empty_on_timeout():
    """read_output(timeout=0.01) returns b'' when select returns no ready fds."""
    fake_pid = 99999
    fake_fd = 42

    with patch("pty.fork", return_value=(fake_pid, fake_fd)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("select.select", return_value=([], [], [])), \
         patch("os.waitpid", return_value=(0, 0)), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"])
        result = wrapper.read_output(timeout=0.01)

    assert result == b""


# ---------------------------------------------------------------------------
# Unit: read_output returns empty when already exited
# ---------------------------------------------------------------------------

def test_read_output_returns_empty_when_already_exited():
    """read_output returns b'' immediately when _exited is True."""
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"])
        wrapper._exited = True
        result = wrapper.read_output(timeout=0.01)
    assert result == b""


# ---------------------------------------------------------------------------
# Unit: ChildProcessError in waitpid sets exited + exit_code = -1
# ---------------------------------------------------------------------------

def test_read_output_child_process_error():
    """ChildProcessError from waitpid marks wrapper as exited with code -1."""
    on_exit = MagicMock()
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"], on_exit=on_exit)

    with patch("os.waitpid", side_effect=ChildProcessError("gone")), \
         patch("select.select", return_value=([], [], [])):
        result = wrapper.read_output(timeout=0.01)

    assert wrapper._exited is True
    assert wrapper._exit_code == -1
    on_exit.assert_called_once_with(-1)
    assert result == b""


# ---------------------------------------------------------------------------
# Unit: OSError on os.read (e.g. EIO when PTY closed)
# ---------------------------------------------------------------------------

def test_read_output_oserror_on_read():
    """OSError from os.read marks exited and returns b''."""
    on_exit = MagicMock()
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"], on_exit=on_exit)

    with patch("os.waitpid", return_value=(0, 0)), \
         patch("select.select", return_value=([42], [], [])), \
         patch("os.read", side_effect=OSError("EIO")):
        result = wrapper.read_output(timeout=0.1)

    assert wrapper._exited is True
    assert wrapper._exit_code == -1
    on_exit.assert_called_once_with(-1)
    assert result == b""


# ---------------------------------------------------------------------------
# Unit: on_output fired when chunk received
# ---------------------------------------------------------------------------

def test_read_output_fires_on_output():
    """on_output callback receives chunk bytes."""
    on_output = MagicMock()
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"], on_output=on_output)

    with patch("os.waitpid", return_value=(0, 0)), \
         patch("select.select", return_value=([42], [], [])), \
         patch("os.read", return_value=b"hello\r\n"):
        result = wrapper.read_output(timeout=0.1)

    on_output.assert_called_once_with(b"hello\r\n")
    assert result == b"hello\r\n"


# ---------------------------------------------------------------------------
# Unit: on_exit not double-fired
# ---------------------------------------------------------------------------

def test_on_exit_not_double_fired():
    """on_exit fires exactly once even across multiple read_output calls."""
    on_exit = MagicMock()
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"], on_exit=on_exit)

    # First call: child exits, no data ready
    with patch("os.waitpid", return_value=(99999, 0)), \
         patch("os.waitstatus_to_exitcode", return_value=0), \
         patch("select.select", return_value=([], [], [])):
        wrapper.read_output(timeout=0.01)

    # Second call: already exited
    wrapper.read_output(timeout=0.01)

    on_exit.assert_called_once_with(0)


# ---------------------------------------------------------------------------
# Unit: SIGWINCH handler
# ---------------------------------------------------------------------------

def test_sigwinch_handler_no_crash():
    """_handle_sigwinch runs without raising even when ioctl may fail."""
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"])

    # Should not raise regardless of terminal state
    try:
        wrapper._handle_sigwinch(signal.SIGWINCH, None)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"_handle_sigwinch raised unexpectedly: {exc}")


def test_sigwinch_handler_forwards_resize():
    """_handle_sigwinch calls fcntl.ioctl with TIOCSWINSZ on master_fd."""
    with patch("pty.fork", return_value=(99999, 42)), \
         patch("fcntl.fcntl"), \
         patch("signal.signal"), \
         patch("os.close"):
        wrapper = PTYWrapper(["echo", "hello"])

    import struct
    import termios
    fake_winsize = struct.pack("HHHH", 24, 80, 0, 0)

    with patch("fcntl.ioctl") as mock_ioctl, \
         patch("termios.tcgetwinsize", return_value=(24, 80), create=True):
        wrapper._handle_sigwinch(signal.SIGWINCH, None)

    # ioctl should be called with TIOCSWINSZ
    calls = mock_ioctl.call_args_list
    tiocswinsz_calls = [c for c in calls if len(c.args) >= 2 and c.args[1] == termios.TIOCSWINSZ]
    assert len(tiocswinsz_calls) == 1


# ---------------------------------------------------------------------------
# Integration: wrap echo command — on_output receives output bytes
# ---------------------------------------------------------------------------

def test_echo_integration():
    """
    PTYWrapper wraps 'echo hello'.
    Drain read_output until on_exit fires — verify on_output received b'hello'.
    """
    received: list[bytes] = []
    exit_codes: list[int] = []

    def on_output(chunk: bytes) -> None:
        received.append(chunk)

    def on_exit(code: int) -> None:
        exit_codes.append(code)

    wrapper = PTYWrapper(["echo", "hello"], on_output=on_output, on_exit=on_exit)

    deadline = time.monotonic() + 5.0
    while not exit_codes and time.monotonic() < deadline:
        wrapper.read_output(timeout=0.1)

    combined = b"".join(received)
    assert b"hello" in combined, f"Expected b'hello' in output, got {combined!r}"
    assert exit_codes == [0], f"Expected exit code 0, got {exit_codes}"
