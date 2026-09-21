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
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

_kiet = Path(__file__).resolve().parents[1] / "LLM-KIET"
if str(_kiet) not in sys.path:
    sys.path.insert(0, str(_kiet))

from domain import ProofExtraction, ProofType
from ai_stack import (
    OLLAMA_BASE as VLM_OLLAMA_BASE,
    VLM_TARGET_MODEL,
    VLM_TIMEOUT_SEC,
    OLLAMA_KEEP_ALIVE,
    has_model,
    ollama_generate,
    ollama_tags,
)
VLM_FORCE_MOCK = os.getenv("VLM_FORCE_MOCK", "0").strip().casefold() in ("1", "true", "yes", "on")
VLM_MOCK_FALLBACK_ALLOWED = os.getenv("VLM_ALLOW_MOCK_FALLBACK", "0").strip().casefold() in ("1", "true", "yes", "on")

VLM_LEAVE_TYPE_PROFILES = {
    "SICK_MEDICAL": {
        "persona": "Bác sĩ kiểm định hồ sơ y tế",
        "json_variant": "medical_certificate",
        "decision_tree": "patient_name -> medical_dates -> issuer -> signature -> integrity",
        "required": "patient_name, diagnosis, issue_date, recommended_from_date, recommended_to_date, issuer",
    },
    "MEDICAL_EMERGENCY": {
        "persona": "Điều phối viên hồ sơ cấp cứu",
        "json_variant": "emergency_record",
        "decision_tree": "patient_name -> emergency_or_hospital_evidence -> issuer -> integrity",
        "required": "patient_name, diagnosis_or_emergency_evidence, issuer, issue_date",
    },
    "SPECIAL_PAID": {
        "persona": "Chuyên viên xác minh sự kiện gia đình",
        "json_variant": "family_event",
        "decision_tree": "event_type -> related_person -> event_date -> issuer -> integrity",
        "required": "subject_name, event_reason, recommended_from_date, issuer, issue_date",
    },
    "STATUTORY_UNPAID": {
        "persona": "Chuyên viên xác minh quan hệ thân nhân theo luật",
        "json_variant": "statutory_relationship",
        "decision_tree": "event_type -> relationship -> evidence -> confidence -> manager_if_unclear",
        "required": "subject_name, relationship, event_reason, issue_date, issuer",
    },
    "MATERNITY": {
        "persona": "Chuyên viên hồ sơ thai sản BHXH",
        "json_variant": "maternity_record",
        "decision_tree": "maternity_phase -> mother_or_child -> dates -> issuer -> integrity",
        "required": "subject_name, maternity_phase, recommended_from_date, recommended_to_date, issuer",
    },
    "WORK_ACCIDENT": {
        "persona": "Chuyên viên hồ sơ tai nạn lao động",
        "json_variant": "work_accident_record",
        "decision_tree": "injury_event -> workplace_or_commute -> dates -> issuer -> integrity",
        "required": "subject_name, injury_event, issue_date, issuer",
    },
}

