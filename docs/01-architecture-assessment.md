# GHOST — Architecture Assessment (As-Is)

Date: 2026-09-17
Method: full source review of all 58 project files (excluding `venv/`, `node_modules/`, `.env` and secret-like files, which were never opened).
Every claim below cites the file and line that evidences it. Nothing here is assumed from names or comments.

---

## 1. Executive Summary

The repository contains **two disconnected applications** plus a large set of **empty placeholder packages** named after the GHOST vision:

1. **Legacy local-model chat app** — `legacy/gradio-app/app.py` + `legacy/gradio-app/orchestrator.py`. A Gradio UI ("DeepSeek AI Orchestrator") that loads local Hugging Face transformers models selected from `legacy/gradio-app/models.json`. It is self-contained and does not touch the `backend/` package at all.
2. **The actual GHOST prototype** — `backend/` (FastAPI) + `frontend/` (React/Vite). A document-RAG chat system with persistent keyword memory, streaming responses from NVIDIA Nemotron via an OpenAI-compatible API, page-citation tracking, and a force-graph "neural map" UI.
3. **Empty scaffolding** — `workers/`, `infrastructure/`, `telegram-gateway/`, `tests/` contain only `.gitkeep`; `backend/agents`, `backend/audit`, `backend/integrations`, `backend/memory`, `backend/orchestrator`, `backend/permissions`, `backend/retrieval`, `backend/tasks`, `backend/tools`, `backend/artifacts` contain only empty `__init__.py`. **The names of the GHOST architecture exist; the code does not.**

Relative to the GHOST master spec, the current system implements roughly: *Model provider abstraction (1 provider), a slice of Memory, a slice of document Context/Retrieval, a UI shell, and a read-only knowledge-graph view.* It does **not** implement: identity, permissions, policy engine, security sentinel, tools, agents, task state machine, event bus, temporal world model, verification, audit trail, model routing, multi-device trust, gestures, evals, or any test.

The prototype is a reasonable **foundation** for GHOST V1 — the retrieval, memory, and provider layers are genuinely reusable — but it currently has **zero security or privacy architecture**, ships an **unrunnable-as-documented backend** (missing dependencies), and its most load-bearing prompt (the GHOST system prompt) is **dead code in the live request path**.

---

## 2. As-Is Architecture (verified)

```
┌────────────────────────────┐        ┌─────────────────────────────────┐
│  App A: Gradio (legacy)    │        │  App B: GHOST prototype          │
│                            │        │                                  │
│  legacy/gradio-app/app.py  │        │  frontend/ (React+Vite, :5173)   │
│   └─ orchestrator.py       │        │   └─ App.jsx (entire UI, 2860 Ln)│
│       └─ local HF models   │        │        │ fetch HTTP              │
│          (torch, CPU/CUDA) │        │        ▼                         │
└────────────────────────────┘        │  backend/main.py (FastAPI :8000) │
                                      │   ├─ /api/chat   (streaming)    │
  No connection between the two.      │   ├─ /api/upload (PDF/DOCX/TXT) │
                                      │   └─ /api/graph  (viz data)     │
                                      │  core: memory / retriever /     │
                                      │  context_optimizer /            │
                                      │  document_(processor|summarizer)│
                                      │  providers: openai_compatible   │
                                      │        │ HTTPS (no auth layer)  │
                                      │        ▼                         │
                                      │  NVIDIA integrate.api.nvidia.com│
                                      │  (Nemotron, key from .env)      │
                                      └─────────────────────────────────┘
```

Data flow of one chat turn (verified in `backend/api/chat.py:889-1787`):
`React App.jsx` → POST `/api/chat {message, provider, model, document_id}` →
keyword-intent classification (whole-doc / exact-page / targeted / plain) →
memory retrieval (`MemoryService.build_context`) → prompt string assembly →
`provider.generate_stream()` to NVIDIA → SSE-ish text stream back, with an
in-band `__SOURCES__:<pages>` first chunk for citations.

---

## 3. Component Inventory

