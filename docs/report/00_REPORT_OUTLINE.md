# Đề cương technical progress / final report

## Quy ước bằng chứng

- Chính sách có thẩm quyền cao nhất: `Leave_Application/policy_rules.md`.
- Hành vi đã triển khai chỉ được khẳng định khi có đường chạy trong code hiện tại; `raw_policy.json` chỉ là nguồn lịch sử.
- Trạng thái dùng trong bộ tài liệu: `DONE`, `PARTIAL`, `DEMO-ONLY`, `TODO`.
- Số liệu hiệu năng chưa có phép đo runtime mới được ghi `NOT MEASURED`.
- `LLM-KIET/README.md`, `LUONG_THUC_THI_HE_THONG.md` và `DANH_SACH_TRUONG_HOP_ESCALATION.md` có nội dung legacy/deprecated. Các claim về Qwen 7B in-process, LLM quyết routing, hoặc lý do “chán đi làm” bị chặn không phản ánh code hiện tại.
- `LUONG_HOAT_DONG.md` cũng stale ở các nhánh thiếu proof/hết balance, phép trừ cho non-annual và khả năng gửi free text kèm file. `HUONG_DAN_CHAY_LOCALHOST.md` còn hữu ích cho port/script, nhưng dependency/model/test command đã lệch code hiện tại. Chỉ dùng sau khi đối chiếu `requirements*.txt`, `ai_stack.py` và pytest.
- `KHAO_SAT_DAC_TRUNG_DATABASE_SAMPLE.md` là khảo sát/đề xuất, không phải schema runtime. Schema thực tế nằm trong `backend/database.py` và `backend/migrations.py`.

## 1. Abstract / Executive Summary

**Mục tiêu section:** Tóm tắt bài toán điều phối đơn nghỉ, kiến trúc hybrid deterministic + AI extraction, kết quả triển khai và giới hạn demo.

**Nguồn:** `policy_rules.md`; `domain.py`; `rule_engine.py`; `backend/services/orchestration.py`; `backend/main.py`; `LLM-KIET/ai_stack.py`.

**Hình/bảng nên có:** Một sơ đồ một trang “Input → extraction → trusted context → rule engine → human”; bảng trạng thái `DONE/PARTIAL/DEMO-ONLY/TODO`.

**Chưa đủ evidence:** Kết quả đánh giá định lượng, benchmark latency/throughput, độ chính xác LLM/VLM, môi trường deployment cuối cùng.

## 2. Problem Statement

**Mục tiêu section:** Nêu nhu cầu xử lý nhiều loại nghỉ với lịch, số dư, chứng từ, quota và thẩm quyền khác nhau mà không giao quyết định policy cho mô hình sinh.

**Nguồn:** Chương I–III của `policy_rules.md`; `taxonomy.py`; `rule_engine.py`.

**Hình/bảng nên có:** Bảng nhóm rủi ro: thiếu facts, vi phạm vận hành, vượt thẩm quyền, chứng từ chưa xác minh.

**Chưa đủ evidence:** Dữ liệu thực tế về khối lượng đơn, thời gian xử lý thủ công, tỷ lệ lỗi trước khi có hệ thống.

## 3. Objectives and Scope

**Mục tiêu section:** Tách mục tiêu hiện có khỏi phạm vi chưa làm: form/free text, calendar 2026–2027, rule engine, workflow người duyệt, proof/VLM và verify harness.

**Nguồn:** `backend/routers/*.py`; `backend/services/orchestration.py`; `frontend/index.html`; `frontend/app.js`; `test_cases.json`.

**Hình/bảng nên có:** Ma trận “in scope / partial / out of scope”.

**Chưa đủ evidence:** Production SLA, SSO/RBAC doanh nghiệp, legal sign-off, tích hợp HRIS/BHXH, mobile/accessibility acceptance.

## 4. Policy Model

**Mục tiêu section:** Mô tả nguồn policy, loại nghỉ, entitlement, notice, quota, handover, proof, overlap, probation, anti-abuse và authority.

