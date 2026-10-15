"""Canonical facts. Employee/LLM input never includes trusted HR or policy state."""
from datetime import date, datetime
from enum import Enum
from typing import Literal, Any
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

TEAM_ABSENCE_THRESHOLD = 0.30


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


_EVENT_RELATIONSHIPS = {
    'CHILD_MARRIAGE': ('Con của nhân viên', {'con', 'con trai', 'con gái', 'con cua nhan vien', 'child', 'son', 'daughter'}),
    'PARENT_DEATH': ('Cha/mẹ của nhân viên', {'cha', 'mẹ', 'bố', 'ba', 'cha ruột', 'mẹ ruột', 'bố ruột', 'ba ruột', 'cha đẻ', 'mẹ đẻ', 'cha/mẹ', 'cha hoặc mẹ', 'parent', 'father', 'mother'}),
    'SPOUSE_PARENT_DEATH': ('Cha/mẹ vợ hoặc chồng', {'cha vợ', 'mẹ vợ', 'bố vợ', 'mẹ vợ', 'cha chồng', 'mẹ chồng', 'bố chồng', 'mẹ chồng', 'parent in law'}),
    'SPOUSE_DEATH': ('Vợ/chồng của nhân viên', {'vợ', 'chồng', 'vợ/chồng', 'spouse', 'wife', 'husband'}),
    'CHILD_DEATH': ('Con của nhân viên', {'con', 'con trai', 'con gái', 'con cua nhan vien', 'child', 'son', 'daughter'}),
    'GRANDPARENT_DEATH': ('Ông/bà của nhân viên', {'ông', 'bà', 'ông nội', 'bà nội', 'ông ngoại', 'bà ngoại', 'grandparent'}),
    'SIBLING_DEATH': ('Anh/chị/em ruột của nhân viên', {'anh', 'chị', 'em', 'anh trai', 'chị gái', 'em trai', 'em gái', 'anh/chị/em ruột', 'sibling', 'brother', 'sister'}),
    'PARENT_MARRIAGE': ('Cha/mẹ của nhân viên', {'cha', 'mẹ', 'bố', 'ba', 'cha ruột', 'mẹ ruột', 'bố ruột', 'ba ruột', 'cha đẻ', 'mẹ đẻ', 'cha/mẹ', 'cha hoặc mẹ', 'parent', 'father', 'mother'}),
    'SIBLING_MARRIAGE': ('Anh/chị/em ruột của nhân viên', {'anh', 'chị', 'em', 'anh trai', 'chị gái', 'em trai', 'em gái', 'anh/chị/em ruột', 'sibling', 'brother', 'sister'}),
}


def assess_event_relationship(reason_category, document_relationship: str | None) -> dict | None:
    """Compare the relationship declared for a family event with what the proof states."""
    category = getattr(reason_category, 'value', reason_category)
    config = _EVENT_RELATIONSHIPS.get(str(category or '').upper())
    if not config:
        return None

    label, aliases = config
    relation = str(document_relationship or '').strip()
    if not relation:
        status = 'UNVERIFIED'
    else:
        cleaned = re.sub(r'\s*\((?:Đã xác minh|Xác minh|Chưa xác minh|Mâu thuẫn|Conflict|Verified|Unverified)\)\s*', '', relation, flags=re.IGNORECASE)
        normalized = re.sub(r'\s+', ' ', ''.join(
            char for char in unicodedata.normalize('NFD', cleaned.casefold())
            if unicodedata.category(char) != 'Mn'
        )).strip()
        normalized_aliases = {
            re.sub(r'\s+', ' ', ''.join(
                char for char in unicodedata.normalize('NFD', alias.casefold())
                if unicodedata.category(char) != 'Mn'
            )).strip()
            for alias in aliases
        }
        status = 'VERIFIED' if normalized in normalized_aliases else 'CONFLICT'

    return {
        'declared_relationship': label,
        'document_relationship': relation or None,
        'status': status,
    }


def relationship_display_label(reason_category, document_relationship: str | None) -> str:
    """Render a stable display label with an explicit verification status for relationship-based leave."""
    assessment = assess_event_relationship(reason_category, document_relationship)
    if not assessment:
        relation = str(document_relationship or '').strip()
        return relation or ''

    label = assessment['declared_relationship']
    status = assessment['status']
    if status == 'VERIFIED':
        return f'{label} (Đã xác minh)'
    if status == 'CONFLICT':
        return f'{label} (Mâu thuẫn)'
    return f'{label} (Chưa xác minh)'


