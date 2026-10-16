"""Authoritative workflow. Financial mutation and state transitions are atomic."""
import time
import sys
import os
import uuid
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
root=Path(__file__).resolve().parents[2]
for name in ('core','backend'):
    if str(root/name) not in sys.path: sys.path.insert(0,str(root/name))
from domain import (RequestFacts, HumanFeedbackResolution, EditableFields,
                    names_approximately_match, should_deduct_annual_balance, VerifiedProof,
                    relationship_display_label)
from rule_engine import LeaveRuleEngine
from taxonomy import ErrorCode, DecisionType
from calendar_service import CalendarService
from vlm_inspector import inspect_document_with_vlm, VLMInspectionOutput, _resolve_persona_config, PERSONA_CONFIGS, _enforce_name_match_verdict
from ai.ai_stack import VLM_TARGET_MODEL
import storage as st
import json
from datetime import date

STATES={'AUTO_APPROVE':'COMPLETED','NO_LEAVE_REQUIRED':'COMPLETED','AUTO_REJECT':'REJECTED',
        'NEED_CORRECTION':'WAITING_EMPLOYEE','ESCALATE':'PENDING_ESCALATION',
        'PENDING_HANDOVER':'PENDING_HANDOVER'}
# Loại nghỉ mà người được khám / ghi tên trên chứng từ phải là chính nhân viên làm đơn
SELF_SUBJECT_LEAVE_TYPES={'SICK_MEDICAL','MEDICAL_EMERGENCY','WORK_ACCIDENT','MATERNITY'}


def _vlm_output_from_json(cj, proof_type_raw=None):
    """Dựng lại VLMInspectionOutput từ JSON VLM đã lưu (document_summary/flags lồng nhau) mà không gọi lại mô hình."""
    from vlm_inspector import VLMInspectionOutput as _VLMOut, ProofExtraction as _PE, ProofType as _PT, _normalize_proof_type
    _ds = cj.get('document_summary') or {}
    _fl = cj.get('flags') or {}
    _ca = cj.get('correlation_analysis') or {}
    _dr = _ds.get('doctor_recommended_range') or {}
    _pt = _normalize_proof_type(proof_type_raw or cj.get('proof_type') or 'NONE')
    def _safe_date(v):
        if not v: return None
        try: return date.fromisoformat(str(v))
        except Exception: return None
    try:
        _pe = _PE(
            proof_type=_pt,
            patient_name=_ds.get('patient_name'),
            issuer=_ds.get('issuer'),
            issue_date=_safe_date(_ds.get('issue_date')),
            recommended_from_date=_safe_date(_dr.get('from')),
            recommended_to_date=_safe_date(_dr.get('to')),
            signature_present=(_fl.get('signature_present_on_scan') if _fl.get('signature_present_on_scan') is not None else _fl.get('has_doctor_signature')),
            digital_signature_present=_fl.get('digital_signature_present'),
            document_readability=_fl.get('document_readability') or 'READABLE',
            fields_detected=list(cj.get('raw_fields_detected') or []),
            is_open_ended=_ds.get('is_open_ended'),
            requires_followup_proof=_ds.get('requires_followup_proof'),
            admission_date=_safe_date(_ds.get('admission_date')),
            discharge_date=_safe_date(_ds.get('discharge_date')),
            maternity_phase=_ds.get('maternity_phase') or (cj.get('proof_extra') or {}).get('maternity_phase'),
            expected_due_date=_safe_date(_ds.get('expected_due_date')),
            patient_name_match=_ca.get('patient_name_match'),
            patient_name_match_reason=_ca.get('patient_name_match_reason'),
            reason_diagnosis_match=_ca.get('reason_diagnosis_match'),
            reason_diagnosis_match_reason=_ca.get('reason_diagnosis_match_reason'),
            deceased_name=_ds.get('deceased_name'),
            subject_name=_ds.get('subject_name'),
            partner_name=_ds.get('partner_name'),
            event_type=_ds.get('event_type'),
            wedding_date=_safe_date(_ds.get('wedding_date')),
            date_of_death=_safe_date(_ds.get('date_of_death')),
            funeral_date=_safe_date(_ds.get('funeral_date')),
            event_date=_safe_date(_ds.get('event_date')),
            injury_date=_safe_date(_ds.get('injury_date')),
            relationship_label=_ds.get('relationship_label') or _ds.get('relationship'),
            relationship_to_employee=_ds.get('relationship_to_employee') or _ds.get('relationship'),
            has_red_stamp=_fl.get('has_red_stamp'),
            has_doctor_signature=_fl.get('has_doctor_signature'),
            is_tampered=_fl.get('is_tampered'),
            ai_edited=_fl.get('ai_generated_or_edited'),
            needs_manager_review=_fl.get('needs_manager_review'),
        )
    except Exception:
        _pe = _PE(proof_type=_PT.NONE)
    return _VLMOut(
        vlm_analysis_json=cj,
        doc_patient_name=_ds.get('patient_name'),
        doc_diagnosis=_ds.get('diagnosis'),
        has_red_stamp=_fl.get('has_red_stamp'),
        has_doctor_signature=_fl.get('has_doctor_signature'),
        is_tampered=_fl.get('is_tampered'),
        ai_edited=_fl.get('ai_generated_or_edited'),
        days_granted_by_doctor=_dr.get('days'),
        correlation_score=_ca.get('score'),
        correlation_issues=list(_ca.get('issues') or []),
        persona_role_used=cj.get('inspector_persona'),
        escalation_reasons_json=list(cj.get('escalation_flags') or []),
        proof_extraction=_pe,
        vlm_error=cj.get('vlm_error'),
    )


# Theo policy_rules.md §3, tổ chức chỉ có Lead Team (DIRECT_MANAGER) và CEO duyệt đơn; rule engine
# vẫn có thể chọn HR / HRD / DEPARTMENT_HEAD. Nếu không ai giữ vai trò đó trong phòng ban, chuyển đơn
# sang vai trò thay thế (cùng quy tắc với database.normalize_pending_approval_roles) để đơn không bị kẹt.
_ROLE_FALLBACK = {'HR': 'DIRECT_MANAGER', 'HRD': 'CEO', 'DEPARTMENT_HEAD': 'CEO', 'DIRECT_MANAGER': 'CEO'}

def _role_is_staffed(conn, role, department, exclude_employee=None):
    """Có ai (ngoài chính người nộp đơn) giữ vai trò này cho phòng ban không. Người nộp không được tự duyệt,
    nên quản lý tự nộp đơn thì vai trò DIRECT_MANAGER của chính họ coi như không có người."""
    return conn.execute("SELECT 1 FROM actor_roles WHERE role=? AND (department_scope='*' OR department_scope=?) AND employee_id IS NOT ? LIMIT 1",
                        (role, department, exclude_employee)).fetchone() is not None

# policy_rules.md §3.1: nghỉ thai sản do CEO duyệt → khi không có HR, hồ sơ thai sản lên thẳng CEO.
_LEAVE_TYPE_FALLBACK = {'MATERNITY': {'HR': 'CEO'}}

def _resolve_staffed_role(conn, role, department, exclude_employee=None, leave_type=None):
    """Đi lên chuỗi thay thế (HR → DIRECT_MANAGER → CEO, DEPARTMENT_HEAD/HRD → CEO) tới vai trò có người duyệt được."""
    fallback = {**_ROLE_FALLBACK, **_LEAVE_TYPE_FALLBACK.get(str(leave_type or '').upper(), {})}
    name = getattr(role, 'value', role)
    seen = set()
    while name in fallback and name not in seen and not _role_is_staffed(conn, name, department, exclude_employee):
        seen.add(name)
        name = fallback[name]
    return name

def _route_to_staffed_roles(conn, result, department, employee_id=None, leave_type=None):
    from taxonomy import TargetApproverRole
    def resolve(role):
        resolved = _resolve_staffed_role(conn, role, department, employee_id, leave_type)
        if resolved == getattr(role, 'value', role) or not _role_is_staffed(conn, resolved, department, employee_id):
            return role
        return TargetApproverRole(resolved)
    original = getattr(result.target_role, 'value', result.target_role)
    result.target_role = resolve(result.target_role) if result.target_role else None
    result.approval_roles = list(dict.fromkeys(resolve(r) for r in result.approval_roles))
    if result.escalation:
        result.escalation.target_role = result.target_role
    if (original == 'DIRECT_MANAGER' and getattr(result.target_role, 'value', None) == 'CEO'
            and employee_id and _role_is_staffed(conn, 'DIRECT_MANAGER', department)):
        note = ' Người nộp đơn là Quản lý trực tiếp của phòng ban nên đơn chuyển Tổng Giám đốc duyệt (không tự phê duyệt).'
        result.human_readable_explanation = (result.human_readable_explanation or '') + note
        if result.escalation:
            result.escalation.plain_reason = (result.escalation.plain_reason or '') + note
    if original == 'HR' and getattr(result.target_role, 'value', None) == 'CEO':
        result.human_readable_explanation = (result.human_readable_explanation or '').replace('Phòng Nhân sự (HR)', 'Tổng Giám đốc (CEO)')
        result.quick_action_options = ['APPROVE', 'REJECT', 'REQUEST_MORE_INFO']
        if result.escalation:
            result.escalation.plain_reason = (result.escalation.plain_reason or '').replace('Phòng Nhân sự (HR)', 'Tổng Giám đốc (CEO)')
    if original == 'HR' and getattr(result.target_role, 'value', None) == 'DIRECT_MANAGER':
        # Lead Team đối chiếu chứng từ thay HR → được phép duyệt; sửa lời nhắn cho đúng người nhận.
        def retarget(text):
            return ((text or '').replace('HR vui lòng xác minh hồ sơ/cấu hình; không thể duyệt bỏ qua điều kiện này.',
                                         'Bạn có phê duyệt sau khi đã đối chiếu chứng từ không?')
                    .replace('HR cần', 'Lead Team cần')
                    .replace('Phòng Nhân sự (HR)', 'Lead Team (quản lý trực tiếp)'))
        result.human_readable_explanation = retarget(result.human_readable_explanation)
        result.actionable_question = retarget(result.actionable_question)
        result.quick_action_options = ['APPROVE', 'REJECT', 'REQUEST_MORE_INFO']
        if result.escalation:
            result.escalation.plain_reason = retarget(result.escalation.plain_reason)
            result.escalation.actionable_question = result.actionable_question or ''

