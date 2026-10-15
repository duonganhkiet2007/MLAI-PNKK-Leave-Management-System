"""API and database regression tests. Fixtures isolate every test from production."""
import json
import sqlite3
from copy import deepcopy
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import pytest
from scenarios import CASES,BASE,PROOF,FIELDS
from domain import RequestFacts,VerifiedProof
from storage import Conflict,AccessDenied

def payload(**changes):
    # Mặc định không có người bàn giao: các test không liên quan bàn giao không dừng ở PENDING_HANDOVER.
    base={k:v for k,v in BASE.items() if k in RequestFacts.model_fields}
    base.update(handover_person_id=None,handover_person_name=None,no_handover_needed=True)
    return {**base,**changes}

def proof_fixture(db,data,owner='E'):
    p=VerifiedProof(**data)
    c=db.get_db_connection()
    c.execute("INSERT INTO proof_documents(id,employee_id,storage_name,original_name,mime_type,size_bytes,proof_type,facts_json,created_at) VALUES('p',?,'p.pdf','p.pdf','application/pdf',10,?,?,?)",
              (owner,p.proof_type.value,p.model_dump_json(),'2026-09-01'))
    c.commit();c.close();return 'p'

def legacy_approval(db,id,employee,dates,department='Engineering'):
    c=db.get_db_connection()
    c.execute('''INSERT INTO leave_requests(id,employee_id,employee_name,department,from_date,to_date,workdays,leave_type,decision,status,submitted_at,updated_at)
        VALUES(?,?,?, ?,?,?,?,'Annual','AUTO_APPROVE','COMPLETED','2026-01-01','2026-01-01')''',
        (id,employee,employee,department,min(dates),max(dates),len(dates)))
    c.commit();c.close()

@pytest.mark.parametrize('case',CASES,ids=lambda c:c['id'])
def test_30_scenarios_persist_real_balance(case,isolated_db,service):
    db=isolated_db;raw=deepcopy(case['request']);data={k:v for k,v in raw.items() if k in RequestFacts.model_fields}
    c=db.get_db_connection()
    c.execute('UPDATE employees SET remaining_leave_days=?,employment_status=? WHERE employee_id=\'E\'',(raw['remaining_leave_days'],raw.get('employment_status','REGULAR')))
    c.commit();c.close()
    if raw.get('proof'):
        proof_id=proof_fixture(db,raw['proof'])
        data['proof_id']=proof_id
        if case['id']=='TC11':
            proof=raw['proof']
            vlm_json={
                'inspector_persona':'Chuyên viên xác minh hôn sự',
                'inspection_mode':'OLLAMA_REAL_QWEN25_VL_3B',
                '_inspection_context':{'leave_type':'SPECIAL_PAID','reason_category':'SELF_MARRIAGE'},
                'document_summary':{
                    'patient_name':proof['subject_name'],
                    'issuer':proof['issuer'],
                    'issue_date':proof['issue_date'],
                    'doctor_recommended_range':{'from':None,'to':None,'days':None},
                    'subject_name':proof['subject_name'],
                    'partner_name':proof['partner_name'],
                    'event_type':proof['event_type'],
                    'wedding_date':proof['wedding_date'],
                },
                'flags':{
                    'has_red_stamp':proof['has_red_stamp'],
                    'has_doctor_signature':False,
                    'signature_present_on_scan':proof['signature_present'],
                    'document_readability':proof['document_readability'],
                    'is_tampered':proof['is_tampered'],
                    'ai_generated_or_edited':proof['ai_edited'],
                },
                'correlation_analysis':{'score':None,'issues':[],'requested_workdays':3},
                'escalation_flags':[],
                'raw_fields_detected':['subject_name','partner_name','event_type','wedding_date'],
            }
            c=db.get_db_connection()
            c.execute("UPDATE proof_documents SET inspection_status='READY',vlm_analysis_json=? WHERE id=?",
                      (json.dumps(vlm_json,ensure_ascii=False),proof_id))
            c.commit();c.close()
    if raw.get('approved_working_dates'): legacy_approval(db,'OLD','E',raw['approved_working_dates'])
    for i in range(raw.get('team_absent_count',0)):
        legacy_approval(db,f'ABS{i}',f'E{i}',['2026-10-05','2026-10-06'])
    service.clock=lambda:datetime.fromisoformat(raw['submitted_at'])
    before=db.get_employee('E')['remaining_leave_days']
    r=service.process_new_request(employee_id='E',structured_data=data)
    if r['status']=='PENDING_HANDOVER':  # người nhận bàn giao chấp nhận thì mới ghi nhận/trừ phép
        r=service.confirm_handover(r['id'],data['handover_person_id'],'ACCEPT')
    assert {k:r[k] for k in FIELDS}==case['expected']
    assert db.get_employee('E')['remaining_leave_days']-before==case['expected']['annual_balance_change']

