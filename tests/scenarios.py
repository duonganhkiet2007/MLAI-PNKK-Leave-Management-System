"""Independent policy expectations, shared with Verify (never computed from engine)."""
from copy import deepcopy
BASE=dict(employee_id='E',employee_name='Nguyễn Văn An',department='Engineering',remaining_leave_days=100,
    submitted_at='2026-09-01T08:00:00+07:00',from_date='2026-10-05',to_date='2026-10-06',leave_type='ANNUAL',reason='Việc riêng',
    handover_person_id='B',handover=dict(employee_id='B',department='Engineering',status='ACTIVE',absent_dates=[]),total_team_members=12)
PROOF=dict(proof_type='MEDICAL_LEAVE_CERTIFICATE',proof_verification_status='VERIFIED',verified_by='HR',issuer='Hospital',
    patient_name='Nguyễn Văn An',issue_date='2026-10-04',recommended_from_date='2026-10-05',recommended_to_date='2026-10-06',
    signature_present=True,document_readability='READABLE')
FIELDS=('decision','target_role','requested_working_days','deducted_days','annual_balance_change','uncertainty_category','error_code')
def case(id,name,changes,decision='AUTO_APPROVE',target=None,days=2,deduct=0,cat=None,error=None,harness=False):
    data=deepcopy(BASE);data.update(changes)
    expected=dict(zip(FIELDS,(decision,target,days,deduct,-deduct if deduct else 0,cat,error)))
    return dict(id=f'TC{id:02}',scenario_name=name,request=data,expected=expected,is_verify_harness=harness)
