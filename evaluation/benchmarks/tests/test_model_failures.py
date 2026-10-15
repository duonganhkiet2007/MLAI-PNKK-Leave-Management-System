import pytest
from pathlib import Path

def test_actual_vlm_json_parser_rejects_invalid_model_output(bench_db,monkeypatch,tmp_path):
    import vlm_inspector as vi
    from evaluation.benchmarks.datasets.proofs import document
    path=tmp_path/'invalid-parser.png';path.write_bytes(document())
    monkeypatch.setattr(vi,'_ollama_reachable',lambda:True)
    monkeypatch.setattr(vi,'_ollama_loaded_models',lambda:[vi.VLM_TARGET_MODEL])
    monkeypatch.setattr(vi,'detect_image_blur',lambda *a,**kw:(False,1000))
    monkeypatch.setattr(vi,'ollama_generate',lambda *a,**kw:{'response':'not valid JSON'})
    result,error=vi._try_ollama_extract(str(path),'SICK_MEDICAL')
    assert result is None and error and 'JSON' in error

def test_api_status_polling_does_not_disclose_sensitive_model_error(bench_db,bench_client):
    from evaluation.benchmarks.tests.test_reliability import add_proof
    sentinel='SYNTHETIC-MEDICAL-CONTENT-NOT-FOR-ERRORS'
    pid=add_proof(bench_db)
    c=bench_db.get_db_connection();c.execute("UPDATE proof_documents SET inspection_status='FAILED',vlm_error=? WHERE id=?",('Parse failed: '+sentinel,pid));c.commit();c.close()
    response=bench_client.get('/api/leave/proofs/'+pid+'/status',headers={'X-Actor-ID':'BENCH-000'})
    assert response.status_code==200
    assert sentinel not in response.text,'Status errors should be sanitized instead of exposing raw model text'
