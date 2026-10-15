from datetime import datetime
import pytest

@pytest.mark.parametrize('name,expected',[
    ('Benchmark Person 000','AUTO_APPROVE'),
    ('Entirely Different Identity','NEED_CORRECTION'),
    ('Benchmark Person 999','NEED_CORRECTION')])
def test_verified_medical_identity_match(name,expected):
    from rule_engine import LeaveRequest,LeaveRuleEngine
    from domain import VerifiedProof
    request=LeaveRequest(employee_id='BENCH-000',employee_name='Benchmark Person 000',department='BENCH-TEAM',
        remaining_leave_days=100,total_team_members=100,submitted_at=datetime.fromisoformat('2026-09-01T08:00:00+07:00'),
        leave_type='SICK_MEDICAL',from_date='2026-09-14',to_date='2026-09-14',
        proof=VerifiedProof(proof_type='MEDICAL_LEAVE_CERTIFICATE',proof_verification_status='VERIFIED',
            patient_name=name,issuer='Synthetic Clinic',issue_date='2026-09-13',signature_present=True,
            document_readability='READABLE',recommended_from_date='2026-09-14',recommended_to_date='2026-09-15'))
    assert LeaveRuleEngine.evaluate(request).decision.value==expected
