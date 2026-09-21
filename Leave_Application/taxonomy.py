"""Engine decisions and routing are deterministic, never model-authored."""
from enum import Enum
from pydantic import BaseModel, Field

class DecisionType(str, Enum):
    NO_LEAVE_REQUIRED = 'NO_LEAVE_REQUIRED'
    AUTO_APPROVE = 'AUTO_APPROVE'
    AUTO_REJECT = 'AUTO_REJECT'
    NEED_CORRECTION = 'NEED_CORRECTION'
    ESCALATE = 'ESCALATE'

class UncertaintyCategory(str, Enum):
    UNCERTAIN_FACTS = 'UNCERTAIN_FACTS'
    OUT_OF_POLICY = 'OUT_OF_POLICY'
    AUTHORITY_ESCALATION = 'AUTHORITY_ESCALATION'

class TargetApproverRole(str, Enum):
    EMPLOYEE = 'EMPLOYEE'
    DIRECT_MANAGER = 'DIRECT_MANAGER'
    DEPARTMENT_HEAD = 'DEPARTMENT_HEAD'
    HR = 'HR'
    HRD = 'HRD'
    CEO = 'CEO'
    HR_OPERATIONS = 'HR'
    HR_DIRECTOR = 'HRD'
    EXECUTIVE_BOARD = 'CEO'

class ErrorCode(str, Enum):
    DATE_MISSING = 'DATE_MISSING'
    DATE_AMBIGUOUS = 'DATE_AMBIGUOUS'
    DATE_RANGE_INVALID = 'DATE_RANGE_INVALID'
    DATE_LOGIC_INVALID = 'DATE_RANGE_INVALID'
    LEAVE_TYPE_MISSING = 'LEAVE_TYPE_MISSING'
    REASON_REQUIRED = 'REASON_REQUIRED'
    RELATIONSHIP_UNCLEAR = 'RELATIONSHIP_UNCLEAR'
    PROOF_MISSING = 'PROOF_MISSING'
    DOC_ILLEGIBLE = 'DOC_ILLEGIBLE'
    DOC_FIELD_MISSING = 'DOC_FIELD_MISSING'
    MEDICAL_DAYS_MISMATCH = 'MEDICAL_DAYS_MISMATCH'
    BALANCE_EXCEEDED = 'BALANCE_EXCEEDED'
    NOTICE_PERIOD_VIOLATED = 'NOTICE_PERIOD_VIOLATED'
    TEAM_QUOTA_EXCEEDED = 'TEAM_QUOTA_EXCEEDED'
    HANDOVER_REQUIRED = 'HANDOVER_REQUIRED'
    HANDOVER_INVALID = 'HANDOVER_INVALID'
    DURATION_OVER_AI_LIMIT = 'DURATION_OVER_AI_LIMIT'
    DURATION_OVER_MANAGER_LIMIT = 'DURATION_OVER_MANAGER_LIMIT'
    LONG_TERM_UNPAID = 'LONG_TERM_UNPAID'
    DAY_ALREADY_NON_WORKING = 'DAY_ALREADY_NON_WORKING'
    REQUEST_ALREADY_COVERED = 'REQUEST_ALREADY_COVERED'
    OVERLAPPING_REQUEST = 'OVERLAPPING_REQUEST'
    AUTOMATION_SCOPE_UNSUPPORTED = 'AUTOMATION_SCOPE_UNSUPPORTED'
    LEGAL_REVIEW_REQUIRED = 'LEGAL_REVIEW_REQUIRED'
    ENTITLEMENT_EXCEEDED = 'ENTITLEMENT_EXCEEDED'
    PROBATION_ANNUAL_RESTRICTED = 'PROBATION_ANNUAL_RESTRICTED'
    PROOF_REVIEW_REQUIRED = 'PROOF_REVIEW_REQUIRED'
    NAME_MISMATCH = 'NAME_MISMATCH'
    DOC_SUSPICIOUS = 'DOC_SUSPICIOUS'
    HANDOVER_CIRCULAR_LOOP = 'HANDOVER_INVALID'
    SPECIAL_LEAVE_DOC_MISSING = 'PROOF_MISSING'
    UNQUALIFIED_SPECIAL_LEAVE = 'REASON_REQUIRED'
    MATERNITY_LEAVE_DOC_MISSING = 'AUTOMATION_SCOPE_UNSUPPORTED'
    MATERNITY_DAYS_EXCEEDED = 'AUTOMATION_SCOPE_UNSUPPORTED'
    MANAGER_SELF_APPROVAL = 'MANAGER_SELF_APPROVAL'
    DIAGNOSIS_MISMATCH = 'DOC_FIELD_MISSING'
    CONSECUTIVE_SPLIT_DETECTED = 'OVERLAPPING_REQUEST'
    CLUSTER_ABSENCE_ANOMALY = 'TEAM_QUOTA_EXCEEDED'
    FLAG_ABUSE_PATTERN = 'FLAG_ABUSE_PATTERN'

class EscalationDetail(BaseModel):
    category: UncertaintyCategory | None = None
    error_code: ErrorCode
    target_role: TargetApproverRole | None = None
    actionable_question: str = ''
    plain_reason: str
    clause: str = ''
    severity: str = 'BLOCKING'

class ApprovalResult(BaseModel):
    decision: DecisionType
    target_role: TargetApproverRole | None = None
    uncertainty_category: UncertaintyCategory | None = None
    error_code: ErrorCode | None = None
    requested_calendar_days: int | None = None
    requested_working_days: int | None = None
    working_dates: list[str] = Field(default_factory=list)
    deducted_days: float = 0
    annual_balance_change: float = 0
    paid: bool | None = None
    approval_roles: list[TargetApproverRole] = Field(default_factory=list)
    human_readable_explanation: str = ''
    actionable_question: str | None = None
    quick_action_options: list[str] = Field(default_factory=list)
    escalation: EscalationDetail | None = None
    all_violations: list[EscalationDetail] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    applied_policy_clauses: list[str] = Field(default_factory=list)
    decision_trace: list[dict] = Field(default_factory=list)
    policy_version: str = '3.0.0'

# Compatibility for consumers displaying metadata; routing must use the result.
TAXONOMY_METADATA = {code: {'category': UncertaintyCategory.UNCERTAIN_FACTS,
    'default_target': TargetApproverRole.EMPLOYEE, 'description': code.value}
    for code in ErrorCode}
for code in (ErrorCode.DURATION_OVER_AI_LIMIT, ErrorCode.DURATION_OVER_MANAGER_LIMIT, ErrorCode.LONG_TERM_UNPAID):
    TAXONOMY_METADATA[code]['category'] = UncertaintyCategory.AUTHORITY_ESCALATION
for code in (ErrorCode.BALANCE_EXCEEDED, ErrorCode.NOTICE_PERIOD_VIOLATED, ErrorCode.TEAM_QUOTA_EXCEEDED,
             ErrorCode.LEGAL_REVIEW_REQUIRED, ErrorCode.AUTOMATION_SCOPE_UNSUPPORTED, ErrorCode.PROOF_REVIEW_REQUIRED,
             ErrorCode.FLAG_ABUSE_PATTERN):
    TAXONOMY_METADATA[code]['category'] = UncertaintyCategory.OUT_OF_POLICY
    if code == ErrorCode.FLAG_ABUSE_PATTERN:
        TAXONOMY_METADATA[code]['default_target'] = TargetApproverRole.DIRECT_MANAGER
