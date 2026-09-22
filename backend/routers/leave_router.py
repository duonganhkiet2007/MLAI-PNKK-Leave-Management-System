"""Leave API. X-Actor-ID selects a demo actor; roles always come from the DB."""
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional, Literal
from fastapi import APIRouter, Depends, Header, Query, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from services.orchestration import LeaveOrchestratorService
from domain import RequestFacts, ProofType, ProofExtraction, VerifiedProof, EditableFields, should_deduct_annual_balance
import database as db
import storage as st

router=APIRouter(prefix='/api/leave',tags=['Leave Application'])
service=LeaveOrchestratorService()

def actor(x_actor_id: Optional[str]=Header(None),actor_id: Optional[str]=Query(None)):
    value=x_actor_id or actor_id
    if not value: raise HTTPException(401,'Chọn nhân sự demo (X-Actor-ID).')
    if x_actor_id and actor_id and x_actor_id!=actor_id: raise HTTPException(403,'Danh tính không khớp.')
    return value

class NewLeaveRequestInput(RequestFacts):
    employee_id: str | None = None
    raw_text: str | None = None

class HumanDecisionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    feedback_text: str = ''
    approver_id: str | None = None
    action_type: str | None = None
    updated_fields: EditableFields = Field(default_factory=EditableFields)

@router.post('/request')
def submit_leave_request(payload: NewLeaveRequestInput, actor_id=Depends(actor)):
    t0 = time.perf_counter()
    if payload.employee_id and payload.employee_id!=actor_id: raise st.AccessDenied('Không được nộp thay nhân sự khác.')
    data=payload.model_dump(exclude={'employee_id','raw_text'})
    res=service.process_new_request(payload.raw_text,actor_id,data)
    total_api_ms = round((time.perf_counter() - t0) * 1000, 2)
    if isinstance(res, dict):
        res['total_api_ms'] = total_api_ms
        if isinstance(res.get('llm_summary_json'), dict):
            res['llm_summary_json'].setdefault('timings', {})['total_api_ms'] = total_api_ms
    return {'success':True,'data':res,'total_api_ms':total_api_ms}

@router.get('/requests')
def list_leave_requests(status: str | None=None,actor_id=Depends(actor)):
    with st.readonly_connection() as conn:
        st.employee(conn,actor_id)
        rows=[]
        for r in conn.execute('SELECT * FROM leave_requests ORDER BY submitted_at DESC').fetchall():
            req=db._parse_leave_row(dict(r))
            if (not status or status=='ALL' or req['status']==status) and st.can_view(conn,actor_id,req):
                req=st.serialize(conn,req)
                req['can_act']=req['status']=='PENDING_ESCALATION' and actor_id!=req['employee_id'] and st.has_role(conn,actor_id,req.get('target_role'),req['department'])
                rows.append(req)
        return {'success':True,'total':len(rows),'data':rows}

@router.post('/proofs')
async def upload_proof(file: UploadFile=File(...),proof_type: ProofType=Form(ProofType.OTHER),actor_id=Depends(actor)):
    with st.readonly_connection() as conn: st.employee(conn,actor_id)
    if proof_type==ProofType.NONE: raise ValueError('Chọn loại chứng từ.')
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024: raise HTTPException(413,'Tệp tối đa 10 MB.')
    actual='application/pdf' if content.startswith(b'%PDF-') else 'image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if content.startswith(b'\xff\xd8\xff') else None
    if not actual or actual!=file.content_type: raise HTTPException(415,'Chỉ nhận PDF/JPEG/PNG đúng định dạng.')
    directory=Path(os.getenv('LEAVE_UPLOAD_DIR',str(Path(db.DB_PATH).parent/'uploads')))
    directory.mkdir(parents=True,exist_ok=True)
    pid=uuid.uuid4().hex
    name=pid+{'application/pdf':'.pdf','image/png':'.png','image/jpeg':'.jpg'}[actual]
    path=directory/name
    proof=VerifiedProof(proof_type=proof_type)
    try:
        with path.open('xb') as output: output.write(content)
        with st.transaction() as conn:
            conn.execute('''INSERT INTO proof_documents(id,employee_id,storage_name,original_name,mime_type,size_bytes,proof_type,facts_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)''',(pid,actor_id,name,Path(file.filename or 'document').name,actual,len(content),proof_type.value,proof.model_dump_json(),st.now_iso()))
            st.audit(conn,'PROOF-'+pid,'UPLOAD',actor_id)
    except Exception:
        path.unlink(missing_ok=True); raise
    return {'success':True,'data':{'proof_id':pid,'proof_type':proof_type.value,'proof_verification_status':'UNVERIFIED'}}

@router.get('/proofs/{proof_id}')
def get_proof(proof_id,actor_id=Depends(actor)):
    with st.readonly_connection() as conn:
        row=conn.execute('SELECT * FROM proof_documents WHERE id=?',(proof_id,)).fetchone()
        if not row: raise LookupError('Không tìm thấy chứng từ.')
        st.employee(conn,actor_id)
        allowed=row['employee_id']==actor_id or st.has_role(conn,actor_id,'HR')
        if not allowed:
            for req in conn.execute('SELECT * FROM leave_requests WHERE proof_id=?',(proof_id,)):
                req_dict = dict(req)
                if st.has_role(conn, actor_id, 'DIRECT_MANAGER', req_dict.get('department')) or st.has_role(conn, actor_id, 'DEPARTMENT_HEAD', req_dict.get('department')):
                    allowed = True
                    break
        if not allowed: raise st.AccessDenied('Không có quyền xem chứng từ.')
        directory=Path(os.getenv('LEAVE_UPLOAD_DIR',str(Path(db.DB_PATH).parent/'uploads')))
        return FileResponse(directory/row['storage_name'],media_type=row['mime_type'],filename=row['original_name'],
                            headers={'X-Content-Type-Options':'nosniff'})

