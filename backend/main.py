"""
main.py
Điểm khởi chạy chính của Backend API (Người 3).
Ghép nối toàn bộ:
- Policy & Rule Engine (Kim)
- LLM Agent (Kiệt)
- SQLite Database & Audit Logs
- Cung cấp API cho Frontend (Kiệt/Người 4) và Ban Giám khảo (Verify Harness).
"""

import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Thêm đường dẫn module
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
for p in [current_dir, os.path.join(root_dir, "LLM-KIET"), os.path.join(root_dir, "Leave_Application")]:
    if p not in sys.path:
        sys.path.insert(0, p)


from database import init_db
from routers.leave_router import router as leave_router
from routers.verify_router import router as verify_router
from routers.meta_router import router as meta_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo Database và nạp dữ liệu nhân viên
    init_db()
    print("✅ [BACKEND INIT] Cơ sở dữ liệu SQLite đã sẵn sàng.")
    # Khởi động nạp model Qwen 2.5 7B trực tiếp trong RAM GPU (Port 8000 duy nhất)
    try:
        root_dir = os.path.dirname(current_dir)
        llm_dir = os.path.join(root_dir, "LLM-KIET")
        if llm_dir not in sys.path:
            sys.path.insert(0, llm_dir)
        from llm_client import get_qwen_engine
        get_qwen_engine().load_model()
    except Exception as e:
        print(f"⚠️ [STARTUP] Chưa nạp model: {e}")
    yield



app = FastAPI(
    title="Leave Application Coordination & Escalation API",
    description="Hệ thống điều phối phê duyệt nghỉ phép AI (The Escalation Referee) - MLAI Hackathon 2026",
    version="1.0.0",
    lifespan=lifespan
)

# Cấu hình CORS để Frontend (Vite/React/Next.js hoặc HTML thuần) gọi API không bị chặn
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các Router
app.include_router(leave_router)
app.include_router(verify_router)
app.include_router(meta_router)


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Đường dẫn tới thư mục frontend
frontend_dir = os.path.join(os.path.dirname(current_dir), "frontend")

if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/", summary="Giao diện Web SPA")
    async def serve_spa_index():
        return FileResponse(
            os.path.join(frontend_dir, "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

    @app.get("/styles.css", include_in_schema=False)
    async def serve_spa_css():
        return FileResponse(
            os.path.join(frontend_dir, "styles.css"),
            media_type="text/css",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

    @app.get("/app.js", include_in_schema=False)
    async def serve_spa_js():
        return FileResponse(
            os.path.join(frontend_dir, "app.js"),
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )


@app.get("/api", summary="Sitemap và trạng thái API")
def api_sitemap():
    return {
        "project": "The Escalation Referee (Track A) - MLAI Hackathon 2026",
        "role": "Người 3 & 4 - Backend & Frontend",
        "docs_url": "/docs",
        "frontend_url": "/",
        "status": "online",
        "endpoints": {
            "verify_harness": "POST /api/verify/escalation",
            "verify_custom": "POST /api/verify/custom",
            "submit_leave": "POST /api/leave/request",
            "list_leaves": "GET /api/leave/requests",
            "policy": "GET /api/meta/policy",
            "employees": "GET /api/meta/employees"
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Khởi chạy Backend API tại: http://0.0.0.0:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

