"""New feature regression checks only. The project's existing test cases are untouched."""
import os,sys,json,tempfile,hashlib
from pathlib import Path
from datetime import datetime
import pytest

ROOT=Path(__file__).resolve().parents[1]
_collection=tempfile.TemporaryDirectory(prefix='mlai-management-checks-')
os.environ.update(LEAVE_DATA_DIR=_collection.name,LEAVE_DB_PATH=str(Path(_collection.name)/'collection.db'),
    LEAVE_AUTH_SECRET='local-employee-management-tests-only',LEAVE_ALLOW_ACTOR_HEADER='true',
    SEED_DEMO_DATA='false',APP_ENV='test',VLM_WARMUP_ON_STARTUP='0',VLM_FORCE_MOCK='1')
for folder in ('backend','core'):sys.path.insert(0,str(ROOT/folder))

@pytest.fixture
def client(tmp_path,monkeypatch):
    import database as db
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'employee.db'))
    monkeypatch.setenv('LEAVE_UPLOAD_DIR',str(tmp_path/'uploads'))
    db.init_db()
    from main import app
    from fastapi.testclient import TestClient
    # No app lifespan / background inference needed for directory operations.
    return TestClient(app)

def headers(id='EMP000'):return {'X-Actor-ID':id}
def create(client,dept='Engineering',actor='EMP000',name='Nhân viên Kiểm thử'):
    return client.post('/api/management/employees',headers=headers(actor),json={'name':name,'department':dept})

def test_add_employee_returns_selectable_person_and_two_department_limit(client):
    r=create(client);assert r.status_code==201
    e=r.json()['data'];assert e['name']=='Nhân viên Kiểm thử' and e['status']=='ACTIVE'
    assert e['remaining_leave_days']==12 and e['actor_roles']==[]
    directory=client.get('/api/verify/employees',headers=headers()).json()['data']
    assert any(p['employee_id']==e['employee_id'] for p in directory)
    assert client.get('/api/management/employees',headers=headers()).json()['departments']==['Engineering','Marketing & Operations']
    assert create(client,dept='Third department').status_code==422

def test_manager_scope_and_non_manager_access(client):
    assert client.get('/api/management/employees',headers=headers('EMP005')).status_code==403
    assert create(client,actor='EMP005').status_code==403
    assert create(client,dept='Marketing & Operations',actor='EMP001').status_code==403
    r=create(client,actor='EMP001');assert r.status_code==201
    assert client.delete('/api/management/employees/'+r.json()['data']['employee_id'],headers=headers('EMP002')).status_code==403

@pytest.mark.parametrize('name',['   ','<img src=x onerror=alert(1)>','a'*101])
def test_invalid_name_is_rejected(client,name):
    assert create(client,name=name).status_code==422

def test_delete_is_soft_and_revokes_selection_and_login(client):
    e=create(client).json()['data'];eid=e['employee_id']
    token=client.post('/api/auth/demo-token',json={'actor_id':eid}).json()['token']
    assert client.delete('/api/management/employees/'+eid,headers=headers()).status_code==200
    assert all(p['employee_id']!=eid for p in client.get('/api/management/employees',headers=headers()).json()['data'])
    assert client.post('/api/auth/demo-token',json={'actor_id':eid}).status_code==403
    assert client.post('/api/leave/request',headers={'Authorization':'Bearer '+token},json={'leave_type':'ANNUAL','from_date':'2026-09-14','to_date':'2026-09-14'}).status_code==403
    import database as db
    with db.get_db_connection() as c:
        assert c.execute('SELECT status FROM employees WHERE employee_id=?',(eid,)).fetchone()[0]=='INACTIVE'
        assert c.execute("SELECT count(*) FROM audit_logs WHERE request_id=? AND action='EMPLOYEE_DEACTIVATED'",('EMPLOYEE-'+eid,)).fetchone()[0]==1

def test_completed_leave_and_balance_history_are_preserved(client):
    e=create(client).json()['data'];eid=e['employee_id']
    from services.orchestration import LeaveOrchestratorService
    svc=LeaveOrchestratorService(clock=lambda:datetime.fromisoformat('2026-09-01T08:00:00+07:00'))
    req=svc.process_new_request(employee_id=eid,structured_data={'leave_type':'ANNUAL','from_date':'2026-09-14','to_date':'2026-09-14'})
    assert req['status']=='COMPLETED'
    assert client.delete('/api/management/employees/'+eid,headers=headers()).status_code==200
    import database as db
    with db.get_db_connection() as c:
        assert c.execute('SELECT status FROM leave_requests WHERE id=?',(req['id'],)).fetchone()[0]=='COMPLETED'
        assert c.execute('SELECT count(*) FROM leave_transactions WHERE request_id=?',(req['id'],)).fetchone()[0]==1
        assert c.execute('SELECT remaining_leave_days FROM employees WHERE employee_id=?',(eid,)).fetchone()[0]==11

