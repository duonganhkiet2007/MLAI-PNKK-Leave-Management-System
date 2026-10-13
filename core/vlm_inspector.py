"""VLM (Vision-Language Model) document inspector for leave certificates, prescriptions,
marriage/death extracts, and identity papers.

Design:
  * NEVER fabricate facts.  The deterministic engine must not receive "invented" claims.
  * When a real model (Ollama qwen2.5vl:7b) is reachable we run structured JSON extraction.
  * Otherwise we fall back to a type-safe persona-driven mock profile, keyed off of the
    legacy ``attachment_type`` string.  The mock still exercises every downstream column
    and the correlation engine so the UI (Manager panels, Attachment Modal, checklists)
    renders exactly the same shape as production data.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
_CORE_DIR = Path(__file__).resolve().parent
for _p in [str(_BACKEND_DIR), str(_CORE_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from domain import ProofExtraction, ProofType
from ai.ai_stack import (
    OLLAMA_BASE as VLM_OLLAMA_BASE,
    VLM_TARGET_MODEL,
    VLM_TIMEOUT_SEC,
    VLM_MAX_IMAGE_DIM,
    OLLAMA_KEEP_ALIVE,
    has_model,
    ollama_generate,
    ollama_tags,
)
VLM_FORCE_MOCK = os.getenv("VLM_FORCE_MOCK", "0").strip().casefold() in ("1", "true", "yes", "on")
VLM_MOCK_FALLBACK_ALLOWED = os.getenv("VLM_ALLOW_MOCK_FALLBACK", "0").strip().casefold() in ("1", "true", "yes", "on")

PERSONA_CONFIGS = {
    "SICK_MEDICAL": {
        "persona": "Bác sĩ kiểm định hồ sơ y tế (Medical Certificate Assessor)",
        "schema_key": "SICK_MEDICAL",
        "decision_tree": "doc_patient_name -> doc_diagnosis -> recommended_dates & days_granted_by_doctor -> issuer -> doctor_signature & red_stamp -> integrity",
        "allowed_proof_types": "MEDICAL_LEAVE_CERTIFICATE, HOSPITAL_DISCHARGE, LAB_RESULT, OTHER",
        "schema_prompt": """  1. proof_type: "MEDICAL_LEAVE_CERTIFICATE" | "HOSPITAL_DISCHARGE" | "LAB_RESULT" | "OTHER"
  2. doc_patient_name: string | null  // Tên bệnh nhân ghi trên giấy
  3. doc_diagnosis: string | null     // Chẩn đoán lâm sàng nguyên văn từ bác sĩ
  4. days_granted_by_doctor: int | null // Số ngày bác sĩ chỉ định nghỉ hưởng BHXH
  5. recommended_from_date: YYYY-MM-DD | null // Nghỉ từ ngày
  6. recommended_to_date: YYYY-MM-DD | null   // Nghỉ đến ngày (BẮT BUỘC có nếu giấy ghi rõ)
  7. issue_date: YYYY-MM-DD | null    // Ngày cấp giấy
  8. issuer: string | null            // Bệnh viện / Phòng khám / Cơ sở y tế cấp
  9. has_red_stamp: bool              // Có dấu mộc đỏ cơ sở y tế
  10. has_doctor_signature: bool      // Có chữ ký bác sĩ điều trị
  11. signature_present: bool         // Giống has_doctor_signature
  12. digital_signature_present: bool | null
  13. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  14. is_tampered: bool | null
  15. ai_edited: bool | null
  16. correlation_issues: list[string]
  17. escalation_reasons: list[string]
  18. fields_detected: list[string]""",
    },
    "EMERGENCY": {
        "persona": "Điều phối viên hồ sơ cấp cứu (Emergency Admission Coordinator)",
        "schema_key": "EMERGENCY",
        "decision_tree": "doc_patient_name -> emergency_admission_evidence -> admission_date -> hospital_issuer -> integrity -> open_ended_status",
        "allowed_proof_types": "EMERGENCY_ADMISSION, HOSPITAL_DISCHARGE, SURGERY_NOTICE, OTHER_MEDICAL",
        "schema_prompt": """  1. proof_type: "EMERGENCY_ADMISSION" | "HOSPITAL_DISCHARGE" | "SURGERY_NOTICE" | "OTHER_MEDICAL"
  2. doc_patient_name: string | null      // Tên người bệnh cấp cứu
  3. emergency_diagnosis: string | null  // Lý do cấp cứu, chẩn đoán ban đầu / can thiệp khẩn
  4. doc_diagnosis: string | null        // Giống emergency_diagnosis
  5. admission_date: YYYY-MM-DD | null   // Ngày giờ tiếp nhận cấp cứu / vào viện
  6. recommended_from_date: YYYY-MM-DD | null // Ngày bắt đầu cấp cứu (thường = admission_date)
  7. discharge_date: YYYY-MM-DD | null   // Ngày xuất viện (ĐỂ null NẾU BỆNH NHÂN ĐANG CẤP CỨU / CHƯA XUẤT VIỆN)
  8. recommended_to_date: YYYY-MM-DD | null   // Giống discharge_date (để null nếu chưa biết ngày ra viện)
  9. is_open_ended: bool                 // true nếu chưa xác định ngày ra viện / ngày đi làm lại
  10. requires_followup_proof: bool      // true nếu cần bổ sung giấy ra viện sau khi xuất viện
  11. issuer: string | null              // Bệnh viện / Khoa cấp cứu / Trung tâm hồi sức
  12. has_red_stamp: bool                // Dấu mộc đỏ bệnh viện
  13. has_hospital_stamp: bool           // Giống has_red_stamp
  14. has_doctor_signature: bool         // Chữ ký bác sĩ trực cấp cứu
  15. signature_present: bool            // Có chữ ký không
  16. digital_signature_present: bool | null
  17. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  18. is_tampered: bool | null
  19. ai_edited: bool | null
  20. correlation_issues: list[string]
  21. escalation_reasons: list[string]
  22. fields_detected: list[string]""",
    },
    "WEDDING": {
        "persona": "Chuyên viên xác minh hôn sự (Marriage & Wedding Adjudicator)",
        "schema_key": "WEDDING",
        "decision_tree": "event_type (SELF/CHILD) -> couple_names -> wedding_date -> issuer (UBND) -> red_stamp -> integrity",
        "allowed_proof_types": "MARRIAGE_CERTIFICATE, WEDDING_INVITATION, OTHER",
        "schema_prompt": """  1. proof_type: "MARRIAGE_CERTIFICATE" | "WEDDING_INVITATION" | "OTHER"
  2. subject_name: string | null         // Tên cô dâu hoặc chú rể trên giấy
  3. partner_name: string | null         // Tên người phối ngẫu (vợ/chồng)
  4. doc_patient_name: string | null     // Giống subject_name
  5. event_type: "SELF_MARRIAGE" | "CHILD_MARRIAGE" | null
  6. wedding_date: YYYY-MM-DD | null     // Ngày cưới / ngày đăng ký kết hôn
  7. recommended_from_date: YYYY-MM-DD | null // Ngày bắt đầu nghỉ cưới
  8. recommended_to_date: YYYY-MM-DD | null   // Ngày kết thúc nghỉ cưới
  9. issue_date: YYYY-MM-DD | null       // Ngày cấp giấy
  10. issuer: string | null              // UBND phường/xã, cơ quan có thẩm quyền cấp
  11. has_red_stamp: bool                // Dấu mộc đỏ UBND/cơ quan
  12. signature_present: bool            // Chữ ký người có thẩm quyền
  13. has_doctor_signature: bool         // false (giấy cưới không có bác sĩ)
  14. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  15. is_tampered: bool | null
  16. ai_edited: bool | null
  17. correlation_issues: list[string]
  18. escalation_reasons: list[string]
  19. fields_detected: list[string]""",
    },
    "BEREAVEMENT": {
        "persona": "Chuyên viên xác minh tang lễ (Bereavement & Death Certificate Assessor)",
        "schema_key": "BEREAVEMENT",
        "decision_tree": "deceased_name -> relationship (cha/mẹ/vợ/chồng/con) -> date_of_death -> issuer -> red_stamp -> integrity",
        "allowed_proof_types": "DEATH_CERTIFICATE, FUNERAL_DECISION, OTHER",
        "schema_prompt": """  1. proof_type: "DEATH_CERTIFICATE" | "FUNERAL_DECISION" | "OTHER"
  2. deceased_name: string | null        // Tên người quá cố trên giấy chứng tử
  3. doc_patient_name: string | null     // Giống deceased_name
  4. relationship_label: string | null   // Quan hệ ghi trên giấy (cha/mẹ/vợ/chồng/con)
  5. date_of_death: YYYY-MM-DD | null    // Ngày mất / từ trần
  6. funeral_date: YYYY-MM-DD | null     // Ngày tổ chức tang lễ (nếu có)
  7. recommended_from_date: YYYY-MM-DD | null // Ngày bắt đầu nghỉ tang
  8. recommended_to_date: YYYY-MM-DD | null   // Ngày kết thúc nghỉ tang
  9. issue_date: YYYY-MM-DD | null       // Ngày cấp giấy chứng tử
  10. issuer: string | null              // UBND / Công an / Trạm y tế cấp
  11. has_red_stamp: bool                // Dấu mộc đỏ cơ quan cấp
  12. signature_present: bool            // Chữ ký người có thẩm quyền
  13. has_doctor_signature: bool         // Chữ ký xác nhận y tế/công an
  14. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  15. is_tampered: bool | null
  16. ai_edited: bool | null
  17. correlation_issues: list[string]
  18. escalation_reasons: list[string]
  19. fields_detected: list[string]""",
    },
    "STATUTORY": {
        "persona": "Chuyên viên xác minh quan hệ thân nhân theo Bộ luật Lao động (Statutory Relationship Adjudicator)",
        "schema_key": "STATUTORY",
        "decision_tree": "event_type -> subject_name -> relationship_to_employee -> evidence_confidence -> manager_escalation",
        "allowed_proof_types": "DEATH_CERTIFICATE, MARRIAGE_CERTIFICATE, WEDDING_INVITATION, FUNERAL_DECISION, FAMILY_EVENT_LETTER, OTHER",
        "schema_prompt": """  1. proof_type: "DEATH_CERTIFICATE" | "MARRIAGE_CERTIFICATE" | "WEDDING_INVITATION" | "FUNERAL_DECISION" | "FAMILY_EVENT_LETTER" | "OTHER"
  2. subject_name: string | null             // Tên người thân liên quan
  3. doc_patient_name: string | null         // Giống subject_name
  4. relationship_to_employee: string | null // Quan hệ: ông, bà nội/ngoại, anh, chị, em ruột...
  5. relationship_label: string | null       // Giống relationship_to_employee
  6. event_type: "DEATH" | "MARRIAGE" | "OTHER" | null
  7. event_date: YYYY-MM-DD | null           // Ngày diễn ra sự kiện
  8. recommended_from_date: YYYY-MM-DD | null
  9. recommended_to_date: YYYY-MM-DD | null
  10. issue_date: YYYY-MM-DD | null
  11. issuer: string | null
  12. has_red_stamp: bool
  13. signature_present: bool
  14. evidence_confidence: "HIGH" | "MEDIUM" | "LOW" // Độ rõ ràng của quan hệ thân nhân trên giấy
  15. needs_manager_review: bool              // true nếu quan hệ khó xác thực tự động
  16. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  17. is_tampered: bool | null
  18. ai_edited: bool | null
  19. correlation_issues: list[string]
  20. escalation_reasons: list[string]
  21. fields_detected: list[string]""",
    },
    "MATERNITY": {
        "persona": "Chuyên viên hồ sơ thai sản BHXH (Maternity Leave Officer)",
        "schema_key": "MATERNITY",
        "decision_tree": "maternity_phase -> mother_name -> expected_or_birth_date -> doctor_period -> issuer -> bhxh_code",
        "allowed_proof_types": "MATERNITY_CERTIFICATE, HOSPITAL_DISCHARGE, LAB_RESULT, OTHER",
        "schema_prompt": """  1. proof_type: "MATERNITY_CERTIFICATE" | "HOSPITAL_DISCHARGE" | "LAB_RESULT" | "OTHER"
  2. subject_name: string | null         // Tên thai phụ / người mẹ
  3. doc_patient_name: string | null     // Giống subject_name
  4. maternity_phase: "PRENATAL" | "BIRTH" | "POSTNATAL" | "CHILD_CARE" | null
  5. expected_due_date: YYYY-MM-DD | null// Ngày dự sinh
  6. recommended_from_date: YYYY-MM-DD | null
  7. recommended_to_date: YYYY-MM-DD | null
  8. days_granted_by_doctor: int | null  // Số ngày nghỉ thai sản bác sĩ/viện cho
  9. bhxh_code: string | null            // Mã số BHXH nếu có trên giấy
  10. issue_date: YYYY-MM-DD | null
  11. issuer: string | null              // Bệnh viện phụ sản / Trạm y tế
  12. has_red_stamp: bool
  13. has_doctor_signature: bool
  14. signature_present: bool
  15. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  16. is_tampered: bool | null
  17. ai_edited: bool | null
  18. correlation_issues: list[string]
  19. escalation_reasons: list[string]
  20. fields_detected: list[string]""",
    },
    "WORK_ACCIDENT": {
        "persona": "Chuyên viên hồ sơ tai nạn lao động BHXH (Workplace Injury Officer)",
        "schema_key": "WORK_ACCIDENT",
        "decision_tree": "subject_name -> injury_description -> is_workplace_related -> dates -> issuer -> bhxh_stamp",
        "allowed_proof_types": "ACCIDENT_CERTIFICATE, ACCIDENT_REPORT, INJURY_CERTIFICATE, HOSPITAL_DISCHARGE, OTHER",
        "schema_prompt": """  1. proof_type: "ACCIDENT_CERTIFICATE" | "ACCIDENT_REPORT" | "INJURY_CERTIFICATE" | "HOSPITAL_DISCHARGE" | "OTHER"
  2. subject_name: string | null         // Tên người bị nạn
  3. doc_patient_name: string | null     // Giống subject_name
  4. injury_description: string | null   // Mô tả tai nạn, vết thương, chẩn đoán thương tật
  5. doc_diagnosis: string | null        // Giống injury_description
  6. is_workplace_related: bool | null   // Tai nạn trong giờ làm / trên đường đi làm?
  7. injury_date: YYYY-MM-DD | null      // Ngày xảy ra tai nạn
  8. recommended_from_date: YYYY-MM-DD | null
  9. recommended_to_date: YYYY-MM-DD | null
  10. days_granted_by_doctor: int | null
  11. issue_date: YYYY-MM-DD | null
  12. issuer: string | null              // Ban ATLĐ / Bệnh viện điều trị / BHXH
  13. has_red_stamp: bool
  14. has_bhxh_stamp: bool | null        // Có dấu cơ quan BHXH
  15. has_doctor_signature: bool
  16. signature_present: bool
  17. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  18. is_tampered: bool | null
  19. ai_edited: bool | null
  20. correlation_issues: list[string]
  21. escalation_reasons: list[string]
  22. fields_detected: list[string]""",
    },
    "ADMINISTRATIVE": {
        "persona": "Chuyên viên đối soát giấy tờ hành chính tổng hợp (General Administrative Officer)",
        "schema_key": "ADMINISTRATIVE",
        "decision_tree": "doc_type -> subject_name -> valid_period -> issuer -> integrity",
        "allowed_proof_types": "VISA_OR_TRAVEL_DOC, IDENTITY_CARD, OTHER_ADMINISTRATIVE, OTHER",
        "schema_prompt": """  1. proof_type: "VISA_OR_TRAVEL_DOC" | "IDENTITY_CARD" | "OTHER_ADMINISTRATIVE" | "OTHER"
  2. subject_name: string | null         // Tên người trên giấy tờ
  3. doc_patient_name: string | null     // Giống subject_name
  4. document_purpose: string | null     // Mục đích giấy tờ (visa, du lịch, thủ tục...)
  5. valid_from: YYYY-MM-DD | null       // Có hiệu lực từ ngày
  6. valid_to: YYYY-MM-DD | null         // Hiệu lực đến ngày
  7. recommended_from_date: YYYY-MM-DD | null
  8. recommended_to_date: YYYY-MM-DD | null
  9. issue_date: YYYY-MM-DD | null
  10. issuer: string | null              // Cơ quan ban hành
  11. has_red_stamp: bool
  12. signature_present: bool
  13. has_doctor_signature: bool
  14. document_readability: "READABLE" | "PARTIAL" | "UNREADABLE"
  15. is_tampered: bool | null
  16. ai_edited: bool | null
  17. correlation_issues: list[string]
  18. escalation_reasons: list[string]
  19. fields_detected: list[string]""",
    },
}

VLM_SYSTEM_PROMPT = """Bạn là chuyên gia kiểm định chứng từ nghỉ phép Nhân sự Việt Nam (VLM-Officer).
Nhiệm vụ: đọc ảnh CHỨNG TỪ đính kèm của đơn nghỉ phép và trả về JSON THUẦN TÚY theo schema đã định nghĩa."""

# Compatibility alias
VLM_LEAVE_TYPE_PROFILES = {
    k: {
        "persona": v["persona"],
        "json_variant": v["schema_key"],
        "decision_tree": v["decision_tree"],
        "required": v["decision_tree"].replace(" -> ", ", "),
    }
    for k, v in PERSONA_CONFIGS.items()
}


def _resolve_persona_config(leave_type: str, reason_category: Optional[str] = None) -> Dict[str, Any]:
    lt = str(leave_type or "").upper()
    rc = str(reason_category or "").upper()

    if lt == "SICK_MEDICAL":
        return PERSONA_CONFIGS["SICK_MEDICAL"]
    elif lt == "MEDICAL_EMERGENCY":
        return PERSONA_CONFIGS["EMERGENCY"]
    elif lt == "SPECIAL_PAID":
        if any(w in rc for w in ("MARRIAGE", "WEDDING", "CUOI", "HY")):
            return PERSONA_CONFIGS["WEDDING"]
        elif any(w in rc for w in ("DEATH", "TANG", "MAT", "BEREAVEMENT")):
            return PERSONA_CONFIGS["BEREAVEMENT"]
        return PERSONA_CONFIGS["WEDDING"]
    elif lt == "STATUTORY_UNPAID":
        return PERSONA_CONFIGS["STATUTORY"]
    elif lt == "MATERNITY":
        return PERSONA_CONFIGS["MATERNITY"]
    elif lt == "WORK_ACCIDENT":
        return PERSONA_CONFIGS["WORK_ACCIDENT"]
    else:
        return PERSONA_CONFIGS["ADMINISTRATIVE"]


def _leave_type_prompt(leave_type: str, reason_category: Optional[str] = None) -> str:
    cfg = _resolve_persona_config(leave_type, reason_category)
    variant_alias = {
        "SICK_MEDICAL": "medical_certificate",
        "EMERGENCY": "emergency_admission",
        "WEDDING": "marriage_certificate",
        "BEREAVEMENT": "death_certificate",
        "STATUTORY": "statutory_relationship",
        "MATERNITY": "maternity_certificate",
        "WORK_ACCIDENT": "accident_certificate",
        "ADMINISTRATIVE": "administrative_document",
    }.get(cfg["schema_key"], "general_document")
    persona_text = cfg["persona"]
    if "STATUTORY" in cfg["schema_key"]:
        persona_text = f"{cfg['persona']} / Chuyên viên xác minh quan hệ thân nhân theo luật"
    return (
        f"LOẠI NGHỈ: {leave_type} (Phân loại: {reason_category or 'CHUNG'}).\n"
        f"🎭 ĐÓNG VAI: {persona_text}.\n"
        f"Biến thể JSON: {variant_alias}.\n"
        f"🌲 THỨ TỰ THẨM ĐỊNH (DECISION TREE): {cfg['decision_tree']}.\n"
        f"📋 CÁC LOẠI CHỨNG TỪ PHÙ HỢP: {cfg['allowed_proof_types']}.\n"
        f"Hãy tuân thủ nghiêm ngặt Decision Tree trên khi phân tích và trích xuất."
    )


class _PersonaRegistry:
    """Known inspecting "personas".  Used only for the mock fallback, and for the UI
    ``persona_role_used`` field that Manager inspectors see."""

    PERSONA_DOCTOR_VL = "Bác sĩ Chuyên viên Khoa Nội tổng quát (VLM)"
    PERSONA_HR_ADJUDICATOR = "Nhân viên Hồ sơ BHXH / Chứng từ (VLM)"
    PERSONA_FORENSIC = "Chuyên viên Pháp lý Chứng từ (VLM)"
    PERSONA_ADMIN = "Nhân viên Hành chính Tổng hợp (VLM)"


_MOCK_PROFILES: Dict[str, Dict[str, Any]] = {
    "none": {
        "doc_patient_name": None,
        "doc_diagnosis": None,
        "has_red_stamp": None,
        "has_doctor_signature": None,
        "is_tampered": None,
        "ai_edited": None,
        "days_granted_by_doctor": None,
        "correlation_score": None,
        "correlation_issues": [],
        "persona_role_used": None,
        "escalation_reasons": [],
        "proof_extra": {"proof_type": ProofType.NONE},
    },
    "clean_prescription": {
        "doc_patient_name": None,  # caller overrides with employee_name when missing
        "doc_diagnosis": "Cảm cúm mùa (influenza-like), viêm họng cấp, sổ mũi nghẹt mũi, ho khan rát họng",
        "has_red_stamp": True,
        "has_doctor_signature": True,
        "is_tampered": False,
        "ai_edited": False,
        "correlation_score": 0.97,
        "correlation_issues": [],
        "persona_role_used": _PersonaRegistry.PERSONA_DOCTOR_VL,
        "escalation_reasons": [],
        "proof_extra": {
            "proof_type": ProofType.MEDICAL_LEAVE_CERTIFICATE,
            "issuer": "Bệnh viện Đa khoa TPHCM - Khoa Cấp cứu",
            "document_readability": "READABLE",
            "digital_signature_present": True,
            "recommended_from_date": "2026-04-13",
            "recommended_to_date": "2026-04-22",
            "recommended_leave_days": 7,
            "issue_date": "2026-04-12",
            "fields_detected": [
                "patient_name", "diagnosis", "issue_date",
                "recommended_from_date", "recommended_to_date",
                "issuer_red_stamp", "doctor_signature",
            ],
        },
    },
    "vague_prescription": {
        "doc_patient_name": None,
        "doc_diagnosis": "Có dấu hiệu sốt siêu vi, khả năng cúm A/H3N2 (chưa test PCR)",
        "has_red_stamp": False,
        "has_doctor_signature": False,
        "is_tampered": False,
        "ai_edited": None,
        "correlation_score": 0.52,
        "correlation_issues": [
            "Không thấy dấu mộc đỏ tròn của Bệnh viện / Phòng khám",
            "Chữ ký bác sĩ bị cắt xén góc phải, không xác minh được",
            "Ảnh chụp thiếu sáng, một số con số ngày tháng khó đọc",
            "Chẩn đoán chỉ ghi là 'sốt' không cụ thể, có dấu hiệu chưa hoàn chỉnh ký",
        ],
        "persona_role_used": _PersonaRegistry.PERSONA_DOCTOR_VL,
        "escalation_reasons": [
            "DOC_MISSING_RED_STAMP",
            "DOC_SIGNATURE_UNVERIFIABLE",
            "DOC_LOW_READABILITY",
        ],
        "proof_extra": {
            "proof_type": ProofType.MEDICAL_LEAVE_CERTIFICATE,
            "issuer": "Phòng khám Gia đình Quận 3 - Chi nhánh 2",
            "document_readability": "ILLEGIBLE",
            "signature_present": False,
            "digital_signature_present": False,
            "recommended_from_date": "2026-04-20",
            "recommended_to_date": "2026-04-22",
            "recommended_leave_days": 3,
            "issue_date": "2026-04-19",
            "fields_detected": ["patient_name", "diagnosis_fragment", "issue_date_fragment"],
        },
    },
    "hospital_discharge": {
        "doc_patient_name": None,
        "doc_diagnosis": "Viêm phổi cộng đồng, xuất viện điều trị ngoại trú tiếp theo",
        "has_red_stamp": True,
        "has_doctor_signature": True,
        "is_tampered": False,
        "ai_edited": False,
        "correlation_score": 0.99,
        "correlation_issues": [],
        "persona_role_used": _PersonaRegistry.PERSONA_HR_ADJUDICATOR,
        "escalation_reasons": [],
        "proof_extra": {
            "proof_type": ProofType.HOSPITAL_DISCHARGE,
            "issuer": "Bệnh viện Chợ Rẫy - Khoa Hô hấp",
            "document_readability": "READABLE",
            "signature_present": True,
            "digital_signature_present": True,
            "recommended_from_date": "2026-05-02",
            "recommended_to_date": "2026-06-01",
            "recommended_leave_days": 30,
            "issue_date": "2026-05-01",
            "fields_detected": [
                "admission_date", "discharge_date", "patient_dob",
                "diagnosis_4line", "doctor_signature", "hospital_stamp_red",
                "bhxh_code",
            ],
        },
    },
    "handwritten_note": {
        "doc_patient_name": None,
        "doc_diagnosis": "(Viết tay khó đọc) Đau bụng tiêu chảy nghi ngờ ngộ độc thực phẩm",
        "has_red_stamp": False,
        "has_doctor_signature": None,
        "is_tampered": None,
        "ai_edited": None,
        "correlation_score": 0.34,
        "correlation_issues": [
            "Giấy viết tay trên phiếu trắng không có đầu báo bệnh viện",
            "Không tìm thấy dấu đỏ hay tem chống giả",
            "Chữ ký cuối trang không khớp mẫu chữ ký bác sĩ công khai phòng khám",
            "Ngày cấp và ngày nghỉ viết gần giống nhau, có dấu hiệu tẩy xoá mực",
        ],
        "persona_role_used": _PersonaRegistry.PERSONA_FORENSIC,
        "escalation_reasons": [
            "DOC_NO_OFFICIAL_LETTERHEAD",
            "DOC_SIGNATURE_ANOMALY",
            "DOC_ERASURE_SUSPECTED",
        ],
        "proof_extra": {
            "proof_type": ProofType.MEDICAL_RECORD_SUMMARY,
            "issuer": "Nguồn chưa xác minh (giấy viết tay)",
            "document_readability": "ILLEGIBLE",
            "signature_present": None,
            "digital_signature_present": False,
            "recommended_from_date": "2026-04-20",
            "recommended_to_date": "2026-04-22",
            "recommended_leave_days": 2,
            "issue_date": "2026-04-19",
            "fields_detected": ["handwritten_text_fragment"],
        },
    },
    "photo_id": {
        "doc_patient_name": None,
        "doc_diagnosis": None,
        "has_red_stamp": None,
        "has_doctor_signature": None,
        "is_tampered": None,
        "ai_edited": None,
        "correlation_score": 0.08,
        "correlation_issues": [
            "Tệp đính kèm là CCCD/CMND (chứng minh nhân thân), KHÔNG phải giấy khám bệnh.",
            "Không có trường thông tin bác sĩ, chẩn đoán hay khoảng ngày nghỉ được đề nghị.",
            "Không có giá trị làm căn cứ duyệt nghỉ bệnh có hưởng BHXH.",
        ],
        "persona_role_used": _PersonaRegistry.PERSONA_ADMIN,
        "escalation_reasons": [
            "DOC_WRONG_DOCUMENT_CLASS",
            "DOC_MISSING_MANDATORY_CLINICAL_FIELDS",
        ],
        "proof_extra": {
            "proof_type": ProofType.OTHER,
            "issuer": "Cục Cảnh sát đăng ký quản lý cư trú (CCCD)",
            "document_readability": "READABLE",
            "signature_present": None,
            "digital_signature_present": None,
            "recommended_from_date": None,
            "recommended_to_date": None,
            "recommended_leave_days": 0,
            "issue_date": None,
            "fields_detected": ["id_number", "full_name", "dob", "address", "qr_code"],
        },
    },
    "fake_document": {
        "doc_patient_name": None,
        "doc_diagnosis": "Gãy xương bàn chân trái (nghi ngờ làm giả, có triệu chứng Photoshop chữ ký)",
        "has_red_stamp": False,
        "has_doctor_signature": False,
        "is_tampered": True,
        "ai_edited": True,
        "correlation_score": 0.06,
        "correlation_issues": [
            "Pixel xung quanh chữ ký bác sĩ không liên tục (dấu hiệu copy/paste từ tài liệu khác)",
            "Màu dấu đỏ có histogram phẳng không tự nhiên (giả lập qua AI photoshop)",
            "Mã BHYT trên giấy check trên cổng VssID không tồn tại theo số CCCD bệnh nhân",
            "Chẩn đoán 'gãy xương' nhưng giấy không có kết luận X-quang hay hình ảnh kèm theo",
        ],
        "persona_role_used": _PersonaRegistry.PERSONA_FORENSIC,
        "escalation_reasons": [
            "DOC_FORGERY_SUSPECTED_SIGNATURE_CLONE",
            "DOC_AI_GENERATED_STAMP_PIXEL",
            "DOC_BHYT_ID_NOT_VERIFIABLE",
            "DOC_CLINICAL_CLAIM_UNSUPPORTED",
        ],
        "proof_extra": {
            "proof_type": ProofType.MEDICAL_LEAVE_CERTIFICATE,
            "issuer": "Bệnh viện đa khoa không xác minh được (giả lập)",
            "document_readability": "READABLE",
            "signature_present": False,
            "digital_signature_present": False,
            "recommended_from_date": "2026-05-02",
            "recommended_to_date": "2026-05-05",
            "recommended_leave_days": 4,
            "issue_date": "2026-05-01",
            "fields_detected": [
                "fake_patient_name", "forged_signature_detected", "synthetic_stamp",
            ],
        },
    },
}


def _profile_key(attachment_type: str, proof_type: Optional[str] = None,
                 document_readability: Optional[str] = None,
                 has_signature=None, has_stamp=None, is_tampered=None,
                 ai_edited=None) -> str:
    t = (attachment_type or "").strip().casefold()
    pt = (proof_type or "").strip().casefold()
    readability = (document_readability or "").strip().casefold()
    if (not t or t == "none") and not pt and readability in ("unknown", ""):
        return "none"
    for key in ("clean_prescription", "vague_prescription", "hospital_discharge",
                "handwritten_note", "photo_id", "fake_document"):
        if (t and (key in t or t.startswith(key))) or (pt and key.replace("_"," ") in pt):
            return key
    # Strong signals from VLM flags: AI edited or tampered -> fake profile
    if is_tampered or ai_edited:
        return "fake_document"
    # Readability unknown with no flags yet: default clean (pending real OCR)
    if readability and readability != "readable":
        return "vague_prescription"
    # Medical certificate proof types map onto clean_prescription by default
    if any(k in pt for k in ("medical", "certificate", "leave", "sick", "khambenh", "donthuoc", "giaynghi")):
        return "clean_prescription"
    if any(k in pt for k in ("discharge", "xuat vien", "inpatient", "vienphi", "hospital")):
        return "hospital_discharge"
    if any(k in pt for k in ("marriage", "death", "birth", "identity", "id", "cccd", "cmnd", "passport")):
        return "photo_id"
    if any(k in t for k in ("clean", "prescription_clean", "certified", "verified")):
        return "clean_prescription"
    if any(k in t for k in ("vague", "blur", "unclear", "indistinct", "low_quality")):
        return "vague_prescription"
    if any(k in t for k in ("discharge", "xuat vien", "xv", "inpatient")):
        return "hospital_discharge"
    if any(k in t for k in ("handwritten", "write", "viet tay", "note", "tay")):
        return "handwritten_note"
    if any(k in t for k in ("photo_id", "cccd", "cmnd", "id_card", "identity")):
        return "photo_id"
    if any(k in t for k in ("fake", "forgery", "synthetic", "gia mao", "fake_document")):
        return "fake_document"
    if has_signature is False or has_stamp is False:
        return "vague_prescription"
    return "clean_prescription"  # default safe: treat as clean so deterministic engine runs


class VLMUnavailableError(RuntimeError):
    """Raised when real VLM inference cannot be performed and mock fallback is disabled."""


@dataclass
class VLMInspectionOutput:
    """Public output shape.  Maps 1-to-1 onto the 13 extended DB columns + full JSON blobs."""

    vlm_analysis_json: Dict[str, Any]
    doc_patient_name: Optional[str]
    doc_diagnosis: Optional[str]
    has_red_stamp: Optional[bool]
    has_doctor_signature: Optional[bool]
    is_tampered: Optional[bool]
    ai_edited: Optional[bool]
    days_granted_by_doctor: Optional[int]
    correlation_score: Optional[float]
    correlation_issues: list[str]
    persona_role_used: Optional[str]
    escalation_reasons_json: list[str]
    proof_extraction: ProofExtraction  # what gets injected into the rule engine
    vlm_error: Optional[str] = None

    @property
    def patient_name(self):
        return self.proof_extraction.patient_name if self.proof_extraction else None

    @property
    def signature_present(self):
        return self.proof_extraction.signature_present if self.proof_extraction else None

    @property
    def proof_type(self):
        if not self.proof_extraction: return 'NONE'
        pt = self.proof_extraction.proof_type
        return pt.value if hasattr(pt, 'value') else str(pt)


# Leave types where clinical diagnosis keywords are NOT applicable
_NON_MEDICAL_LEAVE_TYPES = frozenset({
    'SPECIAL_PAID', 'STATUTORY_UNPAID', 'UNPAID_OTHER', 'ANNUAL', 'MATERNITY', 'WORK_ACCIDENT'
})
_MEDICAL_KWS = (
    "cúm", "sốt", "đau", "ho", "khó thở", "viêm", "phổi", "nhiễm", "xuất viện",
    "ngộ độc", "gãy", "trật", "hô hấp", "cảm", "sổ mũi", "nghẹt mũi", "họng",
    "đau đầu", "mệt mỏi", "amidan", "đơn thuốc", "nằm viện"
)
_MEDICAL_CONCEPT_GROUPS = (
    {'ruột thừa', 'appendicitis', 'viêm ruột thừa', 'đau ruột thừa', 'phẫu thuật ruột thừa', 'cắt ruột thừa'},
    {'phổi', 'viêm phổi', 'pneumonia'},
    {'cúm', 'cúm a', 'influenza'},
    {'gãy', 'fracture', 'xương'},
)


def _same_medical_concept(reason: str, diagnosis: str) -> bool:
    reason_text = reason.casefold()
    diagnosis_text = diagnosis.casefold()
    return any(
        any(term in reason_text for term in group)
        and any(term in diagnosis_text for term in group)
        for group in _MEDICAL_CONCEPT_GROUPS
    )


def _score_correlation(
    employee_name: str,
    reason: str,
    recommended_from: Optional[date],
    recommended_to: Optional[date],
    requested_from: Optional[date],
    requested_to: Optional[date],
    diagnosis: Optional[str],
    days_granted_by_doctor: Optional[int],
    requested_workdays: int,
    leave_type: str = '',
    patient_name_on_doc: Optional[str] = None,
) -> tuple[Optional[float], list[str], Optional[int]]:
    """Deterministic correlation scoring between employee claim + VLM findings.

    For non-medical leave types (SPECIAL_PAID, STATUTORY_UNPAID, MATERNITY, WORK_ACCIDENT),
    skip the clinical-keyword check — marriage/death certs don't have diagnoses.
    """
    if leave_type.upper() in {'SPECIAL_PAID', 'STATUTORY_UNPAID'}:
        return None, [], days_granted_by_doctor

    score = 0.60
    issues: list[str] = []
    is_medical = leave_type.upper() not in _NON_MEDICAL_LEAVE_TYPES

    if patient_name_on_doc and employee_name:
        norm_doc = re.sub(r"\s+", "", str(patient_name_on_doc)).casefold()
        norm_emp = re.sub(r"\s+", "", str(employee_name)).casefold()
        if norm_doc != norm_emp:
            score -= 0.22
            issues.append(f"Tên trên giấy ('{patient_name_on_doc}') không trùng với tên nhân sự ('{employee_name}').")
        else:
            score += 0.08

    # Chỉ check từ khóa y tế khi là loại nghỉ bệnh (SICK_MEDICAL, MEDICAL_EMERGENCY)
    if is_medical:
        if reason and diagnosis:
            r, d = reason.casefold(), diagnosis.casefold()
            overlap = sum(1 for kw in _MEDICAL_KWS if kw in r and kw in d)
            if overlap == 0 and not _same_medical_concept(reason, diagnosis):
                score -= 0.20
                issues.append("Chẩn đoán trên giấy không trùng khớp mô tả lý do nghỉ.")
            else:
                score += min(0.12, 0.04 * max(overlap, 1))
        elif not diagnosis:
            score -= 0.10
            issues.append("VLM không đọc được chẩn đoán lâm sàng trên chứng từ.")
    else:
        # Loại nghỉ sự kiện gia đình / không lương: không penalize vì thiếu "chẩn đoán"
        # Nếu VLM đọc được event_reason / tên người liên quan → điểm thưởng nhỏ
        if diagnosis:
            score += 0.05  # bonus: VLM đọc được nội dung sự kiện

    # date coverage: khoảng ngày xin nghỉ phải nằm trong khoảng ngày chứng từ cho phép
    date_label = "bác sĩ chỉ định" if is_medical else "ghi trong chứng từ"
    if recommended_from and recommended_to and requested_from and requested_to:
        if not (recommended_from <= requested_from and requested_to <= recommended_to):
            score -= 0.25
            issues.append(
                f"Khoảng nghỉ yêu cầu ({requested_from} → {requested_to}) nằm ngoài khoảng "
                f"{date_label} ({recommended_from} → {recommended_to})."
            )
        else:
            score += 0.12
    else:
        # Với giấy sự kiện gia đình hoặc cấp cứu: nếu không đọc được ngày thì không penalize nặng
        if is_medical:
            if leave_type.upper() == 'MEDICAL_EMERGENCY':
                # Cấp cứu nhập viện khẩn: chưa xác định ngày ra viện (open-ended), không phạt
                score += 0.05
            else:
                score -= 0.10
                issues.append(f"VLM không đọc được khoảng ngày {date_label}.")
        # Non-medical: skip penalty (giấy cưới thường chỉ có 1 ngày, không range)

    # days coverage vs requested
    if days_granted_by_doctor is None:
        if requested_workdays and recommended_from and recommended_to:
            try:
                days_granted_by_doctor = (recommended_to - recommended_from).days + 1
                score += 0.03
            except Exception:
                days_granted_by_doctor = None
    if days_granted_by_doctor is not None and requested_workdays:
        days_label = "bác sĩ cho" if is_medical else "chứng từ ghi nhận"
        if requested_workdays > days_granted_by_doctor:
            score -= 0.18
            issues.append(
                f"Số ngày xin nghỉ ({requested_workdays} ngày) VƯỢT quá số ngày "
                f"{days_label} ({days_granted_by_doctor} ngày)."
            )
        else:
            score += 0.08

    score = round(max(0.0, min(1.0, score)), 3)
    return score, issues, days_granted_by_doctor


def _normalize_proof_type(val: Any) -> ProofType:
    if isinstance(val, ProofType):
        return val
    if not val:
        return ProofType.NONE
    s = str(val).strip().upper()
    try:
        return ProofType(s)
    except ValueError:
        pass
    ALIAS_MAP = {
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


def _build_proof_extraction(
    profile: Dict[str, Any],
    leave_type: str,
    employee_name: Optional[str],
    from_date: Optional[date],
    to_date: Optional[date],
    workdays: int,
) -> ProofExtraction:
    extra = dict(profile.get("proof_extra") or {})
    raw_pt = extra.pop("proof_type", ProofType.NONE)
    pt = _normalize_proof_type(raw_pt)

    def _gf(*keys):
        for k in keys:
            if k in profile and profile[k] is not None: return profile[k]
            if k in extra and extra[k] is not None: return extra[k]
        return None

    issue_day_1 = from_date
    issue_day = (issue_day_1 - timedelta(days=1)) if issue_day_1 else None
    # Extract date strings or date objects
    def _as_date(v, default):
        if not v: return default
        if isinstance(v, date): return v
        try: return date.fromisoformat(str(v))
        except Exception: return default

    readability = _gf("document_readability") or "UNKNOWN"
    is_unreadable = readability in ("UNREADABLE", "ILLEGIBLE") or bool(profile.get("_blur_gate_triggered"))
    is_none = (pt == ProofType.NONE or profile.get("persona_role_used") == "VLM_UNAVAILABLE")
    is_real = bool(profile.get("_blur_gate_triggered") or "OLLAMA_REAL" in str(profile.get("inspection_mode", "")))

    if is_unreadable:
        rec_fr = None
        rec_to = None
        patient_name = None
        issue_d = None
        doc_readability = "UNREADABLE"
    elif is_real:
        rec_fr = _as_date(_gf("recommended_from","recommended_from_date","from_date"), None)
        rec_to = _as_date(_gf("recommended_to","recommended_to_date","to_date"), None)
        patient_name = profile.get("doc_patient_name") or _gf("patient_name")
        issue_d = _as_date(_gf("issue_date"), None)
        doc_readability = readability
    else:
        # Mock persona fallback for deterministic tests
        rec_fr = _as_date(_gf("recommended_from","recommended_from_date","from_date"), None if is_none else from_date)
        rec_to = _as_date(_gf("recommended_to","recommended_to_date","to_date"), None if is_none else to_date)
        patient_name = profile.get("doc_patient_name") or (None if is_none else employee_name)
        issue_d = _as_date(_gf("issue_date"), None if is_none else issue_day)
        doc_readability = readability if readability != "UNKNOWN" else ("UNKNOWN" if is_none else "READABLE")

    sig = _gf("signature_present")
    if sig is None and profile.get("has_doctor_signature") is not None:
        sig = bool(profile.get("has_doctor_signature"))

    try:
        p = ProofExtraction(
            proof_type=pt,
            issuer=_gf("issuer") if not is_unreadable else None,
            patient_name=patient_name,
            issue_date=issue_d,
            recommended_from_date=rec_fr,
            recommended_to_date=rec_to,
            signature_present=sig if not is_unreadable else False,
            digital_signature_present=_gf("digital_signature_present") if not is_unreadable else None,
            document_readability=doc_readability,
            fields_detected=list(_gf("fields_detected") or []) if not is_unreadable else [],
            is_open_ended=_gf("is_open_ended") if not is_unreadable else None,
            requires_followup_proof=_gf("requires_followup_proof") if not is_unreadable else None,
            admission_date=_as_date(_gf("admission_date"), None) if not is_unreadable else None,
            discharge_date=_as_date(_gf("discharge_date"), None) if not is_unreadable else None,
            doc_diagnosis=_gf("doc_diagnosis") if not is_unreadable else None,
            emergency_diagnosis=_gf("emergency_diagnosis") if not is_unreadable else None,
            days_granted_by_doctor=_gf("days_granted_by_doctor") if not is_unreadable else None,
            deceased_name=_gf("deceased_name") if not is_unreadable else None,
            subject_name=_gf("subject_name") if not is_unreadable else None,
            partner_name=_gf("partner_name") if not is_unreadable else None,
            wedding_date=_as_date(_gf("wedding_date"), None) if not is_unreadable else None,
            event_type=_gf("event_type") if not is_unreadable else None,
            date_of_death=_as_date(_gf("date_of_death"), None) if not is_unreadable else None,
            funeral_date=_as_date(_gf("funeral_date"), None) if not is_unreadable else None,
            relationship_label=_gf("relationship_label") if not is_unreadable else None,
            relationship_to_employee=_gf("relationship_to_employee") if not is_unreadable else None,
            evidence_confidence=_gf("evidence_confidence") if not is_unreadable else None,
            needs_manager_review=_gf("needs_manager_review") if not is_unreadable else None,
            maternity_phase=_gf("maternity_phase") if not is_unreadable else None,
            expected_due_date=_as_date(_gf("expected_due_date"), None) if not is_unreadable else None,
            bhxh_code=_gf("bhxh_code") if not is_unreadable else None,
            injury_description=_gf("injury_description") if not is_unreadable else None,
            is_workplace_related=_gf("is_workplace_related") if not is_unreadable else None,
            injury_date=_as_date(_gf("injury_date"), None) if not is_unreadable else None,
            has_red_stamp=_gf("has_red_stamp") if not is_unreadable else None,
            has_doctor_signature=_gf("has_doctor_signature") if not is_unreadable else None,
            is_tampered=_gf("is_tampered") if not is_unreadable else None,
            ai_edited=_gf("ai_edited") if not is_unreadable else None,
            has_hospital_stamp=_gf("has_hospital_stamp") if not is_unreadable else None,
            has_bhxh_stamp=_gf("has_bhxh_stamp") if not is_unreadable else None,
            document_purpose=_gf("document_purpose") if not is_unreadable else None,
            valid_from=_as_date(_gf("valid_from"), None) if not is_unreadable else None,
            valid_to=_as_date(_gf("valid_to"), None) if not is_unreadable else None,
        )
    except Exception:
        p = ProofExtraction(
            proof_type=ProofType.OTHER,
            issuer=_gf("issuer") if not is_unreadable else None,
            patient_name=patient_name,
            issue_date=issue_d,
            recommended_from_date=rec_fr,
            recommended_to_date=rec_to,
            signature_present=sig if not is_unreadable else False,
            digital_signature_present=_gf("digital_signature_present") if not is_unreadable else None,
            document_readability=doc_readability,
            fields_detected=list(_gf("fields_detected") or []) if not is_unreadable else [],
        )
    return p


def inspect_document_with_vlm(
    leave_type: str,
    employee_name: Optional[str] = None,
    reason: str = "",
    attachment_path_or_type: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    workdays: int = 0,
    mock_data: Optional[Dict[str, Any]] = None,
    proof_type_hint: Optional[str] = None,
    document_readability_hint: Optional[str] = None,
    doc_flags: Optional[Dict[str, Any]] = None,
    allow_mock_fallback: Optional[bool] = None,
    reason_category: Optional[str] = None,
) -> VLMInspectionOutput:
    """Entry point.  Chạy VLM thật (Ollama qwen2.5vl:7b) trên ảnh thực tế.

    Mô hình chạy (ưu tiên từ cao xuống thấp):
      1. mock_data được truyền trực tiếp  -> dùng mock này (chế độ test tường minh)
      2. VLM_FORCE_MOCK=1                -> dùng persona mock (dev/test)
      3. Gọi Ollama thật                 -> dùng kết quả VLM thật
      4. Nếu (3) lỗi:
         - allow_mock_fallback=True HOẶC VLM_ALLOW_MOCK_FALLBACK=1 -> fallback sang mock + gắn vlm_error
         - mặc định (tích hợp thật) -> raise VLMUnavailableError để caller xử lý
    """
    requested_from = from_date
    requested_to = to_date
    flags = doc_flags or {}
    fallback_allowed = (
        allow_mock_fallback if allow_mock_fallback is not None else VLM_MOCK_FALLBACK_ALLOWED
    )

    profile_raw: Dict[str, Any]
    vlm_error: Optional[str] = None
    mode_used = "UNKNOWN"

    # ---- Case 1: Mock được truyền tường minh (test/debug) ----
    if mock_data:
        profile_raw = mock_data
        mode_used = "EXPLICIT_MOCK_DATA"
    # ---- Case 2: Force mock bằng env (dev mode) ----
    elif VLM_FORCE_MOCK:
        key = _profile_key(
            str(attachment_path_or_type or "none"),
            proof_type=proof_type_hint,
            document_readability=document_readability_hint,
            has_signature=flags.get("has_signature"),
            has_stamp=flags.get("has_stamp"),
            is_tampered=flags.get("is_tampered"),
            ai_edited=flags.get("ai_edited"),
        )
        if key == "none":
            key = "clean_prescription"
        profile_raw = dict(_MOCK_PROFILES.get(key, _MOCK_PROFILES["clean_prescription"]))
        mode_used = "ENV_FORCE_PERSONA_MOCK"
    # ---- Case 3: Thực thi VLM thật (mặc định tích hợp thật) ----
    else:
        real_result, error_detail = _try_ollama_extract(
            attachment_path_or_type, leave_type=leave_type, reason_category=reason_category
        )
        if real_result:
            profile_raw = real_result
            if real_result.get("_blur_gate_triggered"):
                mode_used = "CV_BLUR_GATE_EARLY_EXIT"
            elif real_result.get("_from_cache"):
                mode_used = "VLM_CACHE_HIT"
            else:
                mode_used = "OLLAMA_REAL_QWEN25_VL_3B"
        else:
            vlm_error = error_detail or f"VLM ({VLM_TARGET_MODEL}) không thể xử lý chứng từ này."
            if fallback_allowed:
                key = _profile_key(
                    str(attachment_path_or_type or "none"),
                    proof_type=proof_type_hint,
                    document_readability=document_readability_hint,
                    has_signature=flags.get("has_signature"),
                    has_stamp=flags.get("has_stamp"),
                    is_tampered=flags.get("is_tampered"),
                    ai_edited=flags.get("ai_edited"),
                )
                if key == "none":
                    key = "clean_prescription"
                profile_raw = dict(_MOCK_PROFILES.get(key, _MOCK_PROFILES["clean_prescription"]))
                mode_used = "PERSONA_MOCK_FALLBACK_AFTER_VLM_FAIL"
            else:
                profile_raw = {
                    "doc_patient_name": None,
                    "doc_diagnosis": None,
                    "has_red_stamp": None,
                    "has_doctor_signature": None,
                    "is_tampered": None,
                    "ai_edited": None,
                    "days_granted_by_doctor": None,
                    "correlation_score": 0.0,
                    "correlation_issues": [vlm_error],
                    "persona_role_used": "VLM_UNAVAILABLE",
                    "escalation_reasons": ["VLM_UNAVAILABLE"],
                    "proof_extra": {
                        "proof_type": ProofType.NONE,
                        "issuer": None,
                        "issue_date": None,
                        "recommended_from_date": None,
                        "recommended_to_date": None,
                        "signature_present": None,
                        "digital_signature_present": None,
                        "document_readability": "UNKNOWN",
                        "fields_detected": [],
                    },
                }
                mode_used = "VLM_UNAVAILABLE"

    # ---- doctor-granted days: try explicit or derive from profile + recommended range
    days_explicit = profile_raw.get("days_granted_by_doctor")
    proof_extraction = _build_proof_extraction(
        profile_raw, leave_type, employee_name, requested_from, requested_to, workdays
    )
    dfd = proof_extraction.recommended_from_date
    dtd = proof_extraction.recommended_to_date

    # --- correlation score --- (leave_type-aware: skip medical keywords for family events)
    score, issues_plus, doctor_days_final = _score_correlation(
        employee_name=employee_name or "",
        reason=reason or "",
        recommended_from=dfd,
        recommended_to=dtd,
        requested_from=requested_from,
        requested_to=requested_to,
        diagnosis=profile_raw.get("doc_diagnosis"),
        days_granted_by_doctor=days_explicit,
        requested_workdays=workdays,
        leave_type=leave_type,
        patient_name_on_doc=profile_raw.get("doc_patient_name") or proof_extraction.patient_name,
    )
    if days_explicit is None and doctor_days_final is not None:
        profile_raw["days_granted_by_doctor"] = doctor_days_final

    merged_issues = list(profile_raw.get("correlation_issues") or []) + list(issues_plus)
    merged_issues = list(dict.fromkeys(merged_issues))

    # ---- build vlm_analysis_json (Manager panel sees this full shape) ----
    is_doc_unreadable = (proof_extraction.document_readability in ('UNREADABLE', 'ILLEGIBLE')) or bool(profile_raw.get("_blur_gate_triggered"))

    if is_doc_unreadable:
        final_pat_name = None
        final_diagnosis = None
        final_days = None
        final_dfd = None
        final_dtd = None
        final_issuer = None
        final_issue_d = None
        final_score = 0.0
    else:
        final_pat_name = profile_raw.get("doc_patient_name") or proof_extraction.patient_name
        final_diagnosis = profile_raw.get("doc_diagnosis")
        final_days = profile_raw.get("days_granted_by_doctor")
        final_dfd = dfd.isoformat() if dfd else None
        final_dtd = dtd.isoformat() if dtd else None
        final_issuer = proof_extraction.issuer
        final_issue_d = proof_extraction.issue_date.isoformat() if proof_extraction.issue_date else None
        final_score = score

    vlm_json: Dict[str, Any] = {
        "inspector_persona": profile_raw.get("persona_role_used"),
        "target_model": VLM_TARGET_MODEL,
        "inspection_mode": mode_used,
        "inspected_at": datetime.now().isoformat(timespec="seconds"),
        "vlm_error": vlm_error,
        "document_summary": {
            "patient_name": final_pat_name,
            "diagnosis": final_diagnosis,
            "issuer": final_issuer,
            "issue_date": final_issue_d,
            "doctor_recommended_range": {
                "from": final_dfd,
                "to": final_dtd,
                "days": final_days,
            },
            "is_open_ended": proof_extraction.is_open_ended,
            "requires_followup_proof": proof_extraction.requires_followup_proof,
            "admission_date": proof_extraction.admission_date.isoformat() if proof_extraction.admission_date else None,
            "discharge_date": proof_extraction.discharge_date.isoformat() if proof_extraction.discharge_date else None,
            "deceased_name": proof_extraction.deceased_name,
            "subject_name": proof_extraction.subject_name,
            "partner_name": proof_extraction.partner_name,
            "event_type": proof_extraction.event_type,
            "relationship": proof_extraction.relationship_to_employee or proof_extraction.relationship_label,
            "wedding_date": proof_extraction.wedding_date.isoformat() if proof_extraction.wedding_date else None,
        },
        "flags": {
            "has_red_stamp": profile_raw.get("has_red_stamp"),
            "has_doctor_signature": profile_raw.get("has_doctor_signature"),
            "signature_present_on_scan": proof_extraction.signature_present,
            "digital_signature_present": proof_extraction.digital_signature_present,
            "document_readability": proof_extraction.document_readability,
            "is_tampered": profile_raw.get("is_tampered"),
            "ai_generated_or_edited": profile_raw.get("ai_edited"),
        },
        "correlation_analysis": {
            "score": final_score,
            "issues": merged_issues,
            "requested_workdays": workdays,
        },
        "escalation_flags": list(profile_raw.get("escalation_reasons") or []),
        "raw_fields_detected": list(proof_extraction.fields_detected),
    }

    out = VLMInspectionOutput(
        vlm_analysis_json=vlm_json,
        doc_patient_name=final_pat_name,
        doc_diagnosis=final_diagnosis,
        has_red_stamp=profile_raw.get("has_red_stamp"),
        has_doctor_signature=(profile_raw.get("has_doctor_signature")
                              if profile_raw.get("has_doctor_signature") is not None
                              else proof_extraction.signature_present),
        is_tampered=profile_raw.get("is_tampered"),
        ai_edited=profile_raw.get("ai_edited"),
        days_granted_by_doctor=final_days,
        correlation_score=final_score,
        correlation_issues=merged_issues,
        persona_role_used=profile_raw.get("persona_role_used"),
        escalation_reasons_json=list(profile_raw.get("escalation_reasons") or []),
        proof_extraction=proof_extraction,
        vlm_error=vlm_error,
    )
    return out


# ---------------- Real Ollama integration ----------------

def _ollama_reachable() -> bool:
    ok, _, _ = ollama_tags(timeout=2.0)
    return ok


def _ollama_loaded_models() -> list[str]:
    _, names, _ = ollama_tags(timeout=2.0)
    return names


def _resolve_persona_by_proof_type(proof_type_str: Optional[str]) -> str:
    if not proof_type_str:
        return _PersonaRegistry.PERSONA_HR_ADJUDICATOR
    s = str(proof_type_str).upper()
    if any(k in s for k in ("MEDICAL", "HOSPITAL", "LAB", "MATERNITY", "ACCIDENT", "SICK")):
        return _PersonaRegistry.PERSONA_DOCTOR_VL
    if any(k in s for k in ("DEATH", "FUNERAL", "MARRIAGE", "WEDDING", "FAMILY")):
        return _PersonaRegistry.PERSONA_HR_ADJUDICATOR
    if any(k in s for k in ("IDENTITY", "VISA", "TRAVEL", "ADMINISTRATIVE")):
        return _PersonaRegistry.PERSONA_ADMIN
    if "NONE" in s:
        return _PersonaRegistry.PERSONA_FORENSIC
    return _PersonaRegistry.PERSONA_HR_ADJUDICATOR



def detect_image_blur(path: Optional[str], threshold: float = 50.0) -> tuple[bool, float]:
    """Kiểm tra độ nét của ảnh chứng từ bằng phương sai toán tử Laplacian qua OpenCV.
    Trả về: (is_blurry: bool, score: float).
    Ảnh tài liệu văn bản rõ nét bình thường có điểm > 500 - 3000+.
    Ảnh mờ, mất nét, rung lắc thường có điểm < 10 - 50.
    """
    if not path or not os.path.isfile(path):
        return False, 999.0
    try:
        import cv2
        import numpy as np
        img = None
        try:
            data = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception:
            pass
        if img is None:
            img = cv2.imread(path)
        if img is None:
            return False, 999.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        if max(h, w) > 600:
            scale = 600.0 / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return (score < threshold, round(score, 2))
    except Exception:
        return False, 999.0


def prepare_image_for_vlm(path: str, max_dim: int = VLM_MAX_IMAGE_DIM) -> str:
    """Tự động resize ảnh (tối đa max_dim px, mặc định 1600px) trước khi gửi VLM.
    - Căn chỉnh kích thước là bội số của 28 (chuẩn patch token của Qwen-VL).
    - Giới hạn chiều dài nhất không vượt quá 1600px để giữ nguyên độ nét OCR chứng từ mà không gây OOM.
    - Tự động chuyển hệ màu sang RGB nếu là RGBA hoặc P.
    - Nén JPEG chất lượng cao (quality=85) và mã hóa base64.
    """
    import base64
    import io
    try:
        from PIL import Image
        pil_img = None
        try:
            pil_img = Image.open(path)
        except Exception:
            with open(path, "rb") as f_in:
                raw_bytes = f_in.read()
            pil_img = Image.open(io.BytesIO(raw_bytes))
        with pil_img:
            w, h = pil_img.size
            nw = max(28, round(w / 28) * 28)
            nh = max(28, round(h / 28) * 28)
            if nw > max_dim or nh > max_dim:
                scale = max_dim / max(nw, nh)
                nw = max(28, int(round((nw * scale) / 28) * 28))
                nh = max(28, int(round((nh * scale) / 28) * 28))
            if (nw, nh) != (w, h):
                pil_img = pil_img.resize((nw, nh), Image.Resampling.LANCZOS)
            if pil_img.mode in ("RGBA", "P"):
                pil_img = pil_img.convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")


_VLM_CACHE_MEM: Dict[str, Dict[str, Any]] = {}


def _compute_file_sha256(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    try:
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _get_vlm_cache_dir() -> Path:
    base = Path(os.getenv("LEAVE_UPLOAD_DIR", str(Path(__file__).resolve().parents[1] / "backend" / "uploads")))
    cache_dir = base / "vlm_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _vlm_cache_path(file_hash: str, leave_type: str = "", reason_category: str = "") -> Path:
    context = f"{leave_type or ''}:{reason_category or ''}"
    if not context.strip(":"):
        return _get_vlm_cache_dir() / f"{file_hash}.json"
    import hashlib
    context_hash = hashlib.sha256(context.encode("utf-8")).hexdigest()[:16]
    return _get_vlm_cache_dir() / f"{file_hash}.{context_hash}.json"


def _read_vlm_cache(file_hash: str, leave_type: str = "", reason_category: str = "") -> Optional[Dict[str, Any]]:
    # Kết quả VLM phụ thuộc loại nghỉ (persona): không dùng cache khi thiếu ngữ cảnh loại nghỉ.
    if not file_hash or not (leave_type or "").strip():
        return None
    key = f"{file_hash}:{leave_type or ''}:{reason_category or ''}"
    if key in _VLM_CACHE_MEM:
        import copy
        return copy.deepcopy(_VLM_CACHE_MEM[key])
    try:
        cache_file = _vlm_cache_path(file_hash, leave_type, reason_category)
        if cache_file.is_file():
            import copy
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            _VLM_CACHE_MEM[key] = data
            return copy.deepcopy(data)
    except Exception:
        pass
    return None


def _write_vlm_cache(file_hash: str, leave_type: str, data: Dict[str, Any], reason_category: str = "") -> None:
    if not file_hash or not data or not (leave_type or "").strip():
        return
    key = f"{file_hash}:{leave_type or ''}:{reason_category or ''}"
    import copy
    _VLM_CACHE_MEM[key] = copy.deepcopy(data)
    try:
        cache_file = _vlm_cache_path(file_hash, leave_type, reason_category)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _try_ollama_extract(
    attachment_path_or_type: Optional[str],
    leave_type: str = '',
    reason_category: Optional[str] = None,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Thực thi VLM thật qua Ollama với persona và JSON schema tương ứng decision tree.

    Returns:
        (normalized_dict, None)                nếu thành công
        (None, error_message_description)      nếu thất bại (có lỗi rõ ràng để caller xử lý)
    """
    path = attachment_path_or_type or ""
    if not path:
        return None, (
            "Không có đường dẫn file chứng từ nào được truyền cho VLM. "
            "Nhân viên cần upload file ảnh/PDF thật và gắn proof_id vào đơn nghỉ."
        )
    if not os.path.isfile(path):
        return None, (
            f"File chứng từ '{path}' không tồn tại trên đĩa. "
            f"Không thể gọi VLM ({VLM_TARGET_MODEL}) khi không có file thật để OCR."
        )

    file_hash = _compute_file_sha256(path)
    if file_hash:
        cached_result = _read_vlm_cache(file_hash, leave_type, reason_category or "")
        if cached_result is not None:
            cached_result["_from_cache"] = True
            return cached_result, None

    # 1. Kiểm tra Ollama service có chạy không
    if not _ollama_reachable():
        return None, (
            f"Không thể kết nối tới Ollama tại {VLM_OLLAMA_BASE}. "
            "Hãy chạy: `ollama serve` hoặc kiểm tra biến môi trường VLM_OLLAMA_BASE."
        )
    # 2. Kiểm tra model VLM có sẵn trong Ollama
    loaded = _ollama_loaded_models()
    if not has_model(loaded, VLM_TARGET_MODEL):
        return None, (
            f"Model VLM '{VLM_TARGET_MODEL}' chưa được pull. "
            f"Chạy: `ollama pull {VLM_TARGET_MODEL}`"
        )
    matched_model = VLM_TARGET_MODEL
    # 3.1. Nếu tên file chứa tiếng Việt / non-ASCII, gán tên mới bằng UUID để hàm mở ảnh không gặp lỗi đường dẫn
    p_obj = Path(path)
    if any(ord(c) > 127 for c in p_obj.name):
        import uuid as _uuid, shutil as _shutil
        target_dir = _get_vlm_cache_dir().parent
        target_dir.mkdir(parents=True, exist_ok=True)
        uuid_path = str(target_dir / f"{_uuid.uuid4().hex}{p_obj.suffix or '.png'}")
        try:
            _shutil.copy2(path, uuid_path)
            path = uuid_path
        except Exception:
            pass

    # 3.5. CỔNG KIỂM SOÁT ĐỘ MỜ TẤT ĐỊNH (Deterministic Blur Gate - ~1ms)
    is_blurry, blur_score = detect_image_blur(path, threshold=50.0)
    if is_blurry:
        persona_role = _resolve_persona_by_proof_type(None)
        return {
            "doc_patient_name": None,
            "doc_diagnosis": None,
            "has_red_stamp": False,
            "has_doctor_signature": False,
            "is_tampered": None,
            "ai_edited": None,
            "days_granted_by_doctor": None,
            "correlation_issues": [
                f"Ảnh chứng từ quá mờ / nhòe nét (độ nét Laplacian: {blur_score} < 50.0), không đạt tiêu chuẩn đọc nội dung."
            ],
            "persona_role_used": persona_role,
            "escalation_reasons": ["DOC_LOW_READABILITY", "DOC_BLURRED_IMAGE"],
            "proof_extra": {
                "proof_type": ProofType.MEDICAL_LEAVE_CERTIFICATE.value,
                "issuer": None,
                "issue_date": None,
                "recommended_from_date": None,
                "recommended_to_date": None,
                "signature_present": False,
                "digital_signature_present": None,
                "document_readability": "UNREADABLE",
                "fields_detected": [],
            },
            "_blur_gate_triggered": True,
        }, None

    # 4. Đọc + tự động resize ảnh (tối đa 1600px) trước khi gửi VLM
    try:
        img = prepare_image_for_vlm(path, max_dim=VLM_MAX_IMAGE_DIM)
    except OSError as e:
        return None, f"Lỗi đọc file '{path}': {type(e).__name__}: {e}"

    # 5. Gọi Ollama /api/generate với persona-specific prompt & schema
    persona_cfg = _resolve_persona_config(leave_type, reason_category)
    _PROOF_TYPE_TAXONOMY = (
        "MAPPING proof_type ĐƯỢC PHÉP CHỌN 1 GIÁ TRỊ DUY NHẤT (enums tiếng Anh, dịch nghĩa tiếng Việt kèm):\n"
        "  NONE                       → không phải chứng từ (ảnh rác, screenshot không liên quan, trống)\n"
        "  MEDICAL_LEAVE_CERTIFICATE  → Giấy khám bệnh / Giấy nghỉ bệnh / Giấy giới thiệu khám BHYT\n"
        "  EMERGENCY_ADMISSION        → Phiếu cấp cứu / Phiếu tiếp nhận vào viện cấp cứu khẩn cấp\n"
        "  HOSPITAL_DISCHARGE         → Giấy xuất viện / Quyết định xuất viện / Phiếu điều trị nội trú\n"
        "  SURGERY_NOTICE             → Giấy chỉ định mổ / Giấy phẫu thuật cấp cứu\n"
        "  LAB_RESULT                 → Phiếu xét nghiệm / Siêu âm / MRI / CT / chẩn đoán hình ảnh\n"
        "  MATERNITY_CERTIFICATE      → Giấy nghỉ thai sản / Giấy chứng nhận mang thai / Giấy sinh con\n"
        "  ACCIDENT_CERTIFICATE       → Giấy xác nhận tai nạn lao động / Bệnh nghề nghiệp (có dấu BHXH/ATLĐ)\n"
        "  MARRIAGE_CERTIFICATE       → Giấy đăng ký kết hôn / Giấy xác nhận đã kết hôn (UBND cấp)\n"
        "  WEDDING_INVITATION         → Giấy mời đám cưới / Giấy báo hỷ sự\n"
        "  DEATH_CERTIFICATE          → Giấy chứng tử (Công an / Trạm y tế / UBND cấp)\n"
        "  FUNERAL_DECISION           → Quyết định tang chế / Giấy xác nhận tang lễ\n"
        "  FAMILY_EVENT_LETTER        → Giấy xác nhận sự kiện gia đình\n"
        "  IDENTITY_CARD              → Căn cước công dân / Hộ chiếu\n"
        "  VISA_OR_TRAVEL_DOC         → Visa / Vé máy bay / Giấy phép công tác nước ngoài\n"
        "  OTHER_ADMINISTRATIVE       → Giấy tờ hành chính khác\n"
        "  OTHER                      → Giấy tờ hợp lệ khác không thuộc các loại trên\n"
    )

    prompt_content = (
        f"{VLM_SYSTEM_PROMPT}\n\n"
        f"{_leave_type_prompt(leave_type, reason_category)}\n\n"
        f"{_PROOF_TYPE_TAXONOMY}\n\n"
        f"SCHEMA JSON THEO PERSONA (trả JSON THUẦN TÚY, KHÔNG markdown, KHÔNG text giải thích, CHỈ 1 object duy nhất):\n"
        f"{{\n{persona_cfg['schema_prompt']}\n}}\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        f"  - Tuân thủ thứ tự DECISION TREE: {persona_cfg['decision_tree']}\n"
        "  - NẾU ẢNH BỊ MỜ KHÔNG ĐỌC RÕ: document_readability BẮT BUỘC là 'UNREADABLE' và mọi trường dữ liệu text/ngày tháng PHẢI là null. TUYỆT ĐỐI KHÔNG TỰ BỊA.\n"
    )

    payload = {
        "model": matched_model,
        "stream": False,
        "format": "json",
        "images": [img],
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_ctx": int(os.getenv("VLM_NUM_CTX", "8192")),
            "num_predict": 512,
            "temperature": 0.0,
        },
        "prompt": prompt_content,
    }

    try:
        body = ollama_generate(payload, timeout=VLM_TIMEOUT_SEC)
    except TimeoutError as e:
        return None, f"VLM timeout sau {VLM_TIMEOUT_SEC}s khi gọi Ollama: {e}. Kiểm tra GPU / size_vram."
    except urlerror.URLError as e:
        return None, f"Lỗi network gọi Ollama /api/generate: {type(e).__name__}: {e}"
    except json.JSONDecodeError as e:
        return None, f"Phản hồi từ Ollama không phải JSON hợp lệ: {e}"
    except Exception as e:
        return None, f"Lỗi không mong muốn khi gọi VLM: {type(e).__name__}: {e}"

    # 6. Parse JSON từ raw response của model
    raw = body.get("response") or "{}"
    if "```" in raw:
        start = raw.find("{"); end = raw.rfind("}")
        if start >= 0 and end > start: raw = raw[start:end + 1]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, (
            f"Model VLM trả về text không parse được thành JSON. "
            f"Lỗi parse: {e}. Phản hồi gốc (trước khi cắt): {(body.get('response') or '')[:300]}"
        )

    raw_readability = str(
        parsed.get("document_readability")
        or parsed.get("readability")
        or "UNKNOWN"
    ).strip().upper()
    if raw_readability in ("ILLEGAL", "ILLEGIBLE", "UNREADABLE", "BLURRY", "BLUR", "MO"):
        doc_readability = "UNREADABLE"
    elif raw_readability in ("PARTIAL", "PARTIALLY"):
        doc_readability = "PARTIAL"
    elif raw_readability == "READABLE":
        doc_readability = "READABLE"
    else:
        doc_readability = "UNKNOWN"

    # Nếu tài liệu UNREADABLE: triệt tiêu mọi trường văn bản/ngày tháng bị ảo giác
    if doc_readability == "UNREADABLE":
        p_name = None
        diag = None
        days_granted = None
        issuer_val = None
        issue_d = None
        rec_fr = None
        rec_to = None
        adm_date = None
        disch_date = None
        is_open_ended = None
        requires_followup = None
        dec_name = None
        sub_name = None
        part_name = None
        event_type_val = None
        wed_date = None
        d_death = None
        fun_date = None
        rel_label = None
        rel_emp = None
        evid_conf = None
        needs_mgr = None
        mat_phase = None
        due_date = None
        bhxh_cd = None
        inj_desc = None
        is_wp_rel = None
        inj_date = None
        doc_purp = None
        val_fr = None
        val_to = None
        fields_detected_val = []
        esc_reasons = list(dict.fromkeys(list(parsed.get("escalation_reasons") or []) + ["DOC_LOW_READABILITY"]))
    else:
        p_name = (
            parsed.get("doc_patient_name")
            or parsed.get("subject_name")
            or parsed.get("patient_name")
            or parsed.get("name")
        )
        if p_name and str(p_name).strip().lower() in ("nguyễn văn a", "nguyen van a"):
            p_name = None

        diag = (
            parsed.get("doc_diagnosis")
            or parsed.get("emergency_diagnosis")
            or parsed.get("injury_description")
            or parsed.get("event_reason")
            or parsed.get("diagnosis")
            or parsed.get("event_description")
        )
        days_granted = (
            parsed.get("days_granted_by_doctor")
            or parsed.get("recommended_leave_days")
            or parsed.get("days_recommended")
        )
        issuer_val = parsed.get("issuer")
        if issuer_val and str(issuer_val).strip().lower() in ("bệnh viện đa khoa a", "benh vien da khoa a", "bệnh viện a"):
            issuer_val = None

        issue_d = parsed.get("issue_date")
        rec_fr = parsed.get("recommended_from_date") or parsed.get("admission_date") or parsed.get("valid_from")
        rec_to = parsed.get("recommended_to_date") or parsed.get("discharge_date") or parsed.get("valid_to")

        # Extended fields parse
        adm_date = parsed.get("admission_date")
        disch_date = parsed.get("discharge_date")
        is_open_ended = bool(parsed["is_open_ended"]) if parsed.get("is_open_ended") is not None else None
        requires_followup = bool(parsed["requires_followup_proof"]) if parsed.get("requires_followup_proof") is not None else None
        dec_name = parsed.get("deceased_name")
        sub_name = parsed.get("subject_name")
        part_name = parsed.get("partner_name")
        event_type_val = parsed.get("event_type")
        wed_date = parsed.get("wedding_date")
        d_death = parsed.get("date_of_death")
        fun_date = parsed.get("funeral_date")
        rel_label = parsed.get("relationship_label")
        rel_emp = parsed.get("relationship_to_employee")
        evid_conf = parsed.get("evidence_confidence")
        needs_mgr = bool(parsed["needs_manager_review"]) if parsed.get("needs_manager_review") is not None else None
        mat_phase = parsed.get("maternity_phase")
        due_date = parsed.get("expected_due_date")
        bhxh_cd = parsed.get("bhxh_code")
        inj_desc = parsed.get("injury_description")
        is_wp_rel = bool(parsed["is_workplace_related"]) if parsed.get("is_workplace_related") is not None else None
        inj_date = parsed.get("injury_date")
        doc_purp = parsed.get("document_purpose")
        val_fr = parsed.get("valid_from")
        val_to = parsed.get("valid_to")

        # Đặc thù EMERGENCY: Tự động phát hiện ca cấp cứu chưa xác định ngày ra viện
        if str(leave_type).upper() == "MEDICAL_EMERGENCY":
            if is_open_ended is None and (rec_to is None or disch_date is None):
                is_open_ended = True
            if requires_followup is None and is_open_ended:
                requires_followup = True

        fields_detected_val = list(parsed.get("fields_detected") or [])
        esc_reasons = list(parsed.get("escalation_reasons") or [])

    normalized: Dict[str, Any] = {
        "doc_patient_name": p_name or sub_name or dec_name,
        "doc_diagnosis": diag,
        "has_red_stamp": (
            parsed.get("has_red_stamp")
            if isinstance(parsed.get("has_red_stamp"), bool)
            else (
                parsed.get("has_hospital_stamp")
                if isinstance(parsed.get("has_hospital_stamp"), bool)
                else (parsed.get("has_stamp") if isinstance(parsed.get("has_stamp"), bool) else None)
            )
        ),
        "has_doctor_signature": (
            parsed.get("has_doctor_signature")
            if isinstance(parsed.get("has_doctor_signature"), bool)
            else (parsed.get("signature_present") if isinstance(parsed.get("signature_present"), bool) else None)
        ),
        "is_tampered": parsed.get("is_tampered"),
        "ai_edited": parsed.get("ai_edited"),
        "days_granted_by_doctor": days_granted,
        "correlation_issues": list(parsed.get("correlation_issues") or []),
        "persona_role_used": persona_cfg["persona"],
        "escalation_reasons": esc_reasons,
        "proof_extra": {
            "proof_type": _normalize_proof_type(
                parsed.get("proof_type")
                or parsed.get("document_type")
                or ProofType.MEDICAL_LEAVE_CERTIFICATE.value
            ).value,
            "issuer": issuer_val,
            "issue_date": issue_d,
            "recommended_from_date": rec_fr,
            "recommended_to_date": rec_to,
            "signature_present": (
                parsed.get("signature_present")
                if isinstance(parsed.get("signature_present"), bool)
                else parsed.get("has_doctor_signature")
            ),
            "digital_signature_present": (
                parsed.get("digital_signature_present")
                if isinstance(parsed.get("digital_signature_present"), bool)
                else (
                    parsed.get("has_digital_signature")
                    if isinstance(parsed.get("has_digital_signature"), bool)
                    else None
                )
            ),
            "document_readability": doc_readability,
            "fields_detected": fields_detected_val,
            "is_open_ended": is_open_ended,
            "requires_followup_proof": requires_followup,
            "admission_date": adm_date,
            "discharge_date": disch_date,
            "doc_diagnosis": diag,
            "emergency_diagnosis": parsed.get("emergency_diagnosis"),
            "days_granted_by_doctor": days_granted,
            "deceased_name": dec_name,
            "subject_name": sub_name,
            "partner_name": part_name,
            "event_type": event_type_val,
            "wedding_date": wed_date,
            "date_of_death": d_death,
            "funeral_date": fun_date,
            "relationship_label": rel_label,
            "relationship_to_employee": rel_emp,
            "evidence_confidence": evid_conf,
            "needs_manager_review": needs_mgr,
            "maternity_phase": mat_phase,
            "expected_due_date": due_date,
            "bhxh_code": bhxh_cd,
            "injury_description": inj_desc,
            "is_workplace_related": is_wp_rel,
            "injury_date": inj_date,
            "has_red_stamp": parsed.get("has_red_stamp"),
            "has_doctor_signature": parsed.get("has_doctor_signature"),
            "has_hospital_stamp": parsed.get("has_hospital_stamp"),
            "has_bhxh_stamp": parsed.get("has_bhxh_stamp"),
            "document_purpose": doc_purp,
            "valid_from": val_fr,
            "valid_to": val_to,
        },
    }

    # In kết quả kiểm định theo decision tree (Decision Tree Audit Log)
    print(f"\n==================== [VLM DECISION TREE AUDIT] ====================")
    print(f"🎭 PERSONA: {persona_cfg['persona']} ({persona_cfg['schema_key']})")
    print(f"🌲 DECISION TREE: {persona_cfg['decision_tree']}")
    audit_extracted = {k: v for k, v in normalized["proof_extra"].items() if v is not None}
    print(f"📋 EXTRACTED DATA: {json.dumps(audit_extracted, ensure_ascii=False, indent=2)}")
    print(f"===================================================================\n")

    if file_hash:
        _write_vlm_cache(file_hash, leave_type, normalized, reason_category or "")
    return normalized, None


def print_persona_schemas() -> None:
    """In chi tiết JSON Schema và Decision Tree cho từng Persona VLM."""
    print("=" * 80)
    print("           DANH SÁCH PERSONA VLM & DECISION TREE & JSON SCHEMA")
    print("=" * 80)
    for key, cfg in PERSONA_CONFIGS.items():
        print(f"\n🔹 [SCHEMA KEY]: {key}")
        print(f"   🎭 Persona: {cfg['persona']}")
        print(f"   🌲 Decision Tree: {cfg['decision_tree']}")
        print(f"   📄 Loại chứng từ hợp lệ: {cfg['allowed_proof_types']}")
        print(f"   📋 JSON Schema:")
        for line in cfg['schema_prompt'].strip().split("\n"):
            print(f"      {line}")
        print("-" * 80)


if __name__ == "__main__":
    print_persona_schemas()

