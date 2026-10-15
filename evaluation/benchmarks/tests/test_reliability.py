import json, threading, sqlite3, time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest

def annual(**patch):return {'leave_type':'ANNUAL','from_date':'2026-09-14','to_date':'2026-09-14',**patch}

def add_proof(db,pid='P',version=1,status='PENDING'):
    import os
    from pathlib import Path
    from evaluation.benchmarks.datasets.proofs import document
    from domain import VerifiedProof
    path=Path(os.environ['LEAVE_UPLOAD_DIR']);path.mkdir(parents=True,exist_ok=True)
    (path/(pid+'.png')).write_bytes(document())
    c=db.get_db_connection()
    c.execute("INSERT INTO proof_documents(id,employee_id,storage_name,original_name,mime_type,size_bytes,proof_type,facts_json,created_at,inspection_status,inspection_version) VALUES(?,'BENCH-000',?,?,'image/png',100,'MEDICAL_LEAVE_CERTIFICATE',?,'2026-09-01T08:00:00+07:00',?,?)",(pid,pid+'.png',pid+'.png',VerifiedProof(proof_type='MEDICAL_LEAVE_CERTIFICATE').model_dump_json(),status,version))
    c.commit();c.close();return pid

def test_concurrent_submissions_and_audit_integrity(bench_db,bench_service):
    with ThreadPoolExecutor(max_workers=20) as pool:
        rows=list(pool.map(lambda i:bench_service.process_new_request(employee_id=f'BENCH-{i:03}',structured_data=annual()),range(20)))
    assert all(r['status']=='COMPLETED' for r in rows)
    c=bench_db.get_db_connection()
    assert c.execute('SELECT count(*) FROM leave_transactions').fetchone()[0]==20
    for r in rows:
        assert c.execute("SELECT count(*) FROM audit_logs WHERE request_id=? AND action='EVALUATED'",(r['id'],)).fetchone()[0]==1
    c.close()

def test_duplicate_submission_no_double_debit(bench_db,bench_service):
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows=list(pool.map(lambda _:bench_service.process_new_request(employee_id='BENCH-000',structured_data=annual()),range(5)))
    assert sum(r['status']=='COMPLETED' for r in rows)==1
    c=bench_db.get_db_connection()
    assert c.execute("SELECT remaining_leave_days FROM employees WHERE employee_id='BENCH-000'").fetchone()[0]==99
    c.close()

def test_transaction_rollback(bench_db):
    import storage as st
    with pytest.raises(RuntimeError):
        with st.transaction() as c:
            c.execute("UPDATE employees SET remaining_leave_days=0 WHERE employee_id='BENCH-000'")
            st.audit(c,'TEST','UNCOMMITTED','synthetic');raise RuntimeError('controlled rollback')
    c=bench_db.get_db_connection()
    assert c.execute("SELECT remaining_leave_days FROM employees WHERE employee_id='BENCH-000'").fetchone()[0]==100
    assert c.execute("SELECT count(*) FROM audit_logs WHERE action='UNCOMMITTED'").fetchone()[0]==0
    c.close()

def test_database_busy_error_is_bounded(bench_db,monkeypatch):
    import storage as st
    original=bench_db.get_db_connection
    def short():
        c=original();c.execute('PRAGMA busy_timeout=30');return c
    c=original();c.execute('BEGIN IMMEDIATE')
    monkeypatch.setattr(bench_db,'get_db_connection',short)
    try:
        with pytest.raises(sqlite3.OperationalError,match='locked'):
            with st.transaction():pass
    finally:c.rollback();c.close()
    with st.transaction() as c:c.execute('SELECT 1')

def test_duplicate_job_deduplication(bench_db):
    from services.inspection_service import ProofInspectionService
    pid=add_proof(bench_db);svc=ProofInspectionService()
    a=svc.enqueue_proof_inspection(pid,'BENCH-000');b=svc.enqueue_proof_inspection(pid,'BENCH-000')
    assert a['job_id']==b['job_id']

def test_duplicate_upload_reuses_ready_content(bench_db,bench_client):
    from evaluation.benchmarks.datasets.proofs import document
    content=document();h={'X-Actor-ID':'BENCH-000'}
    a=bench_client.post('/api/leave/proofs',headers=h,files={'file':('one.png',content,'image/png')}).json()['data']
    c=bench_db.get_db_connection();c.execute("UPDATE proof_documents SET inspection_status='READY',vlm_analysis_json=? WHERE id=?",(json.dumps({'flags':{'document_readability':'READABLE'}}),a['proof_id']));c.commit();c.close()
    b=bench_client.post('/api/leave/proofs',headers=h,files={'file':('two.png',content,'image/png')}).json()['data']
    assert a['proof_id']!=b['proof_id'] and b['inspection_status']=='READY'

