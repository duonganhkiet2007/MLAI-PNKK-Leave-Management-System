# AI Components: LLM and VLM

## Canonical model configuration

`LLM-KIET/ai_stack.py` là nguồn cấu hình hiện tại:

- LLM: environment `LLM_MODEL`, mặc định `qwen2.5:3b-instruct`.
- VLM: environment `VLM_TARGET_MODEL`, mặc định `qwen2.5vl:7b`.
- Cả hai gọi Ollama, mặc định `http://localhost:11434`.
- Timeout mặc định: LLM 60 giây, VLM 180 giây; `keep_alive` mặc định là numeric `-1`.

`LLM-KIET/README.md` và docs legacy mô tả Qwen 2.5 7B in-process trong FastAPI. Claim đó stale: code hiện tại gọi Ollama và LLM mặc định là 3B. FastAPI phục vụ port 8000, nhưng Ollama là service endpoint riêng.

## LLM

### Call sites and prompts

| Call site | Prompt/schema | Input | Output | Quyền policy |
|---|---|---|---|---|
| `LeaveApprovalAgent.parse_natural_language` | `PARSE_REQUEST_SYSTEM_PROMPT` + `ParsedLeaveRequest` | Free-text employee request + current date | Request facts only | None |
| `LeaveApprovalAgent.process_human_feedback` | `HUMAN_FEEDBACK_SYSTEM_PROMPT` + `HumanFeedbackResolution` | Free-text human reply | Whitelisted action, editable fields, notes | None; backend validates role/action and re-evaluates |
| `LeaveOrchestratorService._evaluate(enable_llm_polish=True)` | `SUMMARY_MANAGER_SYSTEM_PROMPT` + `ManagerSummaryLLMResponse` | Trusted context + engine/VLM result | Presentation summary | None; opt-in only |

Prompts explicitly cấm model trả identity, department, balance, proof verification, authority hoặc policy result. Pydantic models dùng `extra='forbid'`. `LLMClient.generate_json` requests JSON mode at temperature 0 and validates output against the response schema.

### Input/output contract

Employee parser chỉ xuất: `from_date`, `to_date`, `leave_type`, `reason_category`, `reason`, handover ID/name và `date_ambiguous`. Annual reason is not morally judged: tests explicitly show “chán đi làm” can pass if the policy facts pass.

Human feedback parser chỉ xuất một trong `APPROVE_OVERRIDE`, `REJECT`, `MODIFY_CONDITIONAL`, `REQUEST_MORE_INFO`; editable fields are limited to dates and handover. Backend, not model, checks actor role, revision and current request state.

### Exact call frequency by workflow

| Workflow | LLM calls on current API path | Notes |
|---|---:|---|
| Structured form, no proof | 0 | Deterministic template summary. |
| Structured form with proof | 0 | VLM may run; LLM summary is still off. |
| Free-text employee request | 1 | Facts extraction only. Backend then forces `proof_id=None`. |
| Manager button action | 0 | `action_type` is mapped deterministically. |
| Manager free-text action | 1 | Action extraction only. |
| Verify Harness `/api/verify/escalation` | 0 | Calls rule engine directly. |
| Custom Verify with `raw_text` | 1 | Parser only; response reports `llm_calls=1`. |
| Optional manager-summary polish | +1 if explicitly enabled | `_evaluate` supports it, but `leave_router` does not expose/enable this flag. |

These counts are asserted with mocks in `tests/test_model_invocation_counts.py` and `LLM-KIET/test_llm_kiet.py`. They are code/test contracts, not measured production telemetry.

### Failure behavior

If LLM loading/inference/JSON validation fails, employee text parsing or human free-text parsing raises `ModelUnavailable`; FastAPI returns HTTP 503. There is no heuristic extraction fallback. Structured form and button actions remain available without LLM.

## VLM

### When it runs

`LeaveOrchestratorService._evaluate` runs VLM whenever `attachment_type != none` or a `proof_id` resolves to a proof record. For a stored proof, it resolves the local upload path and calls `inspect_document_with_vlm(..., allow_mock_fallback=False)`.

The default production-like path therefore attempts real Ollama inference. Explicit `mock_data`, `VLM_FORCE_MOCK=1`, or an explicitly allowed fallback exist for tests/dev, but orchestration disables fallback. If VLM fails, orchestration persists a `VLM_RUNTIME_ERROR` shell with unknown fields and the rule engine sees no invented valid proof.