def _name_tokens(value: str) -> list[str]:
    value = unicodedata.normalize('NFD', str(value or '').casefold())
    value = ''.join(char for char in value if unicodedata.category(char) != 'Mn')
    tokens = re.findall(r'[a-z0-9]+', value)
    # Chỉ bỏ danh xưng ở ĐẦU tên ("Ông Lê Văn Nam"); "Anh", "Em"... ở cuối là tên gọi thật ("Trần Quốc Anh").
    titles = {'ong', 'ba', 'co', 'chu', 'anh', 'chi', 'em', 'mr', 'mrs', 'ms', 'bs', 'dr'}
    while len(tokens) > 2 and tokens[0] in titles:
        tokens = tokens[1:]
    return tokens


def names_approximately_match(left: str | None, right: str | None) -> bool:
    """Chấp nhận khác biệt vô hại (danh xưng, dấu, thiếu tên đệm, lỗi chính tả nhỏ ở từ dài) nhưng HỌ và TÊN
    phải cùng khớp. Không coi là cùng một người chỉ vì trùng tên gọi ("Nguyễn Văn An" ≠ "Trần Thị An")
    hoặc trùng một từ ("Person 999" ≠ "Person 000")."""
    from difflib import SequenceMatcher

    left_tokens, right_tokens = _name_tokens(left), _name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False  # chỉ có một từ (vd chỉ tên gọi) thì không đủ căn cứ nhận diện

    def close(a: str, b: str) -> bool:
        # Lỗi chính tả chỉ được bỏ qua với từ đủ dài; từ ngắn / số phải trùng tuyệt đối.
        return a == b or (len(a) >= 4 and len(b) >= 4 and not (a.isdigit() or b.isdigit())
                          and SequenceMatcher(None, a, b).ratio() >= 0.85)

    if not (close(left_tokens[0], right_tokens[0]) and close(left_tokens[-1], right_tokens[-1])):
        return False
    shorter, longer = sorted((left_tokens, right_tokens), key=len)
    # Tên đệm có thể bị lược, nhưng tên đệm nào có mặt thì phải khớp với tên đệm bên kia.
    return all(any(close(t, u) for u in longer[1:-1]) for t in shorter[1:-1])

