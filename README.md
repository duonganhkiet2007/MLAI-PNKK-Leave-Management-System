# The Escalation Referee

Hệ thống điều phối phê duyệt nghỉ phép tích hợp AI (MLAI Hackathon 2026). Hệ thống dùng **Rule Engine quyết định** kết hợp **VLM (Qwen2.5-VL)** để đọc chứng từ (giấy khám bệnh, giấy kết hôn, giấy tang lý...) và tự động phân luồng phê duyệt theo quy chế nội bộ & Bộ luật Lao động 2019.

- **Backend:** FastAPI + SQLite
- **AI:** Ollama + `qwen2.5vl:7b` (chỉ đọc chứng từ, không sinh quyết định)
- **Frontend:** SPA HTML/JS thuần (Tabler UI), phục vụ ngay bởi FastAPI tại `/`
- **Quyết định:** 100% deterministic rule engine (không có LLM halluncination trong luồng phê duyệt)

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu tối thiểu | Ghi chú |
|---|---|---|
| Hệ điều hành | Linux / macOS / Windows (WSL2) | Khuyến nghị Linux |
| Docker | Engine 24+ & Compose v2 | Cách chạy nhanh nhất |
| GPU | NVIDIA ≥ 8 GB VRAM | Bắt buộc cho VLM `qwen2.5vl:7b` |
| NVIDIA Driver | Phiên bản tương ứng với card | Kiểm tra: `nvidia-smi` |
| nvidia-container-toolkit | Đã cài | Để Docker dùng GPU |

Nếu chỉ chạy thử không có GPU, vẫn chạy được nhưng VLM sẽ rơi về CPU (chậm, dễ timeout).

---

## Cách 1 — Chạy bằng Docker (khuyến nghị)

Toàn bộ backend, Ollama và model được đóng gói trong Docker. Bạn không cần cài Python hay Ollama trực tiếp.

### 1. Clone repository

```bash
git clone https://github.com/duonganhkiet2007/MLAI-PNKK-Leave-Management-System.git
cd MLAI-PNKK-Leave-Management-System
```

### 2. (Tùy chọn) Cấu hình biến môi trường

```bash
cp .env.example .env
# Mở .env chỉnh nếu cần (mặc định đã chạy được)
```

### 3. Build & khởi động toàn bộ stack

```bash
docker compose -f deploy/docker-compose.yml up --build -d
```

Compose sẽ làm theo thứ tự:
1. Khởi động `ollama` (có gắn NVIDIA GPU).
2. `ollama-model-init` tự động `ollama pull qwen2.5vl:7b` (lần đầu tải ~5 GB, cần Internet).
3. Khi model sẵn sàng, `backend` khởi động và tự nạp VLM vào GPU.

### 4. Kiểm tra trạng thái

```bash
# Xem model đã được pull chưa
docker compose -f deploy/docker-compose.yml exec ollama ollama list

# Kiểm tra backend healthy
curl -fsS http://localhost:8000/api/meta/health
```

Kết quả mong đợi:
- `ollama list` có dòng `qwen2.5vl:7b`.
- Health endpoint trả JSON có `status: ok`.

### 5. Mở giao diện

Mở trình duyệt: **http://localhost:8000**

Tài liệu Swagger API: **http://localhost:8000/docs**

### Các lệnh thường dùng

```bash
# Xem log realtime
docker compose -f deploy/docker-compose.yml logs -f backend

# Dừng stack (giữ dữ liệu & model trong volume)
docker compose -f deploy/docker-compose.yml down

# Xóa toàn bộ dữ liệu & model (cần pull lại lần sau)
docker compose -f deploy/docker-compose.yml down -v
```

### Khởi động lại (sau lần đầu)

Sau khi đã build xong và pull model lần đầu, những lần sau không cần `--build` nữa:

```bash
# Khởi động lại toàn bộ stack (image đã có, model đã có trong volume)
docker compose -f deploy/docker-compose.yml up -d

# Chỉ restart backend (ví dụ sau khi sửa code, hoặc backend bị treo)
docker compose -f deploy/docker-compose.yml restart backend

# Restart cả ollama lẫn backend
docker compose -f deploy/docker-compose.yml restart
```

Nếu model `qwen2.5vl:7b` bị xóa khỏi volume (ví dụ chạy `down -v`), pull lại thủ công:

```bash
docker compose -f deploy/docker-compose.yml up -d ollama
docker compose -f deploy/docker-compose.yml exec ollama ollama pull qwen2.5vl:7b
docker compose -f deploy/docker-compose.yml up -d backend
```

> **Lưu ý GPU:** Nếu máy không có NVIDIA GPU, mở `deploy/docker-compose.yml`, tìm service `ollama` và xóa block `deploy:` (từ dòng `deploy:` đến hết `capabilities: [gpu]`).

---

## Chạy bộ kiểm thử

Chạy trong container backend (có sẵn source code + dependencies):

```bash
# Image backend đã có sẵn toàn bộ dependencies (production + test).
# Chạy toàn bộ tests:
docker compose -f deploy/docker-compose.yml exec -w /app backend pytest evaluation/ -v

# Chạy một file cụ thể:
docker compose -f deploy/docker-compose.yml exec -w /app backend pytest evaluation/test_decision_tree.py -v
```

