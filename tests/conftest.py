"""Global pytest configuration for agentflow tests."""
import os
import pytest


@pytest.fixture(autouse=True)
def clear_session_id():
    """Automatically clear AGENTFLOW_SESSION_ID for all tests.

    Many tests assume a root-level tasks_in_flight.json path, not a SID-scoped path.
    This fixture ensures tests run with an empty SID by default, maintaining backward
    compatibility with existing tests while allowing explicit SID-setting tests to
    override it.
    """
    # Save original value
    original_sid = os.environ.get("AGENTFLOW_SESSION_ID")

    # Clear it for the test
    os.environ.pop("AGENTFLOW_SESSION_ID", None)

    yield

    # Restore original value
    if original_sid is not None:
        os.environ["AGENTFLOW_SESSION_ID"] = original_sid
