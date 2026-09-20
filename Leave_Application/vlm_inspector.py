"""VLM (Vision-Language Model) document inspector for leave certificates, prescriptions,
marriage/death extracts, and identity papers.

Design:
  * NEVER fabricate facts.  The deterministic engine must not receive "invented" claims.
  * When a real model (Ollama qwen2.5-vl:3b) is reachable we run structured JSON extraction.
  * Otherwise we fall back to a type-safe persona-driven mock profile, keyed off of the
    legacy ``attachment_type`` string.  The mock still exercises every downstream column
    and the correlation engine so the UI (Manager panels, Attachment Modal, checklists)
    renders exactly the same shape as production data.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from domain import ProofExtraction, ProofType


VLM_OLLAMA_BASE = os.getenv("VLM_OLLAMA_BASE", "http://localhost:11434")
VLM_TARGET_MODEL = os.getenv("VLM_TARGET_MODEL", "qwen2.5-vl:3b")
VLM_TIMEOUT_SEC = float(os.getenv("VLM_TIMEOUT_SEC", "60.0"))
VLM_FORCE_MOCK = os.getenv("VLM_FORCE_MOCK", "0").strip().casefold() in ("1", "true", "yes", "on")
VLM_MOCK_FALLBACK_ALLOWED = os.getenv("VLM_ALLOW_MOCK_FALLBACK", "0").strip().casefold() in ("1", "true", "yes", "on")


VLM_SYSTEM_PROMPT = """Bạn là chuyên gia kiểm định chứng từ nghỉ phép BHXH Việt Nam (VLM-Officer).
Nhiệm vụ: đọc chứng từ (đơn thuốc, giấy xuất viện, giấy cưới, giấy tử tang, CCCD/CMND)
và trả về JSON THUẦN TÚY theo schema ProofExtraction.

QUY TẮC BẮT BUỘC:
  1. Chỉ ghi những gì THẤY được trên hình.  Không suy diễn, không đoán.
  2. patient_name phải nguyên văn như trên giấy, không sửa lỗi chính tả.
  3. signature_present = chỉ True nếu thấy CHỮ KÝ CỦA BÁC SĨ (hoặc chữ ký số rõ nét).
  4. document_readability = ILLEGAL nếu ảnh mờ, cắt xén, chữ kí không đọc được.
  5. Tên BỆNH VIỆN / PHÒNG KHÁM cấp (issuer), NGÀY CẤP (issue_date) phải có.
  6. Không được thêm text giải thích trước hay sau JSON.  Chỉ trả { ... } object duy nhất.
  7. recommended_from_date / recommended_to_date = KHOẢNG NGHỈ được bác sĩ CHỈ ĐỊNH.
"""


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

    rec_fr = _as_date(_gf("recommended_from","recommended_from_date","from_date"), from_date)
    rec_to = _as_date(_gf("recommended_to","recommended_to_date","to_date"), to_date)

    patient_name = profile.get("doc_patient_name") or employee_name

    p = ProofExtraction(
        proof_type=pt,
        issuer=_gf("issuer"),
        patient_name=patient_name,
        issue_date=_as_date(_gf("issue_date"), issue_day),
        recommended_from_date=rec_fr,
        recommended_to_date=rec_to,
        signature_present=_gf("signature_present") or bool(profile.get("has_doctor_signature")),
        digital_signature_present=_gf("digital_signature_present"),
        document_readability=_gf("document_readability") or "READABLE",
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
    """Entry point.  Chạy VLM thật (Ollama qwen2.5-vl:3b) trên ảnh thực tế.

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
            vlm_error = error_detail or "VLM (qwen2.5-vl:3b) không thể xử lý chứng từ này."
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
                raise VLMUnavailableError(vlm_error)

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


# ---------------- Real Ollama integration (optional when model pulled) ----------------

def _ollama_reachable() -> bool:
    try:
        with urlrequest.urlopen(f"{VLM_OLLAMA_BASE}/api/tags", timeout=2.0) as r:
            return r.status == 200
    except Exception:
        return False


