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
    """Schema cho LLM (qwen2.5:3b-instruct) tổng hợp đơn nghỉ và chứng từ cho Manager."""
    summary_natural_vn: str = Field(default='', description="Đoạn văn ngắn gọn 3-5 câu tổng hợp các thông tin cốt lõi nhất.")
    info_sufficient_vn: list[str] = Field(default_factory=list, description="Danh sách các thông tin ĐÃ ĐẦY ĐỦ / HỢP LỆ.")
    info_missing_vn: list[str] = Field(default_factory=list, description="Danh sách các thông tin CÒN THIẾU / BẤT THƯỜNG / CẦN LÀM RÕ.")
    why_escalated: str = Field(default='', description="Lý do ngắn gọn 1 câu tại sao cần Manager xem xét.")
    actionable_question: str = Field(default='', description="Câu hỏi hành động rõ ràng cho Manager quyết định, kết thúc bằng dấu chấm hỏi (?).")
    error_code_human_vn: str = Field(default='—', description="Giải thích lỗi tiếng Việt.")
    target_role_human_vn: str = Field(default='—', description="Vai trò người duyệt.")
    quick_action_options_vn: list[str] = Field(default_factory=list, description="Các lựa chọn thao tác nhanh (ví dụ: Duyệt đặc cách, Yêu cầu nộp lại, Từ chối).")
    applied_policy_clauses_vn: list[str] = Field(default_factory=list, description="Điều khoản chính sách áp dụng.")
    warnings: list[str] = Field(default_factory=list, description="Cảnh báo quan trọng nếu có.")
    correlation_tier_vn: str = Field(default='—', description="Độ khớp: RẤT KHỚP / KHỚP / CHƯA KHỚP / KHÔNG KHỚP.")
    integrity_assessment_vn: str = Field(default='—', description="Đánh giá tính toàn vẹn chứng từ.")
    leave_type_vn: str = Field(default='', description="Tên loại nghỉ.")
    staff_errors_vn: list[str] = Field(default_factory=list, description="Chỉ các lỗi nhân viên cần sửa hoặc bổ sung; không viết nhận định nghi vấn.")
    staff_next_steps_vn: list[str] = Field(default_factory=list, description="Việc nhân viên cần làm tiếp theo.")
    manager_suspicions_vn: list[str] = Field(default_factory=list, description="Chỉ các điểm nghi vấn/rủi ro Manager cần xác minh.")
    manager_risk_level_vn: str = Field(default='—', description="Mức rủi ro hoặc nghi vấn dành cho Manager.")
    manager_recommendation_vn: str = Field(default='', description="Khuyến nghị ngắn cho Manager.")
