# The Escalation Referee

Hệ thống điều phối phê duyệt nghỉ phép tích hợp AI (MLAI Hackathon 2026). Quyết định phê duyệt do **Rule Engine** xử lý hoàn toàn; **VLM (Qwen2.5-VL)** chỉ trích xuất thông tin từ chứng từ (loại giấy, ngày, tên, số ngày nghỉ).

- **Backend:** FastAPI + SQLite
- **AI:** Ollama + `qwen2.5vl:7b` (chỉ đọc chứng từ)
- **Frontend:** SPA HTML/JS (Tabler UI), phục vụ tại `/`
- **Phạm vi:** 8 loại nghỉ phép — phép năm, không lương, phúc lợi, luật định, ốm, cấp cứu, tai nạn lao động, thai sản

**Tài liệu & Demo**

- Link Proposal: https://docs.google.com/document/d/1vvmc66DHWcx4OMFSgipeEEpDdnL_SFszAKhkrALF1Xg/edit?usp=sharing
- Link Video Demo: https://drive.google.com/file/d/17AcEXeBfeE7FbaUK6FAuJROpsaZFLUgh/view?usp=sharing
- Link Dataset: https://docs.google.com/spreadsheets/d/1_d9vUImx0TX7yeGoFwtnWIQRDaDFpi_XKqALEeNs1KA/edit?usp=sharing

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Linux / macOS / Windows (WSL2) |
| Docker | Engine 24+ & Compose v2 |
| GPU | NVIDIA ≥ 16 GB VRAM (cần cho VLM `qwen2.5vl:7b` ở mức Q8+; <16 GB Ollama tự hạ xuống Q4, đọc chứng từ kém chính xác) |
| NVIDIA Driver | Phiên bản tương ứng card (kiểm tra: `nvidia-smi`) |
| nvidia-container-toolkit | Đã cài (để Docker truy cập GPU) |

Không có GPU vẫn chạy được, nhưng VLM rơi về CPU (chậm, dễ timeout).

---

## Chạy bằng Docker

```bash
git clone https://github.com/duonganhkiet2007/MLAI-PNKK-Leave-Management-System.git
cd MLAI-PNKK-Leave-Management-System
docker compose -f deploy/docker-compose.yml up --build -d
```

Compose tự động theo thứ tự: khởi động `ollama` (gắn GPU) → `ollama-model-init` pull `qwen2.5vl:7b` (~5 GB, cần Internet) → `backend` lên và nạp VLM.

Kiểm tra:

```bash
docker compose -f deploy/docker-compose.yml exec ollama ollama list   # phải thấy qwen2.5vl:7b
curl -fsS http://localhost:8000/api/meta/health                        # {"status":"ok"}
```

Giao diện: **http://localhost:8000** · Swagger: **http://localhost:8000/docs**

### Lệnh thường dùng

```bash
docker compose -f deploy/docker-compose.yml logs -f backend        # xem log
docker compose -f deploy/docker-compose.yml down                   # dừng (giữ dữ liệu & model)
docker compose -f deploy/docker-compose.yml down -v                # dừng + xóa volume (mất dữ liệu & model)
docker compose -f deploy/docker-compose.yml up -d                  # khởi động lại (đã có image & model)
docker compose -f deploy/docker-compose.yml restart backend        # restart chỉ backend
```

Nếu model bị xóa (sau `down -v`), pull lại thủ công:

```bash
docker compose -f deploy/docker-compose.yml up -d ollama
docker compose -f deploy/docker-compose.yml exec ollama ollama pull qwen2.5vl:7b
docker compose -f deploy/docker-compose.yml up -d backend
```

> **Không có GPU:** Mở `deploy/docker-compose.yml`, trong service `ollama` xóa block `deploy:` (từ `deploy:` đến hết `capabilities: [gpu]`).

---

## Chạy bộ kiểm thử

Tests chạy trong container backend (dùng mock VLM, không cần GPU):

```bash
docker compose -f deploy/docker-compose.yml exec -w /app backend pytest evaluation/ -v
docker compose -f deploy/docker-compose.yml exec -w /app backend pytest evaluation/test_decision_tree.py -v
```

---

## Cấu trúc thư mục

```
MLAI/
├── backend/                     # FastAPI: API, orchestration, DB, auth
│   ├── ai/                      # Ollama client, prompts, schemas, orchestrator
│   ├── routers/                 # leave, verify, meta, auth, employee
│   ├── services/                # orchestration, inspection
│   ├── main.py                  # Entry point
│   ├── database.py              # SQLite init + seed employees.json
│   └── storage.py               # Transaction & leave ledger
│
├── core/                        # Domain logic & rule engine
│   ├── rule_engine.py           # Decision tree 8 nhánh nghỉ phép
│   ├── domain.py                # RequestFacts, ProofType, policy metadata
│   ├── vlm_inspector.py         # Đọc chứng từ qua VLM (cv2 + PIL)
│   ├── vlm_normalizer.py        # Chuẩn hóa ngày tháng, tên tiếng Việt
│   ├── calendar_service.py      # Lịch nghỉ lễ 2026-2027
│   ├── employees.json           # Dữ liệu nhân sự mẫu
│   └── policy_rules.md          # Quy chế nghỉ phép
│
├── frontend/                    # Giao diện web (Tabler UI)
├── deploy/                      # Dockerfile, docker-compose.yml
├── evaluation/                  # pytest + benchmarks framework
├── requirements.txt             # Dependencies (production + test)
└── .env.example                 # Mẫu biến môi trường
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
| `LEAVE_DB_PATH` | `backend/data/leave_app.db` | Đường dẫn SQLite DB |
| `LEAVE_UPLOAD_DIR` | `backend/data/uploads` | Thư mục lưu ảnh chứng từ |

Xem chi tiết tại [.env.example](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/.env.example).
