import json
from unittest.mock import patch
import pytest

from agentflow.hooks.user_prompt_submit import main

def test_should_prompt_consent_is_called_in_hook(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTFLOW_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTFLOW_SESSION_ID", "test-session-consent")
    
    # Write session_state.json with session_type oracle
    agentflow_dir = tmp_path / ".agentflow"
    sid_dir = agentflow_dir / "sessions" / "test-session-consent"
    sid_dir.mkdir(parents=True, exist_ok=True)
    (sid_dir / "session_state.json").write_text(json.dumps({"session_type": "oracle"}))
    
    # Write context_fill.json with tokens >= 50K
    import time
    (sid_dir / "context_fill.json").write_text(json.dumps({"fill_tokens": 55000, "ts": time.time()}))
    
    # Mock sys.stdin
    from io import StringIO
    monkeypatch.setattr("sys.stdin", StringIO(json.dumps({"prompt": "hello"})))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    
    # Mock should_prompt_consent and inject_consent_prompt
    with patch("agentflow.shell.oracle_consent.should_prompt_consent", return_value=True) as mock_should:
        with patch("agentflow.shell.oracle_consent.inject_consent_prompt") as mock_inject:
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 0
            mock_should.assert_called_once()
            mock_inject.assert_called_once()
