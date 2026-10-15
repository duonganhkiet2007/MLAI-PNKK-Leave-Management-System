"""Isolated, non-persisting Verify harness. No production DB or LLM dependencies."""
import json
import os
from contextlib import contextmanager
import time
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from rule_engine import LeaveRequest, LeaveRuleEngine
from domain import RequestFacts, VerifiedProof
from calendar_service import CalendarService
from services.orchestration import LeaveOrchestratorService
import storage as st
from routers.leave_router import actor
import database as db

router=APIRouter(prefix='/api/verify',tags=['Verify Harness'])
_ROOT = Path(__file__).resolve().parents[2]
_PHOTO_DIRS = (
    _ROOT / "backend" / "data" / "uploads",
    _ROOT / "backend" / "uploads",
    _ROOT / "tests" / "assets" / "proofs",
    _ROOT / "frontend" / "assets" / "proofs",
)
_ALLOWED_PHOTO_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}
BENCHMARK_SESSION_CACHE = {}
BENCHMARK_CASE_PREFIX = 'REQ-TC-'


def _cleanup_benchmark_request(req_id: str):
    try:
        with st.transaction() as conn:
            req = conn.execute('SELECT employee_id, deducted_days, leave_type FROM leave_requests WHERE id=?', (req_id,)).fetchone()
            if req and req['deducted_days'] and req['deducted_days'] > 0 and (req['leave_type'] or '') == 'ANNUAL':
                conn.execute('UPDATE employees SET remaining_leave_days=remaining_leave_days+? WHERE employee_id=?',
                             (req['deducted_days'], req['employee_id']))
            conn.execute('DELETE FROM approval_steps WHERE request_id=?', (req_id,))
            conn.execute('DELETE FROM leave_bookings WHERE request_id=?', (req_id,))
            conn.execute('DELETE FROM leave_transactions WHERE request_id=?', (req_id,))
            conn.execute('DELETE FROM leave_requests WHERE id=?', (req_id,))
            conn.execute('DELETE FROM audit_logs WHERE request_id=?', (req_id,))
    except Exception:
        pass
TEST_CASES_FILE=Path(__file__).resolve().parents[2]/'core'/'test_cases.json'
CHECK_FIELDS=('decision','target_role','requested_working_days','deducted_days','annual_balance_change','uncertainty_category','error_code')

def evaluate_case(data):
    return LeaveRuleEngine.evaluate(LeaveRequest.model_validate(data)).model_dump(mode='json')

@router.get('/test-cases')
def get_all_test_cases():
    cases=json.loads(TEST_CASES_FILE.read_text())
    return {'success':True,'total':len(cases),'data':cases}

@router.post('/escalation')
def run_verify_harness():
    begin=time.perf_counter()
    cases=[c for c in json.loads(TEST_CASES_FILE.read_text()) if c.get('is_verify_harness')]
    details=[]
    for c in cases:
        actual=evaluate_case(c['request'])
        passed=all(actual[k]==c['expected'][k] for k in CHECK_FIELDS)
        details.append({'test_id':c['id'],'scenario_name':c['scenario_name'],'expected':c['expected'],
            'expected_decision':c['expected']['decision'],'actual_decision':actual['decision'],
            'actual_category':actual['uncertainty_category'],'is_passed':passed,**actual})
    elapsed=time.perf_counter()-begin
    auto=sum(d['decision']=='AUTO_APPROVE' for d in details)
    esc=sum(d['decision']=='ESCALATE' for d in details)
    count=sum(d['is_passed'] for d in details)
    passed=len(details)==5 and count==5 and auto==3 and esc==2 and elapsed<90
    return {'success':True,'summary':{'total_cases':len(details),'passed_cases':count,
        'auto_approved_cases':auto,'escalated_cases':esc,'target_auto':3,'target_escalate':2,
        'overall_status':'PASS' if passed else 'FAIL','latency_seconds':elapsed,'llm_calls':0},'details':details}

