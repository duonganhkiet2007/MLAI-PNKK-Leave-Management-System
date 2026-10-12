# Repository assessment

Inspected the working tree at commit `33d7dae7c34804bb58ec43a45e206ac09adef97e`, including pre-existing uncommitted edits. This is the current implementation, not a reconstruction of an earlier build.

## Observed API and workflow

- `POST /api/leave/request`: Pydantic `NewLeaveRequestInput` extends `RequestFacts`, with optional `employee_id` and `raw_text`. Structured facts include leave type, reason category, ISO dates, handover fields, proof ID, and the no-handover-needed exception. It returns `{success, data}` with request ID, decision and persisted status. Pending proof inspection returns HTTP 202 and `PROCESSING`.
- `POST /api/leave/proofs`: multipart file + `proof_type`; checks magic bytes and MIME for PDF/PNG/JPEG and a 10 MiB limit; writes a UUID filename, content SHA-256, proof row, upload audit, then enqueues inspection.
- `GET /api/leave/proofs/{id}/status` polls inspection state; `GET /api/leave/proofs/{id}` downloads through authorization; `POST /api/leave/proofs/{id}/verify` accepts `ProofVerificationInput` for HR.
- `GET /api/leave/{id}`, `/analysis`, and `/requests` serialize database state and audit information. `POST /{id}/resubmit`, `/human-decision`, `/handover-response`, `/cancel`, `/revoke` drive persisted workflow.
- Actor headers are permitted in test mode only by benchmark configuration. Production supports signed bearer tokens. Security probes using test headers measure object/role authorization, not production login strength.
- The benchmark saves the sandbox API's actual OpenAPI schema as `openapi.json` to document exact schemas when running load evaluation.

## Execution and model calls

Synchronous FastAPI submission handlers execute in the ASGI thread pool. Upload is async, but filesystem and database writes run directly inside its coroutine. `ProofInspectionService` has one background worker thread; inference runs outside its job-claim transaction. `VLM_MAX_CONCURRENCY` is defined but does not instantiate multiple workers. Queue state is durable in `proof_inspection_jobs`.

Pending proof submissions persist immediately and return 202. Completion resumes pending requests via `resume_pending_request`. READY proof analysis is passed back into the inspector through the existing `mock_data` adapter; this reuses stored extraction and should not call Ollama. Submission without preprocessing can still take a synchronous inference path. The benchmark leaves all these paths intact.

The default orchestrator has `agent=None`. Free-text applications are rejected; summary generation is deterministic and polishing is disabled. `LeaveApprovalAgent(llm_client=...)` retains explicitly injectable Qwen extraction and reviewer classification methods. `--live-llm` evaluates that existing optional adapter and is not described as default production behavior. Default reviewer text uses keyword classification, with an approval fallback. Ambiguous text is therefore an explicit safety probe.

VLM entry: `core/vlm_inspector.py::inspect_document_with_vlm`. It resizes images, applies a CV blur gate, consults memory/disk cache, calls Ollama `/api/generate`, parses JSON and normalizes `ProofExtraction`. Actual request options in source are `num_ctx=4096`, `num_predict=512`, `temperature=0.0`. Ollama duration/token fields were not exposed by production results; optional benchmark observers retain them without recording prompts, images or document text. Client duration includes transport and Ollama-side queuing; it is not pure GPU execution.

## Deterministic evaluation, persistence and audit

`LeaveRuleEngine.evaluate(LeaveRequest, CalendarService)` is the single rule entry; `decision_tree_engine.py` is a compatibility facade. Calendar files define working dates and verified holiday sources. Context comes from `storage.load_context`: balances, daily absences, earlier approvals, handover and proof state.

`storage.transaction` uses `BEGIN IMMEDIATE`, measures lock acquisition and transaction duration, commits on success and rolls back on exceptions. SQLite connections enable foreign keys, attempt WAL with DELETE fallback, and use a 60-second busy timeout. A debit ledger entry is created **per working date**, with a uniqueness constraint preventing active duplicate annual-day debits. Audit events are written within the transaction. The asynchronous proof row and job are also persisted transactionally.

Human review uses a revision token and fresh authorization under a write lock. Completed requests, rejected requests and cancelled requests are business-final; `PENDING_ESCALATION`, `WAITING_EMPLOYEE`, and `PENDING_HANDOVER` are valid automatic stops awaiting human action, not completed final resolution.

## Verified environment and prior tests

SSH host has an NVIDIA RTX 4090 (24564 MiB), Python 3.12.3 in `.venv`, and Ollama model tags `qwen2.5vl:7b` / `qwen2.5:3b-instruct`. Every run records model IDs, hardware, source/dataset/policy hashes, effective configuration and real-versus-mocked scope again. Shared GPU load and external model residency are uncontrolled unless the operator supplies a dedicated Ollama service. No shared model unload is performed.

Existing tests include `test_phase1_async_vlm_tx.py`, model-invocation, resize, organization and API checks. `tests/benchmark_phase1.py` is a smaller mocked experiment with a simulated synchronous baseline; it is not valid evidence of an actual earlier production build. Comprehensive evaluation reuses the bounded async-VLM, invocation and resize tests; live model work is excluded from normal pytest.

## Integration boundaries and limitations

All new implementation is under `benchmarks/`; no production source was edited. API benchmarks start a real loopback TCP backend in a child process using a new marked `/tmp/mlai-benchmark-*` directory, isolated SQLite and uploads, synthetic employee fixtures, startup warmup off, and deterministic clock. Existing employee JSON initialization is redirected to an empty benchmark-only JSON file before initialization. There is no flag to target a production database or external production application API.

Optional observers wrap existing metric methods and Ollama calls in this child process only. SQLite timings are aggregate batch observations, not guessed per-request spans. Queue/job timestamps come from persisted jobs, with retry limitations documented. Missing metrics are N/A.

Policy sources disagree in several places: `policy_rules.md §3.1` names CEO above five annual days whereas raw policy Điều 10.3 names department head; §3.4 states a strict `<30%` quota while code accepts exactly 30%; unverified short medical evidence is allowed by code despite verification language. These cases are retained as diagnostic observations and excluded from headline labeled accuracy. Other clear mismatches remain failures. No policy labels are copied from model or engine output.

Synthetic image corruptions are reproducible stressors, not verified real-world readability annotations. Hard process kill recovery and real prompt injection are marked skipped in lightweight tests; dedicated VLM tests generate an injection document and check extracted annotations when explicitly invoked. A true historical before/after report requires independently supplied equivalent runs; repeat runs of the same source measure repeatability only.
