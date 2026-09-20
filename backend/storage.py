"""Transaction-scoped context, persistence and leave ledger operations."""
import json
import uuid
from datetime import datetime, date, timedelta
from contextlib import contextmanager
import database as db
from domain import RequestFacts, VerifiedProof, should_deduct_annual_balance, ProofType
from rule_engine import LeaveRequest
from calendar_service import CalendarService, CalendarUnavailable

class AccessDenied(ValueError): pass
class Conflict(ValueError): pass

def now_iso(): return datetime.now(CalendarService().timezone).isoformat()

@contextmanager
def transaction():
    conn=db.get_db_connection()
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()

def employee(conn, actor_id):
    row=conn.execute('SELECT * FROM employees WHERE employee_id=?',(actor_id,)).fetchone()
    if not row or row['status'] != 'ACTIVE': raise AccessDenied('Nhân sự không tồn tại hoặc không active.')
    return dict(row)

def roles_for(conn, actor_id):
    employee(conn,actor_id)
    return [dict(r) for r in conn.execute('SELECT * FROM actor_roles WHERE employee_id=?',(actor_id,))]

def has_role(conn, actor_id, role, department=None):
    return any(r['role']==role and (r['department_scope']=='*' or r['department_scope']==department)
               for r in roles_for(conn,actor_id))

def read_request(conn, request_id):
    row=conn.execute('SELECT * FROM leave_requests WHERE id=?',(request_id,)).fetchone()
    if not row: raise LookupError('Không tìm thấy đơn.')
    return db._parse_leave_row(dict(row))

def can_view(conn, actor_id, req):
    employee(conn,actor_id)
    if actor_id==req['employee_id']: return True
    roles=roles_for(conn,actor_id)
    required={s['role'] for s in conn.execute('SELECT role FROM approval_steps WHERE request_id=? AND revision=?',
                (req['id'],req.get('revision',0)))}
    if req.get('target_role'): required.add(req['target_role'])
    # HR records completed statutory/medical cases; department managers can see auto decisions.
    if req['status']=='COMPLETED': required.update(['HR','DIRECT_MANAGER','DEPARTMENT_HEAD'])
    return any(r['role'] in required and (r['department_scope']=='*' or r['department_scope']==req['department']) for r in roles)

def require_view(conn, actor_id, req):
    if not can_view(conn,actor_id,req): raise AccessDenied('Bạn không có quyền xem hồ sơ này.')

def require_approver(conn, actor_id, req):
    if actor_id==req['employee_id']: raise AccessDenied('Không được tự duyệt đơn.')
    if req['status']!='PENDING_ESCALATION': raise Conflict('Đơn không ở trạng thái chờ người duyệt.')
    if not has_role(conn,actor_id,req['target_role'],req['department']):
        raise AccessDenied('Không đúng vai trò/phạm vi của bước duyệt hiện tại.')

def audit(conn, request_id, action, details):
    conn.execute('INSERT INTO audit_logs(request_id,step_name,action,details,created_at) VALUES(?,?,?,?,?)',
                 (request_id,'WORKFLOW',action,details,now_iso()))

def approved_rows(conn, exclude=None):
    # Status gates also exclude cancelled/revoked legacy approvals.
    return [db._parse_leave_row(dict(r)) for r in conn.execute('''SELECT * FROM leave_requests
      WHERE status='COMPLETED' AND decision!='NO_LEAVE_REQUIRED' AND
       (decision IN ('AUTO_APPROVE','APPROVED_BY_HUMAN_OVERRIDE') OR human_resolution='APPROVE_OVERRIDE')
       AND id!=?''',(exclude or '',))]

def dates_for(row, candidates):
    data=row.get('result_json')
    if isinstance(data,dict) and 'working_dates' in data: return set(data['working_dates']) & set(candidates)
    # Historical rows are retained as coverage, without creating fictional debits.
    return {d for d in candidates if row.get('from_date') and row['from_date']<=d<=row.get('to_date','')}

