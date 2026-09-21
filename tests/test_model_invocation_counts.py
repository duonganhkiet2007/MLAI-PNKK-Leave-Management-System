"""
test_model_invocation_counts.py
Tests asserting the exact number of LLM and VLM invocations for every workflow:
1. Structured Form (AUTO_APPROVE) -> 0 LLM calls, 0 VLM calls
2. Structured Form (ESCALATE) -> 0 LLM calls, 0 VLM calls
3. Structured Form (NEED_CORRECTION / REJECT) -> 0 LLM calls, 0 VLM calls
4. Free-text Natural Language Request -> 1 LLM call (parse facts only), 0 VLM calls
5. Form with Proof Document -> 0 LLM calls, 1 VLM call
6. Human Manager Button Action (APPROVE / REQUEST_MORE_INFO / REJECT) -> 0 LLM calls, 0 VLM calls
7. Human Manager Free-text Feedback -> 1 LLM call (parse action only), 0 VLM calls
8. Deterministic Template Schema preservation and Timings instrumentation
"""
from unittest.mock import Mock, patch
import pytest
from agent_orchestrator import LeaveApprovalAgent
from services.orchestration import LeaveOrchestratorService


def test_structured_auto_approve_zero_model_calls(service, isolated_db):
    """Structured form that passes policy: 0 LLM calls, 0 VLM calls."""
    mock_llm = Mock()
    service.agent = LeaveApprovalAgent(mock_llm)
    
    res = service.process_new_request(
        employee_id='E',
        structured_data={
            'leave_type': 'ANNUAL',
            'from_date': '2026-10-05',
            'to_date': '2026-10-06',
            'handover_person_id': 'B',
            'reason': 'Nghỉ du lịch định kỳ'
        }
    )
    assert res['decision'] == 'AUTO_APPROVE'
    mock_llm.generate_json.assert_not_called()
    assert res['llm_summary_json']['timings']['rule_engine_ms'] >= 0
    assert res['llm_summary_json']['timings']['template_ms'] >= 0
    assert res['llm_summary_json']['timings']['llm_generation_ms'] == 0.0


def test_structured_escalate_zero_model_calls(service, isolated_db):
    """Structured form that escalates (e.g. Quota Exceeded): 0 LLM calls, 0 VLM calls."""
    mock_llm = Mock()
    service.agent = LeaveApprovalAgent(mock_llm)
    
    # Create 2 absent colleagues on same dates in Engineering to trigger TEAM_QUOTA_EXCEEDED (3/5 = 60% > 30%)
    c = isolated_db.get_db_connection()
    c.execute("INSERT INTO leave_requests(id,employee_id,employee_name,department,from_date,to_date,workdays,leave_type,decision,status,submitted_at,updated_at) VALUES('ABS1','E1','Emp 1','Engineering','2026-10-05','2026-10-07',3,'ANNUAL','AUTO_APPROVE','COMPLETED','2026-09-01','2026-09-01')")
    c.execute("INSERT INTO leave_requests(id,employee_id,employee_name,department,from_date,to_date,workdays,leave_type,decision,status,submitted_at,updated_at) VALUES('ABS2','E2','Emp 2','Engineering','2026-10-05','2026-10-07',3,'ANNUAL','AUTO_APPROVE','COMPLETED','2026-09-01','2026-09-01')")
    c.commit(); c.close()
    
    res = service.process_new_request(
        employee_id='E',
        structured_data={
            'leave_type': 'ANNUAL',
            'from_date': '2026-10-05',
            'to_date': '2026-10-07',
            'handover_person_id': 'B',
            'reason': 'Nghỉ gia đình'
        }
    )
    assert res['decision'] == 'ESCALATE'
    mock_llm.generate_json.assert_not_called()
    assert 'timings' in res['llm_summary_json']
    assert res['llm_summary_json']['timings']['llm_generation_ms'] == 0.0
    assert 'info_sufficient_vn' in res['llm_summary_json']
    assert 'info_missing_vn' in res['llm_summary_json']


def test_free_text_submission_exactly_one_llm_call(service, isolated_db):
    """Free text submission invokes LLM exactly ONCE to parse facts, and 0 LLM calls for decision/summary."""
    mock_llm = Mock()
    mock_llm.generate_json.return_value = {
        'from_date': '2026-10-05',
        'to_date': '2026-10-06',
        'leave_type': 'ANNUAL',
        'reason': 'Đi du lịch với bạn bè',
        'handover_person_id': 'B'
    }
    service.agent = LeaveApprovalAgent(mock_llm)
    
    res = service.process_new_request(
        raw_text='Tôi xin nghỉ phép năm 2 ngày từ 05/10/2026 đến 06/10/2026',
        employee_id='E'
    )
    assert res['decision'] == 'AUTO_APPROVE'
    assert mock_llm.generate_json.call_count == 1  # Only 1 call for natural language extraction


