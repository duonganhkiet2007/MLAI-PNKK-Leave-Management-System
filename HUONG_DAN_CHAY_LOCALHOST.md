# 🚀 Hướng Dẫn Chạy Localhost — Hệ Thống Phê Duyệt Nghỉ Phép AI (Team PNKK)

Tài liệu này hướng dẫn chi tiết các bước để khởi chạy và sử dụng hệ thống tại môi trường local.

---

## 📌 Tổng Quan Kiến Trúc

Hệ thống bao gồm:
1. **Backend API (FastAPI + SQLite + Rule Engine + LLM Qwen 2.5)**: Cung cấp API xử lý đơn nghỉ phép, tự động duyệt hoặc chuyển tiếp (escalate), phục vụ Swagger UI và tích hợp sẵn Frontend SPA.
2. **Frontend UI (HTML5 / Vanilla CSS / Vanilla JS)**: Giao diện trực quan gồm Bộ kiểm thử tự động (Harness 90s), Nộp đơn nghỉ phép, Hộp thư chuyển tiếp (Escalation Inbox), và Bảng tra cứu quy chế.

---

## 🛠️ Yêu Cầu Môi Trường
- **Python**: Phiên bản 3.10+ (hoặc môi trường conda `qwen_vl`).
- **Dependencies**: `fastapi`, `uvicorn`, `pydantic`, `torch`, `transformers`, `accelerate` (nếu chạy GPU LLM trực tiếp).
- **Trình duyệt**: Chrome, Firefox, Edge, Safari hoặc bất kỳ trình duyệt hiện đại nào.
- **Tmux**: (Tùy chọn) Dùng để duy trì server chạy ngầm không bị tắt khi đóng terminal/SSH.

---

## 🚀 Cách 1: Chạy Tất Cả Trong 1 Lệnh (Khuyên Dùng ⭐)

FastAPI đã được tích hợp sẵn static file server để phục vụ trực tiếp giao diện Frontend.

### Bước 1: Mở Terminal và chuyển vào thư mục backend
```bash
cd /workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/backend
```

### Bước 2: Kích hoạt môi trường và khởi chạy Server
- **Cách nhanh nhất bằng script:**
  ```bash
  bash run_server.sh
  ```
- **Hoặc chạy trực tiếp qua lệnh Python/Uvicorn:**
  ```bash
  # Kích hoạt môi trường conda (nếu dùng conda)
  conda activate qwen_vl

  # Chạy Uvicorn server tại port 8000
  python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
  ```

### Bước 3: Truy cập hệ thống trên Trình duyệt
- **Giao diện Web Frontend (SPA):** 👉 [http://localhost:8000](http://localhost:8000)
- **Tài liệu API (Swagger UI):** 👉 [http://localhost:8000/docs](http://localhost:8000/docs)
- **Tài liệu API dự phòng (ReDoc):** 👉 [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🖥️ Cách 2: Chạy Ngầm Bằng TMUX (Tiện Lợi Khi Làm Việc Từ Xa / SSH)

Sử dụng `tmux` giúp server chạy liên tục trong nền, không bị tắt khi bạn đóng terminal hay ngắt kết nối SSH.

### 1. Tạo session mới và khởi chạy Server
```bash
# Tạo một session tmux tên là 'mlai' và nhảy vào session đó
tmux new -s mlai

# Trong cửa sổ tmux, chuyển thư mục và chạy server
cd /workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/backend
bash run_server.sh
```

### 2. Thoát ra ngoài mà vẫn giữ Server chạy (Detach)
- Nhấn tổ hợp phím: `Ctrl + B`, sau đó thả tay ra và nhấn phím `D`.
- Lúc này server vẫn đang chạy ngầm trong background.

### 3. Quay lại kiểm tra log server (Attach)
```bash
tmux attach -t mlai
```

### 4. Các lệnh Tmux hữu ích khác:
- **Xem danh sách các session đang chạy:**
  ```bash
  tmux ls
  ```
- **Tắt hoàn toàn session và dừng server:**
  ```bash
  tmux kill-session -t mlai
  ```
- **Chia đôi màn hình (Split pane) trong tmux:**
  - Chia ngang (trên/dưới): `Ctrl + B` rồi nhấn `"`
  - Chia dọc (trái/phải): `Ctrl + B` rồi nhấn `%`
  - Chuyển đổi giữa các ô: `Ctrl + B` rồi dùng các phím mũi tên `← ↑ → ↓`

---

## 🌐 Cách 3: Chạy Backend và Frontend Độc Lập (Tách Port)

Nếu bạn muốn chỉnh sửa frontend mà không cần reload backend hoặc muốn chạy server tĩnh riêng:

### 1. Chạy Backend (Port 8000)
```bash
cd /workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/backend
bash run_server.sh
```

### 2. Mở một Terminal khác để chạy Frontend (Port 3000)
```bash
cd /workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/frontend

# Dùng Python HTTP Server
python3 -m http.server 3000

# Hoặc dùng Node.js npx serve / live-server (nếu có Node)
# npx serve -p 3000 .
```

👉 Truy cập Frontend tại: [http://localhost:3000](http://localhost:3000)  
*(Lưu ý: `frontend/app.js` đã hỗ trợ CORS kết nối tới backend tại `http://localhost:8000`)*

---

## 🧪 Kiểm Thử Hệ Thống (Verify & Test)

### 1. Kiểm thử từ Giao diện Web (Harness 90 giây)
1. Truy cập [http://localhost:8000](http://localhost:8000).
2. Vào tab **"Kiểm thử tự động"** (Auto Verification).
3. Bấm nút **"CHẠY BỘ KIỂM THỬ HARNESS (5 KỊCH BẢN)"**.
4. Quan sát kết quả so sánh quyết định thực tế của AI và kết quả kỳ vọng.

### 2. Kiểm thử tự động bằng CLI / Script E2E
```bash
cd /workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/backend
python test_api_e2e.py
```

---

## ⚙️ Các Cổng & Cấu Hình Quan Trọng

| Thành Phần | Cổng Mặc Định | URL Truy Cập | Ghi Chú |
| :--- | :--- | :--- | :--- |
| **Full Web App (Front + Back)** | `8000` | `http://localhost:8000` | Phục vụ cả UI và API |
| **API Docs (Swagger)** | `8000` | `http://localhost:8000/docs` | Test endpoint trực tiếp |
| **Standalone Frontend** | `3000` *(tùy chọn)* | `http://localhost:3000` | Khi chạy riêng qua `python -m http.server` |
| **Database SQLite** | File nội bộ | `backend/leave_app.db` | Tự động tạo khi chạy server |

---

## ❓ Xử Lý Sự Cố Thường Gặp

1. **Lỗi `Address already in use` (Port 8000 bị chiếm):**
   ```bash
   # Tìm và tắt tiến trình đang chiếm port 8000
   lsof -i :8000
   # hoặc
   kill -9 $(lsof -t -i:8000)
   ```

2. **Lỗi không tìm thấy module LLM / Policy:**
   - Đảm bảo bạn chạy server từ thư mục gốc `MLAI` hoặc chạy qua file `backend/run_server.sh` (file này đã tự cấu hình đường dẫn `sys.path`).
