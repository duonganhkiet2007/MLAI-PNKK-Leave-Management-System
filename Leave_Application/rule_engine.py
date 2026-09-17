"""
rule_engine.py
Bộ lọc Deterministic Validator (Rule Engine) cho hệ thống Phê duyệt Nghỉ phép (Track A).
Thực hiện các tính toán số học, kiểm tra ngày tháng, quỹ phép, hạn nộp và quota phòng ban
trước khi cần gọi đến LLM Reasoner. Giúp loại bỏ 100% hiện tượng ảo giác (hallucination).
"""
import os
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# Import các cấu trúc chuẩn từ file taxonomy.py
from taxonomy import (
    DecisionType,
    UncertaintyCategory,
    TargetApproverRole,
    ErrorCode,
    TAXONOMY_METADATA,
    EscalationDetail,
    ApprovalResult
)


class LeaveRequest(BaseModel, extra="allow"):
    """Cấu trúc dữ liệu đầu vào của một đơn nghỉ phép."""
    request_id: str = Field(..., description="Mã định danh đơn nghỉ")
    employee_id: str = Field(..., description="Mã nhân sự")
    employee_name: str = Field(..., description="Họ tên nhân sự")
    department: str = Field(..., description="Phòng ban / Bộ phận")
    remaining_leave_days: float = Field(..., description="Số dư phép năm hiện tại")
    submitted_at: datetime = Field(..., description="Thời điểm gửi đơn thực tế (timestamp)")
    from_date: date = Field(..., description="Ngày bắt đầu nghỉ")
    to_date: date = Field(..., description="Ngày kết thúc nghỉ")
    leave_type: str = Field(..., description="Loại nghỉ: 'Annual', 'Sick', 'Unpaid', 'Special'")
    reason: str = Field(..., description="Lý do xin nghỉ chi tiết")
    handover_person_id: Optional[str] = Field(None, description="Mã nhân sự nhận bàn giao công việc")
    team_absent_count: int = Field(0, description="Số lượng nhân sự trong team đã được duyệt nghỉ trong khoảng thời gian này")
    total_team_members: int = Field(1, description="Tổng số nhân sự của phòng ban")
    attachment_type: str = Field("none", description="Loại chứng từ: 'none', 'valid_bhxh_cert', 'vague_prescription', 'invalid'")

#đọc cache data nhân viên
import json
_employees_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "employees.json")
with open(_employees_file, "r", encoding="utf-8") as f:
    EMPLOYEE_DB: Dict[str, Dict[str, Any]] = {emp["employee_id"]: emp for emp in json.load(f)}

def get_employee_by_id(emp_id: str) -> Optional[Dict[str, Any]]:
    return EMPLOYEE_DB.get(emp_id)

def calculate_workdays(start_date: date, end_date: date) -> int:
    """
    Tính số ngày làm việc thực tế (bỏ qua Thứ Bảy và Chủ Nhật).
    Đảm bảo tính chính xác tuyệt đối về mặt thời gian.
    """
    if start_date > end_date:
        return 0
    
    current = start_date
    workdays = 0
    while current <= end_date:
        # weekday(): 0-4 là Thứ Hai đến Thứ Sáu, 5-6 là T7, CN
        if current.weekday() < 5:
            workdays += 1
        # Chuyển sang ngày tiếp theo
        from datetime import timedelta
        current += timedelta(days=1)
    return workdays


