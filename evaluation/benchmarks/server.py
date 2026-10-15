"""Benchmark-only process. No production endpoint or logic is modified."""
import argparse, os, threading, time
from pathlib import Path
from evaluation.benchmarks.common import bootstrap, read, seed_db

def create(directory,config):
    bootstrap(directory)
    os.environ['VLM_OLLAMA_BASE']=config['ollama_base']
    os.environ['OLLAMA_BASE']=config['ollama_base']
    os.environ['VLM_TARGET_MODEL']=config['vlm_model']
    os.environ['VLM_MAX_IMAGE_DIM']=str(config['vlm_max_image_dim'])
    import database, vlm_inspector as vi
    seed_db(max(config['concurrency_levels']))
    vi._VLM_CACHE_MEM.clear()
    if config['model_mode']=='mock':
        original=vi.inspect_document_with_vlm
        def synthetic(**kw):
            if kw.get('mock_data'):
                return original(**kw)
            path=kw.get('attachment_path_or_type')
            import database as db
            with db.get_db_connection() as conn:
                row=conn.execute('SELECT employee_id,proof_type FROM proof_documents WHERE storage_name=?',(Path(path).name,)).fetchone()
            index=int(row['employee_id'].split('-')[-1]) if row else 0
            time.sleep(config['mock_inference_seconds'])
            kw['mock_data']={'doc_patient_name':f'Benchmark Person {index:03}','doc_diagnosis':'Synthetic supporting reason',
                'has_red_stamp':True,'has_doctor_signature':True,'days_granted_by_doctor':2,
                'proof_extra':{'proof_type':row['proof_type'] if row else 'MEDICAL_LEAVE_CERTIFICATE',
                    'issuer':'Synthetic Evaluation Clinic','issue_date':'2026-09-13','recommended_from_date':'2026-09-14',
                    'recommended_to_date':'2026-09-15','signature_present':True,'document_readability':'READABLE'}}
            out=original(**kw); out.vlm_analysis_json['inspection_mode']='BENCHMARK_MOCK'
            return out
        vi.inspect_document_with_vlm=synthetic
    from main import app
    import routers.leave_router as router
    from services.orchestration import LeaveOrchestratorService
    from datetime import datetime
    router.service=LeaveOrchestratorService(clock=lambda:datetime.fromisoformat(config['reference_time']))
    from metrics import GLOBAL_METRICS
    GLOBAL_METRICS.reset()
    from evaluation.benchmarks.metrics.collectors import Collector
    collector=Collector(config['model_mode'])
    collector.install()
    @app.get('/__benchmark/snapshot',include_in_schema=False)
    def snapshot():
        with database.get_db_connection() as conn:
            jobs=[dict(r) for r in conn.execute('SELECT id,proof_id,status,created_at,started_at,completed_at,retry_count FROM proof_inspection_jobs')]
            proofs=[dict(r) for r in conn.execute('SELECT id,file_sha256,inspection_status FROM proof_documents')]
            counts={t:conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('leave_requests','audit_logs','leave_transactions')}
        return {'metrics':GLOBAL_METRICS.get_summary(),'jobs':jobs,'proofs':proofs,'counts':counts,'events':collector.snapshot()}
    return app

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--config',required=True);p.add_argument('--port',type=int,required=True)
    a=p.parse_args()
    import uvicorn
    uvicorn.run(create(a.directory,read(a.config)),host='127.0.0.1',port=a.port,log_level='warning')
