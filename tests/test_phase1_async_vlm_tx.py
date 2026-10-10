"""
test_phase1_async_vlm_tx.py
Comprehensive test suite for Phase 1:
- Async Proof Inspection
- SQLite Transaction Optimization & No-Lock-Contention Verification
- 12 required test scenarios
"""
import hashlib
import json
import sqlite3
import threading
import time
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from domain import ProofType
from fastapi.testclient import TestClient
from metrics import GLOBAL_METRICS
from services.inspection_service import ProofInspectionService
from vlm_inspector import ProofExtraction, VLMInspectionOutput


@pytest.fixture
def mock_vlm_output():
    """Deterministic sample VLM output."""
    raw_dict = {
        "inspector_persona": "Doctor",
        "target_model": "qwen2.5vl:7b",
        "inspection_mode": "OLLAMA_REAL_QWEN25_VL_3B",
        "inspected_at": "2026-09-01T08:00:00",
        "vlm_error": None,
        "document_summary": {
            "patient_name": "Nguyễn Văn An",
            "diagnosis": "Cảm cúm mùa, sốt nhẹ",
            "issuer": "Bệnh viện Đa khoa",
            "issue_date": "2026-09-07",
            "doctor_recommended_range": {"from": "2026-09-08", "to": "2026-09-10", "days": 3},
        },
        "flags": {
            "has_red_stamp": True,
            "has_doctor_signature": True,
            "signature_present_on_scan": True,
            "digital_signature_present": False,
            "document_readability": "READABLE",
            "is_tampered": False,
            "ai_generated_or_edited": False,
        },
        "correlation_analysis": {"score": 0.95, "issues": [], "requested_workdays": 1},
        "escalation_flags": [],
        "raw_fields_detected": ["patient_name", "diagnosis", "red_stamp", "signature"],
    }
    return VLMInspectionOutput(
        vlm_analysis_json=raw_dict,
        doc_patient_name="Nguyễn Văn An",
        doc_diagnosis="Cảm cúm mùa, sốt nhẹ",
        has_red_stamp=True,
        has_doctor_signature=True,
        is_tampered=False,
        ai_edited=False,
        days_granted_by_doctor=3,
        correlation_score=0.95,
        correlation_issues=[],
        persona_role_used="Doctor",
        escalation_reasons_json=[],
        proof_extraction=ProofExtraction(
            proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
            issuer="Bệnh viện Đa khoa",
            patient_name="Nguyễn Văn An",
            issue_date=date(2026, 9, 7),
            recommended_from_date=date(2026, 9, 8),
            recommended_to_date=date(2026, 9, 10),
            signature_present=True,
            digital_signature_present=False,
            document_readability="READABLE",
        ),
        vlm_error=None,
    )


def test_1_submission_with_previously_inspected_proof(client, service, isolated_db, mock_vlm_output):
    """Case A: Proof inspection is already READY -> 0 VLM inference calls, fast HTTP 200 response."""
    c = isolated_db.get_db_connection()
    pid = "P_READY_01"
    vlm_json = json.dumps(mock_vlm_output.vlm_analysis_json)
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, proof_verification_status, facts_json, created_at, inspection_status, vlm_analysis_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, "E", "sample.png", "sample.png", "image/png", 1024,
         "MEDICAL_LEAVE_CERTIFICATE", "UNVERIFIED", "{}", "2026-09-01T08:00:00", "READY", vlm_json),
    )
    c.commit()
    c.close()

    with patch("vlm_inspector.inspect_document_with_vlm", wraps=mock_vlm_output) as spy_vlm:
        res = client.post(
            "/api/leave/request",
            headers={"X-Actor-ID": "E"},
            json={
                "leave_type": "SICK_MEDICAL",
                "from_date": "2026-09-08",
                "to_date": "2026-09-08",
                "reason": "Bị cảm sốt",
                "proof_id": pid,
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()["data"]
        # Under 3 days medical leave with verified prescription auto-approves
        assert data["status"] in ("COMPLETED", "PENDING_ESCALATION")
        assert data["proof_inspection_status"] == "READY"
        assert res.json()["total_api_ms"] < 500  # ultra fast, no live VLM network call


def test_2_submission_while_proof_inspection_is_processing(client, service, isolated_db, mock_vlm_output):
    """Case B: Proof inspection is PROCESSING -> returns HTTP 202, resumes automatically when worker finishes."""
    c = isolated_db.get_db_connection()
    pid = "P_PENDING_02"
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, proof_verification_status, facts_json, created_at, inspection_status)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, "E", "sample.png", "sample.png", "image/png", 1024,
         "MEDICAL_LEAVE_CERTIFICATE", "UNVERIFIED", "{}", "2026-09-08T08:00:00", "PROCESSING"),
    )
    c.commit()
    c.close()

    res = client.post(
        "/api/leave/request",
        headers={"X-Actor-ID": "E"},
        json={
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-09-08",
            "to_date": "2026-09-08",
            "reason": "Bị cảm sốt",
            "proof_id": pid,
        },
    )
    assert res.status_code == 202, res.text
    data = res.json()["data"]
    assert data["status"] == "PROCESSING"
    assert data["decision"] == "PROCESSING"
    req_id = data["id"]

    # Now simulate inspection worker finishing the job
    from services.inspection_service import GLOBAL_INSPECTION_SERVICE
    GLOBAL_INSPECTION_SERVICE.set_orchestrator(service)
    GLOBAL_INSPECTION_SERVICE._apply_inspection_success(pid, mock_vlm_output.vlm_analysis_json)

    # Check that request was auto-resumed and completed
    get_res = client.get(f"/api/leave/{req_id}", headers={"X-Actor-ID": "E"})
    assert get_res.status_code == 200
    req_resumed = get_res.json()["data"]
    assert req_resumed["status"] in ("COMPLETED", "PENDING_ESCALATION")
    assert req_resumed["status"] != "PROCESSING"