VLM_SYSTEM_PROMPT = """Bạn là chuyên gia kiểm định chứng từ nghỉ phép Nhân sự Việt Nam (VLM-Officer).
Nhiệm vụ: đọc ảnh CHỨNG TỪ đính kèm của đơn nghỉ phép và trả về JSON THUẦN TÚY theo schema đã định nghĩa.

LOẠI CHỨNG TỪ CÓ THỂ GẶP (PHẢI NHẬN DIỆN ĐÚNG proof_type):
  • Giấy giới thiệu khám bệnh / Giấy khám bệnh BHYT (phòng khám, bệnh viện tư, công lập, đa khoa, chuyên khoa)
  • Giấy hẹn tái khám / Phiếu kết quả xét nghiệm / Chẩn đoán hình ảnh
  • Giấy xuất viện / Quyết định xuất viện / Phiếu điều trị nội trú
  • Giấy nghỉ thai sản / Giấy chứng nhận mang thai
  • Giấy xác nhận tai nạn lao động / Bệnh nghề nghiệp (BHXH / Ủy ban ATLĐ)
  • Giấy đăng ký kết hôn / Giấy mời đám cưới / Giấy báo hỷ sự
  • Giấy chứng tử / Giấy báo tử / Giấy xác nhận tang lễ / Quả quyết định tang chế
  • Giấy xác nhận sự kiện gia đình (kỷ niệm 50 năm ngày cưới, lễ 1 ngày, bữa tiệc...)
  • Căn cước công dân (CCCD) / Chứng minh nhân dân (CMND) / Hộ chiếu
  • Giấy phép công tác nước ngoài / Visa / Máy bay đi du lịch
  • Ảnh chụp hợp đồng mua bán / Giấy tờ hành chính khác liên quan trực tiếp đến lý do nghỉ

QUY TẮC BẮT BUỘC:
  1. Chỉ ghi những gì THẤY được trên hình.  Không suy diễn, không đoán, không trùng lặp thông tin không có.
  2. patient_name (nếu có - với các loại giấy có tên người thụ hưởng) phải nguyên văn như trên giấy, không sửa lỗi chính tả.
  3. signature_present = chỉ True nếu thấy CHỮ KÝ CỦA NGƯỜI CÓ THẨM QUYỀN CẤP (bác sĩ, trưởng công an, chủ tịch UBND, cô dâu chú rể, người ký giấy chứng tử...).
     signature_present = False nếu ảnh KHÔNG có chữ ký nào ĐƯỢC NHẬN DIỆN RÕ NÉT, dù người ký thật nhưng mờ / cắt xén.
  4. has_red_stamp = chỉ True nếu thấy DẤU MỘC ĐỎ HÌNH TRÒN / HÌNH VUÔNG CÓ TÊN CƠ QUAN / ĐƠN VỊ / CHỨC DANH rõ nét (dấu đỏ của BHXH, bệnh viện, UBND, công ty, phòng khám...).
  5. document_readability:
       - READABLE    = ảnh đủ sáng, đầy đủ 4 góc, text + dấu + chữ ký đọc rõ
       - PARTIAL     = ảnh hơi mờ / 1 góc bị cắt nhưng đọc được thông tin chính (tên, ngày, chẩn đoán...)
       - ILLEGAL     = ảnh quá mờ, che khuất phần lớn, hoặc chữ/dấu/chữ ký KHÔNG THỂ xác minh
  6. issuer = tên CƠ QUAN / ĐƠN VỊ / BỆNH VIỆN / PHÒNG KHÁM / CÔNG TY / NƠI CẤP ra giấy tờ (đọc nguyên văn trên dấu đỏ / tiêu đề).
  7. issue_date = NGÀY, THÁNG, NĂM giấy tờ được ký / cấp (YYYY-MM-DD).
  8. recommended_from_date / recommended_to_date:
       - Với giấy bệnh: KHOẢNG NGÀY BÁC SĨ CHỈ ĐỊNH NGHỈ
       - Với giấy cưới: NGÀY CƯỚI / NGÀY TỔ CHỨC
       - Với giấy tử tang: NGÀY TANG LỄ / NGÀY LỄ TƯỞNG NIỆM
       - Với giấy thai sản: NGÀY DỰ SINH / NGÀY NGHỈ SINH SẢN ĐỀ NGHỊ
       - Với CCCD / giấy hành chính: khoảng ngày KHÔNG CÓ → cả 2 trường đều để null
  9. Không được thêm text giải thích trước hay sau JSON.  Chỉ trả DUY NHẤT 1 { ... } object hợp lệ.
 10. ai_edited = True nếu nghi vấn ảnh được chỉnh sửa bởi photoshop / AI (chữ không đều, chồng lấn pixel, text clone, dấu đỏ bị tái tạo...).
 11. is_tampered = True nếu nghi vấn giấy tờ bị SỬA NỘI DUNG SAU KHI KÝ (xóa chữ, sửa ngày tháng, đổi tên, dán chữ lên ảnh...).
"""


