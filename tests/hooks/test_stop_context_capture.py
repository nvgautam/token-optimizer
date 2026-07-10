"""Tests for stop_context_capture.py Stop hook."""
from __future__ import annotations
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch


class TestComputeFill(unittest.TestCase):

    def _import(self):
        from agentflow.hooks.stop_context_capture import compute_fill
        return compute_fill

    def test_compute_fill_sums_all_three_fields(self):
        compute_fill = self._import()
        usage = {
            "input_tokens": 1,
            "cache_creation_input_tokens": 1060,
            "cache_read_input_tokens": 70990,
            "output_tokens": 360,
        }
        self.assertEqual(compute_fill(usage), 1 + 1060 + 70990)

    def test_compute_fill_handles_missing_fields(self):
        compute_fill = self._import()
        self.assertEqual(compute_fill({}), 0)
        self.assertEqual(compute_fill({"input_tokens": 5}), 5)
        self.assertEqual(compute_fill({"cache_read_input_tokens": 100}), 100)


class TestExtractFillFromTranscript(unittest.TestCase):

    def _import(self):
        from agentflow.hooks.stop_context_capture import extract_fill_from_transcript
        return extract_fill_from_transcript

    def _write_jsonl(self, tmpdir: str, lines: list) -> str:
        path = pathlib.Path(tmpdir) / "transcript.jsonl"
        path.write_text(
            "\n".join(json.dumps(line) for line in lines) + "\n",
            encoding="utf-8",
        )
        return str(path)

    def test_extract_fill_finds_last_assistant_entry(self):
        extract_fill_from_transcript = self._import()
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = [
                {"type": "human", "message": {}},
                {
                    "type": "assistant",
                    "message": {
                        "usage": {
                            "input_tokens": 10,
                            "cache_read_input_tokens": 100,
                            "cache_creation_input_tokens": 50,
                        }
                    },
                },
                {"type": "human", "message": {}},
                {
                    "type": "assistant",
                    "message": {
                        "usage": {
                            "input_tokens": 1,
                            "cache_read_input_tokens": 70990,
                            "cache_creation_input_tokens": 1060,
                        }
                    },
                },
            ]
            path = self._write_jsonl(tmpdir, lines)
            result = extract_fill_from_transcript(path)
            # Must return last assistant entry, not first
            self.assertEqual(result, 1 + 70990 + 1060)

    def test_extract_fill_returns_none_when_no_assistant_entry(self):
        extract_fill_from_transcript = self._import()
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = [{"type": "human", "message": {}}]
            path = self._write_jsonl(tmpdir, lines)
            result = extract_fill_from_transcript(path)
            self.assertIsNone(result)

    def test_extract_fill_skips_entries_without_usage(self):
        extract_fill_from_transcript = self._import()
        with tempfile.TemporaryDirectory() as tmpdir:
            lines = [
                {"type": "assistant", "message": {}},  # no usage key
                {
                    "type": "assistant",
                    "message": {
                        "usage": {
                            "input_tokens": 5,
                            "cache_read_input_tokens": 200,
                            "cache_creation_input_tokens": 0,
                        }
                    },
                },
            ]
            path = self._write_jsonl(tmpdir, lines)
            result = extract_fill_from_transcript(path)
            self.assertEqual(result, 205)

    def test_extract_fill_returns_none_for_nonexistent_file(self):
        extract_fill_from_transcript = self._import()
        result = extract_fill_from_transcript("/nonexistent/path/transcript.jsonl")
        self.assertIsNone(result)


class TestMain(unittest.TestCase):

    def _call_main(self, payload_str: str, env_overrides: dict | None = None):
        from agentflow.hooks import stop_context_capture
        env = env_overrides or {}
        with patch.dict(os.environ, env):
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.read.return_value = payload_str
                with self.assertRaises(SystemExit) as ctx:
                    stop_context_capture.main()
        return ctx.exception.code

    def test_main_writes_context_fill_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript_path = pathlib.Path(tmpdir) / "transcript.jsonl"
            transcript_path.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "usage": {
                                "input_tokens": 1,
                                "cache_read_input_tokens": 70000,
                                "cache_creation_input_tokens": 1000,
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            project_dir = pathlib.Path(tmpdir) / "project"
            project_dir.mkdir()

            payload = json.dumps({"transcript_path": str(transcript_path)})
            code = self._call_main(
                payload,
                env_overrides={"CLAUDE_PROJECT_DIR": str(project_dir)},
            )
            self.assertEqual(code, 0)

            fill_path = project_dir / ".agentflow" / "context_fill.json"
            self.assertTrue(fill_path.exists())
            data = json.loads(fill_path.read_text(encoding="utf-8"))
            self.assertEqual(data["fill_tokens"], 1 + 70000 + 1000)
            self.assertIn("ts", data)
            self.assertIsInstance(data["ts"], float)

    def test_main_exits_zero_on_missing_transcript(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = pathlib.Path(tmpdir) / "project"
            project_dir.mkdir()
            payload = json.dumps({"transcript_path": "/nonexistent/transcript.jsonl"})
            code = self._call_main(
                payload,
                env_overrides={"CLAUDE_PROJECT_DIR": str(project_dir)},
            )
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
