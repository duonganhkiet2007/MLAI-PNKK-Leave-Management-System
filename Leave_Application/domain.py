"""Canonical facts. Employee/LLM input never includes trusted HR or policy state."""
from datetime import date, datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re
import unicodedata

class LeaveType(str, Enum):
    ANNUAL = 'ANNUAL'
    SPECIAL_PAID = 'SPECIAL_PAID'
    STATUTORY_UNPAID = 'STATUTORY_UNPAID'
    UNPAID_OTHER = 'UNPAID_OTHER'
    SICK_MEDICAL = 'SICK_MEDICAL'
    MEDICAL_EMERGENCY = 'MEDICAL_EMERGENCY'
    WORK_ACCIDENT = 'WORK_ACCIDENT'
    MATERNITY = 'MATERNITY'


# Display metadata is derived from policy_rules.md and is returned with every
# serialized request so employee and manager views use the same classification.
LEAVE_POLICY_METADATA = {
    'ANNUAL': {
        'tag': 'Phép năm (Annual Leave)',
        'pay_type': 'Hưởng nguyên lương',
        'payer': 'Doanh nghiệp',
        'annual_balance': 'Có',
    },
    'SPECIAL_PAID': {
        'tag': 'Nghỉ chế độ (Marriage/Bereavement)',
        'pay_type': 'Hưởng nguyên lương',
        'payer': 'Doanh nghiệp',
        'annual_balance': 'Không',
    },
    'SICK_MEDICAL': {
        'tag': 'Nghỉ BHXH (Sick Leave)',
        'pay_type': 'Hưởng trợ cấp BHXH',
        'payer': 'Quỹ BHXH',
        'annual_balance': 'Không',
    },
    'MEDICAL_EMERGENCY': {
        'tag': 'Nghỉ BHXH (Sick Leave)',
        'pay_type': 'Hưởng trợ cấp BHXH',
        'payer': 'Quỹ BHXH',
        'annual_balance': 'Không',
    },
    'WORK_ACCIDENT': {
        'tag': 'Nghỉ BHXH (Work Accident)',
        'pay_type': 'Hưởng trợ cấp BHXH',
        'payer': 'Quỹ BHXH / Quỹ TNLĐ-BNN',
        'annual_balance': 'Không',
    },
    'MATERNITY': {
        'tag': 'Nghỉ BHXH (Maternity Leave)',
        'pay_type': 'Hưởng trợ cấp BHXH',
        'payer': 'Quỹ BHXH',
        'annual_balance': 'Không',
    },
    'STATUTORY_UNPAID': {
        'tag': 'Nghỉ không lương (Statutory Unpaid Leave)',
        'pay_type': 'Không hưởng lương',
        'payer': '—',
        'annual_balance': 'Không',
    },
    'UNPAID_OTHER': {
        'tag': 'Nghỉ không lương (Unpaid Leave)',
        'pay_type': 'Không hưởng lương',
        'payer': '—',
        'annual_balance': 'Không',
    },
}


def leave_policy_metadata(leave_type):
    if isinstance(leave_type, Enum):
        leave_type = leave_type.value
    normalized = str(leave_type or '').upper()
    metadata = LEAVE_POLICY_METADATA.get(normalized)
    if metadata is None:
        return {
            'tag': 'Chưa phân loại theo policy',
            'pay_type': 'Chưa xác định',
            'payer': 'Chưa xác định',
            'annual_balance': 'Chưa xác định',
            'status': 'UNMAPPED',
        }
    return {**metadata, 'status': 'MAPPED'}

class ReasonCategory(str, Enum):
    PERSONAL = 'PERSONAL'
    SELF_MARRIAGE = 'SELF_MARRIAGE'
    CHILD_MARRIAGE = 'CHILD_MARRIAGE'
    PARENT_DEATH = 'PARENT_DEATH'
    SPOUSE_PARENT_DEATH = 'SPOUSE_PARENT_DEATH'
    SPOUSE_DEATH = 'SPOUSE_DEATH'
    CHILD_DEATH = 'CHILD_DEATH'
    OTHER_STATUTORY_BEREAVEMENT = 'OTHER_STATUTORY_BEREAVEMENT'
    GRANDPARENT_DEATH = 'GRANDPARENT_DEATH'
    SIBLING_DEATH = 'SIBLING_DEATH'
    PARENT_MARRIAGE = 'PARENT_MARRIAGE'
    SIBLING_MARRIAGE = 'SIBLING_MARRIAGE'


def _name_tokens(value: str) -> list[str]:
    value = unicodedata.normalize('NFD', str(value or '').casefold())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    value = re.sub(r'\b(ong|ba|co|chu|anh|chi|em|mr|mrs|ms)\b', ' ', value)
    return re.findall(r'[a-z0-9]+', value)


