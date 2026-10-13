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

# SQLite (WAL) không an toàn trên NFS → dữ liệu runtime mặc định nằm trên ổ cục bộ của máy chạy server.
# Ghi đè bằng LEAVE_DATA_DIR nếu cần. Lần đầu sẽ chép dữ liệu cũ từ backend/data sang.
LEGACY_DATA_DIR="$SCRIPT_DIR/data"
DATA_DIR="${LEAVE_DATA_DIR:-$HOME/.local/share/mlai-pnkk/data}"
mkdir -p "$DATA_DIR/uploads"
if [ "$DATA_DIR" != "$LEGACY_DATA_DIR" ] && [ ! -f "$DATA_DIR/leave_app.db" ] && [ -f "$LEGACY_DATA_DIR/leave_app.db" ]; then
    echo "📦 Chuyển dữ liệu từ $LEGACY_DATA_DIR sang ổ cục bộ $DATA_DIR ..."
    "$PYTHON_BIN" -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" \
        "$LEGACY_DATA_DIR/leave_app.db" "$DATA_DIR/leave_app.db"
    [ -d "$LEGACY_DATA_DIR/uploads" ] && cp -a "$LEGACY_DATA_DIR/uploads/." "$DATA_DIR/uploads/"
    [ -f "$LEGACY_DATA_DIR/.auth_secret" ] && cp -p "$LEGACY_DATA_DIR/.auth_secret" "$DATA_DIR/.auth_secret"
fi
export LEAVE_DATA_DIR="$DATA_DIR"
export LEAVE_DB_PATH="$DATA_DIR/leave_app.db"
export LEAVE_UPLOAD_DIR="$DATA_DIR/uploads"

# Tự động dọn thư mục uploads cũ nếu còn tồn tại
[ -d "$SCRIPT_DIR/uploads" ] && rm -rf "$SCRIPT_DIR/uploads"

echo "=========================================================="
echo "🚀 Khởi chạy Backend API Server tại http://0.0.0.0:$PORT"
echo "📚 Tài liệu Swagger UI: http://localhost:$PORT/docs"
echo "📝 Xem log realtime: tail -f $DATA_DIR/server.log hoặc tmux attach -t mlai"
echo "📁 Dữ liệu runtime lưu biệt lập tại: $DATA_DIR"
echo "=========================================================="

exec "$PYTHON_BIN" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload 2>&1 | tee -a "$DATA_DIR/server.log"

