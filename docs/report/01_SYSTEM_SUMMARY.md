# System Summary

## Bài toán hệ thống giải quyết

MLAI Leave Application là hệ thống demo điều phối đơn nghỉ phép. Hệ thống tiếp nhận facts do nhân viên cung cấp, bổ sung context đáng tin cậy từ SQLite, trích xuất facts từ văn bản/chứng từ khi cần, rồi dùng rule engine xác định một trong năm kết quả. Với hồ sơ cần thẩm quyền con người, backend tạo bước duyệt đúng role, nhận hành động và chạy lại rule engine trước khi commit.

Hệ thống không phải một “LLM phê duyệt nghỉ phép”. Quyết định policy nằm trong `LeaveRuleEngine.evaluate`; LLM chỉ parse ngôn ngữ và, ở một đường chạy opt-in, làm mượt summary. VLM chỉ trích xuất/đối chiếu facts từ file; trạng thái `VERIFIED` chỉ do HR ghi qua API.

## Đầu vào

- Structured form: ngày bắt đầu/kết thúc, loại nghỉ, reason category/lý do, người bàn giao và `proof_id` tùy chọn.
- Free text: chuỗi tiếng Việt được LLM chuyển thành `RequestFacts`. Identity, department, balance, proof verification, authority và decision không được nhận từ model.
- Trusted context: hồ sơ nhân viên, số dư, trạng thái việc làm, team size/absence, các ngày đã được duyệt, người bàn giao, proof record, role đã duyệt và error được waive; tất cả được backend tải từ DB.
- Chứng từ: PDF/JPEG/PNG tối đa 10 MB, có kiểm tra magic bytes/MIME; VLM chạy khi đơn có attachment/proof.
- Human action: nút có `action_type` hoặc free-text feedback được LLM map vào action whitelist.

Nguồn: `domain.RequestFacts`, `leave_router.NewLeaveRequestInput`, `storage.load_context`, `orchestration.process_new_request`.

## Đầu ra

- Quyết định: `NO_LEAVE_REQUIRED`, `AUTO_APPROVE`, `AUTO_REJECT`, `NEED_CORRECTION`, hoặc `ESCALATE`.
- Routing: `target_role`, `approval_roles`, `uncertainty_category`, `error_code`, câu hỏi hành động và quick actions.
- Giải trình: số ngày lịch/làm việc, warnings, policy clauses, decision trace và summary tiếng Việt theo template.
- Trạng thái workflow: `COMPLETED`, `REJECTED`, `WAITING_EMPLOYEE`, `PENDING_ESCALATION`, hoặc `CANCELLED`.
- Persistence: request, approval steps, proof facts, audit logs, leave bookings và ledger debit/refund/allocation.

## User roles

Các role policy/runtime là:

- `EMPLOYEE`: nộp, sửa/nộp lại, hủy đơn đang chờ và nhận yêu cầu correction.
- `DIRECT_MANAGER`: bước duyệt đầu cho annual 3–5 ngày, sick từ 2 ngày theo code hiện tại, special/statutory unpaid và unpaid ≤5 ngày; cũng xử lý một số vi phạm vận hành.
- `DEPARTMENT_HEAD`: annual 6–19 ngày và bước đầu của unpaid >5 ngày.
- `HR`: xác minh chứng từ; nhận calendar/legal review và các loại automation chưa hỗ trợ.
- `HRD`: bước tiếp theo của unpaid >5 ngày và cấp phát balance.
- `CEO`: annual ≥20 ngày theo code; bước cuối của unpaid ≥20 ngày.

Role được map từ chức danh chính xác khi migration chạy. Identity hiện là demo: client gửi `X-Actor-ID` hoặc query `actor_id`, không phải authentication production.

## Supported leave types

`domain.LeaveType` có tám loại đơn:

| Leave type | Hành vi hiện tại |
|---|---|
| `ANNUAL` | Đầy đủ nhất: calendar, balance, notice, quota, handover, overlap, probation, anti-abuse, authority, debit/refund. |
| `SPECIAL_PAID` | Entitlement theo sự kiện, proof + HR verification, Direct Manager xác nhận, không trừ annual. |
| `STATUTORY_UNPAID` | Entitlement một ngày cho các quan hệ/sự kiện được map; quan hệ mơ hồ chuyển Direct Manager; không trừ annual. |
| `UNPAID_OTHER` | Bắt buộc lý do; notice/quota/handover; multi-step authority; không trừ annual. |
| `SICK_MEDICAL` | Bắt buộc proof đã HR verify; kiểm tra fields/name/date/signature; một ngày có thể auto-approve, từ hai ngày chuyển người duyệt. |
| `MEDICAL_EMERGENCY` | Dùng chung logic `MEDICAL` và cutoff 08:30 với `SICK_MEDICAL`. |
| `WORK_ACCIDENT` | Nhận diện trong schema/UI/VLM nhưng rule engine chuyển HR ngay với `AUTOMATION_SCOPE_UNSUPPORTED`: `PARTIAL`. |
| `MATERNITY` | Nhận diện trong schema/UI/VLM nhưng rule engine chuyển HR ngay với `AUTOMATION_SCOPE_UNSUPPORTED`: `PARTIAL`. |

`PUBLIC_HOLIDAY` và `WEEKLY_REST` không phải `LeaveType` có thể nộp trong `domain.py`. Chúng là phân loại ngày của Calendar Engine. Khi toàn bộ khoảng yêu cầu không có ngày làm việc, engine trả `NO_LEAVE_REQUIRED`.

