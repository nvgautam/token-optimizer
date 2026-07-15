"""Tests for sync_session_type — T-227: deterministic session_type detection."""
import json
import os
import pathlib
from unittest.mock import patch, MagicMock

import pytest

from agentflow.shell.threshold_sync import sync_session_type, apply_session_threshold
from tests.shell.conftest import make_manager


class TestSyncSessionType:
    """TDD test suite for deterministic session_type routing."""

    def test_sid_present_sid_file_has_oracle(self, tmp_path):
        """When SID set and SID file has oracle → type set to oracle, root NOT read."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()
            sid_dir = agentflow_dir / "sessions" / "test-sid-1"
            sid_dir.mkdir(parents=True)

            # Write SID file with oracle
            sid_file = sid_dir / "session_state.json"
            sid_file.write_text(json.dumps({"session_type": "oracle"}))

            # Create root file with different type (should NOT be read)
            root_file = agentflow_dir / "session_state.json"
            root_file.write_text(json.dumps({"session_type": "orchestrator"}))

            os.environ["AGENTFLOW_SESSION_ID"] = "test-sid-1"
            try:
                manager.session_type = None
                sync_session_type(manager)
                assert manager.session_type == "oracle"
            finally:
                if "AGENTFLOW_SESSION_ID" in os.environ:
                    del os.environ["AGENTFLOW_SESSION_ID"]

    def test_sid_present_sid_file_has_orchestrator(self, tmp_path):
        """When SID set and SID file has orchestrator → type set to orchestrator, root NOT read."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()
            sid_dir = agentflow_dir / "sessions" / "test-sid-2"
            sid_dir.mkdir(parents=True)

            # Write SID file with orchestrator
            sid_file = sid_dir / "session_state.json"
            sid_file.write_text(json.dumps({"session_type": "orchestrator"}))

            # Create root file with different type (should NOT be read)
            root_file = agentflow_dir / "session_state.json"
            root_file.write_text(json.dumps({"session_type": "oracle"}))

            os.environ["AGENTFLOW_SESSION_ID"] = "test-sid-2"
            try:
                manager.session_type = None
                sync_session_type(manager)
                assert manager.session_type == "orchestrator"
            finally:
                if "AGENTFLOW_SESSION_ID" in os.environ:
                    del os.environ["AGENTFLOW_SESSION_ID"]

    def test_sid_present_sid_file_absent(self, tmp_path):
        """When SID set and no SID file → session_type unchanged, root NOT read."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()

            # Create root file (should NOT be read)
            root_file = agentflow_dir / "session_state.json"
            root_file.write_text(json.dumps({"session_type": "orchestrator"}))

            os.environ["AGENTFLOW_SESSION_ID"] = "test-sid-missing"
            try:
                manager.session_type = None
                sync_session_type(manager)
                # Session type should remain None, NOT picked up from root
                assert manager.session_type is None
            finally:
                if "AGENTFLOW_SESSION_ID" in os.environ:
                    del os.environ["AGENTFLOW_SESSION_ID"]

    def test_sid_present_sid_file_invalid_json(self, tmp_path):
        """When SID set and SID file has invalid JSON → audit logged, root NOT read."""
        manager, _, _ = make_manager()
        manager._log_audit = MagicMock()  # Mock audit logging

        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()
            sid_dir = agentflow_dir / "sessions" / "test-sid-3"
            sid_dir.mkdir(parents=True)

            # Write SID file with invalid JSON
            sid_file = sid_dir / "session_state.json"
            sid_file.write_text("{invalid json")

            # Create root file (should NOT be read)
            root_file = agentflow_dir / "session_state.json"
            root_file.write_text(json.dumps({"session_type": "orchestrator"}))

            os.environ["AGENTFLOW_SESSION_ID"] = "test-sid-3"
            try:
                manager.session_type = None
                sync_session_type(manager)
                # Session type should remain None, NOT picked up from root
                assert manager.session_type is None
                # Audit error should be logged for invalid JSON
                manager._log_audit.assert_called()
                audit_call = manager._log_audit.call_args[0][0]
                assert audit_call.get("event") == "sync_session_type_sid_read_error"
            finally:
                if "AGENTFLOW_SESSION_ID" in os.environ:
                    del os.environ["AGENTFLOW_SESSION_ID"]

    def test_sid_present_sid_file_unknown_type(self, tmp_path):
        """When SID set and SID file has unknown type → session_type unchanged, root NOT read."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()
            sid_dir = agentflow_dir / "sessions" / "test-sid-4"
            sid_dir.mkdir(parents=True)

            # Write SID file with unknown type
            sid_file = sid_dir / "session_state.json"
            sid_file.write_text(json.dumps({"session_type": "unknown"}))

            # Create root file (should NOT be read)
            root_file = agentflow_dir / "session_state.json"
            root_file.write_text(json.dumps({"session_type": "oracle"}))

            os.environ["AGENTFLOW_SESSION_ID"] = "test-sid-4"
            try:
                manager.session_type = None
                sync_session_type(manager)
                # Session type should remain None, NOT picked up from root
                assert manager.session_type is None
            finally:
                if "AGENTFLOW_SESSION_ID" in os.environ:
                    del os.environ["AGENTFLOW_SESSION_ID"]

    def test_sid_absent_root_session_state_has_oracle(self, tmp_path):
        """When no SID and root session_state.json has oracle → type set to oracle."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()

            # Create root file with oracle
            root_file = agentflow_dir / "session_state.json"
            root_file.write_text(json.dumps({"session_type": "oracle"}))

            # No AGENTFLOW_SESSION_ID set
            if "AGENTFLOW_SESSION_ID" in os.environ:
                del os.environ["AGENTFLOW_SESSION_ID"]

            manager.session_type = None
            sync_session_type(manager)
            assert manager.session_type == "oracle"

    def test_sid_absent_root_session_type_file(self, tmp_path):
        """When no SID and root session_type file exists → type set to orchestrator."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()

            # Create root session_type file
            root_file = agentflow_dir / "session_type"
            root_file.write_text("orchestrator")

            # No AGENTFLOW_SESSION_ID set
            if "AGENTFLOW_SESSION_ID" in os.environ:
                del os.environ["AGENTFLOW_SESSION_ID"]

            manager.session_type = None
            sync_session_type(manager)
            assert manager.session_type == "orchestrator"

    def test_sid_absent_no_files(self, tmp_path):
        """When no SID and no root files → session_type unchanged."""
        manager, _, _ = make_manager()
        with patch.object(pathlib.Path, 'cwd', return_value=tmp_path):
            agentflow_dir = tmp_path / ".agentflow"
            agentflow_dir.mkdir()

            # No root files, no SID
            if "AGENTFLOW_SESSION_ID" in os.environ:
                del os.environ["AGENTFLOW_SESSION_ID"]

            manager.session_type = None
            sync_session_type(manager)
            assert manager.session_type is None