**Nguồn:** `policy_rules.md` (authoritative); `domain.py`; `taxonomy.py`; `rule_engine.py`; `calendar_service.py`.

**Hình/bảng nên có:** Bảng policy-to-code traceability; bảng năm outcome; ma trận loại nghỉ × điều kiện × thẩm quyền.

**Chưa đủ evidence:** Cấu hình cho nhóm lao động đặc thù; lịch ngoài 2026–2027; xác nhận pháp lý cuối cùng; chi tiết maternity/work accident trong engine.

## 5. System Architecture

**Mục tiêu section:** Trình bày frontend, FastAPI routers, orchestrator, LLM/VLM qua Ollama, rule/calendar engine, SQLite và human review.

**Nguồn:** `backend/main.py`; `backend/routers/*.py`; `backend/services/orchestration.py`; `LLM-KIET/*.py`; `Leave_Application/vlm_inspector.py`; `backend/database.py`; `backend/storage.py`.

**Hình/bảng nên có:** Component diagram và trust-boundary diagram.

**Chưa đủ evidence:** Topology production, reverse proxy/TLS, containerization, secrets, observability, backup/restore đã kiểm chứng.

## 6. Workflow

**Mục tiêu section:** Theo dõi bốn đường chạy: structured form, form + proof, free text, human approval/re-evaluation.

**Nguồn:** `leave_router.py`; `orchestration.py`; `storage.py`; `agent_orchestrator.py`; `rule_engine.py`.

**Hình/bảng nên có:** Overall flow, escalation flow và bốn sequence diagrams trong `02_ARCHITECTURE_AND_WORKFLOW.md`.

**Chưa đủ evidence:** UX study, failure-recovery runbook và production retry/idempotency ngoài các invariant đã test.

## 7. LLM/VLM Components

**Mục tiêu section:** Nêu đúng model, call sites, schema extraction, VLM facts, fallback/error behavior và ranh giới quyền quyết định.

**Nguồn:** `ai_stack.py`; `llm_client.py`; `agent_orchestrator.py`; `prompts.py`; `schemas.py`; `vlm_inspector.py`; `orchestration.py`; `test_model_invocation_counts.py`.

**Hình/bảng nên có:** Bảng component/input/output/authority/call count; sơ đồ trusted vs untrusted facts.

**Chưa đủ evidence:** Accuracy/F1, hallucination rate, OCR quality by document type, measured cold-start and inference latency.

## 8. Deterministic Rule Engine

**Mục tiêu section:** Giải thích thứ tự stage, short-circuit, calendar, entitlement, proof, overlap, balance, notice, quota, handover, authority và balance mutation.

**Nguồn:** `rule_engine.py`; `calendar_service.py`; `storage.py`; `taxonomy.py`.

**Hình/bảng nên có:** Decision pipeline; bảng outcome và error code; ledger/transaction diagram.

**Chưa đủ evidence:** Formal verification, property-based testing, full policy-coverage matrix và resolution cho policy/code mismatches.

## 9. Human-in-the-loop / Escalation

**Mục tiêu section:** Mô tả target role, approval steps, button/free-text action, HR proof verification, conditional modification, re-evaluation và audit.

**Nguồn:** `orchestration.py`; `storage.py`; `leave_router.py`; `taxonomy.py`; `test_api_e2e.py`.

**Hình/bảng nên có:** Escalation state machine; role/authority matrix.

**Chưa đủ evidence:** Production identity provider, delegation/absence of approver, notification channels, retention and audit governance.

## 10. Implementation Progress

**Mục tiêu section:** Gắn trạng thái có kiểm soát cho từng module và chỉ ra phần còn lại.

**Nguồn:** Toàn bộ code/runtime paths; `05_IMPLEMENTATION_AND_PROGRESS.md`.

**Hình/bảng nên có:** Status matrix; changelog không ngày dựa trên artifact version/legacy markers.

**Chưa đủ evidence:** Sprint history, owner/contribution, completion dates và acceptance sign-off.

## 11. Testing / Evaluation

