"""Deterministic leave evaluation. Caller supplies authoritative DB context only."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import Field
from domain import (RequestFacts, VerifiedProof, LeaveType,
                    names_approximately_match, should_deduct_annual_balance,
                    TEAM_ABSENCE_THRESHOLD, assess_event_relationship)
from calendar_service import CalendarService, CalendarUnavailable, calculate_workdays
from taxonomy import (DecisionType as D, UncertaintyCategory as C, TargetApproverRole as R,
                      ErrorCode as E, EscalationDetail, ApprovalResult)

class LeaveRequest(RequestFacts):
    request_id: str = 'VERIFY'
    employee_id: str
    employee_name: str
    department: str
    remaining_leave_days: float = Field(ge=0, allow_inf_nan=False)
    submitted_at: datetime
    employment_status: str | None = None
    employment_start_date: date | None = None
    probation_start_date: date | None = None
    probation_end_date: date | None = None
    total_team_members: int = Field(default=1, ge=1)
    team_absent_count: int = Field(default=0, ge=0)
    team_absences_by_date: dict[str, int] = Field(default_factory=dict)
    handover: dict | None = None
    approved_working_dates: list[str] = Field(default_factory=list)
    proof: VerifiedProof = Field(default_factory=VerifiedProof)
    granted_roles: list[R] = Field(default_factory=list)
    waived_errors: list[E] = Field(default_factory=list)
    calendar_review_required: bool = False
    has_abuse_pattern: bool = False

PAID_ENTITLEMENTS = {'SELF_MARRIAGE': 3, 'CHILD_MARRIAGE': 1,
                     'PARENT_DEATH': 3, 'SPOUSE_PARENT_DEATH': 3, 'SPOUSE_DEATH': 3, 'CHILD_DEATH': 3}
UNPAID_ENTITLEMENTS = dict.fromkeys(['GRANDPARENT_DEATH','SIBLING_DEATH','PARENT_MARRIAGE','SIBLING_MARRIAGE'], 1)
MEDICAL = {'SICK_MEDICAL', 'MEDICAL_EMERGENCY'}
OPERATIONAL = {'ANNUAL', 'UNPAID_OTHER'}
NO_PROOF_REQUIRED = {'ANNUAL', 'UNPAID_OTHER', 'STATUTORY_UNPAID'}
PROOF_REQUIRED = MEDICAL | {'SPECIAL_PAID'}
MEDICAL_PROOFS = {'MEDICAL_LEAVE_CERTIFICATE','HOSPITAL_DISCHARGE','MEDICAL_RECORD_SUMMARY','INJURY_CERTIFICATE','ACCIDENT_REPORT','ACCIDENT_CERTIFICATE','LAB_RESULT','MATERNITY_CERTIFICATE','EMERGENCY_ADMISSION','SURGERY_NOTICE'}
MATERNITY_CHECKUP_PROOFS = {'MEDICAL_LEAVE_CERTIFICATE', 'MATERNITY_CERTIFICATE'}
STATUTORY_PARENT_LOSS = {'PARENT_DEATH', 'SPOUSE_PARENT_DEATH'}
RULE_STAGES = ['INPUT_DATES','CALENDAR','ENTITLEMENT','INPUT_COMPLETENESS','PROOF',
               'WORKING_DAYS','OVERLAP','BALANCE','NOTICE','TEAM_CAPACITY','HANDOVER','AUTHORITY','FINAL']


def _is_maternity_checkup(request, workdays):
    phase = str(request.proof.maternity_phase or '').strip().upper()
    reason = (request.reason or '').casefold()
    return (
        request.leave_type == 'MATERNITY'
        and workdays == 1
        and (phase == 'PREGNANCY_CHECKUP' or 'khám thai' in reason or 'kham thai' in reason or 'pregnancy checkup' in reason)
    )


def _maternity_checkup_proof_issue(request, dates):
    proof = request.proof
    proof_type = getattr(proof.proof_type, 'value', proof.proof_type)
    phase = str(proof.maternity_phase or '').strip().upper()
    if proof_type not in MATERNITY_CHECKUP_PROOFS:
        return 'Chứng từ không phải giấy khám thai hoặc giấy chứng nhận nghỉ thai sản phù hợp'
    if phase and phase not in {'PRENATAL', 'PREGNANCY_CHECKUP'}:
        return 'Chưa xác định được giai đoạn khám thai trên chứng từ'
    patient_name = proof.patient_name or proof.subject_name
    if not patient_name:
        return 'Chứng từ chưa có tên người khám'
    if proof.patient_name_match not in (None, 'MATCH'):
        return 'Tên người khám trên chứng từ chưa được xác minh khớp với nhân sự'
    if not names_approximately_match(patient_name, request.employee_name):
        return 'Tên người khám trên chứng từ không khớp với nhân sự'
    if not proof.issuer or not proof.issue_date:
        return 'Chứng từ thiếu nơi cấp hoặc ngày cấp'
    if proof.document_readability != 'READABLE':
        return 'Chứng từ chưa đủ rõ để đối chiếu'
    if not (proof.signature_present or proof.digital_signature_present or proof.has_doctor_signature):
        return 'Chứng từ chưa có chữ ký xác nhận của cơ sở y tế'
    if not proof.recommended_from_date or not proof.recommended_to_date:
        return 'Chứng từ chưa thể hiện ngày khám hoặc thời gian được chỉ định'
    if proof.recommended_from_date > proof.recommended_to_date or any(
        not proof.recommended_from_date <= day <= proof.recommended_to_date for day in dates
    ):
        return 'Ngày nghỉ không khớp với thời gian ghi trên chứng từ'
    if proof.proof_verification_status in {'REJECTED', 'NEEDS_HR_REVIEW'}:
        return 'Chứng từ cần được xác minh thêm trước khi duyệt'
    if proof.needs_manager_review or proof.is_tampered is True or proof.ai_edited is True:
        return 'Chứng từ có dấu hiệu cần được kiểm tra thủ công'
    return None


def _relationship_verification_status(proof, reason_category=None) -> str:
    relationship = (
        getattr(proof, 'relationship_label', None)
        or getattr(proof, 'relationship', None)
        or getattr(proof, 'relationship_to_employee', None)
    )
    normalized = str(relationship or '').strip()
    if not normalized:
        return 'UNVERIFIED'
    lowered = normalized.lower()
    if 'mâu thuẫn' in lowered or 'conflict' in lowered or 'không khớp' in lowered:
        return 'CONFLICT'
    if 'chưa xác minh' in lowered or 'chưa rõ' in lowered or 'unverified' in lowered or 'not verified' in lowered:
        return 'UNVERIFIED'
    if 'đã xác minh' in lowered or 'verified' in lowered or 'xác minh' in lowered:
        return 'VERIFIED'
    assessment = assess_event_relationship(reason_category, normalized)
    if assessment:
        return assessment['status']
    return 'VERIFIED' if any(word in lowered for word in ['cha', 'mẹ', 'bố', 'vợ', 'chồng', 'con', 'ông', 'bà', 'anh', 'chị', 'em']) else 'UNVERIFIED'


def _family_event_auto_eligible(request, proof, dates):
    if request.leave_type != 'SPECIAL_PAID':
        return False
    rel_status = _relationship_verification_status(proof, request.reason_category)
    if rel_status != 'VERIFIED':
        return False
    category = getattr(request.reason_category, 'value', request.reason_category)
    allowed = {'PARENT_DEATH', 'SPOUSE_PARENT_DEATH', 'SPOUSE_DEATH', 'CHILD_DEATH'}
    if category not in allowed:
        return False
    if not (proof.subject_name or proof.deceased_name or proof.event_type):
        return False
    event_dates = (proof.date_of_death, proof.funeral_date)
    if not any(event_dates):
        return False
    if proof.document_readability != 'READABLE':
        return False
    # Chữ ký / dấu đỏ chưa xác minh được (None) thì không tự duyệt — chuyển người duyệt đối chiếu.
    if proof.signature_present is None or proof.has_red_stamp is None:
        return False
    try:
        requested_start = date.fromisoformat(request.from_date)
        requested_end = date.fromisoformat(request.to_date)
        for event_date in event_dates:
            if event_date is not None:
                event_day = event_date if isinstance(event_date, date) else date.fromisoformat(str(event_date))
                if not requested_start <= event_day <= requested_end:
                    return False
    except (TypeError, ValueError):
        return False
    return True


class LeaveRuleEngine:
    @staticmethod
    def evaluate(request: LeaveRequest, calendar=None) -> ApprovalResult:
        cal = calendar or CalendarService()
        q = request
        result = ApprovalResult(decision=D.AUTO_APPROVE)
        findings = []
        def trace(stage, status='PASS', detail=''):
            result.decision_trace.append({'node':stage, 'status':status, 'desc':detail})
        def finish(decision, error=None, message='', category=None, target=None, clause='SYS-STATE', roles=None):
            result.decision = decision
            result.error_code = error
            result.target_role = target
            result.uncertainty_category = category
            result.approval_roles = roles or []
            result.human_readable_explanation = message
            result.applied_policy_clauses = list(dict.fromkeys(result.applied_policy_clauses + [clause]))
            if error:
                detail = EscalationDetail(error_code=error, category=category, target_role=target,
                    plain_reason=message, clause=clause)
                if decision == D.ESCALATE:
                    detail.actionable_question = (f'{q.employee_name} xin nghỉ {result.requested_working_days if result.requested_working_days is not None else "chưa xác định"} ngày làm việc '
                        f'từ {q.from_date} đến {q.to_date}. {message} '
                        + ('HR vui lòng xác minh hồ sơ/cấu hình; không thể duyệt bỏ qua điều kiện này.'
                           if target == R.HR else 'Bạn có phê duyệt trong phạm vi thẩm quyền không?'))
                    result.escalation = detail
                    result.actionable_question = detail.actionable_question
                    result.quick_action_options = ['REQUEST_MORE_INFO', 'REJECT'] if target == R.HR else ['APPROVE','REJECT','REQUEST_MORE_INFO']
                findings.append(detail)
            result.all_violations = findings
            trace('FINAL', decision.value, message)
            if decision == D.AUTO_APPROVE and should_deduct_annual_balance(q.leave_type):
                result.deducted_days = result.requested_working_days or 0
                result.annual_balance_change = -result.deducted_days
            return result
        def correction(error, message, clause='SYS-INPUT'):
            return finish(D.NEED_CORRECTION,error,message,C.UNCERTAIN_FACTS,R.EMPLOYEE,clause)
        if q.date_ambiguous: return correction(E.DATE_AMBIGUOUS,'[Chưa rõ ngày nghỉ] Đơn chưa xác định ngày cụ thể theo lịch làm việc. Vui lòng chọn ngày bắt đầu và kết thúc chính xác.')
        if not q.from_date or not q.to_date: return correction(E.DATE_MISSING,'[Thiếu khoảng thời gian] Đơn chưa đủ ngày bắt đầu hoặc ngày kết thúc. Vui lòng bổ sung đầy đủ cả 2 mốc thời gian để hệ thống tính số ngày làm việc.')
        try:
            start, end = date.fromisoformat(q.from_date), date.fromisoformat(q.to_date)
        except ValueError:
            return correction(E.DATE_RANGE_INVALID,'[Sai định dạng ngày] Ngày gửi lên không đúng định dạng chuẩn YYYY-MM-DD. Vui lòng chọn lại ngày trên giao diện lịch.')
        if start > end:
            return correction(E.DATE_RANGE_INVALID,f'[Khoảng ngày không hợp lệ] Ngày kết thúc ({end}) đang đứng trước ngày bắt đầu ({start}). Vui lòng điều chỉnh để ngày kết thúc bằng hoặc sau ngày bắt đầu.')
        if (end-start).days > 3660:
            return correction(E.DATE_RANGE_INVALID,'[Khoảng nghỉ quá dài] Đơn xin nghỉ vượt quá giới hạn tối đa 10 năm theo quy chế hệ thống. Vui lòng kiểm tra lại khoảng ngày.')
        trace('INPUT_DATES')
        result.requested_calendar_days = (end-start).days + 1
        try:
            if q.calendar_review_required: raise CalendarUnavailable('[Lịch công tác chưa đồng bộ] Lịch làm việc cá nhân có yếu tố đặc thù cần HR xác nhận. Đơn chuyển tới HR đối soát.')
            dates = cal.working_dates(start,end)
        except CalendarUnavailable as exc:
            return finish(D.ESCALATE,E.LEGAL_REVIEW_REQUIRED,str(exc),C.OUT_OF_POLICY,R.HR,'CAL-01',[R.HR])
        result.working_dates = [d.isoformat() for d in dates]
        n = result.requested_working_days = len(dates)
        trace('CALENDAR',detail=f'{result.requested_calendar_days} ngày lịch; {n} ngày làm việc.')
        if n == 0:
            return finish(D.NO_LEAVE_REQUIRED,E.DAY_ALREADY_NON_WORKING,'[Toàn bộ là ngày nghỉ quy định] Toàn bộ khoảng thời gian xin nghỉ rơi vào ngày cuối tuần hoặc ngày lễ. Bạn được nghỉ theo lịch chung và quỹ phép năm được giữ nguyên 100%.',clause='CAL-01')
        if not q.leave_type: return correction(E.LEAVE_TYPE_MISSING,'[Chưa chọn loại nghỉ] Đơn chưa có thông tin loại chế độ nghỉ phép. Vui lòng chọn loại nghỉ phù hợp trong danh mục.')
        roles: list = []
        if q.leave_type not in {x.value for x in LeaveType}:
            return correction(E.LEAVE_TYPE_MISSING,'[Loại nghỉ chưa nhận diện] Loại nghỉ gửi lên không nằm trong danh mục quy chế công ty. Vui lòng chọn lại loại nghỉ phép hợp lệ.')
        maternity_checkup = _is_maternity_checkup(q, n)
        maternity_ceo_approved = q.leave_type == 'MATERNITY' and R.CEO in q.granted_roles
        maternity_manager_approved = (
            q.leave_type == 'MATERNITY'
            and R.DIRECT_MANAGER in q.granted_roles
            and E.PROOF_REVIEW_REQUIRED in q.waived_errors
        )
        if q.leave_type == 'MATERNITY':
            if not maternity_checkup and not maternity_ceo_approved:
                return finish(
                    D.ESCALATE, E.AUTOMATION_SCOPE_UNSUPPORTED,
                    '[Nghỉ thai sản dài hạn] Hồ sơ nghỉ sinh, dưỡng thai hoặc thời lượng nghỉ trên 1 ngày thuộc thẩm quyền Tổng Giám đốc. Đơn được chuyển Tổng Giám đốc xem xét; không trừ phép năm, chế độ BHXH được xử lý theo quy định.',
                    C.OUT_OF_POLICY, R.CEO, 'MAT-01', [R.CEO],
                )
            if maternity_checkup:
                proof_issue = _maternity_checkup_proof_issue(q, dates)
                if proof_issue and not maternity_manager_approved:
                    return finish(
                        D.ESCALATE, E.PROOF_REVIEW_REQUIRED,
                        f'[Hồ sơ khám thai cần quản lý đối chiếu] {proof_issue}. Đơn được chuyển Quản lý trực tiếp kiểm tra trước khi quyết định.',
                        C.AUTHORITY_ESCALATION, R.DIRECT_MANAGER, 'MAT-01', [R.DIRECT_MANAGER],
                    )
        elif q.leave_type == 'WORK_ACCIDENT':
            roles = [R.HR]
            remaining = [r for r in roles if r not in q.granted_roles]
            if remaining and E.AUTOMATION_SCOPE_UNSUPPORTED not in q.waived_errors:
                return finish(D.ESCALATE,E.AUTOMATION_SCOPE_UNSUPPORTED,'[Chế độ đặc thù BHXH] Đơn nghỉ theo chế độ Tai nạn lao động cần được đối soát hồ sơ hưởng trợ cấp theo quy định. Hồ sơ được chuyển tới Phòng Nhân sự (HR) để tiếp nhận và hướng dẫn thủ tục.',C.OUT_OF_POLICY,R.HR,'HR-SCOPE',roles)
        if should_deduct_annual_balance(q.leave_type) and q.employment_status == 'PROBATION':
            return correction(E.PROBATION_ANNUAL_RESTRICTED,'[Nhân sự đang thử việc] Theo quy chế nội bộ, nhân sự thử việc chưa áp dụng trừ quỹ phép năm. Vui lòng chọn loại đơn Nghỉ không lương để quản lý duyệt; số ngày phép năm sẽ được bảo lưu.','EMP-01')
        result.paid = q.leave_type in {'ANNUAL','SPECIAL_PAID'} if q.leave_type not in MEDICAL else None
        entitlement = None
        if q.leave_type in {'SPECIAL_PAID','STATUTORY_UNPAID'}:
            entitlements = PAID_ENTITLEMENTS if q.leave_type == 'SPECIAL_PAID' else UNPAID_ENTITLEMENTS
            entitlement = entitlements.get(q.reason_category)
            if entitlement is None:
                if q.leave_type == 'STATUTORY_UNPAID':
                    roles = [R.DIRECT_MANAGER]
                    remaining = [r for r in roles if r not in q.granted_roles]
                    if remaining and E.RELATIONSHIP_UNCLEAR not in q.waived_errors:
                        return finish(D.ESCALATE, E.RELATIONSHIP_UNCLEAR,
                                      '[Chưa rõ quan hệ thân nhân] Thông tin quan hệ gia đình chưa đủ căn cứ theo Điều 115 Bộ luật Lao động. Đơn chuyển tới Quản lý trực tiếp để xác minh thực tế.',
                                      C.UNCERTAIN_FACTS, R.DIRECT_MANAGER, 'ENT-01', roles)
                    entitlement = n
                elif q.leave_type == 'SPECIAL_PAID' and q.reason_category in UNPAID_ENTITLEMENTS:
                    # Đã chọn sự kiện, nhưng sự kiện này chỉ được nghỉ KHÔNG lương (Điều 115 khoản 2): hướng dẫn đổi loại nghỉ.
                    event = getattr(q.reason_category, 'value', q.reason_category)
                    return correction(E.UNQUALIFIED_SPECIAL_LEAVE,f'[Sự kiện không thuộc diện nghỉ có lương] Sự kiện {event} chỉ được nghỉ không hưởng lương tối đa {UNPAID_ENTITLEMENTS[q.reason_category]} ngày theo Điều 115 khoản 2 BLLĐ 2019. Vui lòng đổi loại nghỉ sang "Việc riêng không lương luật định" hoặc dùng phép năm.','ENT-01')
                else:
                    return correction(E.REASON_REQUIRED,'[Thiếu sự kiện hưởng lương] Bạn chưa chọn lý do sự kiện gia đình theo Điều 115 Bộ luật Lao động 2019 (Kết hôn, Con kết hôn, Tang chế tứ thân phụ mẫu). Vui lòng chọn đúng sự kiện để hưởng nguyên lương.','ENT-01')
            if entitlement is not None and n > entitlement: return correction(E.ENTITLEMENT_EXCEEDED,f'[Vượt định mức ngày phép theo luật] Chế độ này quy định tối đa {entitlement} ngày làm việc có lương (bạn đang xin {n} ngày). Vui lòng điều chỉnh đơn về tối đa {entitlement} ngày hoặc gửi đơn Nghỉ không lương cho phần ngày vượt định mức.','ENT-01')
        trace('ENTITLEMENT')
        if q.leave_type == 'UNPAID_OTHER' and not q.reason.strip():
            return correction(E.REASON_REQUIRED,'[Thiếu lý do nghỉ việc riêng] Đơn nghỉ không lương đang để trống phần lý do. Vui lòng ghi rõ lý do để cấp quản lý có cơ sở xem xét phê duyệt.','UNPAID-01')
        trace('INPUT_COMPLETENESS')
        if q.leave_type in PROOF_REQUIRED:
            p = q.proof
            pt = p.proof_type.value if hasattr(p.proof_type,'value') else str(p.proof_type)
            reason_category = getattr(q.reason_category, 'value', q.reason_category)
            couple_names = [p.subject_name, p.partner_name]
            self_marriage_auto_eligible = (
                q.leave_type == 'SPECIAL_PAID'
                and reason_category == 'SELF_MARRIAGE'
                and p.proof_verification_status in {'UNVERIFIED', 'VERIFIED'}
                and pt == 'MARRIAGE_CERTIFICATE'
                and str(p.event_type or '').upper() == 'SELF_MARRIAGE'
                and all(couple_names)
                and any(names_approximately_match(q.employee_name, name) for name in couple_names if name)
                and p.wedding_date is not None
                and start <= p.wedding_date <= end
                and bool(p.issuer)
                and bool(p.issue_date)
                and p.document_readability == 'READABLE'
                and p.has_red_stamp is True
                and p.signature_present is True
                and p.is_tampered is not True
                and p.ai_edited is not True
                and p.needs_manager_review is not True
            )
            if pt == 'NONE': return correction(E.PROOF_MISSING,'[Thiếu chứng từ bắt buộc] Chế độ nghỉ này bắt buộc phải có giấy tờ xác minh theo quy chế công ty. Vui lòng tải lên ảnh chụp hoặc file PDF chứng từ hợp lệ (giấy khám bệnh, giấy ra viện, giấy kết hôn...).','PROOF-01')
            unreadable = p.document_readability in {'ILLEGIBLE', 'UNREADABLE'}
            if unreadable:
                roles = [R.DIRECT_MANAGER]
                remaining = [r for r in roles if r not in q.granted_roles]
                if remaining and E.DOC_ILLEGIBLE not in q.waived_errors:
                    return finish(D.ESCALATE, E.DOC_ILLEGIBLE,
                                 '[Chứng từ mờ / khó nhận diện] Ảnh chứng từ bị mờ, mất nét hoặc thiếu dấu mộc khiến hệ thống không thể tự động đối soát. Đơn chuyển tới Quản lý trực tiếp để kiểm tra bản gốc hoặc yêu cầu bổ sung.',
                                 C.AUTHORITY_ESCALATION, R.DIRECT_MANAGER, 'PROOF-01', roles)
            if p.proof_verification_status == 'REJECTED':
                return correction(E.DOC_FIELD_MISSING,'[Chứng từ chưa được chấp thuận] Hồ sơ chứng từ chưa đáp ứng quy chuẩn: ' + (p.verification_notes or 'Chưa đủ thông tin pháp lý hợp lệ. Vui lòng kiểm tra lại và tải lên chứng từ bổ sung.'),'PROOF-01')
            # Lỗi rõ ràng mà nhân viên tự sửa được (dựa trên thông tin đã đọc được trên giấy) phải báo cho nhân viên
            # TRƯỚC khi chuyển người duyệt đối chiếu chứng từ; nếu không, người duyệt nhận những chứng từ sai hiển nhiên.
            if q.leave_type in MEDICAL:
                name_match = getattr(p, 'patient_name_match', None)
                if p.patient_name and name_match != 'MATCH' and not names_approximately_match(p.patient_name, q.employee_name):
                    return finish(
                        D.ESCALATE,
                        E.NAME_MISMATCH,
                        f'[Họ tên trên chứng từ không khớp] Tên trên giấy y tế ({p.patient_name}) khác với nhân viên làm đơn ({q.employee_name}). Hồ sơ chuyển HR xác minh trước khi quyết định.',
                        C.AUTHORITY_ESCALATION,
                        R.HR,
                        'MED-01',
                        [R.HR],
                    )
                if p.patient_name and name_match in {'UNCERTAIN', 'NOT_APPLICABLE'}:
                    roles = [R.DIRECT_MANAGER]
                    remaining = [r for r in roles if r not in q.granted_roles]
                    if remaining and E.PROOF_REVIEW_REQUIRED not in q.waived_errors:
                        return finish(D.ESCALATE, E.PROOF_REVIEW_REQUIRED,
                                      '[Chưa xác minh được danh tính trên chứng từ] VLM chưa đủ căn cứ xác nhận tên bệnh nhân khớp với nhân viên. Hồ sơ cần được quản lý kiểm tra.',
                                      C.AUTHORITY_ESCALATION, R.DIRECT_MANAGER, 'MED-01', roles)
                if p.recommended_from_date and p.recommended_to_date and (
                        p.recommended_from_date > p.recommended_to_date
                        or any(not p.recommended_from_date <= d <= p.recommended_to_date for d in dates)):
                    return correction(E.MEDICAL_DAYS_MISMATCH,f'[Thời gian nghỉ lệch chỉ định y tế] Khoảng ngày bạn xin nghỉ nằm ngoài thời gian bác sĩ chỉ định trên giấy (từ {p.recommended_from_date} đến {p.recommended_to_date}). Vui lòng điều chỉnh ngày xin nghỉ cho khớp với giấy chứng nhận.','MED-01')
                if p.document_readability == 'READABLE' and p.signature_present is False and not p.digital_signature_present:
                    return correction(E.DOC_FIELD_MISSING,'[Chứng từ thiếu chữ ký] Giấy y tế chưa có chữ ký của bác sĩ / người có thẩm quyền (hoặc chữ ký số). Vui lòng xin xác nhận chữ ký và tải lại chứng từ.','MED-01')
            if p.proof_verification_status != 'VERIFIED' and E.PROOF_REVIEW_REQUIRED not in q.waived_errors:
                relationship_status = _relationship_verification_status(p, q.reason_category)
                family_event_verified = _family_event_auto_eligible(q, p, dates)
                short_medical_valid = (
                    q.leave_type in MEDICAL and
                    n < 3 and
                    p.document_readability in {'READABLE', 'UNKNOWN'} and
                    bool(p.issuer) and bool(p.issue_date) and
                    bool(p.patient_name) and bool(p.recommended_from_date) and bool(p.recommended_to_date) and
                    (bool(p.signature_present) or bool(p.digital_signature_present))
                )
                if not short_medical_valid and not self_marriage_auto_eligible and not family_event_verified:
                    proof_issues = []
                    _sig_present = getattr(p, 'signature_present', None)
                    _dig_sig = getattr(p, 'digital_signature_present', None)
                    if _sig_present is False and not _dig_sig:
                        proof_issues.append('chứng từ thiếu chữ ký người có thẩm quyền')
                    elif _sig_present is None and not _dig_sig:
                        proof_issues.append('chưa xác minh được chữ ký trên chứng từ')
                    if q.leave_type in {'SPECIAL_PAID', 'STATUTORY_UNPAID'} and getattr(p, 'has_red_stamp', None) is None:
                        proof_issues.append('chưa xác minh được dấu đỏ trên chứng từ')
                    if q.leave_type in {'SPECIAL_PAID', 'STATUTORY_UNPAID'}:
                        rel_label = getattr(p, 'relationship_label', None) or getattr(p, 'relationship_to_employee', None) or ''
                        if not rel_label or 'chưa xác minh' in rel_label.lower() or 'chưa rõ' in rel_label.lower():
                            proof_issues.append('quan hệ trên giấy chưa xác minh rõ ràng')
                    if not p.issuer or not p.issue_date:
                        proof_issues.append('thông tin nơi cấp hoặc ngày cấp chưa rõ')
                    if not proof_issues:
                        proof_issues.append('các thông tin chuyên môn trên chứng từ cần đối chiếu lại')
                    issue_text = '; '.join(proof_issues)
                    review_role = R.DIRECT_MANAGER if q.leave_type in {'SPECIAL_PAID', 'STATUTORY_UNPAID'} else R.HR
                    review_role_label = 'Quản lý trực tiếp' if review_role == R.DIRECT_MANAGER else 'Phòng Nhân sự (HR)'
                    return finish(
                        D.ESCALATE,
                        E.PROOF_REVIEW_REQUIRED,
                        f'[Chứng từ cần đối chiếu] Hệ thống đã tiếp nhận chứng từ của bạn. Đơn chuyển tới {review_role_label} để đối chiếu {issue_text} trước khi duyệt.',
                        C.OUT_OF_POLICY,
                        review_role,
                        'PROOF-01',
                        [review_role],
                    )
            allowed = MEDICAL_PROOFS if q.leave_type in MEDICAL else (
                {'MARRIAGE_CERTIFICATE'} if (hasattr(q.reason_category,'value') and q.reason_category.value == 'SELF_MARRIAGE') else
                {'MARRIAGE_CERTIFICATE','WEDDING_INVITATION'} if (hasattr(q.reason_category,'value') and q.reason_category.value == 'CHILD_MARRIAGE') else {'DEATH_CERTIFICATE'})
            if pt not in allowed:
                return correction(E.DOC_FIELD_MISSING,f'[Loại chứng từ không phù hợp] Chứng từ đính kèm ({pt}) không phải loại giấy tờ được chấp nhận cho chế độ nghỉ này. Vui lòng tải đúng loại chứng từ (vd giấy chứng nhận nghỉ ốm / giấy ra viện cho nghỉ ốm, giấy đăng ký kết hôn cho nghỉ cưới, giấy chứng tử cho nghỉ tang).','PROOF-01')
            if (p.document_readability != 'READABLE' and E.DOC_ILLEGIBLE not in q.waived_errors and not any(r in q.granted_roles for r in (R.DIRECT_MANAGER, R.DEPARTMENT_HEAD, R.CEO))) or not p.issuer or not p.issue_date:
                return correction(E.DOC_FIELD_MISSING,'[Thông tin chứng từ chưa đầy đủ] Chứng từ cần thể hiện rõ tên cơ sở y tế cấp, ngày cấp và hình ảnh rõ nét. Vui lòng kiểm tra lại ảnh chụp để đảm bảo thấy rõ các thông tin này.','PROOF-01')
            if q.leave_type in MEDICAL:
                if not p.patient_name or not p.recommended_from_date or not p.recommended_to_date or not (p.signature_present or p.digital_signature_present):
                    return correction(E.DOC_FIELD_MISSING,'[Thiếu thông tin chỉ định y tế] Giấy y tế cần thể hiện rõ họ tên bệnh nhân, khoảng thời gian bác sĩ chỉ định nghỉ và chữ ký xác nhận. Vui lòng bổ sung chứng từ đầy đủ các mục này.','MED-01')
                if p.recommended_from_date > p.recommended_to_date or any(not p.recommended_from_date <= d <= p.recommended_to_date for d in dates):
                    return correction(E.MEDICAL_DAYS_MISMATCH,f'[Thời gian nghỉ lệch chỉ định y tế] Khoảng ngày bạn xin nghỉ nằm ngoài thời gian bác sĩ chỉ định trên giấy (từ {p.recommended_from_date} đến {p.recommended_to_date}). Vui lòng điều chỉnh ngày xin nghỉ cho khớp với giấy chứng nhận.','MED-01')
                if p.proof_verification_status != 'VERIFIED':
                    result.warnings.append('Giấy nghỉ hợp lệ và nằm trong giới hạn quy định; tự động duyệt mà không cần xác minh thêm.')
                else:
                    result.warnings.append('HR xử lý hồ sơ trợ cấp BHXH riêng; ghi nhận nghỉ không xác nhận quyền hưởng trợ cấp.')
        elif q.leave_type in NO_PROOF_REQUIRED:
            trace('PROOF', 'PASS', 'Loại nghỉ này không cần chứng từ làm điều kiện tiên quyết; chỉ xét theo ngày phép / lý do / thời hạn thông báo.')
        trace('PROOF')
        trace('WORKING_DAYS',detail=str(n))
        overlap = set(result.working_dates) & set(q.approved_working_dates)
        if overlap == set(result.working_dates):
            return finish(D.AUTO_REJECT,E.REQUEST_ALREADY_COVERED,'[Trùng lặp toàn bộ lịch nghỉ] Toàn bộ các ngày bạn xin nghỉ đã có đơn nghỉ phép được duyệt trước đó. Đơn này tự động từ chối để tránh trùng lặp trừ phép.',C.OUT_OF_POLICY,R.EMPLOYEE,'SYS-OVERLAP')
        if overlap: return correction(E.OVERLAPPING_REQUEST,'[Trùng lặp một phần lịch nghỉ] Khoảng thời gian bạn chọn có chứa một số ngày đã được duyệt trong đơn trước đó. Vui lòng sửa lại khoảng ngày bắt đầu và kết thúc để tránh ngày trùng lặp.','SYS-OVERLAP')
        trace('OVERLAP')
        if should_deduct_annual_balance(q.leave_type) and n > q.remaining_leave_days:
            return finish(D.AUTO_REJECT,E.BALANCE_EXCEEDED,f'[Vượt quá số dư phép năm] Bạn đang xin nghỉ {n} ngày làm việc trong khi quỹ phép năm chỉ còn {q.remaining_leave_days:g} ngày. Đơn bị từ chối; vui lòng giảm số ngày hoặc làm thêm đơn Nghỉ không lương cho phần ngày còn thiếu.',C.OUT_OF_POLICY,R.EMPLOYEE,'BAL-01')
        trace('BALANCE')
        operational = []
        if q.leave_type in OPERATIONAL:
            if q.leave_type == 'UNPAID_OTHER' or n > 5:
                required = 7
            elif n >= 4:
                required = 3
            else:
                required = 1
            try: actual = cal.notice_days(q.submitted_at,dates[0])
            except CalendarUnavailable as exc:
                return finish(D.ESCALATE,E.LEGAL_REVIEW_REQUIRED,str(exc),C.OUT_OF_POLICY,R.HR,'CAL-01',[R.HR])
            if actual < required:
                operational.append((E.NOTICE_PERIOD_VIOLATED,f'[Nộp đơn gấp vi phạm thời hạn báo trước] Đơn được nộp trước {actual} ngày làm việc trong khi quy chế yêu cầu tối thiểu {required} ngày cho kỳ nghỉ này. Đơn chuyển tới Quản lý trực tiếp xem xét đặc cách.','NOTICE-01'))
            trace('NOTICE','FAIL' if actual < required else 'PASS',f'{actual}/{required}')
        elif q.leave_type in MEDICAL and q.submitted_at:
            tz = ZoneInfo('Asia/Ho_Chi_Minh')
            sub_dt = q.submitted_at.astimezone(tz) if q.submitted_at.tzinfo else q.submitted_at.replace(tzinfo=tz)
            cutoff = datetime(dates[0].year, dates[0].month, dates[0].day, 8, 30, tzinfo=tz)
            if sub_dt > cutoff:
                operational.append((E.NOTICE_PERIOD_VIOLATED,'[Báo nghỉ ốm muộn sau giờ quy định] Đơn nghỉ ốm nộp sau 08:30 sáng của ngày vắng mặt đầu tiên (quy chế yêu cầu thông báo trước 08:30). Đơn chuyển tới Quản lý trực tiếp để xác nhận và thông cảm trường hợp khẩn cấp.','NOTICE-01'))
                trace('NOTICE','FAIL','Sau 08:30')
            else:
                trace('NOTICE','PASS','Trước 08:30')
        if q.leave_type == 'ANNUAL' and getattr(q, 'has_abuse_pattern', False):
            operational.append((E.FLAG_ABUSE_PATTERN, '[Phát hiện chuỗi đơn nghỉ ngắn lặp lại] Bạn đã nộp nhiều đơn nghỉ 1–2 ngày rời rạc trong cùng một tháng, vượt hạn mức tự duyệt tích lũy của hệ thống. Đơn chuyển tới Quản lý trực tiếp xem xét kế hoạch nghỉ phép.', 'ABUSE-01'))
            trace('ANTI_ABUSE', 'FAIL', 'Gắn cờ FLAG_ABUSE_PATTERN')
        quota_dates = [d for d in result.working_dates if (q.team_absences_by_date.get(d,q.team_absent_count)+1)/q.total_team_members > TEAM_ABSENCE_THRESHOLD]
        if quota_dates:
            message = f'[Tỷ lệ vắng mặt phòng ban vượt ngưỡng an toàn] Tỷ lệ nhân sự vắng mặt đồng thời vượt ngưỡng 30% vào các ngày: {", ".join(quota_dates)}. Đơn chuyển tới Quản lý trực tiếp để cân đối phân công công việc.'
            if q.leave_type in OPERATIONAL: operational.append((E.TEAM_QUOTA_EXCEEDED,message,'OPS-01'))
            else: result.warnings.append(message)
        trace('TEAM_CAPACITY','WARNING' if quota_dates and q.leave_type not in OPERATIONAL else 'FAIL' if quota_dates else 'PASS')
        handover_error = None
        handover_bypassed = False
        if q.handover_person_id or q.handover_person_name:
            h = q.handover
            if not q.handover_person_id: handover_error = (E.HANDOVER_REQUIRED,'[Chưa chọn người nhận bàn giao] Bạn đã chọn hình thức bàn giao công việc nhưng chưa chỉ định đồng nghiệp tiếp nhận. Vui lòng chọn người nhận bàn giao trong phòng ban.')
            elif not h or h.get('employee_id') == q.employee_id or h.get('department') != q.department or h.get('status') != 'ACTIVE' or set(h.get('absent_dates',[])) & set(result.working_dates):
                handover_error = (E.HANDOVER_INVALID,'[Người bàn giao chưa phù hợp] Người được chọn bàn giao phải cùng phòng ban, đang làm việc bình thường, không phải chính bạn và không trùng lịch nghỉ. Vui lòng chọn nhân sự khác thay thế.')
        elif n >= 3:
            if q.no_handover_needed:
                result.warnings.append('Nhân viên xác nhận "Không có công việc phát sinh cần bàn giao"; Quản lý cần tự kiểm chứng và chịu trách nhiệm khi duyệt.')
                handover_bypassed = True
            elif q.leave_type in OPERATIONAL:
                handover_error = (E.HANDOVER_REQUIRED,'[Kỳ nghỉ từ 3 ngày cần bàn giao] Với kỳ nghỉ từ 3 ngày làm việc trở lên, quy định công ty yêu cầu chỉ định người bàn giao công việc hoặc xác nhận "Không có công việc phát sinh cần bàn giao". Vui lòng cập nhật thông tin này trên đơn.')
            else:
                result.warnings.append('Khuyến nghị chỉ định người nhận bàn giao cho kỳ nghỉ từ 3 ngày trở lên.')
        if handover_error:
            if q.leave_type in OPERATIONAL: return correction(*handover_error,'OPS-02')
            result.warnings.append(handover_error[1])
        trace('HANDOVER','WARNING' if (handover_error or handover_bypassed or (n >= 3 and not q.handover_person_id)) else 'PASS')
        roles = []
        if q.leave_type == 'ANNUAL': roles = [R.CEO] if n >= 20 else [R.DEPARTMENT_HEAD] if n >= 6 else [R.DIRECT_MANAGER] if n >= 3 else []
        if q.leave_type == 'UNPAID_OTHER': roles = [R.DEPARTMENT_HEAD,R.HRD,R.CEO] if n >= 20 else [R.DEPARTMENT_HEAD,R.HRD] if n >= 6 else [R.DIRECT_MANAGER]
        if q.leave_type in MEDICAL:
            # policy_rules.md §3.1: 1 ngày → AI nếu chứng từ hợp lệ; 2–5 ngày → Lead Team; trên 5 ngày → CEO.
            roles = [R.CEO] if n > 5 else [R.DIRECT_MANAGER] if n >= 2 else []
        if q.leave_type == 'SPECIAL_PAID':
            if self_marriage_auto_eligible and not quota_dates:
                roles = []
            elif _family_event_auto_eligible(q, q.proof, result.working_dates) and not quota_dates:
                roles = []
            else:
                roles = [R.DIRECT_MANAGER]
        if q.leave_type == 'STATUTORY_UNPAID':
            roles = [R.DIRECT_MANAGER]
        if q.leave_type == 'WORK_ACCIDENT':
            roles = [R.HR]
        elif q.leave_type == 'MATERNITY':
            roles = [] if maternity_checkup or maternity_ceo_approved else [R.CEO]
        if operational and not roles: roles = [R.DIRECT_MANAGER]
        remaining = [r for r in roles if r not in q.granted_roles]
        for code, message, clause in operational:
            findings.append(EscalationDetail(error_code=code,category=C.OUT_OF_POLICY,target_role=(remaining or roles)[0],plain_reason=message,clause=clause,
                severity='WAIVED' if code in q.waived_errors else 'BLOCKING'))
        pending_ops = [x for x in operational if x[0] not in q.waived_errors]
        if pending_ops:
            code,message,clause = pending_ops[0]
            return finish(D.ESCALATE,code,message,C.OUT_OF_POLICY,(remaining or roles)[0],clause,roles)
        if remaining:
            target = remaining[0]
            target_name = {
                R.DIRECT_MANAGER: 'Quản lý trực tiếp',
                R.DEPARTMENT_HEAD: 'Trưởng bộ phận',
                R.CEO: 'Tổng Giám đốc (CEO)',
                R.HR: 'Phòng Nhân sự (HR)',
                R.HRD: 'Giám đốc Nhân sự (HRD)',
            }.get(target, 'Cấp có thẩm quyền')
            if q.leave_type == 'UNPAID_OTHER':
                code = E.LONG_TERM_UNPAID
                msg = f'[Nghỉ không lương dài ngày] Đơn xin nghỉ {n} ngày làm việc hợp lệ về quy chuẩn; chuyển tới {target_name} phê duyệt theo thẩm quyền.'
            elif n > 5:
                code = E.DURATION_OVER_MANAGER_LIMIT
                msg = f'[Vượt thẩm quyền Quản lý trực tiếp] Đơn xin nghỉ {n} ngày hợp lệ về số dư nhưng vượt mức 5 ngày của Quản lý trực tiếp; chuyển tới {target_name} phê duyệt.'
            else:
                code = E.DURATION_OVER_AI_LIMIT
                ai_limit = 1 if q.leave_type in MEDICAL else 2
                msg = f'[Vượt hạn mức tự duyệt của AI] Đơn xin nghỉ {n} ngày hợp lệ về số dư nhưng vượt trần tự duyệt {ai_limit} ngày của AI; chuyển tới {target_name} phê duyệt.'
            return finish(D.ESCALATE, code, msg, C.AUTHORITY_ESCALATION, target, 'AUTH-01', roles)
        trace('AUTHORITY')
        if maternity_manager_approved:
            msg = '[Khám thai một ngày đã được Quản lý trực tiếp phê duyệt] Hồ sơ đã được đối chiếu và chấp thuận; không trừ phép năm.'
        elif maternity_ceo_approved:
            msg = '[Thai sản đã được Tổng Giám đốc phê duyệt] Hồ sơ được ghi nhận theo quyết định của Tổng Giám đốc; không trừ phép năm.'
        elif maternity_checkup:
            msg = '[Khám thai một ngày hợp lệ] Thông tin nhân sự, chứng từ và ngày khám đã khớp. Đơn được tự động duyệt; không trừ phép năm.'
        elif should_deduct_annual_balance(q.leave_type):
            msg = f'[Tự động duyệt thành công] Đơn nghỉ {n} ngày làm việc hợp lệ 100% theo quy chế; hệ thống đã tự động phê duyệt và cập nhật trừ quỹ phép.'
        else:
            msg = f'[Tự động duyệt thành công] Đơn nghỉ {n} ngày làm việc hợp lệ 100% theo quy chế; hệ thống đã tự động phê duyệt, không trừ quỹ phép năm.'
        return finish(D.AUTO_APPROVE, message=msg, clause='AUTH-01', roles=roles)
