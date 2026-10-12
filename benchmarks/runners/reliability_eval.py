import subprocess, sys, time, xml.etree.ElementTree as ET
from benchmarks.common import ROOT

def run_reliability(run,existing=False):
    junit=run.path/'pytest.xml'
    paths=['benchmarks/tests']
    if existing:paths+=['tests/test_phase1_async_vlm_tx.py','tests/test_model_invocation_counts.py','tests/test_vlm_resize.py']
    started=time.perf_counter()
    process=subprocess.run([sys.executable,'-m','pytest',*paths,'-q',f'--junitxml={junit}'],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    # Do not publish captured logs; pytest XML may contain synthetic sentinel values only.
    (run.path/'pytest-output.txt').write_text(process.stdout,encoding='utf-8')
    if junit.exists():
        tree=ET.parse(junit)
        for t in tree.iter('testcase'):
            failure=t.find('failure');error=t.find('error');skip=t.find('skipped')
            status='failed' if failure is not None or error is not None else 'skipped' if skip is not None else 'passed'
            suite='security' if 'security' in t.attrib.get('classname','') or 'api_status_polling' in t.attrib.get('name','') else 'proof_correlation' if 'proof_correlation' in t.attrib.get('classname','') else 'reliability' if any(x in t.attrib.get('classname','') for x in ('reliability','phase1','model_failures')) else 'framework'
            detail=failure if failure is not None else error if error is not None else skip
            name=t.attrib['name']
            if len(name)>256:
                import hashlib
                name=name.split('[')[0]+'['+hashlib.sha256(name.encode()).hexdigest()[:12]+']'
            run.correctness.append({'case_id':name,'suite':suite,'status':status,
                'latency_ms':float(t.attrib.get('time',0))*1000,
                'reason':detail.attrib.get('message','')[:350] if detail is not None else None,
                'severity':'critical' if suite=='security' or 'stale' in t.attrib['name'] or 'recovery' in t.attrib['name'] else 'major',
                'mode':'isolated-controlled-injection'})
    else:run.correctness.append({'case_id':'pytest-execution','suite':'framework','status':'failed','reason':'Pytest did not produce XML'})
    for suite in ('reliability','security','framework','proof_correlation'):
        rows=[r for r in run.correctness if r['suite']==suite];n=len(rows);passed=sum(r['status']=='passed' for r in rows)
        run.sections[suite]={'n':n,'passed':passed,'failed':sum(r['status']=='failed' for r in rows),'skipped':sum(r['status']=='skipped' for r in rows),
            'test_pass_rate':passed/sum(r['status']!='skipped' for r in rows) if any(r['status']!='skipped' for r in rows) else None,
            'duration_seconds':time.perf_counter()-started,'pytest_exit_code':process.returncode,
            'database_locked_incidents':None,'duplicate_decision_incidents':None,'recovery_success_rate':None,
            'audit_integrity_rate':None,'invalid_state_transitions':None,
            'scope':'Test pass rate is not a production incident/recovery rate. Unmeasured rates are N/A.'}
