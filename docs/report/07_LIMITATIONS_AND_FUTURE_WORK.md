# Limitations and Future Work

## CURRENT LIMITATIONS

### 1. Policy coverage is incomplete

- `MATERNITY` and `WORK_ACCIDENT` are represented in schemas/UI/VLM profiles, but `rule_engine.py` immediately returns `ESCALATE / HR / AUTOMATION_SCOPE_UNSUPPORTED`. Detailed maternity entitlement in `policy_rules.md` is not implemented.
- Policy describes unsupported leave type as auto-reject; current engine treats an unknown/missing type as correction.
- `PUBLIC_HOLIDAY` and `WEEKLY_REST` are calendar day types, not values accepted by `LeaveType`.

Impact: final report must label these paths `PARTIAL`, not supported end-to-end policy automation.

### 2. Calendar scope is finite

Only `holidays_2026.json` and `holidays_2027.json` exist. An unknown/unverified year escalates to HR. Working week is globally configurable, but individual shifts, foreign-national holidays and complex organization calendars are not modeled. The 2027 file scope text references a proposed schedule, so governance/reverification is needed before relying on it operationally.

### 3. Demo authentication and administration

Identity is supplied through `X-Actor-ID` or query `actor_id`; `/api/meta/employees` exposes the demo actor directory. There is no password, SSO, token or session verification. CORS permits `*` while credentials are enabled. `/api/meta/reset-database` has no actor dependency and can clear request/proof/audit/ledger data plus local uploads. This is explicitly demo behavior, not production security.

### 4. SQLite and local files

The application uses one local SQLite database in WAL mode and a local uploads folder. Transactions and concurrency invariants are tested, but there is no evidence for multi-instance deployment, HA, replication, encrypted backup, object storage, retention or disaster recovery.

### 5. VLM extracts facts; it does not establish authenticity

VLM returns issuer/name/date/signature/readability and possible tamper/AI-edit signals. It does not verify an issuer registry, PKI signature, source-system record or legal authenticity. HR must set proof verification status. Model diagnostic fields can be uncertain and should not be presented as a confirmed fraud finding.

### 6. VLM integration has technical edge gaps

- Real inference is called without forwarding `leave_type` into `_try_ollama_extract`, so the generic prompt profile is used.
- Prompt readability vocabulary and Pydantic vocabulary differ.
- The persisted inspection-mode label says 3B while configured default VLM is 7B.
- Multi-page PDF rendering is not explicitly implemented.
- VLM can rerun on re-evaluation; there is no hash-based cache.
- A stored proof with real inference failure safely remains unverified, but this blocks automation until HR/manual recovery.

### 7. Free text and proof cannot be submitted together

After LLM parsing, `process_new_request` forces `proof_id=None` and `attachment_type='none'` to prevent a model from inventing attachments. This is a sound trust boundary but means a free-text submission cannot associate an already uploaded proof in the same request path.

### 8. LLM availability and cold start

Text parsing and free-text manager feedback have no non-model fallback. If Ollama/model/JSON validation fails, API returns 503 and users must use structured form/buttons or retry. Startup launches background warm-up, but readiness/cold-start behavior has not been benchmarked.

### 9. Performance is not established

Code records rule/template/total/API timings and exposes model status, but there is no controlled benchmark output in the repository. LLM cold start, VLM latency, p95 end-to-end latency, throughput and resource use are all `NOT MEASURED`. Timing claims in comments/UI are estimates only.

### 10. AI quality is not established

Tests mock model calls and verify schemas/call counts. There is no labeled-corpus evaluation for Vietnamese date/type/relation extraction, document OCR, name matching, tamper signals or false positives. The deterministic correlation score is an internal heuristic, not a calibrated probability.

### 11. Anti-abuse audit is partial

Detection totals previously completed annual days in the same calendar month and raises `FLAG_ABUSE_PATTERN`. Policy asks the audit to include employee, period, total, related requests and final approver. Current audit stores the engine result/action details but not that full structured related-request payload.

### 12. Approval and role configuration limitations

Current authority is fixed as follows: Annual ≤2 auto, 3–5 Direct Manager, 6–19 Department Head and ≥20 CEO; `SICK_MEDICAL` 1 working day with valid/verified proof is auto-approved and ≥2 working days routes to Direct Manager; Special Paid and Statutory Unpaid route to Direct Manager. Human approval can waive notice and quota only. Role seeding recognizes only exact sample job titles, so unknown titles need explicit configuration.

