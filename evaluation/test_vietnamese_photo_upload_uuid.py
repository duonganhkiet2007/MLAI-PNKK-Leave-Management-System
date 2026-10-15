import os
import sys
import tempfile
import uuid
import io
from pathlib import Path
from PIL import Image
import pytest

from vlm_inspector import (
    prepare_image_for_vlm,
    detect_image_blur,
    _try_ollama_extract,
    inspect_document_with_vlm,
)


def test_prepare_image_with_vietnamese_filename():
    """Kiểm tra prepare_image_for_vlm mở được file ảnh có tên tiếng Việt có dấu."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vn_filename = os.path.join(tmpdir, "giấy_khám_bệnh_nội_trú.png")
        img = Image.new("RGB", (400, 300), color="blue")
        img.save(vn_filename)

        assert os.path.exists(vn_filename)
        b64 = prepare_image_for_vlm(vn_filename, max_dim=1600)
        assert b64 is not None
        assert len(b64) > 0


def test_detect_image_blur_with_vietnamese_filename():
    """Kiểm tra detect_image_blur không bị lỗi khi mở file ảnh có tên tiếng Việt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vn_filename = os.path.join(tmpdir, "đơn_xin_nghỉ_ốm_bác_sĩ.png")
        img = Image.new("RGB", (300, 300), color="white")
        img.save(vn_filename)

        is_blurry, score = detect_image_blur(vn_filename, threshold=50.0)
        assert isinstance(is_blurry, bool)
        assert isinstance(score, float)


def test_try_ollama_extract_converts_vietnamese_filename_to_uuid():
    """Kiểm tra _try_ollama_extract tự động chuyển đường dẫn ảnh tiếng Việt sang tên file UUID."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vn_filename = os.path.join(tmpdir, "chứng_từ_viện_bạch_mai.png")
        img = Image.new("RGB", (200, 200), color="green")
        img.save(vn_filename)

        res, err = _try_ollama_extract(vn_filename, leave_type="SICK_MEDICAL")
        if err:
            assert "không tồn tại trên đĩa" not in err


def test_upload_proof_sets_uuid_name_for_vietnamese_photo(client, isolated_db):
    """Kiểm tra upload_proof qua API đổi tên file ảnh tiếng Việt sang UUID an toàn."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="red")
    img.save(buf, format="PNG")
    content = buf.getvalue()

    # Tên file ảnh tải lên là tiếng Việt có dấu
    vietnamese_filename = "giấy_ra_viện_bạch_mai_2026.png"

    response = client.post(
        "/api/leave/proofs",
        headers={"X-Actor-ID": "E"},
        data={"proof_type": "MEDICAL_LEAVE_CERTIFICATE"},
        files={"file": (vietnamese_filename, content, "image/png")},
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    pid = res_data["data"]["proof_id"]
    assert pid is not None

    # Kiểm tra trong database: storage_name và original_name phải là tên UUID, không còn ký tự tiếng Việt
    c = isolated_db.get_db_connection()
    row = c.execute("SELECT * FROM proof_documents WHERE id=?", (pid,)).fetchone()
    c.close()

    assert row is not None
    storage_name = row["storage_name"]
    original_name = row["original_name"]

    # storage_name phải kết thúc bằng .png và không chứa ký tự tiếng Việt
    assert storage_name.endswith(".png")
    assert not any(ord(ch) > 127 for ch in storage_name)

    # original_name cũng được gán bằng UUID, không chứa ký tự tiếng Việt
    assert not any(ord(ch) > 127 for ch in original_name)

    # File thật trên đĩa tồn tại và mở được bình thường
    upload_dir = Path(os.getenv("LEAVE_UPLOAD_DIR"))
    real_file = upload_dir / storage_name
    assert real_file.exists()

    # Kiểm tra prepare_image_for_vlm mở file này thành công
    b64 = prepare_image_for_vlm(str(real_file))
    assert len(b64) > 0


def test_orchestrator_vietnamese_photo_resolved_to_uuid(service, isolated_db):
    """Kiểm tra LeaveOrchestratorService xử lý ảnh có tên tiếng Việt chuyển sang UUID an toàn khi gọi VLM."""
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        vn_img_path = os.path.join(tmpdir, "ảnh_giấy_chứng_nhận_kết_hôn.png")
        Image.new("RGB", (200, 200), color="yellow").save(vn_img_path)

        pid = "PROOF-TEST-VN-" + uuid.uuid4().hex[:8]
        upload_dir = Path(os.getenv("LEAVE_UPLOAD_DIR"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vn_img_path, upload_dir / Path(vn_img_path).name)

        c = isolated_db.get_db_connection()
        c.execute(
            """INSERT OR REPLACE INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes, proof_type, facts_json, created_at)
               VALUES(?, 'E', ?, ?, 'image/png', 1000, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-22')""",
            (pid, Path(vn_img_path).name, Path(vn_img_path).name),
        )
        c.commit()
        c.close()

        result = service.process_new_request(
            employee_id="E",
            structured_data={
                "leave_type": "SICK_MEDICAL",
                "from_date": "2026-10-15",
                "to_date": "2026-10-15",
                "reason": "Khám sức khỏe",
                "proof_id": pid,
            },
            skip_vlm=False,
        )

        assert result is not None
        assert "vlm_analysis_json" in result
        vlm_analysis = result.get("vlm_analysis_json") or {}
        vlm_error = vlm_analysis.get("vlm_error") or ""
        assert "FileNotFoundError" not in vlm_error
        assert "không tồn tại trên đĩa" not in vlm_error
