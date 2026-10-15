import asyncio, hashlib, json, socket, subprocess, sys, time, uuid
from datetime import datetime
from pathlib import Path
import httpx
from evaluation.benchmarks.common import ROOT, sandbox, dump
from evaluation.benchmarks.datasets.proofs import document

OUTCOMES={'COMPLETED','REJECTED','WAITING_EMPLOYEE','PENDING_ESCALATION','PENDING_HANDOVER','CANCELLED'}
FINAL={'COMPLETED','REJECTED','CANCELLED'}

def distribution(scenario,n,config):
    if scenario in ('no_proof','ready','cold'): return [scenario]*n
    weights=config['mixed_weights'] if scenario=='mixed' else config['contention_weights']
    if any(x<0 for x in weights.values()) or abs(sum(weights.values())-1)>1e-6: raise ValueError('Workload weights must sum to one')
    raw={k:n*weights.get(k,0) for k in ('no_proof','ready','cold')};counts={k:int(v) for k,v in raw.items()}
    for k in sorted(raw,key=lambda k:raw[k]-counts[k],reverse=True)[:n-sum(counts.values())]: counts[k]+=1
    return [k for k in ('no_proof','ready','cold') for _ in range(counts[k])]

async def wait_proof(client,pid,headers,config):
    deadline=time.perf_counter()+config['completion_timeout_seconds']
    while time.perf_counter()<deadline:
        r=await client.get(f'/api/leave/proofs/{pid}/status',headers=headers);r.raise_for_status()
        s=r.json()['data']['inspection_status']
        if s=='READY': return
        if s=='FAILED': raise RuntimeError('READY preparation failed')
        await asyncio.sleep(config['poll_interval_seconds'])
    raise TimeoutError('READY preparation deadline')

