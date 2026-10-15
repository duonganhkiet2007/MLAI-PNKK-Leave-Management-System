import json, time, unicodedata, re, os
from datetime import date
from evaluation.benchmarks.common import BENCH, read, sandbox, bootstrap, seed_db, dump
from evaluation.benchmarks.datasets.proofs import document, QUALITIES
from evaluation.benchmarks.metrics.aggregate import classification, stats

def normalize(v):
    if v is None:return None
    if isinstance(v,bool):return v
    text=unicodedata.normalize('NFKC',str(v)).casefold()
    return re.sub(r'\s+',' ',text).strip()

def field_metrics(pairs):
    present=[(e,a) for e,a in pairs if e is not None];absent=[(e,a) for e,a in pairs if e is None]
    tp=sum(normalize(e)==normalize(a) for e,a in present)
    predicted=sum(a is not None for e,a in pairs)
    precision=tp/predicted if predicted else None;recall=tp/len(present) if present else None
    return {'n':len(pairs),'present_ground_truth':len(present),'absent_ground_truth':len(absent),
        'exact_match':sum(e==a for e,a in present)/len(present) if present else None,
        'normalized_match':tp/len(present) if present else None,
        'precision':precision,'recall':recall,'f1':(2*precision*recall/(precision+recall) if precision+recall else 0) if precision is not None and recall is not None else None,
        'missing_rate':sum(a is None for e,a in present)/len(present) if present else None,
        'hallucinated_field_rate':sum(a is not None for e,a in absent)/len(absent) if absent else None}

def run_vlm(run,live=False):
    if not live:
        run.correctness.append({'case_id':'vlm-real-suite','suite':'vlm','status':'skipped','reason':'Resource-intensive VLM requires --live-vlm; mocked output is never scored as model accuracy'})
        run.sections['vlm']={'measured':False,'classification':None,'fields':None,'reason':'Opt-in real inference not run'}
        return
    tmp,directory=sandbox();sampler=None
    try:
        bootstrap(directory)
        os.environ['VLM_TARGET_MODEL']=run.config['vlm_model'];os.environ['VLM_OLLAMA_BASE']=run.config['ollama_base']
        seed_db()
        import vlm_inspector as vi
        vi._VLM_CACHE_MEM.clear()
        from evaluation.benchmarks.metrics.collectors import Collector,GPUSampler
        collector=Collector('real');collector.install()
        sampler=GPUSampler();sampler.start()
        pairs={};classes_e=[];classes_a=[];quality_metrics={};rows=[]
        for annotation in read(BENCH/'datasets/proof_annotations.json'):
            for quality in QUALITIES+['prompt_injection']:
                index=int(annotation['id'].split('-')[-1]);path=directory/f'{annotation["id"]}-{quality}.png'
                path.write_bytes(document(index,annotation['proof_type'],quality))
                case_id=f'{annotation["id"]}-{quality}';t=time.perf_counter()
                row={'case_id':case_id,'suite':'vlm','mode':'real','quality':quality,'severity':'critical' if quality=='prompt_injection' else 'major'}
                try:
                    out=vi.inspect_document_with_vlm(leave_type='SPECIAL_PAID' if annotation['proof_type']=='MARRIAGE_CERTIFICATE' else 'SICK_MEDICAL',
                        employee_name=annotation['patient_name'],attachment_path_or_type=str(path),from_date=date(2026,9,14),to_date=date(2026,9,15),allow_mock_fallback=False)
                    actual=out.proof_extraction.model_dump(mode='json');actual['has_red_stamp']=out.has_red_stamp;actual['diagnosis']=out.doc_diagnosis
                    valid=not out.vlm_error;elapsed=(time.perf_counter()-t)*1000
                    # Only original and injection have verified readable labels. Corruptions have no subjective readability labels.
                    scored_fields=[k for k in actual if k in annotation and k not in ('document_readability',)]
                    if quality=='occluded':scored_fields=[k for k in scored_fields if k not in ('issue_date','recommended_from_date','recommended_to_date')]
                    if quality in ('original','prompt_injection'):scored_fields.append('document_readability')
                    expected={k:annotation[k] for k in scored_fields}
                    ok=valid and all(normalize(actual.get(k))==normalize(v) for k,v in expected.items())
                    row.update(status='passed' if ok else 'failed',expected=expected,actual={k:actual.get(k) for k in scored_fields},
                        json_schema_valid=True,inference_ok=valid,inspection_mode=out.vlm_analysis_json.get('inspection_mode'),latency_ms=elapsed,
                        reason='Synthetic image robustness; post-transform readability ground truth not asserted')
                    classes_e.append(annotation['proof_type']);classes_a.append(actual['proof_type'])
                    for k,v in expected.items():pairs.setdefault(k,[]).append((v,actual.get(k)))
                    quality_metrics.setdefault(quality,[]).append(ok)
                    # Score only actual observable fields; original payload source excludes legitimate unknown corruption fields.
                except Exception as e:row.update(status='failed',actual=type(e).__name__,json_schema_valid=False,inference_ok=False)
                run.correctness.append(row);rows.append(row)
                print(f'VLM {case_id}: {row["status"]}',flush=True)
        for e in collector.snapshot():
            if e['kind']=='ollama':run.inference.append(e)
        sampler.close();dump(run.path/'gpu_samples.json',sampler.rows)
        run.sections['vlm']={'measured':True,'classification':classification(classes_e,classes_a),
            'fields':{k:field_metrics(v) for k,v in pairs.items()},
            'robustness':{q:{'n':len(v),'all_fields_match_rate':sum(v)/len(v)} for q,v in quality_metrics.items()},
            'schema_success_rate':sum(r.get('json_schema_valid',False) for r in rows)/len(rows),
            'schema_scope':'Normalized existing ProofExtraction schema; raw model schema not exposed',
            'timeout_rate':sum('Timeout' in str(r.get('actual')) for r in rows)/len(rows),
            'raw_json_valid_rate':sum(e.get('raw_json_valid',False) for e in collector.snapshot() if e['kind']=='ollama')/sum(e['kind']=='ollama' for e in collector.snapshot()) if any(e['kind']=='ollama' for e in collector.snapshot()) else None,
            'gpu_samples':len(sampler.rows),'correlation':None,'limitation':'Synthetic printed documents and corruptions are not representative of real medical records. GPU samples include any other users sharing this GPU. No model-generated annotations.'}
    finally:
        if sampler:sampler.close()
        tmp.cleanup()
