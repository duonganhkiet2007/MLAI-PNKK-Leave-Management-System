"""
orchestration.py
Service kết nối Database, Agent LLM (Kiệt) và Rule Engine (Kim).
Thực thi toàn bộ luồng nghiệp vụ và ghi nhận Audit Log chi tiết.
"""

import sys
import os
import json
import uuid
from datetime import datetime, date
from typing import Dict, Any, Optional

# Thêm đường dẫn tới Leave_Application và LLM-KIET
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.dirname(backend_dir)
leave_app_dir = os.path.join(root_dir, "Leave_Application")
llm_kiet_dir = os.path.join(root_dir, "LLM-KIET")

for p in [leave_app_dir, llm_kiet_dir, backend_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from agent_orchestrator import LeaveApprovalAgent
from rule_engine import calculate_workdays
from database import (
    get_employee,
    get_team_absent_count,
    get_department_total_members,
    save_leave_request,
    add_audit_log,
    get_leave_request,
    deduct_employee_leave_days
)


class LeaveOrchestratorService:
    def __init__(self):
        self.agent = LeaveApprovalAgent()

    def process_new_request(
        self,
        raw_text: Optional[str] = None,
        employee_id: Optional[str] = None,
        structured_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Tiếp nhận đơn nghỉ phép:
        1. Nhận qua tin nhắn chat tự nhiên (raw_text)
        2. Hoặc nhận qua Form có cấu trúc (structured_data)
        """
        request_id = f"REQ-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        
        # 1. Xác định nhân sự gửi đơn
        emp_id = employee_id or (structured_data.get("employee_id") if structured_data else None) or "EMP012"
        employee = get_employee(emp_id)
        if not employee:
            # Fallback nếu mã nhân sự chưa có trong DB
            employee = {
                "employee_id": emp_id,
                "name": "Nhân sự mới",
                "department": "Engineering",
                "remaining_leave_days": 12.0
            }

        # 2. Xây dựng ngữ cảnh nhân sự (Context)
        submitted_at = datetime.now()
        dep = employee.get("department", "Engineering")
        target_date_str = (structured_data.get("from_date") if structured_data else None) or submitted_at.strftime("%Y-%m-%d")
        team_absent = get_team_absent_count(dep, target_date_str)
        total_members = get_department_total_members(dep)

        context = {
            "request_id": request_id,
            "employee_id": employee["employee_id"],
            "employee_name": employee["name"],
            "department": dep,
            "remaining_leave_days": float(employee["remaining_leave_days"]),
            "submitted_at": submitted_at.isoformat(),
            "team_absent_count": team_absent,
            "total_team_members": total_members,
            "handover_person_id": structured_data.get("handover_person_id") if structured_data else None,
            "attachment_type": structured_data.get("attachment_type", "none") if structured_data else "none"
        }

        # 3. Chuẩn bị nội dung text đưa vào pipeline
        input_text = raw_text
        if not input_text and structured_data:
            input_text = f"Tôi là {employee['name']} ({employee['employee_id']}), xin nghỉ phép từ {structured_data.get('from_date')} đến {structured_data.get('to_date')}. Loại nghỉ: {structured_data.get('leave_type', 'Annual')}. Lý do: {structured_data.get('reason', 'Việc cá nhân')}."

        add_audit_log(request_id, "RECEIVE_REQUEST", "SUBMITTED", f"Nhận đơn từ {employee['name']} ({emp_id}): {input_text}")

        # 4. Chạy toàn bộ pipeline của Agent (Parse -> Validate -> Rule Engine -> Gom vấn đề -> Escalation)
        result = self.agent.run_full_pipeline(
            raw_text=input_text,
            employee_context=context
        )

        parsed = result.parsed_request
        esc = result.escalation_payload

        # Tính số ngày làm việc
        workdays = 0
        if parsed and parsed.from_date and parsed.to_date:
            workdays = calculate_workdays(parsed.from_date, parsed.to_date)

        # Trạng thái tổng thể
        status = "COMPLETED" if result.final_decision == "AUTO_APPROVE" else "PENDING_ESCALATION"

        # 5. Lưu vào Cơ sở dữ liệu SQLite
        db_record = {
            "id": request_id,
            "employee_id": employee["employee_id"],
            "employee_name": employee["name"],
            "department": dep,
            "from_date": parsed.from_date.isoformat() if (parsed and parsed.from_date) else None,
            "to_date": parsed.to_date.isoformat() if (parsed and parsed.to_date) else None,
            "workdays": workdays,
            "leave_type": parsed.leave_type.value if parsed else "Annual",
            "reason": parsed.reason if parsed else input_text,
            "handover_person_id": parsed.handover_person_id or context.get("handover_person_id"),
            "handover_person_name": parsed.handover_person_name,
            "attachment_type": parsed.attachment_type.value if parsed else "none",
            "decision": result.final_decision or "UNKNOWN",
            "uncertainty_category": esc.uncertainty_category if esc else None,
            "error_code": esc.error_code if esc else None,
            "target_role": esc.target_role if esc else None,
            "actionable_question": esc.actionable_question if esc else None,
            "quick_action_options": json.dumps(esc.quick_action_options if esc else []),
            "human_readable_explanation": esc.human_readable_explanation if esc else "",
            "applied_policy_clauses": json.dumps(esc.applied_policy_clauses if esc else []),
            "human_feedback_text": None,
            "status": status,
            "submitted_at": submitted_at.isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        save_leave_request(db_record)

        # 6. Ghi nhật ký Audit Trail cho từng bước
        for log_line in result.history_log:
            add_audit_log(request_id, "AGENT_STEP", "PIPELINE_EXEC", log_line)

        # Nếu tự duyệt thành công -> Trừ phép năm ngay
        if result.final_decision == "AUTO_APPROVE" and workdays > 0 and (parsed and parsed.leave_type.value == "Annual"):
            deduct_employee_leave_days(employee["employee_id"], float(workdays))
            add_audit_log(request_id, "LEAVE_BALANCE_DEDUCT", "SUCCESS", f"Đã trừ {workdays} ngày phép năm của {employee['name']}.")

        return get_leave_request(request_id)

    def process_human_decision(
        self,
        request_id: str,
        feedback_text: str,
        approver_id: Optional[str] = "MANAGER"
    ) -> Dict[str, Any]:
        """Tiếp nhận phản hồi từ Quản lý / Ban Giám đốc cho đơn đang bị ESCALATE."""
        req = get_leave_request(request_id)
        if not req:
            raise ValueError(f"Không tìm thấy đơn {request_id}")

        if req["status"] != "PENDING_ESCALATION":
            raise ValueError(f"Đơn {request_id} không ở trạng thái chờ duyệt (Hiện tại: {req['status']})")

        add_audit_log(request_id, "HUMAN_RESPONSE", "RECEIVED", f"Cấp thẩm quyền ({approver_id}) phản hồi: \"{feedback_text}\"")

        # Chuẩn bị context để agent re-check
        employee = get_employee(req["employee_id"]) or {}
        context = {
            "request_id": request_id,
            "employee_id": req["employee_id"],
            "employee_name": req["employee_name"],
            "department": req["department"],
            "remaining_leave_days": float(employee.get("remaining_leave_days", 10.0)),
            "submitted_at": req["submitted_at"],
            "team_absent_count": get_team_absent_count(req["department"], req["from_date"]),
            "total_team_members": get_department_total_members(req["department"]),
            "handover_person_id": req["handover_person_id"],
            "attachment_type": req["attachment_type"]
        }

        # Gọi Agent để parse câu trả lời và khép kín vòng lặp Re-check
        result = self.agent.run_full_pipeline(
            raw_text=req["reason"],
            employee_context=context,
            human_feedback_text=feedback_text
        )

        final_decision = result.final_decision
        final_status = "COMPLETED" if final_decision == "APPROVED_BY_HUMAN_OVERRIDE" else "REJECTED"

        # Cập nhật DB
        req["decision"] = final_decision
        req["status"] = final_status
        req["human_feedback_text"] = feedback_text
        req["updated_at"] = datetime.now().isoformat()
        
        # Parse chuỗi JSON lại để save
        req["quick_action_options"] = json.dumps(req.get("quick_action_options", []))
        req["applied_policy_clauses"] = json.dumps(req.get("applied_policy_clauses", []))

        save_leave_request(req)

        # Ghi log kết quả
        add_audit_log(request_id, "RECHECK_DECISION", final_status, f"Quyết định cuối cùng: {final_decision}. Ghi nhận ý kiến: {feedback_text}")

        # Nếu được duyệt đặc cách -> Trừ phép năm nếu là Annual
        if final_decision == "APPROVED_BY_HUMAN_OVERRIDE" and req.get("workdays", 0) > 0 and req.get("leave_type") == "Annual":
            deduct_employee_leave_days(req["employee_id"], float(req["workdays"]))
            add_audit_log(request_id, "LEAVE_BALANCE_DEDUCT", "SUCCESS", f"Đã trừ {req['workdays']} ngày phép năm sau khi duyệt đặc cách.")

        return get_leave_request(request_id)