Tests dùng mock VLM (`VLM_FORCE_MOCK=1`) nên không cần GPU hay Ollama đang chạy.

---

## Cấu trúc thư mục (Working Tree)

```
MLAI/
├── backend/                     # API FastAPI & điều phối
│   ├── ai/                      # Kết nối Ollama, schemas, orchestrator
│   │   ├── ai_stack.py          # Canonical AI stack (OLLAMA_BASE, VLM_TARGET_MODEL...)
│   │   ├── agent_orchestrator.py
│   │   ├── llm_client.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   ├── routers/                 # Các API endpoint
│   │   ├── leave_router.py      # Tạo/xem đơn nghỉ phép
│   │   ├── verify_router.py     # Verify harness (cho ban giám khảo)
│   │   ├── meta_router.py       # Health, policy, metrics
│   │   ├── auth_router.py       # Đăng nhập, token
│   │   └── employee_router.py  # Quản lý nhân sự
│   ├── services/
│   │   ├── orchestration.py     # Điều phối rule engine + VLM
│   │   └── inspection_service.py
│   ├── data/                    # SQLite DB, uploads (runtime, không commit)
│   ├── main.py                  # Entry point, lifespan, CORS
│   ├── database.py              # SQLite init, employees.json seed
│   ├── storage.py               # Transaction, leave ledger
│   ├── auth.py
│   ├── metrics.py
│   └── run_server.sh            # Script khởi động local
│
├── core/                        # Rule engine & domain logic
│   ├── rule_engine.py           # Decision tree 8 nhánh nghỉ phép
│   ├── domain.py                # RequestFacts, ProofType, policy metadata
│   ├── taxonomy.py              # ApprovalResult taxonomy
│   ├── vlm_inspector.py         # Đọc chứng từ qua VLM (cv2 + PIL)
│   ├── vlm_normalizer.py        # Chuẩn hóa ngày tháng, tên tiếng Việt
│   ├── calendar_service.py      # Lịch nghỉ lễ 2026-2027
│   ├── employees.json           # Dữ liệu nhân sự mẫu
│   ├── raw_policy.json          # Quy chế nghỉ phép dạng thô
│   ├── policy_rules.md          # Quy chế dạng văn bản
│   └── calendars/               # holidays_2026.json, holidays_2027.json
│
├── frontend/                    # Giao diện web (phục vụ bởi FastAPI)
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   ├── employee_management.js
│   ├── employee_management.css
│   ├── assets/proofs/           # Ảnh chứng từ mẫu (demo)
│   └── vendor/tabler/           # Tabler UI (CSS/JS)
│
├── deploy/                      # Docker
│   ├── Dockerfile
│   ├── docker-compose.yml       # backend + ollama + model-init
│   └── README.md
│
├── evaluation/                  # Kiểm thử & đánh giá (tests + benchmarks)
│   ├── conftest.py, test_*.py   # pytest (rule engine, API, VLM mock)
│   └── benchmarks/              # Đánh giá hiệu năng, độ tin cậy, VLM quality
│
├── requirements.txt             # Dependencies (production + test)
├── .env.example                 # Mẫu biến môi trường
├── .dockerignore
├── .gitignore
└── README.md
```

---

## Biến môi trường chính

| Biến | Mặc định | Mô tả |
|---|---|---|
| `VLM_TARGET_MODEL` | `qwen2.5vl:7b` | Tên model VLM trên Ollama |
| `OLLAMA_BASE` | `http://localhost:11434` | URL Ollama (trong Docker: `http://ollama:11434`) |
| `VLM_MAX_IMAGE_DIM` | `1600` | Kích thước ảnh tối đa gửi VLM |
| `VLM_WARMUP_ON_STARTUP` | `1` | Tự nạp VLM vào GPU khi khởi động |
| `OLLAMA_KEEP_ALIVE` | `-1` | Giữ model trên GPU (-1 = vĩnh viễn) |
| `VLM_TIMEOUT_SEC` | `180` | Timeout gọi VLM (giây) |
| `PORT` | `8000` | Cổng backend |
| `CORS_ALLOW_ORIGINS` | `http://localhost:8000` | Origin cho phép CORS |
| `LEAVE_DB_PATH` | `backend/data/leave_app.db` | Đường dẫn SQLite DB |
| `LEAVE_UPLOAD_DIR` | `backend/data/uploads` | Thư mục lưu ảnh chứng từ |

Xem chi tiết tại [.env.example](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/.env.example).

---

## Ghi chú

- **Dữ liệu runtime:** SQLite DB (`leave_app.db`) và ảnh upload nằm trong volume Docker `app_data` (hoặc `~/.local/share/mlai-pnkk/data` khi chạy local). Các file này không được commit.
- **Model Ollama:** Lưu trong volume `ollama_models`, không mất khi `down`.
- **Quyết định phê duyệt:** Luôn do rule engine quyết định. VLM chỉ trích xuất thông tin từ chứng từ (loại giấy, ngày, tên người, số ngày nghỉ).
- **8 loại nghỉ phép:** Nghỉ phép năm, Nghỉ không lương, Nghỉ phúc lợi, Nghỉ luật định, Nghỉ ốm, Cấp cứu, Tai nạn lao động, Thai sản.

## License

Repository hiện chưa có file `LICENSE`; điều khoản sử dụng và phân phối chưa được khai báo.
