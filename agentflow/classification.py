from agentflow.constants import CONTEXT_LIMIT, CTX_WARN_THRESHOLD

_MECHANICAL = {
    "fix", "add", "remove", "delete", "rename", "update", "change",
    "extract", "move", "replace", "export", "import", "wire", "hook",
    "bump", "pin", "revert", "restore", "patch", "correct", "adjust",
    "set", "register", "expose", "skip", "drop", "trim", "guard",
    "convert", "mark", "tag", "log", "emit", "send", "wrap", "expand",
    "collapse", "hide", "show", "enable", "disable", "sort", "filter",
    "format", "parse", "validate", "sanitize", "index", "dedupe",
}

_EXPLORATORY = {
    "investigate", "debug", "design", "refactor", "implement", "review",
    "understand", "audit", "analyze", "analyse", "explore", "rethink",
    "plan", "migrate", "port", "rebuild", "rewrite", "overhaul",
    "architect", "research", "evaluate", "assess", "profile", "spike",
    "prototype",
}


def classify_task(subject: str) -> str:
    """
    Return 'mechanical' or 'exploratory' for a task subject line.

    Mechanical tasks have short, predictable conversation histories and are
    good candidates for session batching. Exploratory tasks generate long
    histories and should always start a fresh session.
    """
    words = set(subject.lower().replace("-", " ").split())
    has_exploratory = bool(words & _EXPLORATORY)
    has_mechanical  = bool(words & _MECHANICAL)

    if has_exploratory:
        return "exploratory"
    if has_mechanical:
        return "mechanical"
    return "exploratory"  # default: conservative


def batch_decision(next_subject: str, current_ctx: int,
                   current_files: set | None = None,
                   next_files: set | None = None) -> dict:
    """
    Decide whether the next task should run in the current session or start fresh.

    Rules applied in order (first match wins):
      1. Exploratory task        → always fresh
      2. Context over threshold  → fresh (not enough headroom)
      3. No file overlap         → fresh (unrelated work)
      4. All checks pass         → batch

    Returns dict with keys:
      decision  : 'batch' | 'fresh'
      reason    : human-readable explanation
    """
    task_type = classify_task(next_subject)
    if task_type == "exploratory":
        return {
            "decision": "fresh",
            "reason":   f"task classified as exploratory — always start fresh",
        }

    ctx_pct = current_ctx / CONTEXT_LIMIT
    if ctx_pct >= CTX_WARN_THRESHOLD:
        return {
            "decision": "fresh",
            "reason":   (f"context at {ctx_pct*100:.0f}% ({current_ctx:,} tokens) "
                         f"exceeds {int(CTX_WARN_THRESHOLD*100)}% batch threshold"),
        }

    if current_files is not None and next_files is not None:
        overlap = current_files & next_files
        if not overlap:
            return {
                "decision": "fresh",
                "reason":   "no file overlap between current session and next task",
            }
        overlap_note = f", shared: {', '.join(sorted(overlap))}"
    else:
        overlap_note = " (file overlap not checked)"

    return {
        "decision": "batch",
        "reason":   (f"mechanical task, context at {ctx_pct*100:.0f}% "
                     f"({current_ctx:,} tokens){overlap_note}"),
    }
