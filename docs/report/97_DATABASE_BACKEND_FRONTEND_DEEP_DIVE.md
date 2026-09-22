# Báo cáo chi tiết: Database, Backend và Frontend

## 1. Mục tiêu báo cáo

Báo cáo này mô tả chi tiết cấu trúc hệ thống hiện tại của ứng dụng Leave Application, gồm ba lớp chính:

- Database layer
- Backend API layer
- Frontend UI layer

Mục tiêu là giúp người đọc hiểu rõ:

1. Dữ liệu được lưu ở đâu và theo cấu trúc nào
2. Backend nhận request ở đâu và xử lý như thế nào
3. Frontend tương tác với backend ra sao
4. Luồng nghiệp vụ tổng thể từ người dùng đến quyết định cuối cùng

---

## 2. Toàn cảnh kiến trúc hệ thống

Hệ thống hiện tại có cấu trúc phân tầng rõ ràng:

- Frontend: giao diện web HTML + JavaScript
- Backend: FastAPI server
- Database: SQLite
- Domain logic: rule engine / policy engine
- AI layer: LLM + VLM qua Ollama

Luồng thực tế:

Frontend -> FastAPI Router -> Orchestrator Service -> Rule Engine / AI Models -> SQLite + Local Uploads

### 2.1 Các file cốt lõi

- [backend/main.py](../../backend/main.py)
- [backend/database.py](../../backend/database.py)
- [backend/storage.py](../../backend/storage.py)
- [backend/services/orchestration.py](../../backend/services/orchestration.py)
- [backend/routers/leave_router.py](../../backend/routers/leave_router.py)
- [backend/routers/meta_router.py](../../backend/routers/meta_router.py)
- [backend/routers/verify_router.py](../../backend/routers/verify_router.py)
- [frontend/index.html](../../frontend/index.html)
- [frontend/app.js](../../frontend/app.js)
- [frontend/styles.css](../../frontend/styles.css)

---

## 3. Database layer

## 3.1 Cơ sở dữ liệu hiện tại

Hệ thống dùng SQLite thông qua mô-đun [backend/database.py](../../backend/database.py).

Điểm nổi bật:

- dùng `sqlite3.connect(...)`
- bật `PRAGMA foreign_keys=ON`
- bật `PRAGMA journal_mode=WAL`
- dùng `row_factory = sqlite3.Row`
- database path mặc định là `backend/leave_app.db`

Đây là lớp lưu trữ dữ liệu runtime và trạng thái workflow.

## 3.2 Chức năng khởi tạo DB

Trong [backend/database.py](../../backend/database.py), hàm `get_db_connection()` là điểm khởi tạo kết nối SQLite.

Khi server khởi động, `init_db()` gọi các bước:

1. tạo schema nếu chưa có
2. nạp dữ liệu nhân viên từ `Leave_Application/employees.json`
3. tự động migration nếu DB cũ thiếu field mới
4. nạp demo data nếu bảng rỗng

## 3.3 Các bảng chính

### 3.3.1 `employees`

Bảng này lưu thông tin nhân viên như:

- `employee_id`
- `name`
- `email`
- `department`
- `role`
- `manager_id`
- `remaining_leave_days`
- `status`
- `hire_date`

Ưu điểm: rất phù hợp cho demo workflow khi backend cần load context theo nhân viên.

### 3.3.2 `leave_requests`

Bảng này lưu hồ sơ đơn nghỉ:

- `id`
- `employee_id`
- `employee_name`
- `department`
- `from_date`, `to_date`
- `workdays`
- `leave_type`
- `reason`
- `handover_person_id`, `handover_person_name`
- `attachment_type`
- `decision`
- `uncertainty_category`
- `error_code`
- `target_role`
- `actionable_question`
- `quick_action_options`
- `human_readable_explanation`
- `applied_policy_clauses`
- `status`
- `submitted_at`, `updated_at`
- các trường VLM/LLM: `vlm_analysis_json`, `llm_summary_json`, `doc_patient_name`, `doc_diagnosis`, ...

Đây là bảng cốt lõi của hệ thống.

### 3.3.3 `audit_logs`

Bảng này lưu lịch sử xử lý đơn:

- `request_id`
- `step_name`
- `action`
- `details`
- `created_at`

Mục đích: truy vết hành vi hệ thống, người duyệt, trạng thái chuyển đổi.

## 3.4 Cấu trúc dữ liệu demo

Bảng `employees` được nạp từ [Leave_Application/employees.json](../../Leave_Application/employees.json), và `seed_demo_request()` tạo các đơn mẫu nếu bảng `leave_requests` rỗng.

Điều này giúp hệ thống UI hiện thị dữ liệu ngay khi chạy local mà không cần nhập tay.

## 3.5 Auto-migration database

