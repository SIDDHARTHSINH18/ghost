# GHOST — Personal AI Operating System (prototype)

GHOST is a privacy-first, permissioned AI layer. This repository currently
contains the **V0.5 prototype**: a FastAPI backend (document RAG + persistent
memory + streaming chat via NVIDIA Nemotron) and a React frontend
(knowledge-graph UI, chat, document upload).

- Architecture assessment: `docs/01-architecture-assessment.md`
- Threat model: `docs/04-threat-model.md`
- Privacy assessment: `docs/05-privacy-assessment.md`
- Migration plan (M0 → V1 → …): `docs/03-migration-plan.md`
- Roadmap: `docs/06-mvp-roadmap.md`

The legacy Gradio experiment lives in `legacy/gradio-app/` and is not part
of the GHOST backend.

---

## Prerequisites

- Python 3.11+ (a local `venv/` may already exist in this folder)
- Node.js 18+ (frontend)
- An NVIDIA API key (Nemotron via `https://integrate.api.nvidia.com/v1`)

## 1. Configure

```bat
copy .env.example .env
```

Then edit `.env` and set `NVIDIA_API_KEY`.

The backend **refuses to start** without it.

## 2. Run the backend

```bat
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Check: <http://127.0.0.1:8000/health> should return `{"status": "ok", ...}`.
A live provider check (network call) is at `/health/provider`.

## 3. Run the frontend

```bat
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## 4. Run the tests

```bat
venv\Scripts\pip install -r requirements-dev.txt
venv\Scripts\python -m pytest
```

## What works today

- Chat with streaming responses (cloud model: NVIDIA Nemotron)
- Multi-turn conversation (history sent with each request)
- PDF / DOCX / TXT upload → chunking → embeddings → hybrid retrieval
- Exact-page questions with deterministic page lookup; missing pages are
  refused, never hallucinated
- Whole-document hierarchical summarization (cached per document)
- Persistent keyword memory with duplicate handling
- Memory management: view, delete one, forget all (`GET/DELETE /api/memory`)
- Document management: list uploaded documents, delete one
  (`GET/DELETE /api/documents`), with post-deletion verification
- Knowledge-graph visualization of documents/memory/tools
  (memory labels only — content stays on the memory API)

## Resource limits (configurable)

There is **no limit on the number of documents**. Limits are real resource
protections, configured via environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `GHOST_MAX_UPLOAD_MB` | `50` | Maximum size of one uploaded file |
| `GHOST_MAX_TOTAL_STORAGE_MB` | `500` | Aggregate cap across all uploaded documents |
| `GHOST_ALLOWED_EXTENSIONS` | `.pdf,.docx,.txt` | Uploadable file types |

Document processing is serialized (`upload_lock`) so concurrent uploads
queue instead of multiplying memory/CPU pressure.

## Security & privacy status (read before exposing this to anyone)

- **No authentication yet** (planned M2) — bind to loopback only; anything on
  this machine can call the API.
- Every message/document/memory is sent to the NVIDIA cloud API; no
  classification/redaction yet (planned V4). See
  `docs/05-privacy-assessment.md`.
- `backend/data/memory.json` stores memories in **plaintext**.
- Never commit or share your `.env`.

## Repository layout

```
backend/          FastAPI app (api/, core/, providers/)
frontend/         React + Vite UI
docs/             Architecture, threat model, privacy, roadmap
legacy/gradio-app/ Quarantined Gradio experiment (not maintained)
tests/            pytest suite
```