C='UNCERTAIN_FACTS';O='OUT_OF_POLICY';A='AUTHORITY_ESCALATION'
CASES=[
case(1,'Annual 2 ngày',{},deduct=2,harness=True),
case(2,'Annual vượt balance',{'remaining_leave_days':1},'AUTO_REJECT','EMPLOYEE',cat=O,error='BALANCE_EXCEEDED'),
case(3,'Annual thiếu ngày',{'from_date':None},'NEED_CORRECTION','EMPLOYEE',days=None,cat=C,error='DATE_MISSING'),
case(4,'Annual 3–5 ngày',{'to_date':'2026-10-07'},'ESCALATE','DIRECT_MANAGER',days=3,cat=A,error='DURATION_OVER_AI_LIMIT',harness=True),
case(5,'Annual 6–19 ngày',{'to_date':'2026-10-12'},'ESCALATE','DEPARTMENT_HEAD',days=6,cat=A,error='DURATION_OVER_MANAGER_LIMIT'),
case(6,'Annual >=20 ngày',{'to_date':'2026-10-30'},'ESCALATE','CEO',days=20,cat=A,error='DURATION_OVER_MANAGER_LIMIT'),
case(7,'Public holiday',{'from_date':'2026-04-30','to_date':'2026-04-30'},'NO_LEAVE_REQUIRED',days=0,error='DAY_ALREADY_NON_WORKING'),
case(8,'Range chứa holiday',{'submitted_at':'2026-04-01T08:00:00+07:00','from_date':'2026-04-29','to_date':'2026-05-02'},days=1,deduct=1),
case(9,'Friday–Monday',{'from_date':'2026-10-09','to_date':'2026-10-12'},deduct=2,harness=True),
case(10,'Chỉ weekend',{'from_date':'2026-10-10','to_date':'2026-10-11'},'NO_LEAVE_REQUIRED',days=0,error='DAY_ALREADY_NON_WORKING'),
case(11,'Self marriage',{'leave_type':'SPECIAL_PAID','reason_category':'SELF_MARRIAGE','to_date':'2026-10-07','proof':{**PROOF,'proof_type':'MARRIAGE_CERTIFICATE'}},'ESCALATE','DIRECT_MANAGER',days=3,cat=A,error='DURATION_OVER_AI_LIMIT'),
case(12,'Child marriage',{'leave_type':'SPECIAL_PAID','reason_category':'CHILD_MARRIAGE','to_date':'2026-10-05','proof':{**PROOF,'proof_type':'WEDDING_INVITATION'}},'ESCALATE','DIRECT_MANAGER',days=1,cat=A,error='DURATION_OVER_AI_LIMIT'),
case(13,'Parent death',{'leave_type':'SPECIAL_PAID','reason_category':'PARENT_DEATH','to_date':'2026-10-07','proof':{**PROOF,'proof_type':'DEATH_CERTIFICATE'}},'ESCALATE','DIRECT_MANAGER',days=3,cat=A,error='DURATION_OVER_AI_LIMIT'),
case(14,'Grandparent death',{'leave_type':'STATUTORY_UNPAID','reason_category':'GRANDPARENT_DEATH','to_date':'2026-10-05'},'ESCALATE','DIRECT_MANAGER',days=1,cat=A,error='DURATION_OVER_AI_LIMIT'),
case(15,'Sick valid proof',{'leave_type':'SICK_MEDICAL','proof':PROOF},'AUTO_APPROVE',None,days=2,cat=None,error=None),
case(16,'Sick missing proof',{'leave_type':'SICK_MEDICAL'},'NEED_CORRECTION','EMPLOYEE',cat=C,error='PROOF_MISSING'),
case(17,'Unreadable proof',{'leave_type':'SICK_MEDICAL','proof':{**PROOF,'document_readability':'ILLEGIBLE'}},'ESCALATE','DIRECT_MANAGER',cat=A,error='DOC_ILLEGIBLE'),
case(18,'Medical period mismatch',{'leave_type':'SICK_MEDICAL','proof':{**PROOF,'recommended_to_date':'2026-10-05'}},'NEED_CORRECTION','EMPLOYEE',cat=C,error='MEDICAL_DAYS_MISMATCH'),
case(19,'Handover missing',{'to_date':'2026-10-07','handover_person_id':None,'handover':None},'NEED_CORRECTION','EMPLOYEE',days=3,cat=C,error='HANDOVER_REQUIRED'),
case(20,'Handover invalid',{'handover_person_id':'E','handover':{'employee_id':'E','department':'Engineering','status':'ACTIVE'}},'NEED_CORRECTION','EMPLOYEE',cat=C,error='HANDOVER_INVALID'),
case(21,'Quota exceeded',{'team_absent_count':4},'ESCALATE','DIRECT_MANAGER',cat=O,error='TEAM_QUOTA_EXCEEDED'),
case(22,'Duplicate',{'approved_working_dates':['2026-10-05','2026-10-06']},'AUTO_REJECT','EMPLOYEE',cat=O,error='REQUEST_ALREADY_COVERED'),
case(23,'Partial overlap',{'approved_working_dates':['2026-10-05']},'NEED_CORRECTION','EMPLOYEE',cat=C,error='OVERLAPPING_REQUEST'),
case(24,'Maternity',{'leave_type':'MATERNITY'},'ESCALATE','HR',cat=O,error='AUTOMATION_SCOPE_UNSUPPORTED'),
case(25,'Work accident',{'leave_type':'WORK_ACCIDENT'},'ESCALATE','HR',cat=O,error='AUTOMATION_SCOPE_UNSUPPORTED'),
case(26,'Probation employee',{'employment_status':'PROBATION'},'NEED_CORRECTION','EMPLOYEE',cat=C,error='PROBATION_ANNUAL_RESTRICTED'),
case(27,'Annual chán đi làm',{'reason':'Em nghỉ 2 ngày vì chán đi làm.'},deduct=2,harness=True),
case(28,'Unpaid Other <=5',{'leave_type':'UNPAID_OTHER'},'ESCALATE','DIRECT_MANAGER',cat=A,error='LONG_TERM_UNPAID',harness=True),
case(29,'Unpaid Other 6–19',{'leave_type':'UNPAID_OTHER','to_date':'2026-10-12'},'ESCALATE','DEPARTMENT_HEAD',days=6,cat=A,error='LONG_TERM_UNPAID'),
case(30,'Unpaid Other >=20',{'leave_type':'UNPAID_OTHER','to_date':'2026-10-30'},'ESCALATE','DEPARTMENT_HEAD',days=20,cat=A,error='LONG_TERM_UNPAID'),
]