def names_approximately_match(left: str | None, right: str | None) -> bool:
    """Accept harmless title, accent, token and small spelling differences."""
    from difflib import SequenceMatcher

    left_tokens, right_tokens = _name_tokens(left), _name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens or left_tokens[-1] == right_tokens[-1]:
        return True
    if left_tokens[-1] in right_tokens or right_tokens[-1] in left_tokens:
        return True
    return any(SequenceMatcher(None, left_token, right_token).ratio() >= 0.82
               for left_token in left_tokens for right_token in right_tokens)

class ProofType(str, Enum):
    MEDICAL_LEAVE_CERTIFICATE = 'MEDICAL_LEAVE_CERTIFICATE'
    HOSPITAL_DISCHARGE = 'HOSPITAL_DISCHARGE'
    MEDICAL_RECORD_SUMMARY = 'MEDICAL_RECORD_SUMMARY'
    INJURY_CERTIFICATE = 'INJURY_CERTIFICATE'
    MARRIAGE_CERTIFICATE = 'MARRIAGE_CERTIFICATE'
    WEDDING_INVITATION = 'WEDDING_INVITATION'
    DEATH_CERTIFICATE = 'DEATH_CERTIFICATE'
    ACCIDENT_REPORT = 'ACCIDENT_REPORT'
    OTHER = 'OTHER'
    NONE = 'NONE'

class ProofExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    proof_type: ProofType = ProofType.NONE
    issuer: str | None = None
    patient_name: str | None = None
    issue_date: date | None = None
    recommended_from_date: date | None = None
    recommended_to_date: date | None = None
    signature_present: bool | None = None
    digital_signature_present: bool | None = None
    document_readability: Literal['READABLE', 'UNREADABLE', 'ILLEGIBLE', 'PARTIAL', 'UNKNOWN'] = 'UNKNOWN'
    fields_detected: list[str] = Field(default_factory=list)

class VerifiedProof(ProofExtraction):
    """Only server-side HR verification may construct a trusted verification result."""
    proof_verification_status: Literal['UNVERIFIED', 'VERIFIED', 'REJECTED', 'NEEDS_HR_REVIEW'] = 'UNVERIFIED'
    verification_notes: str | None = None
    verified_by: str | None = None

