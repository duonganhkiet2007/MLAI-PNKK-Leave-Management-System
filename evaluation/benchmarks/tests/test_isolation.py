import subprocess,sys
from evaluation.benchmarks.common import ROOT

def test_can_switch_only_between_registered_sandboxes():
    source='''
from evaluation.benchmarks.common import sandbox,bootstrap,seed_db
a,pa=sandbox();b,pb=sandbox()
try:
    bootstrap(pa);seed_db()
    import database
    first=database.DB_PATH
    bootstrap(pb);seed_db()
    assert database.DB_PATH!=first
    assert database.get_db_connection().execute('SELECT count(*) FROM leave_requests').fetchone()[0]==0
finally:
    a.cleanup();b.cleanup()
'''
    r=subprocess.run([sys.executable,'-c',source],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stdout+r.stderr
