"""
main.py
Điểm khởi chạy chính của Backend API (Người 3).
Ghép nối toàn bộ:
- Policy & Rule Engine (Kim)
- LLM Agent (Kiệt)
- SQLite Database & Audit Logs
- Cung cấp API cho Frontend (Kiệt/Người 4) và Ban Giám khảo (Verify Harness).

🔥 TÍNH NĂNG NÀY: WARM-UP VLM + LLM KHI STARTUP
→ Trước đây: Server start → weights lazy-load (chờ đơn đầu tiên 60+ giây)
→ Bây giờ:   Server start → TỰ ĐỘNG NẠP GPU ngay trong lúc lifespan startup
            (Async thread nền, không chặn API /docs /api chạy)
"""

import os
import sys
import time
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware

# Thêm đường dẫn module
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
for p in [current_dir, os.path.join(root_dir, "LLM-KIET"), os.path.join(root_dir, "Leave_Application")]:
    if p not in sys.path:
        sys.path.insert(0, p)


from database import init_db
from storage import AccessDenied, Conflict
from agent_orchestrator import ModelUnavailable
from routers.leave_router import router as leave_router
from routers.verify_router import router as verify_router
from routers.meta_router import router as meta_router
from ai_stack import (
    LLM_TARGET_MODEL,
    LLM_TIMEOUT_SEC,
    OLLAMA_BASE,
    OLLAMA_KEEP_ALIVE,
    VLM_TARGET_MODEL,
    VLM_TIMEOUT_SEC,
    has_model,
    ollama_chat,
    ollama_generate,
    ollama_ps,
    ollama_tags,
)

LLM_WARMUP_ON_STARTUP = str(os.getenv("LLM_WARMUP_ON_STARTUP", "1")).strip() not in {"0", "false", "no"}
VLM_WARMUP_ON_STARTUP = str(os.getenv("VLM_WARMUP_ON_STARTUP", "1")).strip() not in {"0", "false", "no"}


def _vram_of(target: str) -> int:
    for m in ollama_ps():
        if has_model([m.get("name") or ""], target):
            return int(m.get("size_vram") or 0)
    return 0


def _warmup_vlm() -> None:
    print(f"👁️ [VLM WARM-UP] Nạp {VLM_TARGET_MODEL} qua Ollama {OLLAMA_BASE} (keep_alive={OLLAMA_KEEP_ALIVE!r})...")
    reachable, names, err = ollama_tags()
    if not reachable:
        print(f"⚠️ [VLM WARM-UP] Ollama không chạy tại {OLLAMA_BASE}. {err or ''}".strip())
        return
    if not has_model(names, VLM_TARGET_MODEL):
        print(f"⚠️ [VLM WARM-UP] Chưa pull {VLM_TARGET_MODEL}. Chạy: ollama pull {VLM_TARGET_MODEL}")
        return
    vram_before = _vram_of(VLM_TARGET_MODEL)
    if vram_before > 0:
        print(f"✅ [VLM WARM-UP] {VLM_TARGET_MODEL} đã resident GPU ({vram_before / (1024**3):.1f} GB). Bỏ qua generate dummy.")
        return
    print("   → Gọi generate dummy (lần đầu load weights có thể 30–90s)...")
    png_1x1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    ollama_generate(
        {
            "model": VLM_TARGET_MODEL,
            "format": "json",
            "images": [png_1x1],
            "prompt": 'Trả JSON: {"ok": true, "proof_type": "NONE"}',
            "options": {"num_predict": 16, "temperature": 0.0},
        },
        timeout=VLM_TIMEOUT_SEC,
    )
    vram = _vram_of(VLM_TARGET_MODEL)
    if vram <= 0:
        print(f"⚠️ [VLM WARM-UP] {VLM_TARGET_MODEL} đã gọi được nhưng size_vram=0 (đang CPU). Inference chứng từ sẽ chậm / timeout.")
    else:
        print(f"✅ [VLM WARM-UP] {VLM_TARGET_MODEL} trên GPU ({vram / (1024**3):.1f} GB VRAM). Ảnh A4 ~8–18s.")


