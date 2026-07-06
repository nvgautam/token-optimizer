import sys
import time
from agentflow.shell.pty_wrapper import PTYWrapper


def test_pty_carriage_return_injection():
    """Spawn a real subprocess running a readline loop, write winning byte sequence, assert unblocks."""
    received = []

    def on_output(data):
        received.append(data)

    # Spawn python readline echo process
    command = [sys.executable, "-c", "import sys; print(f'ECHO:{input()}')"]
    wrapper = PTYWrapper(command, on_output=on_output)

    # Wait for process initialization
    time.sleep(0.5)

    # Write input + carriage return (\r)
    wrapper.write_input("hello_inject")
    wrapper.write_input("\r")

    # Read output and wait for echo
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        wrapper.read_output(timeout=0.1)
        if b"ECHO:hello_inject" in b"".join(received):
            break

    combined = b"".join(received)
    assert b"ECHO:hello_inject" in combined, f"Carriage return failed to submit. Received so far: {combined!r}"
