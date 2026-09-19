"""
database.py
Quản lý cơ sở dữ liệu SQLite cho Hệ thống Phê duyệt Nghỉ phép (Backend - Người 3).
Sử dụng sqlite3 chuẩn của Python, tự động khởi tạo bảng và nạp dữ liệu nhân viên từ employees.json.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leave_app.db")
EMPLOYEES_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Leave_Application",
    "employees.json"
)


def get_db_connection() -> sqlite3.Connection:
    """Tạo kết nối tới SQLite DB với row_factory dạng dict-like."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Khởi tạo cấu trúc các bảng và nạp dữ liệu ban đầu nếu chưa có."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Bảng Nhân viên (Employees)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            employee_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            department TEXT NOT NULL,
            role TEXT,
            manager_id TEXT,
            remaining_leave_days REAL NOT NULL DEFAULT 12.0,
            status TEXT DEFAULT 'ACTIVE',
            hire_date TEXT
        )
    """)

    # 2. Bảng Đơn Nghỉ Phép (Leave Requests)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leave_requests (
            id TEXT PRIMARY KEY,
            employee_id TEXT NOT NULL,
            employee_name TEXT NOT NULL,
            department TEXT NOT NULL,
            from_date TEXT,
            to_date TEXT,
            workdays INTEGER DEFAULT 0,
            leave_type TEXT NOT NULL,
            reason TEXT,
            handover_person_id TEXT,
            handover_person_name TEXT,
            attachment_type TEXT DEFAULT 'none',
            decision TEXT NOT NULL,
            uncertainty_category TEXT,
            error_code TEXT,
            target_role TEXT,
            actionable_question TEXT,
            quick_action_options TEXT,
            human_readable_explanation TEXT,
            applied_policy_clauses TEXT,
            human_feedback_text TEXT,
            status TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 3. Bảng Nhật Ký Giải Trình (Audit Logs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Nạp dữ liệu ban đầu từ employees.json nếu bảng employees còn trống
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0 and os.path.exists(EMPLOYEES_JSON_PATH):
        with open(EMPLOYEES_JSON_PATH, "r", encoding="utf-8") as f:
            employees_data = json.load(f)
            for emp in employees_data:
                cursor.execute("""
                    INSERT OR IGNORE INTO employees (
                        employee_id, name, email, department, role, 
                        manager_id, remaining_leave_days, status, hire_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    emp.get("employee_id"),
                    emp.get("name"),
                    emp.get("email"),
                    emp.get("department"),
                    emp.get("role"),
                    emp.get("manager_id"),
                    float(emp.get("remaining_leave_days", 12.0)),
                    emp.get("status", "ACTIVE"),
                    emp.get("hire_date")
                ))

    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# CÁC HÀM TIỆN ÍCH TRUY VẤN (DAO)
# -----------------------------------------------------------------------------

def get_employee(employee_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_employees() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM employees ORDER BY department, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_team_absent_count(department: str, target_date: str) -> int:
    """Đếm số nhân sự trong cùng phòng ban đã được duyệt nghỉ vào target_date."""
    conn = get_db_connection()
    query = """
        SELECT COUNT(*) FROM leave_requests
        WHERE department = ?
          AND decision IN ('AUTO_APPROVE', 'APPROVED_BY_HUMAN_OVERRIDE')
          AND from_date <= ? AND to_date >= ?
    """
    row = conn.execute(query, (department, target_date, target_date)).fetchone()
    conn.close()
    return row[0] if row else 0


def get_department_total_members(department: str) -> int:
    """Đếm tổng số nhân sự đang hoạt động của phòng ban."""
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*) FROM employees WHERE department = ? AND status = 'ACTIVE'", (department,)).fetchone()
    conn.close()
    total = row[0] if row else 0
    return max(total, 1)


