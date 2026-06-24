"""Assembles minimal context bundles for worker agents."""

import re
from dataclasses import dataclass
from pathlib import Path

from agentflow.config.schema import AgentFlowConfig
from agentflow.telemetry.metrics import emit_metric

MAX_BUNDLE_CHARS = 200_000


@dataclass
class ContextBundle:
    task_id: str
    output_path: Path
    token_estimate: int
    content: str


def build_context(task: dict, project_root: Path, config: AgentFlowConfig) -> ContextBundle:
    """Assemble context bundle and write to .agentflow/context/<task-id>.md."""
    task_id = task["task_id"]
    sections = []

    # 1. TASK
    sections.append(_section("TASK", [
        f"Task ID: {task_id}",
        f"Title: {task.get('title', '')}",
        f"Description: {task.get('description', '')}",
        f"Acceptance criteria: {task.get('acceptance_criteria', task.get('accepts_criteria', ''))}",
    ]))

    # 2. OWNS
    owns = task.get("owns", [])
    sections.append(_section("OWNS", owns or ["(none)"]))

    # 3. READS
    reads = task.get("reads", [])
    sections.append(_section("READS", reads or ["(none)"]))

    # 4. CONTRACTS — content of stub files that exist
    contract_lines = []
    for path_str in task.get("contracts", []):
        stub_path = project_root / path_str
        if stub_path.exists():
            contract_lines.append(f"--- {path_str} ---")
            contract_lines.append(stub_path.read_text())
    if contract_lines:
        sections.append(_section("CONTRACTS", contract_lines))

    # 5. ARCHITECTURE — relevant section only
    arch_path = project_root / "architecture.md"
    if arch_path.exists():
        arch_content = arch_path.read_text()
        anchor = task.get("context_section")
        arch_section = _extract_arch_section(arch_content, anchor)
        sections.append(_section("ARCHITECTURE", [arch_section]))

    # 6. TEST STRATEGY
    strategy_path = project_root / ".agentflow" / "test_strategy.md"
    if strategy_path.exists():
        sections.append(_section("TEST STRATEGY", [strategy_path.read_text()]))

    # 7. TEST SCENARIOS
    unit_scenarios = task.get("test_requirements", {}).get("unit", [])
    if unit_scenarios:
        sections.append(_section("TEST SCENARIOS", unit_scenarios))

    # 8. SECURITY CONSTRAINTS
    constraints = task.get("security_constraints", [])
    sections.append(_section("SECURITY CONSTRAINTS", constraints or ["(none)"]))

    # 9. CONFIG
    sections.append(_section("CONFIG", [
        f"Worker model: {config.models.worker}",
        f"Coverage threshold: {config.testing.coverage_threshold}%",
        f"File limits — implementation: {config.file_limits.implementation} lines, "
        f"tests: {config.file_limits.tests} lines",
        f"Token budget per worker: {config.token_budget.per_worker}",
    ]))

    content = "\n\n".join(sections)

    if len(content) > MAX_BUNDLE_CHARS:
        raise ValueError(
            f"Context bundle for {task_id} exceeds {MAX_BUNDLE_CHARS} chars "
            f"({len(content)} chars). Reduce task scope or split the task."
        )

    output_path = project_root / ".agentflow" / "context" / f"{task_id}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    token_estimate = len(content) // 4
    emit_metric("worker.context_built", task_id=task_id, tokens_in=token_estimate, status="ok")

    return ContextBundle(
        task_id=task_id,
        output_path=output_path,
        token_estimate=token_estimate,
        content=content,
    )


def _extract_arch_section(arch_content: str, anchor: str | None) -> str:
    """Extract the section of architecture.md matching anchor fragment."""
    if not anchor:
        return arch_content

    # Parse fragment from "architecture.md#section-name"
    fragment = anchor.split("#", 1)[-1] if "#" in anchor else ""
    if not fragment:
        return arch_content

    lines = arch_content.splitlines()
    start_idx = None
    start_level = None

    for i, line in enumerate(lines):
        match = re.match(r'^(#{1,6})\s+(.+)', line)
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            slug = _slugify(heading_text)
            if slug == fragment:
                start_idx = i
                start_level = level
                break

    if start_idx is None:
        return arch_content

    # Collect until next heading of same or higher level
    result = [lines[start_idx]]
    for line in lines[start_idx + 1:]:
        match = re.match(r'^(#{1,6})\s+', line)
        if match and len(match.group(1)) <= start_level:
            break
        result.append(line)

    return "\n".join(result)


def _slugify(text: str) -> str:
    """Convert heading text to anchor slug (GitHub-style)."""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = text.strip('-')
    return text


def _section(title: str, items: list[str]) -> str:
    header = f"## {title}"
    body = "\n".join(str(item) for item in items)
    return f"{header}\n\n{body}"
