"""Authoritative workflow. Financial mutation and state transitions are atomic."""
import time
import sys
import uuid
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional
root=Path(__file__).resolve().parents[2]
for name in ('Leave_Application','LLM-KIET','backend'):
    if str(root/name) not in sys.path: sys.path.insert(0,str(root/name))
from domain import (RequestFacts, HumanFeedbackResolution, EditableFields,
                    names_approximately_match, should_deduct_annual_balance, VerifiedProof)
from rule_engine import LeaveRuleEngine
from taxonomy import ErrorCode, DecisionType
from agent_orchestrator import LeaveApprovalAgent
from calendar_service import CalendarService
from vlm_inspector import inspect_document_with_vlm, VLMInspectionOutput
from ai_stack import VLM_TARGET_MODEL
import storage as st
import json
from datetime import date

STATES={'AUTO_APPROVE':'COMPLETED','NO_LEAVE_REQUIRED':'COMPLETED','AUTO_REJECT':'REJECTED',
        'NEED_CORRECTION':'WAITING_EMPLOYEE','ESCALATE':'PENDING_ESCALATION'}

class LeaveOrchestratorService:
    def __init__(self, agent=None, clock=None, calendar=None):
        self.agent=agent or LeaveApprovalAgent()
        self.calendar=calendar or CalendarService()
        self.clock=clock or (lambda: datetime.now(self.calendar.timezone))

    def _evaluate(self, conn, record, facts, granted=None, waived=None, enable_llm_polish=False):
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
        vlm_out: VLMInspectionOutput | None = None
        needs_vlm = bool(att and att.casefold() != 'none') or bool(proof_row)
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
                import os
                uploads_dir = _P(os.getenv('LEAVE_UPLOAD_DIR', str(_P(__file__).resolve().parents[1] / 'uploads')))
                candidate = uploads_dir / proof_row['storage_name']
                if candidate.exists():
                    attachment_for_vlm = str(candidate)
                elif att:
                    attachment_for_vlm = att
            vlm_out: VLMInspectionOutput | None = None
            try:
                vlm_out = inspect_document_with_vlm(
                    leave_type=str(getattr(facts,'leave_type','')),
                    employee_name=getattr(ctx,'employee_name',None),
                    reason=str(getattr(facts,'reason','') or ''),
                    attachment_path_or_type=attachment_for_vlm,
                    from_date=f_date, to_date=t_date,
                    workdays=0,
                    proof_type_hint=proof_type_hint,
                    document_readability_hint=readability_hint,
                    doc_flags=doc_flags,
                    allow_mock_fallback=False,
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
            if vlm_out.proof_extraction and getattr(ctx.proof, 'proof_verification_status', 'UNVERIFIED') != 'VERIFIED':
                proof_dict = vlm_out.proof_extraction.model_dump(mode='python')
                existing_ver_status = getattr(ctx.proof, 'proof_verification_status', 'UNVERIFIED')
                existing_notes = getattr(ctx.proof, 'verification_notes', None)
                # Preserve storage-provided verification status; otherwise default to UNVERIFIED
                proof_dict['proof_verification_status'] = existing_ver_status
                proof_dict['verification_notes'] = existing_notes
                if (not proof_dict.get('proof_type') or str(proof_dict['proof_type']) in ('NONE', 'ProofType.NONE')) and getattr(ctx.proof, 'proof_type', None):
                    pt = ctx.proof.proof_type
                    proof_dict['proof_type'] = pt.value if hasattr(pt, 'value') else pt
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
                    # Re-score correlation with exact calculated workdays
                    if wd and vlm_out.proof_extraction:
                        from vlm_inspector import _score_correlation
                        pe = vlm_out.proof_extraction
                        new_score, new_additional_issues, new_doctor_days = _score_correlation(
                            employee_name=getattr(ctx,'employee_name',''),
                            reason=str(getattr(facts,'reason','')),
                            recommended_from=pe.recommended_from_date,
                            recommended_to=pe.recommended_to_date,
                            requested_from=d1, requested_to=d2,
                            diagnosis=vlm_out.doc_diagnosis,
                            days_granted_by_doctor=vlm_out.days_granted_by_doctor,
                            requested_workdays=wd,
                        )
                        if new_score is not None:
                            vlm_dict = dict(vlm_out.vlm_analysis_json or {})
                            merged = list(dict.fromkeys((vlm_out.correlation_issues or []) + list(new_additional_issues)))
                            vlm_out.correlation_score = new_score
                            vlm_out.correlation_issues = merged
                            if new_doctor_days is not None:
                                vlm_out.days_granted_by_doctor = new_doctor_days
                            ca = vlm_dict.get('correlation_analysis', {}); ca['score'] = new_score; ca['issues'] = merged; ca['requested_workdays'] = wd
                            vlm_dict['correlation_analysis'] = ca
                            dr = vlm_dict.get('document_summary',{}); dr['doctor_recommended_range'] = dict(dr.get('doctor_recommended_range',{}) or {}); dr['doctor_recommended_range']['days'] = new_doctor_days
                            vlm_out.vlm_analysis_json = vlm_dict
                except Exception: pass

        t_rule_0 = time.perf_counter()
        result=LeaveRuleEngine.evaluate(ctx,self.calendar)
        rule_engine_ms = round((time.perf_counter() - t_rule_0) * 1000, 3)
        record.update(employee_name=ctx.employee_name,department=ctx.department,
            from_date=facts.from_date,to_date=facts.to_date,workdays=result.requested_working_days or 0,
            leave_type=facts.leave_type or '',canonical_leave_type=facts.leave_type,reason_category=facts.reason_category,
            reason=facts.reason,handover_person_id=facts.handover_person_id,handover_person_name=facts.handover_person_name,
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
            'NOTICE_PERIOD_VIOLATION':'Thời hạn báo trước chưa đủ theo chính sách',
            'NOTICE_PERIOD_VIOLATED':'Thời hạn báo trước chưa đủ theo chính sách',
            'NOTICE_PERIOD_OPERATIONAL':'Thời hạn báo trước dưới ngưỡng hoạt động, cần Manager ghi nhận',
            'DOC_ILLEGIBLE':'Chứng từ khó đọc / thiếu nét xác nhận, cần Quản lý xem xét đặc cách',
            'PROOF_REVIEW_REQUIRED':'Chứng từ cần người có thẩm quyền đối chiếu',
            'PROOF_MISSING':'Thiếu chứng từ đính kèm (cần bổ sung trước khi duyệt)',
            'DOC_FIELD_MISSING':'Một số trường trên chứng từ bị thiếu hoặc chưa khớp với yêu cầu nghỉ',
            'DURATION_OVER_AI_LIMIT':'Số ngày nghỉ vượt ngưỡng tự duyệt → cần cấp trên xem xét',
            'TEAM_QUOTA_BREACH':'Đội ngũ có nhiều người nghỉ cùng lúc (quá 30%), cần quản lý bộ phận xác nhận',
            'TEAM_QUOTA_EXCEEDED':'Đội ngũ có nhiều người nghỉ cùng lúc (quá 30%), cần Quản lý xác nhận',
            'BALANCE_EXCEEDED':'Số dư phép năm không đủ cho số ngày xin nghỉ',
            'BALANCE_CHECK_REQUIRED':'Cần kiểm tra lại số dư phép trước khi duyệt',
            'OUT_OF_POLICY':'Ngoài phạm vi quy định hiện hành',
            'UNCERTAIN_FACTS':'Các facts chưa chắc chắn (vd chẩn đoán / ngày khớp chưa đủ)',
            'AUTHORITY_REQUIRED':'Cần người có thẩm quyền cao hơn xem xét dựa trên số ngày',
            'FLAG_ABUSE_PATTERN':'Phát hiện mẫu nghỉ phép lặp lại bất thường trong tháng',
        }
        DECISION_VI = {
            'AUTO_APPROVE':'Tự động duyệt',
            'ESCALATE':'Chuyển cấp thẩm quyền xem xét',
            'NEED_CORRECTION':'Cần nhân viên bổ sung thông tin',
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

        bullet_lines = [
            f"• Đơn xin nghỉ: Nhân viên {emp_n} nộp đơn {ltype_vi} {requested_wd or requested_cd or 1} ngày làm việc (từ {from_d} đến {to_d}) với lý do \"{reason or 'Nghỉ theo kế hoạch cá nhân'}\".",
            f"• Bàn giao & Quỹ phép: Người nhận bàn giao là {handover_name}; số dư quỹ phép đủ điều kiện.",
        ]

        if vlm_fields_present and proof_relevant:
            doc_parts = []
            if doc_patient: doc_parts.append(f"Tên trên giấy: {doc_patient}")
            if diag: doc_parts.append(f"Chẩn đoán: {diag}")
            if doctor_days: doc_parts.append(f"Bác sĩ cho nghỉ: {doctor_days} ngày")
            if rs is True: doc_parts.append("Có dấu đỏ")
            if sig is True: doc_parts.append("Có chữ ký")
            bullet_lines.append(f"• Chứng từ y tế: {', '.join(doc_parts) if doc_parts else 'Đã đính kèm chứng từ hợp lệ'}.")
        else:
            bullet_lines.append("• Tình trạng chứng từ: Không yêu cầu chứng từ đối với loại nghỉ này.")

        if result.decision == DecisionType.AUTO_APPROVE:
            bullet_lines.append(f"• Kết quả thẩm định: Hệ thống Tự động duyệt (AUTO_APPROVE) — đạt đầy đủ tiêu chí theo chính sách ({clauses_str}).")
            bullet_lines.append("• Kết luận: Đã tự động duyệt, không cần chuyển cấp quản lý xem xét.")
        elif result.decision == DecisionType.NEED_CORRECTION:
            bullet_lines.append(f"• Kết quả đối soát: Hồ sơ chưa đủ điều kiện tự duyệt ({err_vi}).")
            bullet_lines.append("• Kết luận: Cần nhân viên bổ sung hoặc sửa lại thông tin trước khi duyệt.")
        else:
            bullet_lines.append(f"• Kết quả đối soát: Cần người có thẩm quyền phê duyệt ({err_vi}).")
            bullet_lines.append(f"• Kết luận: Chuyển {role_vi} xem xét và quyết định.")

        template_summary_full = "\n".join(bullet_lines)

        # ---- Quick actions (Vietnamese - template fallback) ----
        QUICK_VI = {
            'APPROVE_OVERRIDE':'✅ Duyệt (ghi chú nếu cần)',
            'REQUEST_MORE_INFO':'❓ Yêu cầu giải thích / bổ sung thêm thông tin',
            'REJECT':'❌ Từ chối (nêu lý do)',
            'ESCALATE_FURTHER':'⬆ Chuyển tiếp cấp cao hơn',
            'WAIVE_NOTICE':'⏳ Bỏ qua quy định báo trước',
            'WAIVE_QUOTA':'👥 Bỏ qua giới hạn team 30%',
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
        if sig is True: integrity_parts.append('có chữ ký bác sĩ')
        elif sig is False: integrity_parts.append('thiếu chữ ký bác sĩ')
        if tamper is True: integrity_parts.append('nghi vấn chỉnh sửa (tampered)')
        if ai_ed is True: integrity_parts.append('nghi vấn được tạo bởi AI')

        integrity_assess = "; ".join(integrity_parts) if integrity_parts else ("Hồ sơ hợp lệ theo quy định." if not vlm_fields_present else "Chứng từ hợp lệ.")

        # Pre-calculated deterministic facts
        if vlm_fields_present:
            name_match = names_approximately_match(emp_n, doc_patient) if (emp_n and doc_patient) else None
            name_status = (
                f"Trùng khớp: '{emp_n}'" if name_match is True
                else f"BẤT THƯỜNG / KHÔNG KHỚP TÊN: Nhân viên nộp là '{emp_n}', nhưng chứng từ đứng tên '{doc_patient}'" if name_match is False
                else "Chưa đọc được tên trên chứng từ"
            )
            diag_status = f"Đơn khai: '{reason}' | Giấy ghi: '{diag}'" if (reason or diag) else "—"
            date_status = f"Đơn xin: {from_d} đến {to_d} ({requested_wd} ngày làm việc) | Bác sĩ chỉ định: {dfd} đến {dtd} ({doctor_days} ngày)"
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
            elif rs is False: info_mis.append("Chứng từ thiếu dấu mộc đỏ bệnh viện/phòng khám")
            if sig is True: info_suf.append("Chứng từ có chữ ký bác sĩ / người cấp giấy")
            elif sig is False: info_mis.append("Chứng từ thiếu chữ ký bác sĩ / người cấp giấy")
            if doc_patient and emp_n and names_approximately_match(emp_n, doc_patient):
                info_suf.append(f"Tên trên chứng từ khớp với nhân viên: {doc_patient}")
            elif doc_patient and emp_n and (emp_n.strip().casefold() != doc_patient.strip().casefold()):
                info_mis.append(f"Tên trên chứng từ ({doc_patient}) KHÔNG khớp với nhân viên nộp đơn ({emp_n})")
            if tamper is True: info_mis.append("Chứng từ có dấu hiệu chỉnh sửa giả mạo (tampered)")
            if ai_ed is True: info_mis.append("Chứng từ nghi vấn được tạo bởi công cụ AI")

        if error_code == 'TEAM_QUOTA_EXCEEDED':
            info_mis.append("Tỷ lệ vắng mặt trong bộ phận vượt ngưỡng an toàn 30% tại ngày xin nghỉ")
        elif error_code in ('NOTICE_PERIOD_VIOLATED', 'NOTICE_PERIOD_VIOLATION'):
            info_mis.append("Thời hạn nộp đơn chưa đủ số ngày báo trước theo chính sách")
        elif error_code == 'DURATION_OVER_AI_LIMIT':
            info_mis.append(f"Số ngày nghỉ ({requested_wd} ngày) vượt hạn mức phê duyệt tự động")
        elif error_code == 'PROOF_REVIEW_REQUIRED':
            info_mis.append("Chứng từ y tế chưa được xác minh")
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
        if tamper is True:
            manager_suspicions.append('Chứng từ có dấu hiệu chỉnh sửa hoặc giả mạo.')
        if ai_ed is True:
            manager_suspicions.append('Chứng từ có dấu hiệu được tạo hoặc chỉnh sửa bằng AI.')
        if doc_patient and emp_n and not names_approximately_match(doc_patient, emp_n):
            manager_suspicions.append(f'Tên trên chứng từ ({doc_patient}) không khớp nhân viên ({emp_n}).')
        if error_code == 'FLAG_ABUSE_PATTERN':
            manager_suspicions.append('Có nhiều đơn phép năm rời rạc trong cùng tháng.')
        if error_code in ('TEAM_QUOTA_EXCEEDED', 'NOTICE_PERIOD_VIOLATED', 'NOTICE_PERIOD_VIOLATION'):
            manager_suspicions.append(ERROR_VI.get(error_code, 'Có sai lệch về điều kiện vận hành.'))
        if corr_score is not None and float(corr_score) < 0.7:
            manager_suspicions.append('Mức khớp giữa đơn và chứng từ thấp.')
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
        llm_gen_ms = 0.0

        if enable_llm_polish:
            # Opt-in polish only when explicitly enabled (never on production synchronous requests)
            t_llm_0 = time.perf_counter()
            try:
                from llm_client import LLMClient
                from prompts import SUMMARY_MANAGER_SYSTEM_PROMPT
                from schemas import ManagerSummaryLLMResponse
                _llm = LLMClient()
                raw_context = {
                    "context_employee": {
                        "employee_name": emp_n,
                        "employee_id": getattr(ctx, 'employee_id', None),
                        "department": getattr(ctx, 'department', None),
                    },
                    "leave_request": {
                        "leave_type_enum": ltype,
                        "leave_type_vi": ltype_vi,
                        "from_date": from_d,
                        "to_date": to_d,
                        "requested_calendar_days": int(requested_cd or 0),
                        "requested_working_days": int(requested_wd or 0),
                        "reason": reason,
                    },
                    "vlm_analysis": {
                        "ran_vlm": bool(vlm_fields_present),
                        "patient_name_on_doc": doc_patient,
                        "issuer": getattr(proof_extraction, 'issuer', None) or (vlm_analysis_data.get('document_summary') or {}).get('issuer'),
                        "issue_date": getattr(proof_extraction, 'issue_date', None).isoformat() if getattr(proof_extraction, 'issue_date', None) else None,
                        "diagnosis": diag,
                        "doctor_recommended_range": {
                            "from": dfd.isoformat() if dfd else None,
                            "to": dtd.isoformat() if dtd else None,
                            "days": doctor_days,
                        },
                        "has_red_stamp": rs,
                        "has_doctor_signature": sig,
                        "is_tampered": tamper,
                        "ai_edited": ai_ed,
                        "correlation_score": corr_score,
                        "correlation_tier": correlation_tier,
                        "integrity_flags_text": integrity_assess,
                    },
                    "facts_comparison_summary": {
                        "name_comparison": name_status,
                        "diagnosis_comparison": diag_status,
                        "date_comparison": date_status,
                        "stamp_and_signature": stamp_sig_status,
                    },
                    "rule_engine_result": {
                        "decision": decision_val,
                        "decision_vi": decision_vi,
                        "status": status_val,
                        "error_code": error_code,
                        "error_code_vi_fallback": ERROR_VI.get(error_code, error_code or '—'),
                        "uncertainty_category": _v_enum(result.uncertainty_category),
                        "target_role": target_role,
                        "target_role_vi_fallback": ROLE_VI.get(target_role, target_role or '—'),
                        "human_readable_explanation": result.human_readable_explanation or '',
                        "quick_action_options_enum": list(result.quick_action_options or []),
                        "applied_policy_clauses_enum": [str(x) for x in list(result.applied_policy_clauses or [])],
                        "warnings_enum": [str(x) for x in list(getattr(result,'warnings',[]) or [])],
                        "why_escalated_template": why_escalated_vi,
                        "actionable_question_template": aq_vi,
                        "summary_template_text": template_summary_full,
                    }
                }
                user_prompt = (
                    "Dưới đây là context đầy đủ của đơn nghỉ phép và kết quả đối soát chứng từ (JSON).\n"
                    "Hãy tổng hợp thành bản báo cáo trung thực, chính xác theo schema ManagerSummaryLLMResponse.\n\n"
                    "CONTEXT_JSON_BEGIN\n"
                    + json.dumps(raw_context, ensure_ascii=False, indent=2)
                    + "\nCONTEXT_JSON_END\n"
                )
                llm_out = _llm.generate_json(
                    system_prompt=SUMMARY_MANAGER_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_model=ManagerSummaryLLMResponse,
                )
                llm_parsed.update(llm_out)
                # Error lists are evidence-backed deterministic findings. Do not
                # let a generative summary add comments, recommendations, or routing.
                llm_parsed['info_missing_vn'] = list(info_mis)
                llm_parsed['staff_errors_vn'] = list(staff_errors)
                llm_parsed['manager_suspicions_vn'] = list(manager_suspicions)
                llm_engine_used = "qwen2.5:3b-instruct (Ollama)"
                llm_gen_ms = round((time.perf_counter() - t_llm_0) * 1000, 3)
            except Exception as e:
                llm_call_error = f"{type(e).__name__}: {e}"
                llm_engine_used += f" | llm_call_failed: {llm_call_error[:160]}"

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
                "patient_name": doc_patient,
                "diagnosis": diag,
                "doctor_recommended_days": doctor_days,
                "has_red_stamp": rs,
                "has_doctor_signature": sig,
                "is_tampered": tamper,
                "ai_edited": ai_ed,
                "correlation_score": corr_score,
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
            st.commit_approval(conn,record,result)
            if granted: record['human_resolution']='APPROVE_OVERRIDE'
        st.save_record(conn,record)
        if result.decision==DecisionType.ESCALATE:
            st.set_steps(conn,record,result.approval_roles)
        st.audit(conn,record['id'],'EVALUATED',json.dumps(result.model_dump(mode='json'),ensure_ascii=False))
        return result

    def process_new_request(self,raw_text=None,employee_id=None,structured_data=None,enable_llm_polish=False):
        data=dict(structured_data or {})
        emp_id=employee_id or data.pop('employee_id',None)
        data.pop('employee_id',None)
        # Never derive identity from LLM. Validate caller before model work.
        with st.transaction() as conn: st.employee(conn,emp_id)
        if raw_text:
            if any(data.get(k) for k in ('from_date','to_date','leave_type')):
                raise ValueError('Chọn một đầu vào: form hoặc free text.')
            facts=RequestFacts.model_validate(self.agent.parse_natural_language(raw_text,current_date=self.clock().date()).model_dump())
            # A model cannot attach another person's document or invent an attachment.
            facts.proof_id=None; facts.attachment_type='none'
        else: facts=RequestFacts.model_validate(data)
        record={'id':'REQ-'+uuid.uuid4().hex[:16].upper(),'employee_id':emp_id,
                'submitted_at':self.clock().isoformat(),'revision':1,'human_resolution':None}
        with st.transaction() as conn:
            self._evaluate(conn,record,facts,enable_llm_polish=enable_llm_polish)
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
        else:
            feedback=self.agent.process_human_feedback(feedback_text)
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
                if req['target_role']=='HR':
                    raise st.Conflict('HR cần xác minh chứng từ/cấu hình; không được duyệt bỏ qua điều kiện chưa xác minh.')
                steps=[dict(r) for r in conn.execute('SELECT * FROM approval_steps WHERE request_id=? AND revision=? ORDER BY step_index',(request_id,req['revision']))]
                granted=[s['role'] for s in steps if s['status']=='APPROVED']
                granted.append(req['target_role'])
                waive=[ErrorCode.NOTICE_PERIOD_VIOLATED,ErrorCode.TEAM_QUOTA_EXCEEDED]
                # Re-evaluate before writing this approval. No balance/proof/overlap bypass.
                st.audit(conn,request_id,'HUMAN_APPROVAL',f'{approver_id}: {req["target_role"]}; {feedback.feedback_notes}')
                old_target=req['target_role']
                result=self._evaluate(conn,req,RequestFacts.model_validate(req['facts_json']),granted,waive)
                if result.decision in {DecisionType.AUTO_APPROVE,DecisionType.ESCALATE} and result.error_code not in {ErrorCode.PROOF_REVIEW_REQUIRED,ErrorCode.LEGAL_REVIEW_REQUIRED,ErrorCode.AUTOMATION_SCOPE_UNSUPPORTED}:
                    conn.execute("UPDATE approval_steps SET status='APPROVED',approver_id=?,decided_at=? WHERE request_id=? AND revision=? AND role=? AND status='PENDING'",
                        (approver_id,self.clock().isoformat(),request_id,req['revision'],old_target))
            st.audit(conn,request_id,feedback.action,approver_id+': '+feedback.feedback_notes)
            return st.serialize(conn,st.read_request(conn,request_id))

    def cancel(self,request_id,actor_id,revoke=False,reason=''):
        with st.transaction() as conn:
            req=st.read_request(conn,request_id)
            st.employee(conn,actor_id)
            if revoke:
                if actor_id==req['employee_id'] or not any(st.has_role(conn,actor_id,r,req['department']) for r in ('DIRECT_MANAGER','DEPARTMENT_HEAD','HRD','CEO')):
                    raise st.AccessDenied('Không có quyền thu hồi quyết định.')
                if req['status']!='COMPLETED' or req['decision']=='NO_LEAVE_REQUIRED': raise st.Conflict('Đơn không thể thu hồi.')
                if not should_deduct_annual_balance(req.get('canonical_leave_type') or req['leave_type']):
                    raise st.Conflict('Không thu hồi quyền nghỉ luật định bằng workflow Annual.')
                if req.get('legacy_reconciliation_required'): raise st.Conflict('Hồ sơ lịch sử cần đối soát debit; không tự hoàn phép.')
                count=st.refund(conn,req)
                req.update(status='REJECTED',human_resolution='REVOKED',deducted_days=0,annual_balance_change=(req.get('annual_balance_change') or 0)+count)
            else:
                if actor_id!=req['employee_id']: raise st.AccessDenied('Chỉ người nộp được hủy.')
                if req['status'] not in {'WAITING_EMPLOYEE','PENDING_ESCALATION'}: raise st.Conflict('Chỉ hủy đơn đang chờ xử lý.')
                req.update(status='CANCELLED',human_resolution='CANCELLED')
            req['updated_at']=self.clock().isoformat()
            st.save_record(conn,req)
            st.audit(conn,request_id,'REVOKE' if revoke else 'CANCEL',actor_id+': '+reason)
            return st.serialize(conn,st.read_request(conn,request_id))