def test_handover_required_from_3_days_with_bypass(service,isolated_db):
    three=dict(to_date='2026-10-07')
    r=service.process_new_request(employee_id='E',structured_data=payload(**three,no_handover_needed=False))
    assert (r['decision'],r['error_code'])==('NEED_CORRECTION','HANDOVER_REQUIRED')
    ok=service.process_new_request(employee_id='E',structured_data=payload(**three,no_handover_needed=True))
    assert ok['decision']=='ESCALATE' or ok['status']=='COMPLETED'
    assert any('bàn giao' in w for w in (ok.get('warnings') or ok.get('result_json',{}).get('warnings',[])))

def test_form_no_model_and_protected_context(client,isolated_db):
    r=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload())
    assert r.status_code==200,r.text
    assert r.json()['data']['decision']=='AUTO_APPROVE'
    for protected in ['decision','remaining_leave_days','department','team_absent_count','proof_verification_status']:
        response=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload(**{protected:100}))
        assert response.status_code==422
    assert isolated_db.get_employee('E')['remaining_leave_days']==98


def test_analysis_uses_vietnamese_labels(client):
    r=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload())
    assert r.status_code==200,r.text
    request_id=r.json()['data']['id']
    res=client.get(f'/api/leave/{request_id}/analysis',headers={'X-Actor-ID':'E'})
    assert res.status_code==200,res.text
    analysis=res.json()
    label_text=json.dumps(analysis['vlm_fields_labels'], ensure_ascii=False)
    assert 'Correlation score' not in label_text
    assert 'Mức độ khớp nội dung' in label_text or 'độ khớp nội dung' in label_text.lower()
    nodes={node['stage']:node for node in analysis['decision_tree_checklist']}
    assert 'TEAM_QUOTA' in nodes
    assert 'Số dư phép hiện tại trước khi trừ: 100 ngày' in nodes['BALANCE']['note']
    assert nodes['TEAM_QUOTA']['status']=='PASS'
    assert '1 / 12 người nghỉ (8,3%) < Giới hạn 30%' == nodes['TEAM_QUOTA']['note']

def test_analysis_flags_team_quota_above_30_percent(client,isolated_db):
    for index in range(3):
        legacy_approval(isolated_db,f'ABS{index}',f'EMP{index}', ['2026-10-05'])
    response=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},
        json=payload(from_date='2026-10-05',to_date='2026-10-05'))
    assert response.status_code==200,response.text
    request_id=response.json()['data']['id']
    analysis=client.get(f'/api/leave/{request_id}/analysis',headers={'X-Actor-ID':'E'})
    assert analysis.status_code==200,analysis.text
    nodes={node['stage']:node for node in analysis.json()['decision_tree_checklist']}
    assert nodes['TEAM_QUOTA']['status']=='WARN'
    assert '4 / 12 người nghỉ (33,3%) > Giới hạn 30% - Quản lý cần xem xét.' == nodes['TEAM_QUOTA']['note']


