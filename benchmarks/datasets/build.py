"""Hand-authored policy expectations; never calls the evaluated system."""
import copy, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent

def build():
    base={'employee_id':'BENCH-000','employee_name':'Benchmark Person 000','department':'BENCH-TEAM',
        'remaining_leave_days':100,'employment_status':'REGULAR','total_team_members':100,
        'submitted_at':'2026-09-01T08:00:00+07:00','leave_type':'ANNUAL',
        'from_date':'2026-09-14','to_date':'2026-09-14','reason':'Synthetic personal leave'}
    medical={'proof_type':'MEDICAL_LEAVE_CERTIFICATE','issuer':'Synthetic Evaluation Clinic',
        'patient_name':'Benchmark Person 000','issue_date':'2026-09-13','recommended_from_date':'2026-09-14',
        'recommended_to_date':'2026-09-15','signature_present':True,'digital_signature_present':False,
        'document_readability':'READABLE','proof_verification_status':'VERIFIED','verified_by':'BENCH-HR'}
    def item(patch,decision,role,ref,reason,conflict=None):
        return (patch,{'decision':decision,'target_role':role},ref,reason,conflict)
    templates={
      'valid':(20,[item({},'AUTO_APPROVE',None,'policy_rules.md §3.4','One working day, sufficient balance/notice; no proof needed'),
          item({'to_date':'2026-09-15'},'AUTO_APPROVE',None,'policy_rules.md §3.4','Two working days within automatic annual limit')]),
      'balance':(10,[item({'remaining_leave_days':0},'AUTO_REJECT','EMPLOYEE','policy_rules.md §2.1, §3.4','Requested annual days exceed balance'),
          item({'remaining_leave_days':1,'to_date':'2026-09-15'},'AUTO_REJECT','EMPLOYEE','policy_rules.md §2.1','Two days exceed balance one')]),
      'notice':(10,[item({'submitted_at':'2026-09-14T08:00:00+07:00'},'ESCALATE','DIRECT_MANAGER','raw_policy.json Điều 10.1; policy_rules.md §3.4','Same-day annual notice is below one working day'),
          item({'to_date':'2026-09-17','submitted_at':'2026-09-11T08:00:00+07:00','no_handover_needed':True},'ESCALATE','DIRECT_MANAGER','raw_policy.json Điều 10.1','Four days require three working days notice')]),
      'quota':(10,[item({'total_team_members':10,'team_absent_count':3},'ESCALATE','DIRECT_MANAGER','policy_rules.md §3.4','Adding employee exceeds 30% quota'),
          item({'total_team_members':10,'team_absences_by_date':{'2026-09-14':3}},'ESCALATE','DIRECT_MANAGER','policy_rules.md §3.4','Date-specific capacity breach')]),
      'exception':(15,[item({'to_date':'2026-09-16','no_handover_needed':True},'ESCALATE','DIRECT_MANAGER','policy_rules.md §2.1, §3.4','Three annual days require manager; explicit no-work exception'),
          item({'to_date':'2026-09-21','no_handover_needed':True},'ESCALATE','DEPARTMENT_HEAD','raw_policy.json Điều 10.3; policy_rules.md §3.1/3.4','Six annual days require higher authority','§3.1 says CEO above five; raw policy says department head'),
          item({'leave_type':'MATERNITY'},'ESCALATE','HR','policy_rules.md §3.4','Out-of-automation maternity scope routed HR'),
          item({'leave_type':'WORK_ACCIDENT'},'ESCALATE','HR','policy_rules.md §3.4','Work accident routed HR'),
          item({'leave_type':'UNPAID_OTHER'},'ESCALATE','DIRECT_MANAGER','raw_policy.json Điều 18.1','Unpaid personal leave needs explicit human approval')]),
      'proof_missing_unreadable':(15,[item({'leave_type':'SICK_MEDICAL'},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §2.2, §3.4','Missing required evidence'),
          item({'leave_type':'SICK_MEDICAL','proof':{**medical,'document_readability':'UNREADABLE'}},'ESCALATE','DIRECT_MANAGER','policy_rules.md §5','Unreadable evidence needs human review'),
          item({'leave_type':'SICK_MEDICAL','proof':{**medical,'proof_verification_status':'UNVERIFIED'}},'ESCALATE','HR','policy_rules.md §3.4','Unverified new medical proof should require HR','Code permits complete unverified short medical proof; §3.4 requires verification')]),
      'proof_mismatch':(15,[item({'leave_type':'SICK_MEDICAL','proof':{**medical,'patient_name':'Entirely Different Identity'}},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §1, §2.2','Subject identity must match'),
          item({'leave_type':'SICK_MEDICAL','proof':{**medical,'recommended_from_date':'2026-09-15'}},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §1, §2.2','Requested dates outside supporting document'),
          item({'leave_type':'SICK_MEDICAL','proof':{**medical,'proof_type':'MARRIAGE_CERTIFICATE'}},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §2.2','Wrong supporting document type')]),
      'duplicate_conflict':(10,[item({'approved_working_dates':['2026-09-14']},'AUTO_REJECT','EMPLOYEE','policy_rules.md §3.4','Duplicate approved leave must not deduct twice'),
          item({'to_date':'2026-09-15','approved_working_dates':['2026-09-14']},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §3.4','Partially overlapping dates require correction')]),
      'boundary':(15,[item({'remaining_leave_days':1},'AUTO_APPROVE',None,'policy_rules.md §2.1','Exactly enough balance'),
          item({'total_team_members':10,'team_absent_count':2},'AUTO_APPROVE',None,'policy_rules.md §3.4','Exactly 30% quota','§3.4 uses <30%; code accepts ≤30%; threshold needs policy owner'),
          item({'from_date':'2026-09-19','to_date':'2026-09-20'},'NO_LEAVE_REQUIRED',None,'policy_rules.md §1; calendars/holidays_2026.json','Weekend has no working dates'),
          item({'from_date':None},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §3.4','Missing start date'),
          item({'to_date':'2026-09-13'},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §3.4','End precedes start'),
          item({'to_date':'2026-09-16'},'NEED_CORRECTION','EMPLOYEE','policy_rules.md §2.1','Three days missing handover and exception'),
          item({'employment_status':'PROBATION'},'NEED_CORRECTION','EMPLOYEE','raw_policy.json Điều 8','Probation annual restrictions'),
          item({'leave_type':'SICK_MEDICAL','to_date':'2026-09-15','proof':medical},'ESCALATE','DIRECT_MANAGER','policy_rules.md §3.1, §3.4','Two medical days require manager')])
    }
    cases=[]; truth={}
    for category,(count,variants) in templates.items():
        for i in range(count):
            patch,expected,ref,rationale,conflict=variants[i%len(variants)]
            context={**copy.deepcopy(base),**copy.deepcopy(patch)}
            id=f'{category}-{i+1:03}'
            cases.append({'id':id,'category':category,'kind':'policy','request':context,
                'variant':i%len(variants),'synthetic':True})
            truth[id]={'expected':expected,'expected_state':{'AUTO_APPROVE':'COMPLETED','AUTO_REJECT':'REJECTED',
                'NEED_CORRECTION':'WAITING_EMPLOYEE','ESCALATE':'PENDING_ESCALATION','NO_LEAVE_REQUIRED':'COMPLETED'}[expected['decision']],
                'expected_audit_events':['EVALUATED'],'policy_reference':'Leave_Application/'+ref,
                'rationale':rationale,'annotation_status':'policy_conflict' if conflict else 'independently_authored',
                'policy_conflict':conflict,'severity':'critical' if category.startswith('proof') else 'major'}
    free=[('Tôi xin nghỉ phép năm ngày 14/09/2026.',{'from_date':'2026-09-14','to_date':'2026-09-14','leave_type':'ANNUAL'}),
        ('Cho em nghỉ phép năm ngày mai nhé.',{'from_date':'2026-09-02','to_date':'2026-09-02','leave_type':'ANNUAL'}),
        ('Em xin nghỉ ốm ngày 14/09/2026.',{'from_date':'2026-09-14','leave_type':'SICK_MEDICAL'}),
        ('Em muốn nghỉ một hôm, chưa biết ngày nào.',{'date_ambiguous':True}),
        ('Tôi xin nghỉ không lương từ 14/09/2026 đến 15/09/2026.',{'from_date':'2026-09-14','to_date':'2026-09-15','leave_type':'UNPAID_OTHER'}),
        ('Tôi xin nghỉ phép năm ngày 14/09/2026, bàn giao cho Benchmark Person 001.',{'handover_person_name':'Benchmark Person 001','leave_type':'ANNUAL'})]
    replies=[('Đồng ý duyệt','APPROVE_OVERRIDE'),('Từ chối','REJECT'),('Cần bổ sung chứng từ','REQUEST_MORE_INFO'),
        ('Sửa ngày bắt đầu sang 15/09/2026','MODIFY_CONDITIONAL'),('Để tôi xem lại sau','AMBIGUOUS'),('Chưa quyết định','AMBIGUOUS'),
        ('Không đồng ý','REJECT'),('Tôi cần kiểm tra thêm','AMBIGUOUS')]
    for i in range(20):
        kind='free_text' if i<12 else 'reviewer'
        text,exp=(free[i%len(free)] if i<12 else replies[(i-12)%len(replies)])
        id=f'language-{i+1:03}'
        cases.append({'id':id,'category':'language','kind':kind,'text':text,'synthetic':True,
            'reference_time':base['submitted_at'],'timezone':'Asia/Ho_Chi_Minh'})
        truth[id]={'expected':exp,'policy_reference':'User-authored literal text / policy_rules.md §3.4 human authority',
            'annotation_status':'independently_authored','severity':'critical' if exp=='AMBIGUOUS' else 'major'}
    def write(name,obj): (HERE/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    write('applications.json',cases); write('ground_truth.json',truth)
    # Annotations describe printed synthetic source, not model output; corrupted unreadability is unlabelled.
    annotations=[]
    for i,(typ,title) in enumerate([('MEDICAL_LEAVE_CERTIFICATE','MEDICAL LEAVE CERTIFICATE'),('HOSPITAL_DISCHARGE','HOSPITAL DISCHARGE'),('MARRIAGE_CERTIFICATE','MARRIAGE CERTIFICATE')]):
        annotations.append({'id':f'doc-{i:03}','proof_type':typ,'title':title,'patient_name':f'Benchmark Person {i:03}',
            'issuer':'Synthetic Evaluation Clinic','issue_date':'2026-09-13','recommended_from_date':'2026-09-14',
            'recommended_to_date':'2026-09-15','signature_present':True,'digital_signature_present':False,
            'has_red_stamp':True,'document_readability':'READABLE','diagnosis':'Synthetic supporting reason',
            'source':'deterministic printed synthetic fixture, no real person or medical record',
            'readability_after_corruption':None})
    write('proof_annotations.json',annotations)
    write('manifest.json',{'version':'1.0','cases':len(cases),'distinct_templates':sum(len(v[1]) for v in templates.values())+len(free)+len(replies),
        'limitation':'140 cases are variations of a smaller authored template set, not 140 independent policy branches.',
        'ground_truth_source':['Leave_Application/policy_rules.md','Leave_Application/raw_policy.json'],
        'conflicts':'Conflicting policy labels are excluded from headline accuracy and retained as diagnostic observations.'})
    print(f'Generated {len(cases)} cases without importing the evaluated engine.')

if __name__=='__main__': build()
