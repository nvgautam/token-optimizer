import json
from pathlib import Path
from agentflow.constants import CLAUDE_PROJECTS_DIR

def _get_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:
        return 0.0


def read_jsonl_usage() -> dict | None:
    """
    Find the most recently modified JSONL session file for the current project
    and sum all unique per-turn usage records.

    Returns dict with:
      session_file, n_turns, input_tokens, cache_creation_tokens,
      cache_read_tokens, output_tokens, initial_ctx, final_ctx
    or None if no file found.
    """
    cwd   = Path.cwd().resolve()
    slug  = str(cwd).replace("/", "-")
    project_dir = CLAUDE_PROJECTS_DIR / slug

    if not project_dir.exists():
        return None

    jsonl_files = list(project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    latest = max(jsonl_files, key=lambda f: f.stat().st_mtime)

    seen              = set()
    turns             = []
    handoff_turn_idx  = None   # index of the first turn that contains the handoff invocation

    with open(latest) as f:
        for raw_line in f:
            # Fast string check before JSON parse — tracks the LAST handoff turn.
            # Always overwrite so repeated /handoff calls in one session don't
            # misclassify early work turns as handoff overhead.
            if "agentflow.py handoff" in raw_line:
                handoff_turn_idx = len(turns)  # will be this turn's index once appended
            try:
                obj = json.loads(raw_line)
            except Exception:
                continue
            usage = obj.get("message", {}).get("usage") or obj.get("usage")
            if not usage:
                continue
            key = (
                usage.get("input_tokens", 0),
                usage.get("cache_creation_input_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
                usage.get("output_tokens", 0),
            )
            if key in seen:
                continue
            seen.add(key)
            turns.append({
                "inp": usage.get("input_tokens", 0),
                "cw":  usage.get("cache_creation_input_tokens", 0),
                "cr":  usage.get("cache_read_input_tokens", 0),
                "out": usage.get("output_tokens", 0),
            })

    if not turns:
        return None

    def ctx(t): return t["inp"] + t["cw"] + t["cr"]

    # Split turns into work vs handoff overhead.
    # handoff_turn_idx > 0 means we found the handoff turn and there's work before it.
    if handoff_turn_idx is not None and handoff_turn_idx > 0:
        work_turns    = turns[:handoff_turn_idx]
        handoff_turns = turns[handoff_turn_idx:]
    else:
        work_turns    = turns
        handoff_turns = []

    pre_handoff_ctx    = ctx(work_turns[-1])
    last_turn_output   = work_turns[-1]["out"]
    handoff_input_toks = sum(ctx(t) for t in handoff_turns)

    return {
        "session_file":           latest.name,
        "n_turns":                len(turns),
        "input_tokens":           sum(t["inp"] for t in turns),
        "cache_creation_tokens":  sum(t["cw"]  for t in turns),
        "cache_read_tokens":      sum(t["cr"]  for t in turns),
        "output_tokens":          sum(t["out"] for t in turns),
        "initial_ctx":            ctx(turns[0]),
        "final_ctx":              ctx(turns[-1]),
        "pre_handoff_ctx":        pre_handoff_ctx,
        "last_turn_output":       last_turn_output,
        "handoff_input_tokens":   handoff_input_toks,
    }


def read_gemini_db_usage() -> dict | None:
    """
    Find the most recently modified SQLite session DB for Gemini/Antigravity
    and extract prompt and candidates token counts from the gen_metadata table.

    Returns dict with:
      session_file, n_turns, input_tokens, cache_creation_tokens,
      cache_read_tokens, output_tokens, initial_ctx, final_ctx
    or None if no file found.
    """
    import sqlite3
    gemini_dir = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
    if not gemini_dir.exists():
        return None

    db_files = list(gemini_dir.glob("*.db"))
    if not db_files:
        return None

    latest = max(db_files, key=lambda f: f.stat().st_mtime)

    try:
        conn = sqlite3.connect(latest)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata'")
        if not cursor.fetchone():
            conn.close()
            return None
        
        cursor.execute("SELECT data FROM gen_metadata ORDER BY idx ASC")
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return None

    if not rows:
        return None

    def parse_varint(data, pos):
        val, shift = 0, 0
        while True:
            b = data[pos]
            val |= (b & 0x7f) << shift
            pos += 1
            if not (b & 0x80): break
            shift += 7
        return val, pos

    def parse_proto(data, pos=0, end=None):
        if end is None: end = len(data)
        res = {}
        while pos < end:
            try:
                key, pos = parse_varint(data, pos)
            except IndexError:
                break
            wt, fn = key & 7, key >> 3
            if wt == 0:
                val, pos = parse_varint(data, pos)
                res[fn] = val
            elif wt == 2:
                length, pos = parse_varint(data, pos)
                val = data[pos:pos+length]
                pos += length
                try: res[fn] = parse_proto(val)
                except Exception: res[fn] = val
            elif wt == 1: pos += 8
            elif wt == 5: pos += 4
        return res

    turns = []
    for (blob,) in rows:
        try:
            d = parse_proto(blob)
            f4 = d.get(1, {}).get(4, {})
            inp = f4.get(2)
            out = f4.get(3)
            if inp is not None and out is not None:
                turns.append({
                    "inp":    inp,          # 1.4.2 — uncached prompt
                    "cached": f4.get(5, 0), # 1.4.5 — cached/thinking tokens
                    "cw":     0,
                    "cr":     0,
                    "out":    out,          # 1.4.3
                })
        except Exception:
            continue

    if not turns:
        return None

    def ctx(t): return t["inp"] + t["cached"]

    return {
        "session_file":           latest.name,
        "n_turns":                len(turns),
        "input_tokens":           sum(t["inp"]    for t in turns),
        "cache_creation_tokens":  0,
        "cache_read_tokens":      sum(t["cached"] for t in turns),
        "output_tokens":          sum(t["out"]    for t in turns),
        "initial_ctx":            ctx(turns[0]),
        "final_ctx":              ctx(turns[-1]),
        # Gemini has no handoff detection yet; defaults keep update_shadow correct
        "pre_handoff_ctx":        ctx(turns[-1]),
        "last_turn_output":       turns[-1]["out"],
        "handoff_input_tokens":   0,
    }