def _leave_type_prompt(leave_type: str) -> str:
    profile = VLM_LEAVE_TYPE_PROFILES.get(leave_type, {"persona": "Chuyên viên đối soát chứng từ hành chính", "json_variant": "general_leave_proof", "decision_tree": "proof_type -> subject -> dates -> issuer -> integrity", "required": "subject_name, event_reason, issue_date, issuer"})
    return (f"LOẠI NGHỈ: {leave_type}. Đóng vai {profile['persona']}. "
            f"Biến thể JSON: {profile['json_variant']}. Trường bắt buộc ưu tiên: {profile['required']}. "
            f"Thứ tự kiểm tra: {profile['decision_tree']}. "
            "Nếu không đọc rõ quan hệ hoặc trường bắt buộc, ghi null/uncertain; không tự suy diễn.")


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
) -> tuple[float, list[str], Optional[int]]:
    """Deterministic correlation scoring between employee claim + VLM findings."""
    score = 0.60
    issues: list[str] = []

    # diagnosis matches free text reason?
    if reason and diagnosis:
        r, d = reason.casefold(), diagnosis.casefold()
        overlap = sum(1 for kw in ("cúm", "sốt", "đau", "ho", "khó thở", "viêm", "phổi",
                                    "nhiễm", "xuất viện", "ngộ độc", "gãy", "trật",
                                    "hô hấp", "cảm", "sổ mũi", "nghẹt mũi", "họng",
                                    "đau đầu", "mệt mỏi", "amidan", "đơn thuốc", "nằm viện")
                      if kw in r and kw in d)
        if overlap == 0:
            score -= 0.20
            issues.append("Chẩn đoán trên giấy (diagnosis) không trùng khớp mô tả lý do nghỉ (reason).")
        else:
            score += min(0.12, 0.04 * overlap)
    elif not diagnosis:
        score -= 0.10
        issues.append("VLM không đọc được chẩn đoán lâm sàng trên chứng từ.")

    # date coverage: requested range must be subset of VLM-recommended range
    if recommended_from and recommended_to and requested_from and requested_to:
        if not (recommended_from <= requested_from and requested_to <= recommended_to):
            score -= 0.25
            issues.append(
                f"Khoảng nghỉ yêu cầu ({requested_from} → {requested_to}) nằm ngoài khoảng "
                f"bác sĩ chỉ định ({recommended_from} → {recommended_to})."
            )
        else:
            score += 0.12
    else:
        score -= 0.10
        issues.append("VLM không đọc được khoảng ngày nghỉ được bác sĩ đề nghị.")

    # doctor-granted days coverage vs requested
    if days_granted_by_doctor is None:
        if requested_workdays and recommended_from and recommended_to:
            try:
                days_granted_by_doctor = (recommended_to - recommended_from).days + 1
                score += 0.03
            except Exception:
                days_granted_by_doctor = None
    if days_granted_by_doctor is not None and requested_workdays:
        if requested_workdays > days_granted_by_doctor:
            score -= 0.18
            issues.append(
                f"Số ngày nghỉ yêu cầu ({requested_workdays} ngày) VƯỢT quá số ngày bác sĩ cho "
                f"({days_granted_by_doctor} ngày)."
            )
        else:
            score += 0.08

    score = round(max(0.0, min(1.0, score)), 3)
    return score, issues, days_granted_by_doctor


