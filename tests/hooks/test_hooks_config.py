import json
from pathlib import Path

REPO = Path(__file__).parent.parent.parent
CLAUDE_SETTINGS = REPO / ".claude" / "settings.json"
GEMINI_HOOKS = REPO / ".agents" / "hooks.json"


def test_claude_settings_valid_and_complete():
    assert CLAUDE_SETTINGS.exists()
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    hooks = data.get("hooks", {})
    
    # Check UserPromptSubmit
    ups = hooks.get("UserPromptSubmit", [])
    assert len(ups) > 0
    ups_commands = [h["command"] for group in ups for h in group.get("hooks", [])]
    assert any("idx_reminder.py" in cmd for cmd in ups_commands)
    assert any("verbosity_reminder.py" in cmd for cmd in ups_commands)

    # Check PreToolUse
    ptu = hooks.get("PreToolUse", [])
    assert len(ptu) > 0
    ptu_matchers = [g["matcher"] for g in ptu]
    assert "Read" in ptu_matchers


def test_gemini_hooks_valid_and_complete():
    assert GEMINI_HOOKS.exists()
    data = json.loads(GEMINI_HOOKS.read_text(encoding="utf-8"))
    
    # Check UserPromptSubmit hooks
    idx_rem = data.get("idx-reminder", {}).get("UserPromptSubmit", [])
    assert len(idx_rem) > 0
    assert "idx_reminder.py" in idx_rem[0]["command"]

    verb_rem = data.get("verbosity-reminder", {}).get("UserPromptSubmit", [])
    assert len(verb_rem) > 0
    assert "verbosity_reminder.py" in verb_rem[0]["command"]

    # Check PreToolUse hooks
    read_chk = data.get("read-check", {}).get("PreToolUse", [])
    assert len(read_chk) > 0
    assert read_chk[0]["matcher"] == "view_file"
    assert "read_check.py" in read_chk[0]["hooks"][0]["command"]
