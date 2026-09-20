"""One extraction call for text, zero for structured requests and explanations."""
import sys
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Leave_Application'))
from domain import RequestFacts, HumanFeedbackResolution
from rule_engine import LeaveRequest, LeaveRuleEngine
from calendar_service import CalendarService
from schemas import ParsedLeaveRequest, AgentPipelineResult, EscalationQuestionPayload
from prompts import PARSE_REQUEST_SYSTEM_PROMPT, HUMAN_FEEDBACK_SYSTEM_PROMPT

class ModelUnavailable(RuntimeError): pass

class LeaveApprovalAgent:
    def __init__(self, llm_client=None):
        self._llm = llm_client

    @property
    def llm(self):
        if self._llm is None:
            from llm_client import LLMClient
            self._llm = LLMClient()
        return self._llm

    def parse_natural_language(self, raw_text, current_date=None, context=None):
        current_date = current_date or datetime.now(CalendarService().timezone).date()
        try:
            data=self.llm.generate_json(
                system_prompt=PARSE_REQUEST_SYSTEM_PROMPT.format(current_date=current_date),
                user_prompt=raw_text, response_model=ParsedLeaveRequest)
            return ParsedLeaveRequest.model_validate(data)
        except Exception as exc:
            raise ModelUnavailable('Không thể trích xuất văn bản. Hãy dùng form hoặc thử lại khi model sẵn sàng.') from exc

    def process_human_feedback(self, human_reply, current_request=None, escalation=None, employee_context=None):
        try:
            data=self.llm.generate_json(system_prompt=HUMAN_FEEDBACK_SYSTEM_PROMPT,
                user_prompt=human_reply,response_model=HumanFeedbackResolution)
            return HumanFeedbackResolution.model_validate(data)
        except Exception as exc:
            raise ModelUnavailable('Không thể đọc phản hồi. Hãy dùng nút thao tác hoặc thử lại.') from exc

    def validate_and_check_policy(self, parsed, employee_context):
        facts=parsed.model_dump()
        # Context comes from caller's trusted DB adapter, not the extraction output.
        return LeaveRuleEngine.evaluate(LeaveRequest(**facts,**employee_context))

    def generate_escalation_payload(self, parsed, rule_result, employee_context=None):
        return EscalationQuestionPayload.model_validate(rule_result.model_dump(mode='json'))

    def run_full_pipeline(self, raw_text=None, employee_context=None, human_feedback_text=None, structured_data=None):
        if human_feedback_text is not None:
            raise ValueError('Human actions must use persisted request workflow; do not reparse the original request.')
        parsed=ParsedLeaveRequest.model_validate(structured_data) if structured_data is not None else self.parse_natural_language(raw_text)
        result=self.validate_and_check_policy(parsed,employee_context or {})
        states={'AUTO_APPROVE':'COMPLETED','NO_LEAVE_REQUIRED':'COMPLETED','AUTO_REJECT':'REJECTED',
                'NEED_CORRECTION':'WAITING_EMPLOYEE','ESCALATE':'PENDING_ESCALATION'}
        return AgentPipelineResult(step='EVALUATED',status=states[result.decision.value],parsed_request=parsed,
            final_decision=result.decision.value,engine_result=result,
            escalation_payload=self.generate_escalation_payload(parsed,result),
            history_log=['Structured input: 0 model calls' if structured_data is not None else 'Text extraction: 1 model call','Deterministic policy evaluated'])
