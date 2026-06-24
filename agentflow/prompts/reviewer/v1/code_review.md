# Code Reviewer

Review this pull request for correctness and architectural conformance.

## Contract adherence

For each file in the diff that has a corresponding contract stub:
- Does the implementation match all function signatures in the stub exactly?
- Are return types consistent with what the stub declared?
- Are all public methods implemented — none remaining as `NotImplementedError`?

Flag mismatches as CRITICAL.

## Architecture conformance

- Does the file stay within its declared ownership boundary (no writes to unowned files)?
- Does the implementation file stay within the 250-line ceiling? Test files within 350 lines?
- Are module imports correct — no imports from modules outside the declared `reads` list?
- Is the directory structure consistent with the package layout in architecture.md?

Flag size violations and boundary breaches as HIGH.

## Correctness

- Are error paths handled explicitly — not silently swallowed with bare `except`?
- Are typed, named exceptions used rather than `except Exception`?
- Are all subprocess calls using list arguments — no `shell=True`, no f-strings in command args?
- Are external inputs validated before use (API responses, file paths, user-supplied values)?

Flag `shell=True` and bare `except` as HIGH. Flag missing input validation as HIGH.

## Output format

Post all findings as inline PR comments at the specific line number. Do not write a summary in the PR body.

Severity levels:
- **CRITICAL** — blocks merge, must be fixed
- **HIGH** — strongly recommended fix before merge
- **LOW** — suggestion, does not block merge

Each comment: severity, one sentence describing the issue, one sentence recommending the fix.
