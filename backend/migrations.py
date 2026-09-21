"""Additive, versioned migrations. Existing employee balances are never rewritten."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1

def backup_if_needed(path):
    path = Path(path)
    if not path.exists(): return None
    src = sqlite3.connect(str(path))
    exists = src.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
    applied = exists and src.execute('SELECT 1 FROM schema_migrations WHERE version=?',(VERSION,)).fetchone()
    if applied:
        src.close(); return None
    directory = path.parent / 'backups'
    directory.mkdir(exist_ok=True)
    target = directory / f'{path.stem}-before-v{VERSION}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.db'
    dst = sqlite3.connect(target)
    src.backup(dst); dst.close(); src.close()
    return str(target)

def migrate(conn):
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)')
        if conn.execute('SELECT 1 FROM schema_migrations WHERE version=?',(VERSION,)).fetchone():
            conn.commit(); return
        additions = {
          'employees': {'employment_start_date':'TEXT','probation_start_date':'TEXT','probation_end_date':'TEXT',
                        'employment_status':'TEXT','calendar_review_required':'INTEGER NOT NULL DEFAULT 0'},
          'leave_requests': {'canonical_leave_type':'TEXT','reason_category':'TEXT','requested_calendar_days':'INTEGER',
            'requested_working_days':'INTEGER','deducted_days':'REAL NOT NULL DEFAULT 0','annual_balance_change':'REAL NOT NULL DEFAULT 0',
            'facts_json':'TEXT','proof_id':'TEXT','decision_trace':'TEXT','result_json':'TEXT',
            'revision':'INTEGER NOT NULL DEFAULT 0','human_resolution':'TEXT',
            'legacy_reconciliation_required':'INTEGER NOT NULL DEFAULT 1','policy_version':'TEXT'}
        }
        for table, fields in additions.items():
            current={r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
            for name,kind in fields.items():
                if name not in current: conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
        statements = [
          '''CREATE TABLE proof_documents (
            id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, storage_name TEXT NOT NULL,
            original_name TEXT NOT NULL, mime_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
            proof_type TEXT NOT NULL, proof_verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            issuer TEXT, patient_name TEXT, issue_date TEXT, recommended_from_date TEXT, recommended_to_date TEXT,
            signature_present INTEGER, digital_signature_present INTEGER, document_readability TEXT NOT NULL DEFAULT 'UNKNOWN',
            verification_notes TEXT, verified_by TEXT, facts_json TEXT NOT NULL, created_at TEXT NOT NULL)''',
          '''CREATE TABLE approval_steps (
            request_id TEXT NOT NULL, revision INTEGER NOT NULL, step_index INTEGER NOT NULL,
            role TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', approver_id TEXT, decided_at TEXT,
            PRIMARY KEY(request_id, revision, step_index))''',
          '''CREATE TABLE leave_transactions (
            id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, employee_id TEXT NOT NULL,
            leave_date TEXT, kind TEXT NOT NULL CHECK(kind IN ('DEBIT','REFUND','ALLOCATION')),
            amount REAL NOT NULL, debit_id INTEGER UNIQUE REFERENCES leave_transactions(id),
            reversed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            CHECK((kind='DEBIT' AND amount=-1 AND leave_date IS NOT NULL) OR
                  (kind='REFUND' AND amount=1 AND debit_id IS NOT NULL) OR
                  (kind='ALLOCATION' AND amount>0)))''',
          '''CREATE UNIQUE INDEX active_annual_day ON leave_transactions(employee_id,leave_date)
             WHERE kind='DEBIT' AND reversed=0''',
          '''CREATE TABLE leave_bookings (
            request_id TEXT NOT NULL, employee_id TEXT NOT NULL, leave_date TEXT NOT NULL,
            canonical_leave_type TEXT NOT NULL, PRIMARY KEY(employee_id,leave_date))''',
          '''CREATE TABLE actor_roles (
            employee_id TEXT NOT NULL, role TEXT NOT NULL, department_scope TEXT NOT NULL DEFAULT '*',
            PRIMARY KEY(employee_id,role,department_scope))'''
        ]
        for sql in statements: conn.execute(sql)
        # Exact known role titles, no LLM inference. Unknown titles need explicit configuration.
        mapping={'Chief Executive Officer (CEO)':'CEO', 'Chief Executive Officer (Boss)':'CEO',
                 'Engineering Manager':'DIRECT_MANAGER', 'Marketing & Operations Manager':'DIRECT_MANAGER'}
        for row in conn.execute('SELECT employee_id,role,department FROM employees').fetchall():
            role=mapping.get(row['role'])
            if role:
                scope='*' if role in {'CEO'} else row['department']
                conn.execute('INSERT OR IGNORE INTO actor_roles VALUES(?,?,?)',(row['employee_id'],role,scope))
        conn.execute('INSERT INTO schema_migrations VALUES(?,?)',(VERSION,datetime.now(timezone.utc).isoformat()))
        conn.commit()
    except Exception:
        conn.rollback(); raise
