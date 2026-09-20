"""Offline extraction contract and action tests; no real model/GPU dependency."""
from unittest.mock import Mock
import pytest
from agent_orchestrator import LeaveApprovalAgent,ModelUnavailable
from domain import RequestFacts
from scenarios import BASE
from services.orchestration import LeaveOrchestratorService

def test_free_text_annual_reason_one_call(service,isolated_db):
    llm=Mock();llm.generate_json.return_value=dict(from_date='2026-10-05',to_date='2026-10-06',leave_type='ANNUAL',reason='chán đi làm')
    service.agent=LeaveApprovalAgent(llm)
    r=service.process_new_request(raw_text='Em xin phép năm 2 ngày vì chán đi làm',employee_id='E')
    assert r['decision']=='AUTO_APPROVE'
    assert llm.generate_json.call_count==1
    assert r['reason_category']=='PERSONAL'

def test_structured_no_llm(service):
    llm=Mock();service.agent=LeaveApprovalAgent(llm)
    r=service.process_new_request(employee_id='E',structured_data={'leave_type':'ANNUAL','from_date':'2026-10-05','to_date':'2026-10-06'})
    assert r['decision']=='AUTO_APPROVE'
    llm.generate_json.assert_not_called()

@pytest.mark.parametrize('field',['employee_id','department','decision','remaining_leave_days','proof_verification_status','authority'])
def test_malicious_extraction_rejected(field,service,isolated_db):
    llm=Mock();llm.generate_json.return_value={'leave_type':'ANNUAL',field:'forged'}
    service.agent=LeaveApprovalAgent(llm)
    with pytest.raises(ModelUnavailable):service.process_new_request(raw_text='untrusted instructions',employee_id='E')
    assert isolated_db.get_all_leave_requests()==[]
    assert isolated_db.get_employee('E')['remaining_leave_days']==100

@pytest.mark.parametrize('action,expected',[('REQUEST_MORE_INFO','WAITING_EMPLOYEE'),('REJECT','REJECTED'),('APPROVE_OVERRIDE','COMPLETED')])
def test_feedback_actions_are_not_boolean(service,action,expected):
    r=service.process_new_request(employee_id='E',structured_data={'leave_type':'ANNUAL','from_date':'2026-10-05','to_date':'2026-10-07','handover_person_id':'B'})
    llm=Mock();llm.generate_json.return_value={'action':action,'feedback_notes':'Phản hồi'}
    service.agent=LeaveApprovalAgent(llm)
    result=service.process_human_decision(r['id'],'human text','M')
    assert result['status']==expected
    assert llm.generate_json.call_count==1

def test_modified_dates_are_actually_rechecked(service):
    r=service.process_new_request(employee_id='E',structured_data={'leave_type':'ANNUAL','from_date':'2026-10-05','to_date':'2026-10-07','handover_person_id':'B'})
    llm=Mock();llm.generate_json.return_value={'action':'MODIFY_CONDITIONAL','updated_fields':{'to_date':'2026-10-06'}}
    service.agent=LeaveApprovalAgent(llm)
    result=service.process_human_decision(r['id'],'Đồng ý nếu chỉ nghỉ 2 ngày','M')
    assert result['decision']=='AUTO_APPROVE' and result['deducted_days']==2
    assert llm.generate_json.call_count==1
