# Policy and Decision Logic

## Source hierarchy

`Leave_Application/policy_rules.md` là policy authoritative. `raw_policy.json` chỉ là nguồn lịch sử và có các khác biệt đã được policy mới thay thế, ví dụ mẫu/ch期限 hồ sơ y tế và các rule nội bộ bổ sung. Bảng dưới đây ghi hành vi code hiện tại; khi code chưa bao phủ policy, trạng thái được nêu rõ.

## Policy-to-implementation matrix

| Policy rule | Leave type | Condition | Expected decision in current code | Target | Error code | Annual deduction? | Proof? | Implementation location |
|---|---|---|---|---|---|---:|---|---|
| Annual auto path | `ANNUAL` | 1–2 working days; balance/notice/quota pass | `AUTO_APPROVE` | — | — | Yes, on commit | No | `rule_engine.py`: balance/operations/authority; `storage.commit_approval` |
| Annual manager authority | `ANNUAL` | 3–5 working days; valid handover if ≥3 | `ESCALATE` | `DIRECT_MANAGER` | `DURATION_OVER_AI_LIMIT` | Only after final approval | No | `rule_engine.py` authority |
| Annual department authority | `ANNUAL` | 6–19 working days | `ESCALATE` | `DEPARTMENT_HEAD` | `DURATION_OVER_MANAGER_LIMIT` | Only after approval | No | `rule_engine.py` authority |
| Annual CEO authority | `ANNUAL` | ≥20 working days | `ESCALATE` | `CEO` | `DURATION_OVER_MANAGER_LIMIT` | Only after approval | No | `rule_engine.py` authority |
| Annual insufficient balance | `ANNUAL` | requested working days > current balance | `AUTO_REJECT` | `EMPLOYEE` | `BALANCE_EXCEEDED` | No | No | `rule_engine.py` balance |
| Annual probation restriction | `ANNUAL` | `employment_status == PROBATION` | `NEED_CORRECTION` | `EMPLOYEE` | `PROBATION_ANNUAL_RESTRICTED` | No | No | `rule_engine.py` entitlement |
| Annual anti-abuse | `ANNUAL` | prior approved annual days exist in same calendar month and cumulative total >2 | `ESCALATE` | `DIRECT_MANAGER` | `FLAG_ABUSE_PATTERN` | Only after approval | No | `storage.load_context`; `rule_engine.py` |
| Medical missing/unreadable proof | `SICK_MEDICAL`, `MEDICAL_EMERGENCY` | no proof or illegible | `NEED_CORRECTION` | `EMPLOYEE` | `PROOF_MISSING` / `DOC_ILLEGIBLE` | No | Required | `rule_engine.py` proof |
| Medical proof not HR-verified | Medical types | extracted/uploaded proof is not `VERIFIED` | `ESCALATE` | `HR` | `PROOF_REVIEW_REQUIRED` | No | Required + HR verification | `rule_engine.py`; `/proofs/{id}/verify` |
| Medical one day | Medical types | verified complete proof; notice before 08:30 | `AUTO_APPROVE` | — | — | No | Required | `rule_engine.py` proof/notice/authority |
| Medical two or more days | Medical types | verified complete proof | `ESCALATE` | `DIRECT_MANAGER` | `DURATION_OVER_AI_LIMIT` | No | Required | `rule_engine.py` authority |
| Medical late notice | Medical types | submitted after 08:30 first absent working day | `ESCALATE` | `DIRECT_MANAGER` | `NOTICE_PERIOD_VIOLATED` | No | Required | `rule_engine.py` notice |
| Special paid entitlement | `SPECIAL_PAID` | mapped event; requested days ≤ entitlement; verified matching proof | `ESCALATE` | `DIRECT_MANAGER` | `DURATION_OVER_AI_LIMIT` | No | Required | `PAID_ENTITLEMENTS`; proof/authority stages |
| Special paid over entitlement | `SPECIAL_PAID` | requested days exceed 3/1/3-day mapping | `NEED_CORRECTION` | `EMPLOYEE` | `ENTITLEMENT_EXCEEDED` | No | Required later in pipeline | `rule_engine.py` entitlement |
| Statutory unpaid | `STATUTORY_UNPAID` | mapped grandparent/sibling death or parent/sibling marriage; max 1 working day | `ESCALATE` | `DIRECT_MANAGER` | `DURATION_OVER_AI_LIMIT` | No | Not required by engine | `UNPAID_ENTITLEMENTS`; authority |
| Statutory relationship unclear | `STATUTORY_UNPAID` | no mapped reason category | `ESCALATE` | `DIRECT_MANAGER` | `RELATIONSHIP_UNCLEAR` | No | No | `rule_engine.py` entitlement |
| Other unpaid ≤5 | `UNPAID_OTHER` | non-empty reason, policy checks pass | `ESCALATE` | `DIRECT_MANAGER` | `LONG_TERM_UNPAID` | No | No | `rule_engine.py` input/authority |
| Other unpaid 6–19 | `UNPAID_OTHER` | policy checks pass | Sequential `ESCALATE` | `DEPARTMENT_HEAD`, then `HRD` | `LONG_TERM_UNPAID` | No | No | `rule_engine.py`; `approval_steps` |
| Other unpaid ≥20 | `UNPAID_OTHER` | policy checks pass | Sequential `ESCALATE` | `DEPARTMENT_HEAD` → `HRD` → `CEO` | `LONG_TERM_UNPAID` | No | No | `rule_engine.py`; `approval_steps` |
| Maternity | `MATERNITY` | any request | `ESCALATE` (`PARTIAL`) | `HR` | `AUTOMATION_SCOPE_UNSUPPORTED` | No | VLM can inspect, engine does not adjudicate | early scope check in `rule_engine.py` |
| Work accident | `WORK_ACCIDENT` | any request | `ESCALATE` (`PARTIAL`) | `HR` | `AUTOMATION_SCOPE_UNSUPPORTED` | No | VLM can inspect, engine does not adjudicate | early scope check in `rule_engine.py` |
| Entire range non-working | Any recognized/omitted leave type, because calendar check precedes type check | zero working dates | `NO_LEAVE_REQUIRED` | — | `DAY_ALREADY_NON_WORKING` | No | No | `calendar_service.py`; early calendar stage |
| Duplicate complete overlap | Any supported type after proof stage | all working dates already approved | `AUTO_REJECT` | `EMPLOYEE` | `REQUEST_ALREADY_COVERED` | No new deduction | As required by type | `rule_engine.py` overlap |
| Partial overlap | Any supported type after proof stage | some requested dates already approved | `NEED_CORRECTION` | `EMPLOYEE` | `OVERLAPPING_REQUEST` | No | As required by type | `rule_engine.py` overlap |
| Unknown/unverified calendar year | Any | calendar JSON absent/unverified | `ESCALATE` | `HR` | `LEGAL_REVIEW_REQUIRED` | No | No | `calendar_service.py`; `rule_engine.py` |

