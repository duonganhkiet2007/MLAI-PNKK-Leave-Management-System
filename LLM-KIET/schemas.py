"""
schemas.py
Pydantic Schemas cho phần LLM (Người 2 - Kiệt).
Đảm bảo định dạng dữ liệu có cấu trúc (Structured Outputs), không bị vỡ JSON và tương thích hoàn toàn với Rule Engine của Kim.
"""

from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class LeaveTypeEnum(str, Enum):
    ANNUAL = "Annual"
    SICK = "Sick"
    UNPAID = "Unpaid"
    SPECIAL = "Special"


class AttachmentTypeEnum(str, Enum):
    NONE = "none"
    VALID_BHXH_CERT = "valid_bhxh_cert"
    VAGUE_PRESCRIPTION = "vague_prescription"
    INVALID = "invalid"


class ParsedLeaveRequest(BaseModel):
    """Kết quả trích xuất từ ngôn ngữ tự nhiên (Chat / Email của nhân viên)."""
    employee_id: Optional[str] = Field(None, description="Mã nhân viên nếu nhận diện được")
    employee_name: Optional[str] = Field(None, description="Tên nhân viên")
    department: Optional[str] = Field(None, description="Phòng ban của nhân sự")
    from_date: Optional[date] = Field(None, description="Ngày bắt đầu nghỉ (YYYY-MM-DD)")
    to_date: Optional[date] = Field(None, description="Ngày kết thúc nghỉ (YYYY-MM-DD)")
    leave_type: LeaveTypeEnum = Field(LeaveTypeEnum.ANNUAL, description="Loại nghỉ phép trích xuất")
    reason: Optional[str] = Field("Không rõ lý do", description="Lý do xin nghỉ phép")
    handover_person_name: Optional[str] = Field(None, description="Tên người nhận bàn giao (nếu có)")
    handover_person_id: Optional[str] = Field(None, description="Mã người nhận bàn giao (nếu có)")
    attachment_type: AttachmentTypeEnum = Field(AttachmentTypeEnum.NONE, description="Loại chứng từ đính kèm")

    # Trường kiểm soát bất định (Uncertainty Flag) - QUAN TRỌNG: KHÔNG ĐOÁN DỮ LIỆU
    is_ambiguous: bool = Field(False, description="True nếu thông tin mơ hồ, không đủ căn cứ xác định")
    ambiguity_reason: Optional[str] = Field(None, description="Lý do mơ hồ (ví dụ: không rõ ngày cụ thể, lý do không rõ)")
    missing_fields: List[str] = Field(default_factory=list, description="Danh sách các trường thông tin quan trọng bị thiếu")
    confidence_score: float = Field(1.0, description="Độ tin cậy của việc parse (0.0 - 1.0)")


class EscalationQuestionPayload(BaseModel):
    """
    Cấu trúc câu hỏi chuyển tiếp đạt chuẩn 6 điểm của BGK:
    - Cụ thể, đủ context để người xử lý quyết định ngay mà không cần tra hồ sơ gốc.
    - Kèm các lựa chọn hành động nhanh (Quick Action Options).
    - Kèm giải trình minh bạch (Audit explanation) cho con người.
    """
    decision: str = Field("ESCALATE", description="'AUTO_APPROVE' hoặc 'ESCALATE'")
    uncertainty_category: Optional[str] = Field(None, description="UNCERTAIN_FACTS | OUT_OF_POLICY | AUTHORITY_ESCALATION")
    error_code: Optional[str] = Field(None, description="Mã lỗi chuẩn từ taxonomy")
    target_role: Optional[str] = Field(None, description="Cấp thẩm quyền giải quyết (Manager, HRD, BOD, HR Ops)")
    actionable_question: Optional[str] = Field(None, description="Câu hỏi trực tiếp, rõ ràng cho người duyệt")
    quick_action_options: List[str] = Field(default_factory=list, description="Các phương án hành động gợi ý")
    human_readable_explanation: Optional[str] = Field("Hệ thống chuyển tiếp đơn để cấp thẩm quyền xem xét theo quy chế.", description="Giải thích lý do cho con người (Audit Trail)")
    applied_policy_clauses: List[str] = Field(default_factory=list, description="Các điều khoản quy chế được áp dụng")

    @field_validator("quick_action_options", mode="before")
    @classmethod
    def sanitize_quick_action_options(cls, v):
        if isinstance(v, list):
            clean = []
            for item in v:
                if isinstance(item, dict):
                    val = item.get("option") or item.get("text") or item.get("label") or item.get("title") or (list(item.values())[0] if item.values() else str(item))
                    clean.append(str(val))
                elif isinstance(item, str):
                    clean.append(item)
                else:
                    clean.append(str(item))
            return clean
        return v



class HumanFeedbackResolution(BaseModel):
    """Kết quả phân tích câu trả lời bằng ngôn ngữ tự nhiên của Quản lý/Human."""
    action: str = Field(..., description="APPROVE_OVERRIDE | REJECT | REQUEST_MORE_INFO | MODIFY_CONDITIONAL")
    is_approved: bool = Field(..., description="Quyết định cuối cùng có duyệt hay không")
    override_reason: Optional[str] = Field(None, description="Lý do đặc cách của người duyệt")
    updated_fields: Dict[str, Any] = Field(default_factory=dict, description="Các trường được cập nhật (VD: đổi người handover, đổi ngày)")
    feedback_notes: str = Field(..., description="Tóm tắt ý kiến chỉ đạo của Human")


class AgentPipelineResult(BaseModel):
    """Kết quả tổng thể của luồng xử lý Agent."""
    step: str = Field(..., description="Bước hiện tại trong quy trình")
    status: str = Field(..., description="COMPLETED | AWAITING_HUMAN | REJECTED")
    parsed_request: Optional[ParsedLeaveRequest] = None
    escalation_payload: Optional[EscalationQuestionPayload] = None
    final_decision: Optional[str] = None
    history_log: List[str] = Field(default_factory=list, description="Nhật ký các bước xử lý (Audit Log)")
