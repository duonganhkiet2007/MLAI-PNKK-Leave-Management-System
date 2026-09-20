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
import json
import threading
import base64
import urllib.request as urlrequest
import urllib.error as urlerror
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

# ============================================================
# CÁC ENVIRONMENT VARIABLE ĐỂ TẮT / TWEAK WARM-UP
# (Mặc định BẬT HẾT, vì mày nói muốn khởi tạo weights luôn)
#   LLM_WARMUP_ON_STARTUP  = 0 (tắt warm-up LLM) / 1 (mặc định)
#   VLM_WARMUP_ON_STARTUP  = 0 (tắt warm-up VLM) / 1 (mặc định)
#   LLM_WARMUP_TIMEOUT_SEC = 300 (s, mặc định 5 ph, nếu lâu hơn thì bỏ qua, không block)
#   VLM_WARMUP_TIMEOUT_SEC = 180 (s, mặc định 3 phút)
#   VLM_OLLAMA_BASE        = http://localhost:11434 (mặc định)
#   VLM_TARGET_MODEL       = qwen2.5-vl:3b (mặc định)
# ============================================================
LLM_WARMUP_ON_STARTUP  = str(os.getenv("LLM_WARMUP_ON_STARTUP","1")).strip() not in {"0","false","no"}
VLM_WARMUP_ON_STARTUP  = str(os.getenv("VLM_WARMUP_ON_STARTUP","1")).strip() not in {"0","false","no"}
LLM_WARMUP_TIMEOUT_SEC = int(os.getenv("LLM_WARMUP_TIMEOUT_SEC","300"))
VLM_WARMUP_TIMEOUT_SEC = int(os.getenv("VLM_WARMUP_TIMEOUT_SEC","180"))
VLM_OLLAMA_BASE        = str(os.getenv("VLM_OLLAMA_BASE","http://localhost:11434")).rstrip("/")
VLM_TARGET_MODEL       = str(os.getenv("VLM_TARGET_MODEL","qwen2.5-vl:3b"))


# ============================================================
# WARM-UP 1: LLM QWEN 2.5 7B IN-PROCESS GPU
# Chạy trong thread nền, không block lifespan / app startup
# ============================================================
def _warmup_llm_worker():
    try:
        from llm_client import LLMClient
        from schemas import ManagerSummaryLLMResponse
        print("🧠 [LLM WARM-UP] Bắt đầu nạp weights Qwen 2.5 7B vào GPU (có thể mất 30-90 giây — vui lòng chờ)...")
        _client = LLMClient()
        # Trigger 1 lần generate_json với context dummy siêu ngắn để nạp model thật + 1 pass KV-cache warm
        _dummy = {
            "context_employee": {"employee_name": "WARMUP TEST", "employee_id": "WARMUP", "department": "WARMUP"},
            "leave_request": {
                "leave_type_enum":"ANNUAL","leave_type_vi":"Nghỉ phép năm",
                "from_date":"2026-01-01","to_date":"2026-01-01",
                "requested_calendar_days":1,"requested_working_days":1,"reason":"Warm-up startup"
            },
            "vlm_analysis": {"ran_vlm": False},
            "rule_engine_result": {
                "decision":"AUTO_APPROVE","status":"COMPLETED","error_code":"OK",
                "target_role":"NONE","human_readable_explanation":"Warm-up test startup.",
                "quick_action_options_enum":[],"applied_policy_clauses_enum":[],
                "warnings_enum":[],"why_escalated_template":"","actionable_question_template":"Warmup?",
                "summary_template_text":"Warm-up summary."
            }
        }
        try:
            _client.generate_json(
                system_prompt="Bạn là HR assistant. Trả JSON ngắn gọn.",
                user_prompt="Warm-up only. Trả về 1 JSON object rỗng hoặc theo schema:\n" + json.dumps(_dummy, ensure_ascii=False),
                response_model=ManagerSummaryLLMResponse,
            )
        except Exception:
            # Dù generate lỗi cũng OK — mục tiêu chính là load model weights vào GPU
            pass
        print(f"✅ [LLM WARM-UP] Hoàn tất nạp weights Qwen 2.5 7B. LLM SẴN SÀNG inference ngay (request đầu tiên ~2-6 giây).")
    except Exception as e:
        print(f"⚠️ [LLM WARM-UP] Không nạp được LLM lúc startup (sẽ lazy-load khi có request đầu tiên): {type(e).__name__}: {str(e)[:200]}")


