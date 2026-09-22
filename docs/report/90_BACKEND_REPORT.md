# Backend Report

## 1. Mục đích

Backend là khối server chính, chịu trách nhiệm:

- nhận request từ frontend
- xác thực actor demo (`X-Actor-ID` hoặc `actor_id`)
- nạp context từ SQLite
- gọi AI khi cần
- chạy rule engine
- persist request, audit, proof, booking, balance
- điều phối escalation / approval

## 2. File quan trọng

- [backend/main.py](../../backend/main.py)
- [backend/services/orchestration.py](../../backend/services/orchestration.py)
- [backend/database.py](../../backend/database.py)
- [backend/storage.py](../../backend/storage.py)
- [backend/routers/leave_router.py](../../backend/routers/leave_router.py)
- [backend/routers/meta_router.py](../../backend/routers/meta_router.py)
- [backend/routers/verify_router.py](../../backend/routers/verify_router.py)

## 3. Kiến trúc hoạt động

Backend theo mô hình FastAPI:

1. Route tiếp nhận request từ frontend hoặc API client
2. Orchestrator load context thực thi từ database
3. Nếu có free text thì gọi LLM
4. Nếu có chứng từ thì gọi VLM
5. Rule engine đánh giá quyết định
6. Lưu trạng thái và ledger / audit

## 4. Chức năng chính

### 4.1 Invoke / request lifecycle

- `leave_router` xử lý tạo đơn nghỉ, điều chỉnh, submit, human decision
- `verify_router` phục vụ verify harness / các case kiểm chứng
- `meta_router` cung cấp trạng thái AI, policy, calendar, status

### 4.2 Orchestrator

- `LeaveOrchestratorService` là lớp điều phối cốt lõi
- Nó có phương thức `_evaluate` chạy:
  - load trusted context
  - gọi VLM nếu có proof
  - gọi rule engine
  - lưu kết quả với status và explanation

### 4.3 Database state

- SQLite lưu:
  - request
  - approval steps
  - proof documents
  - audit logs
  - booking / balance ledger

### 4.4 Upload / proof handling

- file upload lưu trong `backend/uploads` hoặc `uploads/`
- VLM đọc file path để trích xuất dữ liệu chứng từ
- proof không tự động được xác thực; chỉ HR / manager mới đánh dấu `VERIFIED`

## 5. Quy tắc chiến lược chính

- LLM không được quyết định chính sách
- VLM chỉ trích xuất dữ liệu unverified
- Rule engine mới là nơi quyết định policy
- Human approval chỉ được dùng ở ngưỡng thẩm quyền / exception

## 6. Kết luận module Backend

Backend là lớp orchestration trung tâm, nối liền 4 phần:

- frontend
- AI/LLM/VLM
- deterministic rules
- persistent data layer

Nó hoạt động như một hệ thống điều phối, không phải là module AI tự quyết định.

## 7. Điểm mạnh

- Trách nhiệm rõ ràng giữa AI, rule engine, human
- Dữ liệu tin cậy được lưu trong DB
- Audit trail và workflow state tốt

## 8. Hạn chế

- Chưa có auth production-grade
- CORS mở toàn cục
- SQLite là local demo, không production-ready
- Không có auth/tenant isolation  đầy đủ
