"""Employee administration. Deactivation preserves leave history and test fixtures."""
import json
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from routers.leave_router import actor
import storage as st

router = APIRouter(prefix='/api/management', tags=['Employee management'])
DEPARTMENTS = ('Engineering', 'Marketing & Operations')
# Lock identities from the original seed dataset, not names or ID prefixes.
ORIGINAL_EMPLOYEE_IDS = frozenset(
    e['employee_id'] for e in json.loads(Path(st.db.EMPLOYEES_JSON_PATH).read_text(encoding='utf8'))
)

OPEN_STATES = ('PROCESSING', 'PENDING_INSPECTION', 'PENDING_ESCALATION', 'WAITING_EMPLOYEE', 'PENDING_HANDOVER')

class NewEmployee(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    department: Literal['Engineering', 'Marketing & Operations']
    job_title: str = Field(default='Nhân viên', min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=120)

    @field_validator('email')
    @classmethod
    def clean_email(cls, value):
        value = (value or '').strip().lower()
        if not value:
            return None
        if not re.fullmatch(r'[^\s@<>"`]+@[^\s@<>"`]+\.[^\s@<>"`]+', value):
            raise ValueError('Email không đúng định dạng (ví dụ: ten@gmail.com).')
        return value

    @field_validator('name', 'job_title')
    @classmethod
    def clean_name(cls, value):
        value = ' '.join(value.split())
        if not value or any(ord(c) < 32 or c in '<>"`' for c in value):
            raise ValueError('Tên và chức danh phải là văn bản hợp lệ, không chứa ký tự HTML.')
        return value

class EmployeeJobTitle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    job_title: str = Field(min_length=1, max_length=100)

    @field_validator('job_title')
    @classmethod
    def clean_title(cls, value):
        return NewEmployee.clean_name(value)

def permitted_departments(conn, actor_id):
    roles = st.roles_for(conn, actor_id)
    allowed = [dept for dept in DEPARTMENTS if any(
        r['role'] in {'DIRECT_MANAGER', 'DEPARTMENT_HEAD', 'HR', 'HRD', 'CEO'}
        and r['department_scope'] in ('*', dept) for r in roles)]
    if not allowed:
        raise st.AccessDenied('Chỉ người quản lý hoặc HR có quyền quản lý nhân viên.')
    return allowed

def require_department(conn, actor_id, department):
    if department not in permitted_departments(conn, actor_id):
        raise st.AccessDenied('Bạn không có quyền quản lý nhân viên của phòng ban này.')

def serialized(conn, row, actor_id):
    data = dict(row)
    data['actor_roles'] = [dict(r) for r in conn.execute(
        'SELECT role, department_scope FROM actor_roles WHERE employee_id=?', (data['employee_id'],))]
    data['can_delete'] = data['status'] == 'ACTIVE' and not data['actor_roles'] and data['employee_id'] != actor_id
    data['can_edit'] = data['can_delete']
    data['is_test_employee'] = data['employee_id'] in ORIGINAL_EMPLOYEE_IDS
    data['delete_lock_reason'] = ('Nhân viên thuộc dataset kiểm thử gốc, không được xóa.'
                                  if data['is_test_employee'] else 'Giữ tài khoản quản lý để duyệt đơn.' if not data['can_delete'] else '')
    data['can_delete'] = data['can_delete'] and not data['is_test_employee']
    return data

@router.get('/employees')
def list_managed_employees(actor_id=Depends(actor)):
    with st.readonly_connection() as conn:
        departments = permitted_departments(conn, actor_id)
        rows = conn.execute('SELECT * FROM employees WHERE status=\'ACTIVE\' AND department IN (' +
            ','.join('?' for _ in departments) + ') ORDER BY department, name, employee_id', departments).fetchall()
        return {'success': True, 'data': [serialized(conn, r, actor_id) for r in rows],
                'departments': departments, 'total': len(rows)}

@router.post('/employees', status_code=201)
def add_employee(payload: NewEmployee, actor_id=Depends(actor)):
    with st.transaction() as conn:
        require_department(conn, actor_id, payload.department)
        manager = conn.execute('''SELECT e.employee_id FROM actor_roles r JOIN employees e ON e.employee_id=r.employee_id
            WHERE e.status='ACTIVE' AND r.role='DIRECT_MANAGER' AND r.department_scope IN (?, '*')
            ORDER BY CASE WHEN r.department_scope=? THEN 0 ELSE 1 END, e.employee_id LIMIT 1''',
            (payload.department, payload.department)).fetchone()
        if payload.email and conn.execute("SELECT 1 FROM employees WHERE status='ACTIVE' AND lower(email)=?",
                                          (payload.email,)).fetchone():
            raise st.Conflict('Email này đã được dùng cho một nhân viên khác.')
        eid = 'EMPNEW-' + uuid.uuid4().hex[:12].upper()
        today = datetime.now(st.CalendarService().timezone).date().isoformat()
        # Existing employee schema defaults to 12 annual days. No fixture/JSON is changed.
        conn.execute('''INSERT INTO employees(employee_id,name,email,department,role,manager_id,
            remaining_leave_days,status,employment_status,hire_date,employment_start_date)
            VALUES(?,?,?,?,?,?,12,'ACTIVE','REGULAR',?,?)''',
            (eid, payload.name, payload.email, payload.department, payload.job_title,
             manager['employee_id'] if manager else None, today, today))
        st.audit(conn, 'EMPLOYEE-' + eid, 'EMPLOYEE_CREATED',
                 json.dumps({'actor_id': actor_id, 'department': payload.department}, ensure_ascii=False))
        row = conn.execute('SELECT * FROM employees WHERE employee_id=?', (eid,)).fetchone()
        return {'success': True, 'data': serialized(conn, row, actor_id)}

@router.patch('/employees/{employee_id}')
def update_employee_job_title(employee_id: str, payload: EmployeeJobTitle, actor_id=Depends(actor)):
    with st.transaction() as conn:
        permitted_departments(conn, actor_id)
        row = conn.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
        if not row:
            raise LookupError('Không tìm thấy nhân viên.')
        require_department(conn, actor_id, row['department'])
        if not serialized(conn, row, actor_id)['can_edit']:
            raise st.Conflict('Chỉ sửa chức danh của nhân viên đang hoạt động; tài khoản quản lý được giữ nguyên.')
        # role is the existing display field. Permission remains exclusively in actor_roles.
        conn.execute('UPDATE employees SET role=? WHERE employee_id=?', (payload.job_title, employee_id))
        st.audit(conn, 'EMPLOYEE-' + employee_id, 'EMPLOYEE_TITLE_UPDATED',
                 json.dumps({'actor_id': actor_id}, ensure_ascii=False))
        updated = conn.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
        return {'success': True, 'data': serialized(conn, updated, actor_id)}

@router.delete('/employees/{employee_id}')
def deactivate_employee(employee_id: str, actor_id=Depends(actor)):
    with st.transaction() as conn:
        permitted_departments(conn, actor_id)
        row = conn.execute('SELECT * FROM employees WHERE employee_id=?', (employee_id,)).fetchone()
        if not row:
            raise LookupError('Không tìm thấy nhân viên.')
        require_department(conn, actor_id, row['department'])
        if row['status'] != 'ACTIVE':
            raise st.Conflict('Nhân viên này đã được xóa khỏi danh sách hoạt động.')
        if employee_id in ORIGINAL_EMPLOYEE_IDS:
            raise st.Conflict('Nhân viên thuộc dataset kiểm thử gốc, không được xóa.')
        if employee_id == actor_id or conn.execute('SELECT 1 FROM actor_roles WHERE employee_id=?', (employee_id,)).fetchone():
            raise st.Conflict('Không xóa tài khoản quản lý hoặc người duyệt đơn ở màn hình này.')
        pending = conn.execute('SELECT 1 FROM leave_requests WHERE employee_id=? AND status IN (' +
            ','.join('?' for _ in OPEN_STATES) + ') LIMIT 1', (employee_id, *OPEN_STATES)).fetchone()
        # Người được chỉ định nhận bàn giao ở bất kỳ đơn nào chưa xong (kể cả đơn còn chờ duyệt) cũng phải giữ lại.
        handover = conn.execute('SELECT 1 FROM leave_requests WHERE handover_person_id=? AND status IN (' +
            ','.join('?' for _ in OPEN_STATES) + ') LIMIT 1', (employee_id, *OPEN_STATES)).fetchone()
        jobs = conn.execute("SELECT 1 FROM proof_inspection_jobs WHERE employee_id=? AND status IN ('PENDING','PROCESSING') LIMIT 1", (employee_id,)).fetchone()
        if pending or handover or jobs:
            raise st.Conflict('Nhân viên còn đơn nghỉ, bàn giao hoặc chứng từ đang xử lý. Vui lòng giải quyết trước khi xóa.')
        conn.execute("UPDATE employees SET status='INACTIVE' WHERE employee_id=?", (employee_id,))
        st.audit(conn, 'EMPLOYEE-' + employee_id, 'EMPLOYEE_DEACTIVATED',
                 json.dumps({'actor_id': actor_id, 'department': row['department']}, ensure_ascii=False))
        return {'success': True, 'data': {'employee_id': employee_id, 'status': 'INACTIVE'}}
