"""Test oracle task-filing write gate enforcement."""


def test_oracle_cannot_file_task_without_proposing_round_placement():
    """Filing a new task without proposing round placement is blocked by gate wording."""
    oracle_path = "commands/claude/oracle.md"

    with open(oracle_path, "r") as f:
        content = f.read()

    assert "Task-filing duplicate check" in content, "Task-filing section must exist"

    task_filing_start = content.find("### Task-filing duplicate check")
    assert task_filing_start != -1, "Task-filing section not found"

    task_filing_end = content.find("**tasks.json schema", task_filing_start)
    if task_filing_end == -1:
        task_filing_end = content.find("### ", task_filing_start + 1)
    if task_filing_end == -1:
        task_filing_end = len(content)

    task_filing_section = content[task_filing_start:task_filing_end]

    has_gate = (
        ("round placement" in task_filing_section.lower() or
         "proposed round" in task_filing_section.lower()) and
        ("write" in task_filing_section.lower() or "Do NOT" in task_filing_section)
    )
    assert has_gate, "Task-filing section must include rule requiring round placement proposal before write"


def test_oracle_requires_user_confirmation_before_tasks_json_write():
    """User confirmation on round order is captured before tasks.json write proceeds."""
    oracle_path = "commands/claude/oracle.md"

    with open(oracle_path, "r") as f:
        content = f.read()

    task_filing_start = content.find("### Task-filing duplicate check")
    assert task_filing_start != -1, "Task-filing section not found"

    task_filing_end = content.find("**tasks.json schema", task_filing_start)
    if task_filing_end == -1:
        task_filing_end = content.find("### ", task_filing_start + 1)
    if task_filing_end == -1:
        task_filing_end = len(content)

    task_filing_section = content[task_filing_start:task_filing_end]

    has_confirmation_requirement = (
        "user" in task_filing_section.lower() and
        ("confirm" in task_filing_section.lower() or "agreement" in task_filing_section.lower()) and
        ("write" in task_filing_section.lower() or "tasks.json" in task_filing_section)
    )
    assert has_confirmation_requirement, "Task-filing section must require user confirmation before write"


def test_oracle_md_size_constraint():
    """Oracle.md must remain under 150 lines."""
    oracle_path = "commands/claude/oracle.md"

    with open(oracle_path, "r") as f:
        lines = f.readlines()

    line_count = len(lines)
    assert line_count <= 150, f"oracle.md exceeds 150 lines ({line_count} lines)"