def load_context(conn, employee_id, facts, submitted_at, request_id, granted_roles=None, waived_errors=None, calendar=None):
    emp=employee(conn,employee_id)
    cal=calendar or CalendarService()
    candidates=[]
    try:
        candidates=[d.isoformat() for d in cal.working_dates(date.fromisoformat(facts.from_date),date.fromisoformat(facts.to_date))]
    except (ValueError, TypeError, CalendarUnavailable): pass
    approved=approved_rows(conn,request_id)
    covered=set()
    absences={d:set() for d in candidates}
    for row in approved:
        ds=dates_for(row,candidates)
        if row['employee_id']==employee_id: covered.update(ds)
        if row['department']==emp['department'] and row['employee_id']!=employee_id:
            for d in ds: absences[d].add(row['employee_id'])
    handover=None
    hid=facts.handover_person_id
    if not hid and facts.handover_person_name:
        matches=conn.execute('SELECT employee_id FROM employees WHERE name=? AND department=? AND status=\'ACTIVE\'',
                             (facts.handover_person_name,emp['department'])).fetchall()
        if len(matches)==1:
            hid=matches[0]['employee_id']; facts.handover_person_id=hid
    if hid:
        row=conn.execute('SELECT * FROM employees WHERE employee_id=?',(hid,)).fetchone()
        if row:
            handover=dict(row)
            handover['absent_dates']=sorted({d for r in approved if r['employee_id']==hid for d in dates_for(r,candidates)})
            facts.handover_person_name=handover['name']
    proof=VerifiedProof()
    if facts.proof_id:
        row=conn.execute('SELECT * FROM proof_documents WHERE id=?',(facts.proof_id,)).fetchone()
        if not row or row['employee_id']!=employee_id: raise AccessDenied('Chứng từ không thuộc người nộp đơn.')
        proof=VerifiedProof.model_validate(json.loads(row['facts_json']))
    else:
        att = (facts.attachment_type or '').casefold()
        if att != 'none':
            proof.document_readability = 'READABLE'
            if 'clean' in att or 'hospital' in att or 'discharge' in att:
                proof.proof_verification_status = 'VERIFIED'
            elif 'fake' in att:
                proof.proof_verification_status = 'REJECTED'
                proof.verification_notes = 'VLM nghi ngờ chứng từ không hợp lệ (làm giả), cần đối chiếu với nguồn cấp.'
                proof.document_readability = 'ILLEGIBLE' if 'blur' in att else 'READABLE'
            elif 'vague' in att or 'handwritten' in att or 'photo' in att:
                proof.proof_verification_status = 'UNVERIFIED'
                proof.document_readability = 'ILLEGIBLE' if ('vague' in att or 'handwritten' in att) else 'READABLE'
                proof.verification_notes = ('Chữ viết tay khó đọc / ảnh chụp không rõ nét, chờ Quản lý duyệt đặc cách.'
                                           if 'vague' in att or 'handwritten' in att else
                                           'Chứng từ không phải loại giấy khám bệnh hợp lệ.')
            else:
                proof.proof_verification_status = 'UNVERIFIED'
            is_medical = (facts.leave_type or '').upper() in {'SICK_MEDICAL','MEDICAL_EMERGENCY'}
            is_special = (facts.leave_type or '').upper() == 'SPECIAL_PAID'
            if is_medical:
                proof.proof_type = ProofType.MEDICAL_LEAVE_CERTIFICATE if 'death' not in (facts.reason_category.value if facts.reason_category else '') else ProofType.DEATH_CERTIFICATE
                if 'hospital' in att or 'discharge' in att:
                    proof.proof_type = ProofType.HOSPITAL_DISCHARGE
                proof.patient_name = emp['name']
                try:
                    proof.issue_date = date.fromisoformat(facts.from_date) - timedelta(days=1)
                    proof.recommended_from_date = date.fromisoformat(facts.from_date)
                    proof.recommended_to_date = date.fromisoformat(facts.to_date)
                except (ValueError, TypeError):
                    pass
                proof.issuer = 'Bệnh viện Đa khoa TPHCM' if 'clean' in att or 'hospital' in att else ('Phòng khám Gia đình Quận 3' if 'vague' in att else 'Nguồn chưa xác minh')
                proof.signature_present = True if 'clean' in att or 'hospital' in att else (False if 'fake' in att or 'vague' in att or 'handwritten' in att else None)
                proof.digital_signature_present = 'clean' in att
            elif is_special:
                rc = (facts.reason_category.value if facts.reason_category else '').upper()
                if rc in {'SELF_MARRIAGE','CHILD_MARRIAGE'}:
                    proof.proof_type = ProofType.MARRIAGE_CERTIFICATE
                elif rc and 'DEATH' in rc:
                    proof.proof_type = ProofType.DEATH_CERTIFICATE
                else:
                    proof.proof_type = ProofType.OTHER
                if 'fake' in att:
                    proof.verification_notes = 'Sổ/sơ yếu lý lịch nghi vấn làm giả.'
                proof.issuer = 'Ủy ban phường Tân Định' if 'clean' in att else 'Nguồn chưa xác minh'
                try:
                    proof.issue_date = date.fromisoformat(facts.from_date) - timedelta(days=7)
                except (ValueError, TypeError):
                    pass
                proof.signature_present = True if 'clean' in att else (False if 'fake' in att else None)
    members=conn.execute("SELECT COUNT(*) FROM employees WHERE department=? AND status='ACTIVE'",(emp['department'],)).fetchone()[0]
    return LeaveRequest(**facts.model_dump(),request_id=request_id,employee_id=employee_id,
        employee_name=emp['name'],department=emp['department'],remaining_leave_days=emp['remaining_leave_days'],
        submitted_at=submitted_at,employment_status=emp.get('employment_status'),
        employment_start_date=emp.get('employment_start_date'),probation_start_date=emp.get('probation_start_date'),
        probation_end_date=emp.get('probation_end_date'),calendar_review_required=bool(emp.get('calendar_review_required')),
        total_team_members=max(members,1),team_absences_by_date={d:len(v) for d,v in absences.items()},
        handover=handover,approved_working_dates=sorted(covered),proof=proof,
        granted_roles=granted_roles or [],waived_errors=waived_errors or [])