ALIASES = {
    'annual': ('ANNUAL', None), 'nghỉ phép năm': ('ANNUAL', None),
    'sick': ('SICK_MEDICAL', None), 'unpaid': ('UNPAID_OTHER', None),
    'special': ('SPECIAL_PAID', None),
    'special_wedding': ('SPECIAL_PAID', 'SELF_MARRIAGE'),
    'special_child_wedding': ('SPECIAL_PAID', 'CHILD_MARRIAGE'),
    'ket hon': ('SPECIAL_PAID', 'SELF_MARRIAGE'), 'kết hôn': ('SPECIAL_PAID', 'SELF_MARRIAGE'),
    'con cuoi': ('SPECIAL_PAID', 'CHILD_MARRIAGE'), 'con cưới': ('SPECIAL_PAID', 'CHILD_MARRIAGE'),
    'tang me': ('SPECIAL_PAID', 'PARENT_DEATH'), 'tang cha': ('SPECIAL_PAID', 'PARENT_DEATH'),
    'tang mẹ': ('SPECIAL_PAID', 'PARENT_DEATH'), 'tang cha': ('SPECIAL_PAID', 'PARENT_DEATH'),
    'bố mất': ('SPECIAL_PAID', 'PARENT_DEATH'), 'mẹ mất': ('SPECIAL_PAID', 'PARENT_DEATH'),
    'cha mất': ('SPECIAL_PAID', 'PARENT_DEATH'), 'mẹ mất': ('SPECIAL_PAID', 'PARENT_DEATH'),
    'tang vo chong': ('SPECIAL_PAID', 'SPOUSE_DEATH'),
    'vợ mất': ('SPECIAL_PAID', 'SPOUSE_DEATH'), 'chồng mất': ('SPECIAL_PAID', 'SPOUSE_DEATH'),
    'con mất': ('SPECIAL_PAID', 'CHILD_DEATH'),
    # Ambiguous relationships stay unspecified until the employee supplies them.
    'special_funeral_direct': ('SPECIAL_PAID', None),
    'special_funeral_extended': ('STATUTORY_UNPAID', None),
    # Cha mẹ vợ / chồng chết → PAID 3 ngày (Điều 115 BLLĐ 2019 khoản 1: trực hệ vợ chồng)
    'bo vo mat': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'), 'me vo mat': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'),
    'bo chong mat': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'), 'me chong mat': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'),
    'bố vợ mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'), 'mẹ vợ mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'),
    'bố chồng mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'), 'mẹ chồng mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'),
    'cha vợ mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'), 'mẹ vợ mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'),
    'cha chồng mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'), 'mẹ chồng mất': ('SPECIAL_PAID', 'SPOUSE_PARENT_DEATH'),
    # Ông bà mất → UNPAID 1 ngày (Điều 115 khoản 2)
    'ong noi mat': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'), 'ba noi mat': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'),
    'ông nội mất': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'), 'bà nội mất': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'),
    'ong ngoai mat': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'), 'ba ngoai mat': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'),
    'ông ngoại mất': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'), 'bà ngoại mất': ('STATUTORY_UNPAID', 'GRANDPARENT_DEATH'),
    # Anh chị em mất → UNPAID 1 ngày (Điều 115 khoản 2)
    'anh mat': ('STATUTORY_UNPAID', 'SIBLING_DEATH'), 'chi mat': ('STATUTORY_UNPAID', 'SIBLING_DEATH'),
    'em mat': ('STATUTORY_UNPAID', 'SIBLING_DEATH'),
    'anh mất': ('STATUTORY_UNPAID', 'SIBLING_DEATH'), 'chị mất': ('STATUTORY_UNPAID', 'SIBLING_DEATH'),
    'em mất': ('STATUTORY_UNPAID', 'SIBLING_DEATH'),
    # Cha mẹ kết hôn tái hôn / anh chị em kết hôn → UNPAID 1 ngày
    'bo ket hon': ('STATUTORY_UNPAID', 'PARENT_MARRIAGE'), 'me ket hon': ('STATUTORY_UNPAID', 'PARENT_MARRIAGE'),
    'cha kết hôn': ('STATUTORY_UNPAID', 'PARENT_MARRIAGE'), 'mẹ kết hôn': ('STATUTORY_UNPAID', 'PARENT_MARRIAGE'),
    'anh cuoi': ('STATUTORY_UNPAID', 'SIBLING_MARRIAGE'), 'chi cuoi': ('STATUTORY_UNPAID', 'SIBLING_MARRIAGE'),
    'anh cưới': ('STATUTORY_UNPAID', 'SIBLING_MARRIAGE'), 'chị cưới': ('STATUTORY_UNPAID', 'SIBLING_MARRIAGE'),
    'em cuoi': ('STATUTORY_UNPAID', 'SIBLING_MARRIAGE'),
    'em cưới': ('STATUTORY_UNPAID', 'SIBLING_MARRIAGE'),
    'maternity_male': ('MATERNITY', None),
}

def canonical_leave_type(value):
    if isinstance(value, Enum): value = value.value
    if not value: return None
    return ALIASES.get(str(value).lower(), (str(value).upper(), None))[0]

def should_deduct_annual_balance(leave_type) -> bool:
    return canonical_leave_type(leave_type) == LeaveType.ANNUAL.value

class RequestFacts(BaseModel):
    model_config = ConfigDict(extra='forbid')
    from_date: str | None = None
    to_date: str | None = None
    leave_type: str | None = None
    reason_category: ReasonCategory | None = None
    reason: str = ''
    handover_person_id: str | None = None
    handover_person_name: str | None = None
    proof_id: str | None = None
    attachment_type: str = 'none'  # Legacy claim only; never proof verification.
    date_ambiguous: bool = False

    @field_validator('from_date', 'to_date', mode='before')
    @classmethod
    def date_string(cls, v):
        return v.isoformat() if isinstance(v, date) else (v or None)

    @model_validator(mode='before')
    @classmethod
    def aliases(cls, data):
        if not isinstance(data, dict): return data
        data = dict(data)
        raw = data.get('leave_type')
        if raw:
            raw = raw.value if isinstance(raw, Enum) else str(raw)
            value, category = ALIASES.get(raw.lower(), (raw.upper(), None))
            data['leave_type'] = value
            if category and not data.get('reason_category'): data['reason_category'] = category
        if data.get('leave_type') == 'ANNUAL': data['reason_category'] = 'PERSONAL'
        for key in ('reason', 'attachment_type'):
            if data.get(key) is None: data[key] = '' if key == 'reason' else 'none'
        return data

class EditableFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    from_date: date | None = None
    to_date: date | None = None
    handover_person_id: str | None = None
    handover_person_name: str | None = None

class HumanFeedbackResolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['APPROVE_OVERRIDE', 'REJECT', 'MODIFY_CONDITIONAL', 'REQUEST_MORE_INFO']
    updated_fields: EditableFields = Field(default_factory=EditableFields)
    feedback_notes: str = ''
    override_reason: str | None = None
