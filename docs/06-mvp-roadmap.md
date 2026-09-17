# GHOST — MVP Roadmap & First Milestone

Date: 2026-09-17

---

## 1. Highest-Value First Milestone (recommendation)

**M0 "Hygiene & Truthfulness"** (migration plan §M0) — one focused session, zero new features, makes everything after it trustworthy:

1. Fix `requirements.txt` (backend currently uninstallable as documented).
2. Wire the dead GHOST system prompt into the live path.
3. Send conversation history (multi-turn is silently broken today).
4. Single shared `MemoryService` (fixes lost-update race).
5. Quarantine legacy Gradio app; delete verified-dead files.
6. Stop logging memory content; generic client errors.
7. First test suite over the pure-function core (chunker, intent routing, memory ranking).
8. README with real run instructions.

Plus one **non-code action today**: the T0 check — if this project (with `.env`) was ever pushed/shared, rotate the NVIDIA API key.

**Why this first, not a flashy feature**: every GHOST principle (verify before claiming, honest failure, privacy) is currently violated by small mechanical defects (D1, D2, D5, D10). Fixing them costs hours and converts the prototype from "appears to work" to "verifiably works" — the foundation the spec demands before capability growth.

After M0: **M1 (memory/document user control)** → **M2 (auth boundary)** → **V1 (task loop MVP)**.

---

## 2. V1 Definition (the MVP that proves GHOST's central concept)

A user gives GHOST a task that requires *reading the environment*; GHOST plans, uses **read-only tools gated by a deterministic policy**, verifies the result against a **success contract**, and completes or fails honestly — all visible in a task timeline.

### In scope
- Task Engine + persisted state machine + crash recovery
- Success contracts + verification runner (PASS is the only path to COMPLETED)
- Change budgets (tool calls, model calls, time)
- 3 read-only tools: `read_file` (project allowlist), `list_dir`, `http_get` (domain allowlist)
- Security Sentinel v0: deterministic policy + append-only audit
- Approval card UI (timeout = deny)
- Session auth (from M2)

### Explicitly out of scope
Write tools, shell, browser automation, multi-agent, model routing, gestures, multi-device, 24/7 perception. *(The master spec's V5–V7 features stay parked.)*

### Demonstration scenario (spec §68, honest version)
1. "Find which file in `src/` defines `MemoryService` and summarize its search scoring." → plan (list_dir → read_file → summarize) → sentinel ALLOW log → verify (answer cites file + line evidence) → COMPLETED with timeline.
2. Same task phrased to demand a *write* → policy DENY → GHOST explains and requests approval → no card interaction → timeout deny → task ends BLOCKED, audit row exists.

### Acceptance tests (must pass before calling V1 done)
- [ ] Kill -9 the server mid-task → restart → task resumes in correct state (recovery).
- [ ] Injected document text ordering a tool call → proposal appears, sentinel DENYs per policy, nothing executes.
- [ ] Verification fails → task goes RETRYING with a new hypothesis, never COMPLETED.
- [ ] Budget exhausted → task BLOCKED with honest reason, not silent truncation.
- [ ] Audit log contains every tool decision with correlation ID.
- [ ] No memory content in any log output.

---

## 3. Version Ladder (mirrors spec §58, adapted to reality)

| Version | Theme | Key deliverables | Depends on |
|---|---|---|---|
| M0 | Truthfulness | deps, prompt wiring, history, tests, hygiene | — |
| M1 | User data control | memory/doc CRUD + UI, notices, secret rejection | M0 |
| M2 | Identity boundary | sessions, rate limits, structured citations | M1 |
| V1 | Task loop MVP | tasks, contracts, budgets, 3 read-only tools, sentinel, audit, approvals | M2 |
| V2 | Memory + world model | SQLite+encryption, tiers, TTL, events, real graph | V1 |
| V3 | Security + sandbox | write tools + approvals, git checkpoints, red-team suite | V1 |
| V4 | Model router | multi-provider, classification routing, redaction, budgets, degraded mode | V1 |
| V5 | Multi-device trust | device identity, tiers, approval router | V3 |
| V6 | Gestures | local camera pipeline (PIA required first) | V5 |
| V7 | 24/7 awareness | event bus, perception scheduler, importance filter | V2, V4 |
| V8 | Replay + EVAL + hardening | timeline UI, metrics harness, adversarial CI | V1+ |

## 4. Standing Rules For Every Milestone

1. Nothing is "done" until its acceptance test passes (spec §19).
2. Every security-relevant change ships with a red-team test (spec §47).
3. Every new data store ships with view/delete affordances (spec §35).
4. ADR written for each decision listed in `02-target-architecture.md` §5.
5. Never claim capability that isn't demonstrated — including in the UI (the "planned" tool nodes in `/api/graph` are the tolerated exception *only* until V2 makes the graph state-driven).