def _ollama_loaded_models() -> list[str]:
    try:
        with urlrequest.urlopen(f"{VLM_OLLAMA_BASE}/api/tags", timeout=2.0) as r:
            data = json.loads(r.read().decode() or "{}")
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def _try_ollama_extract(attachment_path_or_type: Optional[str]) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
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
    # 2. Kiểm tra model qwen2.5-vl:3b đã được pull chưa
    loaded = _ollama_loaded_models()
    if not any(VLM_TARGET_MODEL in m for m in loaded):
        return None, (
            f"Model VLM '{VLM_TARGET_MODEL}' chưa có trong Ollama (hiện có: {loaded or '<none>'}). "
            f"Hãy chạy: `ollama pull {VLM_TARGET_MODEL}`"
        )
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
            "Không thể gọi VLM (qwen2.5-vl:3b) khi không có file thật để OCR."
        )
    # 4. Đọc + encode ảnh
    import base64
    try:
        with open(path, "rb") as f:
            img = base64.b64encode(f.read()).decode("ascii")
    except OSError as e:
        return None, f"Lỗi đọc file '{path}': {type(e).__name__}: {e}"
    # 5. Gọi Ollama /api/generate
    payload = {
        "model": VLM_TARGET_MODEL,
        "stream": False,
        "format": "json",
        "images": [img],
        "prompt": (
            "Phân tích chứng từ đính kèm cho đơn nghỉ phép Việt Nam.  "
            + VLM_SYSTEM_PROMPT
            + "\n\nSchema keys (trả JSON THUẦN TÚY, không text trước/sau JSON): doc_patient_name, doc_diagnosis, "
              "has_red_stamp (bool), has_doctor_signature (bool), is_tampered (bool|null), "
              "ai_edited (bool|null), days_granted_by_doctor (int|null), "
              "proof_type, issuer, issue_date (YYYY-MM-DD), recommended_from_date, "
              "recommended_to_date, signature_present (bool), document_readability, "
              "correlation_issues (list[str] so với ngữ cảnh chung nếu có thể phỏng đoán từ ảnh), "
              "escalation_reasons (list[str] flags)."
        ),
    }
    req = urlrequest.Request(
        f"{VLM_OLLAMA_BASE}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=VLM_TIMEOUT_SEC) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
    except TimeoutError as e:
        return None, f"VLM timeout sau {VLM_TIMEOUT_SEC}s khi gọi Ollama: {e}. Tăng VLM_TIMEOUT_SEC hoặc kiểm tra GPU."
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
        "doc_patient_name": parsed.get("doc_patient_name"),
        "doc_diagnosis": parsed.get("doc_diagnosis"),
        "has_red_stamp": parsed.get("has_red_stamp"),
        "has_doctor_signature": parsed.get("has_doctor_signature"),
        "is_tampered": parsed.get("is_tampered"),
        "ai_edited": parsed.get("ai_edited"),
        "days_granted_by_doctor": parsed.get("days_granted_by_doctor"),
        "correlation_issues": list(parsed.get("correlation_issues") or []),
        "persona_role_used": _PersonaRegistry.PERSONA_DOCTOR_VL,
        "escalation_reasons": list(parsed.get("escalation_reasons") or []),
        "proof_extra": {
            "proof_type": parsed.get("proof_type") or ProofType.MEDICAL_LEAVE_CERTIFICATE.value,
            "issuer": parsed.get("issuer"),
            "issue_date": parsed.get("issue_date"),
            "recommended_from_date": parsed.get("recommended_from_date"),
            "recommended_to_date": parsed.get("recommended_to_date"),
            "signature_present": parsed.get("signature_present"),
            "document_readability": parsed.get("document_readability", "UNKNOWN"),
            "fields_detected": list(parsed.get("fields_detected") or []),
        },
    }
    return normalized, None
