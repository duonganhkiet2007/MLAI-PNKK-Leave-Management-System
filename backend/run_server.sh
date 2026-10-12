#!/bin/bash
# run_server.sh: Chạy backend FastAPI server tại port 8000.
# Không cần gán tay PYTHONPATH: main.py / ai/__init__.py tự thêm đường dẫn module.
# Có thể chạy từ bất kỳ thư mục nào. Ghi đè interpreter bằng: PYTHON_BIN=/path/to/python

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$PYTHON_BIN" ]; then
    if [ -f "$SCRIPT_DIR/../.venv/bin/python" ]; then
        PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python"
    elif [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
        PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
    else
        PYTHON_BIN="python3"
    fi
fi
PORT="${PORT:-8000}"

DATA_DIR="$SCRIPT_DIR/data"
mkdir -p "$DATA_DIR/uploads"
export LEAVE_DATA_DIR="$DATA_DIR"
export LEAVE_DB_PATH="$DATA_DIR/leave_app.db"
export LEAVE_UPLOAD_DIR="$DATA_DIR/uploads"

# Tự động dọn thư mục uploads cũ nếu còn tồn tại
[ -d "$SCRIPT_DIR/uploads" ] && rm -rf "$SCRIPT_DIR/uploads"

echo "=========================================================="
echo "🚀 Khởi chạy Backend API Server tại http://0.0.0.0:$PORT"
echo "📚 Tài liệu Swagger UI: http://localhost:$PORT/docs"
echo "📝 Xem log realtime: tail -f data/server.log hoặc tmux attach -t mlai"
echo "📁 Dữ liệu runtime lưu biệt lập tại: $DATA_DIR"
echo "=========================================================="

exec "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload 2>&1 | tee -a "$DATA_DIR/server.log"