def save_leave_request(data: Dict[str, Any]):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO leave_requests (
            id, employee_id, employee_name, department, from_date, to_date,
            workdays, leave_type, reason, handover_person_id, handover_person_name,
            attachment_type, decision, uncertainty_category, error_code,
            target_role, actionable_question, quick_action_options,
            human_readable_explanation, applied_policy_clauses,
            human_feedback_text, status, submitted_at, updated_at
        ) VALUES (
            :id, :employee_id, :employee_name, :department, :from_date, :to_date,
            :workdays, :leave_type, :reason, :handover_person_id, :handover_person_name,
            :attachment_type, :decision, :uncertainty_category, :error_code,
            :target_role, :actionable_question, :quick_action_options,
            :human_readable_explanation, :applied_policy_clauses,
            :human_feedback_text, :status, :submitted_at, :updated_at
        )
    """, data)
    conn.commit()
    conn.close()


def add_audit_log(request_id: str, step_name: str, action: str, details: str):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO audit_logs (request_id, step_name, action, details, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (request_id, step_name, action, details, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_leave_request(request_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    if res.get("quick_action_options"):
        try:
            res["quick_action_options"] = json.loads(res["quick_action_options"])
        except Exception:
            pass
    if res.get("applied_policy_clauses"):
        try:
            res["applied_policy_clauses"] = json.loads(res["applied_policy_clauses"])
        except Exception:
            pass
    return res


def get_all_leave_requests(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    if status_filter and status_filter != "ALL":
        rows = conn.execute(
            "SELECT * FROM leave_requests WHERE status = ? ORDER BY submitted_at DESC", 
            (status_filter,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM leave_requests ORDER BY submitted_at DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("quick_action_options"):
            try:
                d["quick_action_options"] = json.loads(d["quick_action_options"])
            except Exception:
                pass
        if d.get("applied_policy_clauses"):
            try:
                d["applied_policy_clauses"] = json.loads(d["applied_policy_clauses"])
            except Exception:
                pass
        result.append(d)
    return result


def get_audit_logs(request_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM audit_logs WHERE request_id = ? ORDER BY id ASC", 
        (request_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def deduct_employee_leave_days(employee_id: str, days: float):
    """Trừ ngày phép năm của nhân sự sau khi đơn được duyệt."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE employees SET remaining_leave_days = MAX(0.0, remaining_leave_days - ?) WHERE employee_id = ?",
        (days, employee_id)
    )
    conn.commit()
    conn.close()


def cancel_leave_request(request_id: str) -> bool:
    """Nhân viên tự hủy đơn khi đơn đang ở trạng thái PENDING_ESCALATION."""
    conn = get_db_connection()
    req = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    if not req:
        conn.close()
        return False
    conn.execute(
        "UPDATE leave_requests SET status = 'CANCELLED', decision = 'CANCELLED_BY_EMPLOYEE', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), request_id)
    )
    conn.execute(
        "INSERT INTO audit_logs (request_id, step_name, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (request_id, "EMPLOYEE_ACTION", "CANCEL_REQUEST", "Nhân viên đã chủ động hủy/thu hồi yêu cầu nghỉ phép", datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True


def override_revoke_auto_approval(request_id: str, reason: str = "Quản lý hủy quyết định tự duyệt của AI") -> bool:
    """Quản lý hủy quyết định tự duyệt của AI và hoàn lại ngày phép nếu có."""
    conn = get_db_connection()
    req = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (request_id,)).fetchone()
    if not req:
        conn.close()
        return False
    
    # Nếu đơn đã trừ ngày phép năm thì hoàn trả
    if req["leave_type"] in ["Annual", "Nghỉ phép năm"] and req["workdays"] and req["workdays"] > 0:
        conn.execute(
            "UPDATE employees SET remaining_leave_days = remaining_leave_days + ? WHERE employee_id = ?",
            (req["workdays"], req["employee_id"])
        )
    
    conn.execute(
        "UPDATE leave_requests SET status = 'REJECTED', decision = 'REVOKED_BY_ADMIN', human_feedback_text = ?, updated_at = ? WHERE id = ?",
        (reason, datetime.now().isoformat(), request_id)
    )
    conn.execute(
        "INSERT INTO audit_logs (request_id, step_name, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (request_id, "ADMIN_OVERRIDE", "REVOKE_AUTO_APPROVAL", f"Quản lý hủy quyết định duyệt của AI: {reason}", datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True


def allocate_leave_days(target_type: str, target_id: Optional[str], days: float, reason: str) -> int:
    """Cấp phát / cộng thêm ngày phép cho nhân viên (Toàn công ty, Phòng ban hoặc Cá nhân)."""
    conn = get_db_connection()
    count = 0
    if target_type == "ALL":
        conn.execute("UPDATE employees SET remaining_leave_days = remaining_leave_days + ? WHERE status = 'ACTIVE'", (days,))
        cursor = conn.execute("SELECT COUNT(*) FROM employees WHERE status = 'ACTIVE'")
        count = cursor.fetchone()[0]
    elif target_type == "DEPARTMENT":
        conn.execute("UPDATE employees SET remaining_leave_days = remaining_leave_days + ? WHERE department = ? AND status = 'ACTIVE'", (days, target_id))
        cursor = conn.execute("SELECT COUNT(*) FROM employees WHERE department = ? AND status = 'ACTIVE'", (target_id,))
        count = cursor.fetchone()[0]
    elif target_type == "EMPLOYEE":
        conn.execute("UPDATE employees SET remaining_leave_days = remaining_leave_days + ? WHERE employee_id = ?", (days, target_id))
        count = 1
    
    conn.commit()
    conn.close()
    return count



