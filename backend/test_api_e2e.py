"""API and database regression tests. Fixtures isolate every test from production."""
import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pytest
from scenarios import CASES,BASE,PROOF,FIELDS
from domain import RequestFacts,VerifiedProof
from storage import Conflict,AccessDenied

def payload(**changes):
    return {**{k:v for k,v in BASE.items() if k in RequestFacts.model_fields},**changes}

def proof_fixture(db,data,owner='E'):
    p=VerifiedProof(**data)
    c=db.get_db_connection()
    c.execute("INSERT INTO proof_documents(id,employee_id,storage_name,original_name,mime_type,size_bytes,proof_type,facts_json,created_at) VALUES('p',?,'p.pdf','p.pdf','application/pdf',10,?,?,?)",
              (owner,p.proof_type.value,p.model_dump_json(),'2026-09-01'))
    c.commit();c.close();return 'p'

def legacy_approval(db,id,employee,dates,department='Engineering'):
    c=db.get_db_connection()
    c.execute('''INSERT INTO leave_requests(id,employee_id,employee_name,department,from_date,to_date,workdays,leave_type,decision,status,submitted_at,updated_at)
        VALUES(?,?,?, ?,?,?,?,'Annual','AUTO_APPROVE','COMPLETED','2026-01-01','2026-01-01')''',
        (id,employee,employee,department,min(dates),max(dates),len(dates)))
    c.commit();c.close()

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_30_scenarios_persist_real_balance(case,isolated_db,service):
    db=isolated_db;raw=deepcopy(case['request']);data={k:v for k,v in raw.items() if k in RequestFacts.model_fields}
    c=db.get_db_connection()
    c.execute('UPDATE employees SET remaining_leave_days=?,employment_status=? WHERE employee_id=\'E\'',(raw['remaining_leave_days'],raw.get('employment_status','REGULAR')))
    c.commit();c.close()
    if raw.get('proof'): data['proof_id']=proof_fixture(db,raw['proof'])
    if raw.get('approved_working_dates'): legacy_approval(db,'OLD','E',raw['approved_working_dates'])
    for i in range(raw.get('team_absent_count',0)):
        legacy_approval(db,f'ABS{i}',f'E{i}',['2026-10-05','2026-10-06'])
    service.clock=lambda:datetime.fromisoformat(raw['submitted_at'])
    before=db.get_employee('E')['remaining_leave_days']
    r=service.process_new_request(employee_id='E',structured_data=data)
    assert {k:r[k] for k in FIELDS}==case['expected']
    assert db.get_employee('E')['remaining_leave_days']-before==case['expected']['annual_balance_change']

