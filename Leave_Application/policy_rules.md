# QUY CHẾ PHÊ DUYỆT NGHỈ PHÉP NỘI BỘ (LEAVE POLICY GROUND TRUTH)
*Mã tài liệu: POL-HR-2026-01 | Phiên bản: 2.0 (Áp dụng cho Hệ thống Điều phối Phê duyệt AI)*

---

## MỤC 1. CÁC CHẾ ĐỘ NGHỈ PHÉP & ĐIỀU KIỆN CHỨNG TỪ

### 1.1. Nghỉ phép năm (Annual Leave - AL)
* **Định mức tiêu chuẩn:** 12 ngày/năm làm việc trong điều kiện bình thường (Điều 113 BLLĐ 2019).
* **Thâm niên:** Cứ đủ mỗi 05 năm làm việc tại công ty được cộng thêm 01 ngày phép (Điều 114 BLLĐ 2019).
* **Nguyên tắc trừ quỹ:** Trừ trực tiếp vào số dư ngày phép năm hiện có (`remaining_annual_leave`).
* **Hạn mức số dư:** Không cho phép nghỉ phép năm vượt quá số dư hiện có (`duration <= remaining_annual_leave`). Trường hợp hết phép năm, nhân sự bắt buộc phải làm đơn xin **Nghỉ việc riêng không hưởng lương**.

### 1.2. Nghỉ ốm đau (Sick Leave - SL)
* **Trách nhiệm chi trả:** Doanh nghiệp không trả lương những ngày này; chế độ trợ cấp ốm đau do Quỹ Bảo hiểm Xã hội (BHXH) chi trả theo quy định pháp luật.
* **Quy chuẩn chứng từ theo thời gian nghỉ:**
  * **Nghỉ 01 ngày:** Báo cáo quản lý trước ca làm việc; chấp nhận toa thuốc hoặc phiếu khám bệnh thông thường.
  * **Nghỉ từ 02 ngày liên tiếp trở lên:** Bắt buộc đính kèm một trong hai loại chứng từ hợp lệ theo chuẩn Bộ Y tế:
    1. *Giấy chứng nhận nghỉ việc hưởng BHXH* (mẫu theo Thông tư 56/2017/TT-BYT & TT 18/2022/TT-BYT).
    2. *Giấy ra viện* (nếu điều trị nội trú).
  * **Yêu cầu hình ảnh chứng từ:** Phải rõ nét, thấy rõ họ tên nhân viên, thời gian bác sĩ chỉ định nghỉ, chữ ký bác sĩ và con dấu mộc đỏ của cơ sở y tế. Nếu ảnh mờ, mất góc hoặc không đúng mẫu, hệ thống không được tự ý công nhận.

### 1.3. Nghỉ việc riêng hưởng nguyên lương (Special Paid Leave - SPL)
Áp dụng theo Điều 115 Bộ luật Lao động 2019 (không trừ vào quỹ phép năm, công ty chi trả 100% lương):
* Bản thân kết hôn: **03 ngày làm việc** (kèm ảnh Giấy chứng nhận kết hôn hoặc Thiệp cưới).
* Con đẻ, con nuôi kết hôn: **01 ngày làm việc** (kèm ảnh Giấy chứng nhận kết hôn của con).
* Cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi; cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi của vợ/chồng; vợ hoặc chồng; con đẻ, con nuôi chết: **03 ngày làm việc** (kèm Giấy chứng tử/báo tử).

### 1.4. Nghỉ việc riêng không hưởng lương (Unpaid Leave - UL)
* **Luật định (Điều 115 BLLĐ 2019):** Được nghỉ 01 ngày khi ông/bà nội ngoại, anh chị em ruột chết; cha mẹ hoặc anh chị em kết hôn (phải thông báo trước).
* **Thỏa thuận khác:** Nghỉ vì việc cá nhân khi đã hết phép năm. Phải có lý do giải trình cụ thể và được phê duyệt theo thẩm quyền.

---

## MỤC 2. QUY ĐỊNH THỜI HẠN BÁO TRƯỚC (NOTICE PERIOD)

