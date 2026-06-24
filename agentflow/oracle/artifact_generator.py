"""Artifact generator — calls Anthropic API and writes project artifacts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import anthropic

from agentflow.config.schema import AgentFlowConfig
from agentflow.oracle.contract_generator import generate_contracts


def _load_generation_prompt() -> str:
    try:
        from importlib.resources import files
        return files("agentflow.prompts.oracle.v1").joinpath("generation.md").read_text()
    except Exception:
        fallback = Path(__file__).parent.parent / "prompts" / "oracle" / "v1" / "generation.md"
        return fallback.read_text()


def _validate_tasks(tasks: list[dict], config: AgentFlowConfig) -> None:
    """Raise ValueError on ownership conflicts or size violations."""
    seen: dict[str, str] = {}
    for task in tasks:
        task_id = task.get("task_id", "?")
        for owned in task.get("owns", []):
            if owned in seen:
                raise ValueError(
                    f"Ownership conflict: '{owned}' claimed by both "
                    f"'{seen[owned]}' and '{task_id}'"
                )
            seen[owned] = task_id

        estimated = task.get("estimated_lines", 0)
        owns_files = task.get("owns", [])
        for f in owns_files:
            if f.startswith("tests/"):
                ceiling = config.file_limits.tests
            elif "prompts/" in f:
                ceiling = config.file_limits.prompts
            elif "stubs/" in f:
                ceiling = config.file_limits.stubs
            else:
                ceiling = config.file_limits.implementation
            if estimated > ceiling:
                raise ValueError(
                    f"Task '{task_id}' estimated_lines={estimated} exceeds "
                    f"ceiling={ceiling} for file type"
                )


def _extract_block(text: str, lang: str) -> str | None:
    pattern = rf"```{lang}\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else None


def _write_design_session(conversation_history: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Design Session Summary\n"]
    lines.append("## Decisions Made\n")
    for turn in conversation_history:
        if turn.get("role") == "assistant":
            content = turn.get("content", "")
            # Extract bullet points or short sentences as decisions
            for line in content.splitlines():
                line = line.strip()
                if line.startswith(("- ", "* ", "**")) and len(line) > 10:
                    lines.append(f"{line}\n")
    lines.append("\n## Full Conversation\n")
    for turn in conversation_history:
        role = turn.get("role", "unknown").capitalize()
        content = turn.get("content", "")
        lines.append(f"**{role}:** {content[:500]}\n\n")
    path.write_text("".join(lines))


def _write_test_strategy(
    conversation_history: list[dict], config: AgentFlowConfig, path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(t.get("content", "") for t in conversation_history)
    lines = [
        "# Test Strategy\n\n",
        "## Coverage Thresholds\n\n",
        f"- Implementation files: {config.testing.coverage_threshold}%\n",
        f"- Integration tests required: {config.testing.require_integration_tests}\n\n",
        "## Mock Boundaries\n\n",
        "- External IO (database, HTTP, filesystem outside worktree) is mocked\n",
        "- Internal module calls are not mocked\n\n",
        "## Integration Test Scope\n\n",
        "- Tests marked integration run against real dependencies using tmp_path\n\n",
    ]
    if re.search(r'\b(gdpr|hipaa|soc.?2|pci)\b', content, re.IGNORECASE):
        lines.append("## Compliance-Driven Scenarios\n\n")
        lines.append("- Compliance constraints captured during design must have dedicated tests\n")
    path.write_text("".join(lines))


def generate_artifacts(
    conversation_history: list[dict],
    project_root: Path,
    config: AgentFlowConfig,
) -> dict:
    """Call Anthropic API to generate architecture.md and tasks.json, then write all artifacts."""
    generation_prompt = _load_generation_prompt()
    messages = list(conversation_history) + [
        {
            "role": "user",
            "content": (
                "Based on our design discussion, generate the artifacts now. "
                "Follow generation.md format exactly.\n\n"
                f"<generation_instructions>\n{generation_prompt}\n</generation_instructions>"
            ),
        }
    ]

    client = anthropic.Anthropic()
    system_prompt = (
        "You are generating project artifacts from a completed design discussion. "
        "Emit architecture.md content in a ```markdown block and tasks.json in a ```json block."
    )
    try:
        response = client.messages.create(
            model=config.models.oracle,
            max_tokens=8192,
            system=system_prompt,
            messages=messages,
        )
    except (anthropic.AuthenticationError, TypeError):
        raise EnvironmentError(
            "No credentials found. Set ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, "
            "or run `ant auth login`."
        )
    response_text = response.content[0].text

    arch_content = _extract_block(response_text, "markdown") or response_text
    tasks_json_str = _extract_block(response_text, "json")

    tasks: list[dict] = []
    if tasks_json_str:
        parsed = json.loads(tasks_json_str)
        tasks = parsed.get("tasks", parsed) if isinstance(parsed, dict) else parsed

    _validate_tasks(tasks, config)

    arch_path = project_root / "architecture.md"
    arch_path.write_text(arch_content)

    tasks_path = project_root / "tasks.json"
    tasks_path.write_text(json.dumps({"tasks": tasks}, indent=2))

    agentflow_dir = project_root / ".agentflow"
    agentflow_dir.mkdir(exist_ok=True)

    _write_design_session(conversation_history, agentflow_dir / "design_session.md")
    _write_test_strategy(conversation_history, config, agentflow_dir / "test_strategy.md")

    contract_count = 0
    for task in tasks:
        artifacts = generate_contracts(task, project_root)
        contract_count += len(artifacts.stubs) + len(artifacts.skeletons)

    return {
        "architecture_path": arch_path,
        "tasks_path": tasks_path,
        "task_count": len(tasks),
        "contract_count": contract_count,
    }
