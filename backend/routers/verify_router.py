"""
verify_router.py
Router thực hiện bài kiểm tra tự động (Verify Harness 90 giây) phục vụ Ban Giám khảo chấm thi MLAI Hackathon 2026.
Tiêu chuẩn ĐẠT:
- 3 trường hợp thường quy: AUTO_APPROVE
- 2 trường hợp cần chuyển tiếp: ESCALATE (kèm nhóm lỗi và câu hỏi hành động cụ thể)
- Hỗ trợ nhập 1 trường hợp mới bất kỳ để kiểm chứng không hard-code.
"""

import os
import json
from datetime import datetime, date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

import sys
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(backend_dir)
leave_app_dir = os.path.join(root_dir, "Leave_Application")
llm_kiet_dir = os.path.join(root_dir, "LLM-KIET")
for p in [leave_app_dir, llm_kiet_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from rule_engine import LeaveRequest, LeaveRuleEngine, calculate_workdays
from agent_orchestrator import LeaveApprovalAgent

router = APIRouter(prefix="/api/verify", tags=["Verify Harness (Ban Giám Khảo)"])

TEST_CASES_FILE = os.path.join(leave_app_dir, "test_cases.json")


class CustomVerifyInput(BaseModel):
    """Đầu vào trường hợp mới do Giám khảo tự nhập trong 90 giây."""
    employee_name: str = Field("Nhân sự Giám khảo test", description="Họ tên nhân viên")
    department: str = Field("Engineering", description="Phòng ban")
    remaining_leave_days: float = Field(10.0, description="Số dư phép năm")
    from_date: str = Field(..., description="Ngày bắt đầu (YYYY-MM-DD)")
    to_date: str = Field(..., description="Ngày kết thúc (YYYY-MM-DD)")
    leave_type: str = Field("Annual", description="Annual, Sick, Unpaid, Special")
    reason: str = Field(..., description="Lý do xin nghỉ")
    handover_person_id: Optional[str] = Field(None, description="Mã người bàn giao")
    team_absent_count: int = Field(0, description="Số người trong team đã nghỉ")
    total_team_members: int = Field(10, description="Tổng quân số team")
    attachment_type: str = Field("none", description="none, valid_bhxh_cert, vague_prescription, invalid")
    submitted_at: Optional[str] = Field(None, description="Thời điểm nộp đơn (ISO datetime)")


@router.get("/test-cases", summary="Lấy toàn bộ bộ dữ liệu kiểm thử (15+ cases)")
def get_all_test_cases():
    if not os.path.exists(TEST_CASES_FILE):
        raise HTTPException(status_code=404, detail="Không tìm thấy file test_cases.json")
    with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"success": True, "total": len(data), "data": data}


@router.post("/escalation", summary="Chạy Verify Harness 90s của Ban Giám Khảo (1 Click thực thi 5 cases chuẩn)")
def run_verify_harness():
    """
    Ban Giám khảo chọn Verify -> Escalation:
    Tự động chạy 5 trường hợp (3 auto + 2 escalate) và trả về bảng so sánh kết quả.
    """
    if not os.path.exists(TEST_CASES_FILE):
        raise HTTPException(status_code=404, detail="Không tìm thấy file test_cases.json")

    with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    # Lọc 5 cases phục vụ harness
    harness_cases = [c for c in all_cases if c.get("is_verify_harness") is True]
    if len(harness_cases) == 0:
        harness_cases = all_cases[:5]

    results = []
    auto_count = 0
    escalate_count = 0
    passed_count = 0

    for tc in harness_cases:
        req_dict = tc["request"]
        # Xây dựng đối tượng LeaveRequest
        req_obj = LeaveRequest(
            request_id=req_dict["request_id"],
            employee_id=req_dict["employee_id"],
            employee_name=req_dict["employee_name"],
            department=req_dict["department"],
            remaining_leave_days=float(req_dict["remaining_leave_days"]),
            submitted_at=datetime.fromisoformat(req_dict["submitted_at"]),
            from_date=date.fromisoformat(req_dict["from_date"]),
            to_date=date.fromisoformat(req_dict["to_date"]),
            leave_type=req_dict["leave_type"],
            reason=req_dict["reason"],
            handover_person_id=req_dict.get("handover_person_id"),
            team_absent_count=int(req_dict.get("team_absent_count", 0)),
            total_team_members=int(req_dict.get("total_team_members", 1)),
            attachment_type=req_dict.get("attachment_type", "none")
        )

        eval_res = LeaveRuleEngine.evaluate(req_obj)
        actual_decision = eval_res.decision.value

        if actual_decision == "AUTO_APPROVE":
            auto_count += 1
        elif actual_decision == "ESCALATE":
            escalate_count += 1

        is_decision_match = (actual_decision == tc.get("expected_decision"))
        
        # So khớp category nếu có
        actual_cat = eval_res.escalation.category.value if eval_res.escalation else None
        expected_cat = tc.get("expected_category")
        is_category_match = (actual_cat == expected_cat) if expected_cat else True

        is_passed = is_decision_match and is_category_match
        if is_passed:
            passed_count += 1

        results.append({
            "test_id": tc["id"],
            "scenario_name": tc["scenario_name"],
            "expected_decision": tc.get("expected_decision"),
            "actual_decision": actual_decision,
            "expected_category": expected_cat,
            "actual_category": actual_cat,
            "error_code": eval_res.escalation.error_code.value if eval_res.escalation else None,
            "target_role": eval_res.escalation.target_role.value if eval_res.escalation else None,
            "actionable_question": eval_res.escalation.actionable_question if eval_res.escalation else "Tự động phê duyệt hợp lệ (Không cần chuyển tiếp).",
            "plain_reason": eval_res.escalation.plain_reason if eval_res.escalation else "Hồ sơ hợp lệ 100% theo quy chế.",
            "is_passed": is_passed
        })

    is_overall_passed = (auto_count == 3 and escalate_count == 2 and passed_count == 5)

    return {
        "success": True,
        "summary": {
            "total_cases": len(harness_cases),
            "passed_cases": passed_count,
            "auto_approved_cases": auto_count,
            "escalated_cases": escalate_count,
            "target_auto": 3,
            "target_escalate": 2,
            "overall_status": "ĐẠT (PASS 100%)" if is_overall_passed else "CẦN ĐIỀU CHỈNH",
            "evaluation_standard": "2 trường hợp được chuyển tiếp, 3 trường hợp được xử lý tự động theo đúng tiêu chí 90 giây của Ban Giám khảo."
        },
        "details": results
    }


