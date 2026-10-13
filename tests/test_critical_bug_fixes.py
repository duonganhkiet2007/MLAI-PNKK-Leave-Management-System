"""Hồi quy cho các lỗi trong system_critical_bugs_summary.txt (mục 1–5, 8, 11, 12).
Mục 6–7 (so khớp tên, thẩm quyền nghỉ ốm) nằm trong test_decision_tree.py."""
import json
from contextlib import contextmanager

import pytest

from domain import VerifiedProof
from scenarios import BASE
from domain import RequestFacts


def payload(**changes):
    base = {k: v for k, v in BASE.items() if k in RequestFacts.model_fields}
    base.update(handover_person_id=None, handover_person_name=None, no_handover_needed=True)
    return {**base, **changes}


VLM_READY = {
    'inspection_mode': 'OLLAMA_REAL_TEST',
    'document_summary': {'patient_name': 'Nguyễn Văn An', 'issuer': 'BV A', 'issue_date': '2026-10-05',
                         'doctor_recommended_range': {'from': '2026-10-05', 'to': '2026-10-05', 'days': 1}},
    'flags': {'document_readability': 'READABLE', 'has_doctor_signature': True, 'has_red_stamp': True},
    'correlation_analysis': {'score': 0.9, 'issues': []},
}


def add_proof(db, pid, status, version=1, vlm=None, owner='E'):
    c = db.get_db_connection()
    c.execute(
        '''INSERT INTO proof_documents(id,employee_id,storage_name,original_name,mime_type,size_bytes,proof_type,
                                       facts_json,created_at,inspection_status,inspection_version,vlm_analysis_json)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
        (pid, owner, f'{pid}.png', f'{pid}.png', 'image/png', 10, 'MEDICAL_LEAVE_CERTIFICATE',
         VerifiedProof(proof_type='MEDICAL_LEAVE_CERTIFICATE').model_dump_json(), '2026-10-01T08:00:00',
         status, version, json.dumps(vlm) if vlm else None))
    c.commit(); c.close()


def add_job(db, job_id, pid, status='PROCESSING', version=1, retry=0, max_retries=2):
    c = db.get_db_connection()
    c.execute('''INSERT INTO proof_inspection_jobs(id,proof_id,employee_id,status,version,retry_count,max_retries,created_at)
                 VALUES(?,?,?,?,?,?,?,?)''', (job_id, pid, 'E', status, version, retry, max_retries, '2026-10-01T08:00:00'))
    c.commit(); c.close()
    return {'id': job_id, 'proof_id': pid, 'version': version, 'retry_count': retry, 'max_retries': max_retries}


def row(db, sql, *args):
    c = db.get_db_connection()
    try:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


# --- 1. Lost wake-up: worker xong giữa lần đọc trạng thái chứng từ và lúc lưu đơn --------------------
def test_submit_does_not_strand_request_when_proof_finishes_mid_submit(isolated_db, service, monkeypatch):
    import storage as st
    add_proof(isolated_db, 'P1', 'PROCESSING')
    real_transaction = st.transaction
    state = {'first': True}

    @contextmanager
    def worker_finishes_first():
        if state['first']:
            state['first'] = False
            c = isolated_db.get_db_connection()
            c.execute("UPDATE proof_documents SET inspection_status='READY', vlm_analysis_json=? WHERE id='P1'",
                      (json.dumps(VLM_READY),))
            c.commit(); c.close()
        with real_transaction() as conn:
            yield conn

    monkeypatch.setattr(st, 'transaction', worker_finishes_first)
    r = service.process_new_request(employee_id='E', structured_data=payload(
        leave_type='SICK_MEDICAL', from_date='2026-10-05', to_date='2026-10-05', proof_id='P1'))
    assert r['status'] != 'PROCESSING'
    assert row(isolated_db, 'SELECT status FROM leave_requests WHERE id=?', r['id'])['status'] != 'PROCESSING'


# --- 2. Job lỗi cũ không được ghi đè trạng thái mới ---------------------------------------------------
def test_stale_failure_does_not_overwrite_ready_proof(isolated_db):
    from services.inspection_service import ProofInspectionService
    add_proof(isolated_db, 'P2', 'READY', vlm=VLM_READY)
    job = add_job(isolated_db, 'J2', 'P2', retry=2, max_retries=2)
    ProofInspectionService()._apply_inspection_failure(job, 'boom')
    assert row(isolated_db, 'SELECT inspection_status FROM proof_documents WHERE id=?', 'P2')['inspection_status'] == 'READY'
    assert row(isolated_db, 'SELECT status FROM proof_inspection_jobs WHERE id=?', 'J2')['status'] == 'SUPERSEDED'


def test_failure_of_old_version_is_discarded(isolated_db):
    from services.inspection_service import ProofInspectionService
    add_proof(isolated_db, 'P3', 'PENDING', version=2)
    job = add_job(isolated_db, 'J3', 'P3', version=1, retry=2, max_retries=2)
    ProofInspectionService()._apply_inspection_failure(job, 'boom')
    assert row(isolated_db, 'SELECT inspection_status FROM proof_documents WHERE id=?', 'P3')['inspection_status'] == 'PENDING'


# --- 3. Job version cũ phải được khép lại, không treo PROCESSING ---------------------------------------
def test_stale_success_settles_job(isolated_db):
    from services.inspection_service import ProofInspectionService
    add_proof(isolated_db, 'P4', 'PROCESSING', version=2)
    add_job(isolated_db, 'J4', 'P4', version=1)
    ProofInspectionService()._apply_inspection_success('P4', dict(VLM_READY), job_id='J4', job_version=1)
    assert row(isolated_db, 'SELECT status FROM proof_inspection_jobs WHERE id=?', 'J4')['status'] == 'SUPERSEDED'
    assert row(isolated_db, 'SELECT inspection_status FROM proof_documents WHERE id=?', 'P4')['inspection_status'] == 'PROCESSING'


# --- 4. Khởi động lại phải đánh thức đơn bị bỏ dở -------------------------------------------------------
def test_restart_recovery_resumes_and_requeues_stranded_requests(isolated_db):
    from services.inspection_service import ProofInspectionService
    add_proof(isolated_db, 'P5', 'READY', vlm=VLM_READY)      # chứng từ xong nhưng đơn lỡ tín hiệu đánh thức
    add_proof(isolated_db, 'P6', 'PENDING')                    # chứng từ chưa xong và không còn job nào
    c = isolated_db.get_db_connection()
    for rid, pid in (('R5', 'P5'), ('R6', 'P6')):
        c.execute("INSERT INTO leave_requests(id,employee_id,employee_name,department,leave_type,decision,status,proof_id,facts_json,submitted_at,updated_at,revision) "
                  "VALUES(?,?,?,?,'SICK_MEDICAL','PROCESSING',?,?,?,?,?,1)", (rid, 'E', 'Nguyễn Văn An', 'Engineering', 'PROCESSING', pid,
                                                   json.dumps({'leave_type': 'SICK_MEDICAL'}), '2026-10-01T08:00:00', '2026-10-01T08:00:00'))
    c.commit(); c.close()

    resumed = []

    class FakeOrchestrator:
        def resume_pending_request(self, rid):
            resumed.append(rid)

    svc = ProofInspectionService()
    svc.set_orchestrator(FakeOrchestrator())
    svc.recover_interrupted_jobs()
    assert resumed == ['R5']
    assert row(isolated_db, "SELECT COUNT(*) n FROM proof_inspection_jobs WHERE proof_id='P6' AND status='PENDING'")['n'] == 1


# --- 5. Ý kiến tự do mơ hồ không được tự suy ra là DUYỆT --------------------------------------------------
@pytest.mark.parametrize('text', ['Để tôi xem lại sau', 'Chưa duyệt được', 'Cần họp lại', ''])
def test_ambiguous_free_text_is_not_approval(service, text):
    r = service.process_new_request(employee_id='E', structured_data=payload(to_date='2026-10-07'))
    assert r['status'] == 'PENDING_ESCALATION'
    with pytest.raises(ValueError):
        service.process_human_decision(r['id'], text, approver_id='M')


def test_explicit_free_text_approval_still_works(service):
    r = service.process_new_request(employee_id='E', structured_data=payload(to_date='2026-10-07'))
    out = service.process_human_decision(r['id'], 'Đồng ý, duyệt đơn', approver_id='M')
    assert out['status'] in ('COMPLETED', 'PENDING_HANDOVER')


# --- 8. attachment_type giả lập không được tạo chứng từ VERIFIED qua API thật ----------------------------
def test_api_ignores_simulated_attachment_outside_tests(client, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    r = client.post('/api/leave/request', headers={'X-Actor-ID': 'E'},
                    json=payload(leave_type='SICK_MEDICAL', to_date='2026-10-05', attachment_type='clean_hospital_discharge'))
    assert r.status_code == 200, r.text
    data = r.json()['data']
    assert data['decision'] != 'AUTO_APPROVE'
    assert data['error_code'] == 'PROOF_MISSING'


# --- 11. Không lộ lỗi nội bộ ra client ------------------------------------------------------------------
def test_internal_errors_are_sanitized():
    import storage as st
    out = st.sanitize_public({
        'vlm_error': 'VLM_EXCEPTION: ConnectionError: HTTPConnectionPool(host=localhost, port=11434)',
        'inspection_mode': 'OLLAMA_REAL_QWEN25_VL',
        'correlation_analysis': {'issues': ['Traceback (most recent call last): File "/workingspace_aiclub/x.py"', 'Chẩn đoán chưa khớp']},
    })
    assert out['vlm_error'] == st.PUBLIC_VLM_ERROR
    assert out['inspection_mode'] == 'OLLAMA_REAL_QWEN25_VL'
    assert out['correlation_analysis']['issues'] == [st.PUBLIC_VLM_ERROR, 'Chẩn đoán chưa khớp']


# --- 12. Không dùng cache VLM khi thiếu ngữ cảnh loại nghỉ ------------------------------------------------
def test_vlm_cache_requires_leave_type(tmp_path, monkeypatch):
    monkeypatch.setenv('LEAVE_UPLOAD_DIR', str(tmp_path))
    import vlm_inspector as vi
    vi._write_vlm_cache('deadbeef', '', {'x': 1})
    assert vi._read_vlm_cache('deadbeef', '') is None
    assert not list((tmp_path / 'vlm_cache').glob('deadbeef*'))
