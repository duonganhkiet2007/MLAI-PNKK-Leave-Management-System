import csv, json
from pathlib import Path
from evaluation.benchmarks.common import read,dump

MATCH_CONFIG=['dataset_version','seed','reference_time','timezone','concurrency_levels','scenarios','mixed_weights',
    'contention_weights','arrival','stagger_window_seconds','request_timeout_seconds','completion_timeout_seconds',
    'poll_interval_seconds','mock_inference_seconds','model_mode','cache_policy','model_start','repetitions',
    'ollama_base','vlm_model','llm_model','vlm_max_image_dim','inference_parameters']

def check(a,b):
    mismatches=[k for k in ['dataset_sha256','annotations_sha256','ground_truth_sha256','policy_sha256','hardware','models'] if a.get(k)!=b.get(k)]
    mismatches+=['config.'+k for k in MATCH_CONFIG if a['config'].get(k)!=b['config'].get(k)]
    if mismatches:raise ValueError('Incomparable runs: '+', '.join(mismatches))

def compare(baseline,optimized,output):
    a=read(Path(baseline)/'metadata.json');b=read(Path(optimized)/'metadata.json');check(a,b)
    sa=read(Path(baseline)/'summary.json');sb=read(Path(optimized)/'summary.json')
    def key(r):return (r['scenario'],r['concurrency'],r['category'],r['arrival'],r['mode'])
    aa={key(r):r for r in sa['performance']};bb={key(r):r for r in sb['performance']}
    if aa.keys()!=bb.keys():raise ValueError('Incomparable observed workload groups')
    rows=[]
    for k in aa:
        if aa[k]['n']!=bb[k]['n']:raise ValueError('Observed sample sizes differ')
        for metric,path in [('ack_p95_ms',('ack','p95_ms')),('end_to_end_mean_ms',('end_to_end','mean_ms'))]:
            av=aa[k][path[0]][path[1]];bv=bb[k][path[0]][path[1]]
            rows.append({'group':k,'metric':metric,'baseline':av,'optimized':bv,
                'absolute_reduction':av-bv if av is not None and bv is not None else None,
                'reduction_percent':100*(av-bv)/av if av is not None and bv is not None and av>0 else None})
        rows.append({'group':k,'metric':'error_rate_change','baseline':aa[k]['error_rate'],'optimized':bb[k]['error_rate'],
            'difference':bb[k]['error_rate']-aa[k]['error_rate']})
    def correctness(path):
        with (Path(path)/'correctness.csv').open(encoding='utf-8') as f:
            return {(r['suite'],r['case_id']):r['actual'] for r in csv.DictReader(f) if r.get('actual')}
    ca=correctness(baseline);cb=correctness(optimized)
    if ca.keys()!=cb.keys():raise ValueError('Correctness case sets differ')
    parity=sum(ca[k]==cb[k] for k in ca)/len(ca) if ca else None
    ba={r['batch_id']:r for r in sa['batches']};bc={r['batch_id']:r for r in sb['batches']}
    if ba.keys()!=bc.keys():raise ValueError('Batch arrival configurations differ')
    batch_changes=[]
    for k in ba:
        batch_changes.append({'batch_id':k,'throughput_change':bc[k]['outcomes_per_second']-ba[k]['outcomes_per_second'],
            'makespan_reduction_seconds':ba[k]['makespan_seconds']-bc[k]['makespan_seconds'],
            'sqlite_lock_mean_reduction_ms':ba[k]['sqlite_lock_wait']['mean_ms']-bc[k]['sqlite_lock_wait']['mean_ms'] if ba[k]['sqlite_lock_wait']['mean_ms'] is not None and bc[k]['sqlite_lock_wait']['mean_ms'] is not None else None})
    result={'baseline':a['run_id'],'optimized':b['run_id'],'decision_parity':parity,'metrics':rows,'batches':batch_changes,
        'same_source':a['source_sha256']==b['source_sha256'],
        'vlm_accuracy_difference':sb.get('vlm',{}).get('classification',{}).get('accuracy')-sa.get('vlm',{}).get('classification',{}).get('accuracy') if sb.get('vlm',{}).get('classification') and sa.get('vlm',{}).get('classification') else None,
        'reliability_failed_difference':sb.get('reliability',{}).get('failed',0)-sa.get('reliability',{}).get('failed',0),
        'limitation':'Equivalent configuration checked. External GPU contention/model residency may remain uncontrolled. Same-source runs measure repeatability, not optimization.'}
    output=Path(output);output.mkdir(parents=True,exist_ok=True);dump(output/'comparison.json',result)
    import html
    def cell(v):return html.escape('N/A' if v is None else f'{v:.3f}' if isinstance(v,(int,float)) else str(v))
    table='<table><tr><th>Scenario / concurrency / category / arrival / mode</th><th>Metric</th><th>Baseline</th><th>Second run</th><th>Absolute reduction / difference</th><th>Reduction %</th></tr>'
    for row in rows:
        table+='<tr>'+''.join('<td>'+cell(v)+'</td>' for v in [row['group'],row['metric'],row['baseline'],row['optimized'],row.get('absolute_reduction',row.get('difference')),row.get('reduction_percent')])+'</tr>'
    table+='</table>'
    title='MLAI same-source repeatability comparison' if result['same_source'] else 'MLAI before / after comparison'
    (output/'comparison.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>body{font:15px system-ui;padding:24px;color:#17202a}table{border-collapse:collapse;width:100%}td,th{text-align:left;border-bottom:1px solid #ddd;padding:10px}th{background:#eee}pre{white-space:pre-wrap}</style><h1>'+title+'</h1><p>'+html.escape(result['limitation'])+'</p><p>Decision parity: '+cell(parity)+'</p>'+table+'<details><summary>Full measured comparison</summary><pre>'+html.escape(json.dumps(result,indent=2,ensure_ascii=False))+'</pre></details>',encoding='utf-8')
    print(output/'comparison.html')