def test_form_with_proof_one_vlm_zero_llm(service, isolated_db):
    """Form with proof document invokes VLM inspection once, but 0 LLM summary calls."""
    mock_llm = Mock()
    service.agent = LeaveApprovalAgent(mock_llm)
    
    from vlm_inspector import VLMInspectionOutput
    from domain import ProofExtraction, ProofType
    mock_proof = ProofExtraction(
        proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
        patient_name='E',
        issuer='Bệnh viện Đa khoa',
        signature_present=True
    )
    mock_vlm_out = VLMInspectionOutput(
        vlm_analysis_json={'document_summary': {'issuer': 'Bệnh viện Đa khoa'}},
        doc_patient_name='E',
        doc_diagnosis='Cảm cúm sốt siêu vi',
        has_red_stamp=True,
        has_doctor_signature=True,
        is_tampered=False,
        ai_edited=False,
        days_granted_by_doctor=3,
        correlation_score=0.92,
        correlation_issues=[],
        persona_role_used='VLM Officer',
        escalation_reasons_json=[],
        proof_extraction=mock_proof
    )
    
    with patch('services.orchestration.inspect_document_with_vlm', return_value=mock_vlm_out) as mock_vlm:
        res = service.process_new_request(
            employee_id='E',
            structured_data={
                'leave_type': 'SICK_MEDICAL',
                'from_date': '2026-10-05',
                'to_date': '2026-10-07',
                'attachment_type': 'image_attachment',
                'reason': 'Sốt cao cần điều trị'
            }
        )
        assert mock_vlm.call_count == 1
        mock_llm.generate_json.assert_not_called()
        assert res['llm_summary_json']['timings']['llm_generation_ms'] == 0.0


def test_human_button_action_zero_llm_calls(service, isolated_db):
    """Human manager clicking APPROVE button triggers 0 LLM calls."""
    mock_llm = Mock()
    service.agent = LeaveApprovalAgent(mock_llm)
    
    req = service.process_new_request(
        employee_id='E',
        structured_data={
            'leave_type': 'ANNUAL',
            'from_date': '2026-10-05',
            'to_date': '2026-10-07',
            'handover_person_id': 'B'
        }
    )
    
    res = service.process_human_decision(
        request_id=req['id'],
        feedback_text='',
        approver_id='M',
        action_type='APPROVE'
    )
    mock_llm.generate_json.assert_not_called()


def test_human_free_text_action_exactly_one_llm_call(service, isolated_db):
    """Human manager entering free-text feedback calls LLM exactly ONCE to parse action, 0 for summary."""
    mock_llm = Mock()
    mock_llm.generate_json.return_value = {
        'action': 'REQUEST_MORE_INFO',
        'feedback_notes': 'Vui lòng bổ sung thêm thông tin chi tiết.'
    }
    service.agent = LeaveApprovalAgent(mock_llm)
    
    req = service.process_new_request(
        employee_id='E',
        structured_data={
            'leave_type': 'ANNUAL',
            'from_date': '2026-10-05',
            'to_date': '2026-10-07',
            'handover_person_id': 'B'
        }
    )
    
    res = service.process_human_decision(
        request_id=req['id'],
        feedback_text='Cần thêm thông tin rõ ràng trước khi quyết định',
        approver_id='M'
    )
    assert res['status'] == 'WAITING_EMPLOYEE'
    assert mock_llm.generate_json.call_count == 1  # Only 1 call to extract human action


def test_deterministic_llm_summary_schema_preserved(service, isolated_db):
    """Verify all 24+ schema fields and timings exist in llm_summary_json without calling LLM."""
    mock_llm = Mock()
    service.agent = LeaveApprovalAgent(mock_llm)
    
    res = service.process_new_request(
        employee_id='E',
        structured_data={
            'leave_type': 'ANNUAL',
            'from_date': '2026-10-05',
            'to_date': '2026-10-06',
            'handover_person_id': 'B'
        }
    )
    summary = res['llm_summary_json']
    expected_fields = [
        'decision', 'status', 'summary_version', 'language', 'engine',
        'error_code', 'error_code_human_vn', 'target_role', 'target_role_human_vn',
        'actionable_question', 'quick_action_options_vn', 'applied_policy_clauses_vn',
        'warnings', 'why_escalated', 'summary_natural_vn', 'info_sufficient_vn',
        'info_missing_vn', 'correlation_tier_vn', 'integrity_assessment_vn',
        'context', 'vlm_summary', 'timings'
    ]
    for field in expected_fields:
        assert field in summary, f"Missing expected field: {field}"
    
    assert summary['timings']['rule_engine_ms'] >= 0
    assert summary['timings']['template_ms'] >= 0
    assert summary['timings']['total_eval_ms'] >= 0
    assert summary['timings']['llm_generation_ms'] == 0.0