def test_team_quota_escalates_without_shifting_requested_date(client,isolated_db):
    for index in range(3):
        legacy_approval(isolated_db,f'ABS{index}',f'EMP{index}', ['2026-10-20'])

    response=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},
        json=payload(from_date='2026-10-20',to_date='2026-10-20'))
    assert response.status_code==200,response.text
    submitted=response.json()['data']
    assert submitted['from_date']=='2026-10-20'
    assert submitted['to_date']=='2026-10-20'
    assert submitted['decision']=='ESCALATE'

    analysis=client.get(f"/api/leave/{submitted['id']}/analysis",headers={'X-Actor-ID':'E'})
    assert analysis.status_code==200,analysis.text
    nodes={node['stage']:node for node in analysis.json()['decision_tree_checklist']}
    assert nodes['TEAM_QUOTA']['status']=='WARN'
    assert '4 / 12 người nghỉ (33,3%)' in nodes['TEAM_QUOTA']['note']


def test_analysis_hides_quota_when_annual_request_needs_no_leave(client):
    response=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},
        json=payload(from_date='2026-10-17',to_date='2026-10-18'))
    assert response.status_code==200,response.text
    assert response.json()['data']['decision']=='NO_LEAVE_REQUIRED'
    request_id=response.json()['data']['id']
    analysis=client.get(f'/api/leave/{request_id}/analysis',headers={'X-Actor-ID':'E'})
    assert analysis.status_code==200,analysis.text
    stages={node['stage'] for node in analysis.json()['decision_tree_checklist']}
    assert 'TEAM_QUOTA' not in stages


