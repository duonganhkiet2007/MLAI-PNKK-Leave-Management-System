# Testing and Evidence

## Test inventory

Static inspection finds 53 pytest test functions across four modules. Accounting for current `pytest.mark.parametrize` inputs, they are expected to collect as 133 test instances:

| Suite | Test functions | Expected collected instances | Main scope |
|---|---:|---:|---|
| `Leave_Application/test_decision_tree.py` | 23 | 65 | 30 canonical policy cases, calendar, entitlement, proof invariants, authority, anti-abuse, name matching, VLM prompt profiles |
| `backend/test_api_e2e.py` | 18 | 49 | Same 30 cases through persistence plus API/auth, transactions, concurrency, proof verification, multi-step approval, migration, harness |
| `LLM-KIET/test_llm_kiet.py` | 5 | 12 | LLM extraction contract, malicious extra fields, human action whitelist, conditional recheck |
| `tests/test_model_invocation_counts.py` | 7 | 7 | Exact LLM/VLM call contracts and deterministic summary timing/schema |
| **Total** | **53** | **133** | Static expected count, not a fresh runtime result |

`tests/scenarios.py` defines 30 canonical cases. `Leave_Application/test_cases.json` also contains 30 cases, of which five have `is_verify_harness=true`. The JSON is used by the Verify API; the Python list is used by pytest unit/API parameterization.

The current available interpreters do not have pytest installed, so this audit could not produce a new pass/fail run. **Latest runtime test result must be inserted manually.** Do not copy “106 passed” or the `4/4` claim from older docs without a fresh command output tied to the final revision.

Suggested reproducible command after installing `requirements-dev.txt`:

```bash
python -m pytest -q
```

Record the timestamp, commit hash, Python version, dependency versions, OS/hardware and complete summary.

## Behavior coverage

### Rule and policy tests

- Five decisions: auto approve, auto reject, correction, escalation and no-leave-required.
- Annual duration tiers, balance, probation, anti-abuse and reason non-judgment.
- Special-paid/statutory-unpaid entitlement and relationship mapping.
- Medical proof missing/readability/fields/date/name/signature and one-day vs two-day authority.
- Notice calculations across weekends/holidays and medical cutoff.
- Quota by each day, handover validity, full/partial overlap.
- Public holiday, weekend, compensatory rest, configurable Saturday, unknown calendar year and span into 2027.
- Invariant that non-annual leave never deducts annual balance.
- Schema guardrails preventing LLM/VLM from constructing trusted fields.

### API/E2E tests

- Canonical decisions persisted with real balance effects.
- Protected input rejection and actor/role visibility checks.
- Atomic rollback, duplicate booking protection and concurrent submissions.
- Concurrent human approval conflict, final balance/overlap recheck and double-refund prevention.
- Multi-step unpaid approval, conditional modification and request-info/resubmit.
- Upload size/MIME, owner visibility, HR-only verification and inability to approve unverified proof.
- Idempotent migration/history preservation.

### Model invocation count tests

Mock-based tests assert:

- Structured auto/escalate: zero LLM calls.
- Free-text submission: exactly one LLM call.
- One form-with-proof evaluation: exactly one VLM call and zero LLM calls. Later re-evaluations of the same proof-bearing request may each add one VLM call.
- Manager button: zero LLM calls.
- Manager free text: exactly one LLM call.
- Deterministic summary contains expected fields/timings and `llm_generation_ms == 0.0`.

These establish orchestration call contracts. They do not measure real-model accuracy or latency.

## Verify Harness

`POST /api/verify/escalation` reads only the five marked JSON cases, invokes `LeaveRuleEngine` directly, does not call LLM and does not write the production DB. It expects:

- all five marked cases matching the selected fields;
- 3 `AUTO_APPROVE`;
- 2 `ESCALATE`;
- 0 LLM calls;
- elapsed time under 90 seconds.

The five current cases are TC01 Annual 2 days, TC04 Annual 3–5 days, TC09 Friday–Monday, TC27 annual with reason “chán đi làm”, and TC28 Unpaid Other ≤5. This harness is a narrow demo acceptance check, not the whole test suite or an AI quality benchmark.