class ProofVerificationInput(ProofExtraction):
    proof_verification_status: Literal['VERIFIED','REJECTED','NEEDS_HR_REVIEW']
    verification_notes: str = Field(min_length=1)

@router.post('/proofs/{proof_id}/verify')
def verify_proof(proof_id,payload: ProofVerificationInput,actor_id=Depends(actor)):
    with st.transaction() as conn:
        if not st.has_role(conn,actor_id,'HR'): raise st.AccessDenied('Chỉ HR được xác minh chứng từ.')
        row=conn.execute('SELECT * FROM proof_documents WHERE id=?',(proof_id,)).fetchone()
        if not row: raise LookupError('Không tìm thấy chứng từ.')
        if row['employee_id']==actor_id: raise st.AccessDenied('Không tự xác minh chứng từ của mình.')
        linked=[db._parse_leave_row(dict(r)) for r in conn.execute('SELECT * FROM leave_requests WHERE proof_id=?',(proof_id,))]
        if any(r['status']=='COMPLETED' for r in linked): raise st.Conflict('Chứng từ đã dùng cho đơn hoàn tất; cần hồ sơ thay thế.')
        proof=VerifiedProof(**payload.model_dump(),verified_by=actor_id)
        fields=proof.model_dump(mode='json');fields.pop('fields_detected')
        fields['facts_json']=proof.model_dump_json()
        conn.execute('UPDATE proof_documents SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',list(fields.values())+[proof_id])
        st.audit(conn,'PROOF-'+proof_id,'HR_VERIFY',actor_id+': '+payload.verification_notes)
        updated=[]
        for req in linked:
            if req['status'] not in {'PENDING_ESCALATION','WAITING_EMPLOYEE'}: continue
            # REQUEST_MORE_INFO must be completed by Employee; a proof-review case resumes here.
            if req.get('human_resolution')=='REQUEST_MORE_INFO': continue
            req.update(revision=req['revision']+1,human_resolution=None)
            service._evaluate(conn,req,RequestFacts.model_validate(req['facts_json']))
            updated.append(req['id'])
    return {'success':True,'data':proof.model_dump(mode='json'),'reevaluated_requests':updated}

@router.get('/{request_id}')
def get_single_request(request_id,actor_id=Depends(actor)):
    with st.readonly_connection() as conn:
        req=st.read_request(conn,request_id);st.require_view(conn,actor_id,req)
        logs=[dict(r) for r in conn.execute('SELECT * FROM audit_logs WHERE request_id=? ORDER BY id',(request_id,))]
        return {'success':True,'data':st.serialize(conn,req),'audit_trail':logs}

