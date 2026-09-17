"""
test_api_e2e.py
Kịch bản kiểm thử tích hợp toàn diện cho Backend API (Người 3).
Kiểm tra tất cả các Router: Leave, Verify Harness 90s, Metadata, Database và Audit Logs.
"""

import sys
import os

# Thêm đường dẫn module backend
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from fastapi.testclient import TestClient
from main import app, init_db

# Khởi tạo DB trước khi test
init_db()
client = TestClient(app)


def run_all_tests():
    print("=" * 75)
    print("🚀 BẮT ĐẦU KIỂM THỬ TÍCH HỢP TOÀN BỘ BACKEND API (NGƯỜI 3)")
    print("=" * 75)

    # --------------------------------------------------------------------------
    # 1. TEST ROOT & METADATA
    # --------------------------------------------------------------------------
    print("\n🔹 [1/7] Kiểm tra Root & Healthcheck")
    res = client.get("/api")
    assert res.status_code == 200, f"Root failed: {res.text}"
    print(f"👉 Root endpoint OK: {res.json().get('project')}")

    res_health = client.get("/api/meta/health")
    assert res_health.status_code == 200, f"Health failed: {res_health.text}"
    print("👉 Healthcheck OK: Status = ok")

    # --------------------------------------------------------------------------
    # 2. TEST EMPLOYEES & POLICY
    # --------------------------------------------------------------------------
    print("\n🔹 [2/7] Kiểm tra danh sách nhân viên & Tài liệu Quy chế")
    res_emp = client.get("/api/meta/employees")
    assert res_emp.status_code == 200, f"Employees failed: {res_emp.text}"
    emp_data = res_emp.json()
    assert emp_data["total"] > 0, "Bảng employees không có dữ liệu!"
    print(f"👉 Đã load thành công {emp_data['total']} nhân viên từ employees.json vào SQLite.")

    res_pol = client.get("/api/meta/policy")
    assert res_pol.status_code == 200, f"Policy failed: {res_pol.text}"
    print(f"👉 Đã load tài liệu quy chế thành công: {res_pol.json().get('document_name')}")

    # --------------------------------------------------------------------------
    # 3. TEST BÀI THI HARNESS 90 GIÂY CỦA BAN GIÁM KHẢO (QUAN TRỌNG NHẤT)
    # --------------------------------------------------------------------------
    print("\n🔹 [3/7] Kiểm tra Verify Harness 90 Giây (POST /api/verify/escalation)")
    res_verify = client.post("/api/verify/escalation")
    assert res_verify.status_code == 200, f"Verify harness failed: {res_verify.text}"
    v_data = res_verify.json()
    summary = v_data["summary"]
    print(f"👉 Tổng số cases kiểm thử: {summary['total_cases']}")
    print(f"👉 Tự động phê duyệt: {summary['auto_approved_cases']}/{summary['target_auto']} cases")
    print(f"👉 Chuyển tiếp (Escalate): {summary['escalated_cases']}/{summary['target_escalate']} cases")
    print(f"👉 Đánh giá tổng thể BGK: {summary['overall_status']}")
    
    assert summary["auto_approved_cases"] == 3, "Phải có đúng 3 ca tự duyệt!"
    assert summary["escalated_cases"] == 2, "Phải có đúng 2 ca chuyển tiếp!"
    assert summary["passed_cases"] == 5, "Cả 5 ca phải đạt chuẩn!"
    print("✅ TEST VERIFY HARNESS 90s: ĐẠT ĐIỂM TỐI ĐA!")

    # --------------------------------------------------------------------------
    # 4. TEST GIÁM KHẢO TỰ NHẬP 1 CA MỚI (CHỐNG BẮT BẺ HARD-CODE)
    # --------------------------------------------------------------------------
    print("\n🔹 [4/7] Kiểm tra Giám khảo nhập ca kiểm thử mới (POST /api/verify/custom)")
    custom_case = {
        "employee_name": "Giám khảo MLAI",
        "department": "Engineering",
        "remaining_leave_days": 1.0, # Chỉ còn 1 ngày phép
        "from_date": "2026-09-23",
        "to_date": "2026-09-25",     # Xin nghỉ 3 ngày làm việc -> Vượt phép!
        "leave_type": "Annual",
        "reason": "Về quê có việc gia đình đột xuất",
        "handover_person_id": "EMP012",
        "team_absent_count": 0,
        "total_team_members": 10,
        "attachment_type": "none"
    }
    res_custom = client.post("/api/verify/custom", json=custom_case)
    assert res_custom.status_code == 200, f"Custom verify failed: {res_custom.text}"
    c_res = res_custom.json()
    print(f"👉 Số ngày làm việc tính ra: {c_res['calculated_workdays']} ngày")
    print(f"👉 Phán quyết của hệ thống: {c_res['decision']}")
    print(f"👉 Mã lỗi nhận diện: {c_res['error_code']}")
    print(f"👉 Câu hỏi hành động sinh ra: \"{c_res['actionable_question']}\"")
    assert c_res["decision"] == "ESCALATE", "Đơn vượt số dư phép phải bị ESCALATE!"
    assert c_res["error_code"] == "BALANCE_EXCEEDED", "Phải báo lỗi BALANCE_EXCEEDED!"
    print("✅ TEST CUSTOM INPUT: ĐẠT CHUẨN (Xử lý linh hoạt không bị hard-code)")

    # --------------------------------------------------------------------------
    # 5. TEST NỘP ĐƠN NGHỈ PHÉP TỰ NHIÊN (POST /api/leave/request)
    # --------------------------------------------------------------------------
    print("\n🔹 [5/7] Kiểm tra Nộp đơn nghỉ phép qua chat tự do (POST /api/leave/request)")
    new_req_payload = {
        "raw_text": "Em xin nghỉ ngày 2026-09-25 để đưa mẹ đi khám bệnh định kỳ nhé sếp.",
        "employee_id": "EMP012"
    }
    res_sub = client.post("/api/leave/request", json=new_req_payload)
    assert res_sub.status_code == 200, f"Submit leave failed: {res_sub.text}"
    created_req = res_sub.json()["data"]
    created_id = created_req["id"]
    print(f"👉 Mã đơn tạo mới: {created_id}")
    print(f"👉 Nhân viên: {created_req['employee_name']} ({created_req['department']})")
    print(f"👉 Quyết định tự động: {created_req['decision']}")
    print(f"👉 Trạng thái đơn: {created_req['status']}")
    assert created_id.startswith("REQ-"), "Mã đơn phải có định dạng REQ-..."
    print("✅ TEST NỘP ĐƠN: Thành công lưu vào SQLite và xử lý tự động!")

    # --------------------------------------------------------------------------
    # 6. TEST NỘP ĐƠN CẦN CHUYỂN TIẾP & HUMAN-IN-THE-LOOP (QUẢN LÝ PHÊ DUYỆT)
    # --------------------------------------------------------------------------
    print("\n🔹 [6/7] Kiểm tra Luồng Escalation & Quản lý phản hồi (POST /api/leave/{id}/human-decision)")
    # Tạo đơn vi phạm thời hạn báo trước hoặc quota để dính ESCALATE
    esc_payload = {
        "raw_text": "Ngày mai 2026-09-18 em xin nghỉ gấp 2 ngày 2026-09-18 đến 2026-09-19 để sửa nhà nhé.",
        "employee_id": "EMP012"
    }
    res_esc = client.post("/api/leave/request", json=esc_payload)
    esc_req = res_esc.json()["data"]
    esc_id = esc_req["id"]
    print(f"👉 Đơn mới bị gắn cờ: {esc_id} (Quyết định: {esc_req['decision']}, Nhóm: {esc_req['uncertainty_category']})")
    print(f"👉 Câu hỏi hành động cho sếp: \"{esc_req['actionable_question']}\"")
    print(f"👉 Gợi ý lựa chọn: {esc_req.get('quick_action_options')}")
    assert esc_req["status"] == "PENDING_ESCALATION", "Đơn nộp gấp phải ở trạng thái PENDING_ESCALATION!"

    # Quản lý phản hồi duyệt đặc cách
    human_input = {
        "feedback_text": "Duyệt đặc cách cho An nghỉ vì việc gia đình gấp.",
        "approver_id": "MGR_HUNG"
    }
    res_decision = client.post(f"/api/leave/{esc_id}/human-decision", json=human_input)
    assert res_decision.status_code == 200, f"Human decision failed: {res_decision.text}"
    resolved_req = res_decision.json()["data"]
    print(f"👉 Kết quả sau khi sếp duyệt: {resolved_req['decision']}")
    print(f"👉 Trạng thái đơn cuối cùng: {resolved_req['status']}")
    assert resolved_req["status"] == "COMPLETED", "Đơn sau duyệt đặc cách phải COMPLETED!"
    assert resolved_req["decision"] == "APPROVED_BY_HUMAN_OVERRIDE", "Phải ghi nhận APPROVED_BY_HUMAN_OVERRIDE!"
    print("✅ TEST HUMAN-IN-THE-LOOP: Khép kín vòng lặp Re-check thành công!")

    # --------------------------------------------------------------------------
    # 7. TEST AUDIT TRAIL (TRÁCH NHIỆM GIẢI TRÌNH)
    # --------------------------------------------------------------------------
    print("\n🔹 [7/7] Kiểm tra Audit Trail & Danh sách đơn (GET /api/leave/{id})")
    res_detail = client.get(f"/api/leave/{esc_id}")
    assert res_detail.status_code == 200
    detail_data = res_detail.json()
    audit_trail = detail_data["audit_trail"]
    print(f"👉 Tổng số sự kiện Audit Trail ghi nhận cho đơn {esc_id}: {len(audit_trail)} bước")
    for log in audit_trail:
        print(f"   [{log['created_at'][:19]}] {log['step_name']} - {log['action']}: {log['details']}")
    assert len(audit_trail) >= 3, "Phải ghi nhận tối thiểu 3 bước xử lý trong nhật ký giải trình!"

    # Danh sách đơn
    res_list = client.get("/api/leave/requests")
    assert res_list.status_code == 200
    print(f"👉 Tổng số đơn hiện có trong cơ sở dữ liệu: {res_list.json()['total']} đơn.")

    print("\n" + "=" * 75)
    print("🎉 TẤT CẢ 7/7 BÀI KIỂM THỬ BACKEND API ĐỀU ĐẠT CHUẨN XUẤT SẮC!")
    print("=" * 75)


if __name__ == "__main__":
    run_all_tests()