| Component | Path | Status | Evidence |
|---|---|---|---|
| Gradio local-model chat | `legacy/gradio-app/app.py`, `orchestrator.py` | Working, standalone legacy app | `legacy/gradio-app/app.py:1-197`; loads models per `models.json` |
| Local model configs | `legacy/gradio-app/models.json` | 3 HF models (DeepSeek-Coder-V2-Lite, R1-Distill-Llama-8B, Mistral-7B) | `legacy/gradio-app/models.json:6-56` |
| FastAPI app shell | `backend/main.py` | Working; CORS limited to localhost:5173 | `backend/main.py:16-24` |
| Chat endpoint | `backend/api/chat.py` | Working; contains ~50 lines of unreachable dead code | dead code at `chat.py:304-353` (after `return` at 303) |
| Upload endpoint | `backend/api/upload.py` | Working; in-memory only, no delete, no size limit | `documents = {}` at `upload.py:13` |
| Graph endpoint | `backend/api/graph.py` | Working; **hardcoded aspirational tool nodes** ("planned": Files, Browser, PC Agent, Gmail, Telegram) | `graph.py:240-289` |
| Provider abstraction | `backend/providers/base.py`, `openai_compatible.py` | Working; one implementation (Nemotron) | `openai_compatible.py:7-96` |
| GHOST orchestrator class | `backend/core/orchestrator.py` | **Mostly dead code**: `build_system_prompt()`, `generate()`, `chat()` are never called in the live path | only `register_provider`/`get_provider` used (`chat.py:95-102`) |
| Memory service | `backend/core/memory.py` | Working; JSON-file, keyword scoring, atomic writes | `memory.py:150-194` (tmp+`os.replace`) |
| Retriever | `backend/core/retriever.py` | Working; hybrid semantic(MiniLM)+TF-IDF+keyword+phrase, neighbor expansion | `retriever.py:343-524` |
| Context optimizer | `backend/core/context_optimizer.py` | Working; word-budget chunk selection | `context_optimizer.py:9-107` |
| Doc processor | `backend/core/document_processor.py` | Working; 1500-word chunks, 200 overlap | `document_processor.py:10-49` |
| Doc summarizer | `backend/core/document_summarizer.py` | Working; 3-level hierarchical map-reduce with retry/backoff | `document_summarizer.py:718-810` |
| Memory data | `backend/data/memory.json` | 3 plaintext user memories, unencrypted | read 2026-09-17 |
| React frontend | `frontend/src/App.jsx` | Working; single 2,860-line file | whole file |
| Dead frontend components | `frontend/src/components/*`, `GhostFlowDiagram.jsx`, `ghost-flow.css` | Never imported (verified by import scan) | only `main.jsx → App.jsx` is live |
| Dead backend file | `backend/core/retriever_backup.py` | Never imported (verified) | grep across `backend/*.py` |
| Placeholder packages | `backend/{agents,audit,integrations,memory,orchestrator,permissions,retrieval,tasks,tools,artifacts}`, `workers/`, `infrastructure/`, `telegram-gateway/`, `tests/` | Empty (`__init__.py` or `.gitkeep` only) | file inventory |
| Dependency manifest | `requirements.txt` | **Wrong**: lists only the Gradio app's deps; none of the backend's | no fastapi/uvicorn/httpx/pypdf/docx/sentence-transformers/sklearn/dotenv |

---

## 4. Working Functionality Worth Preserving (spec §59)

1. **Honest capability refusal** — the legacy orchestrator refuses to pretend text-only models can see images (`legacy/gradio-app/orchestrator.py:533-561`). This is exactly the "never fake capability" principle; keep the pattern.
2. **Deterministic exact-page routing** — page requests are answered by deterministic chunk/page metadata, not LLM guessing, and missing pages produce a scripted refusal (`chat.py:1679-1697`). This is a seed of the spec's "deterministic policy over LLM" principle (§23).
3. **Trigger-gated memory capture** — memories are only stored when trigger phrases appear, greetings/short messages are skipped, and a keyword secret-blocklist exists (`chat.py:735-877`). Right direction, weak implementation (see threat model).
4. **Atomic memory writes** — temp file + `os.replace` (`memory.py:166-186`).
5. **Hybrid retrieval + neighbor expansion + budgeted context** — a solid, testable retrieval core.
6. **Hierarchical summarization** with concurrency limit, retry/backoff, and per-chunk fallback (`document_summarizer.py:34-72, 298-357`).
7. **Mermaid hardening on the frontend** — `securityLevel: "strict"` and HTML stripping before render (`App.jsx:204-236`). Good instinct against rendered-content injection.

---

## 5. Technical Debt & Correctness Defects

