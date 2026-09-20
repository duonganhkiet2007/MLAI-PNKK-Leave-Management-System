"""Deterministic briefing retaining the legacy public adapter name."""
from pydantic import BaseModel
from taxonomy import DecisionType

class ManagerInquiryBriefing(BaseModel):
    target_role: str
    summary_headline: str
    violated_clauses: list[str]
    detailed_findings: list[str]
    actionable_question: str
    recommended_actions: list[str]
    vlm_evidence_summary: str = ''

class SmallLLMManagerReasoner:
    @staticmethod
    def synthesize_manager_briefing(request, approval_result, vlm_result=None):
        r=approval_result
        if r.decision != DecisionType.ESCALATE: return None
        return ManagerInquiryBriefing(target_role=r.target_role.value,
            summary_headline=r.human_readable_explanation,violated_clauses=r.applied_policy_clauses,
            detailed_findings=[v.plain_reason for v in r.all_violations],
            actionable_question=r.actionable_question or '',recommended_actions=r.quick_action_options)