### Policy/code gaps visible in this matrix

- Policy routes `SICK` over 5 days to HR/out-of-policy, but code assigns `DIRECT_MANAGER` for every medical request of two or more days. This is a current mismatch, not a supported feature.
- Policy contains detailed maternity entitlement and HR Ops flow; code short-circuits all maternity requests to HR as unsupported automation.
- Work accident exists in domain/VLM/UI but has no automated decision rules.
- Policy names `PUBLIC_HOLIDAY`/`WEEKLY_REST` as leave concepts, while code represents them as `DayType`, not submit-able `LeaveType` values.
- Policy text says unsupported leave type is `AUTO_REJECT`; code returns `NEED_CORRECTION / LEAVE_TYPE_MISSING` for missing or unrecognized type.
- Policy says all `ANNUAL`/`UNPAID_OTHER` of ≥3 consecutive working days require handover. Code checks `n >= 3` for all types, but treats the resulting missing/invalid handover as blocking only for operational types and warning for the others. This matches the intended blocking/warning split, though it does not explicitly model “consecutive” beyond a single continuous date range.

## Core checks

### Annual balance

Only `ANNUAL` uses `should_deduct_annual_balance`. The engine rejects a request exceeding the current balance. An approved annual request creates one booking and one `DEBIT -1` ledger transaction per working date, then atomically decrements `employees.remaining_leave_days`. Refund reverses proven debits once. Non-annual types are tested to keep both `deducted_days` and `annual_balance_change` at zero.

### Notice period