@router.get('/{request_id}/analysis')
def get_request_analysis(request_id,actor_id=Depends(actor)):
    with st.readonly_connection() as conn:
        req=st.read_request(conn,request_id);st.require_view(conn,actor_id,req)
        proof={}
        proof_storage={}
        proof_file=''
        if req.get('proof_id'):
            p=conn.execute('SELECT * FROM proof_documents WHERE id=?',(req['proof_id'],)).fetchone()
            if p:
                proof_storage=dict(p)
                proof=json.loads(p['facts_json'])
                proof_file=(proof_storage.get('original_name') or proof_storage.get('storage_name') or '')
        # Build 13-node decision tree checklist from flat VLM + rule fields
        def _node(order, stage, status, passed, note, title_vi='', severity=''):
            return {"order":order,"stage":stage,"title_vi":title_vi or stage,"severity":severity or (
                'CRITICAL' if status=='FAIL' else 'WARNING' if status in ('WARN','ESCALATED','REJECTED','WAITING') else
                'INFO' if status=='NOT_RUN' else 'SUCCESS'),"status":status or "NOT_RUN","passed":bool(passed),"note":note or ""}
        # Helpers for human Vietnamese
        def _yn(v,true_txt='Có',false_txt='Không',na_txt='Chưa xác định'):
            if v is None: return na_txt
            if isinstance(v,(int,float)) and v not in (0,1): return str(v)
            return true_txt if (v is True or v==1) else false_txt
        def _s(v):
            if v is None: return ''
            if isinstance(v,(list,dict)):
                try: return json.dumps(v,ensure_ascii=False)
                except Exception: return str(v)
            return str(v)
        checklist = []
        llm = req.get('llm_summary_json') or {}
        vlm_full = req.get('vlm_analysis_json') or {}
        doc_summary = (vlm_full.get('document_summary') or {}) if isinstance(vlm_full, dict) else {}
        readability_raw = _s(req.get('document_readability')) or _s((vlm_full.get('flags') or {}).get('document_readability')) or _s((proof or {}).get('document_readability'))
        is_unreadable_doc = (
            readability_raw.strip().upper() in {'UNREADABLE', 'ILLEGIBLE'}
            or (req.get('error_code') or '').casefold() == 'doc_illegible'
            or 'DOC_LOW_READABILITY' in (vlm_full.get('escalation_flags') or [])
            or 'DOC_BLURRED_IMAGE' in (vlm_full.get('escalation_flags') or [])
        )
        if is_unreadable_doc:
            doc_patient_name = None
            doc_diagnosis = None
            doc_issuer = None
            doc_issue_date = None
        else:
            doc_patient_name = req.get('doc_patient_name') or (doc_summary.get('patient_name') if isinstance(doc_summary, dict) else None) or (proof.get('patient_name') if isinstance(proof, dict) else None)
            doc_diagnosis = req.get('doc_diagnosis') or (doc_summary.get('diagnosis') if isinstance(doc_summary, dict) else None) or (proof.get('diagnosis') if isinstance(proof, dict) else None)
            doc_issuer = (proof or {}).get('issuer') if isinstance(proof, dict) else None
            doc_issue_date = (proof or {}).get('issue_date') if isinstance(proof, dict) else None
        if isinstance(vlm_full, dict) and vlm_full.get('document_summary') and not is_unreadable_doc:
            try:
                from datetime import date as _date
                from vlm_inspector import _score_correlation
                doctor_range = doc_summary.get('doctor_recommended_range') or {}
                requested_from = _date.fromisoformat(str(req['from_date'])) if req.get('from_date') else None
                requested_to = _date.fromisoformat(str(req['to_date'])) if req.get('to_date') else None
                recommended_from = _date.fromisoformat(str(doctor_range['from'])) if doctor_range.get('from') else None
                recommended_to = _date.fromisoformat(str(doctor_range['to'])) if doctor_range.get('to') else None
                refreshed_score, refreshed_issues, refreshed_days = _score_correlation(
                    employee_name=req.get('employee_name') or '',
                    reason=req.get('reason') or '',
                    recommended_from=recommended_from,
                    recommended_to=recommended_to,
                    requested_from=requested_from,
                    requested_to=requested_to,
                    diagnosis=doc_summary.get('diagnosis'),
                    days_granted_by_doctor=doctor_range.get('days'),
                    requested_workdays=int(req.get('requested_working_days') or req.get('workdays') or 0),
                    leave_type=str(req.get('canonical_leave_type') or req.get('leave_type') or ''),
                )
                req['correlation_score'] = refreshed_score
                req['correlation_issues'] = refreshed_issues
                vlm_full = dict(vlm_full)
                vlm_full['correlation_analysis'] = {
                    'score': refreshed_score,
                    'issues': refreshed_issues,
                    'requested_workdays': int(req.get('requested_working_days') or req.get('workdays') or 0),
                }
            except Exception:
                pass
        leave_type_value = req.get('canonical_leave_type') or req.get('leave_type')
        shows_balance = should_deduct_annual_balance(leave_type_value)
        employee_row = conn.execute(
            'SELECT remaining_leave_days FROM employees WHERE employee_id=?',
            (req.get('employee_id'),)
        ).fetchone()
        remaining_leave_days = float(employee_row['remaining_leave_days']) if employee_row and employee_row['remaining_leave_days'] is not None else None
        shows_proof = leave_type_value in {
            'SPECIAL_PAID', 'STATUTORY_UNPAID', 'SICK_MEDICAL',
            'MEDICAL_EMERGENCY', 'WORK_ACCIDENT', 'MATERNITY',
        }

        def add_node(*args, include=True, **kwargs):
            if include:
                checklist.append(_node(*args, **kwargs))
        # ===== NODE 1. VALIDATION (Basic schema / Employee active) =====
        has_basic = bool(req.get('employee_id') and req.get('leave_type') and req.get('from_date') and req.get('to_date'))
        v_status = "PASS" if has_basic else "FAIL"
        ctx = llm.get('context',{}) if isinstance(llm,dict) else {}
        lt_label = ctx.get('leave_type_vn') or _s(req.get('canonical_leave_type') or req.get('leave_type'))
        v_note = f"Nhân sự: {req.get('employee_name') or 'N/A'} • Bộ phận: {req.get('department') or 'N/A'} • Loại nghỉ: {lt_label} • Từ {req.get('from_date')} đến {req.get('to_date')}."
        add_node(1,"VALIDATION",v_status, has_basic, v_note,
                               title_vi="Xác thực thông tin nhân viên & đơn nghỉ",
                       severity="SUCCESS" if has_basic else "CRITICAL")
        # ===== NODE 2. BALANCE (Quota check) =====
        rem = float(remaining_leave_days) if remaining_leave_days is not None else 0.0
        req_days = float(req.get('requested_calendar_days') or req.get('workdays') or 0)
        lt_code = str(req.get('canonical_leave_type') or req.get('leave_type') or '')
        b_pass = (lt_code != 'ANNUAL') or (remaining_leave_days is None or remaining_leave_days >= req_days)
        b_status = "PASS" if b_pass else "FAIL"
        b_note = f"Số ngày phép còn lại: {rem:.1f} ngày • Số ngày xin nghỉ: {req_days:.1f} ngày."
        add_node(2,"BALANCE",b_status, b_pass, b_note,
                               title_vi="Kiểm tra số dư phép năm (Quota)",
                       severity="SUCCESS" if b_pass else "CRITICAL",
                       include=(lt_code == 'ANNUAL' or shows_proof))
        # ===== NODE 3. PROOF (Attachment presence + basic fields) =====
        has_proof = bool(req.get('proof_id')) or bool((req.get('attachment_type') or '').strip() and (req.get('attachment_type') or '').casefold() != 'none')
        proof_pt = proof.get('proof_type') if isinstance(proof,dict) else None
        pt_label = proof_pt or req.get('attachment_type') or proof_storage.get('proof_type') or 'NONE'
        pt_label = {
            'MEDICAL_LEAVE_CERTIFICATE': 'Giấy chứng nhận nghỉ ốm',
            'HOSPITAL_DISCHARGE': 'Giấy ra viện',
            'MEDICAL_RECORD_SUMMARY': 'Tóm tắt hồ sơ bệnh án',
            'INJURY_CERTIFICATE': 'Giấy chứng nhận chấn thương',
            'MARRIAGE_CERTIFICATE': 'Giấy chứng nhận kết hôn',
            'DEATH_CERTIFICATE': 'Giấy chứng tử',
            'OTHER': 'Chứng từ khác',
            'NONE': 'Không có chứng từ',
        }.get(str(pt_label), str(pt_label))
        proof_segments = []
        if pt_label and pt_label not in ('NONE', 'Không có chứng từ'):
            proof_segments.append(f"Loại chứng từ: {pt_label}")
        for label, value in [
            ('Tên trên giấy', _s(doc_patient_name)),
            ('Nơi cấp', _s(doc_issuer)),
            ('Ngày cấp', _s(doc_issue_date)),
            ('Chẩn đoán', _s(doc_diagnosis)),
        ]:
            if value and value.strip() and value.strip().lower() not in {'none','null','unknown','chưa đọc được','không đọc được','không xác định'}:
                proof_segments.append(f"{label}: {value}")
        if proof_segments:
            proof_note = ' • '.join(proof_segments)
        else:
            proof_note = 'Không có thông tin được trích xuất từ chứng từ.'
        if not has_proof:
            proof_pass = False; proof_status = "FAIL"; proof_severity = "CRITICAL"
        elif is_unreadable_doc:
            proof_pass = False; proof_status = "FAIL"; proof_severity = "CRITICAL"
            proof_note = "Chứng từ không đọc được (bị mờ / mất nét / UNREADABLE). Vui lòng chụp lại rõ nét."
        else:
            proof_pass = (req.get('decision') or '').casefold() not in ('need_correction',) and (req.get('error_code') or '').casefold() != 'doc_illegible'
            proof_status = "PASS" if proof_pass else ("FAIL" if (req.get('decision') or '').casefold() == 'need_correction' else "WARN")
            proof_severity = 'SUCCESS' if proof_status=='PASS' else ('CRITICAL' if proof_status=='FAIL' else 'WARNING')
        add_node(3,"PROOF",proof_status, proof_pass, proof_note,
                               title_vi="Kiểm tra chứng từ đính kèm & loại giấy tờ",
                       severity=proof_severity, include=shows_proof)
        # ===== NODE 4. VLM - Document Integrity (red_stamp + signature + tamper + AI) =====
        rs = req.get('has_red_stamp')
        sig = req.get('has_doctor_signature')
        tamper = req.get('is_tampered')
        ai_edit = req.get('ai_edited')
        none_count = sum(1 for x in (rs,sig,tamper,ai_edit) if x is None)
        has_doc = has_proof  # alias
        if not has_doc:
            dint_status = "NOT_RUN"; dint_pass = False; dint_severity = "INFO"
            dint_note = "Không có chứng từ nên bỏ qua bước kiểm tra toàn vẹn VLM."
        elif is_unreadable_doc:
            dint_status = "FAIL"; dint_pass = False; dint_severity = "CRITICAL"
            dint_note = "Độ rõ tài liệu: UNREADABLE (Ảnh bị mờ hoặc mất nét, không thể xác minh tính toàn vẹn)."
        else:
            critical_flags = (tamper is True or ai_edit is True)
            missing_flags = none_count >= 3
            warn_flags = (rs is False or sig is False)
            if critical_flags:
                dint_status = "FAIL"; dint_pass = False; dint_severity = "CRITICAL"
            elif missing_flags:
                dint_status = "WARN"; dint_pass = False; dint_severity = "WARNING"
            elif warn_flags:
                dint_status = "WARN"; dint_pass = True; dint_severity = "WARNING"
            else:
                dint_status = "PASS"; dint_pass = True; dint_severity = "SUCCESS"
            dint_segments = []
            if rs is not None:
                dint_segments.append(f"Dấu đỏ: {_yn(rs,'Có','Không thấy','Chưa đọc được')}")
            if sig is not None:
                dint_segments.append(f"Chữ ký bác sĩ: {_yn(sig,'Có','Thiếu','Chưa đọc được')}")
            readability = _s(req.get('document_readability')) or _s((vlm_full.get('flags') or {}).get('document_readability'))
            if readability and readability.strip() and readability.strip().lower() not in {'none','null','unknown'}:
                dint_segments.append(f"Độ rõ tài liệu: {readability}")
            dint_note = ' • '.join(dint_segments) if dint_segments else 'Không có thông tin toàn vẹn chứng từ được trích xuất.'
        add_node(4,"VLM_INTEGRITY",dint_status, dint_pass, dint_note,
                               title_vi="VLM - Kiểm tra toàn vẹn chứng từ (dấu đỏ, chữ ký, giả mạo)",
                       severity=dint_severity, include=shows_proof)
        # ===== NODE 5. VLM - Patient / Employee name match =====
        doc_pat = doc_patient_name or ''
        emp_n = req.get('employee_name') or ''
        if not has_doc:
            p_status = "NOT_RUN"; p_pass = False; p_severity="INFO"
            p_note = "Không có chứng từ nên bỏ qua bước kiểm tra tên bệnh nhân."
        elif is_unreadable_doc:
            p_status = "FAIL"; p_pass = False; p_severity="CRITICAL"
            p_note = "Chứng từ không đọc được (UNREADABLE). Không thể xác minh tên bệnh nhân."
        elif not doc_pat:
            p_status = "WARN"; p_pass = False; p_severity="WARNING"
            p_note = "VLM KHÔNG đọc được tên người khám trên chứng từ (tên bệnh nhân trống). Không thể xác minh đây là giấy của nhân viên này."
        else:
            match_ok = (doc_pat.casefold().replace(' ','') == emp_n.casefold().replace(' ',''))
            p_status = "PASS" if match_ok else "FAIL"
            p_pass = match_ok
            p_severity = "SUCCESS" if match_ok else "CRITICAL"
            p_note = "Tên trên giấy: {doc} — Tên trong nhân sự: {emp} — {result}.".format(
                doc = doc_pat, emp = emp_n,
                result = "KHỚP ✅" if match_ok else "KHÔNG KHỚP ❌ (có thể giấy của người khác / sai tên)",
            )
        add_node(5,"VLM_PATIENT",p_status, p_pass, p_note,
                               title_vi="VLM - Đối chiếu tên bệnh nhân vs. nhân sự",
                       severity=p_severity, include=shows_proof)
        # ===== NODE 6. VLM - Date coverage (doctor recommended vs requested) =====
        vlm_sum = {}
        if isinstance(vlm_full,dict): vlm_sum = (vlm_full.get('document_summary') or {}) if isinstance(vlm_full.get('document_summary'),dict) else {}
        dr = {}
        if isinstance(vlm_sum.get('doctor_recommended_range'),dict): dr = vlm_sum['doctor_recommended_range']
        dr_from = dr.get('from') or ''
        dr_to = dr.get('to') or ''
        dr_days = dr.get('days') or req.get('days_granted_by_doctor') or None
        req_from = req.get('from_date') or ''
        req_to = req.get('to_date') or ''
        req_wd = int(req.get('requested_working_days') or req.get('workdays') or 0)
        if not has_doc:
            dc_status = "NOT_RUN"; dc_pass = False; dc_severity="INFO"
            dc_note = "Không có chứng từ nên bỏ qua bước kiểm tra ngày khớp."
        elif is_unreadable_doc:
            dc_status = "FAIL"; dc_pass = False; dc_severity="CRITICAL"
            dc_note = "Chứng từ không đọc được (UNREADABLE). Không thể xác minh khoảng ngày bác sĩ chỉ định."
        else:
            in_range = False
            if dr_from and dr_to and req_from and req_to:
                try:
                    from datetime import date as _d
                    df1, dt1 = _d.fromisoformat(dr_from), _d.fromisoformat(dr_to)
                    df2, dt2 = _d.fromisoformat(req_from), _d.fromisoformat(req_to)
                    in_range = df1 <= df2 and dt2 <= dt1
                except Exception: in_range = False
            missing_range = not dr_from or not dr_to
            overlap_issue = False
            if dr_days is not None and req_wd:
                overlap_issue = req_wd > int(dr_days)
            if missing_range:
                dc_status = "WARN"; dc_pass = False; dc_severity = "WARNING"
            elif overlap_issue or not in_range:
                dc_status = "FAIL"; dc_pass = False; dc_severity = "CRITICAL"
            else:
                dc_status = "PASS"; dc_pass = True; dc_severity = "SUCCESS"
            dc_note = "Yêu cầu: {rf} → {rt} ({rw} ngày làm việc) · Bác sĩ chỉ định: {df} → {dt} ({dd} ngày nghỉ) — Kết quả: {res}.".format(
                rf = req_from or 'N/A', rt = req_to or 'N/A', rw = req_wd,
                df = dr_from or 'Chưa đọc được', dt = dr_to or 'Chưa đọc được',
                dd = str(dr_days) if dr_days is not None else 'Chưa đọc được',
                res = ('✅ Khoảng yêu cầu nằm trong khoảng bác sĩ chỉ định' if dc_pass else
                       '⚠ Khoảng yêu cầu vượt ngoài / ngày yêu cầu nhiều hơn số ngày bác sĩ cấp')
            )
        add_node(6,"VLM_DATE_COVERAGE",dc_status, dc_pass, dc_note,
                               title_vi="VLM - Đối chiếu khoảng ngày nghỉ vs. bác sĩ chỉ định",
                       severity=dc_severity, include=shows_proof)
        # ===== NODE 7. VLM - Correlation score (diagnosis ↔ reason + dates) =====
        cs = req.get('correlation_score')
        issues = req.get('correlation_issues') or []
        if not has_doc:
            c_status = "NOT_RUN"; c_pass = False; c_severity="INFO"
            c_note = "Không có chứng từ nên bỏ qua bước correlation."
        elif is_unreadable_doc:
            c_status = "FAIL"; c_pass = False; c_severity="CRITICAL"
            c_note = "Chứng từ không đọc được (UNREADABLE). Không thể đánh giá độ khớp nội dung (0.00 / 1.00)."
        elif cs is None:
            c_status = "WARN"; c_pass = False; c_severity="WARNING"
            c_note = "Chưa tính được correlation_score (VLM chưa đọc đủ các trường để đánh giá độ khớp)."
        else:
            cf = float(cs)
            if cf >= 0.85:
                c_status = "PASS"; c_pass = True; c_severity = "SUCCESS"; tier = "RẤT KHỚP"
            elif cf >= 0.7:
                c_status = "PASS"; c_pass = True; c_severity = "SUCCESS"; tier = "KHỚP Ở MỨC CHẤP NHẬN"
            elif cf >= 0.5:
                c_status = "WARN"; c_pass = False; c_severity = "WARNING"; tier = "CHƯA KHỚP HOÀN TOÀN"
            else:
                c_status = "FAIL"; c_pass = False; c_severity = "CRITICAL"; tier = "KHÔNG KHỚP NHIỀU (nghi vấn giả)"
            top_issues = list(issues or [])[:3]
            c_note = "Correlation score = {sc:.2f} / 1.00 → Đánh giá: {tier}. {n} cảnh báo: {top}.".format(
                sc = cf, tier = tier, n = len(issues or []),
                top = '; '.join(top_issues) if top_issues else '(không có vấn đề đáng kể)'
            )
        add_node(7,"VLM_CORRELATION",c_status, c_pass, c_note,
                               title_vi="VLM - Đánh giá độ khớp (diagnosis ↔ lý do nghỉ ↔ số ngày)",
                       severity=c_severity, include=shows_proof)
        # ===== NODE 8. PROOF VERIFICATION status =====
        pv_status_raw = proof.get('proof_verification_status') if isinstance(proof,dict) else (req.get('status') or '')
        decision_raw = (req.get('decision') or '').casefold()
        human_read = _s(req.get('human_readable_explanation')) or (llm.get('human_readable_explanation') if isinstance(llm,dict) else '') or ''
        why = (llm.get('why_escalated') if isinstance(llm,dict) else '') or ''
        if decision_raw == 'need_correction':
            doc_based_errors = {'doc_illegible', 'doc_field_missing', 'name_mismatch', 'medical_days_mismatch', 'proof_review_required'}
            if (req.get('error_code') or '').casefold() in doc_based_errors:
                pv_status = 'ESCALATED'; pv_pass = True; pv_severity = 'WARNING'
            else:
                pv_status = 'FAIL'; pv_pass = False; pv_severity = 'CRITICAL'
        elif decision_raw == 'escalate':
            pv_status = 'ESCALATED'; pv_pass = True; pv_severity = 'WARNING'
        elif decision_raw == 'auto_approve' or decision_raw in ('approved_by_human_override','approve'):
            pv_status = 'PASS'; pv_pass = True; pv_severity = 'SUCCESS'
        else:
            pv_status = 'WARN'; pv_pass = True; pv_severity = 'WARNING'
        pv_note = "Kết quả bước này: decision = {d} · Trạng thái = {s}. {r}{w}".format(
            d = _s(req.get('decision')), s = _s(req.get('status')),
            r = ('Giải thích: ' + human_read + '. ') if human_read else '',
            w = ('Lý do escalate: ' + _s(why)) if (decision_raw == 'escalate' and why) else '',
        )
        add_node(8,"PROOF_VERIFICATION",pv_status, pv_pass, pv_note,
                               title_vi="Trạng thái xác minh chứng từ (VERIFIED / UNVERIFIED / REJECTED)",
                       severity=pv_severity, include=shows_proof)
        # ===== NODE 9. AUTHORITY =====
        tr = req.get('target_role') or 'NONE'
        TR_VI = {
            'DIRECT_MANAGER':'Quản lý trực tiếp (tầng 1 duyệt)',
            'DEPARTMENT_HEAD':'Trưởng bộ phận / Trưởng khoa',
            'HR': 'Bộ phận Nhân sự (HR)',
            'HRD':'Giám đốc Nhân sự',
            'CEO':'Tổng Giám đốc / CEO',
            'EMPLOYEE':'Nhân viên tự bổ sung / sửa lại',
            'NONE':'Tự động duyệt (không cần người xem xét)',
            '':'Tự động duyệt (không cần người xem xét)',
        }
        wd = int(req.get('requested_working_days') or req.get('workdays') or 0)
        ltype_val = ctx.get('leave_type_vn') if isinstance(ctx,dict) else _s(req.get('canonical_leave_type') or req.get('leave_type'))
        if str(tr).casefold() == 'none' or tr == 'NONE' or not tr:
            a_status="PASS"; a_pass=True; a_severity="SUCCESS"
        else:
            a_status="ESCALATED"; a_pass=True; a_severity="WARNING"
        a_note = "Số ngày làm việc: {wd}. Loại nghỉ: {lt}. Cấp duyệt tiếp theo: {label}.".format(
            wd = wd, lt = ltype_val, label = TR_VI.get(str(tr), str(tr) or 'N/A')
        )
        checklist.append(_node(9,"AUTHORITY",a_status, a_pass, a_note,
                               title_vi="Xác định thẩm quyền phê duyệt (Authority matrix theo loại nghỉ & số ngày)",
                               severity=a_severity))
        # ===== NODE 10. NOTICE / OPERATIONAL =====
        unc = (req.get('uncertainty_category') or '').casefold()
        ec = (req.get('error_code') or '').casefold()
        is_op_violation = 'violation' in unc or 'violation' in ec or 'notice' in ec
        is_op_warn = is_op_violation and (decision_raw == 'escalate')
        if 'notice' not in ec:
            n_status = "PASS"; n_pass = True; n_severity = "SUCCESS"
            n_note = "Đủ thời hạn báo trước theo quy định của bộ phận (không có vi phạm notice period)."
        else:
            if is_op_warn:
                n_status = "WARN"; n_pass = True; n_severity = "WARNING"
            else:
                n_status = "FAIL"; n_pass = False; n_severity = "WARNING"
            ec_label_vn = ''
            if 'notice' in ec:
                if 'operational' in ec: ec_label_vn = 'Thời hạn báo trước dưới ngưỡng hoạt động (dưới 3 ngày đối với nghỉ 3-5d)'
                elif 'violation' in ec: ec_label_vn = 'Thời hạn báo trước không đạt chuẩn theo chính sách (vd báo 1d cho đơn 5d)'
            elif 'out_of_policy' in unc: ec_label_vn = 'Vượt ngoài phạm vi quy định (Manager có thể bỏ qua nếu phù hợp)'
            n_note = "{vn}. {final}".format(
                vn = ec_label_vn or _s(req.get('human_readable_explanation')) or 'Vi phạm thời hạn báo trước.',
                final = 'Quản lý có thể ghi chú và xem xét ngoại lệ nếu cần.'
            )
        checklist.append(_node(10,"NOTICE",n_status, n_pass, n_note,
                               title_vi="Kiểm tra thời hạn báo trước & cảnh báo hoạt động",
                               severity=n_severity))
        # ===== NODE 11. TEAM QUOTA (30% rule) =====
        # (lưu ý: hiện tại engine đã tính, ta hiển thị qua error / clause nếu có)
        quota_breach = 'TEAM' in (req.get('error_code') or '').upper() or any('TEAM' in str(x).upper() for x in (list((llm.get('applied_policy_clauses') if isinstance(llm,dict) else []) or [])[:5]))
        if quota_breach:
            q_status='WARN'; q_pass=True; q_severity='WARNING'
            q_note = 'Phát hiện team hiện tại đang có nhiều nhân viên nghỉ đồng thời (có thể vượt ngưỡng 30%). Trưởng bộ phận cần đối chiếu & chấp nhận hoặc điều chỉnh lịch.'
        else:
            q_status='PASS'; q_pass=True; q_severity='SUCCESS'
            q_note = 'Team hiện tại KHÔNG vi phạm giới hạn nghỉ đồng thời (quy tắc 30% team vẫn trong khoảng an toàn).'
        checklist.append(_node(11,"TEAM_QUOTA",q_status, q_pass, q_note,
                               title_vi="Kiểm tra tỷ lệ nhân sự nghỉ đồng thời trong team (quy tắc 30%)",
                               severity=q_severity))
        # ===== NODE 12. FINAL DECISION =====
        d = (req.get('decision') or '').upper() or 'NOT_RUN'
        DEC_VI = {
            'AUTO_APPROVE':'Tự động DUYỆT (đạt tiêu chí quy định)',
            'ESCALATE':'CHUYỂN LÊN cấp có thẩm quyền xem xét',
            'NEED_CORRECTION':'YÊU CẦU nhân viên bổ sung / sửa lại',
            'REQUEST_INFO':'CẦN THÊM THÔNG TIN rõ hơn trước khi quyết định',
            'AUTO_REJECT':'Tự động TỪ CHỐI (vi phạm nghiêm trọng)',
            'NO_LEAVE_REQUIRED':'Không cần ghi nhận phép (quy tắc trong ngày / off-site được)',
            'NOT_RUN':'Chưa chạy bộ đánh giá',
        }
        target_vi = TR_VI.get(str(tr), str(tr) or '')
        final_note = "Kết quả cuối cùng từ Rule Engine: {d} — {vi} · Status đơn = {st} · Người xem xét tiếp = {tr}{tvi}.".format(
            d = d, vi = DEC_VI.get(d, d), st = _s(req.get('status')),
            tr = tr, tvi = (' (' + target_vi + ')') if (target_vi and str(tr).casefold() != 'none') else ''
        )
        final_pass = d in ('AUTO_APPROVE','ESCALATE','REQUEST_INFO','AUTO_REJECT','NO_LEAVE_REQUIRED')
        final_sev = 'SUCCESS' if d == 'AUTO_APPROVE' else ('WARNING' if d in ('ESCALATE','REQUEST_INFO') else 'CRITICAL' if d == 'AUTO_REJECT' else 'INFO')
        checklist.append(_node(12,"FINAL_DECISION",d, final_pass, final_note,
                               title_vi="Quyết định cuối cùng từ bộ máy rule + VLM",
                               severity=final_sev))
        # ===== NODE 13. LLM Summary =====
        llm_keys = sorted(llm.keys()) if isinstance(llm,dict) else []
        llm_nat = (llm.get('summary_natural_vn') if isinstance(llm,dict) else None) or ''
        if llm and llm_nat:
            l_status="PASS"; l_pass=True; l_severity="SUCCESS"
            note_preview = llm_nat if len(llm_nat) < 420 else llm_nat[:417] + '...'
            l_note = "LLM dịch sang văn phong tiếng Việt tự nhiên (tổng hợp từ fields + rule):\n  {p}\n(Tổng số {k} key structured trong summary JSON).".format(
                p = note_preview, k = len(llm_keys)
            )
        elif llm:
            l_status="WARN"; l_pass=False; l_severity="WARNING"
            l_note = "LLM summary có {k} keys nhưng CHƯA tạo bản tóm tắt tiếng Việt tự nhiên (chưa load engine hoặc logic tắt).".format(k=len(llm_keys))
        else:
            l_status="NOT_RUN"; l_pass=False; l_severity="INFO"
            l_note = "Chưa có bản tóm tắt LLM (đơn cũ tạo trước khi nâng cấp orchestration)."
        checklist.append(_node(13,"LLM_SUMMARY",l_status, l_pass, l_note,
                               title_vi="Bản tóm tắt tiếng Việt tự nhiên từ LLM (tổng hợp cho người xem xét)",
                               severity=l_severity))
        # ---- vlm_fields enriched with Vietnamese labels included inline via top-level extra dict ----
        vlm_fields_ext = {}
        raw_fields = ['doc_patient_name','doc_diagnosis','has_red_stamp','has_doctor_signature',
                      'correlation_score','correlation_issues','days_granted_by_doctor']
        for k in raw_fields:
            vlm_fields_ext[k] = req.get(k)
        return {'success':True,'request_id':request_id,
                'decision':req.get('decision'),'status':req.get('status'),
                'target_role':req.get('target_role'),
                'error_code':req.get('error_code'),'uncertainty_category':req.get('uncertainty_category'),
                'human_readable_reason': req.get('human_readable_explanation') or (llm.get('summary_natural_vn') if isinstance(llm,dict) else None),
                'actionable_question': req.get('actionable_question') or (llm.get('actionable_question') if isinstance(llm,dict) else None),
                'proof':proof,
                'proof_source':{
                    'proof_id':req.get('proof_id'),
                    'proof_type':pt_label,
                    'attachment_type':req.get('attachment_type'),
                    'readability': proof.get('document_readability') if isinstance(proof,dict) else 'UNKNOWN',
                },
                'vlm_analysis': req.get('vlm_analysis_json') or {},
                'vlm_fields': vlm_fields_ext,
                'vlm_fields_labels': {
                    'doc_patient_name': 'Tên bệnh nhân trên giấy khám',
                    'doc_diagnosis': 'Chẩn đoán lâm sàng ghi trên chứng từ',
                    'has_red_stamp': 'Có dấu đỏ của cơ sở y tế (1/0)',
                    'has_doctor_signature': 'Có chữ ký bác sĩ điều trị (1/0)',
                    'days_granted_by_doctor': 'Số ngày nghỉ bác sĩ đề nghị (ngày)',
                    'correlation_score': 'Độ khớp giữa lý do & giấy tờ (0-1, ≥0.7 OK)',
                    'correlation_issues': 'Các điểm chưa khớp cụ thể (danh sách)',
                },
                'llm_summary': llm or {},
                'engine_result': req.get('result_json'),
                'decision_tree_checklist': checklist}

