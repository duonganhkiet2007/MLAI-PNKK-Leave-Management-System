"""
leave_router.py
Router quản lý các yêu cầu xử lý đơn nghỉ phép cho nhân viên và quản lý.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from services.orchestration import LeaveOrchestratorService
from database import (
    get_all_leave_requests,
    get_leave_request,
    get_audit_logs
)

router = APIRouter(prefix="/api/leave", tags=["Leave Application"])
service = LeaveOrchestratorService()


class NewLeaveRequestInput(BaseModel):
    """Đầu vào khi gửi đơn nghỉ phép."""
    raw_text: Optional[str] = Field(None, description="Tin nhắn chat tự do của nhân viên (nếu dùng NLP)")
    employee_id: Optional[str] = Field(None, description="Mã nhân viên (nếu đã đăng nhập)")
    from_date: Optional[str] = Field(None, description="Ngày bắt đầu (YYYY-MM-DD)")
    to_date: Optional[str] = Field(None, description="Ngày kết thúc (YYYY-MM-DD)")
    leave_type: Optional[str] = Field("Annual", description="Loại nghỉ: Annual, Sick, Unpaid, Special")
    reason: Optional[str] = Field(None, description="Lý do xin nghỉ")
    handover_person_id: Optional[str] = Field(None, description="Mã nhân sự nhận bàn giao")
    attachment_type: Optional[str] = Field("none", description="none, valid_bhxh_cert, vague_prescription, invalid")


class HumanDecisionInput(BaseModel):
    """Đầu vào khi Quản lý/HRD phản hồi đơn bị chuyển tiếp."""
    feedback_text: str = Field(..., description="Ý kiến chỉ đạo/câu trả lời bằng ngôn ngữ tự nhiên của Quản lý")
    approver_id: Optional[str] = Field("MGR001", description="Mã người duyệt")


@router.post("/request", summary="Gửi đơn nghỉ phép mới (Text tự do hoặc Form chuẩn)")
def submit_leave_request(payload: NewLeaveRequestInput):
    try:
        structured = {
            "employee_id": payload.employee_id,
            "from_date": payload.from_date,
            "to_date": payload.to_date,
            "leave_type": payload.leave_type,
            "reason": payload.reason,
            "handover_person_id": payload.handover_person_id,
            "attachment_type": payload.attachment_type or "none"
        }
        res = service.process_new_request(
            raw_text=payload.raw_text,
            employee_id=payload.employee_id,
            structured_data=structured
        )
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requests", summary="Lấy danh sách tất cả các đơn nghỉ phép")
def list_leave_requests(status: Optional[str] = Query(None, description="Filter theo trạng thái: ALL, COMPLETED, PENDING_ESCALATION, REJECTED")):
    try:
        requests = get_all_leave_requests(status_filter=status)
        return {"success": True, "total": len(requests), "data": requests}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{request_id}", summary="Xem chi tiết 1 đơn nghỉ phép và câu hỏi hành động")
def get_single_request(request_id: str):
    req = get_leave_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đơn {request_id}")
    audit_logs = get_audit_logs(request_id)
    return {"success": True, "data": req, "audit_trail": audit_logs}


@router.post("/{request_id}/human-decision", summary="Quản lý gửi phản hồi cho đơn đang bị chuyển tiếp (Human-in-the-loop)")
def submit_human_decision(request_id: str, payload: HumanDecisionInput):
    try:
        updated_req = service.process_human_decision(
            request_id=request_id,
            feedback_text=payload.feedback_text,
            approver_id=payload.approver_id
        )
        return {"success": True, "data": updated_req}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{request_id}/cancel", summary="Nhân viên tự hủy/thu hồi đơn đang chờ")
def cancel_single_request(request_id: str):
    from database import cancel_leave_request
    success = cancel_leave_request(request_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hoặc không thể hủy")
    return {"success": True, "message": "Đã hủy đơn thành công"}


class RevokeDecisionInput(BaseModel):
    reason: Optional[str] = Field("Quản lý hủy quyết định tự duyệt của AI", description="Lý do hủy quyết định")


@router.post("/{request_id}/revoke", summary="Quản lý hủy quyết định tự duyệt của AI (Override)")
def revoke_single_approval(request_id: str, payload: Optional[RevokeDecisionInput] = None):
    from database import override_revoke_auto_approval
    reason = payload.reason if payload else "Quản lý hủy quyết định tự duyệt của AI"
    success = override_revoke_auto_approval(request_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hoặc không thể hủy quyết định")
    return {"success": True, "message": "Đã hủy quyết định duyệt của AI thành công"}

