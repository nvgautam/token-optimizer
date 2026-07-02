# Headroom-AI Integration Feasibility Evaluation (PTY + M5)

This document presents the findings of Research Spike T-071: Evaluation of the `headroom-ai` library for integration with the AgentFlow PTY Shell (Milestone 4) and Multi-Agent Orchestration runtime (Milestone 5).

---

## 1. Overview & Objective

The objective of this spike is to evaluate the technical feasibility, architectural fit, and token-saving capabilities of the `headroom-ai` library when integrated with the AgentFlow platform. 

Specifically, we analyze:
* The wrapper and interception mechanism.
* The compression algorithms, modes, and expected savings.
* The behavior of `SharedContext` for inter-agent handoffs.
* The persistence of session-level metrics.
* Composability with the Milestone 4 PTY shell and Milestone 5 multi-agent design.

---

## 2. Installation & Dependency Analysis (Intel macOS)

* **Standard Installation:** Running `pip install "headroom-ai[all]"` compiles native extensions. Under Intel macOS (`x86_64-apple-darwin`), compiling the `ort-sys` crate (Rust bindings for ONNX Runtime) fails because the crate does not distribute pre-compiled binaries for `x86_64-apple-darwin` without features.
* **Workaround:** To install successfully on Intel macOS, `onnxruntime` must be installed via Homebrew, and environment variables must be exported to point the compiler to the dynamic library:
  ```bash
  brew install onnxruntime
  export ORT_LIB_LOCATION=$(brew --prefix onnxruntime)/lib
  export ORT_PREFER_DYNAMIC_LINK=1
  pip install "headroom-ai[all]"
  ```
* **Granular Installation:** If ML-based text compression (`Kompress`) is not required, headroom-ai can be installed without native ML dependencies using `pip install headroom-ai`, though it still builds core crates using `maturin` and cargo.

---

## 3. Execution & Interception Mechanism

`headroom wrap <agent>` (e.g., `headroom wrap claude`) acts as an orchestration shim:
1. **Local HTTP Proxy:** It launches a local asynchronous HTTP proxy server (default port `8787`) that intercepts Anthropic/OpenAI API requests.
2. **Environment Redirection:** It redirects outgoing network traffic by exporting `ANTHROPIC_BASE_URL=http://127.0.0.1:8787` (or `ANTHROPIC_FOUNDRY_BASE_URL`/`ANTHROPIC_VERTEX_BASE_URL` in Azure/GCP modes).
3. **Durable Config Injection:** For Claude Code specifically, the pre-forked conversation workers (`cc-daemon`) spawn as independent processes that do not inherit environment variables from the wrapper process. To resolve this, `headroom` writes the proxy URL directly to the user's global `~/.claude/settings.json` and project-local `.claude/settings.local.json` file on startup, and restores the original settings in a `finally` block or during `headroom unwrap`.
4. **Execution:** It runs the underlying binary (`shutil.which("claude")`) as a child process via `subprocess.run()`.
5. **No I/O Redirection:** Crucially, `headroom wrap` **does not capture, redirect, or modify the stdin/stdout/stderr file descriptors** of the launched process. Stdio is inherited directly from the caller.

---

## 4. Composability Verdict with AgentFlow PTY Shell

> [!IMPORTANT]
> **Composability Verdict: FULLY COMPATIBLE (Proceed)**

* **PTY Interception:** The Milestone 4 PTY shell intercepts I/O from PTY stdout/stdin at the terminal layer to count tokens, detect skill invocations, and manage handoff thresholds. Because `headroom wrap` leaves the child process's stdio streams untouched, the PTY shell can wrap `headroom wrap claude` instead of raw `claude` without any interference.
* **Coexistence:** The PTY shell handles local terminal I/O (PTY slave), while Headroom handles network-level token compression (HTTP proxy). They operate at completely orthogonal layers.

---

## 5. Compression Pipeline & Algorithms

The core of Headroom is its `TransformPipeline` (defined in `headroom/compress.py`), which processes messages sequentially through the following stages:

* **CacheAligner:** Stabilizes prefix messages to maximize provider-side KV cache hits.
* **ContentRouter:** Inspects content blocks and routes them to type-specific compressors:
  1. **SmartCrusher (JSON & Tabular):** Performs structural compression on JSON and tabular data. Uses array deduplication, position-based/anomaly-based element selection, and falls back to lossy Context Compression & Retrieval (CCR).
  2. **CodeCompressor (Code):** Minifies and compresses source code structures.
  3. **Kompress (Natural Text):** An ML-based compressor using a HuggingFace model (`chopratejas/kompress-v2-base`) to perform lossy context summarization.
* **Inflation Guard:** Monitors compression performance; if a transformation inflates the token count rather than reducing it, Headroom reverts the message to its original state.
* **Token Savings Estimate:** 
  * JSON and logs: **60–95% savings** (via SmartCrusher).
  * Natural text: **30–70% savings** (via Kompress).
  * Overall: Typically yields **60%+ context reduction** for coding workflows with large tool/command outputs.

---

## 6. SharedContext Architecture & Multi-Agent Design

`SharedContext` (defined in `headroom/shared_context.py`) is designed to share compressed context between agents:

* **Internal Design:**
  * It is a **purely in-memory** Python class using a thread-safe `threading.Lock` and a `dict` storage.
  * It supports a time-to-live (TTL) eviction policy and max entries limit.
  * Stored data is associated with a key and stores both the `original` (full detail) and `compressed` version of the string.
