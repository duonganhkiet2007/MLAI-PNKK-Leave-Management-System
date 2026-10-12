import sys, time
from benchmarks.common import BENCH, ROOT, read, dump
from benchmarks.metrics.aggregate import classification, stats

def run_policy(run):
    for name in ('backend','Leave_Application'):sys.path.insert(0,str(ROOT/name))
    from rule_engine import LeaveRequest, LeaveRuleEngine
    from calendar_service import CalendarService
    cases=read(BENCH/'datasets/applications.json');truth=read(BENCH/'datasets/ground_truth.json')
    expected=[];actual=[];routes=[];lat=[];violations=[];coverage=None
    try:
        import coverage as coverage_module
        coverage=coverage_module.Coverage(branch=True,include=[str(ROOT/'Leave_Application/rule_engine.py')],data_file=str(run.path/'.coverage'))
        coverage.start()
    except ImportError:pass
    for case in cases:
        if case['kind']!='policy':continue
        gt=truth[case['id']];t0=time.perf_counter()
        try:
            result=LeaveRuleEngine.evaluate(LeaveRequest.model_validate(case['request']),calendar=CalendarService()).model_dump(mode='json')
            observed={k:result.get(k) for k in ('decision','target_role')}
            elapsed=(time.perf_counter()-t0)*1000;lat.append(elapsed)
            conflict=gt.get('policy_conflict');correct=observed==gt['expected']
            row={'case_id':case['id'],'suite':'policy','status':'skipped' if conflict else 'passed' if correct else 'failed',
                'expected':gt['expected'],'actual':observed,'policy_reference':gt['policy_reference'],'severity':gt['severity'],
                'reason':conflict or gt['rationale'],'latency_ms':elapsed,'category':case['category'],
                'policy_conflict_observed_match':correct if conflict else None,'trace':result.get('decision_trace')}
            if not conflict:
                expected.append(gt['expected']['decision']);actual.append(observed['decision'])
                if gt['expected']['decision']=='ESCALATE': routes.append(observed['target_role']==gt['expected']['target_role'])
                if gt['expected']['decision']!='AUTO_APPROVE':violations.append(observed['decision']!='AUTO_APPROVE')
        except Exception as e:
            row={'case_id':case['id'],'suite':'policy','status':'failed','expected':gt['expected'],'actual':type(e).__name__,
                'policy_reference':gt['policy_reference'],'severity':gt['severity'],'reason':'Evaluation exception'}
        run.correctness.append(row)
    branch=None
    if coverage:
        coverage.stop();coverage.save();coverage.json_report(outfile=str(run.path/'coverage.json'))
        totals=read(run.path/'coverage.json')['totals'];branch=totals.get('covered_branches',0)/totals['num_branches'] if totals.get('num_branches') else None
    es=[e=='ESCALATE' for e in expected];ac=[a=='ESCALATE' for a in actual];tp=sum(e and a for e,a in zip(es,ac))
    automatic=[(e,a) for e,a in zip(expected,actual) if a in ('AUTO_APPROVE','AUTO_REJECT','NO_LEAVE_REQUIRED')]
    run.sections['policy']={**classification(expected,actual),'routing_accuracy':sum(routes)/len(routes) if routes else None,
        'violation_detection_recall':sum(violations)/len(violations) if violations else None,
        'branch_coverage':branch,'decision_latency':stats(lat),
        'critical_violation_count':sum(r['suite']=='policy' and r['status']=='failed' and r['severity']=='critical' for r in run.correctness)}
    run.sections['escalation']={'precision':tp/sum(ac) if any(ac) else None,'recall':tp/sum(es) if any(es) else None,
        'unsafe_automatic_count':sum(e!='AUTO_APPROVE' and a=='AUTO_APPROVE' for e,a in zip(expected,actual)),
        'unnecessary_escalation_rate':sum(not e and a for e,a in zip(es,ac))/sum(not e for e in es) if any(not e for e in es) else None,
        'automatic_coverage':len(automatic)/len(actual) if actual else None,
        'automatic_accuracy':sum(e==a for e,a in automatic)/len(automatic) if automatic else None,
        'final_resolution_success_rate':None,'scope':'Independent rule engine; persisted human workflows covered by integration tests'}
