from evaluation.benchmarks.metrics.aggregate import stats,classification
from evaluation.benchmarks.runners.vlm_eval import field_metrics
from evaluation.benchmarks.runners.load_test import distribution,OUTCOMES,FINAL
from evaluation.benchmarks.common import read,BENCH,bootstrap
import pytest

def test_empty_statistics_are_na():
    assert stats([])['p99_ms'] is None

def test_quantiles_and_classification():
    assert stats([0,10])['p50_ms']==5
    result=classification(['A','A','B'],['A','B','B'])
    assert result['confusion_matrix']['A']['B']==1
    assert result['accuracy']==pytest.approx(2/3)

def test_legitimate_absence_separate_from_missing():
    result=field_metrics([(None,None),(None,'invented'),('required',None),('a','a')])
    assert result['hallucinated_field_rate']==.5
    assert result['missing_rate']==.5

def test_all_wrong_present_fields_have_zero_f1():
    assert field_metrics([('expected','wrong')])['f1']==0

def test_workload_exact_counts():
    c=read(BENCH/'config.json')
    kinds=distribution('mixed',20,c)
    assert [kinds.count(x) for x in ('no_proof','ready','cold')]==[10,5,5]
    assert distribution('contention',20,c).count('cold')==10

def test_202_and_human_wait_are_not_business_completion():
    assert 'PROCESSING' not in OUTCOMES
    assert 'PENDING_ESCALATION' in OUTCOMES and 'PENDING_ESCALATION' not in FINAL

def test_isolation_requires_marker(tmp_path):
    with pytest.raises(RuntimeError,match='marker'):bootstrap(tmp_path)

def test_dataset_integrity():
    cases=read(BENCH/'datasets/applications.json');truth=read(BENCH/'datasets/ground_truth.json')
    assert len(cases)==110
    assert len(set(c['id'] for c in cases))==110
    assert all(c['id'] in truth and c['synthetic'] for c in cases)
