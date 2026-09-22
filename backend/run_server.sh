#!/bin/bash
# run_server.sh: Chạy backend FastAPI server tại port 8000

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="/home/phongnh/miniconda3/envs/qwen_vl/bin/python"
PORT=8000

echo "=========================================================="
echo "🚀 Khởi chạy Backend API Server tại http://0.0.0.0:$PORT"
echo "📚 Tài liệu Swagger UI: http://localhost:$PORT/docs"
echo "📝 Xem log realtime: tail -f server.log hoặc tmux attach -t mlai"
echo "=========================================================="

exec $PYTHON_BIN -m uvicorn main:app --host 0.0.0.0 --port $PORT --reload 2>&1 | tee -a server.log

