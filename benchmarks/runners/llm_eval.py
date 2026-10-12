import time
from datetime import datetime
from benchmarks.common import BENCH, ROOT, read, sandbox, bootstrap, seed_db
from benchmarks.metrics.aggregate import classification

def run_llm(run,live=False):
    tmp,directory=sandbox();original_chat=None
    try:
        bootstrap(directory);seed_db()
        from ai.agent_orchestrator import LeaveApprovalAgent
        from services.orchestration import LeaveOrchestratorService
        from ai.llm_client import LLMClient
        # Only explicit injection enables LLM features in this repository.
        client=LLMClient(model=run.config['llm_model']) if live else None
        agent=LeaveApprovalAgent(llm_client=client)
        calls=[];raw_calls=[]
        if live:
            import ai.llm_client as llm_module
            original_chat=llm_module.ollama_chat
            def observed_chat(payload,**kw):
                import json
                ts=time.perf_counter()
                try:
                    body=original_chat(payload,**kw)
                    try:
                        obj=json.loads((body.get('message') or {}).get('content') or '{}');valid=isinstance(obj,dict)
                    except (ValueError,TypeError):valid=False
                    row={'kind':'llm_ollama','model':payload['model'],'mode':'real','client_ms':(time.perf_counter()-ts)*1000,
                        'raw_json_valid':valid,'options':payload.get('options'),
                        **{k:body.get(k) for k in ['total_duration','load_duration','prompt_eval_duration','eval_duration','prompt_eval_count','eval_count']}}
                    raw_calls.append(row);run.inference.append(row);return body
                except Exception as e:
                    raw_calls.append({'error_type':type(e).__name__,'timeout':'timeout' in str(e).lower()});raise
            llm_module.ollama_chat=observed_chat
            original=client.generate_json
            def observed(**kw):
                t=time.perf_counter()
                try:return original(**kw)
                finally:calls.append((time.perf_counter()-t)*1000)
            client.generate_json=observed
        truth=read(BENCH/'datasets/ground_truth.json');ex=[];ac=[];field_results={}
        service=LeaveOrchestratorService(agent=agent if live else None,clock=lambda:datetime.fromisoformat(run.config['reference_time']))
        for case in read(BENCH/'datasets/applications.json'):
            if case['kind'] not in ('free_text','reviewer'):continue
            gt=truth[case['id']];row={'case_id':case['id'],'suite':'llm' if live else 'language_default',
                'expected':gt['expected'],'policy_reference':gt['policy_reference'],'severity':gt['severity'],'mode':'real' if live else 'deterministic-no-model'}
            if case['kind']=='free_text' and not live:
                row.update(status='skipped',actual=None,reason='Default pipeline disables free-text LLM; use --live-llm to evaluate explicitly injected existing adapter')
            else:
                t=time.perf_counter()
                try:
                    if case['kind']=='free_text':
                        observed=agent.parse_natural_language(case['text'],current_date=datetime.fromisoformat(case['reference_time']).date()).model_dump(mode='json')
                        ok=all(observed.get(k)==v for k,v in gt['expected'].items())
                        for k,v in gt['expected'].items(): field_results.setdefault(k,[]).append(observed.get(k)==v)
                    else:
                        # Exercise actual persisted default reviewer path, including ambiguous text.
                        i=int(case['id'].split('-')[-1])
                        req=service.process_new_request(employee_id=f'BENCH-{i:03}',structured_data={
                            'leave_type':'ANNUAL','from_date':'2026-09-14','to_date':'2026-09-16','no_handover_needed':True})
                        res=service.process_human_decision(req['id'],feedback_text=case['text'],approver_id='BENCH-M')
                        observed=res.get('human_resolution')
                        if observed is None and res['status']=='WAITING_EMPLOYEE': observed='MODIFY_CONDITIONAL'
                        if gt['expected']=='AMBIGUOUS':ok=observed not in ('APPROVE_OVERRIDE','REJECT') and res['status']!='COMPLETED'
                        else:ok=observed==gt['expected']
                        ex.append(gt['expected']);ac.append(observed or 'UNKNOWN')
                    row.update(status='passed' if ok else 'failed',actual=observed,latency_ms=(time.perf_counter()-t)*1000)
                except Exception as e:row.update(status='failed',actual=type(e).__name__,reason='Model/workflow failed; raw text omitted')
            run.correctness.append(row)
        run.sections['llm' if live else 'language_default']={'enabled_in_default_pipeline':False,'live_adapter_evaluated':live,
            'reviewer':classification(ex,ac),'extraction_fields':{k:sum(v)/len(v) for k,v in field_results.items()} or None,
            'model_calls':len(calls),'latencies_ms':calls,'llm_calls_per_attempted_case':len(calls)/(20 if live else 8),
            'raw_json_invalid_rate':sum(not r.get('raw_json_valid',False) for r in raw_calls)/len(raw_calls) if raw_calls else None,
            'timeout_rate':sum(r.get('timeout',False) for r in raw_calls)/len(raw_calls) if raw_calls else None,
            'limitation':'Reviewer decisions use keyword fallback when no LLM injected. Default ambiguity handling is evaluated for safety.'}
    finally:
        if original_chat is not None:llm_module.ollama_chat=original_chat
        tmp.cleanup()
