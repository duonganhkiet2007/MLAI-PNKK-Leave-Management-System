import os
from pathlib import Path
import pytest
from benchmarks.datasets.proofs import document
from benchmarks.tests.test_reliability import annual,add_proof

def test_other_employee_cannot_download_or_poll_proof(bench_db,bench_client):
    pid=add_proof(bench_db)
    for suffix in ('','/status'):
        r=bench_client.get('/api/leave/proofs/'+pid+suffix,headers={'X-Actor-ID':'BENCH-OTHER'})
        assert r.status_code==403

def test_cross_department_manager_cannot_poll_unrelated_proof(bench_db,bench_client):
    pid=add_proof(bench_db);c=bench_db.get_db_connection()
    c.execute("UPDATE actor_roles SET department_scope='OTHER-TEAM' WHERE employee_id='BENCH-M'");c.commit();c.close()
    assert bench_client.get('/api/leave/proofs/'+pid+'/status',headers={'X-Actor-ID':'BENCH-M'}).status_code==403

def test_unauthorized_request_and_approval(bench_db,bench_service,bench_client):
    req=bench_service.process_new_request(employee_id='BENCH-000',structured_data=annual(to_date='2026-09-16',no_handover_needed=True))
    h={'X-Actor-ID':'BENCH-OTHER'}
    assert bench_client.get('/api/leave/'+req['id'],headers=h).status_code==403
    assert bench_client.post('/api/leave/'+req['id']+'/human-decision',headers=h,json={'action_type':'APPROVE'}).status_code==403

def test_self_approval_and_non_hr_verification(bench_db,bench_service,bench_client):
    req=bench_service.process_new_request(employee_id='BENCH-000',structured_data=annual(to_date='2026-09-16',no_handover_needed=True))
    assert bench_client.post('/api/leave/'+req['id']+'/human-decision',headers={'X-Actor-ID':'BENCH-000'},json={'action_type':'APPROVE'}).status_code==403
    pid=add_proof(bench_db)
    r=bench_client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'BENCH-M'},json={'proof_verification_status':'VERIFIED','verification_notes':'synthetic'})
    assert r.status_code==403

@pytest.mark.parametrize('content,mime,expected',[(b'#!/bin/sh\necho test','image/png',415),(b'%PDF-'+b'x'*(10*1024*1024),'application/pdf',413)],ids=['unsafe-file-type','oversized-upload'])
def test_unsafe_and_oversized_uploads(bench_client,content,mime,expected):
    assert bench_client.post('/api/leave/proofs',headers={'X-Actor-ID':'BENCH-000'},files={'file':('test.png',content,mime)}).status_code==expected

def test_path_traversal_stays_inside_upload_directory(bench_client,bench_db):
    r=bench_client.post('/api/leave/proofs',headers={'X-Actor-ID':'BENCH-000'},files={'file':('../../escape.png',document(),'image/png')})
    assert r.status_code==200
    c=bench_db.get_db_connection();row=c.execute('SELECT storage_name FROM proof_documents WHERE id=?',(r.json()['data']['proof_id'],)).fetchone();c.close()
    uploads=Path(os.environ['LEAVE_UPLOAD_DIR']).resolve();p=(uploads/row['storage_name']).resolve()
    assert p.parent==uploads and p.is_file()
    assert not (uploads.parent/'escape.png').exists()

def test_api_auth_errors_do_not_echo_token(bench_client):
    sentinel='SYNTHETIC-SECRET-DO-NOT-ECHO'
    r=bench_client.get('/api/leave/requests',headers={'Authorization':'Bearer '+sentinel})
    assert r.status_code==401 and sentinel not in r.text

def test_failed_inspection_logs_do_not_expose_document_text(bench_db,monkeypatch,caplog):
    import services.inspection_service as module
    from benchmarks.tests.test_reliability import add_proof
    sentinel='SYNTHETIC-SENSITIVE-DOCUMENT-CONTENT'
    svc=module.ProofInspectionService();pid=add_proof(bench_db);svc.enqueue_proof_inspection(pid,'BENCH-000');job=svc._claim_next_job()
    def fail(**kw):raise ValueError('Invalid model JSON: '+sentinel)
    monkeypatch.setattr(module,'inspect_document_with_vlm',fail)
    svc._process_single_job(job)
    assert sentinel not in caplog.text,'Raw model exceptions can contain sensitive document content'

@pytest.mark.skip(reason='Prompt injection requires real VLM; synthetic injection documents are evaluated by --live-vlm, never claimed passed by a mock')
def test_real_document_prompt_injection():pass