def test_duplicate_partial_and_atomic_rollback(service,isolated_db,monkeypatch):
    first=service.process_new_request(employee_id='E',structured_data=payload())
    duplicate=service.process_new_request(employee_id='E',structured_data=payload())
    assert duplicate['error_code']=='REQUEST_ALREADY_COVERED'
    partial=service.process_new_request(employee_id='E',structured_data=payload(from_date='2026-10-06',to_date='2026-10-07'))
    assert partial['error_code']=='OVERLAPPING_REQUEST'
    assert isolated_db.get_employee('E')['remaining_leave_days']==98
    import storage
    def fail(*args): raise RuntimeError('simulated disk failure')
    monkeypatch.setattr(storage,'save_record',fail)
    with pytest.raises(RuntimeError): service.process_new_request(employee_id='E',structured_data=payload(from_date='2026-10-12',to_date='2026-10-13'))
    c=isolated_db.get_db_connection()
    assert c.execute('SELECT COUNT(*) FROM leave_transactions').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM leave_bookings').fetchone()[0]==2
    c.close()
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_concurrent_auto_approval_same_day(service,isolated_db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:service.process_new_request(employee_id='E',structured_data=payload()),range(2)))
    assert sorted(r['decision'] for r in results)==['AUTO_APPROVE','AUTO_REJECT']
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_annual_human_approval_and_double_refund(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    r=service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')
    assert r['status']=='COMPLETED' and r['human_resolution']=='APPROVE_OVERRIDE'
    assert isolated_db.get_employee('E')['remaining_leave_days']==97
    with pytest.raises(Conflict):service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')
    undone=service.cancel(r['id'],'M',revoke=True)
    assert undone['deducted_days']==0 and undone['annual_balance_change']==0
    assert isolated_db.get_employee('E')['remaining_leave_days']==100
    with pytest.raises(Conflict):service.cancel(r['id'],'M',revoke=True)
    assert isolated_db.get_employee('E')['remaining_leave_days']==100
    again=service.process_new_request(employee_id='E',structured_data=payload())
    assert again['decision']=='AUTO_APPROVE'

def test_concurrent_human_approval(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    def approve(_):
        try:return service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')['status']
        except Conflict:return 'CONFLICT'
    with ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(approve,range(2)))
    assert sorted(statuses)==['COMPLETED','CONFLICT']
    assert isolated_db.get_employee('E')['remaining_leave_days']==97

@pytest.mark.parametrize('end,actors',[('2026-10-06',['M']),('2026-10-12',['H','HRD']),('2026-10-30',['H','HRD','CEO'])])
def test_unpaid_multistep_approval(service,isolated_db,end,actors):
    r=service.process_new_request(employee_id='E',structured_data=payload(leave_type='UNPAID_OTHER',to_date=end))
    for i,a in enumerate(actors):
        r=service.process_human_decision(r['id'],approver_id=a,action_type='APPROVE')
        assert r['status']==('COMPLETED' if i==len(actors)-1 else 'PENDING_ESCALATION')
    assert all(s['status']=='APPROVED' for s in r['approval_steps'])
    assert r['deducted_days']==0 and isolated_db.get_employee('E')['remaining_leave_days']==100

def test_wrong_role_and_self_approval(client,service):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    for id in ['HR','CEO','E','B']:
        response=client.post('/api/leave/'+r['id']+'/human-decision',headers={'X-Actor-ID':id},json={'action_type':'APPROVE'})
        assert response.status_code==403,response.text
    response=client.post('/api/leave/'+r['id']+'/human-decision',headers={'X-Actor-ID':'M'},json={'action_type':'APPROVE','approver_id':'CEO'})
    assert response.status_code==403

def test_info_then_employee_resubmit(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    r=service.process_human_decision(r['id'],approver_id='M',action_type='REQUEST_MORE_INFO')
    assert r['status']=='WAITING_EMPLOYEE'
    r=service.resubmit(r['id'],'E',payload())
    assert r['status']=='COMPLETED' and r['revision']==2
    assert isolated_db.get_employee('E')['remaining_leave_days']==98

def test_conditional_change_rechecks_and_invalidates_prior_steps(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(leave_type='UNPAID_OTHER',to_date='2026-10-12'))
    r=service.process_human_decision(r['id'],approver_id='H',action_type='APPROVE')
    r=service.process_human_decision(r['id'],approver_id='HRD',action_type='MODIFY_CONDITIONAL',updated_fields={'to_date':'2026-10-13'})
    assert r['target_role']=='DEPARTMENT_HEAD' and r['revision']==2
    assert all(s['status']=='PENDING' for s in r['approval_steps'])
    assert isolated_db.get_employee('E')['remaining_leave_days']==100

def test_balance_and_overlap_rechecked_at_final_approval(service,isolated_db):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    c=isolated_db.get_db_connection();c.execute("UPDATE employees SET remaining_leave_days=1 WHERE employee_id='E'");c.commit();c.close()
    r=service.process_human_decision(r['id'],approver_id='M',action_type='APPROVE')
    assert r['decision']=='AUTO_REJECT' and r['error_code']=='BALANCE_EXCEEDED'
    assert isolated_db.get_employee('E')['remaining_leave_days']==1

def test_no_refund_for_unproven_legacy_debit(service,isolated_db):
    legacy_approval(isolated_db,'OLD','E',['2026-10-05'])
    with pytest.raises(Conflict):service.cancel('OLD','M',revoke=True)
    assert isolated_db.get_employee('E')['remaining_leave_days']==100

PDF=b'%PDF-1.4\n%%EOF'
def upload(client,owner='E'):
    response=client.post('/api/leave/proofs',headers={'X-Actor-ID':owner},data={'proof_type':'MEDICAL_LEAVE_CERTIFICATE'},files={'file':('note.pdf',PDF,'application/pdf')})
    assert response.status_code==200,response.text
    return response.json()['data']['proof_id']

def test_upload_hr_verification_medical_workflow(client,isolated_db):
    pid=upload(client)
    created=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload(leave_type='SICK_MEDICAL',proof_id=pid,to_date='2026-10-05')).json()['data']
    if created.get('status') == 'PROCESSING':
        import time
        for _ in range(50):
            time.sleep(0.05)
            created = client.get('/api/leave/' + created['id'], headers={'X-Actor-ID':'E'}).json()['data']
            if created.get('status') != 'PROCESSING':
                break
    assert created['target_role']=='HR' and created['error_code']=='PROOF_REVIEW_REQUIRED'
    assert client.get('/api/leave/proofs/'+pid,headers={'X-Actor-ID':'B'}).status_code==403
    assert client.get('/api/leave/proofs/'+pid,headers={'X-Actor-ID':'HR'}).content==PDF
    verify={k:v for k,v in PROOF.items() if k!='verified_by'};verify['verification_notes']='Đã đối chiếu với chứng từ gốc.';verify['recommended_to_date']='2026-10-05'
    assert client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'E'},json=verify).status_code==403
    r=client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'HR'},json=verify)
    assert r.status_code==200,r.text
    req=isolated_db.get_leave_request(created['id'])
    assert req['decision']=='AUTO_APPROVE' and req['deducted_days']==0
    assert isolated_db.get_employee('E')['remaining_leave_days']==100
    assert client.post('/api/leave/proofs/'+pid+'/verify',headers={'X-Actor-ID':'HR'},json=verify).status_code==409