# ============================================================
# WARM-UP 2: VLM qwen2.5-vl:3b (Ollama)
# Gọi /api/generate 1 lần với ảnh dummy 1x1 pixel base64 →
# Ollama sẽ nạp weights vision encoder + LLM decoder vào GPU ngay
# ============================================================
def _warmup_vlm_worker():
    try:
        print(f"👁️ [VLM WARM-UP] Kiểm tra Ollama {VLM_OLLAMA_BASE} + nạp weights model {VLM_TARGET_MODEL} (có thể mất 10-30 giây)...")
        # 2a. Kiểm tra Ollama có chạy không
        try:
            with urlrequest.urlopen(f"{VLM_OLLAMA_BASE}/api/tags", timeout=3.0) as r:
                tags = json.loads(r.read().decode() or "{}")
        except (urlerror.URLError, ConnectionError, OSError) as e:
            print(f"⚠️ [VLM WARM-UP] Ollama chưa chạy tại {VLM_OLLAMA_BASE}. Lỗi: {type(e).__name__} → bỏ qua warm-up VLM (sẽ tự động thử lại khi có đơn đầu tiên).")
            return
        # 2b. Kiểm tra model đã pull chưa
        has_model = False
        try:
            with urlrequest.urlopen(f"{VLM_OLLAMA_BASE}/api/tags", timeout=3.0) as r:
                tags = json.loads(r.read().decode() or "{}")
            existing_names = [m.get("name","") for m in tags.get("models",[])]
            has_model = any(
                n == VLM_TARGET_MODEL or n.startswith(VLM_TARGET_MODEL.split(":")[0])
                for n in existing_names
            )
        except Exception:
            has_model = False
        if not has_model:
            print(f"⚠️ [VLM WARM-UP] Model '{VLM_TARGET_MODEL}' chưa được pull trong Ollama.\n"
                  f"   → Model hiện có: {existing_names or '[]'}\n"
                  f"   → Hãy chạy CMD:  ollama pull {VLM_TARGET_MODEL}\n"
                  f"   → Bỏ qua warm-up (sẽ lỗi hoặc fallback khi có đơn đầu tiên nếu model không có).")
            return
        # 2c. Ảnh dummy 1x1 pixel PNG base64 (đen, 67 bytes)
        _PNG_1x1_BASE64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        # 2d. Gọi 1 lần Ollama /api/generate với prompt ngắn → nạp weights thật
        payload = {
            "model": VLM_TARGET_MODEL,
            "stream": False,
            "format": "json",
            "images": [_PNG_1x1_BASE64],
            "prompt": (
                "Bạn đang kiểm tra warm-up. Trả về 1 object JSON duy nhất với 2 keys:\n"
                "   ok: boolean true\n"
                "   proof_type: string \"NONE\"\n"
                "Không được trả về text khác ngoài JSON."
            ),
            "options": {"num_predict": 16, "temperature": 0.0},
        }
        try:
            req = urlrequest.Request(
                f"{VLM_OLLAMA_BASE}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urlrequest.urlopen(req, timeout=VLM_WARMUP_TIMEOUT_SEC) as r:
                out = json.loads(r.read().decode() or "{}")
            # Chỉ cần gọi thành công → weights đã nạp
            print(f"✅ [VLM WARM-UP] Hoàn tất nạp weights {VLM_TARGET_MODEL} vào GPU qua Ollama. VLM SẴN SÀNG đọc chứng từ (inference ảnh A4 scan ~3-12 giây).")
        except Exception as e:
            print(f"⚠️ [VLM WARM-UP] Gọi warm-up Ollama không thành công (vẫn sẽ thử lại khi có đơn thật): {type(e).__name__}: {str(e)[:200]}")
    except Exception as e:
        print(f"⚠️ [VLM WARM-UP] Lỗi tổng thể worker: {type(e).__name__}: {str(e)[:200]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Khởi tạo Database + migration auto-alter columns 27 cột VLM + LLM
    init_db()
    print("✅ [BACKEND INIT] Cơ sở dữ liệu SQLite đã sẵn sàng (auto-migration 27 cột VLM + LLM đã chạy).")

    # 2. Bắt đầu thread warm-up LLM (background, KHÔNG block yield / app startup)
    warmup_threads = []
    if LLM_WARMUP_ON_STARTUP:
        _t = threading.Thread(target=_warmup_llm_worker, daemon=True)
        _t.start()
        warmup_threads.append(("LLM Qwen 2.5 7B GPU", _t))
    else:
        print("ℹ️ [LLM WARM-UP] Bị tắt bởi env LLM_WARMUP_ON_STARTUP=0 → sẽ lazy-load khi có request đầu tiên.")

    # 3. Bắt đầu thread warm-up VLM (background)
    if VLM_WARMUP_ON_STARTUP:
        _t2 = threading.Thread(target=_warmup_vlm_worker, daemon=True)
        _t2.start()
        warmup_threads.append((f"VLM {VLM_TARGET_MODEL} Ollama", _t2))
    else:
        print("ℹ️ [VLM WARM-UP] Bị tắt bởi env VLM_WARMUP_ON_STARTUP=0 → sẽ lazy-load khi có đơn đầu tiên.")

    if warmup_threads:
        print(f"🚀 [BACKEND INIT] Đã khởi chạy {len(warmup_threads)} thread warm-up nền: "
              + ", ".join(name for (name, _) in warmup_threads))
        print(f"   💡 Server trả lời API (/docs, /api) NGAY BÌNH THƯỜNG trong khi 2 con model đang nạp GPU nền.")
        print(f"   💡 Kiểm tra tiến độ:  GET /api/meta/llm-status   → online=true là xong LLM.")
        print(f"   💡 Kiểm tra tiến độ:  GET /api/meta/vlm-status   → mode=READY là xong VLM.")

    yield



app = FastAPI(
    title="Leave Application Coordination & Escalation API",
    description="Hệ thống điều phối phê duyệt nghỉ phép AI (The Escalation Referee) - MLAI Hackathon 2026",
    version="1.0.0",
    lifespan=lifespan
)

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

