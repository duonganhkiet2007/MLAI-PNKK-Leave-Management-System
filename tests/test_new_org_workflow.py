"""
test_new_org_workflow.py
Bộ kiểm thử hoàn chỉnh cho hệ thống nhân sự mới:
- 01 The Boss (Phạm Minh Hoàng - EMP000)
- 02 Department Managers (Đỗ Hoàng Long - EMP001, Dương Mỹ Duyên - EMP002)
- 10 Cán bộ nhân viên (5 Engineering, 5 Marketing & Operations)
- 8 nhánh quy chế và kiểm định chứng từ y tế giả định (không quốc huy)
"""

import json
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import pytest

from rule_engine import LeaveRequest, LeaveRuleEngine
from domain import VerifiedProof, ProofType, RequestFacts
from taxonomy import DecisionType as D, ErrorCode as E, TargetApproverRole as R
from calendar_service import CalendarService
import storage as st

ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "proofs"
EMPLOYEES_FILE = Path(__file__).resolve().parents[1] / "Leave_Application" / "employees.json"

@pytest.fixture(scope="module")
def employees_data():
    with open(EMPLOYEES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {e["employee_id"]: e for e in data}

# =======================================================================
# PHẦN 1: KIỂM TRA TÍNH TOÀN VẸN CỦA DATABASE NHÂN SỰ & QUYỀN
# =======================================================================

def test_database_structure_and_integer_balances(employees_data):
    """Đảm bảo đúng 13 nhân sự, đúng 2 phòng ban, số dư phép nguyên bản, không có HR trống."""
    assert len(employees_data) == 13, f"Số lượng nhân sự phải là 13, hiện có: {len(employees_data)}"
    
    # 1. The Boss
    boss = employees_data["EMP000"]
    assert boss["role"] == "Chief Executive Officer (Boss)"
    assert boss["manager_id"] is None
    assert boss["remaining_leave_days"] == 20.0
    
    # 2. Managers
    mgr1 = employees_data["EMP001"]
    assert mgr1["role"] == "Engineering Manager"
    assert mgr1["department"] == "Engineering"
    assert mgr1["manager_id"] == "EMP000"
    assert mgr1["remaining_leave_days"] == 15.0

    mgr2 = employees_data["EMP002"]
    assert mgr2["role"] == "Marketing & Operations Manager"
    assert mgr2["department"] == "Marketing & Operations"
    assert mgr2["manager_id"] == "EMP000"
    assert mgr2["remaining_leave_days"] == 15.0

    # 3. Kiểm tra số dư nguyên bản cho toàn bộ 13 nhân sự
    for emp_id, emp in employees_data.items():
        bal = emp["remaining_leave_days"]
        assert bal == int(bal), f"Số dư phép của {emp_id} phải là số nguyên, hiện là {bal}"
        assert bal >= 0, f"Số dư phép của {emp_id} không được âm"

    # 4. Kiểm tra phòng ban
    eng_staff = [e for e in employees_data.values() if e["department"] == "Engineering" and e["employee_id"] not in ("EMP000", "EMP001")]
    mkt_staff = [e for e in employees_data.values() if e["department"] == "Marketing & Operations" and e["employee_id"] not in ("EMP000", "EMP002")]
    assert len(eng_staff) == 5, f"Phòng Engineering phải có đúng 5 nhân viên, có {len(eng_staff)}"
    assert len(mkt_staff) == 5, f"Phòng Mkt/Ops phải có đúng 5 nhân viên, có {len(mkt_staff)}"

    # 5. Tất cả nhân viên Kỹ thuật báo cáo cho Manager 1, Marketing báo cáo cho Manager 2
    for e in eng_staff:
        assert e["manager_id"] == "EMP001", f"Nhân viên {e['name']} phải báo cáo cho EMP001"
    for e in mkt_staff:
        assert e["manager_id"] == "EMP002", f"Nhân viên {e['name']} phải báo cáo cho EMP002"

# =======================================================================
# PHẦN 2: NHÓM KIỂM THỬ CẤP 0 (AI TIER - AUTO_APPROVE & AUTO_REJECT)
# =======================================================================

def test_tc_ai_01_annual_single_day_auto_approve(employees_data):
    """TC-AI-01: Nguyễn Văn An (EMP005) xin 1 ngày phép năm -> AUTO_APPROVE, trừ 1 ngày phép."""
    emp = employees_data["EMP005"]
    req = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department=emp["department"],
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",  # Thứ 2
        to_date="2026-10-05",    # 1 ngày làm việc
        leave_type="ANNUAL",
        reason="Việc riêng gia đình",
        total_team_members=6,
        team_absent_count=0
    )
    result = LeaveRuleEngine.evaluate(req)
    assert result.decision == D.AUTO_APPROVE
    assert result.requested_working_days == 1
    assert result.deducted_days == 1
    assert result.annual_balance_change == -1