def test_three_day_medical_escalation_explains_duration_and_proof_review(client,isolated_db,service):
    proof={
        **PROOF,
        'proof_verification_status':'UNVERIFIED',
        'issue_date':'2026-11-03',
        'recommended_from_date':'2026-11-03',
        'recommended_to_date':'2026-11-05',
        'doc_diagnosis':'Viêm họng hạt cấp tính',
        'patient_name_match':'MATCH',
        'reason_diagnosis_match':'MISMATCH',
        'reason_diagnosis_match_reason':'Lý do nghỉ không khớp với chẩn đoán trên giấy.',
    }
    pid=proof_fixture(isolated_db,proof)
    vlm_json={
        'inspection_mode':'OLLAMA_REAL_QWEN25_VL_3B',
        '_inspection_context':{'leave_type':'SICK_MEDICAL','reason_category':''},
        'document_summary':{
            'patient_name':'Nguyễn Văn An',
            'diagnosis':'Viêm họng hạt cấp tính',
            'issuer':'Hospital',
            'issue_date':'2026-11-03',
            'doctor_recommended_range':{'from':'2026-11-03','to':'2026-11-05','days':3},
        },
        'flags':{'document_readability':'READABLE','has_red_stamp':True,'signature_present_on_scan':True},
        'correlation_analysis':{
            'score':0.8,
            'patient_name_match':'MATCH',
            'reason_diagnosis_match':'MISMATCH',
            'reason_diagnosis_match_reason':'Lý do nghỉ không khớp với chẩn đoán trên giấy.',
        },
    }
    connection=isolated_db.get_db_connection()
    connection.execute(
        "UPDATE proof_documents SET inspection_status='READY',vlm_analysis_json=? WHERE id=?",
        (json.dumps(vlm_json,ensure_ascii=False),pid),
    )
    connection.commit();connection.close()

    request=service.process_new_request(
        employee_id='E',
        structured_data=payload(
            leave_type='SICK_MEDICAL',
            from_date='2026-11-03',
            to_date='2026-11-05',
            reason='Nghỉ ốm điều trị',
            proof_id=pid,
        ),
    )
    assert request['decision']=='ESCALATE'
    assert request['error_code']=='PROOF_REVIEW_REQUIRED'

    analysis=client.get(f"/api/leave/{request['id']}/analysis",headers={'X-Actor-ID':'E'})
    assert analysis.status_code==200,analysis.text
    data=analysis.json()
    assert '3 ngày' in data['decision_reason']
    assert 'trần tự duyệt 1 ngày' in data['decision_reason']
    assert 'chứng từ y tế' in data['decision_reason'].lower()
    assert data['reason_diagnosis_match']=='MISMATCH'
    assert 'không khớp' in data['reason_diagnosis_match_reason'].lower()


def test_wedding_escalation_reason_calls_out_missing_signature_and_relationship():
    from routers.leave_router import build_explicit_escalation_reason

    text = build_explicit_escalation_reason(
        'PROOF_REVIEW_REQUIRED',
        'ESCALATE',
        1,
        'SPECIAL_PAID',
        {
            'signature_present': False,
            'digital_signature_present': False,
            'relationship_label': None,
        },
        'Lead Team (quản lý trực tiếp)',
        'Đơn cần Lead Team xem xét trước khi duyệt.',
        reason_category='CHILD_MARRIAGE',
    )

    lowered = text.lower()
    assert 'thiếu chữ ký' in lowered
    assert 'quan hệ' in lowered
    assert 'xác minh' in lowered