Trong [backend/database.py](../../backend/database.py), phần `AUTO_MIGRATE_LEAVE_COLUMNS` có nhiệm vụ:

- kiểm tra cột nào đang thiếu
- thêm cột mới nếu DB cũ được tạo trước đó
- gia tăng tính tương thích khi cấu trúc schema thay đổi theo thời gian

Đây là một điểm quan trọng vì hệ thống có nhiều phiên bản và nhiều module kết nối vào cùng bảng.

## 3.6 Hạn chế DB hiện tại

- SQLite là demo/local, không phải production-grade database
- thiếu auth / tenant isolation
- chưa có full RBAC / identity integration
- lưu file upload ở local disk không phải object storage
- chưa có backup/restore robust cho môi trường production

---

## 4. Backend layer

## 4.1 Vai trò backend

Backend là lớp trung tâm, chạy bằng FastAPI. Nó thực hiện các chức năng sau:

- nhận request từ frontend
- xác thực actor demo (`X-Actor-ID` / `actor_id`)
- load trusted context từ SQLite
- gọi LLM nếu cần parse raw text
- gọi VLM nếu có chứng từ
- chạy rule engine
- lưu state và audit
- trả về phản hồi cho frontend

## 4.2 File chính của backend

- [backend/main.py](../../backend/main.py)
- [backend/services/orchestration.py](../../backend/services/orchestration.py)
- [backend/storage.py](../../backend/storage.py)
- [backend/routers/leave_router.py](../../backend/routers/leave_router.py)
- [backend/routers/meta_router.py](../../backend/routers/meta_router.py)
- [backend/routers/verify_router.py](../../backend/routers/verify_router.py)

## 4.3 `main.py`: điểm khởi tạo server

[backend/main.py](../../backend/main.py) làm các việc chính:

- khởi tạo `FastAPI` app
- register CORS
- register routers
- mount static frontend assets
- warm-up AI models khi server khởi động
- gắn handler cho exception

### 4.3.1 Warm-up AI

Hệ thống có hai hàm khóa:

- `_warmup_llm()`
- `_warmup_vlm()`

Mục tiêu: preload model ngay khi server chạy, để lần request đầu không mất nhiều thời gian.

## 4.4 Middleware và exception

Backend gắn các middleware và exception handler:

- `X-Total-Api-Ms`: đo thời gian xử lý API
- `AccessDenied`, `Conflict`, `ModelUnavailable`, `LookupError`, `ValueError`

Điều này giúp front-end nhận biết rõ lỗi và trạng thái.

## 4.5 Router chính

### 4.5.1 `leave_router`

Responsible for:

- submit leave request
- process human decisions
- create / update / review leave applications
- handle upload proof
- route to orchestrator

### 4.5.2 `meta_router`

Responsible for:

- AI status
- model status
- policy metadata
- calendar metadata
- environment status

### 4.5.3 `verify_router`

Responsible for:

- QA / verification harness
- deterministic validation cases
- verifying scenarios without full heavy workflow

## 4.6 Orchestrator (`LeaveOrchestratorService`)

[backend/services/orchestration.py](../../backend/services/orchestration.py) là lớp cốt lõi của backend.

Nó thực hiện phần lớn logic nghiệp vụ:

1. load trusted context từ DB
2. đọc `facts` từ form hoặc raw text
3. nếu có proof -> gọi VLM
4. gọi `LeaveRuleEngine.evaluate()`
5. update record state
6. persist decision / explanation / policy clauses
7. audit và trả về response

### 4.6.1 `_evaluate()`

Đây là function quan trọng nhất.

Nó làm các bước sau:

- parse `facts`
- detect attachment / proof
- trigger VLM if needed
- run rule engine
- hydrate result JSON and DB row
- set status to `COMPLETED`, `REJECTED`, `WAITING_EMPLOYEE`, `PENDING_ESCALATION`, ...

## 4.7 Luồng xử lý request

### 4.7.1 Structured form

- frontend gửi form structured
- backend load context
- rule engine đánh giá
- nếu đạt chuẩn: commit booking / balance
- nếu cần thêm thông tin: trả về `NEED_CORRECTION`
- nếu vượt cấp: trả về `ESCALATE`

### 4.7.2 Free text

- backend gửi raw text cho LLM
- LLM parse thành `RequestFacts`
- rule engine quyết định final
- không cho phép AI tự quyết policy

### 4.7.3 Proof / attachment

- file được lưu xuống upload storage
- VLM đọc file
- kết quả lưu vào `vlm_analysis_json`
- rule engine dùng các thông tin đó trong phần proof validation
- nhưng proof chưa được `VERIFIED` cho đến khi HR / manager xác nhận

## 4.8 Quyền hạn / actor model

Backend dùng demo identity model:

- `X-Actor-ID` header
- hoặc `actor_id` trong request

Thông tin role và quyền được lấy từ context/DB, không phải JWT production.