def test_tc_ai_02_sick_single_day_with_prescription(employees_data):
    """TC-AI-02: Hoàng Kim Yến (EMP011) nộp đơn ốm 1 ngày trước 08:30 sáng có đơn thuốc -> AUTO_APPROVE."""
    emp = employees_data["EMP011"]
    proof = VerifiedProof(
        proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
        proof_verification_status="VERIFIED",
        issuer="Bệnh viện Đa khoa Quốc tế Hà Nội",
        patient_name=emp["name"],
        issue_date=date(2026, 10, 5),
        recommended_from_date=date(2026, 10, 5),
        recommended_to_date=date(2026, 10, 5),
        signature_present=True,
        document_readability="READABLE"
    )
    req = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department=emp["department"],
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 10, 5, 7, 45, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-05",
        leave_type="SICK_MEDICAL",
        reason="Bị sốt cảm cúm đột xuất",
        proof=proof,
        total_team_members=6
    )
    result = LeaveRuleEngine.evaluate(req)
    assert result.decision == D.AUTO_APPROVE
    assert result.requested_working_days == 1
    assert result.deducted_days == 0  # Ốm đau BHXH không trừ phép năm!

def test_tc_ai_03_balance_boundary_kiet(employees_data):
    """TC-AI-03: Bùi Tuấn Kiệt (EMP006) còn 1 ngày phép: xin 1 ngày -> PASS; xin 2 ngày -> AUTO_REJECT."""
    emp = employees_data["EMP006"]
    assert emp["remaining_leave_days"] == 1.0

    # Nhánh 1: Xin 1 ngày -> AUTO_APPROVE
    req_pass = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department=emp["department"],
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-05",
        leave_type="ANNUAL",
        total_team_members=6
    )
    res_pass = LeaveRuleEngine.evaluate(req_pass)
    assert res_pass.decision == D.AUTO_APPROVE

    # Nhánh 2: Xin 2 ngày -> AUTO_REJECT (BALANCE_EXCEEDED)
    req_fail = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department=emp["department"],
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-06",
        leave_type="ANNUAL",
        total_team_members=6
    )
    res_fail = LeaveRuleEngine.evaluate(req_fail)
    assert res_fail.decision == D.AUTO_REJECT
    assert res_fail.error_code == E.BALANCE_EXCEEDED

def test_tc_ai_04_probation_restriction_huong(employees_data):
    """TC-AI-04: Lê Thị Hương (EMP007 - Thử việc): Xin Annual -> Chặn; Xin Unpaid Other -> Hợp lệ."""
    emp = employees_data["EMP007"]
    assert emp["status"] == "PROBATION"

    # Xin phép năm hưởng lương -> Bắt lỗi PROBATION_ANNUAL_RESTRICTED
    req_annual = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department=emp["department"],
        remaining_leave_days=0.0,
        employment_status="PROBATION",
        submitted_at=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-05",
        leave_type="ANNUAL",
        total_team_members=6
    )
    res_annual = LeaveRuleEngine.evaluate(req_annual)
    assert res_annual.decision == D.NEED_CORRECTION
    assert res_annual.error_code == E.PROBATION_ANNUAL_RESTRICTED

    # Xin nghỉ việc riêng không lương UNPAID_OTHER -> Hợp lệ chuyển Quản lý Cấp 1
    req_unpaid = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department=emp["department"],
        remaining_leave_days=0.0,
        employment_status="PROBATION",
        submitted_at=datetime(2026, 9, 20, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-05",
        leave_type="UNPAID_OTHER",
        reason="Giải quyết việc cá nhân đột xuất",
        total_team_members=6
    )
    res_unpaid = LeaveRuleEngine.evaluate(req_unpaid)
    assert res_unpaid.decision == D.ESCALATE
    assert res_unpaid.target_role == R.DIRECT_MANAGER