def test_annual_leave_escalation_does_not_claim_relationship_is_unverified():
    from routers.leave_router import build_explicit_escalation_reason

    text = build_explicit_escalation_reason(
        'DURATION_OVER_MANAGER_LIMIT',
        'ESCALATE',
        6,
        'ANNUAL',
        {},
        'Tổng Giám đốc',
        'Chuyển cấp do đơn nghỉ 6 ngày vượt thẩm quyền của Lead Team; Tổng Giám đốc xem xét theo phân cấp.',
        reason_category='PERSONAL',
    )

    assert 'vượt thẩm quyền của Lead Team' in text
    assert 'quan hệ' not in text.lower()


def test_escalation_reason_does_not_repeat_existing_proof_issues():
    from routers.leave_router import build_explicit_escalation_reason

    issue = 'quan hệ trên giấy chưa xác minh rõ ràng'
    text = build_explicit_escalation_reason(
        'PROOF_REVIEW_REQUIRED',
        'ESCALATE',
        1,
        'SPECIAL_PAID',
        {'relationship_label': None},
        'Lead Team',
        f'Đơn chuyển cấp để đối chiếu {issue} trước khi duyệt.',
        reason_category='CHILD_MARRIAGE',
    )

    assert text.lower().count(issue) == 1


def test_child_marriage_analysis_uses_event_not_medical_fields(client,isolated_db,service):
    pid=proof_fixture(isolated_db,{
        **PROOF,
        'proof_type':'MARRIAGE_CERTIFICATE',
        'proof_verification_status':'UNVERIFIED',
        'issuer':'UBND Phường Dịch Vọng Hậu, Cầu Giấy, Hà Nội',
        'issue_date':'2026-09-22',
        'document_readability':'READABLE',
        'signature_present':True,
    })
    vlm_json={
        'inspector_persona':'Chuyên viên xác minh hôn sự',
        'target_model':'qwen2.5vl:7b',
        'inspection_mode':'OLLAMA_REAL_QWEN25_VL_3B',
        '_inspection_context':{'leave_type':'SPECIAL_PAID','reason_category':'CHILD_MARRIAGE'},
        'document_summary':{
            'patient_name':'TRẦN QUỐC ANH',
            'issuer':'UBND Phường Dịch Vọng Hậu, Cầu Giấy, Hà Nội',
            'issue_date':'2026-09-22',
            'doctor_recommended_range':{'from':None,'to':None,'days':None},
            'subject_name':'TRẦN QUỐC ANH',
            'partner_name':'ĐẶNG MAI PHƯƠNG',
            'event_type':'CHILD_MARRIAGE',
            'wedding_date':'2026-09-22',
        },
        'flags':{
            'has_red_stamp':True,
            'has_doctor_signature':False,
            'signature_present_on_scan':True,
            'document_readability':'READABLE',
            'is_tampered':False,
            'ai_generated_or_edited':False,
        },
        'correlation_analysis':{'score':None,'issues':[],'requested_workdays':1},
        'escalation_flags':[],
        'raw_fields_detected':['subject_name','partner_name','wedding_date'],
    }
    c=isolated_db.get_db_connection()
    c.execute(
        "UPDATE proof_documents SET inspection_status='READY',vlm_analysis_json=? WHERE id=?",
        (json.dumps(vlm_json,ensure_ascii=False),pid),
    )
    c.commit();c.close()

    request=service.process_new_request(
        employee_id='E',
        structured_data=payload(
            leave_type='SPECIAL_PAID',
            reason_category='CHILD_MARRIAGE',
            from_date='2026-10-12',
            to_date='2026-10-12',
            reason='Nghỉ dự đám cưới con trai Trần Quốc Anh',
            proof_id=pid,
        ),
    )
    response=client.get(f"/api/leave/{request['id']}/analysis",headers={'X-Actor-ID':'E'})
    assert response.status_code==200,response.text
    analysis=response.json()
    nodes={node['stage']:node for node in analysis['decision_tree_checklist']}

    assert 'Số dư phép hiện tại: 100 ngày' in nodes['BALANCE']['note']
    assert 'Đơn nghỉ này không trừ vào phép năm.' in nodes['BALANCE']['note']
    assert nodes['VLM_DATE_COVERAGE']['status']=='FAIL'
    assert 'Ngày cưới trên giấy' in nodes['VLM_DATE_COVERAGE']['note']
    assert 'Bác sĩ chỉ định' not in nodes['VLM_DATE_COVERAGE']['note']
    assert nodes['VLM_CORRELATION']['status']=='NOT_RUN'
    assert nodes['VLM_PATIENT']['status']=='NOT_RUN'
    assert nodes['VLM_DATE_COVERAGE']['title_vi']=='Đối chiếu ngày cưới với ngày nghỉ'
    assert 'TRẦN QUỐC ANH' in nodes['PROOF']['note']
    assert 'Chữ ký người có thẩm quyền: Có' in nodes['VLM_INTEGRITY']['note']
    assert all('Correlation score' not in node['note'] for node in analysis['decision_tree_checklist'])
    assert all('y tế' not in item.casefold() for item in analysis['llm_summary']['info_missing_vn'])