**Mục tiêu section:** Mô tả 30 canonical cases, unit/invariant tests, API/E2E, invocation-count tests và 5-case Verify Harness.

**Nguồn:** `tests/scenarios.py`; `test_cases.json`; `test_decision_tree.py`; `test_api_e2e.py`; `test_llm_kiet.py`; `test_model_invocation_counts.py`; `verify_router.py`.

**Hình/bảng nên có:** Coverage-by-behavior matrix; representative cases; runtime result box.

**Chưa đủ evidence:** Không có pytest trong interpreter hiện tại nên chưa có test run mới; model-quality evaluation và performance benchmark đều `NOT MEASURED`.

## 12. Limitations

**Mục tiêu section:** Công khai các giới hạn thật: demo identity, SQLite/local upload, CORS mở, unauthenticated reset endpoint, lịch hữu hạn, partial leave types, VLM không xác thực nguồn, free-text không gắn proof và mismatch policy/code.

**Nguồn:** `main.py`; `meta_router.py`; `leave_router.py`; `calendar_service.py`; `rule_engine.py`; `orchestration.py`; `vlm_inspector.py`.

**Hình/bảng nên có:** Risk/impact/mitigation table.

**Chưa đủ evidence:** Threat model, pentest, privacy impact assessment, production capacity.

## 13. Future Work

**Mục tiêu section:** Chuyển từng limitation thành hạng mục có thể nghiệm thu, không mô tả như tính năng đã có.

**Nguồn:** Khoảng cách giữa `policy_rules.md` và code; `07_LIMITATIONS_AND_FUTURE_WORK.md`.

**Hình/bảng nên có:** Prioritized backlog theo policy correctness, security, AI evaluation, operations.

**Chưa đủ evidence:** Priority/owner/deadline và nguồn lực.

## 14. Demo / Reproducibility

**Mục tiêu section:** Hướng dẫn dependency, Ollama models, server, UI/API và Verify Harness; tách mock/test khỏi production-like path.

**Nguồn:** `requirements*.txt`; `backend/run_server.sh`; `HUONG_DAN_CHAY_LOCALHOST.md` (chỉ dùng phần còn khớp code); `ai_stack.py`; `verify_router.py`.

**Hình/bảng nên có:** Demo script; environment matrix; danh sách case dự kiến.

**Chưa đủ evidence:** Hardware cuối, exact package lock, clean-machine reproduction, screenshots/video và runtime results được ký nhận.

## Open Questions Before Final Report

1. Kết quả pytest mới nhất trên môi trường chuẩn là gì? Dùng commit/hash nào?
2. Accuracy của LLM parser và VLM extraction trên tập dữ liệu gán nhãn là bao nhiêu?
3. Benchmark cold start, p50/p95 latency, throughput và peak memory/VRAM là gì?
4. Môi trường demo/final deployment cụ thể: OS, CPU, GPU, RAM, Ollama version và model digests?
5. Bộ ảnh/chứng từ đánh giá có quyền sử dụng và đã ẩn dữ liệu cá nhân chưa?
6. Team chọn những case nào cho final demo, và expected output đã được policy owner duyệt chưa?
7. Ai là policy owner/legal reviewer xác nhận `policy_rules.md` phiên bản 3.0.0?
8. Routing đúng mong muốn cho `SICK_MEDICAL` trên 5 ngày là HR hay Direct Manager?
9. Với `ANNUAL` từ 20 ngày, có cần chuỗi duyệt Department Head → CEO hay chỉ CEO như code hiện tại?
10. Maternity và work accident cần mức tự động hóa nào trong bản final?
11. Có giữ VLM tamper/AI-edit signals trong UI không, và disclaimer về việc đây chỉ là nghi vấn sẽ hiển thị thế nào?
12. Production có dùng SSO/RBAC, object storage, encryption, retention và audit export nào?
13. Screenshot, architecture figure và video demo nào được chọn cho submission?
14. Phân công đóng góp của từng thành viên và mốc tiến độ chính thức là gì?
15. Có chấp nhận giới hạn free-text không kèm proof, hay cần workflow ghép proof vào đơn text?