### Extracted output

VLM normalizes these fact/diagnostic groups:

- `ProofExtraction`: proof type, issuer, patient/subject name, issue date, recommended date range, physical/digital signature, readability and detected fields.
- Document summary: name, diagnosis/event, issuer and recommended range.
- Diagnostic flags: red stamp, signature, suspected tamper, suspected AI editing.
- Deterministic correlation result: score/issues comparing reason, requested dates and extracted dates.
- UI metadata: persona, inspection mode, escalation flags and raw detected fields.

The rule engine currently consumes the normalized `ProofExtraction`; many forensic/correlation fields are displayed/persisted but do not independently determine the policy outcome.

### Verification status and authenticity boundary

VLM output is not `VERIFIED`. Orchestration preserves an existing verification status; otherwise it remains `UNVERIFIED`. `rule_engine.py` routes medical/special proof to HR with `PROOF_REVIEW_REQUIRED`. Only `POST /api/leave/proofs/{proof_id}/verify`, restricted to DB role `HR`, constructs `VerifiedProof` with the chosen status and verifier.

Signals such as `is_tampered`, `ai_edited`, red stamp or correlation score are model observations/heuristics. Code does not query an issuer, validate a digital certificate chain, check a government registry or prove document authenticity. They must be presented as “suspected/observed,” never “authentic/fraud confirmed.”

### Known implementation caveats

- `_try_ollama_extract` is invoked without forwarding `leave_type`, so the real-VLM prompt gets the generic leave profile even though leave-specific profiles exist and are unit-tested separately.
- Prompt readability values are `READABLE/PARTIAL/ILLEGAL`, while `ProofExtraction` accepts `READABLE/ILLEGIBLE/UNKNOWN`; edge outputs can fail validation and fall back to stored facts/error handling.
- Runtime `inspection_mode` string says `OLLAMA_REAL_QWEN25_VL_3B` even though the configured default VLM is 7B; treat the model field `target_model` as authoritative.
- PDF bytes are passed through the image-loading/fallback path; robust multi-page PDF rendering/extraction is not implemented.
- Re-evaluation with a proof can call VLM again; there is no persisted inference cache keyed by file hash.

## Component authority table

| Component | Input | Output | Decision authority | Call frequency |
|---|---|---|---|---|
| LLM Parser | Employee free text, current date | Typed request facts | None | 1 per free-text submission; 0 for form |
| LLM Human-action parser | Human free text | Whitelisted action + allowed edits | None | 1 per free-text action; 0 for button |
| Optional LLM summary | Engine/VLM/context JSON | Presentation text/arrays | None | 0 on current route; opt-in +1 |
| VLM Inspector | Uploaded file + request context | Proof facts and diagnostic signals | None | 1 per evaluation that has proof/attachment; re-evaluations can add calls |
| Calendar Service | Date range + verified JSON config | Day types, working dates, notice days | Deterministic calendar authority | Called by engine/context; no model |
| Rule Engine | Trusted `LeaveRequest` | Decision, routing, error, trace, deduction intent | Final policy decision | Once per evaluation/re-evaluation |
| Backend/Storage | Actor, request, DB state, engine result | State transition, audit, booking, ledger mutation | Workflow/state authority | Every request/action |
| HR | Original proof + extracted/stored facts | Verification status and notes | Proof verification authority | Human action as needed |
| Other human approvers | Escalated request and question | Approve/reject/request info/conditional edit | Scoped organizational authority | Per pending approval step |

## Why not let the LLM make the final policy decision?

The current architecture keeps decision inputs auditable and re-checkable. Balance, overlap, team absence, role scope and proof status come from mutable trusted state; an LLM response created earlier cannot safely represent their latest values. Calendar arithmetic, entitlement limits and authority thresholds also need repeatable results for the same context.

The backend therefore loads fresh DB state and calls the deterministic engine both at submission and immediately before human approval is committed. This catches concurrent balance changes and new overlaps, produces stable error codes/clauses, and allows atomic ledger mutation. LLM output is deliberately schema-limited to semantic extraction or presentation. Giving it final authority would bypass the exact trust boundaries, concurrency checks and audit semantics implemented in `storage.py` and `orchestration.py`.
