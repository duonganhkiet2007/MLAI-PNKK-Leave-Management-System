# Policy / Rule Definition Report

## 1. Mục đích

Bộ quy định này là nguồn tham chiếu chính cho mô hình quyết định. Nó chứa nguyên tắc về:

- các loại nghỉ
- thẩm quyền phê duyệt
- số ngày tối đa / điều kiện
- chứng từ
- thời hạn báo trước
- quyền lợi và nguồn chi trả

## 2. File chính

- [Leave_Application/policy_rules.md](../../Leave_Application/policy_rules.md)
- [Leave_Application/raw_policy.json](../../Leave_Application/raw_policy.json)
- [Leave_Application/domain.py](../../Leave_Application/domain.py)
- [Leave_Application/taxonomy.py](../../Leave_Application/taxonomy.py)

## 3. Các loại nghỉ chính

- annual
- special paid
- statutory unpaid
- unpaid other
- sick medical
- medical emergency
- work accident
- maternity

## 4. Thẩm quyền phê duyệt

Policy mô tả các nhóm quyền lực:

- employee
- direct manager
- department head
- HR
- HRD
- CEO

## 5. Lý luận chính

Policy định rõ rằng:

- annual leave trừ quỹ phép năm
- medical / maternity / work accident theo chế độ riêng
- proof và verification là điều kiện bắt buộc ở nhiều loại nghỉ
- nhiều trường hợp cần human review / escalation

## 6. Mối quan hệ với code

Policy file là phần văn bản gốc, còn `rule_engine.py` là triển khai thực thi theo logic. Nói cách khác:

- policy rules = nguồn quy phạm
- rule engine = thực thi quyết định

## 7. Điểm mạnh

- có sự phân tách rõ giữa quy định và logic chạy
- định nghĩa đúng vai trò phê duyệt và loại nghỉ

## 8. Hạn chế

- một số phần là mô tả policy nội bộ / demo hơn là luật production
- không phải lúc nào cũng đồng nghĩa hoàn toàn với runtime code
- cần đối chiếu kỹ với thực thi trong `rule_engine.py`

## 9. Kết luận

Policy file là nền tảng cho toàn bộ hệ thống và là tài liệu tham chiếu quan trọng để đọc logic quyết định.
