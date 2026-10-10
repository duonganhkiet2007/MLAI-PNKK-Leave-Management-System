"""Tests for secured employee directory and personal photo endpoints."""
import pytest
from auth import issue_token


def test_verify_employees_requires_authentication(client):
    """GET /api/verify/employees không có thông tin xác thực phải trả về 401."""
    res = client.get("/api/verify/employees")
    assert res.status_code == 401


def test_verify_employees_with_actor_header(client, isolated_db):
    """GET /api/verify/employees với X-Actor-ID trả về 200 và danh sách nhân viên có photo_url."""
    res = client.get("/api/verify/employees", headers={"X-Actor-ID": "E"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["identity_mode"] == "VERIFIED"
    assert data["verified_by"] == "E"
    assert len(data["data"]) > 0
    # Mỗi nhân viên có trường photo_url trỏ tới verifying endpoint
    for emp in data["data"]:
        assert "photo_url" in emp
        assert emp["photo_url"].startswith("/api/verify/employees/")


def test_verify_employees_with_bearer_token(client, isolated_db):
    """GET /api/verify/employees với Authorization: Bearer <token> hợp lệ trả về 200."""
    token = issue_token("E")
    res = client.get("/api/verify/employees", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["verified_by"] == "E"


def test_verify_single_employee_detail(client, isolated_db):
    """GET /api/verify/employees/{id} trả về thông tin chi tiết của nhân sự."""
    # Không có auth -> 401
    assert client.get("/api/verify/employees/E").status_code == 401

    # Có auth -> 200
    res = client.get("/api/verify/employees/E", headers={"X-Actor-ID": "E"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["employee_id"] == "E"
    assert "photo_url" in data["data"]


def test_verify_single_employee_not_found(client, isolated_db):
    """GET /api/verify/employees/EMP999 trả về 404 nếu không tìm thấy."""
    res = client.get("/api/verify/employees/EMP999", headers={"X-Actor-ID": "E"})
    assert res.status_code == 404


def test_verify_photos_endpoint(client, isolated_db):
    """GET /api/verify/photos/{filename} yêu cầu xác thực và trả về ảnh chứng từ."""
    # Không có auth -> 401
    assert client.get("/api/verify/photos/proof_emp004_sick_days_mismatch.png").status_code == 401

    # Có auth -> 200
    res = client.get(
        "/api/verify/photos/proof_emp004_sick_days_mismatch.png",
        headers={"X-Actor-ID": "E"}
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")
    assert len(res.content) > 0


def test_verify_proofs_alias_endpoint(client, isolated_db):
    """GET /api/verify/proofs/{filename} là alias tương thích cho photos."""
    res = client.get(
        "/api/verify/proofs/proof_emp009_wedding_valid.png",
        headers={"X-Actor-ID": "E"}
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/")


def test_verify_photo_not_found(client, isolated_db):
    """GET /api/verify/photos/non_existent.png trả về 404."""
    res = client.get("/api/verify/photos/non_existent.png", headers={"X-Actor-ID": "E"})
    assert res.status_code == 404


def test_meta_employees_requires_auth_and_points_to_canonical(client, isolated_db):
    """GET /api/meta/employees giờ đây cũng được bảo vệ và trỏ về canonical verifying endpoint."""
    # Không có auth -> 401
    assert client.get("/api/meta/employees").status_code == 401

    # Có auth -> 200 với canonical_endpoint
    res = client.get("/api/meta/employees", headers={"X-Actor-ID": "E"})
    assert res.status_code == 200
    data = res.json()
    assert data["canonical_endpoint"] == "/api/verify/employees"


def test_verify_harness_pipeline_remains_operational(client, isolated_db):
    """Đảm bảo pipeline kiểm thử Verify Harness không bị ảnh hưởng."""
    res = client.post("/api/verify/escalation")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["summary"]["passed_cases"] == 5
    assert data["summary"]["overall_status"] == "PASS"