For `ANNUAL` and `UNPAID_OTHER`, required working-day notice is 1 day for ≤3 days, 3 days for 4–5 days, and 7 days for unpaid or >5 days. For medical types, submission after 08:30 Asia/Ho_Chi_Minh on the first working day is a violation. Violations escalate and may be waived by authorized approval; they do not auto-reject.

### Quota 30%

Backend computes absence count per working date from completed requests in the same department. Engine evaluates `(existing absent + current employee) / active team size > 0.30`. It blocks auto processing for `ANNUAL` and `UNPAID_OTHER` by escalating; other types receive a warning only.

### Handover

When `n >= 3` or a handover was supplied, engine validates an ID, same department, `ACTIVE` status, not self, and no overlapping absence. Missing/invalid handover returns correction for `ANNUAL`/`UNPAID_OTHER`; other types retain a warning.

### Entitlement

`SPECIAL_PAID` mappings are self marriage 3, child marriage 1, and parent/spouse-parent/spouse/child death 3 working days. `STATUTORY_UNPAID` mappings are grandparent/sibling death and parent/sibling marriage, each 1 day. Requests over entitlement are corrected, not partially granted.

### Proof routing

Medical and special-paid types require proof. Missing/illegible/rejected/incomplete proof returns correction. A readable extraction remains `UNVERIFIED` and routes to HR. Only a server-side HR verification can make it `VERIFIED`. Medical validation then checks proof class, issuer, issue date, patient name, recommended range and signature/digital signature. Special-paid validates the proof class associated with the event.

### Overlap

The engine intersects current working dates with the employee's already approved working dates. Full overlap is rejected to prevent double booking/debit. Partial overlap asks the employee to adjust the range. The final human approval path reloads this context, so a newly created overlap is caught.

### Probation

Annual leave during `PROBATION` returns correction asking for a separate `UNPAID_OTHER` request; the annual balance is preserved. Code does not automatically transform the leave type.

### Authority

Authority is deterministic and encoded as ordered roles. Annual uses no role / Direct Manager / Department Head / CEO based on duration. Other unpaid uses Direct Manager, Department Head + HRD, or Department Head + HRD + CEO. Special/statutory unpaid use Direct Manager. Medical code currently uses Direct Manager for every request from two days upward. Granted roles are removed from `remaining`, allowing sequential re-evaluation.

### Anti-abuse

`storage.load_context` totals previously completed annual working dates in the calendar month of the new start date. If at least one prior day exists and prior + current exceeds two days, `has_abuse_pattern` is set. Engine escalates to Direct Manager with `FLAG_ABUSE_PATTERN`. The audit contains the evaluation result, but code does not currently write the full “list of related requests” payload demanded by policy; this aspect is `PARTIAL`.

### Calendar and non-working days

CalendarService defaults to Monday–Friday and loads only verified yearly JSON. It classifies public holidays, weekly rest and automatically computed compensatory days. Missing year/configuration fails closed to HR. If the requested range contains no working day, result is `NO_LEAVE_REQUIRED`; if mixed, only working dates count toward entitlement, authority and annual deduction.

## Meaning of the five decisions

### `NEED_CORRECTION`

Exists for a request the employee can repair without asking an approver to override trusted policy state: missing/ambiguous dates, invalid range/type, missing or unreadable proof, missing proof fields, entitlement excess, partial overlap, invalid handover, or probation annual. It targets `EMPLOYEE` and maps to `WAITING_EMPLOYEE`.

### `AUTO_REJECT`

Exists for a definitive conflict that should not be approved on the same request. Current code uses it for annual balance exceeded and a date range fully covered by an approved request. It maps to `REJECTED` and does not create approval steps.

### `ESCALATE`

Exists when the system must stop automatic processing but the case needs a human authority or verification path. It covers authority thresholds, notice/quota/anti-abuse, unverified proof, unknown calendar, unclear statutory relationship and unsupported maternity/work-accident automation. It maps to `PENDING_ESCALATION`.

### `AUTO_APPROVE`

Exists only after all earlier deterministic stages pass and no approval role remains. Backend commits bookings, and annual requests debit the ledger/balance. An `AUTO_APPROVE` after human steps means the re-evaluated request has no remaining role; it is not an LLM decision.

### `NO_LEAVE_REQUIRED`

Exists when CalendarService finds zero working dates. It communicates that the interval is already non-working, closes the request without leave booking or deduction, and is intentionally distinct from rejection.