@router.post('/{request_id}/resubmit')
def resubmit(request_id,payload: RequestFacts,actor_id=Depends(actor)):
    t0 = time.perf_counter()
    res = service.resubmit(request_id,actor_id,payload.model_dump())
    total_api_ms = round((time.perf_counter() - t0) * 1000, 2)
    if isinstance(res, dict):
        res['total_api_ms'] = total_api_ms
        if isinstance(res.get('llm_summary_json'), dict):
            res['llm_summary_json'].setdefault('timings', {})['total_api_ms'] = total_api_ms
    return {'success':True,'data':res,'total_api_ms':total_api_ms}

@router.post('/{request_id}/human-decision')
def submit_human_decision(request_id,payload: HumanDecisionInput,actor_id=Depends(actor)):
    t0 = time.perf_counter()
    if payload.approver_id and payload.approver_id!=actor_id: raise st.AccessDenied('Người duyệt không khớp.')
    res = service.process_human_decision(request_id,payload.feedback_text,actor_id,
        payload.action_type,payload.updated_fields.model_dump(mode='json',exclude_unset=True))
    total_api_ms = round((time.perf_counter() - t0) * 1000, 2)
    if isinstance(res, dict):
        res['total_api_ms'] = total_api_ms
        if isinstance(res.get('llm_summary_json'), dict):
            res['llm_summary_json'].setdefault('timings', {})['total_api_ms'] = total_api_ms
    return {'success':True,'data':res,'total_api_ms':total_api_ms}

@router.post('/{request_id}/cancel')
def cancel(request_id,actor_id=Depends(actor)):
    return {'success':True,'data':service.cancel(request_id,actor_id)}

class RevokeDecisionInput(BaseModel):
    reason: str = ''

@router.post('/{request_id}/revoke')
def revoke(request_id,payload: RevokeDecisionInput,actor_id=Depends(actor)):
    return {'success':True,'data':service.cancel(request_id,actor_id,True,payload.reason)}
