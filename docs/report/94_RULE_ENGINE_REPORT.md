# Decision Tree / Rule Engine Report

## 1. Mục đích

Rule engine là nơi thực hiện quyết định chính sách. Đây là module quyết định kết quả cuối cùng của đơn nghỉ: approve / reject / need correction / escalate / no leave required.

## 2. File chính

- [Leave_Application/rule_engine.py](../../Leave_Application/rule_engine.py)
- [Leave_Application/taxonomy.py](../../Leave_Application/taxonomy.py)
- [Leave_Application/domain.py](../../Leave_Application/domain.py)
- [Leave_Application/calendar_service.py](../../Leave_Application/calendar_service.py)

## 3. Nguyên tắc cốt lõi

- Không để LLM quyết định policy
- Chỉ có `LeaveRuleEngine.evaluate` mới quyết định outcome
- Rule engine dùng trusted context và deterministic logic

## 4. Quy trình đánh giá

Engine chạy theo các stage chính:

- input dates validation
- calendar / working dates
- entitlement check
- input completeness
- proof validation
- overlap check
- balance check
- notice period check
- team capacity / quota check
- handover check
- authority escalation
- final decision

## 5. Các quyết định chính

- `NO_LEAVE_REQUIRED`
- `AUTO_APPROVE`
- `AUTO_REJECT`
- `NEED_CORRECTION`
- `ESCALATE`

## 6. Logic điều kiện chính

- annual leave cần check balance
- leave type không hợp lệ -> correction
- work accident / maternity -> escalate, scope unsupported
- proof missing / unreadable -> need correction hoặc escalate
- overlap -> reject hoặc correction
- quota / handover / notice -> escalate hoặc correction tùy loại

## 7. Vai trò phê duyệt

Engine xác định `target_role` theo loại nghỉ và số ngày, ví dụ:

- `DIRECT_MANAGER`
- `DEPARTMENT_HEAD`
- `HR`
- `HRD`
- `CEO`

## 8. Kết luận

Rule engine là “decision tree” thực sự của hệ thống. Nó là lớp kiểm soát quyền năng và ứng xử theo policy.

## 9. Điểm mạnh

- Chắc chắn, mô hình deterministic
- Dễ kiểm chứng bằng test
- Không phụ thuộc vào model ngẫu nhiên

## 10. Hạn chế

- Chính sách hiện tại là demo và có phần cố định
- Một số branch chỉ là heuristic / điều kiện demo, chưa phải luật production