@pytest.mark.parametrize('readability', ['READABLE', 'UNREADABLE'])
def test_bereavement_analysis_uses_family_event_fields_not_medical_fields(client,isolated_db,service,readability):
    pid=proof_fixture(isolated_db,{
        **PROOF,
        'proof_type':'DEATH_CERTIFICATE',
        'deceased_name':'Trần Thị Lan',
        'relationship_label':'Mẹ ruột',
        'relationship_to_employee':'Cha/mẹ của nhân viên (Chưa xác minh)',
        'date_of_death':'2026-11-02',
        'funeral_date':'2026-11-04',
        'proof_verification_status':'UNVERIFIED',
        'issuer':'Ủy ban nhân dân phường Quan Hòa',
        'issue_date':'2026-11-01',
        'document_readability':readability,
        'signature_present':True,
        'has_red_stamp':True,
    })
    vlm_json={
        'inspector_persona':'Chuyên viên xác minh tang lễ',
        '_inspection_context':{'leave_type':'SPECIAL_PAID','reason_category':'PARENT_DEATH'},
        'document_summary':{
            'patient_name':'Trần Thị Lan',
            'deceased_name':'Trần Thị Lan',
            'relationship_label':'Mẹ ruột',
            'relationship_to_employee':'Cha/mẹ của nhân viên (Chưa xác minh)',
            'issuer':'Ủy ban nhân dân phường Quan Hòa',
            'issue_date':'2026-11-01',
            'date_of_death':'2026-11-02',
            'funeral_date':'2026-11-04',
        },
        'flags':{
            'has_red_stamp':True,
            'has_doctor_signature':False,
            'signature_present_on_scan':True,
            'document_readability':readability,
            'is_tampered':False,
            'ai_generated_or_edited':False,
        },
        'correlation_analysis':{'score':None,'issues':[]},
        'escalation_flags':[],
    }
    c=isolated_db.get_db_connection()
    c.execute("UPDATE proof_documents SET inspection_status='READY',vlm_analysis_json=? WHERE id=?",
              (json.dumps(vlm_json,ensure_ascii=False),pid))
    c.commit();c.close()

    request=service.process_new_request(
        employee_id='E',
        structured_data=payload(
            leave_type='SPECIAL_PAID',
            reason_category='PARENT_DEATH',
            from_date='2026-11-02',
            to_date='2026-11-04',
            reason='Lo tang lễ cho mẹ ruột (Trần Thị Lan) tại quê nhà',
            proof_id=pid,
        ),
    )
    response=client.get(f"/api/leave/{request['id']}/analysis",headers={'X-Actor-ID':'E'})
    assert response.status_code==200,response.text
    analysis=response.json()
    nodes={node['stage']:node for node in analysis['decision_tree_checklist']}

    if readability == 'READABLE':
        assert 'Chứng từ đính kèm: Có' in nodes['PROOF']['note']
        assert 'Tên người mất: Trần Thị Lan' in nodes['PROOF']['note']
        assert 'Quan hệ ghi trên giấy: Mẹ ruột' in nodes['PROOF']['note']
        assert 'Quan hệ đã đối chiếu: Cha/mẹ của nhân viên (Đã xác minh)' in nodes['PROOF']['note']
        assert 'Chữ ký người có thẩm quyền: Có' in nodes['VLM_INTEGRITY']['note']
        assert nodes['VLM_DATE_COVERAGE']['status']=='PASS', nodes['VLM_DATE_COVERAGE']['note']
        assert '2026-11-02 → 2026-11-04' in nodes['VLM_DATE_COVERAGE']['note']
        assert nodes['VLM_CORRELATION']['status']=='PASS'
        assert 'Nhận xét lý do: phù hợp với tang lễ' in nodes['VLM_CORRELATION']['note']
    else:
        assert 'không đọc được' in nodes['PROOF']['note'].casefold()
        assert 'Không thể xác minh tên người mất' in nodes['VLM_PATIENT']['note']
        assert 'Không thể xác minh ngày mất / tang lễ' in nodes['VLM_DATE_COVERAGE']['note']
    assert all(
        forbidden not in f"{node['title_vi']} {node['note']}".casefold()
        for node in analysis['decision_tree_checklist']
        for forbidden in ('chẩn đoán', 'bác sĩ', 'điều trị', 'mã bhxh')
    )

