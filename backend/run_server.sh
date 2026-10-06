#!/bin/bash
# run_server.sh: Chạy backend FastAPI server tại port 8000.
# Không cần gán tay PYTHONPATH: main.py / ai/__init__.py tự thêm đường dẫn module.
# Có thể chạy từ bất kỳ thư mục nào. Ghi đè interpreter bằng: PYTHON_BIN=/path/to/python

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8000}"

echo "=========================================================="
echo "🚀 Khởi chạy Backend API Server tại http://0.0.0.0:$PORT"
echo "📚 Tài liệu Swagger UI: http://localhost:$PORT/docs"
echo "📝 Xem log realtime: tail -f server.log hoặc tmux attach -t mlai"
echo "=========================================================="

exec "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload 2>&1 | tee -a server.log