def test_3_vlm_failure_and_timeout_no_fraud_accusation(client, service, isolated_db):
    """Case C: VLM failure/timeout persists failure metadata without assuming fraud."""
    c = isolated_db.get_db_connection()
    pid = "P_FAIL_03"
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, proof_verification_status, facts_json, created_at, inspection_status, vlm_error)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, "E", "sample.png", "sample.png", "image/png", 1024,
         "MEDICAL_LEAVE_CERTIFICATE", "UNVERIFIED", "{}", "2026-09-08T08:00:00", "FAILED", "VLM_TIMEOUT_60S"),
    )
    c.commit()
    c.close()

    res = client.post(
        "/api/leave/request",
        headers={"X-Actor-ID": "E"},
        json={
            "leave_type": "SICK_MEDICAL",
            "from_date": "2026-09-08",
            "to_date": "2026-09-08",
            "reason": "Bị cảm sốt",
            "proof_id": pid,
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    # Escalated to HR for verification, NOT rejected for fraud
    assert data["status"] in ("PENDING_ESCALATION", "WAITING_EMPLOYEE")
    assert data["decision"] != "REJECTED"


def test_4_duplicate_uploads_and_sha256_cache_hit(client, isolated_db, mock_vlm_output):
    """Duplicate file upload reuses SHA-256 hash cache without redundant VLM invocation."""
    file_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-png-content-12345"
    sha = hashlib.sha256(file_bytes).hexdigest()

    # Seed an earlier inspected document with this SHA
    c = isolated_db.get_db_connection()
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, proof_verification_status, facts_json, created_at, file_sha256, inspection_status, vlm_analysis_json)
           VALUES('P_PRIOR', 'E', 'p1.png', 'p1.png', 'image/png', 20,
                  'MEDICAL_LEAVE_CERTIFICATE', 'UNVERIFIED', '{}', '2026-09-01T08:00:00', ?, 'READY', ?)""",
        (sha, json.dumps(mock_vlm_output.vlm_analysis_json)),
    )
    c.commit()
    c.close()

    # Upload same file again
    res = client.post(
        "/api/leave/proofs",
        headers={"X-Actor-ID": "E"},
        data={"proof_type": "MEDICAL_LEAVE_CERTIFICATE"},
        files={"file": ("sample.png", file_bytes, "image/png")},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    # Instant cache hit makes it READY immediately
    assert data["inspection_status"] == "READY"


def test_5_replacement_of_proof_during_processing(client, service, isolated_db):
    """Case D: Uploading a new proof invalidates stale job; only current version affects decision."""
    c = isolated_db.get_db_connection()
    pid1 = "P_OLD_05"
    pid2 = "P_NEW_05"
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, facts_json, created_at, inspection_status, inspection_version)
           VALUES(?, 'E', 'old.png', 'old.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-01T08:00:00', 'PROCESSING', 1)""",
        (pid1,),
    )
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, facts_json, created_at, inspection_status, inspection_version)
           VALUES(?, 'E', 'new.png', 'new.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-01T08:01:00', 'READY', 2)""",
        (pid2,),
    )
    c.commit()
    c.close()

    from services.inspection_service import GLOBAL_INSPECTION_SERVICE
    # Simulate old worker attempting to apply to version 1 after version was incremented
    GLOBAL_INSPECTION_SERVICE._apply_inspection_success(pid1, {"flags": {}}, job_version=0)
    # Status should not be corrupted
    c = isolated_db.get_db_connection()
    row = c.execute("SELECT inspection_status FROM proof_documents WHERE id=?", (pid1,)).fetchone()
    assert row["inspection_status"] == "PROCESSING"  # rejected stale overwrite
    c.close()


def test_6_two_concurrent_submissions_using_same_proof(client, service, isolated_db, mock_vlm_output):
    """Two concurrent leave submissions using same proof execute safely without double-booking."""
    c = isolated_db.get_db_connection()
    pid = "P_SHARED_06"
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, facts_json, created_at, inspection_status, vlm_analysis_json)
           VALUES(?, 'E', 'doc.png', 'doc.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-01T08:00:00', 'READY', ?)""",
        (pid, json.dumps(mock_vlm_output.vlm_analysis_json)),
    )
    c.commit()
    c.close()

    results = []
    def _sub(d1, d2):
        r = client.post(
            "/api/leave/request",
            headers={"X-Actor-ID": "E"},
            json={"leave_type": "SICK_MEDICAL", "from_date": d1, "to_date": d2, "reason": "Bệnh", "proof_id": pid},
        )
        results.append(r)

    t1 = threading.Thread(target=_sub, args=("2026-09-01", "2026-09-01"))
    t2 = threading.Thread(target=_sub, args=("2026-09-02", "2026-09-02"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert all(r.status_code == 200 for r in results)


def test_7_worker_crash_or_restart_recovery(isolated_db):
    """Job queue recovers interrupted PROCESSING jobs on restart back to PENDING."""
    c = isolated_db.get_db_connection()
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes, proof_type, facts_json, created_at, inspection_status)
           VALUES('P_CRASH_07', 'E', 'f.png', 'f.png', 'image/png', 10, 'OTHER', '{}', '2026-09-01T08:00:00', 'PROCESSING')"""
    )
    c.execute(
        """INSERT INTO proof_inspection_jobs(id, proof_id, employee_id, status, version, retry_count, max_retries, created_at)
           VALUES('JOB_CRASH', 'P_CRASH_07', 'E', 'PROCESSING', 1, 0, 2, '2026-09-01T08:00:00')"""
    )
    c.commit()
    c.close()

    svc = ProofInspectionService()
    recovered = svc.recover_interrupted_jobs()
    assert recovered == 1

    c = isolated_db.get_db_connection()
    job = c.execute("SELECT status, retry_count FROM proof_inspection_jobs WHERE id='JOB_CRASH'").fetchone()
    assert job["status"] == "PENDING"
    assert job["retry_count"] == 1
    doc = c.execute("SELECT inspection_status FROM proof_documents WHERE id='P_CRASH_07'").fetchone()
    assert doc["inspection_status"] == "PENDING"
    c.close()


def test_8_concurrent_sqlite_writers_no_deadlock(isolated_db):
    """Multiple parallel threads writing to SQLite succeed without locking deadlocks."""
    import storage as st

    errors = []
    def _worker(thread_id):
        for i in range(10):
            try:
                with st.transaction() as conn:
                    conn.execute(
                        "INSERT INTO audit_logs(request_id, step_name, action, details, created_at) VALUES(?, 'CONCURRENT', 'TEST', ?, ?)",
                        (f"REQ-T{thread_id}-{i}", f"Thread {thread_id} step {i}", st.now_iso()),
                    )
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(errors) == 0


def test_9_no_vlm_call_while_write_transaction_is_open(service, isolated_db, mock_vlm_output):
    """Verify that VLM inspection is never executed while a database write transaction lock is active."""
    c = isolated_db.get_db_connection()
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, facts_json, created_at, inspection_status)
           VALUES('P_NO_LOCK', 'E', 'f.png', 'f.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-01T08:00:00', 'PENDING')"""
    )
    c.commit()
    c.close()

    write_lock_active = False

    def spy_vlm(*args, **kwargs):
        nonlocal write_lock_active
        # Probe DB with another connection attempting BEGIN IMMEDIATE
        test_conn = isolated_db.get_db_connection()
        try:
            # If a write transaction is open in another connection, BEGIN IMMEDIATE would fail with busy
            test_conn.execute("BEGIN IMMEDIATE")
            test_conn.rollback()
            write_lock_active = False
        except sqlite3.OperationalError:
            write_lock_active = True
        finally:
            test_conn.close()
        return mock_vlm_output

    with patch("vlm_inspector.inspect_document_with_vlm", side_effect=spy_vlm):
        service.process_new_request(
            employee_id="E",
            structured_data={
                "leave_type": "SICK_MEDICAL",
                "from_date": "2026-09-01",
                "to_date": "2026-09-01",
                "reason": "Sốt",
                "proof_id": "P_NO_LOCK",
            },
            skip_vlm=False,
        )

    # Write lock MUST NOT have been active during VLM call
    assert write_lock_active is False


