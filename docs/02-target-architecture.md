# GHOST — Target Architecture

Date: 2026-09-17
Scope: a realistic target that (a) realizes the master spec's priorities (privacy → safety → correctness → reliability → capability), (b) reuses the working prototype components (`01-architecture-assessment.md` §4), and (c) is reachable in incremental milestones — not a big-bang rewrite.

---

## 1. Design Stance (decisions that shape everything else)

1. **Single host, single user, local-first.** GHOST V1–V3 is a personal system running on the user's own PC. No multi-tenant server. This drastically reduces the identity problem: one local user + future device trust (V5), not user management.
2. **Boundary before capability.** The spec's non-negotiables (§69) require deterministic security independent of the LLM. So the Policy Engine, Capability Firewall, and Audit Log are *prerequisites* for the first tool — not features to add "later".
3. **Deterministic core, LLM at the edges.** Routing, task state, permissions, verification triggers = code, not prompts. The LLM proposes; the state machine disposes.
4. **Keep the working prototype components** (retriever, memory service, provider abstraction, summarizer) and wrap them with interfaces rather than rewriting them.
5. **The Gradio legacy app is quarantined** (moved to `legacy/` or removed) — one product per repo layout.

---

## 2. Target Component Map (V1 → V3)

```
                        ┌──────────────────────────────┐
                        │  frontend (React)            │
                        │  Chat / Graph / Task view     │
                        │  + Approvals / Audit view     │
                        └──────────────┬───────────────┘
                                       │ HTTPS, session token (loopback only by default)
                        ┌──────────────▼───────────────┐
                        │  backend/main.py (FastAPI)   │
                        │  ─ API layer: validation,    │
                        │    auth middleware, rate     │
                        │    limits, structured errors │
                        └──┬───────────┬───────────┬───┘
          ┌────────────────┘           │           └───────────────┐
 ┌────────▼─────────┐        ┌────────▼────────┐        ┌─────────▼─────────┐
 │ IDENTITY &       │        │ TASK ENGINE     │        │ CONTEXT SERVICES  │
 │ SESSIONS         │        │ (state machine) │        │ (existing, wrapped)│
 │ local OS-auth or │        │ CREATED→…→      │        │ • retriever       │
 │ passphrase;      │        │ COMPLETED/FAILED│        │ • memory svc      │
 │ tokens, revoke   │        │ + success       │        │ • context optimizer│
 └──────────────────┘        │   contracts     │        │ • summarizer      │
                             └───┬─────────┬───┘        └─────────┬─────────┘
                                 │         │                      │
                      ┌──────────▼──┐  ┌───▼────────────┐  ┌──────▼──────┐
                      │ SUPERVISOR  │  │ MODEL ROUTER   │  │ WORLD MODEL │
                      │ picks agent │  │ (providers +   │  │ (V2: events │
                      │ + tool set  │  │  policy table) │  │ + entities; │
                      └──────┬──────┘  └───┬────────────┘  │ SQLite)     │
                             │             │               └─────────────┘
                      ┌──────▼─────────────▼──────────────────────┐
                      │ SECURITY SENTINEL (deterministic)         │
                      │  Policy Engine → Capability Firewall      │
                      │  → Approval Router → Audit Log            │
                      └──────┬────────────────────────────────────┘
                             │
                      ┌──────▼───────┐
                      │ TOOL LAYER   │  read_file, write_file (project-scope),
                      │ (registry;   │  run_tests, http_get …
                      │ each tool =  │  every call: agent, task, capability,
                      │ schema +     │  resource, risk, decision, audit row
                      │ policy)      │
                      └──────────────┘
```

### What already exists and is kept
- `backend/providers/*` → grows into the **Model Router** (add capability/privacy/cost metadata per model; selection policy in code).
- `backend/core/{retriever,memory,context_optimizer,document_*}` → the **Context Services** block, wrapped behind interfaces.
- `/api/graph` + force-graph UI → grows into the **Awareness Map** (but must only visualize real state — remove/flag the hardcoded "planned" tool nodes, `graph.py:240-289`).
- `/api/chat` streaming + `__SOURCES__` citation protocol → kept, moved behind the session middleware, upgraded to a structured first event (JSON instead of in-band string, so content can't spoof citations).

### What is new build
- **Identity & Sessions** (V1, minimal): loopback-only bind by default, a session token issued after local authentication, expiry/revocation. Not device-crypto yet — that's V5.
- **Task Engine** (V1): persisted task records + explicit state machine (spec §20) + per-task **success contract** (§19) + **change budget** (§21).
- **Security Sentinel** (V3, but its *interfaces* land in V1 so tools are born gated): policy table (deterministic rules), capability check per tool call, approval hook, append-only audit log.
- **Tool layer** (V1: 2–3 read-only tools; V3: write tools behind approval): each tool declares JSON schema, allowed scopes, risk class, dry-run support.
- **World Model / Event Bus** (V2): SQLite-backed entity/relation/event store; the perception scheduler comes later (V7) — do not build screen/desktop perception early.

---

## 3. Storage Plan (spec §61: no single-tech dogma)

| Data | Store | Why |
|---|---|---|
| Memories | JSON now → **SQLite** (encrypted at rest via SQLCipher or OS-level) in V2 | Needs queries, TTL jobs, deletion semantics; single user ⇒ no server DB |
| Documents/chunks/embeddings | SQLite + local vector table (or keep in-memory per-session with explicit lifecycle) | Current in-RAM-forever dict is unbounded (`upload.py:13`) |
| Tasks / states / tool calls / audit | SQLite, append-only for audit | Transactional, replayable (GHOST Replay, §43) |
| Secrets | **Never in DB** — OS keychain (Windows Credential Manager) or at minimum `.env` outside any shared/published copy, loaded at startup only | Spec §5 |
| World model (V2) | Same SQLite, separate tables | Joins with tasks/memories for "what changed before the error" queries |

---

## 4. Trust Boundaries (must be explicit in code)

1. **Browser ↔ Backend**: session token required on every route except health; rate-limited.
2. **Backend ↔ External model APIs**: only through the Model Router; every outbound payload passes the classification/redaction step (V3); local-only mode available for SENSITIVE+ data.
3. **LLM ↔ Tools**: the model never executes anything directly; it emits *proposals* (structured tool calls) that the Sentinel evaluates deterministically. This is the core spec §22 requirement: "the main AI must never be able to override security merely by generating a different instruction".
4. **Untrusted content (documents, web, tool outputs) ↔ System policy**: untrusted text is tagged and never concatenated into system-prompt position (current code puts document text inside the user message — acceptable start — but memory and document text must remain clearly delimited and citation-protocol strings must be escaped; see threat model T4/T7).

---

## 5. ADRs To Write First (spec §55)

- **ADR-001** Storage: SQLite (single-file, transactional, local-first) vs JSON files vs server DB — decide before V2 memory work.
- **ADR-002** Auth model for a single-user local system: OS-auth bridge vs passphrase + token; loopback-only default.
- **ADR-003** Tool-call protocol: JSON-schema function calls interpreted by the Task Engine (not free-form shell).
- **ADR-004** External-model data policy: classification levels + redaction + local fallback chain (spec §34, §41).
- **ADR-005** What the audit log records (metadata yes, content minimal) — ties to privacy doc.
- **ADR-006** Sandboxing story for V3 write-tools on Windows (job objects / restricted tokens / containers).