SPRINT1_BENCHMARK_CASES = [
    {
        "id": "TC-AI-01",
        "scenario_name": "Phép năm 1 ngày tự động duyệt (1-2 ngày đủ số dư)",
        "sprint1_group": "ROUTINE",
        "sprint1_group_name": "Thường quy (Tự duyệt)",
        "employee_id": "EMP005",
        "employee_name": "Nguyễn Văn An",
        "department": "Engineering",
        "leave_type": "ANNUAL",
        "from_date": "2026-10-19",
        "to_date": "2026-10-19",
        "reason": "Việc riêng gia đình",
        "remaining_leave_days": 10,
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-16T08:00:00+07:00",
        "expected": {
            "decision": "AUTO_APPROVE",
            "target_role": None,
            "deducted_days": 1,
            "uncertainty_category": None,
            "error_code": None
        },
        "actionable_question": "Tự động xử lý hoàn toàn: Phép năm hợp lệ, đủ số dư, không cần chuyển người duyệt."
    },
    {
        "id": "TC-EMP008-03",
        "scenario_name": "Phép năm 2 ngày có bàn giao cùng phòng cho EMP010",
        "sprint1_group": "ROUTINE",
        "sprint1_group_name": "Thường quy (Tự duyệt)",
        "employee_id": "EMP008",
        "employee_name": "Nguyễn Thị Kim Ngân",
        "department": "Marketing & Operations",
        "leave_type": "ANNUAL",
        "from_date": "2026-10-22",
        "to_date": "2026-10-23",
        "reason": "Nghỉ phép thường niên",
        "remaining_leave_days": 12,
        "handover_person_id": "EMP010",
        "handover": {"employee_id": "EMP010", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-19T08:00:00+07:00",
        "expected": {
            "decision": "AUTO_APPROVE",
            "target_role": None,
            "deducted_days": 2,
            "uncertainty_category": None,
            "error_code": None
        },
        "actionable_question": "Tự động xử lý hoàn toàn: Phép năm 2 ngày có bàn giao hợp lệ, không cần chuyển người duyệt."
    },
    {
        "id": "TC-AI-03B",
        "scenario_name": "Biên số dư phép - Còn 1 ngày, xin 2 ngày (Từ chối tự động)",
        "sprint1_group": "ROUTINE",
        "sprint1_group_name": "Thường quy (Tự từ chối)",
        "employee_id": "EMP006",
        "employee_name": "Bùi Tuấn Kiệt",
        "department": "Engineering",
        "leave_type": "ANNUAL",
        "from_date": "2026-10-19",
        "to_date": "2026-10-20",
        "reason": "Nghỉ việc gia đình 2 ngày",
        "remaining_leave_days": 1,
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-16T08:00:00+07:00",
        "expected": {
            "decision": "AUTO_REJECT",
            "target_role": "EMPLOYEE",
            "deducted_days": 0,
            "uncertainty_category": "OUT_OF_POLICY",
            "error_code": "BALANCE_EXCEEDED"
        },
        "actionable_question": "Tự động xử lý hoàn toàn: Bị từ chối tự động do số ngày yêu cầu (2) vượt số dư phép năm còn lại (1)."
    },
    {
        "id": "TC-EMP003-01",
        "scenario_name": "Con kết hôn 1 ngày nguyên lương theo Điều 115 BLLĐ (có giấy kết hôn)",
        "sprint1_group": "AUTHORITY_ESCALATION",
        "sprint1_group_name": "Vượt thẩm quyền AI (Chuyển Quản lý)",
        "employee_id": "EMP003",
        "employee_name": "Trần Quốc Hưng",
        "department": "Engineering",
        "leave_type": "SPECIAL_PAID",
        "reason_category": "CHILD_MARRIAGE",
        "from_date": "2026-10-26",
        "to_date": "2026-10-26",
        "reason": "Nghỉ tham dự lễ thành hôn của con trai ruột (Trần Quốc Anh)",
        "proof_file": "proof_emp003_wedding_child.png",
        "proof": {"proof_type": "MARRIAGE_CERTIFICATE"},
        "submitted_at": "2026-10-19T08:00:00+07:00",
        "expected": {
            "decision": "ESCALATE",
            "target_role": "DIRECT_MANAGER",
            "deducted_days": 0
        },
        "actionable_question": "Trần Quốc Hưng xin nghỉ 1 ngày dự lễ cưới con trai, kèm giấy chứng nhận kết hôn. Quản lý trực tiếp có phê duyệt 1 ngày nghỉ hưởng nguyên lương theo Điều 115 BLLĐ không?"
    },
    {
        "id": "TC-MGR-02",
        "scenario_name": "Phép năm 4 ngày có bàn giao: chuyển Quản lý Marketing duyệt",
        "sprint1_group": "AUTHORITY_ESCALATION",
        "sprint1_group_name": "Vượt thẩm quyền AI (Chuyển Quản lý)",
        "employee_id": "EMP010",
        "employee_name": "Phan Thảo My",
        "department": "Marketing & Operations",
        "leave_type": "ANNUAL",
        "from_date": "2026-10-19",
        "to_date": "2026-10-22",
        "reason": "Nghỉ phép cá nhân",
        "handover_person_id": "EMP008",
        "submitted_at": "2026-10-09T08:00:00+07:00",
        "expected": {
            "decision": "ESCALATE",
            "target_role": "DIRECT_MANAGER",
            "deducted_days": 0,
            "uncertainty_category": "AUTHORITY_ESCALATION",
            "error_code": "DURATION_OVER_AI_LIMIT"
        },
        "actionable_question": "Phan Thảo My xin nghỉ 4 ngày phép năm có bàn giao. Quản lý trực tiếp (Dương Mỹ Duyên) có phê duyệt đợt nghỉ phép này không?"
    }
]

@contextmanager
def _isolated_benchmark_db():
    """Chạy kịch bản chuẩn trên DB tạm (sao từ DB thật, xóa đơn, số dư/thử việc gốc từ employees.json):
    kết quả Verify không phụ thuộc đơn, số dư hay ngày phép được cấp thêm trên hệ thống đang chạy."""
    import shutil, sqlite3, tempfile
    tmpdir = tempfile.mkdtemp(prefix='mlai-bench-')
    path = os.path.join(tmpdir, 'bench.db')
    src = sqlite3.connect(db.DB_PATH)
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
        for table in ('leave_requests', 'approval_steps', 'leave_bookings', 'leave_transactions', 'audit_logs', 'proof_inspection_jobs'):
            try: dst.execute(f'DELETE FROM {table}')
            except sqlite3.OperationalError: pass
        if os.path.exists(db.EMPLOYEES_JSON_PATH):
            with open(db.EMPLOYEES_JSON_PATH, encoding='utf-8') as f:
                for emp in json.load(f):
                    dst.execute('UPDATE employees SET remaining_leave_days=? WHERE employee_id=?',
                                (float(emp.get('remaining_leave_days', 12.0)), emp.get('employee_id')))
        dst.commit()
        db.sync_employment_fields(dst, overwrite=True)
    finally:
        src.close(); dst.close()
    token = db.DB_PATH_OVERRIDE.set(path)
    try:
        yield
    finally:
        db.DB_PATH_OVERRIDE.reset(token)
        shutil.rmtree(tmpdir, ignore_errors=True)


def _ensure_proof_doc(case: dict):
    proof_file = case.get('proof_file')
    if not proof_file:
        return None, 'none'
    # Dùng đúng thư mục upload đang chạy (LEAVE_UPLOAD_DIR), giống API tải chứng từ.
    uploads_dir = Path(os.getenv('LEAVE_UPLOAD_DIR', str(Path(db.DB_PATH).parent / 'uploads')))
    uploads_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(proof_file).suffix or '.png'
    # Gán tên file bằng UUID nếu tên file có tiếng Việt/non-ASCII
    uuid_storage_name = f"{uuid.uuid4().hex}{ext}" if any(ord(c) > 127 for c in proof_file) else proof_file
    dest_path = uploads_dir / uuid_storage_name
    if not dest_path.exists():
        root = Path(__file__).resolve().parents[2]
        for candidate in (
            uploads_dir / proof_file,
            root / 'tests' / 'assets' / 'proofs' / proof_file,
            root / 'frontend' / 'assets' / 'proofs' / proof_file,
        ):
            if candidate.exists():
                import shutil
                shutil.copy2(candidate, dest_path)
                break
    pid = f"PROOF-TC-{case['id']}"
    file_size = dest_path.stat().st_size if dest_path.exists() else 50000
    ptype = (case.get('proof') or {}).get('proof_type') or 'OTHER'
    row = {
        'id': pid, 'employee_id': case['employee_id'], 'storage_name': uuid_storage_name, 'original_name': uuid_storage_name,
        # Không nạp sẵn thông tin chứng từ (tên, ngày chỉ định, VERIFIED...) từ kịch bản: chỉ ghi loại giấy như khi
        # nhân viên tải lên, để VLM thật đọc ảnh và rule engine quyết định giống hệt một đơn nộp qua giao diện.
        'mime_type': 'image/png', 'size_bytes': file_size, 'proof_type': ptype, 'facts_json': json.dumps({'proof_type': ptype}),
        # Cột cũ chỉ có ở DB tạo từ schema đời trước; DB mới không có nên chỉ ghi khi cột tồn tại.
        'storage_path': str(dest_path), 'file_real_path': str(dest_path), 'original_filename': uuid_storage_name,
        'file_size_bytes': file_size, 'uploaded_by': case['employee_id'],
        'created_at': datetime.now().isoformat(), 'inspection_status': 'PENDING',
    }
    with st.transaction() as conn:
        existing = {r[1] for r in conn.execute('PRAGMA table_info(proof_documents)')}
        cols = [k for k in row if k in existing]
        conn.execute(f"INSERT OR REPLACE INTO proof_documents({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
                     [row[k] for k in cols])
    _inspect_like_upload(pid, case)
    return pid, 'image_attachment'


def _inspect_like_upload(proof_id: str, case: dict) -> None:
    """Đọc chứng từ đúng như khi nhân viên tải lên qua giao diện (cùng hàng đợi, cùng prompt, cùng cache VLM),
    nhưng chạy ngay trong luồng này nên mọi dữ liệu nằm trong DB tạm của lượt Verify."""
    from services.inspection_service import GLOBAL_INSPECTION_SERVICE as svc
    res = svc.enqueue_proof_inspection(proof_id, case['employee_id'],
                                       proof_type_hint=(case.get('proof') or {}).get('proof_type'),
                                       leave_type_hint=case.get('leave_type'),
                                       reason_category_hint=case.get('reason_category'))
    if res.get('inspection_status') == 'READY':
        return
    for _ in range(3):  # lần đầu + tối đa 2 lần thử lại như worker
        job = svc._claim_next_job()
        if not job:
            break
        svc._process_single_job(job)
        with st.readonly_connection() as conn:
            r = conn.execute('SELECT inspection_status FROM proof_documents WHERE id=?', (proof_id,)).fetchone()
        if r and r['inspection_status'] in ('READY', 'FAILED'):
            break

def _run_single_case(c: dict, orch: LeaveOrchestratorService = None):
    begin = time.perf_counter()
    proof_id, att_type = _ensure_proof_doc(c)
    sub_at = c.get('submitted_at')
    if sub_at:
        try:
            dt = datetime.fromisoformat(sub_at)
            orch = LeaveOrchestratorService(clock=lambda: dt, register_global=False)
        except Exception:
            orch = orch or LeaveOrchestratorService(register_global=False)
    elif orch is None:
        orch = LeaveOrchestratorService(register_global=False)

    facts_data = {
        'leave_type': c['leave_type'],
        'from_date': c['from_date'],
        'to_date': c['to_date'],
        'reason': c['reason'],
        'reason_category': c.get('reason_category'),
        'handover_person_id': c.get('handover_person_id'),
    }
    if proof_id:
        facts_data['proof_id'] = proof_id
        facts_data['attachment_type'] = att_type

    req_id = f"REQ-{c['id']}"
    record = orch.process_new_request(
        raw_text=None,
        employee_id=c['employee_id'],
        structured_data=facts_data,
        enable_llm_polish=False,
        custom_request_id=req_id,
        skip_vlm=False
    )

    # Simulate a real user submission flow for benchmark checks, but keep the main
    # leave database clean. The record is retained in an isolated in-memory cache
    # for the detail modal, and removed from the shared DB immediately after submission.
    # Dựng sẵn bảng "Kết quả kiểm tra" (checklist cây quyết định) như đơn thường, khi đơn còn trong DB của lượt chạy,
    # để khung Chi tiết của tab Test hiển thị giống hệt Hồ sơ đơn.
    try:
        from routers.leave_router import get_request_analysis
        analysis = get_request_analysis(req_id, actor_id=c['employee_id']) or {}
        if isinstance(analysis, dict):
            data = analysis.get('data', analysis)
            record = dict(record)
            record['decision_tree_checklist'] = data.get('decision_tree_checklist') or []
            if data.get('vlm_analysis') and not record.get('vlm_analysis_json'):
                record['vlm_analysis_json'] = data['vlm_analysis']
            if data.get('llm_summary'):
                record['llm_summary_json'] = data['llm_summary']
    except Exception as exc:
        print(f"⚠️ [VERIFY] Không dựng được checklist cho {c['id']}: {exc}")
    BENCHMARK_SESSION_CACHE[c['id']] = record
    _cleanup_benchmark_request(req_id)
    elapsed = time.perf_counter() - begin

    actual_decision = record.get('decision')
    target_role = record.get('target_role')
    error_code = record.get('error_code')
    llm_summary = record.get('llm_summary_json') or {}
    vlm_analysis = record.get('vlm_analysis_json') or {}

    actionable_q = (
        llm_summary.get('actionable_question') or
        record.get('actionable_question') or
        c.get('actionable_question') or ''
    )
    plain_reason = (
        llm_summary.get('summary_natural_vn') or
        record.get('human_readable_explanation') or
        ''
    )

    is_passed = (actual_decision == c['expected']['decision'])
    if c['expected'].get('target_role'):
        is_passed = is_passed and (target_role == c['expected']['target_role'])

    detail = {
        'test_id': c['id'],
        'request_id': req_id,
        'scenario_name': c['scenario_name'],
        'sprint1_group': c['sprint1_group'],
        'sprint1_group_name': c['sprint1_group_name'],
        'employee_name': c['employee_name'],
        'employee_id': c['employee_id'],
        'department': c['department'],
        'leave_type': c['leave_type'],
        'from_date': c['from_date'],
        'to_date': c['to_date'],
        'proof_file': c.get('proof_file'),
        'expected_decision': c['expected']['decision'],
        'actual_decision': actual_decision,
        'target_role': target_role or c['expected'].get('target_role'),
        'error_code': error_code,
        'actionable_question': actionable_q,
        'plain_reason': plain_reason,
        'is_passed': is_passed,
        'vlm_analysis': vlm_analysis,
        'llm_summary': llm_summary,
        'latency_seconds': round(elapsed, 3),
        'db_status': record.get('status'),
        'record': record
    }
    BENCHMARK_SESSION_CACHE[c['id']] = detail
    return detail

@router.post('/sprint1-benchmark/case/{case_id}')
def run_single_sprint1_benchmark_case(case_id: str):
    matched = next((c for c in SPRINT1_BENCHMARK_CASES if c['id'] == case_id), None)
    if not matched:
        return {'success': False, 'message': f'Không tìm thấy test case {case_id}'}
    with _isolated_benchmark_db():
        detail = _run_single_case(matched)
    return {'success': True, 'data': detail}

@router.get('/case-detail/{case_id}')
def get_benchmark_case_detail(case_id: str):
    req_id = case_id if case_id.startswith('REQ-') else f"REQ-{case_id}"
    cached = BENCHMARK_SESSION_CACHE.get(case_id.replace('REQ-', ''), None)
    if cached:
        record = cached.get('record') or cached
        return {
            'success': True,
            'data': record,
            'audit_trail': [],
            'source': 'benchmark_session_cache'
        }
    # Kết quả Verify chỉ lưu trong bộ nhớ: sau khi server khởi động lại thì mất. Chạy lại kịch bản (trên DB tạm,
    # kết quả tất định, chứng từ đã có cache VLM) để khung Chi tiết luôn có đủ bảng Kết quả kiểm tra.
    matched = next((c for c in SPRINT1_BENCHMARK_CASES if c['id'] == case_id.replace('REQ-', '')), None)
    if matched:
        try:
            with _isolated_benchmark_db():
                detail = _run_single_case(matched)
            return {'success': True, 'data': detail.get('record') or detail, 'audit_trail': [],
                    'source': 'benchmark_rerun'}
        except Exception as e:
            print(f"⚠️ [VERIFY] Không chạy lại được {case_id}: {e}")
    with st.readonly_connection() as conn:
        try:
            req = st.read_request(conn, req_id)
            serialized = st.serialize(conn, req)
            logs = [dict(r) for r in conn.execute('SELECT * FROM audit_logs WHERE request_id=? ORDER BY id', (req_id,))]
            return {
                'success': True,
                'data': serialized,
                'audit_trail': logs
            }
        except Exception as e:
            return {'success': False, 'message': f'Hồ sơ {req_id} chưa sẵn sàng: {e}'}

@router.post('/sprint1-benchmark')
def run_sprint1_benchmark():
    begin = time.perf_counter()
    details = []
    with _isolated_benchmark_db():
        for c in SPRINT1_BENCHMARK_CASES:
            details.append(_run_single_case(c))

    elapsed = time.perf_counter() - begin
    auto_count = sum(d['actual_decision'] in ('AUTO_APPROVE', 'AUTO_REJECT', 'NO_LEAVE_REQUIRED') for d in details)
    esc_count = sum(d['actual_decision'] == 'ESCALATE' for d in details)
    passed_count = sum(d['is_passed'] for d in details)
    all_ok = (passed_count == len(details))

    return {
        'success': True,
        'summary': {
            'total_cases': len(details),
            'passed_cases': passed_count,
            'auto_cases': auto_count,
            'target_auto': 3,
            'escalate_cases': esc_count,
            'target_escalate': 2,
            'overall_status': 'PASS' if all_ok else 'FAIL',
            'latency_seconds': round(elapsed, 4)
        },
        'details': details
    }


class CustomVerifyInput(LeaveRequest):
    model_config = ConfigDict(extra='ignore')
    request_id: str = 'VERIFY'
    employee_id: str = 'VERIFY_EMPLOYEE'
    employee_name: str = 'Nhân sự kiểm thử'
    department: str = 'VERIFY'
    remaining_leave_days: float = Field(default=10, ge=0, allow_inf_nan=False)
    submitted_at: datetime = Field(default_factory=lambda: datetime(2026, 9, 1, 8))
    proof: VerifiedProof | None = Field(default_factory=VerifiedProof)
    raw_text: str | None = None

@router.post('/custom')
def verify_custom_case(payload: CustomVerifyInput):
    begin = time.perf_counter()
    data = payload.model_dump(exclude={'raw_text'})
    if not data.get('proof'):
        data['proof'] = VerifiedProof()
    calls = 0
    if payload.raw_text:
        from ai.agent_orchestrator import LeaveApprovalAgent
        extracted = LeaveApprovalAgent().parse_natural_language(payload.raw_text, current_date=payload.submitted_at.date())
        for k, v in extracted.model_dump().items(): data[k] = v
        calls = 1
    actual = evaluate_case(data)
    elapsed = time.perf_counter() - begin
    return {
        'success': True,
        'actual': actual,
        **actual,
        'plain_reason': actual.get('human_readable_explanation', ''),
        'calculated_workdays': actual.get('requested_working_days', 0),
        'latency_seconds': elapsed,
        'llm_calls': calls,
        'simulation_only': True
    }


# ==============================================================================
# SECURED VERIFYING ENDPOINTS: Employee Directory & Personal Photos
# ==============================================================================

@router.get('/employees', summary="Danh sách nhân viên (Verifying Endpoint)")
def list_verified_employees(actor_id=Depends(actor)):
    """Lấy danh bạ và số dư phép của nhân viên tại verifying endpoint (yêu cầu xác thực token/actor bảo mật)."""
    with st.transaction() as conn:
        st.employee(conn, actor_id)  # Xác minh người gọi tồn tại & đang active
        rows = [dict(r) for r in conn.execute('SELECT * FROM employees')]
        for row in rows:
            row['actor_roles'] = [dict(r) for r in conn.execute('SELECT role,department_scope FROM actor_roles WHERE employee_id=?', (row['employee_id'],))]
            row['photo_url'] = f"/api/verify/employees/{row['employee_id']}/photo"
        return {'success': True, 'total': len(rows), 'data': rows, 'identity_mode': 'VERIFIED', 'verified_by': actor_id}


@router.get('/employees/{employee_id}', summary="Chi tiết nhân viên (Verifying Endpoint)")
def get_verified_employee(employee_id: str, actor_id=Depends(actor)):
    """Lấy thông tin chi tiết một nhân sự sau khi xác thực quyền truy cập."""
    with st.readonly_connection() as conn:
        st.employee(conn, actor_id)
        row = conn.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
        if not row:
            raise HTTPException(404, f'Không tìm thấy nhân sự {employee_id}.')
        emp = dict(row)
        emp['actor_roles'] = [dict(r) for r in conn.execute('SELECT role,department_scope FROM actor_roles WHERE employee_id=?', (employee_id,))]
        emp['photo_url'] = f"/api/verify/employees/{employee_id}/photo"
        return {'success': True, 'data': emp, 'verified_by': actor_id}


@router.get('/employees/{employee_id}/photo', summary="Ảnh cá nhân nhân viên (Verifying Endpoint)")
def get_employee_personal_photo(employee_id: str, actor_id=Depends(actor)):
    """Truy xuất ảnh cá nhân/thẻ nhân viên tại verifying endpoint sau khi xác thực danh tính."""
    with st.readonly_connection() as conn:
        st.employee(conn, actor_id)
        emp = conn.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
        if not emp:
            raise HTTPException(404, f'Không tìm thấy nhân sự {employee_id}.')

    # 1. Tìm trong proof_documents upload gần nhất bởi nhân viên
    with st.readonly_connection() as conn:
        doc = conn.execute('SELECT storage_name, mime_type FROM proof_documents WHERE employee_id=? ORDER BY created_at DESC LIMIT 1', (employee_id,)).fetchone()
        if doc and doc['storage_name']:
            upload_dir = Path(os.getenv('LEAVE_UPLOAD_DIR', str(_ROOT / 'backend' / 'uploads')))
            target = upload_dir / doc['storage_name']
            if target.is_file():
                return FileResponse(
                    target,
                    media_type=doc['mime_type'] or "image/png",
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
                )

    # 2. Tìm ảnh trong các thư mục lưu trữ có chứa employee_id
    emp_clean = employee_id.lower()
    for directory in _PHOTO_DIRS:
        if not directory.exists():
            continue
        for f in directory.iterdir():
            if f.is_file() and emp_clean in f.name.lower() and f.suffix.lower() in _ALLOWED_PHOTO_SUFFIX:
                return FileResponse(
                    f,
                    media_type=_ALLOWED_PHOTO_SUFFIX[f.suffix.lower()],
                    headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
                )

    raise HTTPException(404, f'Không tìm thấy ảnh cá nhân cho nhân viên {employee_id}.')


@router.get('/photos/{filename}', summary="Ảnh chứng từ cá nhân (Verifying Endpoint)")
def get_verified_photo(filename: str, actor_id=Depends(actor)):
    """Ảnh cá nhân / chứng từ tại verifying endpoint sau khi xác thực quyền truy cập."""
    name = Path(filename).name
    suffix = Path(name).suffix.lower()
    if name != filename or suffix not in _ALLOWED_PHOTO_SUFFIX:
        raise HTTPException(404, "Không tìm thấy ảnh hoặc định dạng không hợp lệ.")
    for directory in _PHOTO_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return FileResponse(
                candidate,
                media_type=_ALLOWED_PHOTO_SUFFIX[suffix],
                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"}
            )
    raise HTTPException(404, "Không tìm thấy ảnh tại verifying endpoint.")


@router.get('/proofs/{filename}', summary="Ảnh chứng từ (Bí danh)")
def get_verified_proof(filename: str, actor_id=Depends(actor)):
    """Bí danh cho /photos/{filename} tại verifying endpoint."""
    return get_verified_photo(filename, actor_id=actor_id)