### 13. UI analysis contains presentation logic beyond the core engine

The analysis endpoint builds a 13-node display checklist from flat fields and includes labels such as “LLM summary” even when the content is deterministic template output. Some exact-name comparison in display code is stricter than the engine's approximate matching. The checklist is explanatory UI data, not a second policy engine.

### 14. Existing documentation is partly stale

Legacy files describe in-process Qwen 7B, LLM-generated routing, invalid-reason guardrails and schema designs that do not match runtime. `LUONG_HOAT_DONG.md` collapses correction/rejection into escalation and implies broader annual deduction/file+text behavior than code. `HUONG_DAN_CHAY_LOCALHOST.md` has stale dependencies/model assumptions and does not invoke pytest correctly. `KHAO_SAT_DAC_TRUNG_DATABASE_SAMPLE.md` proposes tables/fields beyond the actual migration. Those documents must not be used as implementation evidence without checking code.

### 15. Legal and production assurance are absent

The repository states legal/policy references but provides no legal sign-off, privacy impact assessment, threat model, pentest, audit-retention policy, accessibility certification or production deployment evidence. The policy itself says it is simplified for hackathon demo scope.

## FUTURE WORK

These are proposed tasks, not current features.

### Policy correctness first

1. Resolve remaining policy/code gaps in a signed traceability matrix, including unknown leave type handling and the incomplete maternity/work-accident paths.
2. Implement explicit maternity and work-accident rules only after legal/policy review, including proof, entitlement, authority and HR Ops workflow.
3. Add traceability tests that preserve current routing: Special Paid requires verified proof before Direct Manager review, while Statutory Unpaid does not require proof and routes to Direct Manager.
4. Add structured anti-abuse audit fields with related request IDs, month, prior approved total, current-request total and final approver.
5. Add calendar governance: annual approval, version/effective date, country/employee schedule and revalidation.

### Security and platform

1. Replace demo actor selection with SSO/OIDC and server-validated roles/scopes.
2. Restrict CORS; protect/remove reset/debug endpoints; add CSRF/rate-limit/security headers as applicable.
3. Move to a production RDBMS and object storage with encryption, malware scanning, backup/restore, retention and audit export.
4. Define secrets management, TLS/reverse proxy, structured logging, metrics, alerting and incident response.
5. Perform privacy/security review for medical and family documents.

### AI/VLM engineering

1. Forward `leave_type` to real VLM prompts; normalize enums; add robust PDF page rendering and cache inference by content hash/model version.
2. Keep VLM results explicitly unverified; add issuer/PKI/source verification only as separate trusted integrations.
3. Build consented, de-identified labeled sets for LLM and VLM; report per-field precision/recall and failure slices.
4. Calibrate or remove correlation/tamper scores if they cannot meet an agreed threshold; document false-positive handling.
5. Add an explicit workflow that safely associates an uploaded proof with a free-text-derived request.

### Testing and evaluation

1. Add reproducible CI with locked dependencies and publish the complete pytest artifact per commit.
2. Add property-based tests for date/calendar/overlap/ledger invariants and policy traceability tests for every clause.
3. Test real Ollama integration separately from deterministic unit tests, including unavailable/timeout/malformed output.
4. Add security/API fuzz, upload malware, authorization and data-retention tests.
5. Benchmark cold/warm model latency, end-to-end p50/p95/p99, throughput, memory/VRAM and database contention on declared hardware.

### UX and operations

1. Clarify template-generated vs LLM-generated summaries in UI labels.
2. Add notifications, approval reminders, delegation and escalation timeout policies.
3. Conduct Vietnamese copy, accessibility, responsive and browser testing.
4. Create an operator runbook for Ollama/model readiness, failed proof extraction, calendar rollover, backup/restore and reconciliation.

## Acceptance evidence needed for future claims

A future item should move to `DONE` only when its code path, policy approval, automated tests and runtime evidence are all available. For performance or AI-quality claims, report dataset/workload, environment, metric definition, sample size and raw result artifact; otherwise retain `NOT MEASURED`.
