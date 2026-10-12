import os, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
for name in ('backend','core'):sys.path.insert(0,str(ROOT/name))

@pytest.fixture
def bench_db(tmp_path,monkeypatch):
    import database as db
    monkeypatch.setattr(db,'DB_PATH',str(tmp_path/'benchmark.db'))
    monkeypatch.setattr(db,'EMPLOYEES_JSON_PATH',str(tmp_path/'empty.json'))
    (tmp_path/'empty.json').write_text('[]')
    monkeypatch.setenv('LEAVE_UPLOAD_DIR',str(tmp_path/'uploads'))
    monkeypatch.setenv('APP_ENV','test');monkeypatch.setenv('SEED_DEMO_DATA','false')
    monkeypatch.setenv('LEAVE_ALLOW_ACTOR_HEADER','true');monkeypatch.setenv('VLM_WARMUP_ON_STARTUP','0')
    from benchmarks.common import seed_db
    seed_db()
    import vlm_inspector as vi
    vi._VLM_CACHE_MEM.clear()
    def forbidden(*a,**kw):raise AssertionError('Real inference forbidden in lightweight benchmark tests')
    monkeypatch.setattr(vi,'ollama_generate',forbidden)
    return db

@pytest.fixture
def bench_service(bench_db):
    from services.orchestration import LeaveOrchestratorService
    from datetime import datetime
    return LeaveOrchestratorService(clock=lambda:datetime.fromisoformat('2026-09-01T08:00:00+07:00'))

@pytest.fixture
def bench_client(bench_service,monkeypatch):
    import routers.leave_router as router
    monkeypatch.setattr(router,'service',bench_service)
    from main import app
    from fastapi.testclient import TestClient
    # Deliberately no lifespan: controlled tests drive inspection jobs explicitly.
    with TestClient(app,raise_server_exceptions=False) as client:
        from services.inspection_service import GLOBAL_INSPECTION_SERVICE
        GLOBAL_INSPECTION_SERVICE.stop_worker()
        yield client
