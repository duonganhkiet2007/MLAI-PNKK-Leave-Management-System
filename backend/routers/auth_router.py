"""Đăng nhập demo (token ký) và chứng từ mẫu sau xác thực."""
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from auth import issue_token, demo_login_enabled, TOKEN_TTL_SECONDS
from routers.leave_router import actor
import storage as st

router = APIRouter(tags=["Auth & Demo proofs"])

_ROOT = Path(__file__).resolve().parents[2]
_PROOF_DIRS = (_ROOT / "backend" / "uploads", _ROOT / "tests" / "assets" / "proofs", _ROOT / "frontend" / "assets" / "proofs")
_ALLOWED_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}


class DemoLoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: str


@router.post("/api/auth/demo-token")
def demo_token(payload: DemoLoginInput):
    """Cấp token cho nhân sự demo. Tắt bằng LEAVE_DEMO_LOGIN=0 khi triển khai thật."""
    if not demo_login_enabled():
        raise HTTPException(403, "Đăng nhập demo đã bị tắt.")
    with st.transaction() as conn:
        st.employee(conn, payload.actor_id)  # AccessDenied nếu không tồn tại / không active
    return {"success": True, "token": issue_token(payload.actor_id), "expires_in": TOKEN_TTL_SECONDS}


@router.get("/api/demo/proofs/{filename}")
def demo_proof(filename: str, actor_id=Depends(actor)):
    """Ảnh chứng từ mẫu của bộ test: chỉ trả cho người đã đăng nhập."""
    name = Path(filename).name
    suffix = Path(name).suffix.lower()
    if name != filename or suffix not in _ALLOWED_SUFFIX:
        raise HTTPException(404, "Không tìm thấy chứng từ mẫu.")
    for directory in _PROOF_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return FileResponse(candidate, media_type=_ALLOWED_SUFFIX[suffix],
                                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
    raise HTTPException(404, "Không tìm thấy chứng từ mẫu.")
