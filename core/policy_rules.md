# QUY CHẾ PHÊ DUYỆT NGHỈ PHÉP NỘI BỘ DOANH NGHIỆP

> Nguồn tham chiếu: Bộ luật Lao động 2019; Luật Bảo hiểm xã hội 2024; các quy định, thông tư, nghị định liên quan; quy định nội bộ doanh nghiệp.

## 1. Nguyên tắc chung
- Đơn nghỉ phải được nộp đúng loại, đúng thời hạn và có đầy đủ hồ sơ, chứng từ theo quy định.
- Ngày làm việc được tính theo lịch làm việc của doanh nghiệp, không bao gồm ngày nghỉ hàng tuần, ngày lễ, tết theo quy định hiện hành.
- Nghỉ phép năm được tính trừ trực tiếp vào quỹ phép năm hiện có; nghỉ thai sản, nghỉ ốm theo chế độ BHXH, và các chế độ theo luật không trừ quỹ phép năm.
- Mọi quyết định phê duyệt, từ chối hoặc chuyển cấp phải được ghi nhận rõ ràng và có căn cứ pháp lý và quản trị nội bộ.

## 2. Các chế độ nghỉ phép
### 2.1. Nghỉ phép năm
- Người lao động được nghỉ phép năm theo mức tối thiểu theo luật và theo quy định nội bộ của doanh nghiệp.
- Số ngày xin nghỉ phải không vượt quá số dư phép năm hiện có.
- Đơn nghỉ phép năm không được làm sai lệch thời hạn báo trước.
- **Bàn giao công việc:** kỳ nghỉ từ 3 ngày làm việc trở lên (phép năm, nghỉ không lương) bắt buộc chỉ định người bàn giao (cùng phòng, đang làm việc, không nghỉ trùng). Người được chọn phải xác nhận (`PENDING_HANDOVER`); nếu từ chối, đơn quay về nhân viên.
- **Lối thoát:** nhân viên có thể chọn "Không có công việc phát sinh cần bàn giao" (`no_handover_needed`). Hệ thống hiển thị cảnh báo cho quản lý khi duyệt để quản lý tự kiểm chứng và chịu trách nhiệm.
- Thiếu cả người bàn giao lẫn lựa chọn ngoại lệ → yêu cầu chỉnh sửa (`HANDOVER_REQUIRED`).

### 2.2. Nghỉ ốm đau
- Nghỉ ốm phải có chứng từ y tế hợp lệ theo quy định.
- Khi nghỉ ốm, người lao động được hưởng chế độ theo Luật Bảo hiểm xã hội; doanh nghiệp không tự ý thay đổi quyền lợi do luật quy định.
- Nếu thiếu chứng từ hoặc không hợp lệ, đơn phải được yêu cầu bổ sung hoặc xử lý theo quy trình phù hợp.

### 2.3. Nghỉ thai sản
- Nghỉ thai sản là quyền lợi theo pháp luật, không trừ quỹ phép năm.
- Đơn phải kèm đầy đủ giấy tờ chứng minh theo quy định và được ghi nhận đúng quy trình.

### 2.4. Nghỉ việc riêng hưởng lương
- Áp dụng trong các trường hợp theo quy định của pháp luật và nội bộ doanh nghiệp.
- Phải có đủ hồ sơ minh chứng và được phê duyệt bởi cấp có thẩm quyền.

### 2.5. Nghỉ không lương
- Áp dụng khi người lao động nghỉ vì lý do cá nhân hoặc do chưa đủ điều kiện hưởng chế độ khác.
- Phải có lý do rõ ràng, có phê duyệt của quản lý và cấp có thẩm quyền.

## 3. Thẩm quyền phê duyệt
- Tự động phê duyệt: áp dụng cho đơn đơn giản, đủ điều kiện, đúng thời hạn, đủ hồ sơ và không vượt giới hạn theo quy định.
- Lead Team: phê duyệt các đơn nghỉ cần kiểm tra công việc, chứng từ và đảm bảo vận hành trong phạm vi của team.
- CEO: phê duyệt các đơn nghỉ dài hạn, phức tạp hoặc vượt thẩm quyền của Lead Team.
- Trường hợp đơn không đủ điều kiện, không đúng hồ sơ hoặc vi phạm nguyên tắc, phải yêu cầu bổ sung, từ chối hoặc chuyển cấp theo đúng thẩm quyền.

