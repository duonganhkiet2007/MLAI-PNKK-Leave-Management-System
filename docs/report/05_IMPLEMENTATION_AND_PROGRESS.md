# Implementation and Progress

Status reflects the current repository only:

- `DONE`: implemented and covered for the stated demo scope.
- `PARTIAL`: executable path exists but policy/coverage is incomplete or has a known mismatch.
- `DEMO-ONLY`: intentionally suitable for local demonstration, not a production control.
- `TODO`: no sufficient implementation/evidence.

## Progress matrix

| Module | Status | Main files | Current behavior | Remaining work |
|---|---|---|---|---|
| Structured Form | `DONE` | `frontend/app.js`, `leave_router.py`, `domain.py`, `orchestration.py` | Typed facts; protected context rejected; 0 LLM calls; routes through full engine/persistence. | Production validation/UX acceptance and accessibility evidence. |
| Free-text parser | `PARTIAL` | `agent_orchestrator.py`, `prompts.py`, `schemas.py`, `llm_client.py` | One Ollama LLM call; strict schema; no trusted fields; fails with 503 if model unavailable. | Labeled accuracy evaluation; support a safe separate proof association flow; multilingual/date robustness. |
| Rule Engine | `PARTIAL` | `rule_engine.py`, `taxonomy.py`, `domain.py` | Deterministic staged evaluation for annual, medical, special paid, statutory/other unpaid, calendar/overlap/balance/authority. | Align sick >5 routing; implement or formally exclude maternity/work accident; resolve unsupported-type outcome mismatch; expand policy coverage. |
| Calendar | `PARTIAL` | `calendar_service.py`, `calendars/*.json` | Configurable working week; verified 2026/2027 holidays; compensatory days; fail-closed on unknown year. | Govern yearly updates; foreign-national/special schedules; verify 2027 provisional source status; cross-year compensatory edge cases. |
| Proof upload | `DONE` | `leave_router.py`, `storage.py`, `migrations.py` | Owner-bound proof record; PDF/JPEG/PNG magic/MIME check; 10 MB limit; protected read; HR verification endpoint. | Malware scanning, encryption, retention, object storage and production content handling. |
| Proof/VLM | `PARTIAL` | `vlm_inspector.py`, `ai_stack.py`, `orchestration.py` | Ollama VLM extracts facts/diagnostics; no invented proof on failure; persists analysis; output remains unverified. | Fix prompt enum/profile wiring, PDF handling, inference cache, quality evaluation and authenticity disclaimers. |
| Escalation | `DONE` | `taxonomy.py`, `rule_engine.py`, `storage.py`, `orchestration.py` | Deterministic target/error/question; persisted approval steps; role/scope checks; multi-step unpaid flow. | Notifications, delegation/absence coverage and resolve policy/code authority gaps. |
| Human decision | `DONE` | `leave_router.py`, `orchestration.py`, `storage.py` | Button or parsed free-text action; request-info/reject/conditional/approve; revision check; fresh re-evaluation. | Production identity, approval SLA/reminders and stronger immutable audit governance. |
| HR proof verification | `DONE` | `leave_router.py`, `domain.py`, `rule_engine.py` | Only HR role can verify; employee cannot self-verify; linked requests re-evaluate; completed proof reuse guarded. | Issuer verification integration and dual-control policy if required. |
| Anti-abuse | `PARTIAL` | `storage.load_context`, `rule_engine.py` | Flags cumulative approved annual days in the same calendar month over auto threshold and routes Direct Manager. | Policy-required audit detail (related request IDs/period/total/final approver); clarify whether pending requests count. |
| Overlap/concurrency | `DONE` | `storage.py`, `orchestration.py`, `test_api_e2e.py` | Full/partial overlap outcomes; unique bookings/debits; `BEGIN IMMEDIATE`; revision conflict; final recheck. | Multi-instance/load testing and database-level production strategy. |
| Annual ledger/refund | `DONE` | `storage.py`, `migrations.py` | Per-working-day debit, atomic balance change, proven refund, allocation ledger. | Reconciliation/reporting and production accounting controls. |
| Vietnamese UI | `DONE` | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` | Staff/manager portals, Vietnamese labels/summaries, proof view, policy tree, verify screen; some English locale strings exist. | Formal localization review, accessibility and responsive/browser testing. |
| Demo identity / roles | `DEMO-ONLY` | `leave_router.actor`, `meta_router.list_employees`, `migrations.py`, frontend selectors | `X-Actor-ID`/query selects actor; exact title-to-role seed mapping; department scopes. | SSO/OIDC, session/token validation, least privilege, CSRF/security controls. |
| Database | `DEMO-ONLY` | `database.py`, `migrations.py`, `storage.py` | Local SQLite WAL; migrations; requests/proofs/steps/ledger/bookings/audit; seed/reset support. | Production RDBMS, backups, encryption, migration governance, retention and HA. |
| Local file storage | `DEMO-ONLY` | `leave_router.py`, `backend/uploads` | Local upload folder and direct protected file response. | Object storage, antivirus/CDR, lifecycle, encryption and signed access. |
| Verify Harness | `DONE` | `verify_router.py`, `test_cases.json`, frontend verify tab | Five marked cases; 3 auto + 2 escalate targets; no persistence and 0 LLM calls; custom simulation endpoint. | Broader harness and CI artifact export; avoid presenting five cases as full evaluation. |
| Automated tests | `DONE` | four test modules + `tests/scenarios.py` | 30 canonical cases plus invariants/API/concurrency/model-call contracts. | Run in reproducible CI; add real-model, security and property tests. No fresh runtime result in this audit. |
| Performance instrumentation | `PARTIAL` | `orchestration.py`, `main.py`, `leave_router.py` | Records rule/template/total evaluation and API timing; warm-up/status endpoints exist. | Controlled benchmark and p50/p95/throughput/memory results. Current performance: `NOT MEASURED`. |
| Production deployment/security | `TODO` | No production deployment manifests/security package | No evidence of production-ready deployment. | TLS/reverse proxy, secrets, SSO, restricted CORS, authorization on admin endpoints, monitoring, backup/DR, privacy/security review. |

## Implementation notes by layer

### Deterministic core

The most complete layer is the annual/operational workflow: calendar calculation, balance, notice, quota, handover, overlap, authority and atomic mutation. Medical and special-paid logic also validate verified proof facts. Maternity and work accident are recognized but intentionally stop at HR.

### AI layer

AI is constrained to extraction/presentation. Call-count tests define a low-call critical path. Real-model quality has not been evaluated in this repository, so model accuracy and latency must not be inferred from UI strings or comments.

### State and audit

SQLite stores request snapshots, result/trace JSON, approval steps, proof records and ledger entries. State mutation is transaction-scoped. The audit mechanism records evaluation and actions, but it is not demonstrated as immutable/compliance-grade.

### UI/demo layer

The SPA exposes staff and manager modes, proof inspection, human actions, calendar/policy visualizations and harness execution. Actor switching, reset operations and broad CORS make the demo convenient but are not production security.

## Undated artifact evolution

No reliable project dates or sprint metadata exist in the inspected files, so this is an undated code-artifact sequence rather than a chronological claim:

1. `raw_policy.json` preserves the historical source policy.
2. `policy_rules.md` establishes the newer authoritative policy and marks additions beyond raw policy.
3. Legacy workflow/escalation docs describe an earlier in-process LLM architecture and are explicitly marked deprecated.
4. Current `ai_stack.py` centralizes two Ollama models; current prompts restrict LLM to extraction.
5. Current rule/storage layer adds five outcomes, verified calendars, proof verification, atomic ledger/bookings, multi-step approval and anti-abuse detection.
6. Current tests add 30 canonical scenarios, API/concurrency checks and exact model-invocation contracts.

No dates are assigned because the repository evidence inspected here does not establish them.