@pytest.mark.parametrize('failure',['timeout','invalid_json','ollama_unavailable'])
def test_bounded_retry_and_failed_state(bench_db,monkeypatch,failure):
    import services.inspection_service as module
    svc=module.ProofInspectionService();pid=add_proof(bench_db)
    svc.enqueue_proof_inspection(pid,'BENCH-000')
    def fail(**kw):
        if failure=='timeout':raise TimeoutError('Synthetic timeout')
        if failure=='invalid_json':raise json.JSONDecodeError('Synthetic invalid JSON','x',0)
        raise ConnectionError('Synthetic Ollama unavailable')
    monkeypatch.setattr(module,'inspect_document_with_vlm',fail)
    for _ in range(3):
        job=svc._claim_next_job();assert job is not None;svc._process_single_job(job)
    assert svc._claim_next_job() is None
    c=bench_db.get_db_connection()
    assert c.execute('SELECT inspection_status FROM proof_documents WHERE id=?',(pid,)).fetchone()[0]=='FAILED'
    assert c.execute('SELECT retry_count FROM proof_inspection_jobs').fetchone()[0]==2
    c.close()

def test_interrupted_worker_recovery(bench_db):
    from services.inspection_service import ProofInspectionService
    pid=add_proof(bench_db);svc=ProofInspectionService();svc.enqueue_proof_inspection(pid,'BENCH-000')
    svc._claim_next_job();new_worker=ProofInspectionService()
    assert new_worker.recover_interrupted_jobs()==1
    assert new_worker._claim_next_job()['retry_count']==1

def test_stale_success_cannot_replace_current_proof(bench_db):
    from services.inspection_service import ProofInspectionService
    pid=add_proof(bench_db,version=2)
    ProofInspectionService()._apply_inspection_success(pid,{'flags':{'document_readability':'UNREADABLE'}},job_version=1)
    c=bench_db.get_db_connection();row=c.execute('SELECT inspection_status,document_readability FROM proof_documents WHERE id=?',(pid,)).fetchone()
    assert row[0]=='PENDING';c.close()

def test_stale_failure_cannot_replace_current_proof(bench_db):
    from services.inspection_service import ProofInspectionService
    svc=ProofInspectionService();pid=add_proof(bench_db,version=1)
    svc.enqueue_proof_inspection(pid,'BENCH-000');job=svc._claim_next_job()
    c=bench_db.get_db_connection();c.execute("UPDATE proof_documents SET inspection_version=2,inspection_status='READY' WHERE id=?",(pid,));c.commit();c.close()
    svc._apply_inspection_failure(job,'synthetic stale failure')
    c=bench_db.get_db_connection();status=c.execute('SELECT inspection_status FROM proof_documents WHERE id=?',(pid,)).fetchone()[0];c.close()
    assert status=='READY','Stale failure must not reset replacement evidence'

def test_stale_job_not_left_processing(bench_db):
    from services.inspection_service import ProofInspectionService
    svc=ProofInspectionService();pid=add_proof(bench_db);svc.enqueue_proof_inspection(pid,'BENCH-000');job=svc._claim_next_job()
    c=bench_db.get_db_connection();c.execute('UPDATE proof_documents SET inspection_version=2 WHERE id=?',(pid,));c.commit();c.close()
    svc._apply_inspection_success(pid,{'flags':{}},job_id=job['id'],job_version=1)
    c=bench_db.get_db_connection();status=c.execute('SELECT status FROM proof_inspection_jobs').fetchone()[0];c.close()
    assert status!='PROCESSING','Discarded stale job must reach a settled job state'

def test_cache_distinct_content_and_defensive_copy(bench_db):
    import vlm_inspector as vi
    vi._write_vlm_cache('a'*64,'SICK_MEDICAL',{'marker':'a'})
    assert vi._read_vlm_cache('b'*64,'SICK_MEDICAL') is None
    first=vi._read_vlm_cache('a'*64,'SICK_MEDICAL');first['marker']='mutated'
    assert vi._read_vlm_cache('a'*64,'SICK_MEDICAL')['marker']=='a'

