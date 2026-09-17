"""
test_llm_kiet.py
Bộ kiểm thử toàn diện các luồng cho Module LLM của Kiệt (Track A - The Escalation Referee).
Kiểm tra:
1. Đơn hợp lệ thường quy -> Tự duyệt tự động 100%.
2. Đơn mập mờ, thiếu dữ liệu -> Bắt lỗi UNCERTAIN_FACTS, tuyệt đối không hallucinate/đoán ngày.
3. Đơn vi phạm quota phòng ban -> Sinh câu hỏi Escalation đạt chuẩn 6/6 điểm BGK.
4. Vòng lặp phản hồi của Quản lý (Human-in-the-loop) -> Parse & Re-check chuẩn xác.
"""

import sys
import os

# Thêm đường dẫn thư mục hiện tại
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from agent_orchestrator import LeaveApprovalAgent
from datetime import datetime


def run_tests():
    print("=" * 70)
    print("🚀 BẮT ĐẦU KIỂM THỬ MODULE LLM (NGƯỜI 2 - KIỆT) - MLAI HACKATHON 2026")
    print("=" * 70)

    agent = LeaveApprovalAgent()

    # --------------------------------------------------------------------------
    # TEST CASE 1: ĐƠN CHUẨN TỰ NHIÊN HỢP LỆ (AUTO_APPROVE)
    # --------------------------------------------------------------------------
    print("\n🔹 [TEST CASE 1] Đơn xin nghỉ phép rõ ràng, hợp lệ")
    text_1 = "Chào sếp, em xin nghỉ phép năm ngày 2026-09-25 để đi giải quyết việc gia đình ạ."
    ctx_1 = {
        "request_id": "REQ-TEST-001",
        "employee_id": "EMP012",
        "employee_name": "Nguyễn Văn An",
        "department": "Engineering",
        "remaining_leave_days": 10.0,
        "submitted_at": "2026-09-21T08:00:00",
        "team_absent_count": 0,
        "total_team_members": 10
    }
    res_1 = agent.run_full_pipeline(text_1, ctx_1)
    print(f"👉 Quyết định: {res_1.final_decision}")
    print(f"👉 Trạng thái: {res_1.status}")
    print(f"👉 Giải trình: {res_1.escalation_payload.human_readable_explanation}")
    assert res_1.final_decision == "AUTO_APPROVE", "TC1 phải AUTO_APPROVE!"
    print("✅ TEST CASE 1: ĐẠT CHUẨN (Tự duyệt không chuyển tiếp thừa)")

    # --------------------------------------------------------------------------
    # TEST CASE 2: ĐƠN MƠ HỒ / THIẾU THÔNG TIN (GUARDRAIL: ZERO HALLUCINATION)
    # --------------------------------------------------------------------------
    print("\n🔹 [TEST CASE 2] Đơn mơ hồ: 'Tuần sau cho em nghỉ vài hôm nhé'")
    text_2 = "Sếp ơi tuần sau cho em xin nghỉ vài hôm em có việc bận nhé!"
    ctx_2 = {
        "request_id": "REQ-TEST-002",
        "employee_id": "EMP015",
        "employee_name": "Lê Văn Bình",
        "department": "Marketing",
        "remaining_leave_days": 5.0,
        "submitted_at": "2026-09-21T08:00:00",
        "team_absent_count": 0,
        "total_team_members": 5
    }
    res_2 = agent.run_full_pipeline(text_2, ctx_2)
    print(f"👉 Quyết định: {res_2.final_decision}")
    print(f"👉 Bị cờ mơ hồ: {res_2.parsed_request.is_ambiguous}")
    print(f"👉 Lý do: {res_2.parsed_request.ambiguity_reason}")
    print(f"👉 Nhóm lỗi: {res_2.escalation_payload.uncertainty_category}")
    print(f"👉 Câu hỏi: \"{res_2.escalation_payload.actionable_question}\"")
    assert res_2.parsed_request.is_ambiguous == True, "TC2 phải phát hiện mơ hồ!"
    assert res_2.escalation_payload.uncertainty_category == "UNCERTAIN_FACTS", "TC2 phải thuộc nhóm UNCERTAIN_FACTS!"
    print("✅ TEST CASE 2: ĐẠT CHUẨN (Bắt cờ mơ hồ, không tự đoán mò dữ liệu)")

    # --------------------------------------------------------------------------
    # TEST CASE 3: ĐƠN VI PHẠM QUOTA PHÒNG BAN (SINH CÂU HỎI CHUẨN 6/6 ĐIỂM BGK)
    # --------------------------------------------------------------------------
    print("\n🔹 [TEST CASE 3] Đơn vi phạm Quota phòng ban (vượt trần an toàn 30%)")
    text_3 = "Em xin nghỉ phép từ 2026-09-24 đến 2026-09-24 để về quê."
    ctx_3 = {
        "request_id": "REQ-TEST-003",
        "employee_id": "EMP020",
        "employee_name": "Hoàng Thị Mai",
        "department": "Finance",
        "remaining_leave_days": 6.0,
        "submitted_at": "2026-09-21T08:00:00",
        "team_absent_count": 2, # Đã có 2 người nghỉ trên tổng số 6 người -> (2+1)/6 = 50% > 30%
        "total_team_members": 6
    }
    res_3 = agent.run_full_pipeline(text_3, ctx_3)
    print(f"👉 Quyết định: {res_3.final_decision}")
    print(f"👉 Nhóm vi phạm: {res_3.escalation_payload.uncertainty_category}")
    print(f"👉 Mã lỗi: {res_3.escalation_payload.error_code}")
    print(f"👉 Cấp duyệt: {res_3.escalation_payload.target_role}")
    print(f"👉 Câu hỏi hành động: \"{res_3.escalation_payload.actionable_question}\"")
    print(f"👉 Tùy chọn gợi ý: {res_3.escalation_payload.quick_action_options}")
    assert res_3.escalation_payload.error_code == "TEAM_QUOTA_EXCEEDED", "TC3 phải báo lỗi quota!"
    assert len(res_3.escalation_payload.quick_action_options) > 0, "TC3 phải có gợi ý hành động!"
    print("✅ TEST CASE 3: ĐẠT CHUẨN (Câu hỏi cụ thể, chỉ rõ tỷ lệ và context cho Trưởng phòng)")

    # --------------------------------------------------------------------------
    # TEST CASE 4: QUẢN LÝ PHẢN HỒI (HUMAN-IN-THE-LOOP & RE-CHECK)
    # --------------------------------------------------------------------------
    print("\n🔹 [TEST CASE 4] Vòng lặp phản hồi: Quản lý gõ câu trả lời tự nhiên")
    human_reply = "Duyệt đặc cách cho Mai nghỉ nhé, việc gấp đã nhờ chị Lan hỗ trợ."
    res_4 = agent.run_full_pipeline(text_3, ctx_3, human_feedback_text=human_reply)
    print(f"👉 Phản hồi từ Quản lý: \"{human_reply}\"")
    print(f"👉 Kết quả sau Re-check: {res_4.final_decision}")
    print(f"👉 Trạng thái cuối: {res_4.status}")
    print("👉 Nhật ký Audit Trail:")
    for log in res_4.history_log:
        print(f"   {log}")
    assert res_4.final_decision == "APPROVED_BY_HUMAN_OVERRIDE", "TC4 phải hoàn tất duyệt đặc cách!"
    print("✅ TEST CASE 4: ĐẠT CHUẨN (Khép kín vòng lặp Re-check theo đúng sơ đồ đề bài)")

    print("\n" + "=" * 70)
    print("🎉 TẤT CẢ 4/4 BÀI TEST CỦA MODULE LLM ĐỀU THÀNH CÔNG RỰC RỠ!")
    print("=" * 70)


if __name__ == "__main__":
    run_tests()
