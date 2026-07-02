# Headroom Auto-Capture of 5hr/Weekly Usage Windows (T-077)

Spike scope: ONLY the `/usage` 5h/7d window %, reset time, cap fields (design_status.md #57).
Per-request token usage is already solved (usage_parser.py) — out of scope here.
Tested against `headroom-ai==0.28.0` (current PyPI, Intel macOS, via the T-071 onnxruntime
workaround). No AgentFlow code changed.

---

## 1. Claude path — MECHANISM CONFIRMED, FEASIBLE

**Question asked was wrong framing — corrected finding:** Whether Claude Code's own `/usage`
network call routes through `ANTHROPIC_BASE_URL` turns out not to matter. Headroom does **not**
rely on intercepting that call at all. It runs its own independent background poller.

Source: `headroom/subscription/{client.py,tracker.py,base.py}`, wired in `headroom/proxy/server.py`.

- `SubscriptionClient.fetch()` hits `GET https://api.anthropic.com/api/oauth/usage` directly
  (`anthropic-beta: oauth-2025-04-20`, `Authorization: Bearer <token>`) — this is the same
  undocumented-but-first-party endpoint Claude Code's own `/usage` command reads.
- Token resolution: `CLAUDE_CODE_OAUTH_TOKEN` env var, else `~/.claude/.credentials.json` →
  `claudeAiOauth.accessToken` (respects `CLAUDE_CONFIG_DIR`). No probing/auth bypass — it's the
  same credential Claude Code already stores on disk after login.
- `SubscriptionTracker` (`headroom/subscription/tracker.py`) polls every 300s (configurable)
  while a live Bearer token has passed through the proxy in the last 60s (`notify_active`,
  triggered passively by real `/v1/messages` traffic), and **also** falls back to the on-disk
  cached token even with zero live proxy traffic — so this can run continuously, not gated on
  the user ever typing `/usage`.
- Registered as a `QuotaTracker` in the process-global registry (`headroom/subscription/base.py`)
  and exposed on two local endpoints:
  - `GET /subscription-window` — single-provider Anthropic view, `render_state()`-synthesized
    (handles the case where the window rolled over since the last 5-min poll).
  - `GET /quota` — aggregates all registered trackers (Anthropic + Codex + Copilot).

**Response shape** (`SubscriptionSnapshot.to_dict()` / `RateLimitWindow.to_dict()`), exactly the
fields design_status.md #57 needs:

```json
{
  "five_hour":  {"used": N, "limit": N, "utilization_pct": F, "resets_at": "ISO8601Z", "seconds_to_reset": F},
  "seven_day":  {"used": N, "limit": N, "utilization_pct": F, "resets_at": "ISO8601Z", "seconds_to_reset": F},
  "seven_day_opus":   { ... optional per-model 7d windows ... },
  "seven_day_sonnet": { ... },
  "extra_usage": {"is_enabled": bool, "monthly_limit_usd": F, "used_credits_usd": F, "utilization_pct": F},
  "contribution": { ...headroom's own token-savings counters, not needed for this spike... }
}
```

`utilization_pct` → the "%"; `resets_at`/`seconds_to_reset` → "reset time"/"reset_min";
`limit` → "cap". Direct 1:1 mapping, zero parsing beyond `json.loads`.

**Empirically verified live** (not just read from source): installed `headroom-ai[proxy]==0.28.0`
in an isolated venv (brew onnxruntime workaround per the T-071 eval doc), started the standalone
proxy (`headroom proxy --port 18787`), and curled both endpoints:

```
$ curl http://127.0.0.1:18787/subscription-window
{"latest":null,"window_tokens":null,"contribution":{...zeroed...},"discrepancies":[],
 "poll_count":0,"poll_errors":0,"last_error":null,"last_active_at":null}

$ curl http://127.0.0.1:18787/quota
{"subscription_window": { ...same shape... }}
```

`latest: null` is expected/correct — no real Anthropic OAuth account/credentials existed in this
sandbox, so the tracker has never had a token to poll with (this is the documented `is_available()`
/ no-op-until-active-token behavior, not a bug). The endpoint contract, field names, and JSON
shape all match the source exactly, confirming the mechanism is real and reachable without
touching Claude Code's own `/usage` command at all.

**Verdict: FEASIBLE.** AgentFlow's rate-pacing protocol could poll
`GET http://127.0.0.1:<headroom_port>/subscription-window` (port defaults to 8787, configurable
via `headroom wrap claude --port`) whenever headroom is wrapping the session, instead of asking
the user to run `/usage` and paste the output.

**Caveats before wiring this in (do not implement from this spike alone):**
1. Never independently verified against a *real* Claude Code `/usage` render — this sandbox has
   no live Anthropic subscription account. `render_state()`'s post-reset synthesis logic (issue
   #281 handling) is a headroom-side estimate when the 5-min poll cadence lags a window rollover;
   it could disagree with what Claude Code itself displays at the exact rollover boundary. A
   follow-up task (same empirical-verification shape as T-072/T-074's Gemini-savings check)
   should diff `/subscription-window` output against a manually-run `/usage` in a real session
   before this replaces the manual-ask step.
2. Only available when `headroom wrap claude` is actually running (i.e., headroom installed +
   PTY shell wraps with it — T-074). If headroom isn't installed, the manual-ask path is still
   required as a fallback.
3. `extra_usage`/`seven_day_opus`/`seven_day_sonnet` are extra fields beyond what #57 currently
   captures — bonus data, not a blocker.

---

## 2. Gemini / agy path — NOT FEASIBLE, blocked before the question even applies

Step 3 of the task ("repeat for `headroom wrap agy`") could not be executed as framed:
**`headroom wrap agy` and `headroom wrap gemini` are not valid commands.**

Empirically confirmed (same 0.28.0 install):

```
$ headroom wrap agy
Usage: headroom wrap [OPTIONS] COMMAND [ARGS]...
Error: No such command 'agy'.

$ headroom wrap gemini
Usage: headroom wrap [OPTIONS] COMMAND [ARGS]...
Error: No such command 'gemini'.
```

`headroom wrap --help` lists only: `claude, codex, copilot, aider, vibe, cursor, cline, continue,
goose, openhands, openclaw, opencode`. No Gemini CLI wrapper exists in this version at all —
confirmed against `headroom/cli/wrap.py` source (`@wrap.command` definitions, one per name above;
no gemini/agy entry).

Additional findings, for completeness:
- The proxy itself *does* have Gemini routing plumbing at the HTTP layer (`headroom proxy`'s
  startup banner lists `/v1internal:streamGenerateContent → https://cloudcode-pa.googleapis.com`
  and a Vertex AI route), used when other tools point their own `GOOGLE_*` base-url env var at
  the proxy manually via `headroom proxy` (not `wrap`).
- Even so, `headroom/subscription/base.py`'s registry only has three registered `QuotaTracker`
  implementations wired in `server.py`: `SubscriptionTracker` (Anthropic), `CodexRateLimitState`
  (OpenAI Codex), `_CopilotQuotaTracker` (GitHub Copilot). **No Gemini/Google quota tracker
  exists**, registered or otherwise (the `GeminiQuotaTracker` shown in `base.py`'s module
  docstring is a documentation example for how to add one — it is not implemented anywhere in
  the package). So even if `agy` were manually pointed at a running `headroom proxy`, there is
  still no 5h/weekly-style window poller for it to expose.
- Gemini's actual quota model (RPM/RPD-style, per `project_agy_usage_windows.md` memory —
  Gemini/agy's `/usage` does mirror Claude Code's 5h+weekly window display, per that note) is a
  distinct API surface from Anthropic's OAuth usage endpoint; nothing in headroom today reads it.

**Side finding, worth flagging even though out of this task's owns list:** `agentflow/cli.py`
`cmd_shell` (T-074) currently builds `cmd_args = ["headroom", "wrap", cmd]` unconditionally
whenever `shutil.which("headroom")` succeeds, including for `cmd == "agy"`. Given the above,
that invocation would hard-fail with Click's "No such command" error and a nonzero exit — not a
graceful fallback to raw `agy`. This is a live bug independent of this spike's usage-window
question; flagging for a future task, not fixing here (outside this task's `owns` list).

**Verdict: NOT FEASIBLE.** No mechanism exists in headroom-ai 0.28.0 to auto-capture, or even
transport, Gemini/agy usage-window data.

---

## 3. Recommendation

- **Claude:** headroom's `/subscription-window` endpoint is a real, verified, low-cost auto-
  capture path. Worth a follow-up implementation task — gated on the accuracy caveat above —
  to replace the manual-ask step for Claude sessions specifically when headroom is wrapping.
- **Gemini/agy:** no auto-capture path exists today. **Recommend keeping the current manual-ask
  + ledger-anchored derivation (design_status.md #57) as-is for agy**, unconditionally — this
  isn't a "not yet verified" gap like the Claude path, it's a hard absence of any underlying
  mechanism in the current headroom-ai release.
- Net effect on #57: the rate-pacing protocol should stay a manual ask **at minimum for Gemini
  sessions**; a Claude-only auto-capture path can be layered in later as an enhancement, not a
  full replacement, since orchestrate.md's protocol runs across both providers uniformly today.
