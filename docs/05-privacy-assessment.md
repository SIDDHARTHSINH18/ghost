# GHOST — Privacy Impact Assessment (Current State)

Date: 2026-09-17
Method per spec §31/§38: for each existing feature — data collected, why, who can access, where processed, retention, what can go wrong, mitigation, user control. No compliance claims are made (spec §37); this is an engineering privacy review.

---

## 1. The Headline Finding

**Everything the user types, every uploaded document's text, and every stored memory is transmitted to NVIDIA's cloud API (`integrate.api.nvidia.com`) on nearly every chat turn** (`backend/api/chat.py:1722-1744`, `openai_compatible.py:43-93`). There is no data classification, no redaction, no local-model fallback, and no indication to the user in the UI that content leaves the machine.

This is the single largest gap between the product's stated identity ("privacy-first", spec §1) and its behavior. It is *acceptable for a personal prototype* if the user knowingly accepts it — but it must become an explicit, visible configuration (data classification → routing policy), not an implicit property.

---

## 2. Data Inventory (verified)

| Data | Collected by | Stored where | Retention | Leaves machine? |
|---|---|---|---|---|
| Chat message text | `/api/chat` | RAM only | Session (lost on restart) | **Yes** → NVIDIA, as prompt |
| Uploaded document full text + per-page text + chunks + embeddings | `/api/upload` (`upload.py:163-170`) | RAM (`documents` dict) | **Forever until restart** (no eviction, no delete API) | **Yes** → retrieved chunks in prompts; full text also sent during hierarchical summarization (`document_summarizer.py`) |
| Memories (auto-captured facts/decisions/preferences) | `save_conversation_memory` (`chat.py:735-877`) | `backend/data/memory.json`, **plaintext, unencrypted** (`memory.py:84-91`) | **Indefinite** — no TTL, no retention policy | **Yes** → injected into prompts when retrieved (`chat.py:1593-1618`); also echoed to **stdout** (`chat.py:944-960`); also returned in full by `/api/graph` (`graph.py:174-215`) |
| Memory metadata (type/importance/confidence/timestamps) | memory service | same file | Indefinite | Via graph endpoint |
| API key | `.env` | Disk, plaintext | Until rotated | To NVIDIA as bearer (necessary); **must never appear in logs/prompts** (currently not sent to model — verified) |
| Frontend layout + active document id/name | `App.jsx:32-47, 552-566` | Browser localStorage | Until cleared | No |
| Server console logs | `print()` calls throughout backend | stdout | Process lifetime | Memory *content* is printed (privacy defect, see below) |

## 3. Per-Feature PIA

### 3.1 Chat
- **Why collected**: to answer.
- **What can go wrong**: (a) sensitive content (health, legal, credentials pasted for "help me with this error") silently goes to a third-party cloud; (b) memory containing earlier sensitive statements is re-sent whenever keyword-retrieval surfaces it; (c) stdout logging writes retrieved memory content to console (`chat.py:944-960`).
- **Mitigation**: (1) UI indicator + setting: "cloud model / local model" with a data-classification step in the router (V4, spec §34); (2) near-term: redact obvious secrets *before* outbound calls (entropy detector — dual-purpose with threat T5); (3) log only IDs and scores, never content; (4) document NVIDIA's data terms in `docs/` and link from UI.

### 3.2 Document upload / RAG
- **Why**: the core feature (document Q&A with page citations).
- **What can go wrong**: entire documents persist in RAM indefinitely with no user-visible list and no delete; unencrypted embeddings of the full text; whole-document summarization sends the *entire* document through the cloud model in batches (`document_summarizer.py:78-205`) — the user asked one question, but the whole file transits.
- **Mitigation**: document registry endpoint (list/get/delete); TTL/eviction; a "summarize whole document" action that *asks* before the full-content cloud pass; classification tag per document that the router respects.

### 3.3 Memory
- **Why**: continuity (spec §9).
- **What can go wrong**: plaintext unencrypted at rest; auto-capture can store sensitive sentences that only *contain* trigger phrases — the secret blocklist is keyword-only (`chat.py:814-823`), so e.g. a connection string or random-token paste without the words "key/token" is kept forever and repeatedly shipped to the cloud; **no user-facing way to view, edit, or delete memories exists** (the service has `delete/clear/update` methods, `memory.py:897-1012`, but no API route exposes them — verified by route scan); no contradiction handling, so stale facts persist.
- **Mitigation** (ordered): (1) memory CRUD API + UI panel (this also serves threat T4); (2) entropy-based secret rejection; (3) encryption at rest (SQLCipher or OS-protected file) in V2; (4) provenance display (the `source`/`metadata.automatic` fields exist — surface them); (5) TTL + "forget everything" command; (6) explicit retention settings (spec §35).

### 3.4 Knowledge-graph endpoint
- **Why**: visualization.
- **What can go wrong**: `/api/graph` returns up to 12 full memory contents to *any* caller (unauthenticated — threat T1).
- **Mitigation**: labels only in graph; content via authenticated memory endpoint.

### 3.5 Frontend
- localStorage holds only layout + active document name/id — proportionate. No third-party scripts loaded (verified `index.html`/`App.jsx` — only local assets). Mermaid `securityLevel: strict` limits rendered-content risks.

## 4. Principles Scorecard (spec §31)

| Principle | Status |
|---|---|
| Data minimization | **Partial** — trigger-gated memory is good; whole-doc cloud summarization and full-text persistence are not minimal |
| Purpose limitation | **Weak** — no purpose tracked per datum |
| Local-first processing | **No** — 100% cloud inference; embeddings are local (MiniLM) — the only local ML today |
| Explicit consent | **No** — no consent/notice that content leaves the machine |
| Least privilege | **N/A yet** (no tools); API itself violates it (T1) |
| Encryption | Transport only (HTTPS to provider); **no encryption at rest** for memory |
| Retention control | **None** — no TTL, no delete endpoints, no eviction |
| Auditability | **None** — no log of what was sent where |
| User control | **Weak** — one-way system; no view/edit/delete of stored data |

## 5. Third-Party Privacy (spec §33)

Uploaded documents may contain other people's personal data (letters, HR docs, medical PDFs). Today such data is embedded, stored, summarized, and shipped to a cloud provider with no notice. Minimum bar before any sharing/demo of GHOST: warn on upload ("this document's text will be sent to the configured cloud model"), and provide a local-only mode for such files. Recording laws are out of scope until camera/mic features exist (V6+) — the PIA must be redone before those ship.

## 6. Priority Remediation (cheapest-first, mapped to roadmap)

1. **M0**: stop printing memory content to stdout; generic client errors (threat T5).
2. **M1**: memory CRUD API + UI (view/edit/delete/forget-all) — restores user control over the only persistent store.
3. **M1**: upload consent indicator + document registry with delete.
4. **M2**: entropy-based secret rejection in memory capture; retention/TTL settings.
5. **V2**: encrypted storage, SQLite migration (ADR-001).
6. **V4**: data classification + model routing policy (SENSITIVE ⇒ local/redacted/deny), external-transmission audit log ("what left the machine, when" — spec §56 without content).
