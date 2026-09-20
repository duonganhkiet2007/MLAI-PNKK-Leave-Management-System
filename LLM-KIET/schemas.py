"""Model output contains request facts or a whitelisted human action only."""
from pydantic import BaseModel, Field
from domain import RequestFacts, HumanFeedbackResolution, LeaveType as LeaveTypeEnum, ProofExtraction
from taxonomy import ApprovalResult
from typing import Any

class ParsedLeaveRequest(RequestFacts):
    pass

class EscalationQuestionPayload(BaseModel):
    decision: str
    uncertainty_category: str | None = None
    error_code: str | None = None
    target_role: str | None = None
    actionable_question: str | None = None
    quick_action_options: list[str] = Field(default_factory=list)
    human_readable_explanation: str = ''
    applied_policy_clauses: list[str] = Field(default_factory=list)

class AgentPipelineResult(BaseModel):
    step: str
    status: str
    parsed_request: ParsedLeaveRequest | None = None
    escalation_payload: EscalationQuestionPayload | None = None
    final_decision: str | None = None
    engine_result: ApprovalResult | None = None
    history_log: list[str] = Field(default_factory=list)

class ManagerSummaryLLMResponse(BaseModel):
    """Schema cho LLM (Qwen 2.5 7B) tổng hợp đơn nghỉ cho Manager xem."""
    summary_natural_vn: str = Field(..., min_length=30, description="Đoạn văn 5-10 câu tiếng Việt tự nhiên, tổng hợp mọi thông tin quan trọng cho người phê duyệt.")
    why_escalated: str = Field(..., description="1-2 câu tiếng Việt giải thích lý do đơn không tự động duyệt (nếu decision != AUTO_APPROVE).")
    actionable_question: str = Field(..., description="Câu hỏi định lựa chọn cho người duyệt, kết thúc bằng dấu chấm hỏi.")
    error_code_human_vn: str = Field(..., description="Dịch error_code gốc sang giải thích tiếng Việt dễ hiểu, hoặc '—' nếu không có lỗi.")
    target_role_human_vn: str = Field(..., description="Tên vai trò tiếng Việt của người duyệt tiếp theo (vd Quản lý trực tiếp), hoặc '—' nếu tự duyệt.")
    quick_action_options_vn: list[str] = Field(default_factory=list, description="Các nút thao tác nhanh dịch sang tiếng Việt có icon.")
    applied_policy_clauses_vn: list[str] = Field(default_factory=list, description="Các điều khoản chính sách áp dụng, mô tả tiếng Việt.")
    warnings: list[str] = Field(default_factory=list, description="Các cảnh báo tiếng Việt (nếu có).")
    correlation_tier_vn: str = Field('—', description="Mức độ khớp: RẤT KHỚP / KHỚP / CHƯA KHỚP / KHÔNG KHỚP / —.")
    integrity_assessment_vn: str = Field('—', description="Đánh giá 1 câu tiếng Việt về tính toàn vẹn chứng từ (dấu đỏ, chữ ký, giả mạo).")
    leave_type_vn: str = Field(..., description="Tên loại nghỉ tiếng Việt đầy đủ (ví dụ Nghỉ phép năm, Nghỉ ốm đau...).")