def _build_proof_extraction(
    profile: Dict[str, Any],
    leave_type: str,
    employee_name: Optional[str],
    from_date: Optional[date],
    to_date: Optional[date],
    workdays: int,
) -> ProofExtraction:
    extra = dict(profile.get("proof_extra") or {})
    pt = extra.pop("proof_type", ProofType.NONE)

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

    is_none = (pt == ProofType.NONE or profile.get("persona_role_used") == "VLM_UNAVAILABLE")
    rec_fr = _as_date(_gf("recommended_from","recommended_from_date","from_date"), None if is_none else from_date)
    rec_to = _as_date(_gf("recommended_to","recommended_to_date","to_date"), None if is_none else to_date)

    patient_name = profile.get("doc_patient_name") or (None if is_none else employee_name)

    sig = _gf("signature_present")
    if sig is None and profile.get("has_doctor_signature") is not None:
        sig = bool(profile.get("has_doctor_signature"))

    p = ProofExtraction(
        proof_type=pt,
        issuer=_gf("issuer"),
        patient_name=patient_name,
        issue_date=_as_date(_gf("issue_date"), None if is_none else issue_day),
        recommended_from_date=rec_fr,
        recommended_to_date=rec_to,
        signature_present=sig,
        digital_signature_present=_gf("digital_signature_present"),
        document_readability=_gf("document_readability") or ("UNKNOWN" if is_none else "READABLE"),
        fields_detected=list(_gf("fields_detected") or []),
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
        real_result, error_detail = _try_ollama_extract(attachment_path_or_type)
        if real_result:
            profile_raw = real_result
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

    # --- correlation score ---
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
    )
    if days_explicit is None and doctor_days_final is not None:
        profile_raw["days_granted_by_doctor"] = doctor_days_final

    merged_issues = list(profile_raw.get("correlation_issues") or []) + list(issues_plus)
    merged_issues = list(dict.fromkeys(merged_issues))

    # ---- build vlm_analysis_json (Manager panel sees this full shape) ----
    vlm_json: Dict[str, Any] = {
        "inspector_persona": profile_raw.get("persona_role_used"),
        "target_model": VLM_TARGET_MODEL,
        "inspection_mode": mode_used,
        "inspected_at": datetime.now().isoformat(timespec="seconds"),
        "vlm_error": vlm_error,
        "document_summary": {
            "patient_name": profile_raw.get("doc_patient_name") or proof_extraction.patient_name,
            "diagnosis": profile_raw.get("doc_diagnosis"),
            "issuer": proof_extraction.issuer,
            "issue_date": proof_extraction.issue_date.isoformat() if proof_extraction.issue_date else None,
            "doctor_recommended_range": {
                "from": dfd.isoformat() if dfd else None,
                "to": dtd.isoformat() if dtd else None,
                "days": profile_raw.get("days_granted_by_doctor"),
            },
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
            "score": score,
            "issues": merged_issues,
            "requested_workdays": workdays,
        },
        "escalation_flags": list(profile_raw.get("escalation_reasons") or []),
        "raw_fields_detected": list(proof_extraction.fields_detected),
    }

    out = VLMInspectionOutput(
        vlm_analysis_json=vlm_json,
        doc_patient_name=(profile_raw.get("doc_patient_name") or proof_extraction.patient_name),
        doc_diagnosis=profile_raw.get("doc_diagnosis"),
        has_red_stamp=profile_raw.get("has_red_stamp"),
        has_doctor_signature=(profile_raw.get("has_doctor_signature")
                              if profile_raw.get("has_doctor_signature") is not None
                              else proof_extraction.signature_present),
        is_tampered=profile_raw.get("is_tampered"),
        ai_edited=profile_raw.get("ai_edited"),
        days_granted_by_doctor=profile_raw.get("days_granted_by_doctor"),
        correlation_score=score,
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


def _try_ollama_extract(attachment_path_or_type: Optional[str], leave_type: str = '') -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Thực thi VLM thật qua Ollama.

    Returns:
        (normalized_dict, None)                nếu thành công
        (None, error_message_description)      nếu thất bại (có lỗi rõ ràng để caller xử lý)
    """
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
    # 3. Kiểm tra đường dẫn file ảnh thật có tồn tại không
    path = attachment_path_or_type or ""
    if not path or not os.path.isfile(path):
        if not path:
            return None, (
                "Không có đường dẫn file chứng từ nào được truyền cho VLM. "
                "Nhân viên cần upload file ảnh/PDF thật và gắn proof_id vào đơn nghỉ."
            )
        return None, (
            f"File chứng từ '{path}' không tồn tại trên đĩa. "
            f"Không thể gọi VLM ({matched_model}) khi không có file thật để OCR."
        )
    # 4. Đọc + encode ảnh (Tối ưu resize ảnh lớn để VLM inference siêu nhanh ~2s)
    import base64
    import io
    img = ""
    try:
        from PIL import Image
        with Image.open(path) as pil_img:
            max_dim = 1280
            w, h = pil_img.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                pil_img = pil_img.resize(new_size, Image.Resampling.LANCZOS)
            if pil_img.mode in ("RGBA", "P"):
                pil_img = pil_img.convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=85)
            img = base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        try:
            with open(path, "rb") as f:
                img = base64.b64encode(f.read()).decode("ascii")
        except OSError as e:
            return None, f"Lỗi đọc file '{path}': {type(e).__name__}: {e}"

    # 5. Gọi Ollama /api/generate
    _PROOF_TYPE_TAXONOMY = (
        "MAPPING proof_type ĐƯỢC PHÉP CHỌN 1 GIÁ TRỊ DUY NHẤT (enums tiếng Anh, dịch nghĩa tiếng Việt kèm):\n"
        "  NONE                       → không phải chứng từ (ảnh rác, screenshot không liên quan, trống)\n"
        "  MEDICAL_LEAVE_CERTIFICATE  → Giấy khám bệnh / Giấy nghỉ bệnh / Giấy giới thiệu khám BHYT (thường có dấu đỏ bệnh viện/phòng khám + chữ ký bác sĩ)\n"
        "  HOSPITAL_DISCHARGE         → Giấy xuất viện / Quyết định xuất viện / Phiếu điều trị nội trú\n"
        "  LAB_RESULT                 → Phiếu xét nghiệm / Kết quả siêu âm / MRI / CT / chẩn đoán hình ảnh\n"
        "  MATERNITY_CERTIFICATE      → Giấy nghỉ thai sản / Giấy chứng nhận mang thai / Giấy sinh con\n"
        "  ACCIDENT_CERTIFICATE       → Giấy xác nhận tai nạn lao động / Bệnh nghề nghiệp (có dấu BHXH / Ủy ban ATLĐ)\n"
        "  MARRIAGE_CERTIFICATE       → Giấy đăng ký kết hôn / Giấy xác nhận đã kết hôn (UBND phường / quận)\n"
        "  WEDDING_INVITATION         → Giấy mời đám cưới / Giấy báo hỷ sự\n"
        "  DEATH_CERTIFICATE          → Giấy chứng tử (Công an / Trạm y tế) / Giấy báo tử\n"
        "  FUNERAL_DECISION           → Quyết định tang chế / Giấy xác nhận tang lễ / Giấy báo dự lễ tang\n"
        "  FAMILY_EVENT_LETTER        → Giấy xác nhận sự kiện gia đình (nghỉ đám hỏi, lễ giỗ tổ tiên, kỉ niệm ngày cưới...)\n"
        "  IDENTITY_CARD              → CCCD / CMND cũ / Hộ chiếu (chỉ dùng khi đơn yêu cầu nghỉ thực hiện thủ tục hành chính liên quan đến giấy tờ)\n"
        "  VISA_OR_TRAVEL_DOC         → Visa / Máy bay / Giấy phép công tác nước ngoài (hợp đồng du lịch / bồi dưỡng công tác)\n"
        "  OTHER_ADMINISTRATIVE       → Giấy tờ hành chính khác (hợp đồng mua nhà, quyết định thưởng, giấy phép thi cử...)\n"
    )
    payload = {
        "model": matched_model,
        "stream": False,
        "format": "json",
        "images": [img],
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_predict": 1024,
            "temperature": 0.0,
        },
        "prompt": (
            VLM_SYSTEM_PROMPT + "\n\n" + _leave_type_prompt(leave_type) + "\n\n" +
            _PROOF_TYPE_TAXONOMY +
            "\nSchema keys (trả JSON THUẦN TÚY, KHÔNG text giải thích, KHÔNG markdown, CHỈ 1 object duy nhất):\n"
            "  1. proof_type                       → enum 1 trong 13 giá trị trên, BẮT BUỘC CHỌN, KHÔNG được tùy ý thêm.\n"
            "  2. doc_patient_name / subject_name  → TÊN NGƯỜI LIÊN QUAN TRÊN GIẤY (bệnh nhân, vợ/chồng, người đã mất, người cưới...). Nếu không có → null.\n"
            "  3. doc_diagnosis / event_reason     → Chẩn đoán bệnh (nếu là giấy bệnh) / Lý do sự kiện (nếu không phải bệnh) / Nội dung giấy tờ tóm tắt. Không có → null.\n"
            "  4. has_red_stamp                    → bool. Có thấy dấu đỏ (mộc đỏ tròn / vuông) rõ nét trên giấy không?\n"
            "  5. has_doctor_signature             → bool. Có thấy CHỮ KÝ NGƯỜI CÓ THẨM QUYỀN (bác sĩ / trưởng đơn vị / chủ tịch / người cấp giấy) KHÔNG?\n"
            "  6. signature_present                → bool = has_doctor_signature (2 trường này giống nhau cho loại giấy không có bác sĩ).\n"
            "  7. is_tampered                      → bool / null. Nghi vấn giấy bị sửa nội dung sau khi ký?\n"
            "  8. ai_edited                        → bool / null. Nghi vấn ảnh được chỉnh sửa AI?\n"
            "  9. days_granted_by_doctor           → int / null. SỐ NGÀY NGHỊ được ghi trên giấy (bác sĩ đề nghị, nghỉ thai sản, ngày lễ, ngày tang...). Nếu không có số ngày → null.\n"
            "  10. document_readability            → enum 1 giá trị: READABLE / PARTIAL / ILLEGAL.\n"
            "  11. issuer                          → string / null. Tên cơ quan cấp giấy (Bệnh viện Đa khoa X, UBND phường Y, BHXH, Phòng khám Z...).\n"
            "  12. issue_date                      → string / null. Ngày cấp giấy YYYY-MM-DD.\n"
            "  13. recommended_from_date           → string / null. Ngày bắt đầu nghỉ / ngày sự kiện YYYY-MM-DD.\n"
            "  14. recommended_to_date             → string / null. Ngày kết thúc nghỉ / ngày sự kiện kết thúc YYYY-MM-DD.\n"
            "  15. correlation_issues              → list[string] (mảng có thể rỗng). Các VẤN ĐỀ PHÁT HIỆN trên giấy (vd: tên sai, chữ ký không thấy, dấu đỏ không thấy, ngày tháng cắt xén...). Không có → [].\n"
            "  16. escalation_reasons              → list[string] (mảng có thể rỗng). Các FLAG cần escalate cho người duyệt (vd: DOC_MISSING_RED_STAMP, DOC_SIGNATURE_UNVERIFIABLE, DOC_LOW_READABILITY, TAMPER_SUSPECTED, AI_EDITED, WRONG_PROOF_TYPE). Không có → [].\n"
            "  17. digital_signature_present       → bool / null. Giấy có chữ ký số (PKI, CA, hình ảnh chữ ký số có khóa công khai) không? Nếu không rõ → null.\n"
            "  18. fields_detected                 → list[string] các trường dữ liệu ĐƯỢC ĐỌC THÀNH CÔNG trên giấy (vd: ['patient_name','diagnosis','issue_date','red_stamp','signature']...).\n"
        ),
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
    normalized: Dict[str, Any] = {
        "doc_patient_name": (
            parsed.get("doc_patient_name")
            or parsed.get("subject_name")
            or parsed.get("patient_name")
            or parsed.get("name")
        ),
        "doc_diagnosis": (
            parsed.get("doc_diagnosis")
            or parsed.get("event_reason")
            or parsed.get("diagnosis")
            or parsed.get("event_description")
        ),
        "has_red_stamp": (
            parsed.get("has_red_stamp")
            if isinstance(parsed.get("has_red_stamp"), bool)
            else (parsed.get("has_stamp") if isinstance(parsed.get("has_stamp"), bool) else None)
        ),
        "has_doctor_signature": (
            parsed.get("has_doctor_signature")
            if isinstance(parsed.get("has_doctor_signature"), bool)
            else (parsed.get("signature_present") if isinstance(parsed.get("signature_present"), bool) else None)
        ),
        "is_tampered": parsed.get("is_tampered"),
        "ai_edited": parsed.get("ai_edited"),
        "days_granted_by_doctor": (
            parsed.get("days_granted_by_doctor")
            or parsed.get("recommended_leave_days")
            or parsed.get("days_recommended")
        ),
        "correlation_issues": list(parsed.get("correlation_issues") or []),
        "persona_role_used": _resolve_persona_by_proof_type(
            parsed.get("proof_type") or parsed.get("document_type")
        ),
        "escalation_reasons": list(parsed.get("escalation_reasons") or []),
        "proof_extra": {
            "proof_type": (
                parsed.get("proof_type")
                or parsed.get("document_type")
                or ProofType.MEDICAL_LEAVE_CERTIFICATE.value
            ),
            "issuer": parsed.get("issuer"),
            "issue_date": parsed.get("issue_date"),
            "recommended_from_date": parsed.get("recommended_from_date"),
            "recommended_to_date": parsed.get("recommended_to_date"),
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
            "document_readability": (
                parsed.get("document_readability")
                or parsed.get("readability")
                or "UNKNOWN"
            ),
            "fields_detected": list(parsed.get("fields_detected") or []),
        },
    }
    return normalized, None
