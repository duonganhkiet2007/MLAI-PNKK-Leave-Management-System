"""Never import the app with a production database or initialize real models in tests."""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
ROOT=Path(__file__).parent
for name in ('Leave_Application','LLM-KIET','backend','tests'): sys.path.insert(0,str(ROOT/name))
_collection_tmp=tempfile.TemporaryDirectory(prefix='mlai-collection-')
os.environ['LEAVE_DB_PATH']=str(Path(_collection_tmp.name)/'collection.db')
os.environ['LEAVE_UPLOAD_DIR']=str(Path(_collection_tmp.name)/'uploads')

@pytest.fixture(autouse=True)
def prohibit_live_models(monkeypatch):
    import llm_client
    def forbidden(*args,**kwargs): raise AssertionError('Live model access is forbidden in tests')
    monkeypatch.setattr(llm_client.LocalQwenEngine,'load_model',forbidden)
    monkeypatch.setattr(llm_client.LocalQwenEngine,'generate_json',forbidden)

@pytest.fixture
def isolated_db(tmp_path,monkeypatch):
    import database as db
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'leave.db'))
    monkeypatch.setenv('LEAVE_UPLOAD_DIR',str(tmp_path/'uploads'))
    db.init_db()
    c=db.get_db_connection()
    c.execute('DELETE FROM actor_roles');c.execute('DELETE FROM employees')
    people=[('E','Nguyễn Văn An','Engineering'),('B','Bàn Giao','Engineering')]+[(f'E{i}',f'Person {i}','Engineering') for i in range(8)]
    people += [('M','Manager','Engineering'),('H','Head','Engineering'),('HR','HR Officer','HR'),('HRD','HR Director','HR'),('CEO','Chief','Board')]
    for id,name,dept in people:
        c.execute("INSERT INTO employees(employee_id,name,department,remaining_leave_days,status,employment_status) VALUES(?,?,?,100,'ACTIVE','REGULAR')",(id,name,dept))
    for id,role,scope in [('M','DIRECT_MANAGER','Engineering'),('H','DEPARTMENT_HEAD','Engineering'),('HR','HR','*'),('HRD','HRD','*'),('CEO','CEO','*')]:
        c.execute('INSERT INTO actor_roles VALUES(?,?,?)',(id,role,scope))
    c.commit();c.close()
    return db

@pytest.fixture
def service(isolated_db):
    from services.orchestration import LeaveOrchestratorService
    return LeaveOrchestratorService(clock=lambda:datetime(2026,9,1,8,tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

@pytest.fixture
def client(service,monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    import routers.leave_router as router
    monkeypatch.setattr(router,'service',service)
    with TestClient(app) as c: yield c