def test_upload_limits_and_fake_mime(client):
    assert client.post('/api/leave/proofs',headers={'X-Actor-ID':'E'},files={'file':('x.png',b'not png','image/png')}).status_code==415
    assert client.post('/api/leave/proofs',headers={'X-Actor-ID':'E'},files={'file':('x.pdf',b'%PDF-'+b'0'*(10*1024*1024),'application/pdf')}).status_code==413

def test_manager_cannot_approve_unverified_proof(client):
    pid=upload(client)
    r=client.post('/api/leave/request',headers={'X-Actor-ID':'E'},json=payload(leave_type='SICK_MEDICAL',proof_id=pid)).json()['data']
    if r.get('status') == 'PROCESSING':
        import time
        for _ in range(50):
            time.sleep(0.05)
            r = client.get('/api/leave/' + r['id'], headers={'X-Actor-ID':'E'}).json()['data']
            if r.get('status') != 'PROCESSING':
                break
    for actor,status in [('M',403),('HR',409)]:
        result=client.post('/api/leave/'+r['id']+'/human-decision',headers={'X-Actor-ID':actor},json={'action_type':'APPROVE'})
        assert result.status_code==status,result.text

def test_actor_queue_and_detail_visibility(client,service):
    r=service.process_new_request(employee_id='E',structured_data=payload(to_date='2026-10-07'))
    assert client.get('/api/leave/requests').status_code==401
    assert client.get('/api/leave/'+r['id'],headers={'X-Actor-ID':'B'}).status_code==403
    assert client.get('/api/leave/requests',headers={'X-Actor-ID':'HRD'}).json()['data']==[]
    data=client.get('/api/leave/requests',headers={'X-Actor-ID':'M'}).json()['data']
    assert len(data)==1 and data[0]['can_act']

def test_verify_harness_no_llm_and_no_mutation(client,isolated_db):
    before=isolated_db.get_all_leave_requests()
    r=client.post('/api/verify/escalation')
    assert r.status_code==200,r.text
    s=r.json()['summary']
    assert (s['passed_cases'],s['auto_approved_cases'],s['escalated_cases'],s['llm_calls'])==(5,3,2,0)
    assert s['latency_seconds']<90
    assert isolated_db.get_all_leave_requests()==before

def test_migration_is_idempotent_and_preserves_history(isolated_db):
    before=isolated_db.get_employee('E')['remaining_leave_days']
    legacy_approval(isolated_db,'HISTORY','E',['2026-01-05'])
    old=isolated_db.get_leave_request('HISTORY')
    isolated_db.init_db();isolated_db.init_db()
    assert isolated_db.get_employee('E')['remaining_leave_days']==before
    assert isolated_db.get_leave_request('HISTORY')==old
    c=isolated_db.get_db_connection()
    assert c.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM leave_transactions').fetchone()[0]==0
    c.close()