Thời hạn nộp đơn hợp lệ được tính từ mốc thời gian gửi đơn (`submitted_at`) đến **08:30 sáng** của ngày bắt đầu nghỉ làm việc đầu tiên (`from_date`):

| Thời lượng nghỉ dự kiến | Thời hạn nộp đơn trước tối thiểu |
| :--- | :--- |
| **Nghỉ $\le 02$ ngày làm việc** | Tối thiểu **24 giờ** trước ca làm việc. |
| **Nghỉ từ $03$ đến $05$ ngày làm việc** | Tối thiểu **03 ngày làm việc** (không tính T7, CN). |
| **Nghỉ $> 05$ ngày làm việc** hoặc **Nghỉ không lương** | Tối thiểu **07 ngày làm việc**. |
| **Nghỉ ốm đột xuất / Sự cố khẩn cấp** | Gửi đơn hoặc báo cáo trước **08:30 sáng** của ngày nghỉ đầu tiên. Đơn gửi sau 08:30 sáng bị tính là vi phạm thời hạn báo trước. |

---

## MỤC 3. ĐIỀU KIỆN VẬN HÀNH & BÀN GIAO CÔNG VIỆC

### 3.1. Hạn mức vắng mặt phòng ban (Team Absence Quota)
* Trong bất kỳ ngày làm việc nào, tỷ lệ vắng mặt do nghỉ phép trong một phòng ban/đội nhóm không được vượt quá **30% tổng quân số** của bộ phận đó:
  $$\text{Tỷ lệ vắng mặt} = \frac{\text{Số nhân sự đã được duyệt nghỉ trong ngày} + 1}{\text{Tổng nhân sự phòng ban}} \le 30\%$$
* Nếu tỷ lệ này vượt quá 30%, đơn nghỉ phép rơi vào trạng thái nguy cơ gián đoạn vận hành và không được tự động duyệt.

### 3.2. Bàn giao công việc (Handover / Backup Requirement)
* Đơn xin nghỉ từ **03 ngày làm việc liên tục trở lên** bắt buộc phải chỉ định nhân sự nhận bàn giao công việc (`handover_person_id`).
* **Điều kiện người bàn giao:** 
  1. Thuộc cùng phòng ban với người làm đơn.
  2. Tài khoản đang hoạt động (active) trên hệ thống nhân sự.
  3. Không có lịch nghỉ phép trùng vào khoảng thời gian người nộp đơn vắng mặt.
  4. Không được trùng với chính người làm đơn.

---

## MỤC 4. PHÂN CẤP THẨM QUYỀN & NGUYÊN TẮC HOẠT ĐỘNG CỦA AI

### 4.1. Bảng phân cấp thẩm quyền

| Cấp phê duyệt | Phạm vi thẩm quyền tối đa | Hành vi của Hệ thống |
| :--- | :--- | :--- |
| **Hệ thống AI (Tier 0)** | • Nghỉ phép năm $\le 02$ ngày.<br>• Nghỉ ốm $01$ ngày.<br>• Thỏa mãn 100% điều kiện: Đủ phép, đúng hạn báo trước, quota team $\le 30\%$, chứng từ hợp lệ. | **TỰ ĐỘNG DUYỆT (AUTO_APPROVE)**.<br>Ghi nhật ký kiểm toán (Audit Log). |
| **Trưởng phòng / Manager (Tier 1)** | • Nghỉ phép năm từ **$03$ đến $05$ ngày**.<br>• Nghỉ ốm $\ge 02$ ngày (đủ giấy tờ y tế hợp lệ).<br>• Các ngoại lệ vi phạm thời hạn nộp hoặc vi phạm quota team 30%. | **CHUYỂN TIẾP (ESCALATE)**.<br>Tạo câu hỏi trực diện cho Trưởng phòng quyết định. |
| **Giám đốc Khối / HR Director (Tier 2)**| • Nghỉ phép năm **$> 05$ ngày liên tiếp**.<br>• Nghỉ việc riêng không hưởng lương dài hạn ($> 14$ ngày).<br>• Tạm ứng quỹ phép năm sau. | **CHUYỂN TIẾP (ESCALATE)**.<br>Tạo câu hỏi thẩm quyền gửi cấp Giám đốc. |