def test_pending_request_cannot_be_orphaned_by_delete(client):
    e=create(client).json()['data'];eid=e['employee_id']
    from services.orchestration import LeaveOrchestratorService
    svc=LeaveOrchestratorService(clock=lambda:datetime.fromisoformat('2026-09-01T08:00:00+07:00'))
    req=svc.process_new_request(employee_id=eid,structured_data={'leave_type':'ANNUAL','from_date':'2026-09-14','to_date':'2026-09-16','no_handover_needed':True})
    assert req['status']=='PENDING_ESCALATION'
    assert client.delete('/api/management/employees/'+eid,headers=headers()).status_code==409

def test_manager_accounts_are_preserved(client):
    assert client.delete('/api/management/employees/EMP001',headers=headers()).status_code==409
    assert client.post('/api/auth/demo-token',json={'actor_id':'EMP001'}).status_code==200

def test_test_case_data_and_decisions_are_unchanged_after_directory_edits(client):
    fixture=ROOT/'core/test_cases.json';before_hash=hashlib.sha256(fixture.read_bytes()).hexdigest()
    cases_before=client.get('/api/verify/test-cases').json()
    result_before=client.post('/api/verify/escalation').json()
    created=create(client).json()['data']
    assert client.delete('/api/management/employees/'+created['employee_id'],headers=headers()).status_code==200
    assert client.delete('/api/management/employees/EMP005',headers=headers()).status_code==200
    cases_after=client.get('/api/verify/test-cases').json();result_after=client.post('/api/verify/escalation').json()
    assert cases_before==cases_after
    assert result_before['details']==result_after['details']
    assert hashlib.sha256(fixture.read_bytes()).hexdigest()==before_hash

def test_duplicate_names_keep_distinct_employee_ids(client):
    a=create(client).json()['data'];b=create(client).json()['data']
    assert a['employee_id']!=b['employee_id']

def test_custom_title_and_edit_update_display_without_granting_approver_permissions(client):
    r=client.post('/api/management/employees',headers=headers(),json={
        'name':'Nhân viên Chức danh','department':'Engineering','job_title':'Frontend Engineer'})
    assert r.status_code==201
    e=r.json()['data'];assert e['role']=='Frontend Engineer' and e['actor_roles']==[]
    r=client.patch('/api/management/employees/'+e['employee_id'],headers=headers(),json={'job_title':'CEO'})
    assert r.status_code==200 and r.json()['data']['role']=='CEO' and r.json()['data']['actor_roles']==[]
    assert client.get('/api/management/employees',headers=headers(e['employee_id'])).status_code==403

def test_title_change_respects_manager_scope_and_protects_existing_managers(client):
    e=create(client).json()['data']
    endpoint='/api/management/employees/'+e['employee_id']
    assert client.patch(endpoint,headers=headers('EMP002'),json={'job_title':'Developer'}).status_code==403
    assert client.patch(endpoint,headers=headers(),json={'job_title':'   '}).status_code==422
    assert client.patch(endpoint,headers=headers(),json={'job_title':'Developer','actor_roles':[{'role':'CEO'}]}).status_code==422
    assert client.patch('/api/management/employees/EMP001',headers=headers(),json={'job_title':'Other'}).status_code==409

def test_real_local_api_accepts_annual_submission_without_server_or_vlm(client,monkeypatch):
    from services.orchestration import LeaveOrchestratorService
    import routers.leave_router as leave
    monkeypatch.setattr(leave,'service',LeaveOrchestratorService(clock=lambda:datetime.fromisoformat('2026-09-01T08:00:00+07:00')))
    e=create(client).json()['data']
    token=client.post('/api/auth/demo-token',json={'actor_id':e['employee_id']}).json()['token']
    r=client.post('/api/leave/request',headers={'Authorization':'Bearer '+token},json={
        'employee_id':e['employee_id'],'leave_type':'ANNUAL','from_date':'2026-11-09','to_date':'2026-11-09','reason':'Kiểm thử nộp đơn cục bộ'})
    assert r.status_code==200 and r.json()['data']['status']=='COMPLETED'
    assert r.json()['data']['decision']=='AUTO_APPROVE'