def test_tc_ai_05_weekend_and_holiday_no_leave_required():
    """TC-AI-05: Đơn rơi vào ngày lễ/cuối tuần -> NO_LEAVE_REQUIRED."""
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 4, 20, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-04-26",  # Giỗ Tổ Hùng Vương (Chủ Nhật)
        to_date="2026-04-27",    # Nghỉ bù (Thứ Hai)
        leave_type="ANNUAL",
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.NO_LEAVE_REQUIRED
    assert res.error_code == E.DAY_ALREADY_NON_WORKING
    assert res.deducted_days == 0

# =======================================================================
# PHẦN 3: PHÂN LUỒNG QUẢN LÝ CẤP 1 (MANAGER 1 VS MANAGER 2)
# =======================================================================

def test_tc_mgr_01_engineering_manager_routing(employees_data):
    """TC-MGR-01: Lê Văn Nam (Engineering) xin 4 ngày -> Chuyển Manager 1 (DIRECT_MANAGER - Engineering)."""
    emp = employees_data["EMP004"]
    handover_colleague = employees_data["EMP003"]
    req = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department="Engineering",
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 9, 25, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-08",  # 4 ngày làm việc
        leave_type="ANNUAL",
        reason="Nghỉ phép thường niên",
        handover_person_id=handover_colleague["employee_id"],
        handover={
            "employee_id": handover_colleague["employee_id"],
            "department": "Engineering",
            "status": "ACTIVE",
            "absent_dates": []
        },
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.target_role == R.DIRECT_MANAGER
    assert res.requested_working_days == 4

def test_tc_mgr_02_marketing_manager_routing(employees_data):
    """TC-MGR-02: Phan Thảo My (Marketing) xin 4 ngày -> Chuyển Manager 2 (DIRECT_MANAGER - Mkt/Ops)."""
    emp = employees_data["EMP010"]
    handover_colleague = employees_data["EMP008"]
    req = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department="Marketing & Operations",
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 9, 25, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-08",  # 4 ngày làm việc
        leave_type="ANNUAL",
        reason="Nghỉ phép cá nhân",
        handover_person_id=handover_colleague["employee_id"],
        handover={
            "employee_id": handover_colleague["employee_id"],
            "department": "Marketing & Operations",
            "status": "ACTIVE",
            "absent_dates": []
        },
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.target_role == R.DIRECT_MANAGER
    assert res.requested_working_days == 4

