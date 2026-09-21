"""Deterministic leave evaluation. Caller supplies authoritative DB context only."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import Field
from domain import (RequestFacts, VerifiedProof, LeaveType,
                    names_approximately_match, should_deduct_annual_balance)
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
MEDICAL_PROOFS = {'MEDICAL_LEAVE_CERTIFICATE','HOSPITAL_DISCHARGE','MEDICAL_RECORD_SUMMARY','INJURY_CERTIFICATE'}
STATUTORY_PARENT_LOSS = {'PARENT_DEATH', 'SPOUSE_PARENT_DEATH'}
RULE_STAGES = ['INPUT_DATES','CALENDAR','ENTITLEMENT','INPUT_COMPLETENESS','PROOF',
               'WORKING_DAYS','OVERLAP','BALANCE','NOTICE','TEAM_CAPACITY','HANDOVER','AUTHORITY','FINAL']

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
        if q.date_ambiguous: return correction(E.DATE_AMBIGUOUS,'Vui lòng xác định ngày nghỉ cụ thể.')
        if not q.from_date or not q.to_date: return correction(E.DATE_MISSING,'Vui lòng bổ sung ngày bắt đầu và kết thúc.')
        try:
            start, end = date.fromisoformat(q.from_date), date.fromisoformat(q.to_date)
        except ValueError:
            return correction(E.DATE_RANGE_INVALID,'Ngày phải đúng định dạng YYYY-MM-DD.')
        if start > end or (end-start).days > 3660:
            return correction(E.DATE_RANGE_INVALID,'Khoảng ngày không hợp lệ (tối đa 10 năm).')
        trace('INPUT_DATES')
        result.requested_calendar_days = (end-start).days + 1
        try:
            if q.calendar_review_required: raise CalendarUnavailable('Lịch cá nhân cần HR xác minh.')
            dates = cal.working_dates(start,end)
        except CalendarUnavailable as exc:
            return finish(D.ESCALATE,E.LEGAL_REVIEW_REQUIRED,str(exc),C.OUT_OF_POLICY,R.HR,'CAL-01',[R.HR])
        result.working_dates = [d.isoformat() for d in dates]
        n = result.requested_working_days = len(dates)
        trace('CALENDAR',detail=f'{result.requested_calendar_days} ngày lịch; {n} ngày làm việc.')
        if n == 0:
            return finish(D.NO_LEAVE_REQUIRED,E.DAY_ALREADY_NON_WORKING,'Toàn bộ khoảng ngày đã là ngày nghỉ; không trừ phép.',clause='CAL-01')
        if not q.leave_type: return correction(E.LEAVE_TYPE_MISSING,'Vui lòng chọn loại nghỉ.')
        roles: list = []
        if q.leave_type not in {x.value for x in LeaveType}:
            return correction(E.LEAVE_TYPE_MISSING,'Loại nghỉ chưa được nhận diện; vui lòng chọn lại.')
        if q.leave_type in {'WORK_ACCIDENT','MATERNITY'}:
            return finish(D.ESCALATE,E.AUTOMATION_SCOPE_UNSUPPORTED,'Chính sách tự động chưa bao phủ đầy đủ chế độ này.',C.OUT_OF_POLICY,R.HR,'HR-SCOPE',[R.HR])
        if should_deduct_annual_balance(q.leave_type) and q.employment_status == 'PROBATION':
            return correction(E.PROBATION_ANNUAL_RESTRICTED,'Trong thử việc chưa sử dụng Annual. Hãy gửi đơn Unpaid Other riêng; số dư được giữ nguyên.','EMP-01')
        result.paid = q.leave_type in {'ANNUAL','SPECIAL_PAID'} if q.leave_type not in MEDICAL else None
        entitlement = None
        if q.leave_type in {'SPECIAL_PAID','STATUTORY_UNPAID'}:
            entitlements = PAID_ENTITLEMENTS if q.leave_type == 'SPECIAL_PAID' else UNPAID_ENTITLEMENTS
            entitlement = entitlements.get(q.reason_category)
            if entitlement is None:
                if q.leave_type == 'STATUTORY_UNPAID':
                    return finish(D.ESCALATE, E.RELATIONSHIP_UNCLEAR,
                                  'Quan hệ thân nhân chưa đủ rõ để xác định chế độ luật định; chuyển Quản lý xác minh.',
                                  C.UNCERTAIN_FACTS, R.DIRECT_MANAGER, 'ENT-01')
                return correction(E.REASON_REQUIRED,'Vui lòng chọn sự kiện/quan hệ thân nhân thuộc chế độ.','ENT-01')
            if n > entitlement: return correction(E.ENTITLEMENT_EXCEEDED,f'Chế độ này ghi nhận tối đa {entitlement} ngày làm việc. Hãy điều chỉnh hoặc gửi đơn riêng cho phần dư.','ENT-01')
        trace('ENTITLEMENT')
        if q.leave_type == 'UNPAID_OTHER' and not q.reason.strip():
            return correction(E.REASON_REQUIRED,'Vui lòng nêu lý do xin nghỉ không lương.','UNPAID-01')
        trace('INPUT_COMPLETENESS')
        if q.leave_type in MEDICAL | {'SPECIAL_PAID'}:
            p = q.proof
            pt = p.proof_type.value if hasattr(p.proof_type,'value') else str(p.proof_type)
            if pt == 'NONE': return correction(E.PROOF_MISSING,'Vui lòng tải chứng từ phù hợp.','PROOF-01')
            if p.document_readability == 'ILLEGIBLE':
                return correction(E.DOC_ILLEGIBLE,'Chứng từ mờ / không đọc được; vui lòng tải lại bản rõ hơn.','PROOF-01')
            if p.proof_verification_status == 'REJECTED':
                return correction(E.DOC_FIELD_MISSING,'Chứng từ chưa đạt yêu cầu: ' + (p.verification_notes or 'Vui lòng bổ sung.'),'PROOF-01')
            if p.proof_verification_status != 'VERIFIED':
                return finish(D.ESCALATE,E.PROOF_REVIEW_REQUIRED,'Đã nhận chứng từ; cần HR xác minh facts trước khi ghi nhận chế độ.',C.OUT_OF_POLICY,R.HR,'PROOF-01',[R.HR])
            allowed = MEDICAL_PROOFS if q.leave_type in MEDICAL else (
                {'MARRIAGE_CERTIFICATE'} if (hasattr(q.reason_category,'value') and q.reason_category.value == 'SELF_MARRIAGE') else
                {'MARRIAGE_CERTIFICATE','WEDDING_INVITATION'} if (hasattr(q.reason_category,'value') and q.reason_category.value == 'CHILD_MARRIAGE') else {'DEATH_CERTIFICATE'})
            if pt not in allowed or p.document_readability != 'READABLE' or not p.issuer or not p.issue_date:
                return correction(E.DOC_FIELD_MISSING,'Loại chứng từ, nơi cấp, ngày cấp hoặc độ rõ chưa đầy đủ.','PROOF-01')
            if q.leave_type in MEDICAL:
                if not p.patient_name or not p.recommended_from_date or not p.recommended_to_date or not (p.signature_present or p.digital_signature_present):
                    return correction(E.DOC_FIELD_MISSING,'Cần tên bệnh nhân, khoảng nghỉ được chỉ định và chữ ký/chữ ký số.','MED-01')
                if not names_approximately_match(p.patient_name, q.employee_name):
                    return correction(E.NAME_MISMATCH,'Tên bệnh nhân không khớp người nghỉ; vui lòng làm rõ.','MED-01')
                if p.recommended_from_date > p.recommended_to_date or any(not p.recommended_from_date <= d <= p.recommended_to_date for d in dates):
                    return correction(E.MEDICAL_DAYS_MISMATCH,'Ngày nghỉ yêu cầu nằm ngoài khoảng bác sĩ chỉ định.','MED-01')
                result.warnings.append('HR xử lý hồ sơ trợ cấp BHXH riêng; ghi nhận nghỉ không xác nhận quyền hưởng trợ cấp.')
        trace('PROOF')
        trace('WORKING_DAYS',detail=str(n))
        overlap = set(result.working_dates) & set(q.approved_working_dates)
        if overlap == set(result.working_dates):
            return finish(D.AUTO_REJECT,E.REQUEST_ALREADY_COVERED,'Các ngày này đã có đơn được duyệt; không trừ phép lần hai.',C.OUT_OF_POLICY,R.EMPLOYEE,'SYS-OVERLAP')
        if overlap: return correction(E.OVERLAPPING_REQUEST,'Một phần ngày nghỉ đã có đơn được duyệt. Hãy sửa khoảng ngày.','SYS-OVERLAP')
        trace('OVERLAP')
        if should_deduct_annual_balance(q.leave_type) and n > q.remaining_leave_days:
            return finish(D.AUTO_REJECT,E.BALANCE_EXCEEDED,f'Bạn yêu cầu {n} ngày nhưng chỉ còn {q.remaining_leave_days:g} ngày phép. Hãy giảm số ngày hoặc gửi một đơn Unpaid Leave riêng.',C.OUT_OF_POLICY,R.EMPLOYEE,'BAL-01')
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
                operational.append((E.NOTICE_PERIOD_VIOLATED,f'Báo trước {actual}/{required} ngày làm việc.','NOTICE-01'))
            trace('NOTICE','FAIL' if actual < required else 'PASS',f'{actual}/{required}')
        elif q.leave_type in MEDICAL and q.submitted_at:
            tz = ZoneInfo('Asia/Ho_Chi_Minh')
            sub_dt = q.submitted_at.astimezone(tz) if q.submitted_at.tzinfo else q.submitted_at.replace(tzinfo=tz)
            cutoff = datetime(dates[0].year, dates[0].month, dates[0].day, 8, 30, tzinfo=tz)
            if sub_dt > cutoff:
                operational.append((E.NOTICE_PERIOD_VIOLATED,'Báo nghỉ ốm sau 08:30 sáng của ngày vắng mặt đầu tiên.','NOTICE-01'))
                trace('NOTICE','FAIL','Sau 08:30')
            else:
                trace('NOTICE','PASS','Trước 08:30')
        if q.leave_type == 'ANNUAL' and getattr(q, 'has_abuse_pattern', False):
            operational.append((E.FLAG_ABUSE_PATTERN, 'Nhiều đơn phép năm rời rạc trong cùng tháng dương lịch vượt hạn mức tự duyệt của AI.', 'ABUSE-01'))
            trace('ANTI_ABUSE', 'FAIL', 'Gắn cờ FLAG_ABUSE_PATTERN')
        quota_dates = [d for d in result.working_dates if (q.team_absences_by_date.get(d,q.team_absent_count)+1)/q.total_team_members > .30]
        if quota_dates:
            message = 'Vượt quota 30% vào: ' + ', '.join(quota_dates)
            if q.leave_type in OPERATIONAL: operational.append((E.TEAM_QUOTA_EXCEEDED,message,'OPS-01'))
            else: result.warnings.append(message)
        trace('TEAM_CAPACITY','WARNING' if quota_dates and q.leave_type not in OPERATIONAL else 'FAIL' if quota_dates else 'PASS')
        handover_error = None
        if n >= 3 or q.handover_person_id or q.handover_person_name:
            h = q.handover
            if not q.handover_person_id: handover_error = (E.HANDOVER_REQUIRED,'Vui lòng chỉ định người nhận bàn giao.')
            elif not h or h.get('employee_id') == q.employee_id or h.get('department') != q.department or h.get('status') != 'ACTIVE' or set(h.get('absent_dates',[])) & set(result.working_dates):
                handover_error = (E.HANDOVER_INVALID,'Người bàn giao phải cùng phòng, active, không phải chính bạn và không nghỉ trùng.')
        if handover_error:
            if q.leave_type in OPERATIONAL: return correction(*handover_error,'OPS-02')
            result.warnings.append(handover_error[1])
        trace('HANDOVER','WARNING' if handover_error else 'PASS')
        roles = []
        if q.leave_type == 'ANNUAL': roles = [R.CEO] if n >= 20 else [R.DEPARTMENT_HEAD] if n >= 6 else [R.DIRECT_MANAGER] if n >= 3 else []
        if q.leave_type == 'UNPAID_OTHER': roles = [R.DEPARTMENT_HEAD,R.HRD,R.CEO] if n >= 20 else [R.DEPARTMENT_HEAD,R.HRD] if n >= 6 else [R.DIRECT_MANAGER]
        if q.leave_type in MEDICAL:
            roles = [R.DIRECT_MANAGER] if n >= 2 else []
        if q.leave_type in {'SPECIAL_PAID', 'STATUTORY_UNPAID'}:
            roles = [R.DIRECT_MANAGER]
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
            code = E.LONG_TERM_UNPAID if q.leave_type == 'UNPAID_OTHER' else E.DURATION_OVER_MANAGER_LIMIT if n > 5 else E.DURATION_OVER_AI_LIMIT
            return finish(D.ESCALATE,code,'Đơn hợp lệ nhưng cần phê duyệt theo phân cấp.',C.AUTHORITY_ESCALATION,remaining[0],'AUTH-01',roles)
        trace('AUTHORITY')
        return finish(D.AUTO_APPROVE,message='Đủ điều kiện ghi nhận/phê duyệt theo policy.',clause='AUTH-01',roles=roles)