`POST /api/verify/custom` is simulation-only. It can call the LLM once when `raw_text` is supplied, otherwise evaluates supplied typed facts.

## Representative cases

| Case | Input | Expected decision | Target | Reason | Test source |
|---|---|---|---|---|---|
| Routine auto approve | Annual 2026-10-05→06, balance 100, early submission | `AUTO_APPROVE` | — | 2 working days, all checks pass | `tests/scenarios.py` TC01 |
| Authority escalation | Annual 2026-10-05→07 with handover | `ESCALATE` | `DIRECT_MANAGER` | 3 days exceeds auto limit | TC04 |
| Higher authority | Annual 2026-10-05→12 | `ESCALATE` | `DEPARTMENT_HEAD` | 6 working days | TC05 |
| Quota violation | Annual with 4/12 existing absent | `ESCALATE` | `DIRECT_MANAGER` | Current employee pushes ratio over 30% | TC21 |
| Notice violation | Annual submitted across holiday/weekend without sufficient working-day notice | `ESCALATE` | Applicable authority | Insufficient notice | `test_notice_excludes_holidays_and_weekends` |
| Proof missing | Sick medical, no proof | `NEED_CORRECTION` | `EMPLOYEE` | Medical proof required | TC16 |
| Proof illegible | Sick, verified-shaped proof but `ILLEGIBLE` | `NEED_CORRECTION` | `EMPLOYEE` | File cannot support field checks | TC17 |
| Proof unverified | Uploaded medical proof record remains `UNVERIFIED` | `ESCALATE` | `HR` | HR must verify extracted/stored facts | `test_upload_hr_verification_medical_workflow` |
| Balance exceeded | Annual 2 days, balance 1 | `AUTO_REJECT` | `EMPLOYEE` | Cannot borrow annual on same request | TC02 |
| Complete overlap | Both working dates already approved | `AUTO_REJECT` | `EMPLOYEE` | Prevent duplicate booking/debit | TC22 |
| Partial overlap | One of two days already approved | `NEED_CORRECTION` | `EMPLOYEE` | Employee must adjust range | TC23 |
| Holiday/no leave | 2026-04-30 only | `NO_LEAVE_REQUIRED` | — | Public holiday; zero working days | TC07 |
| Weekend/no leave | 2026-10-10→11 | `NO_LEAVE_REQUIRED` | — | Weekly rest only | TC10 |
| Sick one day | Verified complete proof, on-time | `AUTO_APPROVE` | — | Medical one-day auto tier | `test_sick_authority_1d_vs_2d` |
| Sick two days | Verified complete proof | `ESCALATE` | `DIRECT_MANAGER` | Above medical auto tier | TC15 / sick authority test |
| Special paid | Self marriage, 3 days, verified marriage proof | `ESCALATE` | `DIRECT_MANAGER` | Entitlement valid; manager confirmation required | TC11 |
| Statutory unpaid | Grandparent death, 1 day | `ESCALATE` | `DIRECT_MANAGER` | Statutory entitlement, human authority | TC14 |
| Unpaid other long | 6 working days, reason present | `ESCALATE` | `DEPARTMENT_HEAD` first | Multi-step Department Head + HRD | TC29 / multi-step E2E |
| Maternity | Any maternity request | `ESCALATE` | `HR` | Automation scope unsupported | TC24 |
| Work accident | Any work-accident request | `ESCALATE` | `HR` | Automation scope unsupported | TC25 |
| Anti-abuse | Annual with `has_abuse_pattern=true` | `ESCALATE` | `DIRECT_MANAGER` | Cumulative split requests over auto threshold | `test_anti_abuse_pattern_flag` |

## Evidence not currently available

- Real LLM parser accuracy on a labeled corpus: `NOT MEASURED`.
- Real VLM field/document accuracy, false-positive tamper rate and authenticity verification: `NOT MEASURED`.
- End-to-end p50/p95/p99 latency, throughput and memory/VRAM: `NOT MEASURED`.
- Browser/accessibility/security test results: `NOT MEASURED`.
- Production-scale database/load/failover results: `NOT MEASURED`.

UI comments such as “~8–18s”, “~0.5–2s” or “Rule Engine <0.3s” are expectations/display copy, not benchmark evidence and must not be quoted as measured results.
