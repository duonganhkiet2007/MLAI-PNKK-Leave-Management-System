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

DB_PATH = os.getenv("LEAVE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "leave_app.db"))
EMPLOYEES_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Leave_Application",
    "employees.json"
)


def get_db_connection() -> sqlite3.Connection:
    """Tạo kết nối tới SQLite DB với row_factory dạng dict-like và bật WAL mode cho đa luồng."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _init_legacy_schema():
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
            updated_at TEXT NOT NULL,
            vlm_analysis_json TEXT,
            llm_summary_json TEXT,
            doc_patient_name TEXT,
            doc_diagnosis TEXT,
            has_red_stamp INTEGER,
            has_doctor_signature INTEGER,
            is_tampered INTEGER,
            ai_edited INTEGER,
            days_granted_by_doctor INTEGER,
            correlation_score REAL,
            correlation_issues TEXT,
            persona_role_used TEXT,
            escalation_reasons_json TEXT
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

    # ============================================================
    # AUTO-MIGRATION: thêm các cột VLM + LLM nếu DB cũ chưa có
    # (Trường hợp file leave.db tạo từ schema cũ, chưa có 11 cột VLM
    #  + cột llm_summary_json → save_record sẽ bỏ lặng các field
    #  này đi, Manager panel thấy None/null toàn bộ.)
    # ============================================================
    AUTO_MIGRATE_LEAVE_COLUMNS = [
        ("vlm_analysis_json",        "TEXT"),
        ("llm_summary_json",         "TEXT"),
        ("doc_patient_name",         "TEXT"),
        ("doc_diagnosis",            "TEXT"),
        ("has_red_stamp",            "INTEGER"),
        ("has_doctor_signature",     "INTEGER"),
        ("is_tampered",              "INTEGER"),
        ("ai_edited",                "INTEGER"),
        ("days_granted_by_doctor",   "INTEGER"),
        ("correlation_score",        "REAL"),
        ("correlation_issues",       "TEXT"),
        ("persona_role_used",        "TEXT"),
        ("escalation_reasons_json",  "TEXT"),
        ("facts_json",               "TEXT"),
        ("result_json",              "TEXT"),
        ("decision_trace",           "TEXT"),
        ("canonical_leave_type",     "TEXT"),
        ("reason_category",          "TEXT"),
        ("proof_id",                 "TEXT"),
        ("requested_calendar_days",  "INTEGER"),
        ("requested_working_days",   "INTEGER"),
        ("deducted_days",            "INTEGER DEFAULT 0"),
        ("annual_balance_change",    "INTEGER DEFAULT 0"),
        ("policy_version",           "TEXT"),
        ("legacy_reconciliation_required", "INTEGER DEFAULT 1"),
        ("revision",                 "INTEGER DEFAULT 1"),
        ("human_resolution",         "TEXT"),
    ]
    existing_cols = {r[1].lower() for r in conn.execute("PRAGMA table_info(leave_requests)").fetchall()}
    for (col_name, col_type) in AUTO_MIGRATE_LEAVE_COLUMNS:
        if col_name.lower() not in existing_cols:
            try:
                conn.execute(f"ALTER TABLE leave_requests ADD COLUMN {col_name} {col_type}")
                print(f"[AUTO-MIGRATION DB] Đã thêm cột {col_name} ({col_type}) vào leave_requests.")
            except Exception as e:
                print(f"[AUTO-MIGRATION DB][WARNING] Không thêm được cột {col_name}: {e}")
    conn.commit()

    # Tương tự migration cho bảng proof_documents (nếu chưa có cột storage_path / file_real_path)
    AUTO_MIGRATE_PROOF_COLUMNS = [
        ("storage_path",         "TEXT"),
        ("file_real_path",       "TEXT"),
        ("original_filename",    "TEXT"),
        ("mime_type",            "TEXT"),
        ("file_size_bytes",      "INTEGER"),
        ("uploaded_by",          "TEXT"),
        ("document_readability", "TEXT"),
        ("signature_present",    "INTEGER"),
        ("digital_signature_present", "INTEGER"),
    ]
    try:
        existing_proof_cols = {r[1].lower() for r in conn.execute("PRAGMA table_info(proof_documents)").fetchall()}
        for (col_name, col_type) in AUTO_MIGRATE_PROOF_COLUMNS:
            if col_name.lower() not in existing_proof_cols:
                try:
                    conn.execute(f"ALTER TABLE proof_documents ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
        conn.commit()
    except Exception:
        pass

    conn.close()


def seed_demo_request():
    """Tự động nạp 5 đơn demo cho 5 nhân viên khác nhau nếu bảng leave_requests còn trống."""
    if os.getenv("SEED_DEMO_DATA", "true").lower() in ("false", "0", "no") or os.getenv("APP_ENV") == "test":
        return
    conn = get_db_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM leave_requests").fetchone()[0]
        if count == 0:
            now = datetime.now().isoformat()
            cases = [
                {
                    "id": "REQ-2026-001-AN", "employee_id": "EMP012", "employee_name": "Nguyễn Văn An", "department": "Engineering",
                    "from_date": "2026-09-22", "to_date": "2026-09-22", "workdays": 1, "leave_type": "SICK_MEDICAL",
                    "reason": "Bị sốt phát ban và cảm cúm, cần nghỉ ngơi và theo dõi sức khỏe tại nhà.",
                    "handover_person_id": "EMP015", "handover_person_name": "Đỗ Hoàng Long", "attachment_type": "none",
                    "decision": "ESCALATE", "uncertainty_category": "AUTHORITY_ESCALATION", "error_code": "DURATION_OVER_AI_LIMIT",
                    "target_role": "DIRECT_MANAGER",
                    "actionable_question": "Quản lý Đỗ Hoàng Long xem xét phê duyệt đơn xin nghỉ ốm 1 ngày cho Nguyễn Văn An.",
                    "human_readable_explanation": "Đơn nghỉ ốm đang chờ Quản lý trực tiếp (Đỗ Hoàng Long) xem xét và phê duyệt.",
                    "applied_policy_clauses": ["MED-01", "AUTH-01"], "status": "PENDING_ESCALATION",
                    "approval_role": "DIRECT_MANAGER", "approval_status": "PENDING"
                },
                {
                    "id": "REQ-2026-002-NGAN", "employee_id": "EMP019", "employee_name": "Nguyễn Thị Kim Ngân", "department": "Product Design",
                    "from_date": "2026-09-23", "to_date": "2026-09-24", "workdays": 2, "leave_type": "ANNUAL",
                    "reason": "Nghỉ phép năm theo kế hoạch cá nhân cùng gia đình.",
                    "handover_person_id": "EMP012", "handover_person_name": "Nguyễn Văn An", "attachment_type": "none",
                    "decision": "AUTO_APPROVE", "uncertainty_category": "NONE", "error_code": None,
                    "target_role": "DIRECT_MANAGER", "actionable_question": "",
                    "human_readable_explanation": "Đơn xin nghỉ phép năm 2 ngày trong hạn mức quỹ phép còn lại, AI tự động phê duyệt.",
                    "applied_policy_clauses": ["ANN-01", "AUTO-01"], "status": "COMPLETED",
                    "approval_role": "DIRECT_MANAGER", "approval_status": "APPROVED"
                },
                {
                    "id": "REQ-2026-003-TRONG", "employee_id": "EMP023", "employee_name": "Vũ Đình Trọng", "department": "DevOps",
                    "from_date": "2026-09-24", "to_date": "2026-09-26", "workdays": 3, "leave_type": "SPECIAL_PAID",
                    "reason": "Nghỉ đám cưới bản thân theo chế độ việc riêng hưởng lương.",
                    "handover_person_id": "EMP015", "handover_person_name": "Đỗ Hoàng Long", "attachment_type": "none",
                    "decision": "ESCALATE", "uncertainty_category": "AUTHORITY_ESCALATION", "error_code": "SPECIAL_LEAVE_REVIEW",
                    "target_role": "DIRECT_MANAGER",
                    "actionable_question": "Quản lý Đỗ Hoàng Long xác nhận duyệt chế độ nghỉ kết hôn 3 ngày hưởng nguyên lương.",
                    "human_readable_explanation": "Đơn việc riêng hưởng lương kết hôn đang chờ Quản lý xác nhận.",
                    "applied_policy_clauses": ["SPEC-01", "AUTH-01"], "status": "PENDING_ESCALATION",
                    "approval_role": "DIRECT_MANAGER", "approval_status": "PENDING"
                },
                {
                    "id": "REQ-2026-004-YEN", "employee_id": "EMP051", "employee_name": "Trịnh Hoàng Yến", "department": "Finance",
                    "from_date": "2026-09-25", "to_date": "2026-09-25", "workdays": 1, "leave_type": "ANNUAL",
                    "reason": "Giải quyết thủ tục hành chính cá nhân tại địa phương.",
                    "handover_person_id": "EMP045", "handover_person_name": "Trần Thị Bích", "attachment_type": "none",
                    "decision": "AUTO_APPROVE", "uncertainty_category": "NONE", "error_code": None,
                    "target_role": "DIRECT_MANAGER", "actionable_question": "",
                    "human_readable_explanation": "Đơn nghỉ 1 ngày đã có người bàn giao hợp lệ, AI tự động phê duyệt.",
                    "applied_policy_clauses": ["ANN-01", "AUTO-01"], "status": "COMPLETED",
                    "approval_role": "DIRECT_MANAGER", "approval_status": "APPROVED"
                },
                {
                    "id": "REQ-2026-005-CUONG", "employee_id": "EMP062", "employee_name": "Lâm Quốc Cường", "department": "Quality Assurance",
                    "from_date": "2026-09-28", "to_date": "2026-09-29", "workdays": 2, "leave_type": "UNPAID_OTHER",
                    "reason": "Nghỉ việc riêng không hưởng lương theo thỏa thuận với quản lý bộ phận.",
                    "handover_person_id": "EMP015", "handover_person_name": "Đỗ Hoàng Long", "attachment_type": "none",
                    "decision": "ESCALATE", "uncertainty_category": "AUTHORITY_ESCALATION", "error_code": "LONG_TERM_UNPAID",
                    "target_role": "DIRECT_MANAGER",
                    "actionable_question": "Quản lý xem xét thỏa thuận nghỉ không hưởng lương 2 ngày cho nhân sự Lâm Quốc Cường.",
                    "human_readable_explanation": "Đơn nghỉ không hưởng lương cần Quản lý trực tiếp xem xét và phê duyệt.",
                    "applied_policy_clauses": ["UNP-01", "AUTH-01"], "status": "PENDING_ESCALATION",
                    "approval_role": "DIRECT_MANAGER", "approval_status": "PENDING"
                }
            ]

            for c in cases:
                facts_data = {
                    "leave_type": c["leave_type"], "reason_category": "PERSONAL",
                    "from_date": c["from_date"], "to_date": c["to_date"], "reason": c["reason"],
                    "handover_person_id": c["handover_person_id"], "handover_person_name": c["handover_person_name"],
                    "attachment_type": c["attachment_type"]
                }
                result_data = {
                    "decision": c["decision"], "requested_calendar_days": c["workdays"],
                    "requested_working_days": c["workdays"], "working_dates": [c["from_date"]],
                    "paid": True if c["leave_type"] in ["ANNUAL", "SPECIAL_PAID"] else False,
                    "warnings": [c["human_readable_explanation"]], "error_code": c["error_code"]
                }
                conn.execute("""
                    INSERT INTO leave_requests (
                        id, employee_id, employee_name, department, from_date, to_date,
                        workdays, leave_type, reason, handover_person_id, handover_person_name,
                        attachment_type, decision, uncertainty_category, error_code, target_role,
                        actionable_question, quick_action_options, human_readable_explanation,
                        applied_policy_clauses, status, submitted_at, updated_at,
                        facts_json, result_json, legacy_reconciliation_required
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["id"], c["employee_id"], c["employee_name"], c["department"], c["from_date"], c["to_date"],
                    c["workdays"], c["leave_type"], c["reason"], c["handover_person_id"], c["handover_person_name"],
                    c["attachment_type"], c["decision"], c["uncertainty_category"], c["error_code"], c["target_role"],
                    c["actionable_question"], json.dumps(["APPROVE", "REJECT", "REQUEST_MORE_INFO"], ensure_ascii=False),
                    c["human_readable_explanation"], json.dumps(c["applied_policy_clauses"], ensure_ascii=False),
                    c["status"], now, now,
                    json.dumps(facts_data, ensure_ascii=False), json.dumps(result_data, ensure_ascii=False), 0
                ))
                conn.execute("""
                    INSERT OR IGNORE INTO approval_steps (request_id, revision, step_index, role, status)
                    VALUES (?, ?, ?, ?, ?)
                """, (c["id"], 1, 0, c["approval_role"], c["approval_status"]))
                conn.execute("""
                    INSERT INTO audit_logs (request_id, step_name, action, details, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (c["id"], "WORKFLOW", "SUBMITTED", f"Nhân sự {c['employee_name']} nộp đơn {c['leave_type']}", now))

            conn.commit()
            print("✅ [DEMO SEED] Đã nạp thành công 5 đơn mẫu cho 5 nhân viên.")
    finally:
        conn.close()


def reset_all_data(include_demo: bool = False):
    """Reset toàn bộ dữ liệu database về trạng thái sạch 100%:
    - Xóa toàn bộ đơn leave_requests, proof_documents, audit_logs, approval_steps, leave_transactions, leave_bookings
    - Xóa các file upload tạm thời
    - Khôi phục danh sách nhân viên từ employees.json (reset số dư phép về mặc định 12.0 ngày)
    - Đưa số lượng đơn về 0 (trắng tinh hoàn toàn)
    """
    conn = get_db_connection()
    try:
        tables_to_clear = [
            "leave_requests", "proof_documents", "audit_logs", 
            "approval_steps", "leave_transactions", "leave_bookings"
        ]
        for tbl in tables_to_clear:
            try:
                conn.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
        
        # Reset lại bảng employees
        conn.execute("DELETE FROM employees")
        if os.path.exists(EMPLOYEES_JSON_PATH):
            with open(EMPLOYEES_JSON_PATH, "r", encoding="utf-8") as f:
                employees_data = json.load(f)
                for emp in employees_data:
                    conn.execute("""
                        INSERT OR REPLACE INTO employees (
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

        # Dọn dẹp thư mục uploads nếu có
        uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
        if os.path.exists(uploads_dir):
            for fname in os.listdir(uploads_dir):
                fpath = os.path.join(uploads_dir, fname)
                try:
                    if os.path.isfile(fpath) and not fname.startswith('.'):
                        os.remove(fpath)
                except Exception:
                    pass

    finally:
        conn.close()

    if include_demo:
        seed_demo_request()
    print("✅ [DATABASE RESET] Đã xóa sạch toàn bộ đơn nghỉ phép và khôi phục database về 0 đơn.")


def init_db():
    from migrations import backup_if_needed, migrate
    backup_if_needed(DB_PATH)
    _init_legacy_schema()
    conn = get_db_connection()
    try:
        migrate(conn)
        normalize_pending_approval_roles(conn)
    finally:
        conn.close()
    seed_demo_request()


def normalize_pending_approval_roles(conn):
    """Migrate legacy human approval roles to the current Lead Team/CEO model."""
    rows = conn.execute("""
        SELECT id, revision, target_role, department, actionable_question,
               human_readable_explanation, result_json, llm_summary_json
        FROM leave_requests
        WHERE status='PENDING_ESCALATION'
        AND (target_role IN ('HR', 'HRD', 'DEPARTMENT_HEAD')
            OR llm_summary_json LIKE '%cần HR xác minh%'
            OR actionable_question LIKE '%cần HR xác minh%')
    """).fetchall()
    for row in rows:
        old_role = row['target_role']
        new_role = 'DIRECT_MANAGER' if old_role in {'HR', 'DIRECT_MANAGER', None} else 'CEO'
        def replace_json(raw):
            if not raw:
                return raw
            try:
                value = json.loads(raw)
                if isinstance(value, dict):
                    if value.get('target_role') in {'HR', 'HRD', 'DEPARTMENT_HEAD'}:
                        value['target_role'] = new_role
                    if value.get('target_role_human_vn') in {'Nhân sự (HR)', 'Giám đốc Nhân sự'}:
                        value['target_role_human_vn'] = 'Lead Team' if new_role == 'DIRECT_MANAGER' else 'CEO'
                    for key in ('human_readable_explanation', 'why_escalated', 'summary_natural_vn'):
                        if isinstance(value.get(key), str):
                            value[key] = value[key].replace('HR xác minh', 'Lead Team xác minh').replace('HR xem xét', 'Lead Team xem xét').replace('Nhân sự (HR)', 'Lead Team').replace('HR', 'Lead Team')
                    value['actionable_question'] = value.get('actionable_question', '').replace('HR vui lòng', 'Lead Team vui lòng').replace('cần HR xác minh', 'cần Lead Team xác minh')
                return json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                return raw
        result_json = replace_json(row['result_json'])
        llm_summary_json = replace_json(row['llm_summary_json'])
        conn.execute(
            """UPDATE leave_requests
               SET target_role=?, actionable_question=?, human_readable_explanation=?,
                   result_json=?, llm_summary_json=?, updated_at=? WHERE id=?""",
            (new_role,
             (row['actionable_question'] or '').replace('HR vui lòng', 'Lead Team vui lòng').replace('cần HR xác minh', 'cần Lead Team xác minh'),
             (row['human_readable_explanation'] or '').replace('HR xác minh', 'Lead Team xác minh'),
             result_json, llm_summary_json, datetime.now().isoformat(), row['id']),
        )
        conn.execute(
            "UPDATE approval_steps SET role=? WHERE request_id=? AND revision=? AND role=? AND status='PENDING'",
            (new_role, row['id'], row['revision'], old_role),
        )
        conn.execute(
            "INSERT INTO audit_logs(request_id,step_name,action,details,created_at) VALUES(?,?,?,?,?)",
            (row['id'], 'AUTHORITY', 'ROUTING_MIGRATED',
             f"{old_role} -> {new_role}; department={row['department']}; summaries synchronized",
             datetime.now().isoformat()),
        )
    if rows:
        conn.commit()


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


def _serialize_for_save(data: Dict[str, Any]) -> Dict[str, Any]:
    """Reverse of _parse_leave_row: serialize dict/list JSON fields to strings and bools to ints for SQLite binding."""
    data = dict(data)
    json_fields = [
        "quick_action_options", "applied_policy_clauses",
        "vlm_analysis_json", "llm_summary_json",
        "correlation_issues", "escalation_reasons_json", "facts_json", "result_json", "decision_trace"
    ]
    for f in json_fields:
        v = data.get(f)
        if v is not None and not isinstance(v, str):
            try:
                data[f] = json.dumps(v, ensure_ascii=False)
            except Exception:
                data[f] = None
    bool_int_fields = ["has_red_stamp", "has_doctor_signature", "is_tampered", "ai_edited"]
    for f in bool_int_fields:
        v = data.get(f)
        if v is not None:
            data[f] = 1 if v else 0
    return data


def save_leave_request(data: Dict[str, Any]):
    data = _serialize_for_save(data)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO leave_requests (
            id, employee_id, employee_name, department, from_date, to_date,
            workdays, leave_type, reason, handover_person_id, handover_person_name,
            attachment_type, decision, uncertainty_category, error_code,
            target_role, actionable_question, quick_action_options,
            human_readable_explanation, applied_policy_clauses,
            human_feedback_text, status, submitted_at, updated_at,
            vlm_analysis_json, llm_summary_json, doc_patient_name, doc_diagnosis,
            has_red_stamp, has_doctor_signature, is_tampered, ai_edited,
            days_granted_by_doctor, correlation_score, correlation_issues,
            persona_role_used, escalation_reasons_json
        ) VALUES (
            :id, :employee_id, :employee_name, :department, :from_date, :to_date,
            :workdays, :leave_type, :reason, :handover_person_id, :handover_person_name,
            :attachment_type, :decision, :uncertainty_category, :error_code,
            :target_role, :actionable_question, :quick_action_options,
            :human_readable_explanation, :applied_policy_clauses,
            :human_feedback_text, :status, :submitted_at, :updated_at,
            :vlm_analysis_json, :llm_summary_json, :doc_patient_name, :doc_diagnosis,
            :has_red_stamp, :has_doctor_signature, :is_tampered, :ai_edited,
            :days_granted_by_doctor, :correlation_score, :correlation_issues,
            :persona_role_used, :escalation_reasons_json
        )
    """, {
        "id": data.get("id"),
        "employee_id": data.get("employee_id"),
        "employee_name": data.get("employee_name"),
        "department": data.get("department"),
        "from_date": data.get("from_date"),
        "to_date": data.get("to_date"),
        "workdays": data.get("workdays", 0),
        "leave_type": data.get("leave_type"),
        "reason": data.get("reason"),
        "handover_person_id": data.get("handover_person_id"),
        "handover_person_name": data.get("handover_person_name"),
        "attachment_type": data.get("attachment_type", "none"),
        "decision": data.get("decision"),
        "uncertainty_category": data.get("uncertainty_category"),
        "error_code": data.get("error_code"),
        "target_role": data.get("target_role"),
        "actionable_question": data.get("actionable_question"),
        "quick_action_options": data.get("quick_action_options"),
        "human_readable_explanation": data.get("human_readable_explanation"),
        "applied_policy_clauses": data.get("applied_policy_clauses"),
        "human_feedback_text": data.get("human_feedback_text"),
        "status": data.get("status"),
        "submitted_at": data.get("submitted_at"),
        "updated_at": data.get("updated_at"),
        "vlm_analysis_json": data.get("vlm_analysis_json"),
        "llm_summary_json": data.get("llm_summary_json"),
        "doc_patient_name": data.get("doc_patient_name"),
        "doc_diagnosis": data.get("doc_diagnosis"),
        "has_red_stamp": 1 if data.get("has_red_stamp") else (0 if data.get("has_red_stamp") is not None else None),
        "has_doctor_signature": 1 if data.get("has_doctor_signature") else (0 if data.get("has_doctor_signature") is not None else None),
        "is_tampered": 1 if data.get("is_tampered") else (0 if data.get("is_tampered") is not None else None),
        "ai_edited": 1 if data.get("ai_edited") else (0 if data.get("ai_edited") is not None else None),
        "days_granted_by_doctor": data.get("days_granted_by_doctor"),
        "correlation_score": data.get("correlation_score"),
        "correlation_issues": data.get("correlation_issues"),
        "persona_role_used": data.get("persona_role_used"),
        "escalation_reasons_json": data.get("escalation_reasons_json")
    })
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
    res = _parse_leave_row(dict(row))
    return res


def _parse_leave_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Parse JSON fields and convert boolean integers from a leave request row."""
    json_fields = [
        "quick_action_options", "applied_policy_clauses",
        "vlm_analysis_json", "llm_summary_json",
        "correlation_issues", "escalation_reasons_json", "facts_json", "result_json", "decision_trace"
    ]
    for f in json_fields:
        if row.get(f):
            try:
                row[f] = json.loads(row[f])
            except Exception:
                pass
    bool_int_fields = ["has_red_stamp", "has_doctor_signature", "is_tampered", "ai_edited"]
    for f in bool_int_fields:
        if row.get(f) is not None:
            row[f] = bool(row[f])
    return row


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
        d = _parse_leave_row(dict(r))
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
    raise ValueError("Use transactional request approval; standalone deduction is prohibited")


def cancel_leave_request(request_id: str, actor_id=None) -> bool:
    from services.orchestration import LeaveOrchestratorService
    LeaveOrchestratorService().cancel(request_id, actor_id)
    return True


def override_revoke_auto_approval(request_id: str, reason: str = "", actor_id=None) -> bool:
    from services.orchestration import LeaveOrchestratorService
    LeaveOrchestratorService().cancel(request_id, actor_id, revoke=True, reason=reason)
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



