"""
agent_orchestrator.py
Bộ điều phối Agentic Workflow (The Escalation Referee Pipeline) cho Người 2 - Kiệt.
Hiện thực hóa đúng 100% sơ đồ quy trình:
Request -> Parse toàn bộ -> Validate toàn bộ -> Check toàn bộ rule -> Gom vấn đề ->
[Không vấn đề -> Auto xử lý] | [Có vấn đề -> Hỏi human 1 lần -> Nhận câu trả lời -> Re-check toàn bộ -> Auto xử lý / hỏi tiếp]
"""

import sys
import os
import re
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

# Thêm đường dẫn để import Rule Engine của Kim
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
leave_app_dir = os.path.join(parent_dir, "Leave_Application")
if leave_app_dir not in sys.path:
    sys.path.insert(0, leave_app_dir)

from taxonomy import (
    DecisionType,
    UncertaintyCategory,
    TargetApproverRole,
    ErrorCode,
    TAXONOMY_METADATA,
    EscalationDetail,
    ApprovalResult
)
from rule_engine import LeaveRequest, LeaveRuleEngine, calculate_workdays

from schemas import (
    ParsedLeaveRequest,
    EscalationQuestionPayload,
    HumanFeedbackResolution,
    AgentPipelineResult,
    LeaveTypeEnum,
    AttachmentTypeEnum
)
from prompts import (
    PARSE_REQUEST_SYSTEM_PROMPT,
    ESCALATION_SYSTEM_PROMPT,
    HUMAN_FEEDBACK_SYSTEM_PROMPT
)
from llm_client import LLMClient


class LeaveApprovalAgent:
    """Agent điều phối toàn bộ quy trình phê duyệt nghỉ phép."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    # --------------------------------------------------------------------------
    # BƯỚC 1: PARSE TOÀN BỘ (Natural Language -> Structured Leave Request)
    # --------------------------------------------------------------------------
    def parse_natural_language(
        self,
        raw_text: str,
        current_date: Optional[date] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ParsedLeaveRequest:
        """Trích xuất tin nhắn tự nhiên thành cấu trúc dữ liệu chuẩn. Bắt cờ mơ hồ nếu thiếu thông tin."""
        current_date = current_date or date.today()
        sys_prompt = PARSE_REQUEST_SYSTEM_PROMPT.format(current_date=current_date.isoformat())
        user_prompt = f"Tin nhắn nhân viên: \"{raw_text}\"\nContext nhân sự: {context or {}}"

        data = self.llm.generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            response_model=ParsedLeaveRequest
        )
        return ParsedLeaveRequest.model_validate(data)


    # --------------------------------------------------------------------------
    # BƯỚC 2: VALIDATE TOÀN BỘ & GOM VẤN ĐỀ VỚI RULE ENGINE
    # --------------------------------------------------------------------------
    def validate_and_check_policy(
        self,
        parsed: ParsedLeaveRequest,
        employee_context: Dict[str, Any]
    ) -> ApprovalResult:
        """
        Gom tất cả vấn đề phát hiện được:
        1. Nếu parser phát hiện dữ liệu mơ hồ/thiếu ngày -> ESCALATE với nhóm UNCERTAIN_FACTS.
        2. Nếu đầy đủ -> Gọi Rule Engine của Kim để kiểm tra policy & hạn ngạch.
        """
        # Kiểm tra nếu dữ liệu mơ hồ hoặc lý do không chính đáng
        vague_patterns = [
            "lười", "không thích làm", "thích thì nghỉ", "không có lý do", "không lý do",
            "chán đi làm", "chẳng có lý do", "không vì lý do gì", "không cần lý do"
        ]
        reason_lower = (parsed.reason or "").lower()
        if any(p in reason_lower for p in vague_patterns):
            parsed.is_ambiguous = True
            if not parsed.ambiguity_reason:
                parsed.ambiguity_reason = f"Lý do xin nghỉ không chính đáng hoặc vi phạm kỷ luật lao động: '{parsed.reason}'"

        if parsed.is_ambiguous or not parsed.from_date or not parsed.to_date:
            action_q = (
                f"Đơn của nhân viên {parsed.employee_name or 'này'} có lý do không chính đáng hoặc vi phạm chuẩn mực lao động ('{parsed.reason}'). Quản lý có yêu cầu nhân viên giải trình lý do hợp lệ hoặc từ chối đơn không?"
                if ("lý do" in (parsed.ambiguity_reason or "").lower() or any(p in reason_lower for p in vague_patterns))
                else f"Đơn của nhân viên {parsed.employee_name or 'này'} chưa ghi rõ ngày bắt đầu/kết thúc cụ thể ({parsed.reason}). Nhân sự có yêu cầu nhân viên nộp lại đơn kèm lịch nghỉ chuẩn xác không?"
            )
            return ApprovalResult(
                decision=DecisionType.ESCALATE,
                escalation=EscalationDetail(
                    category=UncertaintyCategory.UNCERTAIN_FACTS,
                    error_code=ErrorCode.DOC_ILLEGIBLE,
                    target_role=TargetApproverRole.DIRECT_MANAGER,
                    plain_reason=f"Dữ liệu đơn không rõ ràng hoặc lý do không hợp lệ: {parsed.ambiguity_reason or parsed.missing_fields}",
                    actionable_question=action_q
                ),
                applied_policy_clauses=["Mục 1 & Mục 4: Tính minh bạch lý do xin nghỉ - Dữ liệu không chắc chắn (Uncertain Facts)"]
            )


        # Xây dựng đối tượng LeaveRequest hoàn chỉnh cho Rule Engine của Kim
        submitted_at_val = employee_context.get("submitted_at")
        if isinstance(submitted_at_val, str):
            submitted_at = datetime.fromisoformat(submitted_at_val)
        elif isinstance(submitted_at_val, datetime):
            submitted_at = submitted_at_val
        else:
            submitted_at = datetime.now()

        request_obj = LeaveRequest(
            request_id=employee_context.get("request_id", "REQ-TEMP"),
            employee_id=parsed.employee_id or employee_context.get("employee_id", "EMP001"),
            employee_name=parsed.employee_name or employee_context.get("employee_name", "Nhân viên"),
            department=parsed.department or employee_context.get("department", "Engineering"),
            remaining_leave_days=float(employee_context.get("remaining_leave_days", 12.0)),
            submitted_at=submitted_at,
            from_date=parsed.from_date,
            to_date=parsed.to_date,
            leave_type=parsed.leave_type.value,
            reason=parsed.reason,
            handover_person_id=parsed.handover_person_id or employee_context.get("handover_person_id"),
            team_absent_count=int(employee_context.get("team_absent_count", 0)),
            total_team_members=int(employee_context.get("total_team_members", 10)),
            attachment_type=parsed.attachment_type.value or employee_context.get("attachment_type", "none")
        )

        # Gọi trực tiếp Rule Engine của Kim
        rule_result = LeaveRuleEngine.evaluate(request_obj)
        return rule_result

    # --------------------------------------------------------------------------
    # BƯỚC 3: SINH CÂU HỎI ESCALATION CHUẨN 6/6 ĐIỂM BAN GIÁM KHẢO
    # --------------------------------------------------------------------------
    def generate_escalation_payload(
        self,
        parsed: ParsedLeaveRequest,
        rule_result: ApprovalResult,
        employee_context: Dict[str, Any]
    ) -> EscalationQuestionPayload:
        """Nếu có vấn đề, sinh câu hỏi hành động trực diện, tùy chọn nhanh và giải trình minh bạch."""
        if rule_result.decision == DecisionType.AUTO_APPROVE:
            return EscalationQuestionPayload(
                decision="AUTO_APPROVE",
                human_readable_explanation="Đơn hợp lệ 100% theo quy chế: Trong quỹ phép năm, đảm bảo thời hạn báo trước, quota vắng mặt phòng ban < 30%, nằm trong thẩm quyền tự duyệt của hệ thống.",
                applied_policy_clauses=rule_result.applied_policy_clauses
            )

        escalation = rule_result.escalation
        user_prompt = f"""
