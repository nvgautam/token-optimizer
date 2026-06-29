"""PTY shell I/O interception wrapper.

Forks a child process under a PTY, relays I/O via read_output/write_input,
and fires on_output/on_exit callbacks. stdlib-only — zero LLM calls.
"""
import fcntl
import os
import pty
import select
import signal
import struct
import termios
from typing import Callable, Optional


class PTYError(Exception):
    """Raised when PTY fork or setup fails."""


class PTYWrapper:
    """Wraps a command under a PTY for I/O interception.

    Args:
        command: Command as list[str] — never passed through shell.
        on_output: Called with each bytes chunk read from the child PTY.
        on_exit: Called with the child exit code when the process exits.
    """

    def __init__(
        self,
        command: list,
        on_output: Optional[Callable[[bytes], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._command = command
        self._on_output = on_output
        self._on_exit = on_exit
        self._exited = False
        self._exit_code: Optional[int] = None

        try:
            child_pid, master_fd = pty.fork()
        except OSError as exc:
            raise PTYError(str(exc)) from exc

        if child_pid == 0:
            # Child process — exec the command (no shell=True)
            os.execvp(command[0], command)
            # execvp replaces the process; reaching here means exec failed
            os._exit(127)

        # Parent process
        self.master_fd: int = master_fd
        self.child_pid: int = child_pid

        # Set master_fd non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Forward terminal resize (SIGWINCH) to child
        signal.signal(signal.SIGWINCH, self._handle_sigwinch)
        # Sync actual terminal size immediately so child doesn't start with OS default
        self._sync_winsize()

    # ------------------------------------------------------------------
    # Signal handler
    # ------------------------------------------------------------------

    def _sync_winsize(self) -> None:
        """Push the outer terminal's current window size into the PTY master."""
        try:
            packed = termios.tcgetwinsize(0) if hasattr(termios, "tcgetwinsize") else None
            if packed is None:
                buf = b"\x00" * 8
                result = fcntl.ioctl(1, termios.TIOCGWINSZ, buf)
                rows, cols, _, _ = struct.unpack("HHHH", result)
            else:
                rows, cols = packed
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except Exception:  # noqa: BLE001
            pass

    def _handle_sigwinch(self, signum: int, frame) -> None:  # noqa: ARG002
        """Forward terminal window resize to child PTY."""
        self._sync_winsize()

    # ------------------------------------------------------------------
    # I/O methods
    # ------------------------------------------------------------------

    def read_output(self, timeout: float = 1.0) -> bytes:
        """Read available bytes from child PTY with timeout.

        Calls on_output callback with each chunk read. When child exits,
        calls on_exit callback with exit code. Returns bytes read (may be
        empty on timeout or after child exit).
        """
        if self._exited:
            return b""

        # Check if child has exited (non-blocking)
        try:
            pid, status = os.waitpid(self.child_pid, os.WNOHANG)
            if pid == self.child_pid:
                self._exited = True
                self._exit_code = os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            self._exited = True
            self._exit_code = -1

        # Drain any remaining output even after exit
        ready, _, _ = select.select([self.master_fd], [], [], timeout)
        if not ready:
            if self._exited and self._on_exit is not None:
                self._on_exit(self._exit_code)
                # Prevent double-firing
                self._on_exit = None
            return b""

        try:
            chunk = os.read(self.master_fd, 4096)
        except OSError:
            chunk = b""
            self._exited = True
            if self._exit_code is None:
                self._exit_code = -1

        if chunk and self._on_output is not None:
            self._on_output(chunk)

        if self._exited and self._on_exit is not None:
            self._on_exit(self._exit_code)
            self._on_exit = None

        return chunk

    def write_input(self, text: str) -> None:
        """Write UTF-8 encoded text to child PTY stdin."""
        os.write(self.master_fd, text.encode("utf-8"))
