# Báo cáo tách module hệ thống Leave Application

## Tóm tắt nhanh

- Trạng thái hiện tại kiểm tra thực tế:
  - LLM: HOẠT ĐỘNG BÌNH THƯỜNG
  - VLM: KHÔNG ỔN ĐỊNH / ĐANG LỖI 500 khi gọi thực tế qua Ollama
- Kết quả này dựa trên kiểm tra runtime thực tế bằng API Ollama, không chỉ đọc code.

## Danh sách file report

- [docs/report/90_BACKEND_REPORT.md](90_BACKEND_REPORT.md) — Backend API, orchestrator, DB, upload, lifecycle
- [docs/report/91_FRONTEND_REPORT.md](91_FRONTEND_REPORT.md) — Frontend SPA, UI, interaction, API calls
- [docs/report/92_LLM_REPORT.md](92_LLM_REPORT.md) — Module LLM / parser logic
- [docs/report/93_VLM_REPORT.md](93_VLM_REPORT.md) — Module VLM / document inspector
- [docs/report/94_RULE_ENGINE_REPORT.md](94_RULE_ENGINE_REPORT.md) — Decision tree / rule engine
- [docs/report/95_POLICY_REPORT.md](95_POLICY_REPORT.md) — Quy định và thẩm quyền
- [docs/report/96_SYSTEM_STATUS_AND_EVIDENCE.md](96_SYSTEM_STATUS_AND_EVIDENCE.md) — Kiểm chứng runtime và kết luận thực tế

## Mục tiêu

Bản report này tách hệ thống thành các module riêng để người đọc dễ theo dõi:

1. Backend server
2. Frontend client
3. LLM
4. VLM
5. Rule engine / decision tree
6. Quy định pháp lý nội bộ
7. Trạng thái hoạt động thực tế

## Sơ đồ mô tả nhanh

Frontend -> FastAPI backend -> Orchestrator -> Rule Engine / AI modules -> SQLite + uploads

- LLM: parse text, extract facts, map human feedback
- VLM: analyze proof docs, extract evidence, return unverified facts
- Rule engine: evaluate policy and approve / reject / escalate
- Policy file: nguồn tham chiếu nội bộ và luật nền

## Link tới code thực tế

- [backend/main.py](../../backend/main.py)
- [backend/services/orchestration.py](../../backend/services/orchestration.py)
- [frontend/index.html](../../frontend/index.html)
- [frontend/app.js](../../frontend/app.js)
- [backend/ai/ai_stack.py](../../backend/ai/ai_stack.py)
- [backend/ai/llm_client.py](../../backend/ai/llm_client.py)
- [Leave_Application/vlm_inspector.py](../../Leave_Application/vlm_inspector.py)
- [Leave_Application/rule_engine.py](../../Leave_Application/rule_engine.py)
- [Leave_Application/policy_rules.md](../../Leave_Application/policy_rules.md)

---

Nguồn báo cáo này được tổng hợp từ code hiện tại và kiểm tra runtime thực tế trong máy local.
