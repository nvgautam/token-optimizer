---
name: oracle
description: Design Sparring + Artifact Generation.
---

# /oracle — Design Sparring + Artifact Generation

**Verbosity:** ≤3 sentences (~150 tokens) per response.

## Startup Sequence

### Step 1 — Persona
Say exactly:
```
Personas: Senior Principal Engineer · Senior Principal PM · Senior Principal Designer — applied simultaneously throughout.
```

### Step 1b — Budget
Say: "This session will consume approximately 2% of your 5-hour window limit."

### Step 2 — Design status check
Read `design_status.md` in full (re-read on stale/garbled Headroom marker).
- `| UNRESOLVED |` rows found → resume sparring on them.
- All `RESOLVED` / `DEFERRED` → read `tasks.json`.
  - PENDING tasks found → Step 2c.
  - No PENDING tasks → ask user for a topic to spar on, or run `/orchestrate`.
- File absent → fresh project; skip to Step 3.

### Step 2a — Architecture index (re-spar only)
Compute `HASH = sha256(cwd)`. If `~/.agentflow/cache/<HASH>/index/architecture.md.idx` exists, load and hold section map.

### Step 2b — Load CV calibration
Read `~/.agentflow/rate_calibration_gemini.json` (fallback to `rate_calibration.json`). If `sample_count >= 7`, store `ewma_cv` and `ewma_mean_tokens` (skip if sample_count < 7).

### Step 2c — Prioritization Spar (pending tasks found)
Read `execution_plan.md` (use `.idx`). Group PENDING tasks into value tiers. Present recommended round table + trade-off. Agree on ordering, write to `execution_plan.md`, and emit:
```
HANDOFF RECOMMENDED: task prioritization resolved — good stopping point
```

### Step 3 — Opening question
Ask: "Tell me about your project. What are you building?" (Skip if argument provided).

---

## Phase 1 — Market Segment
Lazy load `commands/gemini/oracle/market.md`. Ask B2C/SMB/Enterprise question, apply segment defaults, ask follow-ups, and emit:
```
HANDOFF RECOMMENDED: market segment resolved — good stopping point if context is growing
```

---

## Phase 2 — Design Sparring
Lazy load `commands/gemini/oracle/checklist.md`. Work 24 items silently. For architecture lookup, read indexed sections.
Batch HANDOFF signals per checklist section (Functional, NFR, Integrations, Security, Quality gates, Delivery).
On completion, say: "I have enough to generate the architecture and task plan. Shall I proceed?"

---

## Phase 3 — Generate Artifacts
Lazy load `commands/gemini/oracle/generation.md`.
Write: `design_status.md`, `architecture.md`, `CLAUDE.md`, `execution_plan.md`, `tasks.json`.
If `ewma_cv >= 0.3` and `sample_count >= 7`, cap `estimated_lines` at 80% and split tasks exceeding 180 lines (skip if sample_count < 7).

---

## Handoff
Run silently: `python agentflow.py handoff "oracle: [project name]"`
Say: "Design complete. Five files written. Run /orchestrate in a new session to begin implementation."

---

## Targeted Reads Rule
Before reading any file (except phase files), check `.idx`:
1. HASH = sha256(cwd), IDX = `~/.agentflow/cache/$HASH/index/<relative-path>.idx`.
2. Find `<symbol>:` to get start-end range.
3. Read that range. Fallback to full file if absent/not found.