def _warmup_ai_stack_worker():
    """Nạp tuần tự VLM rồi LLM. Lỗi một con không chặn con kia."""
    if VLM_WARMUP_ON_STARTUP:
        try:
            _warmup_vlm()
        except Exception as e:
            print(f"⚠️ [VLM WARM-UP] {type(e).__name__}: {str(e)[:400]}")
    else:
        print("ℹ️ [VLM WARM-UP] Tắt (VLM_WARMUP_ON_STARTUP=0).")
    if LLM_WARMUP_ON_STARTUP:
        try:
            _warmup_llm()
        except Exception as e:
            print(f"⚠️ [LLM WARM-UP] {type(e).__name__}: {str(e)[:400]}")
    else:
        print("ℹ️ [LLM WARM-UP] Tắt (LLM_WARMUP_ON_STARTUP=0).")


def _warmup_llm() -> None:
    print(f"🧠 [LLM WARM-UP] Nạp {LLM_TARGET_MODEL} qua Ollama (keep_alive={OLLAMA_KEEP_ALIVE})...")
    reachable, names, err = ollama_tags()
    if not reachable:
        print(f"⚠️ [LLM WARM-UP] Ollama không chạy tại {OLLAMA_BASE}. {err or ''}".strip())
        return
    if not has_model(names, LLM_TARGET_MODEL):
        print(f"⚠️ [LLM WARM-UP] Chưa pull {LLM_TARGET_MODEL}. Chạy: ollama pull {LLM_TARGET_MODEL}")
        return
    from llm_client import get_qwen_engine
    engine = get_qwen_engine()
    with engine._lock:
        engine.is_loading = True
        engine.load_error = None
    try:
        ollama_chat(
            {
                "model": LLM_TARGET_MODEL,
                "format": "json",
                "messages": [{"role": "user", "content": 'Trả JSON: {"ok": true}'}],
                "options": {"num_predict": 16, "temperature": 0.0},
            },
            timeout=LLM_TIMEOUT_SEC,
        )
        with engine._lock:
            engine.is_ready = True
            engine.is_loading = False
        vram = _vram_of(LLM_TARGET_MODEL)
        where = f"GPU {vram / (1024**3):.1f} GB" if vram > 0 else "không thấy VRAM (kiểm tra /api/ps)"
        print(f"✅ [LLM WARM-UP] {LLM_TARGET_MODEL} sẵn sàng ({where}). JSON ~0.5–2s.")
    except Exception as e:
        with engine._lock:
            engine.is_loading = False
            engine.is_ready = False
            engine.load_error = str(e)
        raise


def _warmup_ai_stack_worker():
    """Nạp tuần tự VLM rồi LLM để cả hai keep_alive=-1 cùng resident."""
    try:
        if VLM_WARMUP_ON_STARTUP:
            _warmup_vlm()
        else:
            print("ℹ️ [VLM WARM-UP] Tắt (VLM_WARMUP_ON_STARTUP=0).")
        if LLM_WARMUP_ON_STARTUP:
            _warmup_llm()
        else:
            print("ℹ️ [LLM WARM-UP] Tắt (LLM_WARMUP_ON_STARTUP=0).")
    except Exception as e:
        print(f"⚠️ [AI STACK WARM-UP] {type(e).__name__}: {str(e)[:240]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ [BACKEND INIT] SQLite sẵn sàng.")
    print(f"🚀 [BACKEND INIT] AI stack: VLM={VLM_TARGET_MODEL} · LLM={LLM_TARGET_MODEL} (chỉ 2 model này).")
    threading.Thread(target=_warmup_ai_stack_worker, daemon=True).start()
    print("   💡 GET /api/meta/ai-stack-status")
    yield



app = FastAPI(
    title="Leave Application Coordination & Escalation API",
    description="Hệ thống điều phối phê duyệt nghỉ phép AI (The Escalation Referee) - MLAI Hackathon 2026",
    version="1.0.0",
    lifespan=lifespan
)

@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t_start = time.perf_counter()
    response = await call_next(request)
    total_api_ms = round((time.perf_counter() - t_start) * 1000, 2)
    response.headers["X-Total-Api-Ms"] = str(total_api_ms)
    return response

@app.exception_handler(AccessDenied)
async def access_error(request: Request, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})

@app.exception_handler(Conflict)
async def conflict_error(request: Request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

@app.exception_handler(ModelUnavailable)
async def model_error(request: Request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc), "error_code": "MODEL_UNAVAILABLE"})

@app.exception_handler(LookupError)
async def missing_error(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(ValueError)
async def input_error(request: Request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})

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
    assets_dir = os.path.join(frontend_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

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