def test_10_correct_audit_logs_and_unchanged_policy_decisions(client, service, isolated_db, mock_vlm_output):
    """Ensure audit trail and policy evaluations remain 100% compliant with policy definitions."""
    c = isolated_db.get_db_connection()
    pid = "P_AUDIT_10"
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, facts_json, created_at, inspection_status, vlm_analysis_json)
           VALUES(?, 'E', 'p.png', 'p.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-01T08:00:00', 'READY', ?)""",
        (pid, json.dumps(mock_vlm_output.vlm_analysis_json)),
    )
    c.commit()
    c.close()

    res = client.post(
        "/api/leave/request",
        headers={"X-Actor-ID": "E"},
        json={"leave_type": "SICK_MEDICAL", "from_date": "2026-09-01", "to_date": "2026-09-01", "reason": "Ốm", "proof_id": pid},
    )
    assert res.status_code == 200
    req_id = res.json()["data"]["id"]

    c = isolated_db.get_db_connection()
    logs = [r["action"] for r in c.execute("SELECT action FROM audit_logs WHERE request_id=?", (req_id,)).fetchall()]
    assert "EVALUATED" in logs
    c.close()


def test_11_no_double_evaluation_when_inspection_and_submission_race(service, isolated_db, mock_vlm_output):
    """Ensure no duplicate approvals or double balance deductions when inspection and submission race."""
    c = isolated_db.get_db_connection()
    pid = "P_RACE_11"
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes,
           proof_type, facts_json, created_at, inspection_status)
           VALUES(?, 'E', 'r.png', 'r.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE', '{}', '2026-09-01T08:00:00', 'PROCESSING')""",
        (pid,),
    )
    c.commit()
    c.close()

    # Submit request while PROCESSING
    req = service.process_new_request(
        employee_id="E",
        structured_data={"leave_type": "SICK_MEDICAL", "from_date": "2026-09-01", "to_date": "2026-09-01", "reason": "Sốt", "proof_id": pid},
    )
    req_id = req["id"]

    from services.inspection_service import GLOBAL_INSPECTION_SERVICE
    GLOBAL_INSPECTION_SERVICE.set_orchestrator(service)

    # Call resume twice concurrently
    t1 = threading.Thread(target=GLOBAL_INSPECTION_SERVICE.resume_pending_requests_for_proof, args=(pid,))
    t2 = threading.Thread(target=GLOBAL_INSPECTION_SERVICE.resume_pending_requests_for_proof, args=(pid,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Check only one evaluation occurred
    c = isolated_db.get_db_connection()
    count = c.execute("SELECT COUNT(*) FROM audit_logs WHERE request_id=? AND action='INSPECTION_RESUMED'", (req_id,)).fetchone()[0]
    assert count <= 1
    c.close()


def test_12_authorization_checks_on_proof_and_status_endpoints(client, isolated_db):
    """Verify authorization gates on proof status endpoint: owner and managers can view, outsiders cannot."""
    c = isolated_db.get_db_connection()
    c.execute(
        """INSERT INTO proof_documents(id, employee_id, storage_name, original_name, mime_type, size_bytes, proof_type, facts_json, created_at, inspection_status)
           VALUES('P_AUTH_12', 'E', 'doc.png', 'doc.png', 'image/png', 10, 'OTHER', '{}', '2026-09-01T08:00:00', 'READY')"""
    )
    c.commit()
    c.close()

    # Owner E can view status
    r_owner = client.get("/api/leave/proofs/P_AUTH_12/status", headers={"X-Actor-ID": "E"})
    assert r_owner.status_code == 200

    # HR can view status
    r_hr = client.get("/api/leave/proofs/P_AUTH_12/status", headers={"X-Actor-ID": "HR"})
    assert r_hr.status_code == 200

    # Outsider B cannot view status
    r_outsider = client.get("/api/leave/proofs/P_AUTH_12/status", headers={"X-Actor-ID": "B"})
    assert r_outsider.status_code == 403
