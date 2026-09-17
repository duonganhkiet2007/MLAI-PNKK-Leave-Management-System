# MODULE LLM (NGƯỜI 2 - KIỆT)
## ĐỀ BÀI A: THE ESCALATION REFEREE — MLAI HACKATHON 2026

Thư mục này hiện thực hóa trọn vẹn toàn bộ phần việc của **Người 2 (AI/LLM)** theo đúng sơ đồ quy trình được giao:
```
Request (Nhận text/chat tự nhiên của nhân viên)
  │
  ▼
Parse toàn bộ (LLM NLP Parser -> Pydantic LeaveRequest)
  │
  ▼
Validate toàn bộ (Guardrail: phát hiện thiếu/mơ hồ -> UNCERTAIN_FACTS, KHÔNG ĐOÁN MÒ)
  │
  ▼
Check toàn bộ policy/rule (Tích hợp trực tiếp với Rule Engine của Kim)
  │
  ▼
Gom tất cả vấn đề phát hiện được
  ├── Không có vấn đề  ──► Auto xử lý (AUTO_APPROVE)
  └── Có vấn đề        ──► Hỏi Human 1 lần (Sinh câu hỏi hành động chuẩn 6/6 điểm BGK)
                             │
                             ▼
                        Nhận câu trả lời từ Quản lý
                             │
                             ▼
                        Re-check toàn bộ
                             │
                             ▼
                        Auto xử lý / Phê duyệt đặc cách / Từ chối
```

---

## 1. Cấu trúc mã nguồn trong `LLM-KIET`

| File | Vai trò |
| :--- | :--- |
| [schemas.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/LLM-KIET/schemas.py) | Định nghĩa Pydantic Schemas: `ParsedLeaveRequest`, `EscalationQuestionPayload`, `HumanFeedbackResolution`, `AgentPipelineResult`. |
| [prompts.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/LLM-KIET/prompts.py) | Bộ Prompt Engineering tối ưu: Parse thông tin, phát hiện mơ hồ (Zero Hallucination), sinh câu hỏi chuyển tiếp chuẩn 6/6 điểm BGK. |
| [llm_client.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/LLM-KIET/llm_client.py) | Engine In-Process Local LLM Qwen 2.5 7B nạp trực tiếp vào RAM GPU RTX 4090, phục vụ trên DUY NHẤT 1 PORT 8000. |
| [agent_orchestrator.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/LLM-KIET/agent_orchestrator.py) | Lõi điều phối (`LeaveApprovalAgent`) liên kết LLM với [rule_engine.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/Leave_Application/rule_engine.py) và [taxonomy.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/Leave_Application/taxonomy.py) của Kim. |
| [test_llm_kiet.py](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/ML%20AI%20/LLM-KIET/test_llm_kiet.py) | Bộ kiểm thử tự động 4/4 kịch bản chuẩn của Track A. |

---

## 2. Hướng dẫn chạy thử nghiệm (Verification)

Mở terminal và kích hoạt môi trường Python sẵn có trên máy:
```bash
/home/phongnh/miniconda3/envs/qwen_vl/bin/python "/workingspace_aiclub/WorkingSpace/Personal/phongnh/ML AI /LLM-KIET/test_llm_kiet.py"
```

Kết quả:
```text
======================================================================
🚀 BẮT ĐẦU KIỂM THỬ MODULE LLM (NGƯỜI 2 - KIỆT) - MLAI HACKATHON 2026
======================================================================
✅ TEST CASE 1: ĐẠT CHUẨN (Tự duyệt không chuyển tiếp thừa)
✅ TEST CASE 2: ĐẠT CHUẨN (Bắt cờ mơ hồ, không tự đoán mò dữ liệu)
✅ TEST CASE 3: ĐẠT CHUẨN (Câu hỏi cụ thể, chỉ rõ tỷ lệ và context cho Trưởng phòng)
✅ TEST CASE 4: ĐẠT CHUẨN (Khép kín vòng lặp Re-check theo đúng sơ đồ đề bài)
======================================================================
🎉 TẤT CẢ 4/4 BÀI TEST CỦA MODULE LLM ĐỀU THÀNH CÔNG RỰC RỠ!
======================================================================
```

---

## 3. Cách Người 3 (Backend) tích hợp vào FastAPI

Người phụ trách Backend chỉ cần gọi class `LeaveApprovalAgent` cực kỳ đơn giản:

```python
from agent_orchestrator import LeaveApprovalAgent

agent = LeaveApprovalAgent()

# 1. Khi nhận đơn nghỉ phép dạng text tự nhiên (POST /leave/request):
pipeline_result = agent.run_full_pipeline(
    raw_text=request_data.text,
    employee_context={
        "employee_id": employee.id,
        "employee_name": employee.name,
        "department": employee.department,
        "remaining_leave_days": employee.leave_balance,
        "submitted_at": datetime.now(),
        "team_absent_count": current_team_absent,
        "total_team_members": department.total_members
    }
)

# 2. Khi Quản lý phản hồi câu hỏi chuyển tiếp (POST /leave/{id}/human-decision):
resolved_result = agent.run_full_pipeline(
    raw_text=previous_request_text,
    employee_context=employee_context,
    human_feedback_text=manager_comment
)
```

---

## 4. Kiến trúc triển khai mô hình (In-Process GPU Port 8000)

Hệ thống triển khai mô hình **Qwen/Qwen2.5-7B-Instruct** theo mô thức **In-Process**:
- Model được nạp trực tiếp vào RAM GPU RTX 4090 (~14.9 GB VRAM, `bfloat16`).
- Tích hợp thẳng vào tiến trình FastAPI Backend trên **DUY NHẤT 1 PORT 8000**.
- Không dùng server vLLM riêng, không mở port phụ (8001, 8080), không cần tmux.
- Chạy 100% bằng trí tuệ nhân tạo thực, không sử dụng heuristic fallback.

