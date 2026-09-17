# GHOST — Migration Plan (incremental, no rewrite)

Date: 2026-09-17
Rule (spec §59): preserve working functionality, improve incrementally. Every milestone keeps the system runnable and adds tests for what it touches. Sizes are estimates of *code sessions*, not lines.

---

## M0 — Hygiene & Truthfulness (first code milestone, ~1 session)

Goal: make the repo honest, runnable, and reproducible before adding anything.

1. **Fix `requirements.txt`** — add `fastapi`, `uvicorn`, `httpx`, `pypdf`, `python-docx`, `sentence-transformers`, `scikit-learn`, `python-dotenv` (all currently imported by `backend/` but undeclared — D5).
2. **Add `README.md`** — how to configure `.env` (from `.env.example`), create venv, install, run `uvicorn backend.main:app --port 8000` and `npm run dev` in `frontend/`.
3. **Quarantine legacy** — move `app.py`, `orchestrator.py` (root), `models.json` into `legacy/gradio-app/` (D7/T9). Update nothing else; the GHOST backend doesn't import them (verified).
4. **Delete dead code** — `backend/core/retriever_backup.py`; `frontend/src/components/{ChatWindow,ChatInput,MessageBubble}.jsx`, `GhostFlowDiagram.jsx`, `ghost-flow.css` (verified unimported); unreachable block `chat.py:304-353` (D4).
5. **Singletons** — create `backend/core/services.py` holding one `MemoryService`, one `Orchestrator`, one provider registry; `chat.py` and `graph.py` import from there (fixes D3 race).
6. **Wire the real system prompt** — route the live chat path through `Orchestrator` so `build_system_prompt()` actually reaches the model (fixes D2). Smallest change: in the stream call, send `[{system}, {user}]`.
7. **Send conversation history** — add `history: list[{role,content}]` to `ChatRequest` (cap at last N turns), populate from the frontend `messages` state (fixes D1, the broken multi-turn context).
8. **Log hygiene** — remove memory-content `print`s (`chat.py:944-960`); map exceptions to generic client errors (D10, threat T5a/c).
9. **Startup validation** — fail fast with a clear message if `NVIDIA_API_KEY` is missing; real provider ping in `/health` (D12, T10).
10. **Typo fixes** — `frontedn` → `ghost-frontend` (package name + title).
11. **First tests** — `pytest` for: memory add/search/duplicate/delete; chunker + page-range mapping; intent classifiers (`is_whole_document_request`, `extract_requested_page`, `should_use_document`); context optimizer budget. These are pure functions — cheap, high value (D14 starts shrinking).

**Acceptance**: fresh clone → install → both processes run; multi-turn chat retains context; `pytest` green; no memory text in server console.

## M1 — User Control Over Data (privacy floor, ~1–2 sessions)

1. **Memory API + UI**: `GET/DELETE /api/memory`, `DELETE /api/memory/all` wrapping the existing service methods (`memory.py:897-1012`); a Memory drawer list with delete buttons + provenance display. (Privacy §3.3, threat T4.)
2. **Document registry**: `GET /api/documents` (list metadata), `DELETE /api/documents/{id}` (removes from `documents`); cap concurrent documents + max upload size (T6).
3. **Cloud-transmission notice** — status line in UI: "model: cloud (NVIDIA)" and an upload notice. (Privacy headline finding.)
4. **Secret rejection upgrade** — entropy-based detector added to keyword blocklist (T5a).
5. **Graph endpoint** — return labels/counts only; content via memory API (T1-adjacent, T5d).

## M2 — Identity Boundary (security floor, ~1–2 sessions)

1. Session-token middleware on all API routes; token issued via a local login (passphrase or OS-auth — ADR-002); loopback-only bind by default with explicit opt-out warning (T1).
2. Rate limiting per session (slowapi or hand-rolled) (T6).
3. Replace in-band `__SOURCES__` string with a structured first event (T7).
4. Untrusted-content delimiters around document/memory sections in prompts (T3 layer 1).

## V1 — GHOST MVP Task Loop (the spec's "smallest system that proves the concept", ~3–5 sessions)

The milestone that turns a chat app into GHOST. Scope exactly per spec §58:

```
UNDERSTAND → PLAN → EXECUTE (controlled tools) → OBSERVE → VERIFY → COMPLETE/RETRY
```

1. **Task Engine** (`backend/tasks/`): SQLite-persisted task records; state machine CREATED→UNDERSTANDING→PLANNING→WAITING_PERMISSION→EXECUTING→VERIFYING→RETRYING→COMPLETED/FAILED/CANCELLED (spec §20); crash-recovery by state reload.
2. **Success contracts**: every task carries a machine-checkable "done" definition (spec §19) — start with: "tests pass", "file exists", "command exit code".
3. **Change budget** per task: max tool calls, max model calls, max wall time, max files touched (spec §21).
4. **Tool layer** (`backend/tools/`) — three read-only tools only: `read_file` (project-scope allowlist), `list_dir`, `http_get` (GET, domain allowlist). Each tool = JSON schema + policy metadata + audit row.
5. **Security Sentinel v0** (`backend/permissions/` + `backend/audit/`): deterministic policy table (ALLOW/DENY/APPROVE by capability × scope); every tool call flows through it; append-only audit log (SQLite). The LLM proposes; this decides (spec §22).
6. **Approval UX**: WAITING_PERMISSION renders an approve/deny card; silence times out to DENY (spec §27).
7. **UI**: Task view (state, steps, verification result, budget usage) beside the existing chat/graph.
8. **Verification runner**: executes the success contract; only its PASS moves the task to COMPLETED (spec §2: "never complete because a tool call succeeded").

**Out of scope for V1** (explicitly): write tools, shell, browser, agents, memory/world-model upgrades, multi-model routing, gestures, devices, perception.

## V2 — Memory + World Model (per spec §58)
SQLite migration + encryption at rest (ADR-001); memory tiers (working/session/episodic); TTL + consolidation job; event log table; temporal queries ("what changed before this error"); `/api/graph` fed by real entities/relations, hardcoded tool nodes removed or state-driven.

## V3 — Security + Sandbox
Write-capable tools behind APPROVE; git checkpoint/rollback wrapper for write tools; sandbox for unknown executables (ADR-006); injection red-team suite (spec §47) wired into CI; model-output/tool-output isolation rules (spec §25).

## V4 — Model Router
Multi-provider registration (local + cloud); capability/privacy/cost metadata; classification-aware routing + redaction (spec §12, §34); offline/degraded chain (spec §41); budget manager (spec §42).

## V5+ — Trust, Gestures, Awareness (unchanged from spec §58)
Device trust tiers, approval router across devices, gestures (PIA required first), perception scheduler + event bus, replay UI, GHOST EVAL harness.

---

## Dependency order (why this sequence)

- M0 before everything: broken deps/history/prompt mean any feature built on top inherits lies.
- M1 before M2: giving the user view/delete power is the cheapest real privacy win and needs no auth complexity on a loopback box.
- M2 before V1: tools *must* be born behind auth + policy (spec: boundary before capability).
- V1 before V2/V3 upgrades: the core loop with 3 read-only tools proves the architecture while blast radius is tiny.