### 3.1. Nghiên cứu trường hợp theo thời lượng và nguồn chi trả
| Loại nghỉ | Thời lượng | Ai phê duyệt | Có lương không? | Nguồn chi trả |
|---|---|---|---|---|
| Nghỉ phép năm | 1–2 ngày | Hệ thống/AI nếu đủ điều kiện; nếu không thì Lead Team | Có | Doanh nghiệp |
| Nghỉ phép năm | 3–5 ngày | Lead Team | Có | Doanh nghiệp |
| Nghỉ phép năm | Trên 5 ngày liên tiếp | CEO | Có | Doanh nghiệp |
| Nghỉ ốm | 1 ngày | Hệ thống/AI nếu có chứng từ hợp lệ; nếu không thì Lead Team | Không | BHXH |
| Nghỉ ốm | 2–5 ngày | Lead Team | Không | BHXH |
| Nghỉ ốm | Trên 5 ngày | CEO theo quy định BHXH | Không | BHXH |
| Nghỉ thai sản | Theo quy định pháp luật | CEO theo thẩm quyền | Không trừ phép năm | BHXH |
| Nghỉ việc riêng hưởng lương | Bất kỳ thời lượng nào | Lead Team hoặc CEO theo thẩm quyền | Có | Doanh nghiệp |
| Nghỉ không lương | Bất kỳ thời lượng nào | Lead Team hoặc CEO theo thẩm quyền | Không | Không có |

### 3.2. Giải thích từng trường hợp
- Nghỉ phép năm là chế độ nghỉ có lương. Số ngày nghỉ bị trừ trực tiếp khỏi quỹ phép năm hiện có. Nếu đủ quỹ phép, đúng thời hạn và hồ sơ hợp lệ, đơn có thể được phê duyệt theo quy trình thông thường; nếu không đủ hoặc không đúng quy định thì phải xem xét lại hoặc chuyển cấp.
- Nghỉ ốm là chế độ theo quy định bảo hiểm y tế và BHXH. Doanh nghiệp không tự ý trả lương cho các ngày nghỉ ốm; nguồn chi trả chính là quỹ BHXH theo luật. Chứng từ y tế phải hợp lệ.
- Nghỉ thai sản là quyền lợi theo pháp luật, không trừ vào phép năm và không tính là nghỉ không lương. Nguồn chi trả là BHXH theo chế độ thai sản.
- Nghỉ việc riêng hưởng lương là các trường hợp được nghỉ có lương theo pháp luật và quy định nội bộ doanh nghiệp. Phải có chứng từ và được phê duyệt theo thẩm quyền.
- Nghỉ không lương áp dụng khi người lao động nghỉ vì lý do cá nhân hoặc không thuộc các chế độ có lương khác. Không có lương do doanh nghiệp chi trả.

### 3.3. Bảng 3.1. Đối chiếu Database và Rule hiện tại
| Trường hợp | AI phê duyệt | Lead Team | CEO | Đối chiếu với Database / Quy tắc hệ thống |
|---|---|---|---|---|
| Nghỉ phép năm 1–2 ngày, đủ phép, đúng hồ sơ | Có | Không bắt buộc nếu AI chấp nhận | Không bắt buộc | `remaining_leave_days` đủ; hệ thống trừ quỹ phép nếu đơn được duyệt |
| Nghỉ phép năm 3–5 ngày | Không | Có | Không bắt buộc | `rule_engine.py` chuyển `n >= 3` tới `DIRECT_MANAGER` / Lead Team; nếu duyệt thì trừ quỹ phép |
| Nghỉ phép năm từ 20 ngày trở lên | Không | Có thể xem xét đầu vào | Bắt buộc phê duyệt cuối | `rule_engine.py` dùng `CEO` cho `ANNUAL` khi `n >= 20`; cần xác nhận cuối cùng |
| Nghỉ ốm 1 ngày hợp lệ | Có nếu có chứng từ hợp lệ | Không bắt buộc nếu đủ chứng từ | Không bắt buộc | Không trừ phép năm; phải có chứng từ hợp lệ và phù hợp với đơn |
| Nghỉ ốm 2–5 ngày | Không | Có | Không bắt buộc | Chuyển tới `DIRECT_MANAGER` / Lead Team; không trừ phép năm |
| Nghỉ việc riêng hưởng lương | Không | Có | Không bắt buộc ở hầu hết trường hợp | Yêu cầu chứng từ, sự kiện hợp pháp và xác nhận theo thẩm quyền |
| Nghỉ không lương | Không | Có | Có thể yêu cầu khi dài hạn | Không trừ phép năm; cần lý do rõ ràng và phê duyệt quản lý / cấp cao |

### 3.4. Định nghĩa 3 Kiểu Dừng Quyết Định Chuẩn (Three Spec Stops)
Hệ thống tuân thủ nghiêm ngặt 3 kiểu dừng xử lý độc lập để đảm bảo ranh giới con người (Human-in-the-loop) và ngăn chặn việc đoán mò:

1. **Kiểu dừng 1 - `AUTO_APPROVE` (Tự Động Duyệt):**
   - Đơn thỏa mãn 100% các tiêu chuẩn chính sách: đủ ngày phép, không trùng lặp, báo trước đúng hạn, tỷ lệ vắng mặt < 30%, chứng từ y tế đã xác minh hợp lệ và thời lượng nằm trong ngưỡng cho phép tự động của AI (≤ 2 ngày phép năm, 1 ngày nghỉ ốm).
   - Hệ thống tự động phê duyệt và trừ số dư quỹ phép ngay lập tức (nếu là phép năm).

2. **Kiểu dừng 2 - `NEED_CORRECTION` / `AUTO_REJECT` (Yêu Cầu Nhân Viên Bổ Sung / Từ Chối):**
   - Trường hợp đơn vi phạm các điều kiện hình thức hoặc dữ liệu tiên quyết mà nhân viên có thể tự khắc phục: thiếu ngày, ngày kết thúc trước ngày bắt đầu, thiếu chứng từ, thiếu người bàn giao khi nghỉ ≥ 3 ngày, hoặc vượt quá quỹ phép năm hiện có.
   - Trạng thái trả về: `WAITING_EMPLOYEE` hoặc `REJECTED`, yêu cầu nhân viên tự điều chỉnh lại dữ liệu, không làm phiền cấp quản lý khi đơn chưa hoàn thiện.

3. **Kiểu dừng 3 - `ESCALATE` (Dừng Chuyển Người Có Thẩm Quyền / Human-in-the-Loop):**
   - Hệ thống dừng tự động hóa và tạo câu hỏi nghiệp vụ cụ thể (`actionable_question`) gửi đúng cấp thẩm quyền:
     - **Quản lý trực tiếp (`DIRECT_MANAGER`):** Đơn nghỉ phép năm 3–5 ngày, đơn nghỉ ốm 2–5 ngày, đơn vi phạm thời hạn báo trước, đơn vượt quota phòng ban, hoặc chứng từ mờ (`DOC_ILLEGIBLE`).
     - **Nhân sự (`HR`):** Đơn nghỉ ốm có chứng từ y tế mới cần đối chiếu tính xác thực pháp lý (`PROOF_REVIEW_REQUIRED`), chế độ thai sản/tai nạn lao động, hoặc lịch làm việc chưa rõ.
     - **Cấp cao (`DEPARTMENT_HEAD`, `CEO`):** Các đợt nghỉ dài ngày (> 5 ngày hoặc ≥ 20 ngày).

> Lưu ý: Theo logic hiện tại, hệ thống phân bổ quyền phê duyệt đúng vai trò theo ma trận phân cấp. AI chỉ thực hiện đánh giá tự động theo điều kiện, không thay thế quyết định của con người khi đơn vượt ngưỡng, thiếu thông tin hoặc có rủi ro.

## 4. Thời hạn báo trước và hồ sơ
- Đơn nghỉ phải được nộp trước khi bắt đầu nghỉ theo mức thời hạn tối thiểu do doanh nghiệp quy định và theo yêu cầu vận hành.
- Đối với nghỉ ốm hoặc trường hợp khẩn cấp, chứng từ và thông tin cần được bổ sung trong thời gian sớm nhất.
- Người lao động có trách nhiệm cung cấp thông tin đầy đủ, chính xác và kịp thời.

## 5. Xử lý hồ sơ không hợp lệ
- Nếu thiếu chứng từ, không rõ ngày hoặc không đúng dạng, đơn phải được yêu cầu chỉnh sửa.
- Nếu chứng từ mờ, hệ thống không tự đoán: đơn được chuyển lên quản lý trực tiếp (`DOC_ILLEGIBLE`), vì quản lý có thể đọc được bản gốc hoặc yêu cầu nộp lại bản rõ hơn.
- Nếu vượt quá quỹ phép năm, không có căn cứ pháp lý hợp lệ, hoặc đơn không phù hợp với loại nghỉ được phép, đơn có thể bị từ chối.
- Nếu có dấu hiệu lạm dụng hoặc nhiều đợt nghỉ rời rạc trong cùng thời gian, quản lý có quyền xem xét và xử lý theo nguyên tắc công bằng, hợp lý và đúng quy định.

## 6. Hiệu lực
- Quy chế này có hiệu lực kể từ ngày ban hành và áp dụng cho toàn bộ nhân sự trong doanh nghiệp.
- Mọi quy định trước đó trái với quy chế này được điều chỉnh, bổ sung hoặc bãi bỏ theo mức cần thiết.
