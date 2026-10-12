# Hướng dẫn Triển khai (Deployment Guide)

Thư mục này chứa toàn bộ cấu hình đóng gói và triển khai hệ thống bằng Docker.

## 1. Khởi chạy bằng Docker Compose

Từ thư mục gốc dự án, chạy:
```bash
docker compose -f deploy/docker-compose.yml up --build -d
```
Hoặc di chuyển vào thư mục `deploy/`:
```bash
cd deploy
docker compose up --build -d
```

## 2. Khởi chạy kèm Ollama Container
Nếu muốn chạy cả model Ollama trong container:
```bash
docker compose -f deploy/docker-compose.yml --profile ollama up -d
```

## 3. Kiểm tra trạng thái
- API Health Check: `curl http://localhost:8000/api/meta/health`
- Giao diện Web: Truy cập `http://localhost:8000` trên trình duyệt.