| # | Defect | Evidence | Impact |
|---|---|---|---|
| D1 | **Multi-turn context is broken**: frontend never sends chat history; `ChatRequest` has no history field; each turn is stateless | `App.jsx:905-925` (request body), `chat.py:122-130` | Conversational continuity silently absent |
| D2 | **GHOST system prompt is dead code**: live path calls `provider.generate_stream` with a single user message; `Orchestrator.build_system_prompt/generate/chat` never invoked | `chat.py:1722-1744` vs `core/orchestrator.py:103-381` | The designed identity/safety prompt has no effect |
| D3 | **Two `MemoryService` instances** (chat.py and graph.py) on one file → concurrent lost-update races | `chat.py:47`, `graph.py:13` | Memory corruption/loss under concurrency |
| D4 | ~50 lines unreachable code in `is_whole_document_request` | `chat.py:304-353` | Confusion, drift risk |
| D5 | `requirements.txt` missing all backend deps | see inventory | Backend not reproducible/installable as documented |
| D6 | No run instructions for the backend (no README, no start script, uvicorn invocation undocumented) | repo root | Onboarding/repro failure |
| D7 | Dead files: `retriever_backup.py`, `components/*`, `GhostFlowDiagram.jsx`, `ghost-flow.css`; `.gitignore` references a backup path that doesn't exist (`backend/core/memory_backup.py`) | verified imports | Repo noise |
| D8 | In-memory `documents` never evicted; embeddings + full text retained forever; lost on restart | `upload.py:13, 163-170` | Unbounded RAM; no durability |
| D9 | `print()`-based logging; memory context printed to stdout | `chat.py:944-960` | No observability; privacy leak in logs (see privacy doc) |
| D10 | Raw exception text streamed to client | `chat.py:1770-1779` | Internal detail disclosure |
| D11 | Typos: package `name: "frontedn"` and `<title>frontedn</title>` | `package.json:2`, `index.html` | Cosmetic; signals haste |
| D12 | `nvidia_api_key` may be `None` at startup; failure surfaces only at request time as 500 | `chat.py:74-102`, `openai_compatible.py:14-15` | Poor failure mode; no health gating |
| D13 | Model IDs not verifiable from code alone (`nvidia/nemotron-3.5-lightning-30b-a3b` in `.env.example`; `nvidia/deepseek-v4-flash` in `opencode.json`) — existence unconfirmed, keep as config, validate at startup | `.env.example:3`, `opencode.json:4` | Config rot |
| D14 | No tests at all | `tests/` empty | Everything above ships unverified |

---

## 6. Missing Abstractions (gap to spec §3 target architecture)

- **Identity/auth**: none. API is unauthenticated (see threat model T1).
- **Policy/permission engine**: none; `backend/permissions/` is empty.
- **Tool layer**: none; `backend/tools/` empty; graph endpoint *displays* tool nodes as "planned" (which at least does not fake capability).
- **Task state machine / supervisor / agents**: none; `backend/tasks`, `backend/orchestrator/`, `backend/agents/` empty.
- **Event bus / perception / temporal world model**: none.
- **Model router**: `ChatRequest.provider/model` exists but only one provider is registered and selection is effectively fixed to `nemotron` (`chat.py:95-102`); no capability/privacy/cost-aware routing (spec §12).
- **Audit/verification/replay**: none; `backend/audit/` empty.
- **Memory tiers**: single flat store; no working/session/episodic split, no TTL/retention, no contradiction handling (spec §9).
- **Config layer**: env vars read inline in `chat.py`; no central settings object.

---

## 7. Assessment Verdict

- The **Gradio app** (`legacy/gradio-app/app.py`, `orchestrator.py`, `models.json`) is a quarantined experiment, kept out of the GHOST backend (two apps named "orchestrator" in one repo invites confusion — `legacy/gradio-app/orchestrator.py` vs `backend/core/orchestrator.py`).
- The **GHOST prototype** is a credible V0.5: document RAG + memory + streaming + a distinctive UI. Its architecture (provider ABC, retriever, memory service) is worth building on rather than rewriting.
- The gap to the GHOST vision is almost everything security/privacy/agency-related — which is also the stated top priority order of the spec (PRIVACY → SAFETY → …). Therefore the next milestones must add **boundaries** (auth, policy, tool gating) *before* adding **capabilities** (tools, agents, autonomy).

See: `02-target-architecture.md`, `03-migration-plan.md`, `04-threat-model.md`, `05-privacy-assessment.md`, `06-mvp-roadmap.md`.