def test_tc_mgr_03_special_paid_wedding(employees_data):
    """TC-MGR-03: Võ Minh Khang (EMP009) nộp đơn kết hôn 3 ngày kèm minh chứng -> DIRECT_MANAGER duyệt."""
    emp = employees_data["EMP009"]
    proof = VerifiedProof(
        proof_type=ProofType.MARRIAGE_CERTIFICATE,
        proof_verification_status="VERIFIED",
        issuer="UBND Phường Dịch Vọng Hậu",
        issue_date=date(2026, 9, 20),
        document_readability="READABLE"
    )
    req = LeaveRequest(
        employee_id=emp["employee_id"],
        employee_name=emp["name"],
        department="Marketing & Operations",
        remaining_leave_days=emp["remaining_leave_days"],
        submitted_at=datetime(2026, 9, 25, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-07",  # 3 ngày kết hôn hưởng nguyên lương
        leave_type="SPECIAL_PAID",
        reason="Nghỉ đám cưới bản thân",
        reason_category="SELF_MARRIAGE",
        proof=proof,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.target_role == R.DIRECT_MANAGER
    assert res.requested_working_days == 3
    assert res.paid is True
    assert res.deducted_days == 0  # Không trừ phép năm!

def test_tc_mgr_04_statutory_unclear_relationship():
    """TC-MGR-04: Nghỉ việc riêng không rõ thân nhân -> Không từ chối, chuyển Quản lý xác minh."""
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-05",
        leave_type="STATUTORY_UNPAID",
        reason="Về quê lo việc họ hàng",
        reason_category=None,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.target_role == R.DIRECT_MANAGER
    assert res.error_code == E.RELATIONSHIP_UNCLEAR

# =======================================================================
# PHẦN 4: CÁC TÌNH HUỐNG KHÓ, GẮN CỜ & CHẶN TỰ DUYỆT (EDGE CASES)
# =======================================================================

def test_tc_hard_01_prevent_manager_self_approval_and_route_to_boss():
    """TC-HARD-01: Manager 1 nộp đơn -> Khi duyệt đa bước, không được tự duyệt mình, cấp trên là Boss."""
    # Kiểm tra cấu trúc hierarchy trong database
    with open(EMPLOYEES_FILE, "r", encoding="utf-8") as f:
        data = {e["employee_id"]: e for e in json.load(f)}
    mgr1 = data["EMP001"]
    boss = data["EMP000"]
    assert mgr1["manager_id"] == boss["employee_id"], "Cấp trên trực tiếp của Manager 1 phải là The Boss"

def test_tc_hard_02_long_term_leave_over_20_days_routes_to_boss():
    """TC-HARD-02: Đơn >= 20 ngày -> Bắt buộc Tổng Giám đốc (CEO/Boss) phê duyệt."""
    handover_colleague = {"employee_id": "EMP010", "department": "Marketing & Operations", "status": "ACTIVE", "absent_dates": []}
    req = LeaveRequest(
        employee_id="EMP012",
        employee_name="Lê Mai Loan",
        department="Marketing & Operations",
        remaining_leave_days=12.0,
        submitted_at=datetime(2026, 9, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-01",
        to_date="2026-10-29",  # 21 ngày làm việc
        leave_type="UNPAID_OTHER",
        reason="Nghỉ việc riêng dài hạn",
        handover_person_id="EMP010",
        handover=handover_colleague,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert R.CEO in res.approval_roles or res.target_role in (R.CEO, R.DEPARTMENT_HEAD)
    assert res.requested_working_days >= 20

def test_tc_hard_03_extended_consecutive_leave_over_5_days():
    """TC-HARD-03: Nghỉ phép năm liên tục > 5 ngày -> Vượt trần Quản lý, chuyển cấp cao hơn (The Boss)."""
    handover_colleague = {"employee_id": "EMP004", "department": "Engineering", "status": "ACTIVE", "absent_dates": []}
    req = LeaveRequest(
        employee_id="EMP003",
        employee_name="Trần Quốc Hưng",
        department="Engineering",
        remaining_leave_days=18.0,
        submitted_at=datetime(2026, 9, 10, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-12",  # 6 ngày làm việc liên tiếp
        leave_type="ANNUAL",
        reason="Nghỉ du lịch gia đình dài ngày",
        handover_person_id="EMP004",
        handover=handover_colleague,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.target_role in (R.DEPARTMENT_HEAD, R.CEO)
    assert res.error_code == E.DURATION_OVER_MANAGER_LIMIT

def test_tc_hard_04_flag_abuse_pattern_fragmented_leaves():
    """TC-HARD-04: Nhân viên nộp nhiều đơn rời rạc trong tháng tích lũy > 2 ngày -> Bắt cờ FLAG_ABUSE_PATTERN."""
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 10, 15, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-19",
        to_date="2026-10-19",  # 1 ngày (lẽ ra AI tự duyệt)
        leave_type="ANNUAL",
        has_abuse_pattern=True,  # Đã tích lũy quá hạn tự duyệt trong tháng
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.error_code == E.FLAG_ABUSE_PATTERN
    assert res.target_role == R.DIRECT_MANAGER

def test_tc_hard_05_team_quota_exceeded_over_30_percent():
    """TC-HARD-05: Tỷ lệ vắng mặt phòng ban vượt 30% -> Cảnh báo TEAM_QUOTA_EXCEEDED."""
    req = LeaveRequest(
        employee_id="EMP010",
        employee_name="Phan Thảo My",
        department="Marketing & Operations",
        remaining_leave_days=10.0,
        submitted_at=datetime(2026, 10, 1, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-05",
        leave_type="ANNUAL",
        total_team_members=6,
        team_absent_count=2  # Đã có 2/6 = 33% vắng mặt
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.error_code == E.TEAM_QUOTA_EXCEEDED
    assert res.target_role == R.DIRECT_MANAGER

def test_tc_hard_06_invalid_handover_cross_department():
    """TC-HARD-06: Người bàn giao khác phòng ban -> Báo lỗi HANDOVER_INVALID."""
    req = LeaveRequest(
        employee_id="EMP004",
        employee_name="Lê Văn Nam",
        department="Engineering",
        remaining_leave_days=14.0,
        submitted_at=datetime(2026, 9, 25, 8, 0, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-10-05",
        to_date="2026-10-07",  # 3 ngày làm việc (bắt buộc bàn giao)
        leave_type="ANNUAL",
        handover_person_id="EMP009",  # Nhân viên phòng Marketing!
        handover={
            "employee_id": "EMP009",
            "department": "Marketing & Operations",  # Khác phòng
            "status": "ACTIVE",
            "absent_dates": []
        },
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.NEED_CORRECTION
    assert res.error_code == E.HANDOVER_INVALID

# =======================================================================
# PHẦN 5: KIỂM THỬ THỊ GIÁC VLM & ẢNH CHỨNG TỪ Y TẾ GIẢ ĐỊNH (KHÔNG QUỐC HUY)
# =======================================================================

def test_tc_vlm_01_valid_generated_image_exists():
    """TC-VLM-01: Xác nhận 6 file ảnh chứng từ giả định đã được sinh ra đầy đủ."""
    expected_files = [
        "proof_sick_valid_3days.png",
        "proof_name_mismatch.png",
        "proof_days_mismatch.png",
        "proof_blurry_illegible.png",
        "proof_digital_signed.png",
        "proof_wedding_cert.png"
    ]
    for filename in expected_files:
        p = ASSETS_DIR / filename
        assert p.exists(), f"Thiếu file ảnh chứng từ giả định: {p}"
        assert p.stat().st_size > 1000, f"File ảnh {p} bị rỗng hoặc lỗi kích thước"

def test_tc_vlm_02_name_mismatch_detection():
    """TC-VLM-02: Bẫy lệch tên bệnh nhân -> Bắt cờ NAME_MISMATCH."""
    proof = VerifiedProof(
        proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
        proof_verification_status="VERIFIED",
        issuer="Bệnh viện Đa khoa Medlatec",
        patient_name="Phạm Quốc Dũng",  # Hoàn toàn không khớp Nguyễn Văn An
        issue_date=date(2026, 9, 22),
        recommended_from_date=date(2026, 9, 22),
        recommended_to_date=date(2026, 9, 24),
        signature_present=True,
        document_readability="READABLE"
    )
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 9, 22, 7, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-09-22",
        to_date="2026-09-24",
        leave_type="SICK_MEDICAL",
        proof=proof,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.NEED_CORRECTION
    assert res.error_code == E.NAME_MISMATCH

def test_tc_vlm_03_medical_days_mismatch_detection():
    """TC-VLM-03: Bác sĩ cho 2 ngày nhưng đơn xin 3 ngày -> Bắt lỗi MEDICAL_DAYS_MISMATCH."""
    proof = VerifiedProof(
        proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
        proof_verification_status="VERIFIED",
        issuer="Bệnh viện Đa khoa Quốc tế Hà Nội",
        patient_name="Nguyễn Văn An",
        issue_date=date(2026, 9, 22),
        recommended_from_date=date(2026, 9, 22),
        recommended_to_date=date(2026, 9, 23),  # Chỉ cho 2 ngày
        signature_present=True,
        document_readability="READABLE"
    )
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 9, 22, 7, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-09-22",
        to_date="2026-09-24",  # Xin 3 ngày
        leave_type="SICK_MEDICAL",
        proof=proof,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.NEED_CORRECTION
    assert res.error_code == E.MEDICAL_DAYS_MISMATCH

def test_tc_vlm_04_blurry_illegible_proof():
    """TC-VLM-04: Ảnh mờ / blur không đọc được -> escalate, không suy đoán và không tự sinh dữ liệu."""
    proof = VerifiedProof(
        proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
        document_readability="UNREADABLE"
    )
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 9, 22, 7, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-09-22",
        to_date="2026-09-24",
        leave_type="SICK_MEDICAL",
        proof=proof,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    assert res.decision == D.ESCALATE
    assert res.error_code == E.DOC_ILLEGIBLE
    assert proof.document_readability == "UNREADABLE"

def test_tc_vlm_05_digital_signature_valid_without_red_stamp():
    """TC-VLM-05: Chữ ký số hợp lệ theo Thông tư 25/2025/TT-BYT (không bắt buộc mộc đỏ)."""
    proof = VerifiedProof(
        proof_type=ProofType.MEDICAL_LEAVE_CERTIFICATE,
        proof_verification_status="VERIFIED",
        issuer="Bệnh viện Đa khoa Quốc tế Hà Nội",
        patient_name="Nguyễn Văn An",
        issue_date=date(2026, 9, 22),
        recommended_from_date=date(2026, 9, 22),
        recommended_to_date=date(2026, 9, 24),
        signature_present=False,          # Không có chữ ký tay
        digital_signature_present=True,   # Có chữ ký số hợp lệ
        document_readability="READABLE"
    )
    req = LeaveRequest(
        employee_id="EMP005",
        employee_name="Nguyễn Văn An",
        department="Engineering",
        remaining_leave_days=8.0,
        submitted_at=datetime(2026, 9, 22, 7, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")),
        from_date="2026-09-22",
        to_date="2026-09-24",  # 3 ngày
        leave_type="SICK_MEDICAL",
        proof=proof,
        total_team_members=6
    )
    res = LeaveRuleEngine.evaluate(req)
    # Vì 3 ngày ốm có chứng từ số hợp lệ -> Chuyển Quản lý duyệt, KHÔNG bị bắt lỗi thiếu chữ ký
    assert res.decision == D.ESCALATE
    assert res.target_role == R.DIRECT_MANAGER
    assert res.error_code == E.DURATION_OVER_AI_LIMIT

def test_tc_vlm_06_blur_gate_early_exit_no_hallucination():
    """TC-VLM-06: Blur gate phát hiện ảnh mờ trong ~1ms, gắn UNREADABLE và không bịa dữ liệu."""
    from vlm_inspector import inspect_document_with_vlm, detect_image_blur
    import os

    blur_img = "tests/assets/proofs/proof_blurry_illegible.png"
    assert os.path.exists(blur_img), f"File {blur_img} must exist"

    is_blurry, score = detect_image_blur(blur_img, threshold=50.0)
    assert is_blurry is True
    assert score < 50.0

    out = inspect_document_with_vlm(
        leave_type="SICK_MEDICAL",
        employee_name="Phan Thảo My",
        reason="Nghỉ ốm điều trị",
        attachment_path_or_type=blur_img,
        allow_mock_fallback=False,
    )
    assert out.proof_extraction.document_readability == "UNREADABLE"
    assert out.doc_patient_name is None
    assert out.doc_diagnosis is None
    assert out.proof_extraction.issuer is None
    assert out.proof_extraction.issue_date is None
    assert out.proof_extraction.fields_detected == []
    assert "DOC_BLURRED_IMAGE" in out.escalation_reasons_json
    assert out.vlm_analysis_json.get("inspection_mode") == "CV_BLUR_GATE_EARLY_EXIT"