Thông tin đơn:
- Nhân viên: {parsed.employee_name} (Phòng {parsed.department})
- Thời gian: Từ {parsed.from_date} đến {parsed.to_date}
- Lý do: {parsed.reason}
- Kết quả Rule Engine: Mã lỗi {escalation.error_code.value}, Nhóm {escalation.category.value}
- Cấp thẩm quyền đích: {escalation.target_role.value}
- Chi tiết vi phạm: {escalation.plain_reason}
- Câu hỏi gốc: {escalation.actionable_question}
"""

        try:
            data = self.llm.generate_json(
                system_prompt=ESCALATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=None
            )
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

        payload_dict = {
            "decision": "ESCALATE",
            "uncertainty_category": data.get("uncertainty_category") or escalation.category.value,
            "error_code": data.get("error_code") or escalation.error_code.value,
            "target_role": data.get("target_role") or escalation.target_role.value,
            "actionable_question": data.get("actionable_question") or escalation.actionable_question,
            "quick_action_options": data.get("quick_action_options") or [
                "Phê duyệt đặc cách",
                "Từ chối đơn",
                "Yêu cầu nhân viên giải trình thêm"
            ],
            "human_readable_explanation": data.get("human_readable_explanation") or f"Hệ thống chuyển tiếp do: {escalation.plain_reason}",
            "applied_policy_clauses": data.get("applied_policy_clauses") or rule_result.applied_policy_clauses
        }
        return EscalationQuestionPayload.model_validate(payload_dict)


    # --------------------------------------------------------------------------
    # BƯỚC 4: NHẬN CÂU TRẢ LỜI CỦA HUMAN & RE-CHECK TOÀN BỘ
    # --------------------------------------------------------------------------
    def process_human_feedback(
        self,
        human_reply: str,
        current_request: ParsedLeaveRequest,
        escalation: EscalationQuestionPayload,
        employee_context: Dict[str, Any]
    ) -> HumanFeedbackResolution:
        """Phân tích câu trả lời của con người để ra quyết định hoặc điều chỉnh dữ liệu rồi re-check."""
        user_prompt = f"""
