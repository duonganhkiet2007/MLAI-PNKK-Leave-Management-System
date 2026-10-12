from __future__ import annotations
import csv, hashlib, json, os, platform, subprocess, sys, tempfile, time, uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'benchmarks'
ISOLATED_PATHS=set()

def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def command(args):
    try:
        return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=8).strip()
    except (OSError, subprocess.SubprocessError):
        return None

def code_digest():
    h = hashlib.sha256()
    for folder in ('backend', 'core'):
        for p in sorted((ROOT / folder).glob('**/*.py')):
            if any(x in p.parts for x in ('test_env', '.venv', '__pycache__')): continue
            h.update(str(p.relative_to(ROOT)).encode()); h.update(p.read_bytes())
    return h.hexdigest()

def bootstrap(directory):
    """Must precede ANY backend import; refuse non-benchmark DB paths."""
    directory = Path(directory).resolve()
    if not (directory / '.mlai-benchmark-isolated').is_file():
        raise RuntimeError('Isolation marker missing')
    os.environ.update(LEAVE_DB_PATH=str(directory/'evaluation.db'),
        LEAVE_UPLOAD_DIR=str(directory/'uploads'), SEED_DEMO_DATA='false', APP_ENV='test',
        LEAVE_ALLOW_ACTOR_HEADER='true', VLM_WARMUP_ON_STARTUP='0',
        VLM_FORCE_MOCK='0', VLM_ALLOW_MOCK_FALLBACK='0')
    for name in ('backend', 'core'):
        sys.path.insert(0, str(ROOT/name))
    if 'database' in sys.modules:
        import database
        if Path(database.DB_PATH).resolve() != directory/'evaluation.db':
            if Path(database.DB_PATH).resolve() not in ISOLATED_PATHS:
                raise RuntimeError('Backend already imported against a non-benchmark database')
            database.DB_PATH=str(directory/'evaluation.db')
    ISOLATED_PATHS.add(directory/'evaluation.db')

def sandbox():
    tmp = tempfile.TemporaryDirectory(prefix='mlai-benchmark-')
    directory = Path(tmp.name)
    (directory/'.mlai-benchmark-isolated').touch()
    return tmp, directory

def seed_db(count=30):
    import database as db
    empty_people=Path(db.DB_PATH).parent/'synthetic-employees.json'
    dump(empty_people,[])
    db.EMPLOYEES_JSON_PATH=str(empty_people)
    db.init_db()
    c = db.get_db_connection()
    # Seed only a brand new isolated database. Never delete existing records.
    if c.execute('SELECT count(*) FROM employees').fetchone()[0]:
        c.close(); raise RuntimeError('Expected an empty benchmark DB')
    for i in range(max(count*4, 100)):
        c.execute("INSERT INTO employees(employee_id,name,department,remaining_leave_days,status,employment_status) VALUES(?,?,?,100,'ACTIVE','REGULAR')",
            (f'BENCH-{i:03}', f'Benchmark Person {i:03}', 'BENCH-TEAM'))
    for actor, role in [('BENCH-M','DIRECT_MANAGER'),('BENCH-H','DEPARTMENT_HEAD'),('BENCH-HR','HR'),('BENCH-HRD','HRD'),('BENCH-CEO','CEO')]:
        c.execute("INSERT INTO employees(employee_id,name,department,remaining_leave_days,status,employment_status) VALUES(?,?,?,100,'ACTIVE','REGULAR')", (actor, actor, 'BENCH-TEAM'))
        c.execute('INSERT INTO actor_roles VALUES(?,?,?)', (actor,role,'*'))
    c.execute("INSERT INTO employees(employee_id,name,department,remaining_leave_days,status,employment_status) VALUES('BENCH-OTHER','Other Test Person','OTHER-TEAM',100,'ACTIVE','REGULAR')")
    c.commit(); c.close()

def csv_write(path, rows, defaults):
    fields = list(dict.fromkeys(defaults + [k for row in rows for k in row]))
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})

class Run:
    def __init__(self, config, label='evaluation'):
        self.config=config
        self.id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        self.path=BENCH/'results'/self.id; self.path.mkdir(parents=True)
        self.started=time.perf_counter()
        self.requests=[]; self.inference=[]; self.correctness=[]; self.batches=[]
        self.sections={}
        self.metadata={
            'run_id':self.id,'label':label,'timestamp':datetime.now(timezone.utc).isoformat(),
            'config':config,'git_commit':command(['git','rev-parse','HEAD']),
            'working_tree_dirty':bool(command(['git','status','--porcelain'])),
            'source_sha256':code_digest(), 'dataset_sha256':sha(BENCH/'datasets/applications.json'),
            'annotations_sha256':sha(BENCH/'datasets/proof_annotations.json'),
            'ground_truth_sha256':sha(BENCH/'datasets/ground_truth.json'),
            'policy_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'core/policy_rules.md',ROOT/'core/raw_policy.json']},
            'hardware':{'platform':platform.platform(),'cpu':platform.processor(), 'logical_cpus':os.cpu_count(),
                'gpu':command(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader']),
                'memory':command(['getconf','_PHYS_PAGES'])},
            'models':command(['ollama','list']), 'python':sys.version,
            'timing_kind':'real API/SQLite timings; mocked inference' if config['model_mode']=='mock' else 'real API/SQLite/model timings',
            'safety':'new temporary SQLite database; synthetic test identities and documents only',
        }
    def finish(self):
        from benchmarks.metrics.aggregate import aggregate
        from benchmarks.reports.generate_report import generate
        self.metadata['duration_seconds']=time.perf_counter()-self.started
        self.sections['performance']=aggregate(self.requests,self.batches,self.config['seed'])
        counts={k:sum(r['status']==k for r in self.correctness) for k in ('passed','failed','skipped')}
        summary={'run_id':self.id,'tests':counts,**self.sections,'batches':self.batches}
        if self.requests:
            from collections import Counter
            summary['load_summary']={'requests':len(self.requests),'unfinished':sum(not r.get('outcome_reached',False) for r in self.requests),
                'automatic_outcome_rate':sum(r.get('outcome_reached',False) for r in self.requests)/len(self.requests),
                'timeouts':sum(r.get('timeout',False) for r in self.requests),
                'http_status_distribution':dict(Counter(str(r.get('status_code')) for r in self.requests)),
                'error_distribution':dict(Counter(r['error'] for r in self.requests if r.get('error')))}
        dump(self.path/'metadata.json',self.metadata); dump(self.path/'summary.json',summary)
        csv_write(self.path/'requests.csv',self.requests,['case_id','scenario','concurrency','status_code','ack_ms','final_ms'])
        csv_write(self.path/'inference.csv',self.inference,['case_id','model','client_ms','queue_ms','mode'])
        csv_write(self.path/'correctness.csv',self.correctness,['case_id','suite','status','expected','actual','policy_reference','severity'])
        dump(self.path/'failures.json',[r for r in self.correctness if r['status']!='passed']+
            [r for r in self.requests if r.get('error')])
        generate(self.path,summary,self.metadata,self.requests,self.correctness)
        print(f'Run: {self.path}\nTests: {counts}')
        return self.path
