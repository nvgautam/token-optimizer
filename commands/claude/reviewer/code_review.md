# Architecture and Contract Review Checks

The programmatic pre-filter has already checked for `shell=True`, bare `except:`,
file sizes > 250 lines, and hardcoded secrets. Do not repeat those checks. Focus only
on the judgment calls below.

---

## 1. Contract Adherence

Verify the implementation satisfies every stub interface it was given.

Check:
- Function signatures match the stub (name, positional args, keyword args, defaults)
- Return types match the stub annotation
- Exception types raised match the stub contract (docstring or `raises` annotation)
- `NotImplementedError` stubs are fully replaced — no stub body remains in non-stub,
  non-test files

Flag any mismatch as CRITICAL.

---

## 2. Architecture Conformance

Check every new module or directory introduced by this diff against the Module
Boundaries section of `architecture.md`.

- New modules that do not appear in any existing boundary → flag as DRIFT
- Existing modules that have taken on responsibilities not listed for them → flag as DRIFT

Flag as DRIFT (not CRITICAL) — a DRIFT finding surfaces at the human gate for approval.

---

## 3. Cross-Module Imports

Check every new import added by this diff against the Shared Interfaces section of
`architecture.md`.

- Imports that cross module boundaries not listed in Shared Interfaces → flag as DRIFT
- Internal sub-module imports that expose private symbols across boundaries → flag as DRIFT

---

## 4. File Size

No implementation file may exceed 250 lines.
No test file may exceed 350 lines.
No prompt file (`.md` in a prompts/ or commands/ directory) may exceed 150 lines.

If the pre-filter already flagged an overage, note it here only if it was suppressed
or still unresolved. Flag as WARNING.

---

## 5. Scope Check (Owns List)

Every file written or modified in this diff must appear in the task's `owns` list.

Flag any file modified outside the `owns` list as CRITICAL (scope creep). This
includes incidental formatting changes to files not listed.

---

## 6. Idempotency

Operations must be safe to run twice with the same result.

Check for non-idempotent side effects:
- Unconditional file writes that overwrite without checking existing content
- Database inserts without upsert / existence check
- API calls that create resources without checking if they already exist

Flag as WARNING.

---

## 7. Bare Except Confirmation

The pre-filter catches bare `except:` at parse time. Confirm the pre-filter finding
was not suppressed by a `# noqa` comment or equivalent. Flag as WARNING if suppressed.

---

## 8. Coding Standards Compliance

Lazy-load `commands/common/coding_standards.md` and check the diff for violations.

Check:
- **Hardcoded Strings**: Hardcoded string literals or magic numbers in logical checks or
  command inputs should be centralized in constants (e.g., `agentflow/config/constants.py`).
  Flag as WARNING.
- **Bare Except**: Check that specific exceptions are caught, not bare `except:`.
  The pre-filter catches most cases, but contextual misses may exist. Flag as WARNING if found.
- **File Size Violations**: Implementation files > 250 lines, test files > 350 lines, or
  prompt/skill files > 150 lines. The pre-filter catches full-file violations, but flag
  if new lines introduced push a file over its limit. Flag as WARNING.
- **Idempotency**: Operations must be safe to run twice. Check for unconditional overwrites,
  lack of existence checks, or duplicate resource creation. Flag as WARNING.

If no coding standards violations found in this diff, report `CLEAN`.

---

## Output Format

- `CRITICAL: [finding] — [file:line]` — blocks merge; must be fixed
- `WARNING:  [finding] — [file:line]` — surfaces to human at review gate
- `DRIFT:    [finding] — [file:line]` — architecture.md needs update if intentional
- `CLEAN` if no findings in this section
