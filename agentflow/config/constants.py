"""Central constants for AgentFlow config, shell, hooks, and session management.

This file centralizes all hardcoded string literals used across the codebase to avoid
magic values and reduce maintenance overhead.
"""

from __future__ import annotations

# Encoding
UTF8 = "utf-8"

# Environment Variables
ENV_SESSION_ID = "AGENTFLOW_SESSION_ID"
ENV_PROJECT_ROOT = "AGENTFLOW_PROJECT_ROOT"
ENV_CLAUDE_PROJECT_DIR = "CLAUDE_PROJECT_DIR"

# Directory names
DIR_AGENTFLOW = ".agentflow"

# Core filenames
FILE_SESSION_STATE = "session_state.json"
FILE_CURRENT_ROUND = "current_round.json"
FILE_TASKS_IN_FLIGHT = "tasks_in_flight.json"
FILE_HANDOFF_COMPLETE = "handoff_complete.json"
FILE_TASK_COMPLETE = "task_complete.json"
FILE_CLEAR_SIGNAL = "clear_signal"
FILE_HANDOFF_DISABLED = "handoff_disabled"
FILE_VERBOSITY_AB_ARM = "verbosity_ab_arm.txt"
FILE_TASKS_JSON = "tasks.json"
FILE_EXECUTION_PLAN = "execution_plan.md"
FILE_ADDENDUMS_ARCHIVE = "addendums_archive.md"
FILE_CONTEXT_FILL = "context_fill.json"
FILE_CONFIG_TOML = "config.toml"
FILE_HOOK_DRAIN_DEBUG = "hook_drain_debug.jsonl"

# Lock files
LOCK_TASKS_JSON = "tasks.json.lock"
LOCK_EXECUTION_PLAN = "execution_plan.md.lock"
LOCK_ADDENDUMS_ARCHIVE = "addendums_archive.md.lock"

# Session types
SESSION_TYPE_ORCHESTRATOR = "orchestrator"
SESSION_TYPE_ORACLE = "oracle"
SESSION_TYPE_UNKNOWN = "unknown"

# Tools
TOOL_BASH = "Bash"
TOOL_WRITE = "Write"
TOOL_EDIT = "Edit"

# Triggers
TRIGGER_AUTO = "auto"

# Config keys
CFG_HANDOFF_PRIMARY_TOKENS = "handoff_primary_tokens"
CFG_RESTART_DELAY_SECONDS = "restart_delay_seconds"
CFG_SHELL = "shell"
CFG_ORACLE_THRESHOLD_TOKENS = "oracle_threshold_tokens"
CFG_ORACLE_CONSENT_THRESHOLD_TOKENS = "oracle_consent_threshold_tokens"

# Hook metadata fields
HOOK_FIELD_HOOK = "hook"
HOOK_FIELD_EVENT = "event"
HOOK_FIELD_ERROR = "error"
HOOK_FIELD_TS = "ts"

# Common dictionary keys
KEY_TASKS = "tasks"
KEY_TASK_ID = "task_id"
KEY_STATUS = "status"
KEY_SESSION_TYPE = "session_type"
KEY_TASK_IDS = "task_ids"
KEY_FILE_PATH = "file_path"
KEY_CONTENT = "content"
KEY_TOOL_NAME = "tool_name"
KEY_TOOL_INPUT = "tool_input"
KEY_TOOL_RESPONSE = "tool_response"
KEY_TRANSCRIPT_PATH = "transcript_path"
KEY_FILL_TOKENS = "fill_tokens"
KEY_TS = "ts"
KEY_SID = "sid"
KEY_PROMPT = "prompt"

# Status values
STATUS_PENDING = "pending"
STATUS_COMPLETE = "complete"
STATUS_CANCELLED = "cancelled"
STATUS_SKIPPED = "skipped"

# Hook names
HOOK_USER_PROMPT_SUBMIT = "user_prompt_submit"
HOOK_POST_TOOL_USE = "post_tool_use"