def test_form_no_model_and_protected_context(client,isolated_db):
    r=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload())
    assert r.status_code==200,r.text
    assert r.json()['data']['decision']=='AUTO_APPROVE'
    for protected in ['decision','remaining_leave_days','department','team_absent_count','proof_verification_status']:
        response=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload(**{protected:100}))
        assert response.status_code==422
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_duplicate_partial_and_atomic_rollback(service,isolated_db,monkeypatch):
    first=service.process_new_request(employee_id='E',structured_data=payload())
    duplicate=service.process_new_request(employee_id='E',structured_data=payload())
    assert duplicate['error_code']=='REQUEST_ALREADY_COVERED'
    partial=service.process_new_request(employee_id='E',structured_data=payload(from_date='2026-10-06',to_date='2026-10-07'))
    assert partial['error_code']=='OVERLAPPING_REQUEST'
    assert isolated_db.get_employee('E')['remaining_leave_days']==98
    import storage
    def fail(*args): raise RuntimeError('simulated disk failure')
    monkeypatch.setattr(storage,'save_record',fail)
    with pytest.raises(RuntimeError): service.process_new_request(employee_id='E',structured_data=payload(from_date='2026-10-12',to_date='2026-10-13'))
    c=isolated_db.get_db_connection()
    assert c.execute('SELECT COUNT(*) FROM leave_transactions').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM leave_bookings').fetchone()[0]==2
    c.close()
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_concurrent_auto_approval_same_day(service,isolated_db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:service.process_new_request(employee_id='E',structured_data=payload()),range(2)))
    assert sorted(r['decision'] for r in results)==['AUTO_APPROVE','AUTO_REJECT']
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_annual_human_approval_and_double_refund(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    r=service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')
    assert r['status']=='COMPLETED' and r['human_resolution']=='APPROVE_OVERRIDE'
    assert isolated_db.get_employee('E')['remaining_leave_days']==97
    with pytest.raises(Conflict):service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')
    undone=service.cancel(r['id'],'M',revoke=True)
    assert undone['deducted_days']==0 and undone['annual_balance_change']==0
    assert isolated_db.get_employee('E')['remaining_leave_days']==100
    with pytest.raises(Conflict):service.cancel(r['id'],'M',revoke=True)
    assert isolated_db.get_employee('E')['remaining_leave_days']==100
    again=service.process_new_request(employee_id='E',structured_data=payload())
    assert again['decision']=='AUTO_APPROVE'

def test_concurrent_human_approval(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    def approve(_):
        try:return service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')['status']
        except Conflict:return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(approve,range(2)))
    assert sorted(statuses)==['COMPLETED','CONFLICT']
    assert isolated_db.get_employee('E')['remaining_leave_days']==97

@pytest.mark.parametrize('end,actors',[('2026-10-06',['M']),('2026-10-12',['H','HRD']),('2026-10-30',['H','HRD','CEO'])])
def test_unpaid_multistep_approval(service,isolated_db,end,actors):
    r=service.process_new_request(employee_id='E',structured_data=payload(leave_type='UNPAID_OTHER',to_date=end))
    for i,a in enumerate(actors):
        r=service.process_human_decision(r['id'],approver_id=a,action_type='APPROVE')
        assert r['status']==('COMPLETED' if i==len(actors)-1 else 'PENDING_ESCALATION')
    assert all(s['status']=='APPROVED' for s in r['approval_steps'])
    assert r['deducted_days']==0 and isolated_db.get_employee('E')['remaining_leave_days']==100

def test_wrong_role_and_self_approval(client,service):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    for id in ['HR','CEO','E','B']:
        response=client.post('/api/leave/'+r['id']+'/human-decision',headers={'X-Actor-ID':id},json={'action_type':'APPROVE'})
        assert response.status_code==403,response.text
    response=client.post('/api/leave/'+r['id']+'/human-decision',headers={'X-Actor-ID':'M'},json={'action_type':'APPROVE','approver_id':'CEO'})
    assert response.status_code==403

def test_info_then_employee_resubmit(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    r=service.process_human_decision(r['id'],approver_id='M',action_type='REQUEST_MORE_INFO')
    assert r['status']=='WAITING_EMPLOYEE'
    r=service.resubmit(r['id'],'E',payload())
    assert r['status']=='COMPLETED' and r['revision']==2
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_conditional_change_rechecks_and_invalidates_prior_steps(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(leave_type='UNPAID_OTHER',to_date='2026-10-12'))
    r=service.process_human_decision(r['id'],approver_id='H',action_type='APPROVE')
    r=service.process_human_decision(r['id'],approver_id='HRD',action_type='MODIFY_CONDITIONAL',updated_fields={'to_date':'2026-10-13'})
    assert r['target_role']=='DEPARTMENT_HEAD' and r['revision']==2
    assert all(s['status']=='PENDING' for s in r['approval_steps'])
    assert isolated_db.get_employee('E')['remaining_leave_days']==100

def test_balance_and_overlap_rechecked_at_final_approval(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    c=isolated_db.get_db_connection();c.execute("UPDATE employees SET remaining_leave_days=1 WHERE employee_id='E'");c.commit();c.close()
    r=service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')
    assert r['decision']=='AUTO_REJECT' and r['error_code']=='BALANCE_EXCEEDED'
    assert isolated_db.get_employee('E')['remaining_leave_days']==1

def test_no_refund_for_unproven_legacy_debit(service,isolated_db):
    legacy_approval(isolated_db,'OLD','E',['2026-10-05'])
    with pytest.raises(Conflict):service.cancel('OLD','M',revoke=True)
    assert isolated_db.get_employee('E')['remaining_leave_days']==100

PDF=b'%PDF-1.4\n%%EOF'
def upload(client,owner='E'):
    response=client.post('/api/leave/proofs',headers={'X-Actor-ID':owner},data={'proof_type':'MEDICAL_LEAVE_CERTIFICATE'},files={'file':('note.pdf',PDF,'application/pdf')})
    assert response.status_code==200,response.text
    return response.json()['data']['proof_id']

def test_upload_hr_verification_medical_workflow(client,isolated_db):
    pid=upload(client)
    created=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload(leave_type='SICK_MEDICAL',proof_id=pid,to_date='2026-10-05')).json()['data']
    print("DEBUG CREATED:", created)
    assert created['target_role']=='HR' and created['error_code']=='PROOF_REVIEW_REQUIRED'
    assert client.get('/api/leave/proofs/'+pid,headers={'X-Actor-ID':'B'}).status_code==403
    assert client.get('/api/leave/proofs/'+pid,headers={'X-Actor-ID':'HR'}).content==PDF
    verify={k:v for k,v in PROOF.items() if k!='verified_by'};verify['verification_notes']='Đã đối chiếu với chứng từ gốc.';verify['recommended_to_date']='2026-10-05'
    assert client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'E'},json=verify).status_code==403
    r=client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'HR'},json=verify)
    assert r.status_code==200,r.text
    req=isolated_db.get_leave_request(created['id'])
    assert req['decision']=='AUTO_APPROVE' and req['deducted_days']==0
    assert isolated_db.get_employee('E')['remaining_leave_days']==100
    assert client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'HR'},json=verify).status_code==409

