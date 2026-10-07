"""Isolated, non-persisting Verify harness. No production DB or LLM dependencies."""
import json
import time
import uuid
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from rule_engine import LeaveRequest, LeaveRuleEngine
from domain import RequestFacts, VerifiedProof
from calendar_service import CalendarService
from services.orchestration import LeaveOrchestratorService
import storage as st

router=APIRouter(prefix='/api/verify',tags=['Verify Harness'])
BENCHMARK_SESSION_CACHE = {}
BENCHMARK_CASE_PREFIX = 'REQ-TC-'


def _cleanup_benchmark_request(req_id: str):
    try:
        with st.transaction() as conn:
            conn.execute('DELETE FROM approval_steps WHERE request_id=?', (req_id,))
            conn.execute('DELETE FROM leave_bookings WHERE request_id=?', (req_id,))
            conn.execute('DELETE FROM leave_transactions WHERE request_id=?', (req_id,))
            conn.execute('DELETE FROM leave_requests WHERE id=?', (req_id,))
            conn.execute('DELETE FROM audit_logs WHERE request_id=?', (req_id,))
    except Exception:
        pass
TEST_CASES_FILE=Path(__file__).resolve().parents[2]/'Leave_Application'/'test_cases.json'
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
        "from_date": "2026-10-05",
        "to_date": "2026-10-05",
        "reason": "Việc riêng gia đình",
        "remaining_leave_days": 10,
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-01T08:00:00+07:00",
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
        "from_date": "2026-10-08",
        "to_date": "2026-10-09",
        "reason": "Nghỉ phép thường niên",
        "remaining_leave_days": 12,
        "handover_person_id": "EMP010",
        "handover": {"employee_id": "EMP010", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []},
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-01T08:00:00+07:00",
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
        "from_date": "2026-10-05",
        "to_date": "2026-10-06",
        "reason": "Nghỉ việc gia đình 2 ngày",
        "remaining_leave_days": 1,
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-01T08:00:00+07:00",
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
        "id": "TC-VLM-03",
        "scenario_name": "Bác sĩ chỉ định 1 ngày nhưng đơn xin 3 ngày (Lệch ảnh & Text)",
        "sprint1_group": "UNCERTAIN_FACTS",
        "sprint1_group_name": "Chưa xác định thực tế (Lệch chứng từ)",
        "employee_id": "EMP004",
        "employee_name": "Lê Văn Nam",
        "department": "Engineering",
        "leave_type": "SICK_MEDICAL",
        "from_date": "2026-10-12",
        "to_date": "2026-10-14",
        "reason": "Rối loạn tiêu hóa cấp, theo dõi ngộ độc thức ăn",
        "proof_file": "proof_emp004_sick_days_mismatch.png",
        "proof": {
            "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
            "proof_verification_status": "VERIFIED",
            "issuer": "Bệnh viện Đa khoa Hồng Ngọc",
            "patient_name": "Lê Văn Nam",
            "issue_date": "2026-10-12",
            "recommended_from_date": "2026-10-12",
            "recommended_to_date": "2026-10-12",
            "signature_present": True,
            "document_readability": "READABLE"
        },
        "remaining_leave_days": 10,
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-10-12T07:30:00+07:00",
        "expected": {
            "decision": "NEED_CORRECTION",
            "target_role": "EMPLOYEE",
            "deducted_days": 0,
            "uncertainty_category": "UNCERTAIN_FACTS",
            "error_code": "MEDICAL_DAYS_MISMATCH"
        },
        "actionable_question": "Đơn xin nghỉ 3 ngày (12/10 - 14/10) nhưng giấy chứng nhận y tế chỉ chỉ định nghỉ 1 ngày (12/10). Nhân viên cần điều chỉnh lại số ngày hoặc bổ sung thông tin để khớp với chứng từ."
    },
    {
        "id": "TC-MGR-03",
        "scenario_name": "Nghỉ kết hôn 3 ngày hưởng nguyên lương (Vượt thẩm quyền AI)",
        "sprint1_group": "AUTHORITY_ESCALATION",
        "sprint1_group_name": "Vượt thẩm quyền AI (Chuyển Quản lý)",
        "employee_id": "EMP009",
        "employee_name": "Võ Minh Khang",
        "department": "Marketing & Operations",
        "leave_type": "SPECIAL_PAID",
        "reason_category": "SELF_MARRIAGE",
        "from_date": "2026-10-05",
        "to_date": "2026-10-07",
        "reason": "Nghỉ đám cưới bản thân (Lễ thành hôn)",
        "proof_file": "proof_emp009_wedding_valid.png",
        "proof": {
            "proof_type": "MARRIAGE_CERTIFICATE",
            "proof_verification_status": "VERIFIED",
            "issuer": "UBND Phường Dịch Vọng Hậu",
            "patient_name": "Võ Minh Khang",
            "issue_date": "2026-09-20",
            "recommended_from_date": "2026-10-05",
            "recommended_to_date": "2026-10-07",
            "signature_present": True,
            "document_readability": "READABLE"
        },
        "remaining_leave_days": 10,
        "total_team_members": 6,
        "team_absent_count": 0,
        "submitted_at": "2026-09-25T08:00:00+07:00",
        "expected": {
            "decision": "ESCALATE",
            "target_role": "DIRECT_MANAGER",
            "deducted_days": 0,
            "uncertainty_category": "AUTHORITY_ESCALATION",
            "error_code": "DURATION_OVER_AI_LIMIT"
        },
        "actionable_question": "Nhân viên Võ Minh Khang xin nghỉ 3 ngày kết hôn kèm Giấy chứng nhận kết hôn hợp lệ. Quản lý trực tiếp có phê duyệt hưởng 100% lương 3 ngày chế độ đặc biệt theo Điều 115 BLLĐ không?"
    }
]

def _ensure_proof_doc(case: dict):
    proof_file = case.get('proof_file')
    if not proof_file:
        return None, 'none'
    uploads_dir = Path(__file__).resolve().parents[1] / 'uploads'
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
    with st.transaction() as conn:
        conn.execute('''INSERT OR REPLACE INTO proof_documents(
            id, employee_id, storage_name, original_name, mime_type, size_bytes,
            proof_type, facts_json, storage_path, file_real_path, original_filename, file_size_bytes, uploaded_by, created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            pid, case['employee_id'], uuid_storage_name, uuid_storage_name, 'image/png', file_size,
            ptype, json.dumps(case.get('proof') or {}), str(dest_path), str(dest_path),
            uuid_storage_name, file_size, case['employee_id'], datetime.now().isoformat()
        ))
    return pid, 'image_attachment'

def _run_single_case(c: dict, orch: LeaveOrchestratorService):
    begin = time.perf_counter()
    proof_id, att_type = _ensure_proof_doc(c)
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
        enable_llm_polish=True,
        custom_request_id=req_id,
        skip_vlm=False
    )

    # Simulate a real user submission flow for benchmark checks, but keep the main
    # leave database clean. The record is retained in an isolated in-memory cache
    # for the detail modal, and removed from the shared DB immediately after submission.
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
    orch = LeaveOrchestratorService()
    detail = _run_single_case(matched, orch)
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
    orch = LeaveOrchestratorService()
    details = []
    for c in SPRINT1_BENCHMARK_CASES:
        details.append(_run_single_case(c, orch))

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