class ProofType(str, Enum):
    MEDICAL_LEAVE_CERTIFICATE = 'MEDICAL_LEAVE_CERTIFICATE'
    HOSPITAL_DISCHARGE = 'HOSPITAL_DISCHARGE'
    MEDICAL_RECORD_SUMMARY = 'MEDICAL_RECORD_SUMMARY'
    INJURY_CERTIFICATE = 'INJURY_CERTIFICATE'
    MARRIAGE_CERTIFICATE = 'MARRIAGE_CERTIFICATE'
    WEDDING_INVITATION = 'WEDDING_INVITATION'
    DEATH_CERTIFICATE = 'DEATH_CERTIFICATE'
    ACCIDENT_REPORT = 'ACCIDENT_REPORT'
    ACCIDENT_CERTIFICATE = 'ACCIDENT_CERTIFICATE'
    LAB_RESULT = 'LAB_RESULT'
    MATERNITY_CERTIFICATE = 'MATERNITY_CERTIFICATE'
    FUNERAL_DECISION = 'FUNERAL_DECISION'
    FAMILY_EVENT_LETTER = 'FAMILY_EVENT_LETTER'
    IDENTITY_CARD = 'IDENTITY_CARD'
    VISA_OR_TRAVEL_DOC = 'VISA_OR_TRAVEL_DOC'
    OTHER_ADMINISTRATIVE = 'OTHER_ADMINISTRATIVE'
    EMERGENCY_ADMISSION = 'EMERGENCY_ADMISSION'
    SURGERY_NOTICE = 'SURGERY_NOTICE'
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

    # Extended fields for persona-specific extraction
    is_open_ended: bool | None = None
    requires_followup_proof: bool | None = None
    admission_date: date | None = None
    discharge_date: date | None = None
    doc_diagnosis: str | None = None
    emergency_diagnosis: str | None = None
    patient_name_match: Literal['MATCH', 'MISMATCH', 'UNCERTAIN', 'NOT_APPLICABLE'] | None = None
    patient_name_match_reason: str | None = None
    reason_diagnosis_match: Literal['MATCH', 'PARTIAL', 'MISMATCH', 'UNCERTAIN', 'NOT_APPLICABLE'] | None = None
    reason_diagnosis_match_reason: str | None = None
    days_granted_by_doctor: int | None = None
    deceased_name: str | None = None
    subject_name: str | None = None
    partner_name: str | None = None
    event_type: str | None = None
    wedding_date: date | None = None
    date_of_death: date | None = None
    funeral_date: date | None = None
    relationship_label: str | None = None
    relationship_to_employee: str | None = None
    evidence_confidence: str | None = None
    needs_manager_review: bool | None = None
    maternity_phase: str | None = None
    expected_due_date: date | None = None
    bhxh_code: str | None = None
    injury_description: str | None = None
    is_workplace_related: bool | None = None
    injury_date: date | None = None
    has_red_stamp: bool | None = None
    has_doctor_signature: bool | None = None
    is_tampered: bool | None = None
    ai_edited: bool | None = None
    has_hospital_stamp: bool | None = None
    has_bhxh_stamp: bool | None = None
    document_purpose: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None

    @field_validator('proof_type', mode='before')
    @classmethod
    def coerce_proof_type(cls, v: Any) -> Any:
        if isinstance(v, ProofType):
            return v
        if not v:
            return ProofType.NONE
        s = str(v).strip().upper()
        try:
            return ProofType(s)
        except ValueError:
            pass
        ALIAS_MAP = {
            "EMERGENCY_ADMISSION": ProofType.EMERGENCY_ADMISSION,
            "EMERGENCY": ProofType.EMERGENCY_ADMISSION,
            "SURGERY_NOTICE": ProofType.SURGERY_NOTICE,
            "SURGERY": ProofType.SURGERY_NOTICE,
            "ACCIDENT_CERTIFICATE": ProofType.ACCIDENT_CERTIFICATE,
            "ACCIDENT": ProofType.ACCIDENT_REPORT,
            "INJURY": ProofType.INJURY_CERTIFICATE,
            "LAB_RESULT": ProofType.LAB_RESULT,
            "MATERNITY_CERTIFICATE": ProofType.MATERNITY_CERTIFICATE,
            "MATERNITY": ProofType.MATERNITY_CERTIFICATE,
            "FUNERAL_DECISION": ProofType.FUNERAL_DECISION,
            "FUNERAL": ProofType.FUNERAL_DECISION,
            "FAMILY_EVENT_LETTER": ProofType.FAMILY_EVENT_LETTER,
            "FAMILY_EVENT": ProofType.FAMILY_EVENT_LETTER,
            "IDENTITY_CARD": ProofType.IDENTITY_CARD,
            "VISA_OR_TRAVEL_DOC": ProofType.VISA_OR_TRAVEL_DOC,
            "OTHER_ADMINISTRATIVE": ProofType.OTHER_ADMINISTRATIVE,
            "WEDDING": ProofType.WEDDING_INVITATION,
            "MARRIAGE": ProofType.MARRIAGE_CERTIFICATE,
            "DEATH": ProofType.DEATH_CERTIFICATE,
            "HOSPITAL": ProofType.HOSPITAL_DISCHARGE,
            "MEDICAL": ProofType.MEDICAL_LEAVE_CERTIFICATE,
        }
        if s in ALIAS_MAP:
            return ALIAS_MAP[s]
        for k, target in ALIAS_MAP.items():
            if k in s:
                return target
        return ProofType.OTHER

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
    no_handover_needed: bool = False  # Bypass: nhân viên xác nhận không có việc cần bàn giao.
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
    no_handover_needed: bool | None = None

class HumanFeedbackResolution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['APPROVE_OVERRIDE', 'REJECT', 'MODIFY_CONDITIONAL', 'REQUEST_MORE_INFO']
    updated_fields: EditableFields = Field(default_factory=EditableFields)
    feedback_notes: str = ''
    override_reason: str | None = None
