import copy,pytest
from evaluation.benchmarks.reports.compare import check
from evaluation.benchmarks.common import BENCH,read

def meta():return {'config':read(BENCH/'config.json'),'dataset_sha256':'a','annotations_sha256':'b','policy_sha256':{},'hardware':{},'models':'test'}

def test_comparison_rejects_different_cache_workload_model_or_hardware():
    a=meta()
    for field,value in [('cache_policy','warm'),('seed',999),('model_mode','real'),('arrival','staggered')]:
        b=copy.deepcopy(a);b['config'][field]=value
        with pytest.raises(ValueError,match='Incomparable'):check(a,b)
    b=copy.deepcopy(a);b['hardware']={'gpu':'different'}
    with pytest.raises(ValueError):check(a,b)

def test_comparison_accepts_same_experiment_different_build():
    a=meta();b=copy.deepcopy(a);a['git_commit']='baseline';b['git_commit']='optimized'
    check(a,b)
