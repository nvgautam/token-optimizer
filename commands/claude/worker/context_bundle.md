# Context Bundle — Format Spec and Interpretation Guide

Your context bundle is a token-optimised package assembled by the orchestrator
before you are spawned. It contains everything you need; nothing you don't.

---

## Bundle Structure (sections in order)

| # | Section | Purpose |
|---|---------|---------|
| 1 | **Task brief** | Description + acceptance criteria |
| 2 | **Owned file list** | Files you may create or modify |
| 3 | **Read-only file contents** | Dependency files, pre-loaded |
| 4 | **Contract stubs** | Function signatures to implement against |
| 5 | **Architecture section** | Relevant anchor section of architecture.md only |
| 6 | **Test scenarios** | Specific test cases your suite must cover |
| 7 | **Security constraints** | Any auth, input validation, or data constraints |
| 8 | **Config snapshot** | model, coverage_threshold, file_limits |

---

## Interpretation Rules

### Task brief
Your acceptance criteria. This is your definition of done. You are finished
when every criterion in this section is met and tests pass.

### Owned file list
The only files you may write to. Writing outside this list is a scope
violation. If the task cannot be completed without touching a non-owned file,
stop and report `ESCALATE: [reason]`.

### Read-only file contents
Dependency files already included — do not re-read via tool. The full content
is embedded here. Using the Read tool on these files pays the token cost twice
for identical bytes.

### Contract stubs
Implement against these signatures exactly. If a stub is incomplete or
ambiguous, use the architecture section to resolve — do not guess.

### Architecture section
Only the relevant anchor section of architecture.md is included here, not the
full document. Never use the Read tool to load architecture.md in full; if a
section beyond the one provided is needed, add it to the ESCALATE report.

### Test scenarios
The specific scenarios your test suite must cover. Treat these as the minimum
required test coverage — you may add more, but do not omit any listed here.

### Security constraints
Honour these in both implementation and tests. Write at least one security
test per constraint listed.

### Config snapshot
Use `coverage_threshold` as your pytest `--cov` pass threshold.
Use `file_limits.implementation` (default 250 lines) as the max length for any
owned implementation file.
Use `file_limits.tests` (default 350 lines) as the max length for any test
file.

---

## Bundle Size Note

If this bundle exceeds 50K tokens, flag it as a telemetry warning — the reads
list may be too broad. Report:

```
TELEMETRY: bundle_tokens=N (exceeds 50K threshold — reads list may be too broad)
```

Include this line before your first implementation step. The orchestrator uses
this signal to trim future bundles.
