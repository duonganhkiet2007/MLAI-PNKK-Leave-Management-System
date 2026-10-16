"""VLM có lúc trả ngày đúng dạng in trên giấy (23/10/2026) thay vì YYYY-MM-DD: khoảng nghỉ không được bị rơi."""
from datetime import date

import vlm_inspector as vi


def test_to_iso_date_accepts_printed_formats():
    assert vi._to_iso_date("23/10/2026") == "2026-10-23"
    assert vi._to_iso_date("ngày 05 tháng 11 năm 2026") == "2026-11-05"
    assert vi._to_iso_date("2026-11-05") == "2026-11-05"
    assert vi._to_iso_date("Bốn tuần sau") == "Bốn tuần sau"
    assert vi._to_iso_date(None) is None


def test_leave_range_trusted_only_when_matching_doctor_days():
    # Khớp số ngày bác sĩ cho -> giữ nguyên
    assert vi._trusted_leave_range("2026-10-23", "2026-10-23", 1)[:2] == ("2026-10-23", "2026-10-23")
    assert vi._trusted_leave_range("2026-10-26", "2026-10-28", 3)[:2] == ("2026-10-26", "2026-10-28")
    # Một ngày đơn lẻ ("kể từ ngày 25/10", giờ nhập viện) không kèm số ngày -> bỏ, kèm ghi chú
    fr, to, note = vi._trusted_leave_range("2026-10-25", "2026-10-25", None)
    assert (fr, to) == (None, None) and note
    # Lệch số ngày bác sĩ cho -> bỏ
    fr, to, note = vi._trusted_leave_range("2026-10-25", "2026-10-25", 7)
    assert (fr, to) == (None, None) and "7" in note
    # Khoảng nhiều ngày ghi rõ nhưng không có số ngày -> vẫn giữ
    assert vi._trusted_leave_range("2026-10-26", "2026-10-28", None)[:2] == ("2026-10-26", "2026-10-28")


def test_real_reading_keeps_ddmmyyyy_leave_range():
    profile = {
        "inspection_mode": "OLLAMA_REAL_QWEN25_VL_3B",
        "doc_patient_name": "TRAN QUOC HUNG",
        "proof_extra": {
            "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
            "recommended_from_date": "23/10/2026",
            "recommended_to_date": "23/10/2026",
            "issue_date": "2026-10-23",
            "document_readability": "READABLE",
        },
    }
    proof = vi._build_proof_extraction(profile, "SICK_MEDICAL", None, date(2026, 10, 23), date(2026, 10, 23), 1)
    assert proof.recommended_from_date == date(2026, 10, 23)
    assert proof.recommended_to_date == date(2026, 10, 23)