## DecisionType

| Decision | Ý nghĩa runtime |
|---|---|
| `NO_LEAVE_REQUIRED` | Khoảng ngày toàn bộ là holiday/weekly rest/compensatory day; không booking và không trừ phép. |
| `AUTO_APPROVE` | Tất cả điều kiện đã qua và không còn bước thẩm quyền; backend commit booking, chỉ annual mới debit balance. |
| `AUTO_REJECT` | Vi phạm xác định không thể giải quyết bằng approve override trên cùng đơn, hiện thấy ở vượt balance hoặc toàn bộ ngày đã được đơn khác cover. |
| `NEED_CORRECTION` | Facts có thể sửa bởi employee: thiếu/sai ngày, loại, lý do, proof/fields, entitlement, overlap một phần, handover, probation annual. |
| `ESCALATE` | Cần HR/cấp duyệt do proof/legal/unsupported scope, vi phạm vận hành có thể xem xét, hoặc vượt thẩm quyền tự động. |

## Uncertainty categories

- `UNCERTAIN_FACTS`: dữ liệu thiếu, mơ hồ, không khớp hoặc cần employee sửa/manager xác minh quan hệ.
- `OUT_OF_POLICY`: điều kiện policy/vận hành hoặc trusted verification chưa đạt; nhóm này có thể dẫn đến auto-reject hoặc escalation tùy error.
- `AUTHORITY_ESCALATION`: hồ sơ đã vượt các kiểm tra trước nhưng cần cấp có thẩm quyền.

Category không tự quyết outcome. Ví dụ `BALANCE_EXCEEDED` là `OUT_OF_POLICY` nhưng `AUTO_REJECT`, còn `TEAM_QUOTA_EXCEEDED` cũng là `OUT_OF_POLICY` nhưng `ESCALATE`.

## Authority levels

Code hiện có bốn tầng xử lý thực tế:

1. System auto path: annual ≤2 ngày; medical 1 ngày với proof hợp lệ; và các path không cần leave.
2. `DIRECT_MANAGER`.
3. `DEPARTMENT_HEAD`, `HR`, hoặc `HRD` tùy loại điều kiện.
4. `CEO` cho ngưỡng dài hạn được code định tuyến.

`approval_steps` lưu chuỗi role theo revision. Mỗi approver phải đúng role/scope phòng ban; employee không được tự duyệt. Sau mỗi approval, hệ thống re-evaluate với các role đã grant. Notice và quota là hai error được human approval waive; balance, proof, overlap, legal calendar và unsupported automation không bị bypass.

## Human-in-the-loop

- Direct Manager/Department Head/HRD/CEO dùng nút `APPROVE`, `REJECT`, `REQUEST_INFO`, hoặc conditional modification.
- Free-text manager feedback gọi LLM đúng một lần để trích action whitelist; button action không gọi LLM.
- HR dùng endpoint riêng để gán `VERIFIED`, `REJECTED`, hoặc `NEEDS_HR_REVIEW` và facts chứng từ; request liên kết được re-evaluate.
- Human approval luôn kiểm tra lại trusted context trước commit, nhằm bắt thay đổi balance/overlap trong thời gian chờ.
- Tất cả bước chính được audit vào SQLite.

## Phạm vi demo hiện tại

- FastAPI + static Vietnamese-first SPA chạy trên port 8000; Ollama chạy riêng ở mặc định `localhost:11434`.
- Dữ liệu nhân viên, role và balance mẫu từ `employees.json`; lịch xác minh chỉ có 2026 và 2027.
- SQLite local, local upload directory, demo actor selector/header, CORS `*` và reset-database endpoint phục vụ demo.
- Verify Harness chạy năm case đánh dấu sẵn, không persist và không gọi LLM.
- Maternity/work accident chưa được quyết policy tự động; production security/deployment/benchmark chưa được chứng minh.

## Key Design Principle

**LLM = semantic extraction.** `qwen2.5:3b-instruct` qua Ollama chuyển free text thành schema facts, hoặc chuyển free-text manager feedback thành một action whitelist. Structured form và manager button không cần LLM. Summary runtime mặc định là deterministic template; LLM polish chỉ chạy khi caller bật `enable_llm_polish`, nhưng route hiện tại không bật cờ này.

**VLM = proof fact extraction.** `qwen2.5vl:7b` đọc file để đề xuất loại giấy, tên, issuer, ngày, signature/readability và các dấu hiệu tương quan/tamper. Output vẫn là unverified. VLM không chứng minh nguồn phát hành hoặc authenticity và không tự gán `VERIFIED`.

**Rule Engine = deterministic policy decision.** `LeaveRuleEngine.evaluate` tính ngày làm việc và chạy các stage policy theo thứ tự cố định, tạo decision/routing/error/trace. Đây là nơi duy nhất quyết outcome policy.

**Backend = orchestration/state.** FastAPI và service tải context tin cậy, gọi AI khi cần, gọi rule engine, quản lý transaction, approval step, audit, proof, booking và balance ledger.

**Human = authority/exception.** Con người xác minh proof, quyết định các bước vượt thẩm quyền, có thể waive đúng hai vi phạm vận hành được code cho phép, yêu cầu thêm facts, sửa có điều kiện hoặc từ chối. Human không được bypass balance, overlap, proof chưa verify, calendar chưa xác minh hay automation scope chưa hỗ trợ.
