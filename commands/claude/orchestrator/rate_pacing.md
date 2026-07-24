# Rate-pacing protocol (DISABLED)

**Status:** This protocol is currently disabled. The first-agent-alone spawn gating has been removed; all parallel tasks in a round spawn simultaneously. Kept for future re-enablement.

Compute:
```
remaining_tokens_5hr  = cap_5hr  × (1 − start_pct_5hr/100)
remaining_tokens_wkly = cap_wkly × (1 − start_pct_wkly/100)
rate_5hr  = remaining_tokens_5hr  / reset_min_5hr
rate_wkly = remaining_tokens_wkly / reset_min_wkly
effective_rate = min(rate_5hr, rate_wkly)
```

**Round-sizing heuristic:** After each `TOKENS:` report, append `input+output` to `observed_costs[]`. Compare remaining token budget (based on `orchestrator_threshold_tokens` config) to ensure rate-pacing limits are not breached. Per-task cost (`pct_cost`): `sample_count < 7` → 2500; `sample_count ≥ 7` and `cv < cv_threshold` (default 0.3) → `mean` as the cost estimate when CV (coefficient of variation) is low; `cv ≥ cv_threshold` (default 0.3) → p85 (85th percentile) when CV is high. EWMA: `new_ewma = 0.3 × session_mean + 0.7 × prior_ewma`.

1. Before each round: `max_tasks_by_rate = max(1, floor(effective_rate × 10 / pct_cost))`; `max_tasks_by_budget = max(1, floor(orchestrator_threshold_tokens / pct_cost))`; `max_tasks = min(max_tasks_by_rate, max_tasks_by_budget)`
2. After each `TOKENS:`: `effective_rate × remaining_minutes < 3 × pct_cost` → pause, ask `/usage`.
3. Session end: ask `/usage` (`end_pct_5hr`, `end_pct_wkly`). Derive caps ledger-anchored:
   - Window boundaries (naive local time only — never UTC): `reset_time = datetime.now() + timedelta(minutes=reset_min)`; `win_start = reset_time − window_size`
   - Read `agentflow_ledger.json`; filter `sessions[]` where `start_time ≥ window_start`
   - Count `sessions_in_window_5hr`, `sessions_in_window_wkly`
   - Sum per session: `uncached_input + cache_creation + output`
   - `cap_wkly = total_wkly_tokens / (end_pct_wkly / 100)` — derive weekly first (more sessions, more reliable)
   - `sessions_in_window_5hr >= 3` → `cap_5hr = total_5hr_tokens / (end_pct_5hr / 100)`; else `cap_5hr = cap_wkly` with low-confidence note
   - Gap: add `(end_pct − start_pct) × prior_cap` if ledger sum is low
   - Write `~/.agentflow/rate_calibration_claude.json`: `{timestamp (naive local, no Z), start_pct_5hr, end_pct_5hr, start_pct_wkly, end_pct_wkly, session_tokens, cap_5hr, cap_5hr_note, cap_wkly, cap_wkly_note, rate_5hr, rate_wkly, ewma_mean_tokens, ewma_cv, sample_count, ewma_alpha}`
