"""VLM khẳng định có dấu mộc mà OpenCV không thấy con dấu nào: kết luận "có chữ ký" trên cùng ảnh không được dùng."""
import json
from pathlib import Path

import pytest
import vlm_inspector as vi

IMAGE = Path(__file__).resolve().parents[1] / "frontend" / "assets" / "proofs" / "proof_emp011_sick_morning_valid.png"
VLM_ANSWER = {
    "proof_type": "MEDICAL_LEAVE_CERTIFICATE", "doc_patient_name": "HOÀNG KIM YẾN", "doc_diagnosis": "Viêm dạ dày ruột cấp",
    "days_granted_by_doctor": 1, "recommended_from_date": "2026-11-05", "recommended_to_date": "2026-11-05",
    "issue_date": "2026-11-05", "issuer": "Bệnh viện Đa khoa Quốc tế Hà Nội",
    "has_red_stamp": True, "has_doctor_signature": True, "signature_present": True, "document_readability": "READABLE",
}


@pytest.fixture
def fake_vlm(monkeypatch, tmp_path):
    monkeypatch.setenv("LEAVE_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(vi, "_read_vlm_cache", lambda *a, **k: None)
    monkeypatch.setattr(vi, "_write_vlm_cache", lambda *a, **k: None)
    monkeypatch.setattr(vi, "_ollama_reachable", lambda: True)
    monkeypatch.setattr(vi, "_ollama_loaded_models", lambda: [vi.VLM_TARGET_MODEL])
    monkeypatch.setattr(vi, "has_model", lambda *a, **k: True)
    monkeypatch.setattr(vi, "ollama_generate", lambda payload, timeout=None: {"response": json.dumps(VLM_ANSWER)})
    return monkeypatch


def test_signature_claim_dropped_when_vlm_invents_stamp(fake_vlm):
    fake_vlm.setattr(vi, "evidence_red_stamp_cv", lambda path: {"verdict": False, "reason": "không có vòng mộc"})
    normalized, error = vi._try_ollama_extract(str(IMAGE), leave_type="SICK_MEDICAL")
    assert error is None
    assert normalized["has_red_stamp"] is None
    assert normalized["has_doctor_signature"] is None
    assert normalized["proof_extra"]["signature_present"] is None


def test_signature_kept_when_stamp_confirmed(fake_vlm):
    fake_vlm.setattr(vi, "evidence_red_stamp_cv", lambda path: {"verdict": True, "reason": "có vòng mộc"})
    normalized, error = vi._try_ollama_extract(str(IMAGE), leave_type="SICK_MEDICAL")
    assert error is None
    assert normalized["has_red_stamp"] is True
    assert normalized["has_doctor_signature"] is True