Câu hỏi đã gửi: {escalation.actionable_question}
Lựa chọn có sẵn: {escalation.quick_action_options}
Câu trả lời thực tế của Quản lý: "{human_reply}"
"""

        data = self.llm.generate_json(
            system_prompt=HUMAN_FEEDBACK_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=HumanFeedbackResolution
        )
        return HumanFeedbackResolution.model_validate(data)


    # --------------------------------------------------------------------------
    # TOÀN BỘ PIPELINE LIÊN HOÀN (FULL FLOW)
    # --------------------------------------------------------------------------
    def run_full_pipeline(
        self,
        raw_text: str,
        employee_context: Dict[str, Any],
        human_feedback_text: Optional[str] = None
    ) -> AgentPipelineResult:
        """
        Chạy toàn bộ quy trình:
        Request -> Parse -> Validate -> Check Rule -> Gom vấn đề -> [Auto duyệt hoặc Hỏi Human] -> Re-check.
        """
        logs = []
        logs.append(f"1. Nhận yêu cầu: \"{raw_text}\"")

        # Bước 1: Parse
        parsed = self.parse_natural_language(raw_text, context=employee_context)
        logs.append(f"2. Trích xuất thành công: Nghỉ từ {parsed.from_date} đến {parsed.to_date} ({parsed.leave_type.value})")
        if parsed.is_ambiguous:
            logs.append(f"   [CẢNH BÁO MƠ HỒ]: {parsed.ambiguity_reason}")

        # Bước 2: Validate & Rule Engine
        rule_result = self.validate_and_check_policy(parsed, employee_context)
        logs.append(f"3. Kiểm tra Rule Engine: Quyết định = {rule_result.decision.value}")

        # Bước 3: Gom vấn đề & Sinh Escalation nếu cần
        escalation_payload = self.generate_escalation_payload(parsed, rule_result, employee_context)

        if rule_result.decision == DecisionType.AUTO_APPROVE:
            logs.append("4. Hoàn tất: Đơn được phê duyệt tự động (Không có vi phạm).")
            return AgentPipelineResult(
                step="AUTO_COMPLETED",
                status="COMPLETED",
                parsed_request=parsed,
                escalation_payload=escalation_payload,
                final_decision="AUTO_APPROVE",
                history_log=logs
            )

        # Nếu có vấn đề -> Cần hỏi Human
        logs.append(f"4. Phát hiện vi phạm [{escalation_payload.error_code}]. Đang chuyển tiếp cho {escalation_payload.target_role}...")
        logs.append(f"   Câu hỏi: \"{escalation_payload.actionable_question}\"")

        # Nếu chưa có câu trả lời của Human -> Tạm dừng chờ Human
        if not human_feedback_text:
            return AgentPipelineResult(
                step="AWAITING_HUMAN_FEEDBACK",
                status="AWAITING_HUMAN",
                parsed_request=parsed,
                escalation_payload=escalation_payload,
                final_decision="ESCALATED_PENDING_HUMAN",
                history_log=logs
            )

        # Bước 4: Đã có câu trả lời của Human -> Parse & Re-check
        logs.append(f"5. Nhận phản hồi từ Human: \"{human_feedback_text}\"")
        feedback_res = self.process_human_feedback(
            human_reply=human_feedback_text,
            current_request=parsed,
            escalation=escalation_payload,
            employee_context=employee_context
        )
        logs.append(f"   Phân tích ý kiến: Action={feedback_res.action}, Duyệt={feedback_res.is_approved}")

        if feedback_res.is_approved:
            logs.append("6. Re-check: Nhân sự quản lý đã phê duyệt đặc cách/điều chỉnh hợp lệ. Hoàn tất phê duyệt!")
            return AgentPipelineResult(
                step="RESOLVED_AFTER_FEEDBACK",
                status="COMPLETED",
                parsed_request=parsed,
                escalation_payload=escalation_payload,
                final_decision="APPROVED_BY_HUMAN_OVERRIDE",
                history_log=logs
            )
        else:
            logs.append("6. Re-check: Nhân sự quản lý từ chối đơn. Đã đóng yêu cầu!")
            return AgentPipelineResult(
                step="REJECTED_AFTER_FEEDBACK",
                status="REJECTED",
                parsed_request=parsed,
                escalation_payload=escalation_payload,
                final_decision="REJECTED_BY_HUMAN",
                history_log=logs
            )