@router.post("/custom", summary="Giám khảo kiểm thử 1 trường hợp mới bất kỳ (Chống hard-code)")
def verify_custom_case(payload: CustomVerifyInput):
    """
    Sau khi chạy 5 cases tự động, Giám khảo nhập 1 trường hợp mới dựa trên quy chế
    để kiểm tra xem hệ thống có xử lý linh hoạt và chính xác không.
    """
    submitted_at = datetime.fromisoformat(payload.submitted_at) if payload.submitted_at else datetime.now()
    f_date = date.fromisoformat(payload.from_date)
    t_date = date.fromisoformat(payload.to_date)
    workdays = calculate_workdays(f_date, t_date)

    context = {
        "request_id": f"REQ-GK-{datetime.now().strftime('%M%S')}",
        "employee_id": "EMP_JUDGE",
        "employee_name": payload.employee_name,
        "department": payload.department,
        "remaining_leave_days": payload.remaining_leave_days,
        "submitted_at": submitted_at.isoformat(),
        "team_absent_count": payload.team_absent_count,
        "total_team_members": payload.total_team_members,
        "handover_person_id": payload.handover_person_id,
        "attachment_type": payload.attachment_type
    }

    input_text = f"Tôi là {payload.employee_name} ({payload.department}), xin nghỉ từ {payload.from_date} đến {payload.to_date}. Loại nghỉ: {payload.leave_type}. Lý do: {payload.reason}."

    try:
        agent = LeaveApprovalAgent()
        agent_res = agent.run_full_pipeline(raw_text=input_text, employee_context=context)

        esc = agent_res.escalation_payload
        final_dec = "AUTO_APPROVE" if agent_res.final_decision == "AUTO_APPROVE" else "ESCALATE"

        return {
            "success": True,
            "input": payload.model_dump(),
            "calculated_workdays": workdays,
            "decision": final_dec,
            "uncertainty_category": esc.uncertainty_category if esc else None,
            "error_code": esc.error_code if esc else None,
            "target_role": esc.target_role if esc else None,
            "actionable_question": esc.actionable_question if esc else None,
            "plain_reason": esc.human_readable_explanation if esc else "Đơn hoàn toàn hợp lệ và tự động được phê duyệt.",
            "applied_policy_clauses": esc.applied_policy_clauses if esc else []
        }
    except Exception as e:
        return {
            "success": False,
            "input": payload.model_dump(),
            "calculated_workdays": workdays,
            "decision": "LLM_OFFLINE",
            "uncertainty_category": "SYSTEM_DEPENDENCY_OFFLINE",
            "error_code": "LLM_SERVER_UNAVAILABLE",
            "target_role": "SYSTEM_ADMIN",
            "actionable_question": "Model vLLM Qwen 7B chưa được bật trên GPU. Bạn có muốn kích hoạt bằng tmux để LLM phân tích ngữ nghĩa không?",
            "plain_reason": f"Không thể phân tích ngữ nghĩa vì vLLM Qwen 7B chưa được khởi chạy: {e}",
            "applied_policy_clauses": ["Yêu cầu LLM Server hoạt động"]
        }

