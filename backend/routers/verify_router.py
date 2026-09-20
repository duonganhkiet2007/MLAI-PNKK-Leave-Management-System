"""Isolated, non-persisting Verify harness. No production DB or LLM dependencies."""
import json
import time
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from rule_engine import LeaveRequest, LeaveRuleEngine
from domain import RequestFacts, VerifiedProof
from calendar_service import CalendarService

router=APIRouter(prefix='/api/verify',tags=['Verify Harness'])
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

class CustomVerifyInput(RequestFacts):
    employee_id: str = 'VERIFY_EMPLOYEE'
    employee_name: str = 'Nhân sự kiểm thử'
    department: str = 'VERIFY'
    remaining_leave_days: float = Field(default=10,ge=0,allow_inf_nan=False)
    submitted_at: datetime = datetime(2026,9,1,8)
    team_absent_count: int = Field(default=0,ge=0)
    total_team_members: int = Field(default=10,ge=1)
    handover: dict | None = None
    proof: VerifiedProof = Field(default_factory=VerifiedProof)
    raw_text: str | None = None

@router.post('/custom')
def verify_custom_case(payload: CustomVerifyInput):
    begin=time.perf_counter()
    data=payload.model_dump(exclude={'raw_text'})
    calls=0
    if payload.raw_text:
        from agent_orchestrator import LeaveApprovalAgent
        extracted=LeaveApprovalAgent().parse_natural_language(payload.raw_text,current_date=payload.submitted_at.date())
        for k,v in extracted.model_dump().items(): data[k]=v
        calls=1
    actual=evaluate_case(data)
    return {'success':True,**actual,'plain_reason':actual['human_readable_explanation'],
        'calculated_workdays':actual['requested_working_days'],'latency_seconds':time.perf_counter()-begin,
        'llm_calls':calls,'simulation_only':True}