### 4.2. Nguyên tắc an toàn cốt lõi (Guardrails)
1. **Tuyệt đối không tự ý phê duyệt** bất kỳ trường hợp nào có dữ liệu bị nghi vấn, chứng từ mờ/không xác thực hoặc vi phạm quy định.
2. **Không chuyển tiếp chung chung:** Mọi quyết định ESCALATE phải phân loại đúng 1 trong 3 nhóm và kèm câu hỏi hành động đầy đủ ngữ cảnh để người duyệt quyết định ngay trong 1 click.

---

## MỤC 5. CHUẨN HÓA BẢNG MÃ LỖI CHUYỂN TIẾP (ESCALATION TAXONOMY)

Khi không thể tự động phê duyệt, hệ thống bắt buộc phải phân loại lý do vào đúng một trong 3 nhóm sau:

### Nhóm 1: `UNCERTAIN_FACTS` (Chưa xác định được thông tin thực tế)
*Áp dụng khi dữ liệu đầu vào bị thiếu, sai định dạng, mâu thuẫn hoặc không thể xác minh bằng chứng từ.*
* `DOC_ILLEGIBLE`: Ảnh chụp chứng từ y tế / kết hôn / tang chế bị mờ, mất góc, không nhận diện được ngày cấp hoặc mộc cơ sở y tế.
* `DATE_LOGIC_INVALID`: Ngày kết thúc trước ngày bắt đầu (`from_date > to_date`) hoặc số ngày xin nghỉ là số âm/bằng 0.
* `HANDOVER_INVALID`: Nhân sự nhận bàn giao không tồn tại, đã nghỉ việc, trùng chính người nộp đơn, hoặc đang có lịch nghỉ trùng.
* `MEDICAL_DAYS_MISMATCH`: Số ngày xin nghỉ ốm vượt quá số ngày bác sĩ chỉ định trên Giấy chứng nhận nghỉ BHXH.

### Nhóm 2: `OUT_OF_POLICY` (Nằm ngoài phạm vi quy định)
*Áp dụng khi dữ liệu đầu vào rõ ràng nhưng vi phạm các điều khoản quy chế; cần con người xem xét đặc cách.*
* `NOTICE_PERIOD_VIOLATED`: Nộp đơn trễ hơn thời hạn quy định (ví dụ: nghỉ 1 ngày nhưng nộp trước 2 tiếng, hoặc nghỉ ốm báo sau 08:30 sáng).
* `BALANCE_EXCEEDED`: Số ngày xin nghỉ phép năm vượt quá số dư hiện có (`duration > remaining_annual_leave`).
* `TEAM_QUOTA_EXCEEDED`: Số lượng người nghỉ trong phòng ban vào ngày đó vượt quá ngưỡng cho phép ($> 30\%$).
* `UNQUALIFIED_SPECIAL_LEAVE`: Xin nghỉ việc riêng có lương nhưng lý do không thuộc các trường hợp quy định tại Điều 115 BLLĐ 2019.

### Nhóm 3: `AUTHORITY_ESCALATION` (Vượt thẩm quyền xử lý tự động)
*Áp dụng khi hồ sơ hoàn toàn hợp lệ, thông tin minh bạch nhưng quy mô vượt trần tự duyệt của AI/Tier 0.*
* `DURATION_OVER_AI_LIMIT`: Đơn nghỉ phép năm hợp lệ từ $03$ đến $05$ ngày làm việc (thuộc thẩm quyền Manager).
* `DURATION_OVER_MANAGER_LIMIT`: Đơn nghỉ phép năm hợp lệ $> 05$ ngày làm việc (thuộc thẩm quyền Giám đốc/HRD).
* `LONG_TERM_UNPAID`: Đơn xin nghỉ việc riêng không hưởng lương dài hạn ($> 14$ ngày làm việc).