import json
from pathlib import Path

# Prices per million tokens (Claude API, 2026-07)
PRICING = {
    "sonnet": {"uncached_input": 3.00, "cache_creation": 3.75, "cache_read": 0.30, "output": 15.00},
    "haiku": {"uncached_input": 0.80, "cache_creation": 1.00, "cache_read": 0.08, "output": 4.00},
}

_HAIKU_ALIASES = {"haiku", "claude-haiku-4-5-20251001"}


def tokens_to_usd(token_detail: dict, model: str = "sonnet") -> float:
    """Compute USD cost for a token_detail dict using model pricing."""
    prices = PRICING.get(model, PRICING["sonnet"])
    m = 1_000_000
    return (
        token_detail.get("uncached_input", 0) * prices["uncached_input"] / m
        + token_detail.get("cache_creation", 0) * prices["cache_creation"] / m
        + token_detail.get("cache_read", 0) * prices["cache_read"] / m
        + token_detail.get("output", 0) * prices["output"] / m
    )


def model_routing_savings(project_root: Path) -> dict:
    """Compute USD saved by routing tasks to Haiku instead of Sonnet.

    Returns {"usd_saved": float, "haiku_tasks": int, "token_saved_equivalent": int}
    """
    ledger_path = project_root / "agentflow_ledger.json"
    if not ledger_path.exists():
        return {"usd_saved": 0.0, "haiku_tasks": 0, "token_saved_equivalent": 0}
    try:
        raw = json.loads(ledger_path.read_text())
        sessions = raw if isinstance(raw, list) else raw.get("sessions", [])
    except Exception:
        return {"usd_saved": 0.0, "haiku_tasks": 0, "token_saved_equivalent": 0}

    task_models: dict[str, str] = {}
    try:
        td = json.loads((project_root / "tasks.json").read_text())
        for t in td.get("tasks", []):
            if "model" in t:
                task_models[t["task_id"]] = t["model"]
    except Exception:
        pass

    usd_saved = 0.0
    haiku_tasks = 0
    for session in sessions:
        task_ids_str = session.get("task_ids", "") or ""
        task_ids = [t.strip() for t in task_ids_str.split(",") if t.strip()]
        if not task_ids:
            continue
        routed_haiku = [tid for tid in task_ids if task_models.get(tid) in _HAIKU_ALIASES]
        if not routed_haiku:
            continue
        td = session.get("token_detail") or {}
        # Prorate by fraction of haiku tasks in this session
        frac = len(routed_haiku) / len(task_ids)
        haiku_cost = tokens_to_usd(td, "haiku") * frac
        sonnet_cost = tokens_to_usd(td, "sonnet") * frac
        usd_saved += max(0.0, sonnet_cost - haiku_cost)
        haiku_tasks += len(routed_haiku)

    output_price_per_tok = PRICING["sonnet"]["output"] / 1_000_000
    token_saved_equiv = int(usd_saved / output_price_per_tok) if usd_saved > 0 else 0
    return {"usd_saved": usd_saved, "haiku_tasks": haiku_tasks, "token_saved_equivalent": token_saved_equiv}
