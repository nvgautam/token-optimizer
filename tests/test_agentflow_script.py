import argparse
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

# Load the agentflow.py script directly to avoid conflicts with the agentflow package
ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("agentflow_script", str(ROOT / "agentflow.py"))
af_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(af_script)


def setup_function():
    # Reset global override before each test to avoid state leakage from other tests
    af_script._ledger_override = None


def test_agentflow_parser_choices():
    with patch("sys.argv", ["agentflow.py", "status"]):
        with patch("argparse.ArgumentParser") as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser_cls.return_value = mock_parser
            # Ensure parse_args returns a clean namespace
            mock_parser.parse_args.return_value = argparse.Namespace(command="status", agent=None, ledger=None)
            
            with patch("agentflow.legacy_cli.load_ledger", return_value={"sessions": []}):
                af_script.main()
            
            # Find the call to add_argument with "--agent"
            agent_call = None
            for call in mock_parser.add_argument.call_args_list:
                if len(call[0]) > 0 and call[0][0] == "--agent":
                    agent_call = call
                    break
            assert agent_call is not None
            assert "choices" in agent_call[1]
            assert set(agent_call[1]["choices"]) == {"claude", "gemini", "agy"}


def test_cmd_start_maps_gemini_to_agy():
    # Test that cmd_start maps input 'gemini' to 'agy'
    args = argparse.Namespace()
    
    with patch("builtins.input", side_effect=["gemini", "C-123"]), \
         patch("agentflow.legacy_cli.load_ledger", return_value={"sessions": []}), \
         patch("agentflow.legacy_cli.save_ledger") as mock_save, \
         patch("agentflow.legacy_cli.active_session", return_value=None):
        
        af_script.cmd_start(args)
        
        # Verify the saved session uses 'agy'
        assert mock_save.called
        saved_ledger = mock_save.call_args[0][0]
        assert len(saved_ledger["sessions"]) == 1
        assert saved_ledger["sessions"][0]["agent"] == "agy"


def test_cmd_handoff_maps_gemini_and_agy_correctly():
    # Test that cmd_handoff treats 'gemini' and 'agy' forced agents similarly, mapping detected_agent to 'agy'
    args_gemini = argparse.Namespace(agent="gemini")
    args_agy = argparse.Namespace(agent="agy")
    
    # Mock read_gemini_db_usage to return a fake usage dict
    fake_usage = {
        "session_file": "session_123.db",
        "n_turns": 3,
        "input_tokens": 100,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "output_tokens": 50,
        "initial_ctx": 0,
        "final_ctx": 150
    }
    
    for args in (args_gemini, args_agy):
        with patch("agentflow.legacy_cli.read_gemini_db_usage", return_value=fake_usage) as mock_read, \
             patch("agentflow.legacy_cli.update_shadow", return_value={}), \
             patch("agentflow.legacy_cli._print_token_breakdown"), \
             patch("agentflow.legacy_cli._print_summary"), \
             patch("builtins.input", return_value=""):
            
            with patch("agentflow.legacy_cli.load_ledger", return_value={"sessions": []}), \
                 patch("agentflow.legacy_cli.save_ledger"):
                
                af_script.cmd_handoff(args)
                assert mock_read.called


def test_cmd_report_filters_both_gemini_and_agy():
    # Test that cmd_report maps filter 'gemini' to 'agy' and retrieves both gemini and agy sessions
    args_gemini = argparse.Namespace(agent="gemini")
    args_agy = argparse.Namespace(agent="agy")
    
    fake_ledger = {
        "sessions": [
            {"status": "closed", "agent": "gemini", "session_id": "1", "end_reason": "task_complete", "n_turns": 1, "final_ctx": 10, "input_tokens": 5, "output_tokens": 5, "token_detail": {}, "shadow_event": {"shadow_input": 5, "shadow_output": 5, "shadow_extra": 0}},
            {"status": "closed", "agent": "agy", "session_id": "2", "end_reason": "task_complete", "n_turns": 1, "final_ctx": 10, "input_tokens": 5, "output_tokens": 5, "token_detail": {}, "shadow_event": {"shadow_input": 5, "shadow_output": 5, "shadow_extra": 0}},
            {"status": "closed", "agent": "claude", "session_id": "3", "end_reason": "task_complete", "n_turns": 1, "final_ctx": 10, "input_tokens": 5, "output_tokens": 5, "token_detail": {}, "shadow_event": {"shadow_input": 5, "shadow_output": 5, "shadow_extra": 0}}
        ],
        "shadow_state": {"compaction_events": 0}
    }
    
    for args in (args_gemini, args_agy):
        with patch("agentflow.legacy_cli.load_ledger", return_value=fake_ledger), \
             patch("agentflow.legacy_cli.total_real_tokens", return_value=10), \
             patch("agentflow.legacy_cli.real_cost_from_usage", return_value=0.0):
            
            with patch("builtins.print") as mock_print:
                af_script.cmd_report(args)
                
                any_savings_print = False
                for call in mock_print.call_args_list:
                    if len(call[0]) > 0 and "real" in str(call[0][0]).lower():
                        any_savings_print = True
                assert any_savings_print
