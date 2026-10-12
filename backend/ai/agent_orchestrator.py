"""Deterministic agent orchestrator. Zero LLM calls in default pipeline."""
from datetime import datetime
from domain import RequestFacts, HumanFeedbackResolution
from rule_engine import LeaveRequest, LeaveRuleEngine
from calendar_service import CalendarService
from .schemas import ParsedLeaveRequest, AgentPipelineResult, EscalationQuestionPayload

class ModelUnavailable(RuntimeError): pass

class LeaveApprovalAgent:
    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        return self._llm

    def parse_natural_language(self, raw_text, current_date=None, context=None):
        if self._llm is not None:
            current_date = current_date or datetime.now(CalendarService().timezone).date()
            try:
                data = self._llm.generate_json(
                    system_prompt=f"Trích xuất đơn nghỉ phép ngày hiện tại {current_date}",
                    user_prompt=raw_text, response_model=ParsedLeaveRequest)
                return ParsedLeaveRequest.model_validate(data)
            except Exception as exc:
                raise ModelUnavailable('Không thể trích xuất văn bản.') from exc
        raise ModelUnavailable('LLM đã được loại bỏ hoàn toàn khỏi pipeline để tránh rủi ro hallucination. Hãy sử dụng form có cấu trúc.')

    def process_human_feedback(self, human_reply, current_request=None, escalation=None, employee_context=None):
        if self._llm is not None:
            try:
                data = self._llm.generate_json(
                    system_prompt="Phân tích phản hồi của quản lý",
                    user_prompt=human_reply, response_model=HumanFeedbackResolution)
                return HumanFeedbackResolution.model_validate(data)
            except Exception as exc:
                raise ModelUnavailable('Không thể đọc phản hồi.') from exc
        fb_u = (human_reply or '').upper()
        if any(k in fb_u for k in ('TỪ CHỐI', 'REJECT', 'BÁC BỎ', 'KHÔNG DUYỆT')):
            act = 'REJECT'
        elif any(k in fb_u for k in ('BỔ SUNG', 'INFO', 'THÊM THÔNG TIN', 'SỬA')):
            act = 'REQUEST_MORE_INFO'
        else:
            act = 'APPROVE_OVERRIDE'
        return HumanFeedbackResolution(action=act, feedback_notes=human_reply)

    def validate_and_check_policy(self, parsed, employee_context):
        facts = parsed.model_dump()
        return LeaveRuleEngine.evaluate(LeaveRequest(**facts, **employee_context))

    def generate_escalation_payload(self, parsed, rule_result, employee_context=None):
        return EscalationQuestionPayload.model_validate(rule_result.model_dump(mode='json'))

    def run_full_pipeline(self, raw_text=None, employee_context=None, human_feedback_text=None, structured_data=None):
        if human_feedback_text is not None:
            raise ValueError('Human actions must use persisted request workflow; do not reparse the original request.')
        parsed = ParsedLeaveRequest.model_validate(structured_data) if structured_data is not None else self.parse_natural_language(raw_text)
        result = self.validate_and_check_policy(parsed, employee_context or {})
        states = {'AUTO_APPROVE': 'COMPLETED', 'NO_LEAVE_REQUIRED': 'COMPLETED', 'AUTO_REJECT': 'REJECTED',
                  'NEED_CORRECTION': 'WAITING_EMPLOYEE', 'ESCALATE': 'PENDING_ESCALATION'}
        return AgentPipelineResult(
            step='EVALUATED', status=states[result.decision.value], parsed_request=parsed,
            final_decision=result.decision.value, engine_result=result,
            escalation_payload=self.generate_escalation_payload(parsed, result),
            history_log=['Structured input: 0 model calls' if structured_data is not None else 'Deterministic extraction', 'Deterministic policy evaluated']
        )