def test_upload_limits_and_fake_mime(client):
    assert client.post('/api/leave/proofs',headers={'X-Actor-ID':'E'},files={'file':('x.png',b'not png','image/png')}).status_code==415
    assert client.post('/api/leave/proofs',headers={'X-Actor-ID':'E'},files={'file':('x.pdf',b'%PDF-'+b'0'*(10*1024*1024),'application/pdf')}).status_code==413

def test_manager_cannot_approve_unverified_proof(client):
    pid=upload(client)
    r=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload(leave_type='SICK_MEDICAL',proof_id=pid)).json()['data']
    for actor,status in [('M',403),('HR',409)]:
        result=client.post('/api/leave/'+r['id']+'/human-decision',headers={'X-Actor-ID':actor},json={'action_type':'APPROVE'})
        assert result.status_code==status,result.text

def test_actor_queue_and_detail_visibility(client,service):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    assert client.get('/api/leave/requests').status_code==401
    assert client.get('/api/leave/'+r['id'],headers={'X-Actor-ID':'B'}).status_code==403
    assert client.get('/api/leave/requests',headers={'X-Actor-ID':'HRD'}).json()['data']==[]
    data=client.get('/api/leave/requests',headers={'X-Actor-ID':'M'}).json()['data']
    assert len(data)==1 and data[0]['can_act']

def test_verify_harness_no_llm_and_no_mutation(client,isolated_db):
    before=isolated_db.get_all_leave_requests()
    r=client.post('/api/verify/escalation')
    assert r.status_code==200,r.text
    s=r.json()['summary']
    assert (s['passed_cases'],s['auto_approved_cases'],s['escalated_cases'],s['llm_calls'])==(5,3,2,0)
    assert s['latency_seconds']<90
    assert isolated_db.get_all_leave_requests()==before

def test_migration_is_idempotent_and_preserves_history(isolated_db):
    before=isolated_db.get_employee('E')['remaining_leave_days']
    legacy_approval(isolated_db,'HISTORY','E',['2026-01-05'])
    old=isolated_db.get_leave_request('HISTORY')
    isolated_db.init_db();isolated_db.init_db()
    assert isolated_db.get_employee('E')['remaining_leave_days']==before
    assert isolated_db.get_leave_request('HISTORY')==old
    c=isolated_db.get_db_connection()
    assert c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM leave_transactions').fetchone()[0]==0
    c.close()
