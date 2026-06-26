# Context Bundle Format

Your opening message is your complete context bundle. Read all sections before writing any code.
The bundle is assembled by `context_builder.py` and token-counted before delivery. If it exceeds
50 000 tokens, a telemetry warning is emitted — the reads list may be too broad.

---

## TASK

What you are building and the acceptance criteria you must satisfy. The acceptance criteria is the
definition of done — if it is not met, the PR must not be opened.

---

## OWNS

Files you are responsible for creating or modifying. Do not touch any file not on this list. If a
file needs to exist but is missing from your list, it belongs to another task — escalate via the
blockers file.

---

## READS (Dependencies)

Files included for reference. Their full contents are already inlined in this bundle.

**Do not re-read them via tool.** Doing so wastes tokens on content already present. Every file
listed here is available in the sections that follow — you never need to fetch them again.

If you need to understand an interface, read the contract stub in this section, not the source file.

---

## CONTRACTS

Interface stubs already committed to the repository. Function signatures, class names, and module
paths are frozen. Your implementation must satisfy them exactly. Do not change signatures.

---

## ARCHITECTURE

The relevant anchor section of this project's architecture document — not the full document.
The `context_section` field (e.g. `architecture.md#context-bundle`) identifies which section was
extracted. Understand the design intent before writing code. If your implementation would deviate
from the architecture, write to the blockers file instead.

---

## TEST STRATEGY

This project's testing philosophy. Follow it exactly:
- Use only the mock fixtures pre-provided; do not introduce new mocking libraries.
- Do not mock internal functions of the module under test.
- Integration tests use real dependencies (`tmp_path` for filesystem isolation).
- Coverage threshold is stated here and is a hard gate for PR creation.

---

## TEST SCENARIOS

The specific behaviours your tests must cover. The skeleton test file already has method stubs for
each. Make every one pass.

---

## SECURITY CONSTRAINTS

Non-negotiable requirements. Each must be satisfied in your implementation. Consult testing_guide.md
for how to verify security properties in tests.

---

## CONFIG

Active configuration snapshot for this task run. Fields:

| Field | Meaning |
|---|---|
| `model` | LLM model identifier used for this worker session |
| `coverage_threshold` | Minimum line coverage percentage required before opening a PR |
| `max_file_lines` | Hard limit on lines per implementation file (default: 250) |
| `max_test_lines` | Hard limit on lines per test file (default: 350) |
| `max_prompt_lines` | Hard limit on lines per prompt file (default: 150) |

Do not exceed these limits. If a file would breach a limit, split it or escalate.