def test_cache_context_isolation(bench_db):
    import vlm_inspector as vi
    vi._write_vlm_cache('c'*64,'SICK_MEDICAL',{'marker':'medical-context'})
    assert vi._read_vlm_cache('c'*64,'SPECIAL_PAID') is None,'Context-dependent results should not share a disk cache entry'

def test_pending_application_recovery_after_restart(bench_db,bench_service):
    from services.inspection_service import ProofInspectionService
    pid=add_proof(bench_db)
    req=bench_service.process_new_request(employee_id='BENCH-000',structured_data={**annual(leave_type='SICK_MEDICAL'),'proof_id':pid})
    assert req['status']=='PROCESSING'
    c=bench_db.get_db_connection();c.execute("UPDATE proof_documents SET inspection_status='FAILED',vlm_error='synthetic failure' WHERE id=?",(pid,));c.commit();c.close()
    ProofInspectionService().recover_interrupted_jobs()
    c=bench_db.get_db_connection();status=c.execute('SELECT status FROM leave_requests WHERE id=?',(req['id'],)).fetchone()[0];c.close()
    assert status!='PROCESSING','Restart recovery must also resume requests whose proof already settled'

def test_inspection_completion_before_pending_submit_persistence(bench_db,bench_service,monkeypatch):
    """Deterministically order the exact lost-wakeup race seen in COLD burst traffic."""
    import storage as st
    from contextlib import contextmanager
    from services.inspection_service import ProofInspectionService
    pid=add_proof(bench_db);svc=ProofInspectionService();svc.set_orchestrator(bench_service)
    original=st.readonly_connection;reads=0
    @contextmanager
    def ordered_read():
        nonlocal reads
        reads+=1;current=reads
        with original() as c:yield c
        if current==2:
            # The submission has read PENDING but has not persisted its request yet.
            # Worker completes now and discovers no request to resume.
            svc._apply_inspection_success(pid,{'flags':{'document_readability':'READABLE'}},job_version=1)
    monkeypatch.setattr(st,'readonly_connection',ordered_read)
    result=bench_service.process_new_request(employee_id='BENCH-000',structured_data={**annual(leave_type='SICK_MEDICAL'),'proof_id':pid})
    assert result['status']!='PROCESSING','A READY proof cannot leave a newly persisted request waiting for a job that already finished'

def test_concurrent_reviewer_only_one_final_debit(bench_db,bench_service):
    from storage import Conflict
    req=bench_service.process_new_request(employee_id='BENCH-000',structured_data=annual(to_date='2026-09-16',no_handover_needed=True))
    def approve(_):
        try:return bench_service.process_human_decision(req['id'],approver_id='BENCH-M',action_type='APPROVE')['status']
        except Conflict:return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(approve,range(4)))
    assert results.count('COMPLETED')==1
    c=bench_db.get_db_connection()
    assert c.execute('SELECT count(*) FROM leave_transactions WHERE request_id=?',(req['id'],)).fetchone()[0]==3
    assert c.execute("SELECT remaining_leave_days FROM employees WHERE employee_id='BENCH-000'").fetchone()[0]==97
    c.close()

def test_form_summary_does_not_invoke_llm(bench_db,bench_service):
    class Trap:
        def __getattr__(self,name):raise AssertionError('Unexpected model access '+name)
    bench_service.agent=Trap()
    result=bench_service.process_new_request(employee_id='BENCH-000',structured_data=annual(),enable_llm_polish=False)
    assert result['status']=='COMPLETED'

@pytest.mark.skip(reason='Hard-killing a live backend is not part of lightweight tests; recovery API is separately injected and checked')
def test_actual_process_kill_recovery():pass

def test_recovered_exhausted_job_resumes_request(bench_db,bench_service):
    from services.inspection_service import ProofInspectionService
    svc=ProofInspectionService();pid=add_proof(bench_db)
    svc.enqueue_proof_inspection(pid,'BENCH-000');job=svc._claim_next_job()
    req=bench_service.process_new_request(employee_id='BENCH-000',structured_data={**annual(leave_type='SICK_MEDICAL'),'proof_id':pid})
    c=bench_db.get_db_connection();c.execute('UPDATE proof_inspection_jobs SET retry_count=max_retries');c.commit();c.close()
    svc.recover_interrupted_jobs()
    c=bench_db.get_db_connection();status=c.execute('SELECT status FROM leave_requests WHERE id=?',(req['id'],)).fetchone()[0];c.close()
    assert status!='PROCESSING','Exhausted recovered job must not leave its application unfinished'
