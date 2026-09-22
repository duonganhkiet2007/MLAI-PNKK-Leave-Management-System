# TÓM TẮT CASE KIỂM NGHIỆM

## 1. 5 case thử nghiệm nhanh

| Case | Input chính | Output kỳ vọng | Kết luận |
|---|---|---|---|
| 1. Annual hợp lệ | `leave_type=ANNUAL`, đủ balance, 2 ngày, có bàn giao | `AUTO_APPROVE`, `deducted_days=2`, `annual_balance_change=-2` | Flow cơ bản chạy đúng |
| 2. Annual vượt balance | `leave_type=ANNUAL`, balance còn 1, xin 2 ngày | `AUTO_REJECT`, `error_code=BALANCE_EXCEEDED` | Không được nghỉ vượt quỹ |
| 3. Annual thiếu ngày | `leave_type=ANNUAL`, thiếu `from_date` | `NEED_CORRECTION`, `error_code=DATE_MISSING` | Cần bổ sung dữ liệu |
| 4. Annual 3-5 ngày | `leave_type=ANNUAL`, 3 ngày | `ESCALATE`, `target_role=DIRECT_MANAGER` | Chuyển lên reviewer |
| 5. Sick medical 3 ngày | `leave_type=SICK_MEDICAL`, có proof hợp lệ, 3 ngày | `ESCALATE`, `target_role=DIRECT_MANAGER`, `error_code=DURATION_OVER_AI_LIMIT` | Vượt ngưỡng auto approve |
# TÓM TẮT 15 CASE KIỂM NGHIỆM TỪ KHO DỮ LIỆU

| Case | Input chính | Output kỳ vọng | Kết luận |
|---|---|---|---|
| TC01 | `ANNUAL`, 2 ngày, balance đủ, có bàn giao | `AUTO_APPROVE`, `deducted_days=2`, `annual_balance_change=-2` | Hợp lệ, auto approve |
| TC02 | `ANNUAL`, balance còn 1, xin 2 ngày | `AUTO_REJECT`, `error_code=BALANCE_EXCEEDED` | Vượt quỹ phép |
| TC03 | `ANNUAL`, thiếu `from_date` | `NEED_CORRECTION`, `error_code=DATE_MISSING` | Thiếu thông tin |
| TC04 | `ANNUAL`, 3 ngày | `ESCALATE`, `target_role=DIRECT_MANAGER` | Cần review cấp 1 |
| TC05 | `ANNUAL`, 6-19 ngày | `ESCALATE`, `target_role=DEPARTMENT_HEAD` | Cần review cấp 2 |
| TC06 | `ANNUAL`, >=20 ngày | `ESCALATE`, `target_role=CEO` | Phải lên CEO |
| TC07 | `ANNUAL`, ngày lễ / holiday | `NO_LEAVE_REQUIRED`, `error_code=DAY_ALREADY_NON_WORKING` | Không tính ngày nghỉ |
| TC08 | `ANNUAL`, range có holiday | `AUTO_APPROVE`, `requested_working_days=1` | Chỉ tính ngày làm việc thực tế |
| TC11 | `SPECIAL_PAID`, cưới hỏi, có giấy chứng nhận | `ESCALATE`, `target_role=DIRECT_MANAGER` | Cần xác minh theo quy định |
| TC12 | `SPECIAL_PAID`, con cưới, hồ sơ hợp lệ | `ESCALATE`, `target_role=DIRECT_MANAGER` | Cùng nhóm quyền lợi |
| TC14 | `STATUTORY_UNPAID`, tang ông bà | `ESCALATE`, `target_role=DIRECT_MANAGER` | Cần xác minh quan hệ thân nhân |
| TC15 | `SICK_MEDICAL`, chứng từ hợp lệ 2 ngày | `ESCALATE`, `target_role=DIRECT_MANAGER` | Y tế hợp lệ nhưng vẫn lên review |
| TC16 | `SICK_MEDICAL`, thiếu chứng từ | `NEED_CORRECTION`, `error_code=PROOF_MISSING` | Thiếu chứng từ |
| TC17 | `SICK_MEDICAL`, giấy tờ không đọc được | `ESCALATE`, `error_code=DOC_ILLEGIBLE` | Chứng từ không rõ |
| TC18 | `SICK_MEDICAL`, ngày trên giấy khác với đơn | `NEED_CORRECTION`, `error_code=MEDICAL_DAYS_MISMATCH` | Mâu thuẫn thời gian |
| TC19 | `ANNUAL`, thiếu người bàn giao | `NEED_CORRECTION`, `error_code=HANDOVER_REQUIRED` | Thiếu bàn giao |
| TC21 | `ANNUAL`, team absent quá quota | `ESCALATE`, `error_code=TEAM_QUOTA_EXCEEDED` | Rủi ro vận hành |
| TC22 | `ANNUAL`, đơn trùng lịch đã duyệt | `AUTO_REJECT`, `error_code=REQUEST_ALREADY_COVERED` | Trùng đơn |
| TC24 | `MATERNITY` | `ESCALATE`, `target_role=HR` | Phức tạp, cần review |
| TC26 | `ANNUAL`, nhân viên thử việc | `NEED_CORRECTION`, `error_code=PROBATION_ANNUAL_RESTRICTED` | Không dùng annual trong thử việc |
| TC28 | `UNPAID_OTHER`, <=5 ngày | `ESCALATE`, `target_role=DIRECT_MANAGER` | Nghỉ không lương dài ngắn vẫn cần review |
| TC30 | `UNPAID_OTHER`, >=20 ngày | `ESCALATE`, `target_role=DEPARTMENT_HEAD` | Dài, cần cấp cao |

## 1. Nhận xét nhanh

- Flow gốc: hợp lệ -> `AUTO_APPROVE`
- Thiếu thông tin -> `NEED_CORRECTION`
- Vi phạm rule -> `AUTO_REJECT`
- Quá ngưỡng / phức tạp -> `ESCALATE`
- Dài hạn / pháp lý -> `DEPARTMENT_HEAD` hoặc `CEO`

## 2. Một câu tóm tắt

Kho dữ liệu có rất nhiều case, nhưng 15 case này đủ để phản ánh toàn bộ luồng xử lý: input hợp lệ, thiếu thông tin, vi phạm, chứng từ, rủi ro vận hành, và quyền phê duyệt theo cấp độ.