class LeaveOrchestratorService:
    def __init__(self, agent=None, clock=None, calendar=None, register_global=True):
        self.agent=agent
        self.calendar=calendar or CalendarService()
        self.clock=clock or (lambda: datetime.now(self.calendar.timezone))
        # Instance tạm (vd Verify với đồng hồ giả lập) không được thay orchestrator của worker kiểm định chứng từ.
        if register_global:
            try:
                from services.inspection_service import GLOBAL_INSPECTION_SERVICE
                GLOBAL_INSPECTION_SERVICE.set_orchestrator(self)
            except Exception:
                pass

    def _evaluate(self, conn, record, facts, granted=None, waived=None, enable_llm_polish=False, skip_vlm=False, precomputed_vlm=None):
        t_eval_0 = time.perf_counter()
        ctx=st.load_context(conn,record['employee_id'],facts,record['submitted_at'],record['id'],granted,waived,self.calendar)

        # ---- Step VLM (new): inspect document via VLM when attachment provided ----
        att = (getattr(facts,'attachment_type', None) or '').strip()
        proof_id = getattr(facts,'proof_id',None)
        proof_row = None
        if proof_id:
            proof_row = conn.execute('SELECT * FROM proof_documents WHERE id=?',(proof_id,)).fetchone()
            proof_row = dict(proof_row) if proof_row else None
            if proof_row and not (att and att.casefold()!='none'):
                # derive att from proof storage_name/mime when attachment_type was not set explicitly
                from pathlib import Path
                name = Path(proof_row['storage_name']).name.casefold()
                mime = (proof_row.get('mime_type') or '').casefold()
                pt = (proof_row.get('proof_type') or '').casefold()
                if 'pdf' in name or 'pdf' in mime:
                    att = 'pdf_attachment'
                elif 'png' in name or 'jpg' in name or 'jpeg' in name or 'image' in mime:
                    att = 'image_attachment'
                else:
                    att = proof_row.get('proof_type') or 'generic_attachment'
        if str(getattr(facts, 'leave_type', '')).upper() == 'ANNUAL':
            skip_vlm = True
        vlm_out: VLMInspectionOutput | None = None
        needs_vlm = not skip_vlm and (bool(att and att.casefold() != 'none') or bool(proof_row))
        if needs_vlm:
            f_date, t_date = None, None
            try:
                if getattr(facts,'from_date',None): f_date = date.fromisoformat(str(facts.from_date))
            except Exception: pass
            try:
                if getattr(facts,'to_date',None): t_date = date.fromisoformat(str(facts.to_date))
            except Exception: pass
            proof_type_hint = None
            readability_hint = None
            doc_flags = {}
            attachment_for_vlm = att
            if proof_row:
                proof_type_hint = proof_row['proof_type']
                readability_hint = proof_row.get('document_readability')
                doc_flags = {
                    'has_signature': bool(proof_row.get('signature_present')) if proof_row.get('signature_present') is not None else None,
                    'has_stamp': None,
                    'is_tampered': None,
                    'ai_edited': None,
                }
                # If real file exists, pass the absolute real path so Ollama wrapper reads the PNG directly
                from pathlib import Path as _P
                uploads_dir = _P(os.getenv('LEAVE_UPLOAD_DIR', str(_P(__file__).resolve().parents[1] / 'uploads')))
                candidate = uploads_dir / proof_row['storage_name']
                if candidate.exists():
                    attachment_for_vlm = str(candidate)
                elif att:
                    attachment_for_vlm = att

            # Đảm bảo nếu attachment_for_vlm là file có tên tiếng Việt / non-ASCII,
            # đổi tên bằng UUID để các hàm mở ảnh VLM (OpenCV, PIL, Ollama) không gặp lỗi đường dẫn
            if attachment_for_vlm and os.path.isfile(attachment_for_vlm):
                att_p = _P(attachment_for_vlm)
                if any(ord(c) > 127 for c in att_p.name):
                    import uuid as _uuid, shutil as _shutil
                    uploads_dir = _P(os.getenv('LEAVE_UPLOAD_DIR', str(_P(__file__).resolve().parents[1] / 'uploads')))
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    uuid_cand = uploads_dir / f"{_uuid.uuid4().hex}{att_p.suffix or '.png'}"
                    try:
                        _shutil.copy2(attachment_for_vlm, uuid_cand)
                        attachment_for_vlm = str(uuid_cand)
                    except Exception:
                        pass
            vlm_out: VLMInspectionOutput | None = precomputed_vlm
            if vlm_out is None:
                precomputed_mock = None
                cached_vlm_json = None
                if proof_row and proof_row.get('vlm_analysis_json'):
                    try:
                        cached_vlm_json = json.loads(proof_row['vlm_analysis_json'])
                    except Exception:
                        cached_vlm_json = None

                # ---- Optimisation: nếu proof_documents đã có kết quả VLM thật (READY),
                # tái sử dụng trực tiếp mà KHÔNG pass qua inspect_document_with_vlm như mock_data.
                # Reason: real VLM JSON dùng cấu trúc document_summary.* (nested), còn mock profile
                # dùng flat keys (doc_patient_name, doc_diagnosis, ...). Nếu pass nhầm sang mock_data
                # thì vlm_inspector sẽ không map được fields → document_summary trống rỗng.
                _proof_ready = (
                    proof_row
                    and proof_row.get('inspection_status') == 'READY'
                    and cached_vlm_json
                    and (
                        cached_vlm_json.get('inspection_mode', '').startswith('OLLAMA_REAL')
                        or cached_vlm_json.get('inspection_mode') == 'VLM_CACHE_HIT'
                    )
                    and (
                        (
                            (cached_vlm_json.get('_inspection_context') or {}).get('leave_type')
                            == str(getattr(facts, 'leave_type', '')).upper()
                            and (
                                (cached_vlm_json.get('_inspection_context') or {}).get('reason_category') or ''
                            ) == str(getattr(getattr(facts, 'reason_category', ''), 'value', getattr(facts, 'reason_category', '')) or '').upper()
                        )
                        or (
                            not cached_vlm_json.get('_inspection_context')
                            and str(getattr(facts, 'leave_type', '')).upper() == 'SICK_MEDICAL'
                            and not getattr(facts, 'reason_category', None)
                            and proof_row.get('proof_type') in {
                                'MEDICAL_LEAVE_CERTIFICATE', 'MEDICAL_RECORD_SUMMARY',
                                'LAB_RESULT', 'HOSPITAL_DISCHARGE',
                            }
                        )
                    )
                )
                if _proof_ready:
                    vlm_out = _vlm_output_from_json(cached_vlm_json, proof_row.get('proof_type') or cached_vlm_json.get('proof_type'))
                else:
                    # Chỉ dùng cached JSON như mock khi không phải real VLM result
                    if cached_vlm_json and cached_vlm_json.get('inspection_mode', '').startswith('OLLAMA_REAL'):
                        pass  # đã được xử lý ở trên
                    elif cached_vlm_json:
                        precomputed_mock = cached_vlm_json

                try:
                    if vlm_out is None:
                        if proof_row and proof_row.get('inspection_status') == 'FAILED' and not precomputed_mock:
                            raise RuntimeError(proof_row.get('vlm_error') or 'Proof inspection failed')
                        vlm_out = inspect_document_with_vlm(
                            leave_type=str(getattr(facts,'leave_type','')),
                            employee_name=getattr(ctx,'employee_name',None),
                            reason=str(getattr(facts,'reason','') or ''),
                            attachment_path_or_type=attachment_for_vlm,
                            from_date=f_date, to_date=t_date,
                            workdays=0,
                            mock_data=precomputed_mock,
                            proof_type_hint=proof_type_hint,
                            document_readability_hint=readability_hint,
                            doc_flags=doc_flags,
                            allow_mock_fallback=False,
                            reason_category=getattr(facts, 'reason_category', None),
                        )
                except Exception as _vlm_exc:
                    # Nếu VLM hỏng nghiêm trọng: gắn vlm_error trực tiếp vào record VLM column
                    # để Manager panel thấy lỗi rõ ràng thay vì crash pipeline
                    from vlm_inspector import VLMInspectionOutput, ProofExtraction, ProofType
                    vlm_err_msg = f"VLM_EXCEPTION: {type(_vlm_exc).__name__}: {_vlm_exc}"
                    vlm_json_shell = {
                        "inspector_persona": None,
                        "target_model": VLM_TARGET_MODEL,
                        "inspection_mode": "VLM_RUNTIME_ERROR",
                        "inspected_at": datetime.now().isoformat(timespec="seconds"),
                        "vlm_error": vlm_err_msg,
                        "document_summary": {
                            "patient_name": None, "diagnosis": None, "issuer": None,
                            "issue_date": None, "doctor_recommended_range": {"from": None, "to": None, "days": None},
                        },
                        "flags": {
                            "has_red_stamp": None, "has_doctor_signature": None,
                            "signature_present_on_scan": None, "digital_signature_present": None,
                            "document_readability": "UNKNOWN", "is_tampered": None, "ai_generated_or_edited": None,
                        },
                        "correlation_analysis": {"score": 0.0, "issues": [vlm_err_msg], "requested_workdays": 0},
                        "escalation_flags": ["VLM_INFERENCE_FAILED"],
                        "raw_fields_detected": [],
                    }
                    vlm_out = VLMInspectionOutput(
                        vlm_analysis_json=vlm_json_shell,
                        doc_patient_name=None, doc_diagnosis=None,
                        has_red_stamp=None, has_doctor_signature=None,
                        is_tampered=None, ai_edited=None,
                        days_granted_by_doctor=None,
                        correlation_score=0.0,
                        correlation_issues=[vlm_err_msg],
                        persona_role_used="VLM_RUNTIME_ERROR",
                        escalation_reasons_json=["VLM_INFERENCE_FAILED"],
                        proof_extraction=ProofExtraction(proof_type=ProofType.NONE),
                        vlm_error=vlm_err_msg,
                    )
            # Inject VLM proof fields into context so rule engine PROOF stage uses REAL VLM extraction
            # and not just storage heuristics.
            if vlm_out and vlm_out.proof_extraction and getattr(ctx.proof, 'proof_verification_status', 'UNVERIFIED') != 'VERIFIED':
                proof_dict = vlm_out.proof_extraction.model_dump(mode='python')
                existing_ver_status = getattr(ctx.proof, 'proof_verification_status', 'UNVERIFIED')
                existing_notes = getattr(ctx.proof, 'verification_notes', None)
                # Preserve storage-provided verification status; otherwise default to UNVERIFIED
                proof_dict['proof_verification_status'] = existing_ver_status
                proof_dict['verification_notes'] = existing_notes
                if (not proof_dict.get('proof_type') or str(proof_dict['proof_type']) in ('NONE', 'ProofType.NONE')):
                    if proof_row and proof_row.get('proof_type'):
                        proof_dict['proof_type'] = proof_row['proof_type']
                    elif getattr(ctx.proof, 'proof_type', None):
                        pt = ctx.proof.proof_type
                        proof_dict['proof_type'] = pt.value if hasattr(pt, 'value') else pt

                v_analysis = vlm_out.vlm_analysis_json or {}
                doc_sum = v_analysis.get('document_summary') or {}
                flags = v_analysis.get('flags') or {}
                if not proof_dict.get('patient_name'):
                    proof_dict['patient_name'] = doc_sum.get('patient_name') or vlm_out.doc_patient_name
                if not proof_dict.get('issuer'):
                    proof_dict['issuer'] = doc_sum.get('issuer')
                if not proof_dict.get('issue_date'):
                    proof_dict['issue_date'] = doc_sum.get('issue_date')
                dr = doc_sum.get('doctor_recommended_range') or {}
                if not proof_dict.get('recommended_from_date') and dr.get('from'):
                    proof_dict['recommended_from_date'] = dr['from']
                if not proof_dict.get('recommended_to_date') and dr.get('to'):
                    proof_dict['recommended_to_date'] = dr['to']
                if proof_dict.get('signature_present') is None:
                    # Giữ None khi VLM không xác định được: None = chưa rõ, False = chắc chắn không có chữ ký.
                    sig_values = (vlm_out.has_doctor_signature, flags.get('has_doctor_signature'), flags.get('signature_present_on_scan'))
                    proof_dict['signature_present'] = True if any(v is True for v in sig_values) else (
                        False if any(v is False for v in sig_values) else None)
                if not proof_dict.get('document_readability') or proof_dict.get('document_readability') == 'UNKNOWN':
                    proof_dict['document_readability'] = flags.get('document_readability') or 'READABLE'

                try:
                    ctx.proof = VerifiedProof.model_validate(proof_dict)
                except Exception:
                    pass  # storage fallback stays if validation fails on VLM edge data
            # Calculate workdays using calendar service to refine correlation
            if vlm_out and hasattr(ctx,'from_date') and hasattr(ctx,'to_date'):
                try:
                    d1 = date.fromisoformat(str(ctx.from_date))
                    d2 = date.fromisoformat(str(ctx.to_date))
                    wd = len(self.calendar.working_dates(d1,d2)) if d1 and d2 and d1<=d2 else 0
                    # Re-score correlation with exact calculated workdays (skip if document is UNREADABLE)
                    is_unreadable = getattr(vlm_out.proof_extraction, 'document_readability', '') in ('UNREADABLE', 'ILLEGIBLE')
                    if wd and vlm_out.proof_extraction and not is_unreadable:
                        from vlm_inspector import (
                            _resolve_reason_diagnosis_match,
                            _score_correlation,
                            is_provisional_correlation_issue,
                        )
                        pe = vlm_out.proof_extraction
                        # Bước tiền kiểm chạy khi chưa biết lý do nghỉ nên kết luận đối chiếu ở đó chỉ là tạm thời:
                        # tính lại với lý do thật rồi ghi đè, thay vì chỉ cộng thêm và giữ mãi câu cũ.
                        resolved_match, resolved_reason = _resolve_reason_diagnosis_match(
                            str(getattr(facts, 'reason', '')),
                            vlm_out.doc_diagnosis or '',
                            pe.reason_diagnosis_match,
                            pe.reason_diagnosis_match_reason,
                        )
                        pe.reason_diagnosis_match = resolved_match
                        pe.reason_diagnosis_match_reason = resolved_reason
                        new_score, new_additional_issues, new_doctor_days = _score_correlation(
                            employee_name=getattr(ctx,'employee_name',''),
                            reason=str(getattr(facts,'reason','')),
                            recommended_from=pe.recommended_from_date,
                            recommended_to=pe.recommended_to_date,
                            requested_from=d1, requested_to=d2,
                            diagnosis=vlm_out.doc_diagnosis,
                            days_granted_by_doctor=vlm_out.days_granted_by_doctor,
                            requested_workdays=wd,
                            patient_name_on_doc=pe.patient_name,
                            patient_name_match=pe.patient_name_match,
                            patient_name_match_reason=pe.patient_name_match_reason,
                            reason_diagnosis_match=resolved_match,
                            reason_diagnosis_match_reason=resolved_reason,
                        )
                        if new_score is not None:
                            vlm_dict = dict(vlm_out.vlm_analysis_json or {})
                            kept_issues = [
                                issue for issue in (vlm_out.correlation_issues or [])
                                if not is_provisional_correlation_issue(issue)
                            ]
                            merged = list(dict.fromkeys(kept_issues + list(new_additional_issues)))
                            vlm_out.correlation_score = new_score
                            vlm_out.correlation_issues = merged
                            if new_doctor_days is not None:
                                vlm_out.days_granted_by_doctor = new_doctor_days
                            ca = vlm_dict.get('correlation_analysis', {}); ca['score'] = new_score; ca['issues'] = merged; ca['requested_workdays'] = wd
                            ca['reason_diagnosis_match'] = resolved_match; ca['reason_diagnosis_match_reason'] = resolved_reason
                            vlm_dict['correlation_analysis'] = ca
                            dr = vlm_dict.get('document_summary',{}); dr['doctor_recommended_range'] = dict(dr.get('doctor_recommended_range',{}) or {}); dr['doctor_recommended_range']['days'] = new_doctor_days
                            vlm_out.vlm_analysis_json = vlm_dict
                except Exception: pass

        # VLM đọc ảnh lúc chưa biết tên nhân viên nên kết luận "khớp tên" của VLM không có giá trị: với chứng từ mà
        # người khám là chính nhân viên, code tự đối chiếu tên trên giấy với tên nhân sự trước khi chạy bộ quy tắc.
        leave_type_value = getattr(ctx.leave_type, 'value', ctx.leave_type)
        if leave_type_value in SELF_SUBJECT_LEAVE_TYPES and ctx.proof is not None and ctx.proof.patient_name and ctx.employee_name:
            name_match, name_match_reason = _enforce_name_match_verdict(
                ctx.proof.patient_name, ctx.employee_name, ctx.proof.patient_name_match, ctx.proof.patient_name_match_reason)
            ctx.proof.patient_name_match, ctx.proof.patient_name_match_reason = name_match, name_match_reason
            if vlm_out is not None and isinstance(vlm_out.vlm_analysis_json, dict):
                ca = vlm_out.vlm_analysis_json.setdefault('correlation_analysis', {})
                ca['patient_name_match'], ca['patient_name_match_reason'] = name_match, name_match_reason

        t_rule_0 = time.perf_counter()
        result=LeaveRuleEngine.evaluate(ctx,self.calendar)
        _route_to_staffed_roles(conn,result,ctx.department,record.get('employee_id'),getattr(facts,'leave_type',None))
        rule_engine_ms = round((time.perf_counter() - t_rule_0) * 1000, 3)
        record.update(employee_name=ctx.employee_name,department=ctx.department,
            from_date=facts.from_date,to_date=facts.to_date,workdays=result.requested_working_days or 0,
            leave_type=facts.leave_type or '',canonical_leave_type=facts.leave_type,reason_category=facts.reason_category,
            reason=facts.reason,handover_person_id=facts.handover_person_id,handover_person_name=facts.handover_person_name,
            handover_status=record.get('handover_status'),handover_decided_at=record.get('handover_decided_at'),handover_decline_reason=record.get('handover_decline_reason'),
            attachment_type=facts.attachment_type,proof_id=facts.proof_id,facts_json=facts.model_dump(mode='json'),
            decision=result.decision.value,status=STATES[result.decision.value],
            requested_calendar_days=result.requested_calendar_days,requested_working_days=result.requested_working_days,
            deducted_days=0,annual_balance_change=0,target_role=result.target_role,
            uncertainty_category=result.uncertainty_category,error_code=result.error_code,
            human_readable_explanation=result.human_readable_explanation,actionable_question=result.actionable_question,
            quick_action_options=result.quick_action_options,applied_policy_clauses=result.applied_policy_clauses,
            decision_trace=result.decision_trace,result_json=result.model_dump(mode='json'),policy_version=result.policy_version,
            updated_at=self.clock().isoformat(),legacy_reconciliation_required=0)
        # ---- Persist 13 VLM + 1 LLM summary DB columns so Manager panels see real data
        if vlm_out is not None:
            record['vlm_analysis_json'] = vlm_out.vlm_analysis_json
            record['doc_patient_name'] = vlm_out.doc_patient_name
            record['doc_diagnosis'] = vlm_out.doc_diagnosis
            record['has_red_stamp'] = vlm_out.has_red_stamp
            record['has_doctor_signature'] = vlm_out.has_doctor_signature
            record['is_tampered'] = vlm_out.is_tampered
            record['ai_edited'] = vlm_out.ai_edited
            record['days_granted_by_doctor'] = vlm_out.days_granted_by_doctor
            record['correlation_score'] = vlm_out.correlation_score
            record['correlation_issues'] = vlm_out.correlation_issues
            record['persona_role_used'] = vlm_out.persona_role_used
            record['escalation_reasons_json'] = vlm_out.escalation_reasons_json
        # Deterministic Vietnamese template summary: không gọi LLM trên critical path.
        def _v_enum(value):
            if value is None: return ''
            return str(value.value) if hasattr(value,'value') else str(value)
        decision_val = _v_enum(result.decision)
        status_val = STATES.get(result.decision.value, STATES.get('ESCALATE','PENDING_ESCALATION'))
        error_code = _v_enum(result.error_code)
        target_role = _v_enum(result.target_role)
        # ---- human-readable Vietnamese summary (template fallback) ----
        ROLE_VI = {
            'DIRECT_MANAGER':'Quản lý trực tiếp',
            'DEPARTMENT_HEAD':'Trưởng bộ phận',
            'HR':'Nhân sự (HR)',
            'HRD':'Giám đốc Nhân sự',
            'CEO':'Tổng Giám đốc',
            'EMPLOYEE':'Nhân viên (nộp lại / bổ sung)',
            'NONE':'—',
            '':'—',
        }
        DECISION_VI = {
            'AUTO_APPROVE':'Tự động duyệt (không cần người xem xét)',
            'ESCALATE':'Chuyển lên người có thẩm quyền phê duyệt',
            'NEED_CORRECTION':'Yêu cầu nhân viên bổ sung / sửa lại hồ sơ',
            'AUTO_REJECT':'Từ chối theo quy tắc',
            'REQUEST_INFO':'Cần thêm thông tin rõ hơn',
            'NO_LEAVE_REQUIRED':'Không cần ghi nhận phép',
        }
        ERROR_VI = {
            'OK':'—',
            'NOTICE_PERIOD_VIOLATION':'[Nộp đơn gấp vi phạm thời hạn báo trước] Thời gian nộp đơn chưa đủ hạn báo trước theo quy chế. Đơn cần Quản lý trực tiếp xem xét đặc cách.',
            'NOTICE_PERIOD_VIOLATED':'[Nộp đơn gấp vi phạm thời hạn báo trước] Thời gian nộp đơn chưa đủ hạn báo trước theo quy chế. Đơn cần Quản lý trực tiếp xem xét đặc cách.',
            'NOTICE_PERIOD_OPERATIONAL':'[Báo trước gấp] Thời hạn báo trước dưới ngưỡng vận hành thông thường. Đơn cần Quản lý trực tiếp ghi nhận.',
            'DOC_ILLEGIBLE':'[Chứng từ mờ / khó nhận diện] Ảnh chứng từ khó đọc hoặc thiếu nét xác nhận. Cần Quản lý trực tiếp kiểm tra bản gốc hoặc yêu cầu bổ sung.',
            'PROOF_REVIEW_REQUIRED':'[Chứng từ y tế cần đối chiếu] Đã tiếp nhận chứng từ y tế. Cần Phòng Nhân sự (HR) đối soát thông tin chuyên môn trước khi duyệt.',
            'PROOF_MISSING':'[Thiếu chứng từ bắt buộc] Chế độ nghỉ yêu cầu phải có giấy tờ xác minh. Vui lòng bổ sung chứng từ hợp lệ trước khi đơn được xử lý.',
            'DOC_FIELD_MISSING':'[Thiếu thông tin chứng từ] Một số thông tin quan trọng trên chứng từ chưa đầy đủ hoặc chưa khớp với đơn. Vui lòng bổ sung.',
            'DURATION_OVER_AI_LIMIT':'[Vượt trần tự duyệt của AI] Số ngày nghỉ trên 2 ngày vượt hạn mức tự duyệt. Đơn chuyển Quản lý trực tiếp xem xét theo phân cấp.',
            'DURATION_OVER_MANAGER_LIMIT':'[Vượt thẩm quyền Quản lý trực tiếp] Số ngày nghỉ trên 5 ngày vượt mức Quản lý trực tiếp. Đơn chuyển Trưởng bộ phận xem xét.',
            'TEAM_QUOTA_BREACH':'[Tỷ lệ vắng mặt phòng ban cao] Đội ngũ có trên 30% nhân sự vắng mặt cùng ngày. Cần Quản lý trực tiếp xem xét phân công.',
            'TEAM_QUOTA_EXCEEDED':'[Tỷ lệ vắng mặt phòng ban cao] Đội ngũ có trên 30% nhân sự vắng mặt cùng ngày. Cần Quản lý trực tiếp xem xét phân công.',
            'BALANCE_EXCEEDED':'[Không đủ số dư phép] Số ngày xin nghỉ vượt quá quỹ phép năm hiện có. Vui lòng giảm số ngày hoặc nộp đơn nghỉ không lương.',
            'BALANCE_CHECK_REQUIRED':'[Kiểm tra số dư phép] Cần đối soát lại số dư phép năm trước khi hoàn tất phê duyệt.',
            'OUT_OF_POLICY':'[Ngoài phạm vi quy chế thường quy] Đơn có yếu tố ngoại lệ. Cần chuyển cấp có thẩm quyền xem xét trực tiếp.',
            'UNCERTAIN_FACTS':'[Dữ liệu chứng từ chưa rõ] Thông tin trích xuất từ chứng từ chưa đủ độ tin cậy. Cần kiểm tra lại hồ sơ.',
            'AUTHORITY_REQUIRED':'[Cần phê duyệt theo thẩm quyền] Số ngày nghỉ vượt trần tự động. Đơn chuyển tới cấp thẩm quyền theo quy định.',
            'FLAG_ABUSE_PATTERN':'[Phát hiện nhiều đơn nghỉ ngắn lặp lại] Phát hiện chuỗi đơn nghỉ phép rời rạc trong tháng. Cần Quản lý trực tiếp xem xét kế hoạch.',
            'LONG_TERM_UNPAID':'[Nghỉ không lương dài hạn] Đơn nghỉ không lương kéo dài. Cần Trưởng bộ phận / Ban Giám đốc xem xét phê duyệt.',
        }
        DECISION_VI = {
            'AUTO_APPROVE':'Tự động duyệt',
            'ESCALATE':'Chuyển cấp thẩm quyền xem xét',
            'AUTO_REJECT':'Tự động từ chối',
            'NO_LEAVE_REQUIRED':'Không cần nghỉ phép',
        }
        decision_vi = DECISION_VI.get(decision_val, decision_val)
        def _fmt(d, key, default='—'):
            v = d.get(key) if isinstance(d,dict) else None
            if v is None or v == '' or v == 0: return default
            if isinstance(v, float): return f'{v:.2f}'
            return v
        vlm_fields_present = vlm_out is not None
        corr_score = record.get('correlation_score') or (vlm_out.correlation_score if vlm_out else None)
        rs = record.get('has_red_stamp') if 'has_red_stamp' in record else (vlm_out.has_red_stamp if vlm_out else None)
        sig = record.get('has_doctor_signature') if 'has_doctor_signature' in record else (vlm_out.has_doctor_signature if vlm_out else None)
        tamper = record.get('is_tampered') if 'is_tampered' in record else (vlm_out.is_tampered if vlm_out else None)
        ai_ed = record.get('ai_edited') if 'ai_edited' in record else (vlm_out.ai_edited if vlm_out else None)
        diag = record.get('doc_diagnosis') if 'doc_diagnosis' in record else (vlm_out.doc_diagnosis if vlm_out else None)
        doc_patient = record.get('doc_patient_name') if 'doc_patient_name' in record else (vlm_out.doc_patient_name if vlm_out else None)
        doctor_days = record.get('days_granted_by_doctor') if 'days_granted_by_doctor' in record else (vlm_out.days_granted_by_doctor if vlm_out else None)
        proof_extraction = getattr(ctx, 'proof', None)
        dfd = getattr(proof_extraction, 'recommended_from_date', None)
        dtd = getattr(proof_extraction, 'recommended_to_date', None)
        vlm_analysis_data = record.get('vlm_analysis_json') or (getattr(vlm_out, 'vlm_analysis_json', None) if vlm_out else {}) or {}
        if not dfd and isinstance(vlm_analysis_data, dict):
            dr = (vlm_analysis_data.get('document_summary') or {}).get('doctor_recommended_range') or {}
            dfd = dr.get('from')
            dtd = dr.get('to')
        requested_wd = result.requested_working_days or 0
        requested_cd = result.requested_calendar_days or 0
        emp_n = ctx.employee_name or 'Nhân viên'
        ltype = _v_enum(facts.leave_type)
        LTYPE_VI = {
            'ANNUAL':'Nghỉ phép năm',
            'SICK_MEDICAL':'Nghỉ ốm đau (có giấy khám bệnh)',
            'MEDICAL_EMERGENCY':'Nghỉ bệnh cấp cứu',
            'WORK_ACCIDENT':'Nghỉ tai nạn lao động',
            'MATERNITY':'Nghỉ thai sản',
            'SPECIAL_PAID':'Nghỉ đặc cách có lương',
            'STATUTORY_UNPAID':'Nghỉ phép chế độ không lương',
            'UNPAID_OTHER':'Nghỉ không lương khác',
        }
        ltype_vi = LTYPE_VI.get(ltype, ltype or 'Không xác định')
        proof_relevant = ltype in {
            'SPECIAL_PAID', 'STATUTORY_UNPAID', 'SICK_MEDICAL',
            'MEDICAL_EMERGENCY', 'WORK_ACCIDENT', 'MATERNITY',
        }
        from_d = _v_enum(facts.from_date)
        to_d = _v_enum(facts.to_date)
        reason = (getattr(facts, 'reason', None) or '').strip()
        # ---- Build template text theo định dạng Bullet Points (•) chuẩn mực ----
        t_tmpl_0 = time.perf_counter()
        handover_name = getattr(facts, 'handover_person_name', None) or 'Đồng nghiệp trong bộ phận'
        clauses_str = ", ".join(str(x) for x in list(result.applied_policy_clauses or [])) or "AUTH-01"
        err_vi = ERROR_VI.get(error_code) or (result.human_readable_explanation or error_code or '—')
        role_vi = ROLE_VI.get(target_role, target_role or 'Cấp quản lý')

        # Resolve persona config and schema key
        reason_cat = getattr(facts, 'reason_category', None)
        persona_cfg = _resolve_persona_config(ltype, reason_cat)
        schema_key = persona_cfg.get('schema_key', 'ADMINISTRATIVE')
        pe = proof_extraction or (getattr(vlm_out, 'proof_extraction', None) if vlm_out else None)
        if schema_key == 'WEDDING' and vlm_out:
            wedding_flags = (vlm_out.vlm_analysis_json or {}).get('flags') or {}
            sig = wedding_flags.get('signature_present_on_scan')
        reason_cat_value = getattr(reason_cat, 'value', reason_cat)
        wedding_event_type = getattr(pe, 'event_type', None)
        is_child_marriage = (
            schema_key == 'WEDDING'
            and (reason_cat_value == 'CHILD_MARRIAGE' or wedding_event_type == 'CHILD_MARRIAGE')
        )

        bullet_lines = [
            f"• Đơn xin nghỉ: Nhân viên {emp_n} nộp đơn {ltype_vi} {requested_wd or requested_cd or 1} ngày làm việc (từ {from_d} đến {to_d}) với lý do \"{reason or 'Nghỉ theo kế hoạch cá nhân'}\".",
            f"• Bàn giao & Quỹ phép: Người nhận bàn giao là {handover_name}; số dư quỹ phép đủ điều kiện.",
        ]

        if vlm_fields_present and proof_relevant:
            doc_parts = []
            if schema_key == 'SICK_MEDICAL':
                if doc_patient: doc_parts.append(f"Bệnh nhân: {doc_patient}")
                if diag: doc_parts.append(f"Chẩn đoán: {diag}")
                if doctor_days: doc_parts.append(f"Bác sĩ cho nghỉ: {doctor_days} ngày ({dfd} → {dtd})")
                elif dfd and dtd: doc_parts.append(f"Thời gian chỉ định: {dfd} → {dtd}")
                if rs is True: doc_parts.append("Có dấu đỏ cơ sở y tế")
                if sig is True: doc_parts.append("Có chữ ký bác sĩ")
                bullet_lines.append(f"• Chứng từ y tế ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm chứng từ hợp lệ'}.")
            elif schema_key == 'EMERGENCY':
                adm_d = getattr(pe, 'admission_date', None) or dfd
                is_oo = getattr(pe, 'is_open_ended', None)
                em_diag = getattr(pe, 'emergency_diagnosis', None) or diag
                if doc_patient: doc_parts.append(f"Bệnh nhân: {doc_patient}")
                if em_diag: doc_parts.append(f"Lý do cấp cứu: {em_diag}")
                if adm_d: doc_parts.append(f"Tiếp nhận viện: {adm_d}")
                if is_oo: doc_parts.append("Đang cấp cứu (chưa ra viện, cần bổ sung giấy ra viện sau)")
                elif getattr(pe, 'discharge_date', None): doc_parts.append(f"Ra viện: {getattr(pe, 'discharge_date', None)}")
                if rs is True or getattr(pe, 'has_hospital_stamp', None) is True: doc_parts.append("Có dấu bệnh viện")
                if sig is True: doc_parts.append("Có chữ ký bác sĩ")
                bullet_lines.append(f"• Hồ sơ cấp cứu ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm giấy cấp cứu'}.")
            elif schema_key == 'WEDDING':
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                part_n = getattr(pe, 'partner_name', None)
                wed_d = getattr(pe, 'wedding_date', None) or dfd
                iss = getattr(pe, 'issuer', None)
                if sub_n and part_n: doc_parts.append(f"Cặp đôi: {sub_n} & {part_n}")
                elif sub_n: doc_parts.append(f"Người kết hôn: {sub_n}")
                if wed_d: doc_parts.append(f"Ngày cưới: {wed_d}")
                if iss: doc_parts.append(f"Cơ quan cấp: {iss}")
                if rs is True: doc_parts.append("Có dấu đỏ UBND/cơ quan")
                bullet_lines.append(f"• Chứng từ hôn sự ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm giấy kết hôn / thiệp cưới'}.")
            elif schema_key == 'BEREAVEMENT':
                dec_n = getattr(pe, 'deceased_name', None) or doc_patient
                rel_lbl = getattr(pe, 'relationship_label', None) or getattr(pe, 'relationship_to_employee', None)
                if not rel_lbl and reason_cat_value:
                    rel_lbl = relationship_display_label(reason_cat_value, None)
                dod = getattr(pe, 'date_of_death', None) or dfd
                iss = getattr(pe, 'issuer', None)
                if dec_n: doc_parts.append(f"Người quá cố: {dec_n}")
                if rel_lbl: doc_parts.append(f"Quan hệ: {rel_lbl}")
                if dod: doc_parts.append(f"Ngày mất: {dod}")
                if getattr(pe, 'funeral_date', None): doc_parts.append(f"Tang lễ: {getattr(pe, 'funeral_date', None)}")
                if iss: doc_parts.append(f"Đơn vị cấp: {iss}")
                if rs is True: doc_parts.append("Có dấu đỏ")
                bullet_lines.append(f"• Chứng từ tang chế ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm giấy chứng tử'}.")
            elif schema_key == 'STATUTORY':
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                rel_emp = getattr(pe, 'relationship_to_employee', None) or getattr(pe, 'relationship_label', None)
                if not rel_emp and reason_cat_value:
                    rel_emp = relationship_display_label(reason_cat_value, None)
                ev_d = getattr(pe, 'event_date', None) or dfd
                ev_conf = getattr(pe, 'evidence_confidence', None)
                if sub_n: doc_parts.append(f"Thân nhân: {sub_n}")
                if rel_emp: doc_parts.append(f"Mối quan hệ: {rel_emp}")
                if ev_d: doc_parts.append(f"Ngày sự kiện: {ev_d}")
                if ev_conf: doc_parts.append(f"Độ tin cậy: {ev_conf}")
                if rs is True: doc_parts.append("Có dấu đỏ")
                bullet_lines.append(f"• Chứng từ thân nhân BLLĐ ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm xác nhận thân nhân'}.")
            elif schema_key == 'MATERNITY':
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                mat_ph = getattr(pe, 'maternity_phase', None)
                due_d = getattr(pe, 'expected_due_date', None) or dfd
                bhxh = getattr(pe, 'bhxh_code', None)
                if sub_n: doc_parts.append(f"Thai phụ: {sub_n}")
                if mat_ph: doc_parts.append(f"Giai đoạn: {mat_ph}")
                if due_d: doc_parts.append(f"Ngày dự sinh/sinh: {due_d}")
                if bhxh: doc_parts.append(f"Mã BHXH: {bhxh}")
                if doctor_days: doc_parts.append(f"Chỉ định nghỉ: {doctor_days} ngày ({dfd} → {dtd})")
                if rs is True: doc_parts.append("Có dấu đỏ")
                bullet_lines.append(f"• Hồ sơ thai sản ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm hồ sơ thai sản'}.")
            elif schema_key == 'WORK_ACCIDENT':
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                inj_d = getattr(pe, 'injury_description', None) or diag
                wp_rel = getattr(pe, 'is_workplace_related', None)
                inj_dt = getattr(pe, 'injury_date', None) or dfd
                if sub_n: doc_parts.append(f"Người bị nạn: {sub_n}")
                if inj_d: doc_parts.append(f"Thương tật: {inj_d}")
                if wp_rel is True: doc_parts.append("Liên quan công việc")
                if inj_dt: doc_parts.append(f"Ngày xảy ra: {inj_dt}")
                if getattr(pe, 'has_bhxh_stamp', None) is True: doc_parts.append("Có dấu BHXH")
                if rs is True: doc_parts.append("Có dấu đỏ cơ sở y tế")
                bullet_lines.append(f"• Hồ sơ tai nạn lao động ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm hồ sơ tai nạn'}.")
            else:
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                purp = getattr(pe, 'document_purpose', None)
                v_fr = getattr(pe, 'valid_from', None) or dfd
                v_to = getattr(pe, 'valid_to', None) or dtd
                if sub_n: doc_parts.append(f"Chủ giấy tờ: {sub_n}")
                if purp: doc_parts.append(f"Mục đích: {purp}")
                if v_fr and v_to: doc_parts.append(f"Thời hạn: {v_fr} → {v_to}")
                if rs is True: doc_parts.append("Có dấu đỏ")
                bullet_lines.append(f"• Giấy tờ hành chính ({persona_cfg['persona']}): {', '.join(doc_parts) if doc_parts else 'Đã đính kèm giấy tờ hành chính'}.")
        else:
            bullet_lines.append("• Tình trạng chứng từ: Không yêu cầu chứng từ đối với loại nghỉ này.")

        if result.decision == DecisionType.AUTO_APPROVE:
            bullet_lines.append(f"• Kết quả thẩm định: Hệ thống Tự động duyệt (AUTO_APPROVE) — đạt đầy đủ tiêu chí theo chính sách ({clauses_str}).")
            bullet_lines.append("• Kết luận: Đã tự động duyệt, không cần chuyển cấp quản lý xem xét.")
        elif result.decision == DecisionType.NEED_CORRECTION:
            bullet_lines.append(f"• Kết quả đối soát: Hồ sơ chưa đủ cơ sở tự duyệt và cần đối chiếu lại ({err_vi}).")
            bullet_lines.append("• Kết luận: Chuyển lên người có thẩm quyền xem xét trước khi quyết định cuối cùng.")
        else:
            bullet_lines.append(f"• Kết quả đối soát: Cần người có thẩm quyền phê duyệt ({err_vi}).")
            bullet_lines.append(f"• Kết luận: Chuyển {role_vi} xem xét và quyết định.")

        template_summary_full = "\n".join(bullet_lines)

        # ---- Quick actions (Vietnamese - template fallback) ----
        QUICK_VI = {
            'APPROVE_OVERRIDE':'Duyệt (ghi chú nếu cần)',
            'REQUEST_MORE_INFO':'Yêu cầu giải thích / bổ sung thêm thông tin',
            'REJECT':'Từ chối (nêu lý do)',
            'ESCALATE_FURTHER':'Chuyển tiếp cấp cao hơn',
            'WAIVE_NOTICE':'Bỏ qua quy định báo trước',
            'WAIVE_QUOTA':'Bỏ qua giới hạn team 30%',
        }
        quick_vi = [QUICK_VI.get(str(x), str(x)) for x in list(result.quick_action_options or [])]
        policy_vi = []
        for pc in list(result.applied_policy_clauses or []):
            s = str(pc)
            if 'SICK' in s and 'AUTHORITY' in s: s = 'Chính sách: Nghỉ ốm đau cần Quản lý xác minh dựa trên số ngày'
            elif 'ANNUAL' in s and 'AUTHORITY' in s: s = 'Chính sách: Nghỉ phép năm cần cấp trên xem xét dựa trên số ngày'
            elif 'NOTICE' in s: s = 'Chính sách: Quy định báo trước khi nghỉ'
            elif 'TEAM' in s: s = 'Chính sách: Tỷ lệ nghỉ đồng thời trong team (30%)'
            elif 'BALANCE' in s: s = 'Chính sách: Kiểm tra số dư phép năm'
            elif 'PROOF' in s: s = 'Chính sách: Yêu cầu chứng từ / giấy tờ hợp lệ'
            policy_vi.append(s)
        why_escalated_vi = ''
        if result.decision == DecisionType.ESCALATE:
            parts = []
            if error_code and ERROR_VI.get(error_code, error_code) and ERROR_VI.get(error_code, error_code) != '—':
                parts.append(ERROR_VI.get(error_code, error_code))
            if target_role and target_role != 'NONE':
                parts.append('cần ' + ROLE_VI.get(target_role, target_role) + ' xem xét')
            why_escalated_vi = '. '.join(p for p in parts if p).capitalize()
        elif result.decision == DecisionType.AUTO_APPROVE:
            why_escalated_vi = 'Không escalate — đơn đã tự động duyệt thành công theo chính sách.'
        else:
            why_escalated_vi = 'Cần bổ sung thông tin hồ sơ.'
        warnings_vi = []
        for w in list(getattr(result,'warnings',[]) or []):
            s = str(w)
            if 'NOTICE' in s.upper(): s = 'Cảnh báo: thời hạn báo trước chưa đạt chuẩn, nhưng Manager có thể bỏ qua với ghi chú.'
            warnings_vi.append(s)
        aq_vi = result.actionable_question or ''
        if not aq_vi or '?' not in aq_vi:
            if result.decision == DecisionType.ESCALATE and error_code:
                if 'DOC' in error_code:
                    aq_vi = 'Nội dung giấy tờ hơi khó xem, bạn có chấp nhận duyệt đặc cách với đơn này hay yêu cầu tải lại bản rõ hơn không?'
                elif 'NOTICE' in error_code:
                    aq_vi = 'Thời hạn báo trước chưa đủ, bạn có chấp nhận bỏ qua quy định này và phê duyệt đơn không?'
                elif 'TEAM' in error_code or 'QUOTA' in error_code:
                    aq_vi = 'Team hiện tại có nhiều người nghỉ cùng lúc, bạn có chấp nhận phê duyệt đơn này hay sắp xếp lại lịch nghỉ không?'
                elif 'AUTHORITY' in error_code or 'DURATION' in error_code:
                    aq_vi = 'Số ngày nghỉ vượt ngưỡng tự duyệt, bạn có xác nhận phê duyệt đơn hay cần chuyển cấp cao hơn xem xét không?'
                else:
                    aq_vi = 'Dựa trên các thông tin phân tích bên trên, bạn có phê duyệt đơn này, từ chối, hay cần thêm thông tin nào không?'
            elif result.decision == DecisionType.NEED_CORRECTION:
                aq_vi = 'Đơn này còn thiếu thông tin hoặc có điểm nghi vấn, bạn có muốn nhân viên nộp lại hồ sơ đầy đủ hơn không?'
            elif result.decision == DecisionType.AUTO_APPROVE:
                aq_vi = ''

        cs = float(corr_score) if corr_score is not None else -1.0
        if cs >= 0.85: correlation_tier = "RẤT KHỚP"
        elif cs >= 0.7: correlation_tier = "KHỚP"
        elif cs >= 0.5: correlation_tier = "CHƯA KHỚP"
        elif cs >= 0: correlation_tier = "KHÔNG KHỚP"
        elif result.decision == DecisionType.AUTO_APPROVE: correlation_tier = "TỰ ĐỘNG DUYỆT (HỢP LỆ)"
        else: correlation_tier = "—"
        integrity_parts = []
        if rs is True: integrity_parts.append('đã thấy dấu đỏ')
        elif rs is False: integrity_parts.append('không thấy dấu đỏ')
        signature_label = 'chữ ký cơ quan/người có thẩm quyền' if schema_key == 'WEDDING' else 'chữ ký bác sĩ'
        if sig is True: integrity_parts.append(f'có {signature_label}')
        elif sig is False: integrity_parts.append(f'thiếu {signature_label}')
        if tamper is True: integrity_parts.append('nghi vấn chỉnh sửa (tampered)')
        if ai_ed is True: integrity_parts.append('nghi vấn được tạo bởi AI')

        integrity_assess = "; ".join(integrity_parts) if integrity_parts else ("Hồ sơ hợp lệ theo quy định." if not vlm_fields_present else "Chứng từ hợp lệ.")

        # Pre-calculated deterministic facts
        if vlm_fields_present:
            if schema_key == 'BEREAVEMENT':
                dec_n = getattr(pe, 'deceased_name', None) or doc_patient
                rel_lbl = getattr(pe, 'relationship_label', None) or getattr(pe, 'relationship_to_employee', None) or 'Thân nhân'
                name_status = f"Chứng từ tang chế: Người mất là '{dec_n or '—'}' ({rel_lbl}). Người nộp đơn là nhân viên '{emp_n}'."
            elif schema_key == 'WEDDING':
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                part_n = getattr(pe, 'partner_name', None)
                m_sub = names_approximately_match(emp_n, sub_n) if (emp_n and sub_n) else False
                m_part = names_approximately_match(emp_n, part_n) if (emp_n and part_n) else False
                if m_sub or m_part:
                    name_status = f"Trùng khớp: Nhân viên '{emp_n}' là đương sự trên giấy kết hôn/thiệp cưới."
                else:
                    name_status = f"Cần đối chiếu tên: Giấy ghi '{sub_n}' & '{part_n}', nhân viên nộp là '{emp_n}'."
            elif schema_key == 'STATUTORY':
                sub_n = getattr(pe, 'subject_name', None) or doc_patient
                rel_emp = getattr(pe, 'relationship_to_employee', None) or getattr(pe, 'relationship_label', None) or 'Thân nhân'
                name_status = f"Chứng từ thân nhân: Người trên giấy là '{sub_n or '—'}' ({rel_emp}). Nhân viên nộp đơn: '{emp_n}'."
            else:
                target_check_name = doc_patient or getattr(pe, 'subject_name', None)
                name_match = names_approximately_match(emp_n, target_check_name) if (emp_n and target_check_name) else None
                name_status = (
                    f"Trùng khớp: '{emp_n}'" if name_match is True
                    else f"BẤT THƯỜNG / KHÔNG KHỚP TÊN: Nhân viên nộp là '{emp_n}', nhưng chứng từ đứng tên '{target_check_name}'" if name_match is False
                    else "Chưa đọc được tên trên chứng từ"
                )

            if schema_key == 'EMERGENCY' and getattr(pe, 'is_open_ended', None):
                diag_status = f"Lý do cấp cứu: '{getattr(pe, 'emergency_diagnosis', None) or diag or reason}'"
                date_status = f"Đơn xin: {from_d} đến {to_d} ({requested_wd} ngày) | Cấp cứu từ: {getattr(pe, 'admission_date', None) or dfd} (Chưa xuất viện - Cấp cứu mở)"
            elif schema_key == 'WEDDING':
                diag_status = f"Lý do kết hôn: '{reason}'"
                date_status = f"Đơn xin: {from_d} đến {to_d} ({requested_wd} ngày) | Ngày cưới trên giấy: {getattr(pe, 'wedding_date', None) or 'Theo đơn'}"
            elif schema_key == 'BEREAVEMENT':
                diag_status = f"Lý do tang chế: '{reason}'"
                date_status = f"Đơn xin: {from_d} đến {to_d} ({requested_wd} ngày) | Ngày mất: {getattr(pe, 'date_of_death', None) or 'Ghi trên giấy'}"
            else:
                diag_status = f"Đơn khai: '{reason}' | Giấy ghi: '{diag or getattr(pe, 'doc_diagnosis', None) or '—'}'" if (reason or diag) else "—"
                date_status = f"Đơn xin: {from_d} đến {to_d} ({requested_wd} ngày làm việc) | Chỉ định y tế: {dfd} đến {dtd} ({doctor_days} ngày)"

            stamp_sig_status = f"Dấu đỏ: {'Có' if rs is True else 'Thiếu' if rs is False else 'Chưa rõ'}, Chữ ký: {'Có' if sig is True else 'Thiếu' if sig is False else 'Chưa rõ'}"
        else:
            name_status = f"Không có chứng từ đính kèm (loại nghỉ '{ltype_vi}' không bắt buộc chứng từ)"
            diag_status = f"Lý do nhân viên khai: '{reason}'"
            date_status = f"Thời gian xin nghỉ: {from_d} đến {to_d} ({requested_wd} ngày làm việc)"
            stamp_sig_status = "Không áp dụng (đơn không có chứng từ)"

        # Deterministic info_sufficient_vn and info_missing_vn for ALL decisions
        info_suf = []
        info_mis = []
        if emp_n:
            info_suf.append(f"Nhân viên nộp đơn: {emp_n} ({getattr(ctx, 'department', None) or 'Bộ phận'})")
        if from_d and to_d:
            info_suf.append(f"Thời gian xin nghỉ: {from_d} → {to_d} ({requested_wd} ngày làm việc)")
        if handover_name and handover_name != 'Không yêu cầu':
            info_suf.append(f"Người nhận bàn giao công việc: {handover_name}")

        rem_days = getattr(ctx, 'remaining_leave_days', 0)
        if (should_deduct_annual_balance(ltype)
            and error_code != 'BALANCE_EXCEEDED'
            and rem_days >= requested_wd):
            info_suf.append(f"Số dư phép năm hiện có ({rem_days} ngày) đủ cho đơn")

        if result.decision == DecisionType.AUTO_APPROVE:
            info_suf.append(f"Thời lượng xin nghỉ ({requested_wd} ngày) trong hạn mức quy định")
            info_suf.append(f"Thời hạn nộp đơn tuân thủ quy định báo trước ({clauses_str})")

        if vlm_fields_present:
            if rs is True: info_suf.append("Chứng từ có dấu mộc đỏ hợp lệ")
            elif rs is False:
                stamp_type = 'UBND/cơ quan' if schema_key == 'WEDDING' else 'bệnh viện/phòng khám'
                info_mis.append(f"Chứng từ thiếu dấu mộc đỏ {stamp_type}")
            signature_type = 'cơ quan/người có thẩm quyền' if schema_key == 'WEDDING' else 'bác sĩ/người cấp giấy'
            if sig is True: info_suf.append(f"Chứng từ có chữ ký {signature_type}")
            elif sig is False: info_mis.append(f"Chứng từ thiếu chữ ký {signature_type}")
            if is_child_marriage:
                subject = getattr(pe, 'subject_name', None) or doc_patient
                partner = getattr(pe, 'partner_name', None)
                names = ' & '.join(name for name in (subject, partner) if name)
                if names:
                    info_suf.append(f"Chứng từ hôn sự ghi nhận cặp đôi: {names}; không yêu cầu tên cặp đôi trùng nhân viên nộp đơn")
            elif schema_key == 'WEDDING' and reason_cat_value == 'SELF_MARRIAGE':
                participants = [getattr(pe, 'subject_name', None) or doc_patient, getattr(pe, 'partner_name', None)]
                if any(name and emp_n and names_approximately_match(emp_n, name) for name in participants):
                    info_suf.append(f"Tên nhân viên ({emp_n}) trùng với một bên trên giấy kết hôn")
                elif any(participants):
                    info_mis.append("Không tìm thấy tên nhân viên trong các bên kết hôn trên chứng từ")
            elif schema_key not in ('WEDDING', 'BEREAVEMENT', 'STATUTORY'):
                if doc_patient and emp_n and names_approximately_match(emp_n, doc_patient):
                    info_suf.append(f"Tên trên chứng từ khớp với nhân viên: {doc_patient}")
                elif doc_patient and emp_n and (emp_n.strip().casefold() != doc_patient.strip().casefold()):
                    info_mis.append(f"Tên trên chứng từ ({doc_patient}) KHÔNG khớp với nhân viên nộp đơn ({emp_n})")

        if error_code == 'TEAM_QUOTA_EXCEEDED':
            info_mis.append("Tỷ lệ vắng mặt trong bộ phận vượt ngưỡng an toàn 30% tại ngày xin nghỉ")
        elif error_code in ('NOTICE_PERIOD_VIOLATED', 'NOTICE_PERIOD_VIOLATION'):
            info_mis.append("Thời hạn nộp đơn chưa đủ số ngày báo trước theo chính sách")
        elif error_code == 'DURATION_OVER_AI_LIMIT':
            info_mis.append(f"Số ngày nghỉ ({requested_wd} ngày) vượt hạn mức phê duyệt tự động")
        elif error_code == 'PROOF_REVIEW_REQUIRED':
            review_label = {
                'WEDDING': 'Chứng từ hôn sự chưa được người có thẩm quyền xác minh',
                'BEREAVEMENT': 'Chứng từ tang chế chưa được người có thẩm quyền xác minh',
                'STATUTORY': 'Chứng từ quan hệ thân nhân chưa được người có thẩm quyền xác minh',
            }.get(schema_key, 'Chứng từ y tế chưa được xác minh' if schema_key in {'SICK_MEDICAL', 'EMERGENCY'} else 'Chứng từ chưa được xác minh')
            info_mis.append(review_label)
        elif error_code == 'PROOF_MISSING':
            info_mis.append("Thiếu chứng từ đính kèm bắt buộc theo quy định của loại nghỉ này")
        elif error_code == 'DOC_ILLEGIBLE':
            info_mis.append("Chứng từ mờ, khó đọc rõ nét chữ ký hoặc mộc")
        elif error_code == 'BALANCE_EXCEEDED':
            info_mis.append(f"Số ngày nghỉ ({requested_wd} ngày) vượt quá số dư phép năm hiện có ({rem_days} ngày)")
        elif error_code == 'FLAG_ABUSE_PATTERN':
            info_mis.append("Đơn thuộc diện kiểm tra phòng chống lạm dụng quỹ phép năm trong tháng")

        for v in getattr(result, 'all_violations', []) or []:
            msg = getattr(v, 'plain_reason', None) or str(v)
            if msg and msg not in info_mis and not any(m in msg for m in info_mis):
                info_mis.append(msg)

        # Keep employee-facing correction errors separate from escalation rules.
        # An escalation can be valid and only needs the authority decision below.
        staff_errors = list(dict.fromkeys(info_mis)) if result.decision in (
            DecisionType.NEED_CORRECTION,
            DecisionType.AUTO_REJECT,
        ) else []
        staff_next_steps = []
        if result.decision == DecisionType.NEED_CORRECTION:
            staff_next_steps.append('Sửa hoặc bổ sung các mục đang báo lỗi rồi nộp lại đơn.')
        elif result.decision == DecisionType.AUTO_REJECT:
            staff_next_steps.append('Điều chỉnh ngày nghỉ hoặc loại nghỉ theo quy định trước khi nộp lại.')
        elif result.decision == DecisionType.ESCALATE and error_code == 'PROOF_REVIEW_REQUIRED':
            staff_next_steps.append('Chờ HR xác minh chứng từ; không cần nộp lại nếu chưa được yêu cầu.')

        manager_suspicions = []
        if schema_key not in ('BEREAVEMENT', 'STATUTORY', 'WEDDING'):
            if doc_patient and emp_n and not names_approximately_match(doc_patient, emp_n):
                manager_suspicions.append(f'Tên trên chứng từ ({doc_patient}) không khớp nhân viên ({emp_n}).')
        if error_code == 'FLAG_ABUSE_PATTERN':
            manager_suspicions.append('Có nhiều đơn phép năm rời rạc trong cùng tháng.')
        if error_code in ('TEAM_QUOTA_EXCEEDED', 'NOTICE_PERIOD_VIOLATED', 'NOTICE_PERIOD_VIOLATION'):
            manager_suspicions.append(ERROR_VI.get(error_code, 'Có sai lệch về điều kiện vận hành.'))
        manager_suspicions = list(dict.fromkeys(manager_suspicions))
        if manager_suspicions:
            manager_risk_level = 'CAO' if tamper is True or ai_ed is True else 'TRUNG BÌNH'
            manager_recommendation = 'Đối chiếu các điểm nghi vấn trước khi quyết định duyệt.'
        else:
            manager_risk_level = 'THẤP'
            manager_recommendation = 'Không phát hiện nghi vấn; xử lý theo kết quả Rule Engine và thẩm quyền.'

        llm_engine_used = "decision_tree_engine (Deterministic Template Fast-Path)"
        llm_call_error = None
        llm_parsed = {
            "summary_natural_vn": template_summary_full,
            "info_sufficient_vn": info_suf,
            "info_missing_vn": info_mis,
            "why_escalated": why_escalated_vi,
            "actionable_question": aq_vi,
            "error_code_human_vn": ERROR_VI.get(error_code, error_code or '—'),
            "target_role_human_vn": ROLE_VI.get(target_role, target_role or '—'),
            "quick_action_options_vn": quick_vi,
            "applied_policy_clauses_vn": policy_vi,
            "warnings": warnings_vi,
            "correlation_tier_vn": correlation_tier,
            "integrity_assessment_vn": integrity_assess,
            "leave_type_vn": ltype_vi,
            "staff_errors_vn": staff_errors,
            "staff_next_steps_vn": staff_next_steps,
            "manager_suspicions_vn": manager_suspicions,
            "manager_risk_level_vn": manager_risk_level,
            "manager_recommendation_vn": manager_recommendation,
        }
        llm_engine_used = "Deterministic Rule Engine (No LLM)"
        llm_call_error = None
        llm_gen_ms = 0.0
        template_ms = round((time.perf_counter() - t_tmpl_0) * 1000, 3)

        # Build structured summary (24 keys như cũ, hoàn toàn tương thích ngược)
        _error_vn = ERROR_VI.get(error_code, error_code or '—')
        _role_vn = ROLE_VI.get(target_role, target_role or '—')
        if llm_parsed:
            if llm_parsed.get('error_code_human_vn'):
                _error_vn = llm_parsed['error_code_human_vn']
            if llm_parsed.get('target_role_human_vn'):
                _role_vn = llm_parsed['target_role_human_vn']
        total_eval_ms = round((time.perf_counter() - t_eval_0) * 1000, 3)
        llm_summary = {
            "decision": decision_val,
            "status": status_val,
            "summary_version": 3,
            "language": "vi-VN",
            "engine": llm_engine_used,
            "llm_call_error": llm_call_error,
            "error_code": error_code,
            "error_code_human_vn": _error_vn,
            "uncertainty_category": _v_enum(result.uncertainty_category),
            "target_role": target_role,
            "target_role_human_vn": _role_vn,
            "human_readable_explanation": result.human_readable_explanation,
            "actionable_question": aq_vi,
            "quick_action_options": list(result.quick_action_options or []),
            "quick_action_options_vn": quick_vi,
            "applied_policy_clauses": list(result.applied_policy_clauses or []),
            "applied_policy_clauses_vn": policy_vi,
            "warnings": warnings_vi or list(getattr(result,'warnings',[]) or []),
            "all_violations_count": len(getattr(result,'all_violations',[]) or []),
            "authority_granted_roles_so_far": list(granted or []),
            "waived_operational_errors": [_v_enum(w) for w in list(waived or [])],
            "why_escalated": why_escalated_vi,
            "summary_natural_vn": template_summary_full,
            "info_sufficient_vn": list(llm_parsed.get('info_sufficient_vn') or []) if llm_parsed else [],
            "info_missing_vn": list(llm_parsed.get('info_missing_vn') or []) if llm_parsed else [],
            "correlation_tier_vn": correlation_tier,
            "integrity_assessment_vn": integrity_assess,
            "context": {
                "employee_name": emp_n,
                "leave_type": ltype,
                "leave_type_vn": ltype_vi,
                "from_date": from_d,
                "to_date": to_d,
                "requested_calendar_days": int(requested_cd or 0),
                "requested_working_days": int(requested_wd or 0),
                "reason": reason,
            },
            "vlm_summary": {
                "fields_extracted": bool(vlm_fields_present),
                "schema_key": schema_key,
                "persona": persona_cfg.get("persona"),
                "decision_tree": persona_cfg.get("decision_tree"),
                "patient_name": doc_patient,
                "diagnosis": diag,
                "doctor_recommended_days": doctor_days,
                "has_red_stamp": rs,
                "has_doctor_signature": None if schema_key == 'WEDDING' else sig,
                "signature_present_on_scan": sig,
                "is_tampered": tamper,
                "ai_edited": ai_ed,
                "correlation_score": corr_score,
                "schema_data": {
                    "is_open_ended": getattr(pe, "is_open_ended", None),
                    "requires_followup_proof": getattr(pe, "requires_followup_proof", None),
                    "admission_date": getattr(pe, "admission_date", None).isoformat() if getattr(pe, "admission_date", None) else None,
                    "discharge_date": getattr(pe, "discharge_date", None).isoformat() if getattr(pe, "discharge_date", None) else None,
                    "emergency_diagnosis": getattr(pe, "emergency_diagnosis", None),
                    "subject_name": getattr(pe, "subject_name", None),
                    "partner_name": getattr(pe, "partner_name", None),
                    "event_type": getattr(pe, "event_type", None),
                    "wedding_date": getattr(pe, "wedding_date", None).isoformat() if getattr(pe, "wedding_date", None) else None,
                    "deceased_name": getattr(pe, "deceased_name", None),
                    "relationship_label": getattr(pe, "relationship_label", None),
                    "relationship_to_employee": getattr(pe, "relationship_to_employee", None),
                    "date_of_death": getattr(pe, "date_of_death", None).isoformat() if getattr(pe, "date_of_death", None) else None,
                    "funeral_date": getattr(pe, "funeral_date", None).isoformat() if getattr(pe, "funeral_date", None) else None,
                    "evidence_confidence": getattr(pe, "evidence_confidence", None),
                    "needs_manager_review": getattr(pe, "needs_manager_review", None),
                    "maternity_phase": getattr(pe, "maternity_phase", None),
                    "expected_due_date": getattr(pe, "expected_due_date", None).isoformat() if getattr(pe, "expected_due_date", None) else None,
                    "bhxh_code": getattr(pe, "bhxh_code", None),
                    "injury_description": getattr(pe, "injury_description", None),
                    "is_workplace_related": getattr(pe, "is_workplace_related", None),
                    "injury_date": getattr(pe, "injury_date", None).isoformat() if getattr(pe, "injury_date", None) else None,
                    "has_bhxh_stamp": getattr(pe, "has_bhxh_stamp", None),
                    "has_hospital_stamp": getattr(pe, "has_hospital_stamp", None),
                    "document_purpose": getattr(pe, "document_purpose", None),
                    "valid_from": getattr(pe, "valid_from", None).isoformat() if getattr(pe, "valid_from", None) else None,
                    "valid_to": getattr(pe, "valid_to", None).isoformat() if getattr(pe, "valid_to", None) else None,
                    "issuer": getattr(pe, "issuer", None),
                },
            },
            "staff_summary": {
                "errors_vn": staff_errors,
                "next_steps_vn": staff_next_steps,
                "summary_natural_vn": '\n'.join(staff_errors) if staff_errors else 'Không phát hiện lỗi cần nhân viên sửa.'
            },
            "manager_summary": {
                "suspicions_vn": manager_suspicions,
                "risk_level_vn": manager_risk_level,
                "recommendation_vn": manager_recommendation,
                "summary_natural_vn": '\n'.join(manager_suspicions) if manager_suspicions else manager_recommendation
            },
            "timings": {
                "rule_engine_ms": rule_engine_ms,
                "template_ms": template_ms,
                "total_eval_ms": total_eval_ms,
                "llm_generation_ms": llm_gen_ms,
            },
        }
        record['llm_summary_json'] = llm_summary
        record['rule_engine_ms'] = rule_engine_ms
        record['template_ms'] = template_ms
        record['total_eval_ms'] = total_eval_ms
        if result.decision==DecisionType.AUTO_APPROVE:
            if facts.handover_person_id:
                record['status'] = 'PENDING_HANDOVER'
                record['handover_status'] = 'PENDING'
                record['handover_decline_reason'] = None
                record['handover_decided_at'] = None
                if granted: record['human_resolution']='APPROVE_OVERRIDE'
            else:
                record['handover_status'] = None
                record['handover_decline_reason'] = None
                record['handover_decided_at'] = None
                st.commit_approval(conn,record,result)
                if granted: record['human_resolution']='APPROVE_OVERRIDE'
        elif result.decision==DecisionType.ESCALATE:
            if facts.handover_person_id:
                record['handover_status'] = 'PENDING'
        st.save_record(conn,record)
        if result.decision==DecisionType.ESCALATE:
            st.set_steps(conn,record,result.approval_roles)
        st.audit(conn,record['id'],'EVALUATED',json.dumps(result.model_dump(mode='json'),ensure_ascii=False))
        return result

    def resume_pending_request(self, request_id: str):
        """Called automatically after proof inspection completes to resume evaluation."""
        with st.readonly_connection() as conn:
            try:
                req_dict = st.read_request(conn, request_id)
            except LookupError:
                return None
            if req_dict.get('status') not in ('PROCESSING', 'PENDING_INSPECTION'):
                return None
            facts_raw = req_dict.get('facts_json')
            if isinstance(facts_raw, str):
                try: facts_raw = json.loads(facts_raw)
                except Exception: facts_raw = {}
            facts = RequestFacts.model_validate(facts_raw or {})

        record = dict(req_dict)
        record['updated_at'] = self.clock().isoformat()
        with st.transaction() as conn:
            fresh = conn.execute("SELECT status FROM leave_requests WHERE id=?", (request_id,)).fetchone()
            if not fresh or fresh['status'] not in ('PROCESSING', 'PENDING_INSPECTION'):
                return None
            self._evaluate(conn, record, facts, skip_vlm=False)
            st.audit(conn, request_id, 'INSPECTION_RESUMED', 'Proof inspection completed; leave policy evaluated.')
            return st.serialize(conn, st.read_request(conn, record['id']))

    def process_new_request(self,raw_text=None,employee_id=None,structured_data=None,enable_llm_polish=False,custom_request_id=None,skip_vlm=False,submitted_at=None):
        data=dict(structured_data or {})
        emp_id=employee_id or data.pop('employee_id',None)
        data.pop('employee_id',None)
        # Readonly validation of caller before model work
        with st.readonly_connection() as conn:
            emp = st.employee(conn,emp_id)
        if raw_text:
            if any(data.get(k) for k in ('from_date','to_date','leave_type')):
                raise ValueError('Chọn một đầu vào: form hoặc free text.')
            if self.agent and hasattr(self.agent, 'parse_natural_language'):
                facts=RequestFacts.model_validate(self.agent.parse_natural_language(raw_text,current_date=self.clock().date()).model_dump())
            else:
                raise ValueError('Hệ thống chỉ chấp nhận dữ liệu form có cấu trúc. LLM xử lý văn bản tự do đã được tắt hoàn toàn để tránh hallucination.')
            facts.proof_id=None; facts.attachment_type='none'
        else: facts=RequestFacts.model_validate(data)

        # Check proof inspection status if proof_id is provided
        proof_row = None
        if facts.proof_id:
            with st.readonly_connection() as conn:
                p = conn.execute('SELECT * FROM proof_documents WHERE id=?', (facts.proof_id,)).fetchone()
                if not p: raise st.AccessDenied('Chứng từ không tồn tại.')
                if p['employee_id'] != emp_id: raise st.AccessDenied('Chứng từ không thuộc người nộp đơn.')
                proof_row = dict(p)

        req_id = custom_request_id or ('REQ-'+uuid.uuid4().hex[:16].upper())
        now_str = self.clock().isoformat()
        # submitted_at giả lập (kịch bản test ở chế độ demo) quyết định các kiểm tra báo trước / mốc 08:30
        submitted_str = submitted_at.isoformat() if submitted_at else now_str
        record={'id':req_id,'employee_id':emp_id,
                'submitted_at':submitted_str,'updated_at':now_str,'revision':1,'human_resolution':None}

        # Case B: Proof inspection is still PENDING or PROCESSING -> Return 202 without blocking
        if proof_row and not skip_vlm and (proof_row.get('inspection_status') in ('PENDING', 'PROCESSING')):
            base_record = dict(record)
            record.update({
                'employee_name': emp['name'],
                'department': emp['department'],
                'leave_type': str(getattr(facts, 'leave_type', '')),
                'canonical_leave_type': str(getattr(facts, 'leave_type', '')),
                'from_date': str(facts.from_date) if facts.from_date else None,
                'to_date': str(facts.to_date) if facts.to_date else None,
                'reason': facts.reason,
                'reason_category': str(getattr(facts, 'reason_category', '')),
                'handover_person_id': facts.handover_person_id,
                'handover_person_name': facts.handover_person_name,
                'proof_id': facts.proof_id,
                'attachment_type': facts.attachment_type or 'generic_attachment',
                'facts_json': facts.model_dump(),
                'status': 'PROCESSING',
                'decision': 'PROCESSING',
                'human_readable_explanation': 'Chứng từ đang được kiểm định tự động. Kết quả thẩm định sẽ được cập nhật ngay khi hoàn tất.',
            })
            # Kiểm tra lại trạng thái chứng từ NGAY TRONG transaction ghi đơn (BEGIN IMMEDIATE tuần tự hóa với worker):
            # nếu worker đã xong giữa lần đọc ở trên và lúc này, lời đánh thức của worker đã bị bỏ lỡ → không lưu
            # PROCESSING nữa mà đánh giá luôn bên dưới. Ngược lại, đơn được lưu trước khi worker ghi kết quả nên
            # resume_pending_requests_for_proof chắc chắn tìm thấy đơn.
            saved_pending = False
            with st.transaction() as conn:
                current = conn.execute('SELECT inspection_status FROM proof_documents WHERE id=?', (facts.proof_id,)).fetchone()
                if current and current['inspection_status'] in ('PENDING', 'PROCESSING'):
                    st.save_record(conn, record)
                    st.audit(conn, req_id, 'SUBMIT_PENDING_INSPECTION', f'Waiting for proof {facts.proof_id} inspection')
                    saved_pending = True
            if not saved_pending:
                record = base_record
                with st.readonly_connection() as conn:
                    fresh = conn.execute('SELECT * FROM proof_documents WHERE id=?', (facts.proof_id,)).fetchone()
                    proof_row = dict(fresh) if fresh else proof_row
        if proof_row and not skip_vlm and record.get('status') == 'PROCESSING':
            return {
                'id': req_id,
                'status': 'PROCESSING',
                'decision': 'PROCESSING',
                'proof_id': facts.proof_id,
                'proof_inspection_status': proof_row.get('inspection_status', 'PROCESSING'),
                'human_readable_explanation': record['human_readable_explanation'],
                'employee_id': emp_id,
                'employee_name': emp['name'],
                'department': emp['department'],
                'submitted_at': record['submitted_at'],
                'facts_json': facts.model_dump(),
            }

        # Case A / Case C / No Proof:
        # If synchronous VLM is required and wasn't pre-inspected via background queue:
        precomputed_vlm = None
        att = (getattr(facts,'attachment_type', None) or '').strip()
        if str(getattr(facts, 'leave_type', '')).upper() == 'ANNUAL':
            skip_vlm = True
        needs_vlm = not skip_vlm and (bool(att and att.casefold() != 'none') or bool(proof_row))
        if needs_vlm and not (proof_row and (proof_row.get('vlm_analysis_json') or proof_row.get('inspection_status') == 'FAILED')):
            try:
                from vlm_inspector import inspect_document_with_vlm
                attachment_for_vlm = att
                if proof_row:
                    from pathlib import Path as _P
                    uploads_dir = _P(os.getenv('LEAVE_UPLOAD_DIR', str(_P(__file__).resolve().parents[1] / 'uploads')))
                    candidate = uploads_dir / proof_row['storage_name']
                    if candidate.exists(): attachment_for_vlm = str(candidate)
                precomputed_vlm = inspect_document_with_vlm(
                    leave_type=str(getattr(facts,'leave_type','')),
                    employee_name=emp['name'],
                    reason=str(getattr(facts,'reason','') or ''),
                    attachment_path_or_type=attachment_for_vlm,
                    from_date=facts.from_date, to_date=facts.to_date,
                    allow_mock_fallback=False,
                    reason_category=getattr(facts, 'reason_category', None),
                )
            except Exception:
                pass

        # Open short write transaction ONLY to persist (~1ms)
        with st.transaction() as conn:
            if custom_request_id:
                prev = conn.execute('SELECT * FROM leave_requests WHERE id=?', (custom_request_id,)).fetchone()
                if prev:
                    prev_dict = dict(prev)
                    prev_debit = prev_dict.get('deducted_days') or 0
                    if prev_debit > 0 and (prev_dict.get('canonical_leave_type') or prev_dict.get('leave_type')) == 'ANNUAL':
                        conn.execute('UPDATE employees SET remaining_leave_days=remaining_leave_days+? WHERE employee_id=?',
                                     (prev_debit, prev_dict['employee_id']))
                    conn.execute('DELETE FROM leave_bookings WHERE request_id=?', (custom_request_id,))
                    conn.execute('DELETE FROM leave_transactions WHERE request_id=?', (custom_request_id,))
                conn.execute('DELETE FROM approval_steps WHERE request_id=?', (custom_request_id,))
            self._evaluate(conn,record,facts,enable_llm_polish=enable_llm_polish,skip_vlm=skip_vlm,precomputed_vlm=precomputed_vlm)
            return st.serialize(conn,st.read_request(conn,record['id']))

    def resubmit(self,request_id,actor_id,data):
        facts=RequestFacts.model_validate(data)
        with st.transaction() as conn:
            req=st.read_request(conn,request_id)
            st.employee(conn,actor_id)
            if actor_id!=req['employee_id']: raise st.AccessDenied('Chỉ Employee của đơn được sửa.')
            if req['status']!='WAITING_EMPLOYEE': raise st.Conflict('Chỉ sửa đơn đang chờ Employee.')
            req.update(revision=req['revision']+1,submitted_at=self.clock().isoformat(),human_resolution=None)
            self._evaluate(conn,req,facts)
            st.audit(conn,request_id,'EMPLOYEE_RESUBMIT',actor_id)
            return st.serialize(conn,st.read_request(conn,request_id))

    def process_human_decision(self,request_id,feedback_text='',approver_id=None,action_type=None,updated_fields=None):
        # Read a revision token before extraction, then check under lock afterwards.
        with st.transaction() as conn:
            before=st.read_request(conn,request_id)
            st.require_approver(conn,approver_id,before)
            token=(before['revision'],before['updated_at'])
        if action_type:
            action={'APPROVE':'APPROVE_OVERRIDE','REQUEST_INFO':'REQUEST_MORE_INFO'}.get(action_type,action_type)
            feedback=HumanFeedbackResolution(action=action,updated_fields=updated_fields or {},feedback_notes=feedback_text)
        elif self.agent and hasattr(self.agent, 'process_human_feedback'):
            feedback=self.agent.process_human_feedback(feedback_text)
        else:
            # Fail-closed: chỉ DUYỆT khi văn bản có từ khóa duyệt rõ ràng và không kèm phủ định / do dự.
            # Câu mơ hồ ("Để tôi xem lại", "Chưa duyệt được", "Cần họp lại") không được tự suy ra là duyệt.
            fb_u = ' '.join((feedback_text or '').upper().split())
            if any(k in fb_u for k in ('TỪ CHỐI', 'REJECT', 'BÁC BỎ', 'KHÔNG ĐỒNG Ý', 'KHÔNG DUYỆT')):
                act = 'REJECT'
            elif any(k in fb_u for k in ('BỔ SUNG', 'INFO', 'THÊM THÔNG TIN', 'SỬA')):
                act = 'REQUEST_MORE_INFO'
            elif (any(k in fb_u for k in ('ĐỒNG Ý', 'PHÊ DUYỆT', 'DUYỆT', 'APPROVE', 'CHẤP THUẬN'))
                  and not any(k in fb_u for k in ('KHÔNG', 'CHƯA', 'XEM LẠI', 'HỌP', 'SAU', 'CÂN NHẮC', '?', 'NOT ', "DON'T", 'LATER'))):
                act = 'APPROVE_OVERRIDE'
            else:
                raise ValueError('Không xác định được quyết định từ ý kiến. Vui lòng chọn rõ Duyệt / Yêu cầu bổ sung / Từ chối.')
            feedback=HumanFeedbackResolution(action=act,updated_fields=updated_fields or {},feedback_notes=feedback_text)
        with st.transaction() as conn:
            req=st.read_request(conn,request_id)
            if (req['revision'],req['updated_at'])!=token: raise st.Conflict('Đơn đã thay đổi; vui lòng tải lại.')
            st.require_approver(conn,approver_id,req)
            if not req.get('facts_json'): raise st.Conflict('Hồ sơ cũ cần đối soát trước khi xử lý theo policy mới.')
            req['human_feedback_text']=feedback.feedback_notes
            req['updated_at']=self.clock().isoformat()
            if feedback.action in {'REQUEST_MORE_INFO','REJECT'}:
                req['status']='WAITING_EMPLOYEE' if feedback.action=='REQUEST_MORE_INFO' else 'REJECTED'
                req['human_resolution']=feedback.action
                st.save_record(conn,req)
            elif feedback.action=='MODIFY_CONDITIONAL':
                changes=feedback.updated_fields.model_dump(mode='json',exclude_unset=True)
                if not changes: raise ValueError('Không có trường được phép điều chỉnh.')
                facts=dict(req['facts_json']);facts.update(changes)
                if 'handover_person_name' in changes and 'handover_person_id' not in changes: facts['handover_person_id']=None
                req.update(revision=req['revision']+1,human_resolution=None)
                self._evaluate(conn,req,RequestFacts.model_validate(facts))
            else:
                old_target=req['target_role']
                # Chứng từ chưa xác minh chỉ HR được xử lý (xem nhánh HR bên dưới).
                if req['target_role']=='HR':
                    raise st.Conflict('HR cần xác minh chứng từ/cấu hình; không được duyệt bỏ qua điều kiện chưa xác minh.')
                steps=[dict(r) for r in conn.execute('SELECT * FROM approval_steps WHERE request_id=? AND revision=? ORDER BY step_index',(request_id,req['revision']))]
                granted=[s['role'] for s in steps if s['status']=='APPROVED']
                granted.append(req['target_role'])
                # Vai trò thay thế (vd CEO duyệt thay DEPARTMENT_HEAD/HRD khi không ai giữ vai trò đó) được tính là
                # đã duyệt vai trò gốc; nếu không, rule engine lại đòi vai trò gốc và đơn quay vòng về chính người vừa duyệt.
                for original in _ROLE_FALLBACK:
                    if original not in granted and _resolve_staffed_role(conn,original,req['department'],req['employee_id'],req.get('canonical_leave_type') or req.get('leave_type')) in granted:
                        granted.append(original)
                waive=[ErrorCode.NOTICE_PERIOD_VIOLATED,ErrorCode.TEAM_QUOTA_EXCEEDED]
                # Đơn chờ đối chiếu chứng từ đã được chuyển cho Lead Team (không có HR): Lead Team duyệt
                # nghĩa là đã xem xét chứng từ, nên không chuyển lại bước này. Các kiểm tra nội dung chứng từ vẫn áp dụng.
                if req.get('error_code')==ErrorCode.PROOF_REVIEW_REQUIRED.value:
                    waive.append(ErrorCode.PROOF_REVIEW_REQUIRED)
                if req.get('error_code') in {ErrorCode.AUTOMATION_SCOPE_UNSUPPORTED.value, ErrorCode.RELATIONSHIP_UNCLEAR.value, ErrorCode.DOC_ILLEGIBLE.value}:
                    try: waive.append(ErrorCode(req['error_code']))
                    except Exception: pass
                # Re-evaluate before writing this approval. No balance/proof/overlap bypass.
                st.audit(conn,request_id,'HUMAN_APPROVAL',f'{approver_id}: {req["target_role"]}; {feedback.feedback_notes}')
                # Dùng lại kết quả đọc chứng từ đã lưu trên đơn (không gọi lại VLM). Nếu bỏ qua hẳn VLM,
                # rule engine mất dữ liệu chứng từ và chuyển nhầm sang HR (PROOF_REVIEW_REQUIRED).
                stored_vlm=req.get('vlm_analysis_json')
                if isinstance(stored_vlm,str):
                    try: stored_vlm=json.loads(stored_vlm)
                    except ValueError: stored_vlm=None
                cached_vlm=None
                if isinstance(stored_vlm,dict) and stored_vlm.get('document_summary') and not stored_vlm.get('vlm_error'):
                    try: cached_vlm=_vlm_output_from_json(stored_vlm)
                    except Exception: cached_vlm=None
                result=self._evaluate(conn,req,RequestFacts.model_validate(req['facts_json']),granted,waive,
                    skip_vlm=cached_vlm is None,precomputed_vlm=cached_vlm)
                if result.decision == DecisionType.AUTO_APPROVE or (result.decision == DecisionType.ESCALATE and result.error_code not in {ErrorCode.PROOF_REVIEW_REQUIRED,ErrorCode.LEGAL_REVIEW_REQUIRED,ErrorCode.AUTOMATION_SCOPE_UNSUPPORTED}):
                    conn.execute("UPDATE approval_steps SET status='APPROVED',approver_id=?,decided_at=? WHERE request_id=? AND revision=? AND role=? AND status='PENDING'",
                        (approver_id,self.clock().isoformat(),request_id,req['revision'],old_target))
            st.audit(conn,request_id,feedback.action,approver_id+': '+feedback.feedback_notes)
            return st.serialize(conn,st.read_request(conn,request_id))

    def confirm_handover(self, request_id, actor_id, action, reason=''):
        with st.transaction() as conn:
            req = st.read_request(conn, request_id)
            st.employee(conn, actor_id)
            if actor_id != req.get('handover_person_id'):
                raise st.AccessDenied('Chỉ người được bàn giao mới có quyền xác nhận.')
            if req['status'] != 'PENDING_HANDOVER':
                raise st.Conflict('Đơn không ở trạng thái chờ xác nhận bàn giao.')
            now_str = self.clock().isoformat()
            req['updated_at'] = now_str
            req['handover_decided_at'] = now_str
            if action == 'ACCEPT':
                req['handover_status'] = 'ACCEPTED'
                req['status'] = 'COMPLETED'
                result_json = req.get('result_json') or {}
                if isinstance(result_json, str):
                    try: result_json = json.loads(result_json)
                    except Exception: result_json = {}
                class _Res:
                    working_dates = result_json.get('working_dates', [])
                st.commit_approval(conn, req, _Res())
                st.save_record(conn, req)
                st.audit(conn, request_id, 'HANDOVER_ACCEPTED', f'{actor_id} đã chấp nhận bàn giao công việc.')
            elif action == 'DECLINE':
                req['handover_status'] = 'DECLINED'
                req['handover_decline_reason'] = reason or 'Người được bàn giao từ chối nhận bàn giao.'
                req['status'] = 'WAITING_EMPLOYEE'
                req['human_resolution'] = 'HANDOVER_DECLINED'
                st.save_record(conn, req)
                st.audit(conn, request_id, 'HANDOVER_DECLINED', f'{actor_id} từ chối bàn giao: {reason}')
            else:
                raise ValueError(f'Hành động không hợp lệ: {action}')
            return st.serialize(conn, st.read_request(conn, request_id))

    def cancel(self,request_id,actor_id,revoke=False,reason=''):
        with st.transaction() as conn:
            req=st.read_request(conn,request_id)
            st.employee(conn,actor_id)
            if revoke:
                if actor_id==req['employee_id'] or not any(st.has_role(conn,actor_id,r,req['department']) for r in ('DIRECT_MANAGER','DEPARTMENT_HEAD','HRD','CEO')):
                    raise st.AccessDenied('Không có quyền thu hồi quyết định.')
                if req['status']!='COMPLETED' or req['decision']=='NO_LEAVE_REQUIRED': raise st.Conflict('Đơn không thể thu hồi.')
                # Phép năm: hoàn lại số ngày đã trừ. Loại nghỉ khác (ốm, chế độ...) không trừ quỹ phép nên chỉ gỡ lịch nghỉ.
                if req.get('legacy_reconciliation_required'): raise st.Conflict('Hồ sơ lịch sử cần đối soát debit; không tự hoàn phép.')
                count=st.refund(conn,req)
                req.update(status='REJECTED',human_resolution='REVOKED',deducted_days=0,annual_balance_change=(req.get('annual_balance_change') or 0)+count)
            else:
                if actor_id!=req['employee_id']: raise st.AccessDenied('Chỉ người nộp được hủy.')
                if req['status'] not in {'WAITING_EMPLOYEE','PENDING_ESCALATION','PENDING_HANDOVER'}: raise st.Conflict('Chỉ hủy đơn đang chờ xử lý.')
                req.update(status='CANCELLED',human_resolution='CANCELLED')
            req['updated_at']=self.clock().isoformat()
            st.save_record(conn,req)
            st.audit(conn,request_id,'REVOKE' if revoke else 'CANCEL',actor_id+': '+reason)
            return st.serialize(conn,st.read_request(conn,request_id))