async def batch(run,scenario,n,arrival,repeat):
    config=run.config
    tmp,directory=sandbox()
    dump(directory/'config.json',config)
    with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    # A separate real TCP server avoids ASGITransport serialising synchronous handlers.
    log=(directory/'backend.log').open('w')
    process=subprocess.Popen([sys.executable,'-m','benchmarks.server','--directory',str(directory),'--config',str(directory/'config.json'),'--port',str(port)],cwd=ROOT,stdout=log,stderr=log)
    batch_id=f'{scenario}-{n}-{arrival}-{repeat}'
    try:
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',timeout=config['request_timeout_seconds'],limits=httpx.Limits(max_connections=max(n*3,20))) as client:
            for _ in range(300):
                if process.poll() is not None: raise RuntimeError('Isolated backend startup failed; '+(directory/'backend.log').read_text()[-1200:])
                try:
                    ready=await client.get('/api')
                    if ready.status_code==200: break
                except httpx.HTTPError: pass
                await asyncio.sleep(.1)
            else: raise RuntimeError('Isolated backend startup timeout')
            dump(run.path/'openapi.json',(await client.get('/openapi.json')).json())
            kinds=distribution(scenario,n,config)
            documents=[document(i) for i in range(n)]
            hashes=[hashlib.sha256(d).hexdigest() for d in documents]
            if len(set(hashes))!=n: raise AssertionError('Proof contents must have distinct hashes')
            proof_ids={}
            # READY preprocessing belongs to setup, not measured submit latency.
            for i,kind in enumerate(kinds):
                if kind=='ready':
                    h={'X-Actor-ID':f'BENCH-{i:03}'}
                    r=await client.post('/api/leave/proofs',headers=h,files={'file':(f'test-{i}.png',documents[i],'image/png')},data={'proof_type':'MEDICAL_LEAVE_CERTIFICATE'})
                    r.raise_for_status();pid=r.json()['data']['proof_id'];proof_ids[i]=pid
                    await wait_proof(client,pid,h,config)
            before=(await client.get('/__benchmark/snapshot')).json()
            epoch=time.perf_counter()+.1; wall_epoch=time.time()+.1
            async def employee(i,kind):
                offset=0 if arrival=='burst' else config['stagger_window_seconds']*i/max(n-1,1)
                planned=epoch+offset
                await asyncio.sleep(max(0,planned-time.perf_counter()))
                t0=time.perf_counter();row={'case_id':f'{batch_id}-{i:03}','batch_id':batch_id,'scenario':scenario,'concurrency':n,
                    'category':kind,'arrival':arrival,'mode':config['model_mode'],'planned_offset_ms':offset*1000,
                    'arrival_offset_ms':(t0-epoch)*1000,'arrival_timestamp':datetime.fromtimestamp(time.time()).astimezone().isoformat(),
                    'skew_ms':(t0-planned)*1000,'proof_sha256':hashes[i] if kind!='no_proof' else None,'outcome_reached':False,'business_final':False}
                h={'X-Actor-ID':f'BENCH-{i:03}'};pid=proof_ids.get(i)
                try:
                    if kind=='cold':
                        ts=time.perf_counter();r=await client.post('/api/leave/proofs',headers=h,files={'file':(f'test-{i}.png',documents[i],'image/png')},data={'proof_type':'MEDICAL_LEAVE_CERTIFICATE'})
                        row['upload_ms']=(time.perf_counter()-ts)*1000;row['upload_status_code']=r.status_code;r.raise_for_status()
                        pid=r.json()['data']['proof_id']
                    payload={'employee_id':f'BENCH-{i:03}','leave_type':'ANNUAL' if kind=='no_proof' else 'SICK_MEDICAL',
                        'from_date':'2026-09-14','to_date':'2026-09-14','reason':'Synthetic supporting reason'}
                    if pid:payload['proof_id']=pid
                    ts=time.perf_counter();row['submit_offset_ms']=(ts-epoch)*1000
                    r=await client.post('/api/leave/request',headers=h,json=payload)
                    row['ack_ms']=(time.perf_counter()-ts)*1000;row['ack_offset_ms']=(time.perf_counter()-epoch)*1000
                    row['status_code']=r.status_code;r.raise_for_status();data=r.json()['data'];row['request_id']=data['id'];row['proof_id']=pid
                    deadline=time.perf_counter()+config['completion_timeout_seconds']
                    while data.get('status') not in OUTCOMES and time.perf_counter()<deadline:
                        await asyncio.sleep(config['poll_interval_seconds'])
                        r=await client.get('/api/leave/'+data['id'],headers=h);r.raise_for_status();data=r.json()['data']
                    row.update(outcome_reached=data.get('status') in OUTCOMES,business_final=data.get('status') in FINAL,
                        final_state=data.get('status'),decision=data.get('decision'),error_code=data.get('error_code'),
                        rule_ms=data.get('rule_engine_ms'),final_offset_ms=(time.perf_counter()-epoch)*1000)
                    if row['outcome_reached']: row['final_ms']=(time.perf_counter()-t0)*1000
                    else: row.update(error='completion_deadline',timeout=True)
                except Exception as exc:
                    row.update(error=type(exc).__name__,timeout=isinstance(exc,(TimeoutError,httpx.TimeoutException)))
                return row
            rows=await asyncio.gather(*(employee(i,k) for i,k in enumerate(kinds)))
            done=time.perf_counter();snapshot=(await client.get('/__benchmark/snapshot')).json()
            jobs={j['proof_id']:j for j in snapshot['jobs']}
            for row in rows:
                job=jobs.get(row.get('proof_id'))
                if job and job['started_at']:
                    t_created=datetime.fromisoformat(job['created_at']).timestamp();t_start=datetime.fromisoformat(job['started_at']).timestamp()
                    row['queue_ms']=(t_start-t_created)*1000
                    row['queue_start_offset_ms']=(t_created-wall_epoch)*1000;row['inference_start_offset_ms']=(t_start-wall_epoch)*1000
                    if job['completed_at']:
                        t_end=datetime.fromisoformat(job['completed_at']).timestamp()
                        row['job_service_ms']=(t_end-t_start)*1000;row['inference_end_offset_ms']=(t_end-wall_epoch)*1000
                    run.inference.append({'case_id':row['case_id'],'model':config['vlm_model'],'queue_ms':row['queue_ms'],
                        'job_service_ms':row.get('job_service_ms'),'mode':config['model_mode'],'retries':job['retry_count'],
                        'timing_note':'Job timestamps include wrapper/persistence, not pure GPU inference. Retry timestamps do not provide per-attempt queue waits.'})
            dump(run.path/f'{batch_id}-snapshot.json',snapshot)
            run.requests.extend(rows)
            makespan=max(0,done-epoch);complete=sum(r['outcome_reached'] for r in rows)
            new_events=snapshot['events'][len(before['events']):]
            for event in new_events:
                if event['kind']=='ollama': run.inference.append({'case_id':batch_id,**event,'queue_ms':None,'timing_note':'Ollama response durations in ns; client duration in ms'})
            from evaluation.benchmarks.metrics.aggregate import stats
            run.batches.append({'batch_id':batch_id,'scenario':scenario,'concurrency':n,'arrival':arrival,'repetition':repeat,
                'mode':config['model_mode'],'makespan_seconds':makespan,'outcomes_per_second':complete/makespan if makespan else None,
                'business_final_count':sum(r['business_final'] for r in rows),'outcome_count':complete,'unfinished':n-complete,
                'sqlite_lock_wait':stats([e['duration_ms'] for e in new_events if e['kind']=='sqlite_lock_wait']),
                'sqlite_transaction':stats([e['duration_ms'] for e in new_events if e['kind']=='sqlite_transaction']),
                'vlm_client':stats([e['duration_ms'] for e in new_events if e['kind']=='vlm_client'])})
            print(f'{batch_id}: {complete}/{n} automatic outcomes, {makespan:.3f}s [{config["model_mode"]}]',flush=True)
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close();tmp.cleanup()

async def run_load(run,scenarios=None,levels=None,arrivals=None):
    for repeat in range(run.config['repetitions']):
        for scenario in scenarios or run.config['scenarios']:
            for n in levels or run.config['concurrency_levels']:
                for arrival in arrivals or [run.config['arrival']]:
                    await batch(run,scenario,n,arrival,repeat)