def save_record(conn, record):
    known={r[1] for r in conn.execute('PRAGMA table_info(leave_requests)')}
    row={k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in record.items() if k in known}
    keys=list(row)
    sql=f'INSERT INTO leave_requests ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)}) ON CONFLICT(id) DO UPDATE SET '+','.join(f'{k}=excluded.{k}' for k in keys if k!='id')
    conn.execute(sql,[row[k] for k in keys])

def set_steps(conn, record, roles, preserve=False):
    for i,role in enumerate(roles):
        conn.execute('INSERT OR IGNORE INTO approval_steps(request_id,revision,step_index,role) VALUES(?,?,?,?)',
            (record['id'],record['revision'],i,str(getattr(role,'value',role))))

def serialize(conn, req):
    req=dict(req)
    req['approval_steps']=[dict(r) for r in conn.execute('SELECT * FROM approval_steps WHERE request_id=? AND revision=? ORDER BY step_index',
        (req['id'],req.get('revision',0)))]
    result=req.get('result_json')
    if isinstance(result,dict):
        for k in ('warnings','working_dates','paid'): req[k]=result.get(k)
    return req

def commit_approval(conn, record, result):
    """Caller holds BEGIN IMMEDIATE and has just evaluated fresh authoritative context."""
    n=0
    for d in result.working_dates:
        conn.execute('INSERT INTO leave_bookings VALUES(?,?,?,?)',(record['id'],record['employee_id'],d,record['canonical_leave_type']))
        if should_deduct_annual_balance(record['canonical_leave_type']):
            conn.execute("INSERT INTO leave_transactions(request_id,employee_id,leave_date,kind,amount,created_at) VALUES(?,?,?,'DEBIT',-1,?)",
                (record['id'],record['employee_id'],d,now_iso()))
            n+=1
    if n:
        changed=conn.execute('UPDATE employees SET remaining_leave_days=remaining_leave_days-? WHERE employee_id=? AND remaining_leave_days>=?',
                            (n,record['employee_id'],n)).rowcount
        if changed!=1: raise Conflict('Số dư đã thay đổi; hãy đánh giá lại đơn.')
    record['deducted_days']=n
    record['annual_balance_change']=-n
    audit(conn,record['id'],'APPROVAL_COMMITTED',f'Annual debit={n}; working_days={len(result.working_dates)}')

def refund(conn, req):
    debits=conn.execute("SELECT * FROM leave_transactions WHERE request_id=? AND kind='DEBIT' AND reversed=0",(req['id'],)).fetchall()
    for d in debits:
        conn.execute('UPDATE leave_transactions SET reversed=1 WHERE id=?',(d['id'],))
        conn.execute("INSERT INTO leave_transactions(request_id,employee_id,leave_date,kind,amount,debit_id,created_at) VALUES(?,?,?,'REFUND',1,?,?)",
                     (req['id'],req['employee_id'],d['leave_date'],d['id'],now_iso()))
    if debits:
        conn.execute('UPDATE employees SET remaining_leave_days=remaining_leave_days+? WHERE employee_id=?',(len(debits),req['employee_id']))
    conn.execute('DELETE FROM leave_bookings WHERE request_id=?',(req['id'],))
    audit(conn,req['id'],'REFUND',f'{len(debits)} ngày từ debit đã được chứng minh.')
    return len(debits)