* **Cross-Process Behavior:** 
  * Because it is in-memory, **it is NOT cross-process out-of-the-box**. Two separate Python processes (e.g., the PTY shell process and a separate background worker process) instantiating `SharedContext()` will not see each other's keys.
* **Cross-Provider Sharing:**
  * Since stored keys are associated with standard strings, context sharing is provider-agnostic. Agent A (Gemini) can put a string in, and Agent B (Claude) can retrieve the compressed string. The compression uses the configured headroom tokenizer, independent of the provider.

---

## 7. Metrics & Reporting

Headroom provides comprehensive savings tracking:
* **Durable Ledger:** Every proxy request and MCP compression event is recorded in a file-locked, append-only JSONL ledger (`savings_events.jsonl` located in the workspace directory, usually `~/.headroom/`).
* **Concurrency-Safe:** It uses Unix `fcntl` advisory locking to support multiple concurrent writer processes.
* **Summary Metrics:** The ledger tracks `before` tokens, `after` tokens, `saved` tokens, `cost_usd` (avoided cost calculated using LiteLLM model pricing), `model`, `client` (corresponds to the project directory name), and `timestamp`.
* **Report Generator:** Exposes `headroom.reporting.generator.generate_report(store_url, output_path)` to compile the ledger into a premium HTML dashboard complete with a waste histogram, top high-waste requests, and cache alignment diagnostics.

---

## 8. Design Implications for Milestone 5

To support multi-agent orchestrator-to-worker handoffs in Milestone 5 using Headroom, we must address `SharedContext`'s in-memory limitation:

1. **Option A: File-Based/SQLite Shared Cache (Recommended)**
   Instead of using `SharedContext` in-memory, we can implement a custom `SharedContext` subclass or adapter that persists the keys to a shared sqlite database (e.g. sharing `.headroom/memory.db`) or a simple project-local JSON file. This guarantees cross-process consistency when the orchestrator hands off to independent worker processes.
2. **Option B: Shared Local MCP Server**
   We can launch a single background Headroom MCP server (`headroom mcp start`) during the PTY shell session. All orchestrators and worker processes connect to this single MCP server. The server exposes `headroom_compress` and `headroom_retrieve` tools, acting as the centralized, cross-process context broker.

---

## 9. Recommended Integration Plan

We recommend integrating Headroom as an optional, high-efficiency layer in the PTY Shell:

1. **PTY Wrapper Integration:**
   Modify the PTY shell's session startup to invoke `headroom wrap claude` instead of raw `claude` if `headroom` is installed.
2. **Environment Isolation:**
   Set `HEADROOM_WORKSPACE_DIR` to the project's local path (e.g., `token-optimizer/.headroom/`) to isolate the session caches, databases, and savings ledger from the user's global folder.
3. **Project Savings Attribution:**
   Pass the workspace name to `X-Headroom-Project` header or env `HEADROOM_PROJECT` so that all savings are attributed to the specific token-optimizer repository inside `savings_events.jsonl`.
4. **Report Hook:**
   Add a subcommand `agentflow report` that calls `headroom.reporting.generator.generate_report` on the project-local ledger to generate a visual HTML report of session savings.

---

## 10. Cache-Mode Regression and Fix (T-084, 2026-07-02)

T-080 set `HEADROOM_MODE=cache` to fix a real corruption incident (T-079: gate files like design_status.md occasionally garbled by ContentRouter compression). This traded away nearly all compression savings as an unintended side effect.

**Root cause, confirmed by reading the installed `headroom-ai` 0.28.0 source:**
- `DEFAULT_EXCLUDE_TOOLS` (`headroom/config.py`) protects Read/Glob/Grep/Write/Edit output unconditionally in *both* token and cache mode — cache mode never added tool-type protection that wasn't already there.
- Token mode's actual gap: `server.py:637` sets `protect_recent_reads_fraction=0.3` — excluded-tool output older than ~30% of the conversation loses protection. This, not the mode dichotomy, was T-079's real leak vector.
- Cache mode's actual effect: `anthropic.py:908-915`'s `_strict_previous_turn_frozen_count()` unconditionally freezes every message except the current turn — for every tool and content type, not just the five excluded tools. Measured via `.headroom/logs/proxy.log`: compression rate collapsed from 649/882 requests (74%) pre-cutover to 8/920 (<1%, all in the transition window) post-cutover.
- No upstream knob decouples these two effects — `protect_recent_reads_fraction` has no env var/CLI override; it's hardwired to `is_token_mode(config.mode)` in `server.py`.

**Resolution:** reverted `agentflow/cli.py` to `HEADROOM_MODE=token`. The residual 0.3-fraction recency leak on gate files is mitigated at the skill level, not the proxy level — `commands/claude/oracle.md` and `commands/claude/orchestrate.md` (T-079) already require a fresh same-turn Read before acting on any gate file's contents, and immediate re-read on any stale/garbled-looking result. That guard doesn't depend on which headroom mode is active. Given the mitigation already exists and cache mode's cost (~9M of ~10.7M tokens in the project's measured savings pool, per T-072/T-082) vastly exceeds the risk it was defending against, token mode is the correct steady-state choice.

**Not done (out of scope for T-084):** no upstream feature request filed for a knob that would set `protect_recent_reads_fraction=0.0` under token mode without the frozen-count side effect. Worth filing if the 0.3-fraction leak proves material in practice.
