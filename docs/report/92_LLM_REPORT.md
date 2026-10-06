# LLM Report

## 1. Mục đích

LLM module được dùng để parse văn bản tự nhiên của nhân viên và chuyển thành `RequestFacts` chuẩn hóa. Nó không là nơi quyết định policy; nhiệm vụ chính là extraction / normalization.

## 2. File chính

- [backend/ai/ai_stack.py](../../backend/ai/ai_stack.py)
- [backend/ai/llm_client.py](../../backend/ai/llm_client.py)
- [backend/ai/agent_orchestrator.py](../../backend/ai/agent_orchestrator.py)
- [backend/ai/prompts.py](../../backend/ai/prompts.py)
- [backend/ai/schemas.py](../../backend/ai/schemas.py)

## 3. Model dùng

Theo code hiện tại:

- model LLM mặc định: `qwen2.5:3b-instruct`
- gọi qua Ollama
- đường dẫn mặc định: `http://localhost:11434`

## 4. Vai trò thực tế

LLM thực hiện các việc sau:

- trích xuất ngày nghỉ từ text tự nhiên
- xác định loại nghỉ
- xác định lý do / reason category
- trích dẫn người bàn giao nếu có
- map free-text feedback manager về action whitelist

## 5. Lớp xử lý

- `LocalQwenEngine` trong `llm_client.py` là singleton call engine
- `LLMClient` là wrapper cho việc call JSON
- `LeaveApprovalAgent` trong `agent_orchestrator.py` tổ chức pipeline

## 6. Vị trí trong luồng

LLM xuất hiện ở các điểm:

1. parse raw text thành structured request
2. map human feedback thành action
3. optional summary polish nếu có flag bật

## 7. Kiểm tra trạng thái thực tế

Chúng tôi đã chạy kiểm tra runtime thực:

- Gọi Ollama `/api/chat` với model `qwen2.5:3b-instruct`
- Kết quả: thành công
- Output JSON: `{"ok": true, "test": "llm"}`

Đây là bằng chứng thực tế cho thấy LLM đang hoạt động bình thường ở môi trường hiện tại.

## 8. Kết luận module LLM

LLM hoạt động như một module extraction và mapping, không phải quyết định cuối cùng. Đây là đúng mô hình “LLM as semantic extraction”, chứ không phải “AI quyết định policy”.

## 9. Điểm mạnh

- Rõ ranh giới trách nhiệm
- Gọi qua Ollama chuẩn hóa
- JSON schema giúp giảm sai lệch

## 10. Hạn chế

- Cũng có rủi ro hallucination nếu text không rõ
- Không dùng để quyết định cân bằng policy / legal
- Cần thực tế đánh giá model quality