Đây là model demo phù hợp cho hackathon hoặc bối cảnh local.

## 4.9 Hạn chế backend

- không có real authentication
- không có RBAC/authorization thực sự
- SQLite local không đủ cho production scale
- upload file local, thiếu object storage và antivirus
- dùng CORS `*` và không có security layer
- chưa có full observability / retry / idempotency

---

## 5. Frontend layer

## 5.1 Vai trò frontend

Frontend là giao diện web dạng SPA (static HTML + JavaScript), nằm trong [frontend/index.html](../../frontend/index.html) và [frontend/app.js](../../frontend/app.js).

Nó hoạt động như giao diện cho:

- nhân viên nộp đơn
- manager xem queue và xử lý
- admin / QA xem logs và test harness
- người dùng đọc policy

## 5.2 Cấu trúc frontend

### 5.2.1 `index.html`

File này chứa layout tổng thể:

- header
- tabs
- side panel
- form area
- manager queue area
- policy area
- test harness

### 5.2.2 `app.js`

Đây là file cốt lõi của UI logic. Nó chứa:

- `apiFetch` wrapper
- role labels / decision labels
- i18n dictionary
- initializers cho tabs và modals
- logic render request list
- logic submit form
- logic fetch policies and statuses

### 5.2.3 `styles.css`

Chứa giao diện CSS, form styling, dashboard layout, card UI, table layout.

## 5.3 Chế độ frontend

Frontend hỗ trợ nhiều chế độ chính:

- Staff portal
- Manager portal
- Test harness
- Policy page

Điều này cho phép demo một app cùng lúc với nhiều người dùng giả lập.

## 5.4 Tương tác API

Frontend không gọi model trực tiếp; nó chỉ gọi API backend qua `fetch()`.

Ví dụ:

- submit leave request
- get leave requests by employee
- get manager queue
- get policy / AI status
- verify proofs

## 5.5 UX / demo flow

### 5.5.1 Nhân viên

- chọn loại nghỉ
- chọn ngày
- chọn lý do
- upload chứng từ nếu cần
- gửi đơn lên backend
- nhận decision + explanation

### 5.5.2 Manager

- xem queue
- nhận request cần escalated
- approve / reject / request more info
- backend re-evaluate sau khi human action

### 5.5.3 QA

- chạy bộ test / harness
- so sánh expected vs actual
- kiểm tra route logic

## 5.6 Hạn chế frontend

- demo UI hơn là sản phẩm production
- không có auth real
- không có secure session
- data render phụ thuộc nhiều vào API backend
- không có testing automation UI tối ưu

---

## 6. Liên kết giữa 3 lớp

### 6.1 Database <-> Backend

Backend đọc và ghi từ SQLite thông qua `database.py` và `storage.py`.

### 6.2 Backend <-> Frontend

Frontend gọi REST APIs để đọc / submit / approve / review data.

### 6.3 Backend <-> AI

Backend orchestrator quyết định khi nào gọi LLM / VLM, sau đó merge output vào quyết định chính sách.

### 6.4 Frontend <-> User

Frontend hiện thị quyết định, `target_role`, `error_code`, `actionable_question`, `explanation` cho người dùng.

---

## 7. Tóm tắt hoạt động tổng thể

Một request đi qua chuỗi sau:

1. Nhân viên điền form hoặc nhập text
2. Frontend gọi backend route
3. Backend load context từ SQLite
4. Backend gọi LLM nếu cần parse text
5. Backend gọi VLM nếu có chứng từ
6. Rule engine đánh giá quyết định
7. Backend lưu kết quả vào database
8. Frontend render kết quả cho người dùng
9. Nếu cần human approval, frontend hiển thị queue và request action cho manager / HR / CEO

---

## 8. Kết luận

Hệ thống hiện tại có kiến trúc rõ ràng và hợp lý cho demo / prototype:

- Database: SQLite, đủ cho local demo
- Backend: FastAPI, orchestrator-based, tách chức năng rất rõ
- Frontend: static SPA, dễ chạy, dễ demo, rất phù hợp cho hackathon

Tuy nhiên, nếu cần nâng lên production-grade thì cần làm thêm:

- auth/authorization mạnh hơn
- database production (Postgres)
- file storage robust
- monitoring & tracing
- infrastructure security
- AI quality evaluation

---

## 9. Dấu hiệu hệ thống hiện tại

Hệ thống triển khai đúng mô hình:

- AI hỗ trợ extraction
- Rule engine quyết định policy
- Human thực hiện quyền phê duyệt đặc biệt
- Database là nơi lưu trạng thái thực tế
- Frontend là lớp tương tác cho user

Vì vậy, cơ chế này là “hybrid deterministic + AI-assisted orchestration”, không phải “AI tự quyết định đơn nghỉ hoàn toàn”.