class LeaveRuleEngine:
    """Lớp thực thi các quy tắc kiểm tra định lượng."""

    @staticmethod
    def evaluate(request: LeaveRequest) -> ApprovalResult:
        applied_clauses: List[str] = []

        # ------------------------------------------------------------------
        # BƯỚC 1: KIỂM TRA TÍNH TOÀN VẸN THỜI GIAN (Temporal Integrity)
        # ------------------------------------------------------------------
        applied_clauses.append("Mục 2 & Mục 3: Toàn vẹn thời gian")
        if request.from_date > request.to_date:
            meta = TAXONOMY_METADATA[ErrorCode.DATE_LOGIC_INVALID]
            return ApprovalResult(
                decision=DecisionType.ESCALATE,
                escalation=EscalationDetail(
                    category=meta["category"],
                    error_code=ErrorCode.DATE_LOGIC_INVALID,
                    target_role=meta["default_target"],
                    plain_reason="Khoảng thời gian nghỉ không hợp lệ do ngày kết thúc trước ngày bắt đầu.",
                    actionable_question=f"Đơn của {request.employee_name} có ngày kết thúc ({request.to_date}) trước ngày bắt đầu ({request.from_date}). Quản lý có muốn từ chối để nhân sự nộp lại đơn chính xác không?"
                ),
                applied_policy_clauses=applied_clauses
            )

        workdays = calculate_workdays(request.from_date, request.to_date)
        if workdays <= 0:
            meta = TAXONOMY_METADATA[ErrorCode.DATE_LOGIC_INVALID]
            return ApprovalResult(
                decision=DecisionType.ESCALATE,
                escalation=EscalationDetail(
                    category=meta["category"],
                    error_code=ErrorCode.DATE_LOGIC_INVALID,
                    target_role=meta["default_target"],
                    plain_reason="Thời gian xin nghỉ không tính được ngày làm việc hợp lệ (có thể rơi toàn bộ vào cuối tuần).",
                    actionable_question=f"Đơn của {request.employee_name} tính ra số ngày làm việc bằng 0. Quản lý vui lòng xác nhận lại lịch nghỉ với nhân sự."
                ),
                applied_policy_clauses=applied_clauses
            )

        # ------------------------------------------------------------------
        # BƯỚC 2: KIỂM TRA CHỨNG TỪ NGHỈ ỐM (Sick Leave Check)
        # ------------------------------------------------------------------
        if request.leave_type.lower() == "sick" and workdays >= 2:
            applied_clauses.append("Mục 1.2: Chứng từ nghỉ ốm từ 2 ngày trở lên")
            if request.attachment_type != "valid_bhxh_cert":
                meta = TAXONOMY_METADATA[ErrorCode.DOC_ILLEGIBLE]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.DOC_ILLEGIBLE,
                        target_role=meta["default_target"],
                        plain_reason=f"Nghỉ ốm {workdays} ngày nhưng chứng từ đính kèm không phải Giấy chứng nhận nghỉ BHXH hợp lệ.",
                        actionable_question=f"Nhân sự {request.employee_name} xin nghỉ ốm {workdays} ngày nhưng chứng từ chưa đạt chuẩn BHXH. Quản lý có yêu cầu bổ sung giấy khám đúng mẫu hay đồng ý chuyển sang trừ phép năm?"
                    ),
                    applied_policy_clauses=applied_clauses
                )

        # ------------------------------------------------------------------
        # BƯỚC 3: KIỂM TRA QUỸ PHÉP NĂM (Balance Check)
        # ------------------------------------------------------------------
        if request.leave_type.lower() == "annual":
            applied_clauses.append("Mục 1.1: Quỹ phép năm")
            if workdays > request.remaining_leave_days:
                meta = TAXONOMY_METADATA[ErrorCode.BALANCE_EXCEEDED]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.BALANCE_EXCEEDED,
                        target_role=meta["default_target"],
                        plain_reason=f"Số ngày xin nghỉ ({workdays} ngày) vượt quá số dư phép năm hiện có ({request.remaining_leave_days} ngày).",
                        actionable_question=f"{request.employee_name} xin nghỉ {workdays} ngày nhưng quỹ phép chỉ còn {request.remaining_leave_days} ngày. Quản lý có đồng ý trừ hết phép và chuyển số ngày dôi ra thành nghỉ không lương không?"
                    ),
                    applied_policy_clauses=applied_clauses
                )

        # ------------------------------------------------------------------
        # BƯỚC 4: KIỂM TRA THỜI HẠN NỘP ĐƠN TRƯỚC (Notice Period Check)
        # ------------------------------------------------------------------
        applied_clauses.append("Mục 2: Thời hạn báo trước (Notice Period)")
        # Giả định mốc 08:30 sáng của ngày bắt đầu nghỉ
        from datetime import datetime, time
        deadline_datetime = datetime.combine(request.from_date, time(8, 30))
        
        # Tính khoảng cách thời gian từ lúc nộp (submitted_at) đến 08:30 sáng ngày nghỉ
        time_diff_hours = (deadline_datetime - request.submitted_at.replace(tzinfo=None)).total_seconds() / 3600.0

        # Xử lý theo loại nghỉ:
        # 1. Nghỉ ốm đột xuất: Báo trước 08:30 sáng của ngày nghỉ đầu tiên (time_diff_hours >= 0)
        if request.leave_type.lower() == "sick":
            if time_diff_hours < 0:
                meta = TAXONOMY_METADATA[ErrorCode.NOTICE_PERIOD_VIOLATED]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.NOTICE_PERIOD_VIOLATED,
                        target_role=meta["default_target"],
                        plain_reason=f"Nghỉ ốm đột xuất nhưng nộp sau 08:30 sáng của ngày bắt đầu nghỉ.",
                        actionable_question=f"{request.employee_name} nộp đơn nghỉ ốm sau 08:30 sáng. Quản lý có phê duyệt ngoại lệ đơn nộp muộn này không?"
                    ),
                    applied_policy_clauses=applied_clauses
                )
        else:
            # 2. Các loại nghỉ thông thường (Annual, Unpaid, Special):
            if workdays <= 2 and time_diff_hours < 24:
                meta = TAXONOMY_METADATA[ErrorCode.NOTICE_PERIOD_VIOLATED]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.NOTICE_PERIOD_VIOLATED,
                        target_role=meta["default_target"],
                        plain_reason=f"Nghỉ {workdays} ngày nhưng nộp đơn trễ (dưới 24 giờ trước thời điểm nghỉ).",
                        actionable_question=f"{request.employee_name} nộp đơn xin nghỉ {workdays} ngày vi phạm quy định báo trước 24 giờ. Quản lý có phê duyệt ngoại lệ do tính cấp bách không?"
                    ),
                    applied_policy_clauses=applied_clauses
                )
            elif workdays > 2 and time_diff_hours < (3 * 24): # Yêu cầu 3 ngày làm việc (~72h)
                meta = TAXONOMY_METADATA[ErrorCode.NOTICE_PERIOD_VIOLATED]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.NOTICE_PERIOD_VIOLATED,
                        target_role=meta["default_target"],
                        plain_reason=f"Nghỉ {workdays} ngày nhưng nộp đơn trễ hơn thời hạn quy định (yêu cầu báo trước 3 ngày làm việc).",
                        actionable_question=f"{request.employee_name} xin nghỉ {workdays} ngày nhưng nộp đơn gấp. Quản lý có đồng ý phê duyệt ngoại lệ này không?"
                    ),
                    applied_policy_clauses=applied_clauses
                )

        # ------------------------------------------------------------------
        # BƯỚC 5: KIỂM TRA HẠN MỨC PHÒNG BAN (Team Capacity Quota <= 30%)
        # ------------------------------------------------------------------
        applied_clauses.append("Mục 3.1: Hạn mức vắng mặt phòng ban (30%)")
        if request.total_team_members > 0:
            absence_ratio = (request.team_absent_count + 1) / request.total_team_members
            if absence_ratio > 0.30:
                meta = TAXONOMY_METADATA[ErrorCode.TEAM_QUOTA_EXCEEDED]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.TEAM_QUOTA_EXCEEDED,
                        target_role=meta["default_target"],
                        plain_reason=f"Tỷ lệ vắng mặt của phòng ban trong ngày đạt {absence_ratio*100:.1f}%, vượt trần an toàn 30%.",
                        actionable_question=f"Vào ngày nghỉ của {request.employee_name}, phòng {request.department} đã có {request.team_absent_count} người nghỉ (tổng tỷ lệ đạt {absence_ratio*100:.1f}% > 30%). Trưởng phòng có phê duyệt trường hợp trùng lịch này không?"
                    ),
                    applied_policy_clauses=applied_clauses
                )

        # ------------------------------------------------------------------
        # BƯỚC 6: KIỂM TRA BÀN GIAO CÔNG VIỆC (Handover Check >= 3 days)
        # ------------------------------------------------------------------
        if workdays >= 3:
            applied_clauses.append("Mục 3.2: Bàn giao công việc (từ 3 ngày trở lên)")
            if not request.handover_person_id or request.handover_person_id.strip() == "":
                meta = TAXONOMY_METADATA[ErrorCode.HANDOVER_INVALID]
                return ApprovalResult(
                    decision=DecisionType.ESCALATE,
                    escalation=EscalationDetail(
                        category=meta["category"],
                        error_code=ErrorCode.HANDOVER_INVALID,
                        target_role=meta["default_target"],
                        plain_reason=f"Đơn nghỉ dài ngày ({workdays} ngày) nhưng thiếu thông tin nhân sự nhận bàn giao công việc.",
                        actionable_question=f"{request.employee_name} xin nghỉ {workdays} ngày nhưng chưa chỉ định người bàn giao. Quản lý có yêu cầu nhân sự cập nhật người backup trước khi duyệt không?"
                    ),
                    applied_policy_clauses=applied_clauses
                )

        # ------------------------------------------------------------------
        # BƯỚC 7: KIỂM TRA THẨM QUYỀN TỰ ĐOẠN (Authority Tier Scope)
        # ------------------------------------------------------------------
        applied_clauses.append("Mục 4.1: Phân cấp thẩm quyền phê duyệt")
        if workdays <= 2:
            # Hợp lệ 100% và nằm trong hạn mức tự duyệt của AI (<= 2 ngày)
            return ApprovalResult(
                decision=DecisionType.AUTO_APPROVE,
                escalation=None,
                applied_policy_clauses=applied_clauses
            )
        elif 3 <= workdays <= 5:
            # Rơi vào thẩm quyền của Trưởng bộ phận (Manager)
            meta = TAXONOMY_METADATA[ErrorCode.DURATION_OVER_AI_LIMIT]
            return ApprovalResult(
                decision=DecisionType.ESCALATE,
                escalation=EscalationDetail(
                    category=meta["category"],
                    error_code=ErrorCode.DURATION_OVER_AI_LIMIT,
                    target_role=meta["default_target"],
                    plain_reason=f"Đơn hợp lệ nhưng thời lượng nghỉ kéo dài {workdays} ngày (vượt trần tự duyệt 2 ngày của hệ thống).",
                    actionable_question=f"{request.employee_name} xin nghỉ {workdays} ngày, hồ sơ đầy đủ hợp lệ và đã bàn giao công việc. Trưởng phòng có phê duyệt đợt nghỉ này không?"
                ),
                applied_policy_clauses=applied_clauses
            )
        else:
            # Rơi vào thẩm quyền của Giám đốc Khối / HRD (> 5 ngày)
            meta = TAXONOMY_METADATA[ErrorCode.DURATION_OVER_MANAGER_LIMIT]
            return ApprovalResult(
                decision=DecisionType.ESCALATE,
                escalation=EscalationDetail(
                    category=meta["category"],
                    error_code=ErrorCode.DURATION_OVER_MANAGER_LIMIT,
                    target_role=meta["default_target"],
                    plain_reason=f"Đơn nghỉ dài hạn kéo dài {workdays} ngày, vượt thẩm quyền của Trưởng phòng.",
                    actionable_question=f"{request.employee_name} xin nghỉ dài hạn {workdays} ngày liên tiếp. Giám đốc Khối có phê duyệt đợt nghỉ này không?"
                ),
                applied_policy_clauses=applied_clauses
            )