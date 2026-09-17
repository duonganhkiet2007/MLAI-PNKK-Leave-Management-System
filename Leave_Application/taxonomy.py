"""
Định nghĩa cấu trúc phân tầng Escalation Taxonomy cho Hệ thống Phê duyệt Nghỉ phép (Track A).
Tuân thủ 3 nhóm không chắc chắn bắt buộc:
1. UNCERTAIN_FACTS: Dữ liệu bị thiếu, sai định dạng, mâu thuẫn hoặc không thể xác minh.
2. OUT_OF_POLICY: Thông tin rõ ràng nhưng vi phạm quy chế (cần xem xét đặc cách).
3. AUTHORITY_ESCALATION: Hồ sơ hợp lệ nhưng vượt thẩm quyền tự duyệt của hệ thống.
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    """Quyết định tổng thể của hệ thống."""
    AUTO_APPROVE = "AUTO_APPROVE"
    ESCALATE = "ESCALATE"
    # Lưu ý: Theo tiêu chí đề bài, dữ liệu nghi vấn không được tự ý phán quyết,
    # mà bắt buộc phải chuyển tiếp (ESCALATE) kèm câu hỏi hành động.


class UncertaintyCategory(str, Enum):
    """3 nhóm mức độ không chắc chắn bắt buộc theo yêu cầu đề bài."""
    UNCERTAIN_FACTS = "UNCERTAIN_FACTS"
    OUT_OF_POLICY = "OUT_OF_POLICY"
    AUTHORITY_ESCALATION = "AUTHORITY_ESCALATION"


class TargetApproverRole(str, Enum):
    """Cấp thẩm quyền được định tuyến để xử lý câu hỏi chuyển tiếp."""
    DIRECT_MANAGER = "Trưởng bộ phận (Manager)"
    HR_DIRECTOR = "Giám đốc Nhân sự (HRD)"
    EXECUTIVE_BOARD = "Ban Giám đốc (BOD)"
    HR_OPERATIONS = "Chuyên viên Nhân sự (C&B/HR Ops)"


class ErrorCode(str, Enum):
    """Mã lỗi định danh duy nhất cho từng tình huống cụ thể."""
    
    # --- NHÓM 1: UNCERTAIN_FACTS ---
    DOC_ILLEGIBLE = "DOC_ILLEGIBLE"
    # Giấy khám/ra viện/thiệp cưới bị mờ, mất góc, không nhận diện được ngày hoặc mộc đỏ
    
    DOC_SUSPICIOUS = "DOC_SUSPICIOUS"
    # Chứng từ có dấu hiệu chỉnh sửa hình ảnh hoặc trùng lặp mã hồ sơ bệnh án cũ
    
    DATE_LOGIC_INVALID = "DATE_LOGIC_INVALID"
    # Ngày kết thúc trước ngày bắt đầu hoặc số ngày nghỉ tính ra <= 0
    
    HANDOVER_INVALID = "HANDOVER_INVALID"
    # Người nhận bàn giao không tồn tại, đã thôi việc, hoặc trùng chính người làm đơn
    
    HANDOVER_CIRCULAR_LOOP = "HANDOVER_CIRCULAR_LOOP"
    # Bàn giao chéo vòng tròn (A bàn giao cho B, B lại bàn giao ngược lại cho A khi cùng nghỉ)
    
    MEDICAL_DAYS_MISMATCH = "MEDICAL_DAYS_MISMATCH"
    # Số ngày xin nghỉ ốm vượt quá số ngày bác sĩ ghi trên Giấy chứng nhận nghỉ BHXH


    # --- NHÓM 2: OUT_OF_POLICY ---
    NOTICE_PERIOD_VIOLATED = "NOTICE_PERIOD_VIOLATED"
    # Nộp đơn muộn hơn thời hạn quy định (ví dụ: nghỉ 1 ngày nhưng nộp trước 2 giờ)
    
    BALANCE_EXCEEDED = "BALANCE_EXCEEDED"
    # Số ngày xin nghỉ phép năm vượt quá số dư phép hiện có
    
    TEAM_QUOTA_EXCEEDED = "TEAM_QUOTA_EXCEEDED"
    # Tỷ lệ nhân sự nghỉ phép trong phòng ban cùng ngày vượt ngưỡng 30%
    
    UNQUALIFIED_SPECIAL_LEAVE = "UNQUALIFIED_SPECIAL_LEAVE"
    # Xin nghỉ việc riêng hưởng nguyên lương cho các lý do không thuộc Điều 115 BLLĐ
    
    CONSECUTIVE_SPLIT_DETECTED = "CONSECUTIVE_SPLIT_DETECTED"
    # Tình huống lách luật: Chia nhỏ đơn liên tiếp (Salami slicing) để né trần tự duyệt 2 ngày
    
    CLUSTER_ABSENCE_ANOMALY = "CLUSTER_ABSENCE_ANOMALY"
    # Bất thường tập thể: Gần như toàn bộ nhân sự 1 team cùng nộp đơn nghỉ sát giờ


    # --- NHÓM 3: AUTHORITY_ESCALATION ---
    DURATION_OVER_AI_LIMIT = "DURATION_OVER_AI_LIMIT"
    # Đơn hợp lệ nhưng kéo dài 3 - 5 ngày làm việc (vượt quyền tự duyệt của AI -> Manager)
    
    DURATION_OVER_MANAGER_LIMIT = "DURATION_OVER_MANAGER_LIMIT"
    # Đơn hợp lệ nhưng kéo dài > 5 ngày làm việc (vượt quyền Manager -> HRD/Director)
    
    LONG_TERM_UNPAID = "LONG_TERM_UNPAID"
    # Đơn xin nghỉ việc riêng không hưởng lương dài hạn (> 14 ngày làm việc)
    
    MANAGER_SELF_APPROVAL = "MANAGER_SELF_APPROVAL"
    # Người nộp đơn chính là Trưởng bộ phận (cần định tuyến lên Giám đốc khối)


# Metadata ánh xạ chi tiết từng ErrorCode sang Category và Người duyệt mặc định
TAXONOMY_METADATA: Dict[ErrorCode, Dict[str, Any]] = {
    # 1. UNCERTAIN_FACTS
    ErrorCode.DOC_ILLEGIBLE: {
        "category": UncertaintyCategory.UNCERTAIN_FACTS,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Ảnh chứng từ bị mờ hoặc không nhận diện được thông tin pháp lý."
    },
    ErrorCode.DOC_SUSPICIOUS: {
        "category": UncertaintyCategory.UNCERTAIN_FACTS,
        "default_target": TargetApproverRole.HR_OPERATIONS,
        "description": "Chứng từ có dấu hiệu can thiệp số liệu hoặc nghi vấn gian lận."
    },
    ErrorCode.DATE_LOGIC_INVALID: {
        "category": UncertaintyCategory.UNCERTAIN_FACTS,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Khoảng thời gian nghỉ không hợp lệ hoặc nghịch lý ngày tháng."
    },
    ErrorCode.HANDOVER_INVALID: {
        "category": UncertaintyCategory.UNCERTAIN_FACTS,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Nhân sự nhận bàn giao không hợp lệ trong hệ thống tổ chức."
    },
    ErrorCode.HANDOVER_CIRCULAR_LOOP: {
        "category": UncertaintyCategory.UNCERTAIN_FACTS,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Phát hiện vòng lặp bàn giao chéo giữa các nhân sự cùng vắng mặt."
    },
    ErrorCode.MEDICAL_DAYS_MISMATCH: {
        "category": UncertaintyCategory.UNCERTAIN_FACTS,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Số ngày xin nghỉ lệch so với thời hạn y khoa chỉ định trên giấy BHXH."
    },

    # 2. OUT_OF_POLICY
    ErrorCode.NOTICE_PERIOD_VIOLATED: {
        "category": UncertaintyCategory.OUT_OF_POLICY,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Thời hạn gửi đơn vi phạm quy định báo trước tối thiểu."
    },
    ErrorCode.BALANCE_EXCEEDED: {
        "category": UncertaintyCategory.OUT_OF_POLICY,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Số ngày xin nghỉ vượt quá số dư ngày phép năm tích lũy."
    },
    ErrorCode.TEAM_QUOTA_EXCEEDED: {
        "category": UncertaintyCategory.OUT_OF_POLICY,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Tỷ lệ vắng mặt của bộ phận vượt ngưỡng an toàn vận hành (30%)."
    },
    ErrorCode.UNQUALIFIED_SPECIAL_LEAVE: {
        "category": UncertaintyCategory.OUT_OF_POLICY,
        "default_target": TargetApproverRole.HR_OPERATIONS,
        "description": "Lý do xin nghỉ việc riêng có lương không đúng quy định Điều 115 BLLĐ."
    },
    ErrorCode.CONSECUTIVE_SPLIT_DETECTED: {
        "category": UncertaintyCategory.OUT_OF_POLICY,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Hành vi chia nhỏ đơn nghỉ thành các ngày liền kề để qua mặt hạn mức."
    },
    ErrorCode.CLUSTER_ABSENCE_ANOMALY: {
        "category": UncertaintyCategory.OUT_OF_POLICY,
        "default_target": TargetApproverRole.HR_DIRECTOR,
        "description": "Bất thường vắng mặt đồng loạt quy mô lớn trong cùng một thời điểm."
    },

    # 3. AUTHORITY_ESCALATION
    ErrorCode.DURATION_OVER_AI_LIMIT: {
        "category": UncertaintyCategory.AUTHORITY_ESCALATION,
        "default_target": TargetApproverRole.DIRECT_MANAGER,
        "description": "Đơn hợp lệ từ 3 đến 5 ngày, vượt trần tự duyệt của hệ thống."
    },
    ErrorCode.DURATION_OVER_MANAGER_LIMIT: {
        "category": UncertaintyCategory.AUTHORITY_ESCALATION,
        "default_target": TargetApproverRole.HR_DIRECTOR,
        "description": "Đơn nghỉ phép trên 5 ngày liên tục, cần phê duyệt cấp Giám đốc."
    },
    ErrorCode.LONG_TERM_UNPAID: {
        "category": UncertaintyCategory.AUTHORITY_ESCALATION,
        "default_target": TargetApproverRole.HR_DIRECTOR,
        "description": "Đơn nghỉ việc riêng không lương dài hạn trên 14 ngày làm việc."
    },
    ErrorCode.MANAGER_SELF_APPROVAL: {
        "category": UncertaintyCategory.AUTHORITY_ESCALATION,
        "default_target": TargetApproverRole.EXECUTIVE_BOARD,
        "description": "Trưởng phòng làm đơn nghỉ, thẩm quyền chuyển tiếp lên cấp trên trực tiếp."
    }
}


class EscalationDetail(BaseModel):
    """Mô hình dữ liệu chi tiết cho một trường hợp chuyển tiếp."""
    category: UncertaintyCategory = Field(
        ..., 
        description="Một trong 3 nhóm mức độ không chắc chắn bắt buộc."
    )
    error_code: ErrorCode = Field(
        ..., 
        description="Mã định danh lỗi cụ thể từ bảng Taxonomy."
    )
    target_role: TargetApproverRole = Field(
        ..., 
        description="Cấp quản lý có trách nhiệm trả lời câu hỏi chuyển tiếp."
    )
    actionable_question: str = Field(
        ..., 
        description="Câu hỏi trực diện, đủ dữ kiện để người duyệt bấm quyết định ngay."
    )
    plain_reason: str = Field(
        ..., 
        description="Giải thích bằng ngôn ngữ hành chính đơn giản, không dùng từ kỹ thuật."
    )


class ApprovalResult(BaseModel):
    """Cấu trúc dữ liệu đầu ra chuẩn hoá (Structured Output) của toàn hệ thống."""
    decision: DecisionType = Field(
        ..., 
        description="Quyết định cuối cùng: AUTO_APPROVE hoặc ESCALATE."
    )
    escalation: Optional[EscalationDetail] = Field(
        None, 
        description="Chi tiết chuyển tiếp nếu decision là ESCALATE."
    )
    applied_policy_clauses: list[str] = Field(
        default_factory=list,
        description="Danh sách các điều khoản trong policy_rules.md đã được đối chiếu."
    )
