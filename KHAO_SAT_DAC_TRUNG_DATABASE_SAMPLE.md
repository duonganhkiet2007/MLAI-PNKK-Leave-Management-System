# 📊 BẢN KHẢO SÁT TOÀN DIỆN: CÁC ĐẶC TRƯNG BẮT BUỘC CỦA 1 SAMPLE DỮ LIỆU
## HỆ THỐNG ĐIỀU PHỐI PHÊ DUYỆT NGHỈ PHÉP AI — THE ESCALATION REFEREE

> **Tài liệu tham chiếu căn cứ:**  
> - `Leave_Application/policy_rules.md` (Quy chế phê duyệt nghỉ phép nội bộ doanh nghiệp - Authoritative Sole Source of Truth)  
> - `Leave_Application/domain.py` & `Leave_Application/taxonomy.py` (Mô hình thực thể chuẩn hóa & Cây phân loại quyết định)  
> - `Leave_Application/vlm_inspector.py` (Mô hình thị giác máy tính VLM kiểm định chứng từ y tế/pháp lý)  
> - `Leave_Application/rule_engine.py` (Bộ máy suy diễn quy chế tất định)  
> - `DANH_SACH_TRUONG_HOP_ESCALATION.md` (Ma trận 18 tình huống chuyển tiếp cho con người)  

---

## 📌 I. TỔNG QUAN KIẾN TRÚC: MỘT "SAMPLE" HOÀN CHỈNH GỒM NHỮNG GÌ?

Trong hệ thống AI điều phối nghỉ phép, một **Sample (Mẫu dữ liệu hoàn chỉnh)** không đơn thuần chỉ là một dòng đăng ký ngày nghỉ, mà là một **hồ sơ tổng hợp 4 tầng dữ liệu (4-Layer Canonical Record)**. 

Nếu thiếu bất kỳ tầng nào, hệ thống sẽ bị khuyết tính năng (ví dụ: không tính được tỷ lệ vắng mặt phòng ban 30%, không kiểm tra được tính thật giả của chứng từ, hoặc không thể sinh câu hỏi hành động cho Quản lý).

```
┌────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: PROFILE NHÂN SỰ & TỔ CHỨC (Employee & Org Context)            │
│ • Định danh, chức vụ, thâm niên, số dư phép, quân số phòng, tỷ lệ vắng  │
├────────────────────────────────────────────────────────────────────────┤
│ TẦNG 2: DỮ LIỆU ĐĂNG KÝ NGHỈ PHÉP (Leave Request Facts)               │
│ • Loại nghỉ, lý do chuẩn hóa, ngày bắt đầu/kết thúc, giờ nộp đơn,      │
│   nhân sự nhận bàn giao, số ngày phép đã nghỉ dồn trong tháng          │
├────────────────────────────────────────────────────────────────────────┤
│ TẦNG 3: THẨM ĐỊNH CHỨNG TỪ BẰNG VLM (Proof & Visual Inspection)       │
│ • Loại giấy tờ, độ nét, tên bệnh nhân, chẩn đoán, số ngày bác sĩ cho,  │
│   mộc đỏ, chữ ký, kiểm tra dấu hiệu photoshop/AI giả mạo, điểm tương quan│
├────────────────────────────────────────────────────────────────────────┤
│ TẦNG 4: ĐÁNH GIÁ QUY CHẾ & PHÊ DUYỆT (Rule Engine & Human Resolution)  │
│ • Ngày làm việc thực tế, chế độ lương, quyết định (Auto/Escalate),     │
│   mã lỗi, cấp thẩm quyền duyệt, câu hỏi hành động, vết giải trình      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🏢 II. CHI TIẾT CÁC ĐẶC TRƯNG THEO TỪNG TẦNG DỮ LIỆU

### 1. TẦNG 1: PROFILE NHÂN SỰ & TỔ CHỨC (EMPLOYEE CONTEXT)
*Cung cấp căn cứ để kiểm tra tư cách pháp lý, hạn mức số dư phép năm và quy định hạn mức vắng mặt của phòng ban.*

| STT | Tên đặc trưng (Field) | Kiểu dữ liệu | Giá trị mẫu | Mục đích kỹ thuật & Căn cứ quy chế |
| :---: | :--- | :---: | :--- | :--- |
| 1 | `employee_id` | `String` | `"EMP012"` | Mã định danh duy nhất của nhân viên làm đơn. |
| 2 | `name` / `employee_name` | `String` | `"Nguyễn Văn An"` | Họ tên nhân sự. Dùng đối soát chéo với tên người bệnh/người thụ hưởng trên chứng từ y tế/kết hôn (`doc_patient_name`). |
| 3 | `department` | `String` | `"Engineering"` | Phòng ban làm việc. Dùng để tính tỷ lệ vắng mặt 30% và gom nhóm thẩm quyền duyệt cho Trưởng phòng. |
| 4 | `role` | `String` | `"Software Engineer"` | Chức vụ/vị trí công tác của nhân sự. |
| 5 | `manager_id` | `String` | `"EMP015"` | Mã của Quản lý trực tiếp. Đơn cần chuyển tiếp Cấp 1 sẽ gửi đích danh đến người này. Nếu nhân sự chính là CEO/Trưởng phòng, hệ thống áp dụng cơ chế chuyển tiếp cấp cao hơn (`MANAGER_SELF_APPROVAL`). |
| 6 | `remaining_leave_days` | `Float` | `8.0` | Số dư ngày phép năm hiện có trước khi nghỉ. Bắt buộc có để kiểm tra lỗi vượt quỹ phép `BALANCE_EXCEEDED` (Điều 2.1). |
| 7 | `hire_date` | `Date` | `"2023-08-15"` | Ngày vào làm việc. Dùng tính thâm niên (cứ 5 năm thêm 1 ngày phép) và xác định nhân viên thử việc (chưa được hưởng phép năm có lương, Điều 2.6). |
| 8 | `status` | `Enum` | `"ACTIVE"` | Trạng thái nhân sự: `ACTIVE` (Chính thức), `PROBATION` (Thử việc), `SUSPENDED` (Tạm hoãn). |
| 9 | `total_team_members` | `Integer` | `8` | Tổng số nhân sự của phòng ban tại thời điểm xét đơn (mẫu số để tính tỷ lệ vắng mặt phòng ban). |
| 10 | `concurrent_absences` | `Integer` | `1` | Số lượng nhân sự khác trong cùng phòng ban đã có lịch nghỉ trùng với khoảng thời gian này (tử số để tính quota 30%, Điều 4.1). |

---

### 2. TẦNG 2: DỮ LIỆU ĐĂNG KÝ NGHỈ PHÉP (LEAVE REQUEST FACTS)
*Dữ liệu do người lao động nhập vào form xin nghỉ phép trên giao diện web.*

| STT | Tên đặc trưng (Field) | Kiểu dữ liệu | Giá trị mẫu | Mục đích kỹ thuật & Căn cứ quy chế |
| :---: | :--- | :---: | :--- | :--- |
| 11 | `id` / `request_id` | `String` | `"REQ-2026-001"` | Mã đơn xin nghỉ phép duy nhất trong cơ sở dữ liệu. |
| 12 | `leave_type` | `Enum` | `"ANNUAL"` | Phân loại quyền lợi nghỉ: `ANNUAL` (Phép năm), `SICK_MEDICAL` (Nghỉ ốm BHXH), `SPECIAL_PAID` (Nghỉ chế độ có lương), `STATUTORY_UNPAID` (Nghỉ luật định không lương 1 ngày), `UNPAID_OTHER` (Nghỉ việc riêng không lương), `MATERNITY` (Thai sản), `PUBLIC_HOLIDAY`, `WEEKLY_REST`. |
| 13 | `reason_category` | `Enum` | `"PERSONAL"` | Nhóm lý do chuẩn hóa theo Điều 115 Bộ luật Lao động 2019: `PERSONAL`, `SELF_MARRIAGE`, `CHILD_MARRIAGE`, `PARENT_DEATH`, `SPOUSE_PARENT_DEATH`, `SPOUSE_DEATH`, `CHILD_DEATH`, `GRANDPARENT_DEATH`, `SIBLING_DEATH`, `PARENT_MARRIAGE`, `SIBLING_MARRIAGE`. |
| 14 | `reason` | `String` | `"Nghỉ theo dõi sức khỏe tại nhà do cảm cúm"` | Đoạn văn bản mô tả chi tiết lý do. LLM dùng đoạn này để phân tích tính hợp lệ và ngữ cảnh thực tế. |
| 15 | `from_date` | `Date` | `"2026-09-22"` | Ngày bắt đầu xin nghỉ (định dạng `YYYY-MM-DD`). |
| 16 | `to_date` | `Date` | `"2026-09-23"` | Ngày kết thúc xin nghỉ (định dạng `YYYY-MM-DD`). Phải thỏa mãn `to_date >= from_date`, nếu không bắt lỗi `DATE_RANGE_INVALID`. |
| 17 | `submitted_at` | `DateTime` | `"2026-09-21T07:30:00+07:00"` | **Đặc trưng cực kỳ quan trọng**: Thời điểm bấm nộp đơn. Dùng để đối chiếu mốc **08:30 sáng** của ca làm việc (với đơn ốm đau khẩn cấp) và thời hạn nộp trước tối thiểu 24 giờ / 3 ngày / 7 ngày / 15 ngày (Điều 3). |
| 18 | `handover_person_id` | `String` | `"EMP015"` | Mã nhân sự nhận bàn giao công việc. Bắt buộc có với đơn phép năm (`ANNUAL`) hoặc không lương (`UNPAID_OTHER`) có tổng thời lượng $\ge 3$ ngày làm việc (Điều 4.2). |
| 19 | `handover_person_name`| `String` | `"Đỗ Hoàng Long"` | Tên nhân sự nhận bàn giao công việc. |
| 20 | `handover_validity` | `Boolean` | `True` | Cờ xác thực người bàn giao: phải cùng phòng ban, trạng thái `ACTIVE`, không có lịch nghỉ trùng khoảng này và không được là chính bản thân người làm đơn (Điều 4.3). |
| 21 | `monthly_accumulated_days`| `Float`| `2.0` | Số ngày phép năm đã nghỉ hoặc đã nộp trong cùng tháng dương lịch. Dùng để phát hiện hành vi chia nhỏ đơn liên tiếp nhằm lách luật tự duyệt 2 ngày của AI (`FLAG_ABUSE_PATTERN`, Điều 1.5). |

---

### 3. TẦNG 3: THẨM ĐỊNH CHỨNG TỪ BẰNG THỊ GIÁC MÁY TÍNH (VLM & OCR INSPECTION)
*Các thông số do mô hình Vision-Language (Qwen 2.5 VL) quét, bóc tách và đối soát tự động từ hình ảnh chứng từ đính kèm.*

| STT | Tên đặc trưng (Field) | Kiểu dữ liệu | Giá trị mẫu | Ý nghĩa kiểm tra thực tế & Căn cứ quy chế |
| :---: | :--- | :---: | :--- | :--- |
| 22 | `has_attachment` | `Boolean` | `True` | Có đính kèm tệp chứng từ hay không. Nếu nghỉ ốm $\ge 2$ ngày hoặc nghỉ việc riêng hưởng lương mà thiếu $\rightarrow$ Báo lỗi `PROOF_MISSING` (Điều 7.1.d). |
| 23 | `proof_id` / `file_path` | `String` | `"proof_20260921_001.png"` | Đường dẫn lưu trữ tệp chứng từ trên server. |
| 24 | `proof_type` | `Enum` | `"MEDICAL_LEAVE_CERTIFICATE"` | Loại giấy tờ được AI nhận diện: `MEDICAL_LEAVE_CERTIFICATE` (Giấy chứng nhận nghỉ việc hưởng BHXH Mẫu 07), `HOSPITAL_DISCHARGE` (Giấy ra viện), `PRESCRIPTION` (Toa thuốc/Phiếu khám bệnh), `MARRIAGE_CERTIFICATE`, `WEDDING_INVITATION`, `DEATH_CERTIFICATE`, `BIRTH_CERTIFICATE`. |
| 25 | `document_readability` | `Enum` | `"READABLE"` | Độ rõ nét: `READABLE` (Rõ nét đọc tốt), `PARTIAL` (Mờ một phần), `ILLEGIBLE` (Mờ, tối, mất góc, không đọc được $\rightarrow$ Kích hoạt `NEED_CORRECTION` gửi trả nhân viên). |
| 26 | `doc_patient_name` | `String` | `"Nguyễn Văn An"` | Họ tên bệnh nhân/đối tượng ghi trên chứng từ. Nếu không khớp với `employee_name` $\rightarrow$ Kích hoạt cờ `NAME_MISMATCH`. |
| 27 | `doc_issuer` | `String` | `"Bệnh viện Đa khoa Quốc tế"` | Cơ sở y tế hoặc cơ quan có thẩm quyền ban hành chứng từ. |
| 28 | `doc_diagnosis` | `String` | `"Viêm phế quản cấp (J20)"` | Chẩn đoán bệnh lý của bác sĩ. |
| 29 | `days_granted_by_doctor`| `Integer`| `2` | Số ngày bác sĩ chỉ định nghỉ việc trên giấy tờ. Nếu nhân viên xin 4 ngày mà giấy chỉ cho 2 ngày $\rightarrow$ Báo lỗi `MEDICAL_DAYS_MISMATCH` (Điều 7.1.e). |
| 30 | `recommended_from_date` | `Date` | `"2026-09-22"` | Ngày bắt đầu khoảng chỉ định nghỉ trên giấy tờ y tế. |
| 31 | `recommended_to_date` | `Date` | `"2026-09-23"` | Ngày kết thúc khoảng chỉ định nghỉ trên giấy tờ y tế. |
| 32 | `has_red_stamp` | `Boolean` | `True` | Có dấu mộc đỏ pháp lý hợp lệ của cơ sở khám chữa bệnh/cơ quan hành chính hay không. |
| 33 | `has_doctor_signature` | `Boolean` | `True` | Có chữ ký của bác sĩ điều trị/người có thẩm quyền hay không. |
| 34 | `is_tampered` / `ai_edited`| `Boolean`| `False` | Dấu hiệu bị chỉnh sửa số liệu bằng Photoshop, cắt dán hoặc AI tạo sinh giả mạo (`DOC_SUSPICIOUS`). |
| 35 | `correlation_score` | `Float` | `0.98` | Điểm tin cậy đối chiếu tổng hợp giữa hồ sơ đơn và nội dung chứng từ (thang điểm từ 0.0 đến 1.0). |
| 36 | `correlation_issues` | `List[String]`| `[]` | Danh sách các điểm bất thường phát hiện (ví dụ: `["NAME_MISMATCH", "DAYS_MISMATCH"]`). |

---

### 4. TẦNG 4: ĐÁNH GIÁ QUY CHẾ, ĐIỀU PHỐI & VẾT DUYỆT (RULE ENGINE & AUDIT)
*Dữ liệu do Rule Engine tính toán ra, hiển thị cho Quản lý trong Hàng đợi duyệt và lưu nhật ký giải trình.*

| STT | Tên đặc trưng (Field) | Kiểu dữ liệu | Giá trị mẫu | Ý nghĩa vận hành & Tương tác giao diện |
| :---: | :--- | :---: | :--- | :--- |
| 37 | `requested_calendar_days`| `Integer`| `2` | Tổng số ngày lịch theo khoảng ngày chọn. |
| 38 | `requested_working_days`| `Integer`| `2` | **Số ngày làm việc thực tế** xin nghỉ (sau khi Calendar Engine đã loại bỏ Thứ Bảy, Chủ Nhật và các ngày Lễ Tết theo Điều 112 BLLĐ). |
| 39 | `working_dates` | `List[String]`| `["2026-09-22", "2026-09-23"]` | Danh sách cụ thể các ngày làm việc xin nghỉ. |
| 40 | `paid` | `Boolean` | `False` | Chế độ lương: `True` (Công ty trả lương), `False` (BHXH trả trợ cấp hoặc nghỉ không lương). |
| 41 | `payer` | `String` | `"Quỹ BHXH"` | Đơn vị chi trả: `"Doanh nghiệp"`, `"Quỹ BHXH"`, hoặc `"—"` (không lương). |
| 42 | `decision` | `Enum` | `"ESCALATE"` | Phân loại quyết định của hệ thống: `AUTO_APPROVE` (Tự duyệt), `AUTO_REJECT` (Từ chối tự động), `NEED_CORRECTION` (Yêu cầu nhân viên bổ sung/sửa), `ESCALATE` (Chuyển con người duyệt), `NO_LEAVE_REQUIRED` (Rơi hoàn toàn vào ngày Lễ/Cuối tuần). |
| 43 | `uncertainty_category` | `Enum` | `"AUTHORITY_ESCALATION"` | Nhóm mức độ không chắc chắn: `UNCERTAIN_FACTS` (Dữ liệu chưa rõ ràng/lỗi), `OUT_OF_POLICY` (Vi phạm quy chế/nộp gấp/vượt quota), `AUTHORITY_ESCALATION` (Vượt trần tự duyệt của AI). |
| 44 | `error_code` | `Enum` | `"DURATION_OVER_AI_LIMIT"` | Mã lỗi quy chuẩn của hệ thống (xem Bảng 18 mã lỗi ở Mục III). |
| 45 | `target_role` | `Enum` | `"DIRECT_MANAGER"` | Cấp thẩm quyền xử lý đích: `EMPLOYEE`, `DIRECT_MANAGER` (Trưởng phòng), `DEPARTMENT_HEAD`, `HR` (Chuyên viên Nhân sự), `HRD` (Giám đốc Nhân sự), `CEO` (Tổng Giám đốc). |
| 46 | `applied_policy_clauses`| `List[String]`| `["Điều 2.2.b", "Điều 6.2.b"]` | Danh sách các điều khoản quy chế được viện dẫn làm căn cứ. |
| 47 | `actionable_question` | `String` | `"Quản lý Đỗ Hoàng Long xem xét phê duyệt đơn xin nghỉ ốm 3 ngày của Nguyễn Văn An."` | Câu hỏi hành động thông minh do Qwen 2.5 sinh ra, hướng dẫn Quản lý đưa ra quyết định chính xác. |
| 48 | `quick_action_options` | `List[String]`| `["APPROVE", "REJECT", "REQUEST_MORE_INFO"]` | Danh sách các nút bấm thao tác nhanh hiển thị trên UI Manager. |
| 49 | `human_readable_explanation`| `String`| `"Đơn nghỉ ốm 3 ngày có chứng từ hợp lệ, thời lượng từ 2-5 ngày thuộc thẩm quyền Quản lý trực tiếp."` | Lời giải thích minh bạch cho nhân viên và quản lý nắm bắt. |
| 50 | `status` | `Enum` | `"PENDING_ESCALATION"` | Trạng thái vòng đời của đơn: `PENDING_ESCALATION`, `COMPLETED`, `REJECTED`, `NEED_CORRECTION`, `CANCELLED`. |
| 51 | `deducted_days` | `Float` | `0.0` (chờ) $\rightarrow$ `2.0` | Số ngày thực tế bị trừ vào quỹ phép năm sau khi có quyết định cuối cùng. |
| 52 | `annual_balance_change`| `Float` | `-2.0` | Biến động số dư phép năm (ví dụ: trừ 2 ngày thì giá trị là `-2.0`). |
| 53 | `human_resolution` | `Enum` | `"APPROVE_OVERRIDE"` | Quyết định can thiệp của người duyệt: `APPROVE_OVERRIDE` (Duyệt đặc cách), `REJECT` (Từ chối), `REQUEST_MORE_INFO` (Yêu cầu giải trình thêm). |
| 54 | `reviewer_id` | `String` | `"EMP015"` | Mã nhân sự của người trực tiếp bấm duyệt đơn. |
| 55 | `feedback_notes` | `String` | `"Đồng ý cho nghỉ vì công việc đã được bàn giao đầy đủ."` | Ý kiến nhận xét, ghi chú của Quản lý khi duyệt/từ chối đơn. |

---

## 📑 III. BẢNG DANH MỤC 18 MÃ LỖI QUY CHUẨN (ERROR CODES)

Mỗi Sample khi rơi vào trạng thái ngoại lệ sẽ mang một `error_code` chuẩn xác theo bộ phân loại (Taxonomy):

| STT | Mã lỗi (`error_code`) | Nhóm bất định (`uncertainty_category`) | Cấp xử lý (`target_role`) | Mô tả vi phạm theo Quy chế |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `DATE_RANGE_INVALID` | `UNCERTAIN_FACTS` | `EMPLOYEE` | Ngày kết thúc trước ngày bắt đầu (`from_date > to_date`) hoặc số ngày làm việc tính ra $\le 0$. |
| 2 | `DATE_MISSING` / `DATE_AMBIGUOUS`| `UNCERTAIN_FACTS` | `EMPLOYEE` | Đơn thiếu ngày cụ thể hoặc câu chữ mơ hồ (*"cho em nghỉ vài hôm"*). |
| 3 | `PROOF_MISSING` | `UNCERTAIN_FACTS` | `EMPLOYEE` | Nghỉ ốm $\ge 2$ ngày hoặc nghỉ việc riêng có lương nhưng không nộp giấy tờ đính kèm. |
| 4 | `DOC_ILLEGIBLE` | `UNCERTAIN_FACTS` | `EMPLOYEE` | Ảnh chụp chứng từ y tế bị mờ, mất góc, không đọc được chữ, thiếu con dấu hoặc chữ ký. |
| 5 | `NAME_MISMATCH` | `UNCERTAIN_FACTS` | `HR` / `DIRECT_MANAGER` | Tên người bệnh trên giấy khám không khớp với tên nhân sự làm đơn. |
| 6 | `MEDICAL_DAYS_MISMATCH` | `UNCERTAIN_FACTS` | `EMPLOYEE` / `DIRECT_MANAGER` | Số ngày xin nghỉ ốm nhiều hơn số ngày bác sĩ chỉ định trên Giấy nghỉ việc hưởng BHXH. |
| 7 | `DOC_SUSPICIOUS` | `UNCERTAIN_FACTS` | `HR` | Chứng từ có dấu hiệu photoshop tẩy xóa, chỉnh sửa ngày tháng, hoặc làm giả bằng AI. |
| 8 | `HANDOVER_INVALID` | `UNCERTAIN_FACTS` | `EMPLOYEE` | Người nhận bàn giao không cùng phòng ban, đã nghỉ việc, trùng lịch nghỉ hoặc trùng chính mình. |
| 9 | `BALANCE_EXCEEDED` | `OUT_OF_POLICY` | `EMPLOYEE` | Số ngày xin nghỉ phép năm vượt quá số dư phép hiện có $\rightarrow$ Tự động từ chối. |
| 10 | `NOTICE_PERIOD_VIOLATED` | `OUT_OF_POLICY` | `DIRECT_MANAGER` | Nộp đơn gấp vi phạm thời hạn báo trước (dưới 24h với đơn $\le 2$ ngày, sau 08:30 sáng với đơn ốm). |
| 11 | `TEAM_QUOTA_EXCEEDED` | `OUT_OF_POLICY` | `DIRECT_MANAGER` | Tỷ lệ vắng mặt phòng ban vượt quá 30% định biên nhân sự. |
| 12 | `FLAG_ABUSE_PATTERN` | `OUT_OF_POLICY` | `DIRECT_MANAGER` | Nộp nhiều đơn nghỉ rời rạc trong cùng 1 tháng dương lịch để lách trần tự duyệt của AI. |
| 13 | `UNQUALIFIED_SPECIAL_LEAVE`| `OUT_OF_POLICY` | `EMPLOYEE` | Xin nghỉ việc riêng có lương nhưng lý do không thuộc quy định tại Điều 115 BLLĐ. |
| 14 | `DURATION_OVER_AI_LIMIT` | `AUTHORITY_ESCALATION` | `DIRECT_MANAGER` | Đơn hợp lệ nhưng thời lượng từ 3 đến 5 ngày làm việc (vượt trần tự duyệt 2 ngày của AI). |
| 15 | `DURATION_OVER_MANAGER_LIMIT`| `AUTHORITY_ESCALATION` | `HRD` | Nghỉ phép năm liên tiếp trên 5 ngày làm việc $\rightarrow$ Vượt thẩm quyền Quản lý trực tiếp. |
| 16 | `LONG_TERM_UNPAID` | `AUTHORITY_ESCALATION` | `HRD` / `CEO` | Nghỉ việc riêng không hưởng lương dài hạn trên 5 ngày hoặc trên 14 ngày. |
| 17 | `MANAGER_SELF_APPROVAL` | `AUTHORITY_ESCALATION` | `CEO` | Quản lý trực tiếp tự làm đơn xin nghỉ cho chính mình $\rightarrow$ Phải chuyển cấp trên phê duyệt. |
| 18 | `AUTOMATION_SCOPE_UNSUPPORTED`| `AUTHORITY_ESCALATION` | `HR` / `HRD` | Các chế độ phức tạp vượt phạm vi tự động (nghỉ thai sản dài hạn, tai nạn lao động). |

---

## 🎯 IV. MA TRẬN 18 KỊCH BẢN MẪU (TEST CASE SCENARIO MATRIX)

Để bộ dữ liệu mẫu (Database Seed Data) phản ánh được **100% các tình huống thực tế**, một bộ database cần tối thiểu 18 mẫu tương ứng với 4 nhóm kịch bản:

```
┌────────────────────────────────────────────────────────────────────────┐
│ MA TRẬN 18 KỊCH BẢN PHỦ KÍN TOÀN BỘ NGHIỆP VỤ                          │
├───────────────────┬───────────────────┬────────────────────────────────┤
│ NHÓM 1: AUTO (3)  │ NHÓM 2: REJECT (3)│ NHÓM 3: CORRECTION (5)         │
│ • Phép năm 1-2d   │ • Hết quỹ phép    │ • Thiếu chứng từ               │
│ • Nghỉ ốm 1d toa  │ • Sai loại đơn    │ • Ảnh chứng từ bị mờ           │
│ • Trùng ngày lễ   │ • Việc riêng sai  │ • Nghịch lý ngày tháng         │
│                   │                   │ • Người bàn giao không hợp lệ  │
│                   │                   │ • Xin nhiều ngày hơn y lệnh    │
├───────────────────┴───────────────────┴────────────────────────────────┤
│ NHÓM 4: ESCALATE - CHUYỂN TIẾP CHO CON NGƯỜI (7)                       │
│ • Nộp gấp phạm hạn báo trước          • Phép năm 3-5 ngày              │
│ • Vượt hạn mức vắng mặt phòng 30%     • Phép năm dài hạn > 5 ngày      │
│ • Lách luật chia nhỏ đơn trong tháng  • Việc riêng có lương kết hôn    │
│ • Quản lý tự làm đơn nghỉ cho mình                                     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 💻 V. CẤU TRÚC JSON MẪU CỦA 1 SAMPLE CHUẨN (CANONICAL RECORD SPECIFICATION)

Dưới đây là một bản ghi mẫu chuẩn (Sample Record) định dạng JSON chứa đủ 100% các trường dữ liệu ở trên, sẵn sàng để nạp vào Database hoặc dùng làm bộ Test Harness:

```json
{
  "id": "REQ-2026-015-AN",
  "employee": {
    "employee_id": "EMP012",
    "name": "Nguyễn Văn An",
    "email": "an.nguyen@company.com",
    "department": "Engineering",
    "role": "Software Engineer",
    "manager_id": "EMP015",
    "remaining_leave_days": 8.0,
    "hire_date": "2023-08-15",
    "status": "ACTIVE",
    "total_team_members": 8,
    "concurrent_absences": 1
  },
  "request": {
    "leave_type": "SICK_MEDICAL",
    "reason_category": "PERSONAL",
    "reason": "Điều trị sốt xuất huyết Dengue theo chỉ định y khoa của Bệnh viện.",
    "from_date": "2026-09-22",
    "to_date": "2026-09-24",
    "submitted_at": "2026-09-21T07:15:00+07:00",
    "handover_person_id": "EMP015",
    "handover_person_name": "Đỗ Hoàng Long",
    "monthly_accumulated_days": 0.0
  },
  "proof_verification": {
    "has_attachment": true,
    "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
    "document_readability": "READABLE",
    "doc_patient_name": "Nguyễn Văn An",
    "doc_issuer": "Bệnh viện Đa khoa Quốc tế Vinmec",
    "doc_diagnosis": "Sốt xuất huyết Dengue có dấu hiệu cảnh báo (Mã ICD: A91)",
    "days_granted_by_doctor": 3,
    "recommended_from_date": "2026-09-22",
    "recommended_to_date": "2026-09-24",
    "has_red_stamp": true,
    "has_doctor_signature": true,
    "is_tampered": false,
    "correlation_score": 0.99,
    "correlation_issues": []
  },
  "engine_evaluation": {
    "requested_calendar_days": 3,
    "requested_working_days": 3,
    "working_dates": ["2026-09-22", "2026-09-23", "2026-09-24"],
    "paid": false,
    "payer": "Quỹ BHXH",
    "decision": "ESCALATE",
    "uncertainty_category": "AUTHORITY_ESCALATION",
    "error_code": "DURATION_OVER_AI_LIMIT",
    "target_role": "DIRECT_MANAGER",
    "applied_policy_clauses": ["Điều 2.2.b", "Điều 6.2.b"],
    "human_readable_explanation": "Đơn nghỉ ốm 3 ngày có Giấy chứng nhận BHXH hợp lệ. Thời lượng từ 2 đến 5 ngày thuộc thẩm quyền Quản lý trực tiếp phê duyệt.",
    "actionable_question": "Quản lý Đỗ Hoàng Long xác nhận phê duyệt đơn nghỉ ốm 3 ngày hưởng trợ cấp BHXH cho nhân sự Nguyễn Văn An.",
    "quick_action_options": ["APPROVE", "REJECT", "REQUEST_MORE_INFO"]
  },
  "audit_and_resolution": {
    "status": "PENDING_ESCALATION",
    "human_resolution": null,
    "reviewer_id": null,
    "feedback_notes": null,
    "deducted_days": 0.0,
    "annual_balance_change": 0.0,
    "submitted_at": "2026-09-21T07:15:00+07:00",
    "updated_at": "2026-09-21T07:15:05+07:00"
  }
}
```

---

## 🛠️ VI. THIẾT KẾ DATABASE SQLITE HOÀN CHỈNH (`leave_app_v2.db`)

Dưới đây là thiết kế chi tiết toàn bộ mã **SQL DDL** để tạo cơ sở dữ liệu mới, lưu trữ trọn vẹn 55+ đặc trưng của 1 sample, hỗ trợ đầy đủ khóa ngoại (`FOREIGN KEY`) và chỉ mục tối ưu truy vấn:

```sql
-- ============================================================================
-- 1. BẢNG NHÂN SỰ & TỔ CHỨC (employees)
-- ============================================================================
CREATE TABLE IF NOT EXISTS employees (
    employee_id             TEXT PRIMARY KEY,              -- Mã nhân viên (EMP012)
    name                    TEXT NOT NULL,                 -- Họ và tên đầy đủ
    email                   TEXT UNIQUE,                   -- Email doanh nghiệp
    department              TEXT NOT NULL,                 -- Phòng ban (Engineering, HR,...)
    role                    TEXT NOT NULL,                 -- Chức danh công việc
    manager_id              TEXT,                          -- Quản lý trực tiếp (FK tự tham chiếu)
    remaining_leave_days    REAL NOT NULL DEFAULT 12.0,    -- Số dư phép năm hiện có
    hire_date               TEXT NOT NULL,                 -- Ngày vào làm việc (YYYY-MM-DD)
    status                  TEXT NOT NULL DEFAULT 'ACTIVE',-- Trạng thái: ACTIVE, PROBATION, SUSPENDED
    created_at              TEXT NOT NULL DEFAULT (datetime('now', '+7 hours')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now', '+7 hours')),
    FOREIGN KEY (manager_id) REFERENCES employees(employee_id) ON DELETE SET NULL
);

-- Chỉ mục phòng ban để tính nhanh quân số & quota 30%
CREATE INDEX IF NOT EXISTS idx_employees_dept ON employees(department);
CREATE INDEX IF NOT EXISTS idx_employees_manager ON employees(manager_id);


-- ============================================================================
-- 2. BẢNG ĐƠN NGHỈ PHÉP & ĐIỀU PHỐI (leave_requests)
-- ============================================================================
CREATE TABLE IF NOT EXISTS leave_requests (
    -- Định danh & Nhân sự
    id                          TEXT PRIMARY KEY,          -- Mã đơn (REQ-2026-001-AN)
    employee_id                 TEXT NOT NULL,             -- Mã nhân viên làm đơn
    employee_name               TEXT NOT NULL,             -- Tên nhân viên
    department                  TEXT NOT NULL,             -- Phòng ban tại thời điểm nộp
    
    -- Thông tin đơn nộp (Request Facts)
    leave_type                  TEXT NOT NULL,             -- ANNUAL, SICK_MEDICAL, SPECIAL_PAID,...
    reason_category             TEXT NOT NULL,             -- PERSONAL, SELF_MARRIAGE, PARENT_DEATH,...
    reason                      TEXT,                      -- Lý do chi tiết
    from_date                   TEXT NOT NULL,             -- Ngày bắt đầu (YYYY-MM-DD)
    to_date                     TEXT NOT NULL,             -- Ngày kết thúc (YYYY-MM-DD)
    submitted_at                TEXT NOT NULL,             -- Giờ bấm nộp (ISO 8601 có timezone)
    
    -- Bàn giao công việc (Handover - Bắt buộc nếu >= 3 ngày)
    handover_person_id          TEXT,                      -- Mã nhân sự nhận bàn giao
    handover_person_name        TEXT,                      -- Tên người nhận bàn giao
    handover_valid              INTEGER DEFAULT 1,         -- 1 = hợp lệ, 0 = vi phạm
    
    -- Kết quả tính toán lịch & Quy chế (Engine Evaluation)
    requested_calendar_days     INTEGER NOT NULL DEFAULT 0,-- Tổng số ngày lịch
    requested_working_days      INTEGER NOT NULL DEFAULT 0,-- Số ngày làm việc thực tế
    working_dates_json          TEXT NOT NULL DEFAULT '[]',-- JSON danh sách ngày làm việc
    paid                        INTEGER NOT NULL DEFAULT 1,-- 1 = Có lương, 0 = Không lương/BHXH
    payer                       TEXT DEFAULT 'Doanh nghiệp',-- Doanh nghiệp, Quỹ BHXH, hoặc '—'
    
    -- Quyết định & Phân loại chuyển tiếp (Taxonomy Decision)
    decision                    TEXT NOT NULL,             -- AUTO_APPROVE, ESCALATE, AUTO_REJECT, NEED_CORRECTION, NO_LEAVE_REQUIRED
    uncertainty_category        TEXT,                      -- UNCERTAIN_FACTS, OUT_OF_POLICY, AUTHORITY_ESCALATION
    error_code                  TEXT,                      -- DURATION_OVER_AI_LIMIT, BALANCE_EXCEEDED,...
    target_role                 TEXT,                      -- DIRECT_MANAGER, HR, HRD, CEO
    applied_policy_clauses      TEXT DEFAULT '[]',         -- JSON danh sách điều khoản quy chế
    
    -- Trí tuệ nhân tạo giải trình (LLM Reasoning & Guidance)
    human_readable_explanation  TEXT,                      -- Giải thích minh bạch cho con người
    actionable_question         TEXT,                      -- Câu hỏi gợi mở hành động cho Quản lý
    quick_action_options        TEXT DEFAULT '[]',         -- JSON các nút bấm nhanh: ["APPROVE", "REJECT",...]
    
    -- Chứng từ liên kết
    proof_id                    TEXT,                      -- ID chứng từ trong proof_documents
    has_attachment              INTEGER DEFAULT 0,         -- 1 = có file, 0 = không có
    
    -- Trạng thái vòng đời & Phê duyệt của con người (Human Resolution)
    status                      TEXT NOT NULL DEFAULT 'PENDING_ESCALATION', -- PENDING_ESCALATION, COMPLETED, REJECTED, NEED_CORRECTION
    human_resolution            TEXT,                      -- APPROVE_OVERRIDE, REJECT, REQUEST_MORE_INFO
    reviewer_id                 TEXT,                      -- Người thực hiện duyệt
    reviewer_name               TEXT,                      -- Tên người duyệt
    feedback_notes              TEXT,                      -- Ý kiến chỉ đạo của người duyệt
    override_reason             TEXT,                      -- Lý do duyệt ngoại lệ
    
    -- Cấn trừ số dư phép sau khi duyệt
    deducted_days               REAL DEFAULT 0.0,          -- Số ngày thực tế bị trừ
    annual_balance_change       REAL DEFAULT 0.0,          -- Biến động số dư phép (-X.X)
    
    -- Metadata hệ thống
    policy_version              TEXT DEFAULT '3.0.0',      -- Phiên bản quy chế áp dụng
    created_at                  TEXT NOT NULL DEFAULT (datetime('now', '+7 hours')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now', '+7 hours')),
    
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id) ON DELETE CASCADE,
    FOREIGN KEY (handover_person_id) REFERENCES employees(employee_id) ON DELETE SET NULL,
    FOREIGN KEY (reviewer_id) REFERENCES employees(employee_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_emp ON leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON leave_requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_dates ON leave_requests(from_date, to_date);


-- ============================================================================
-- 3. BẢNG THẨM ĐỊNH CHỨNG TỪ QUA THỊ GIÁC MÁY TÍNH (proof_documents)
-- ============================================================================
CREATE TABLE IF NOT EXISTS proof_documents (
    id                          TEXT PRIMARY KEY,          -- Mã chứng từ (PRF-2026-001)
    request_id                  TEXT,                      -- Mã đơn liên kết
    file_name                   TEXT NOT NULL,             -- Tên tệp gốc
    file_path                   TEXT NOT NULL,             -- Đường dẫn lưu trên server
    mime_type                   TEXT NOT NULL,             -- image/png, image/jpeg, application/pdf
    file_size_bytes             INTEGER NOT NULL,          -- Dung lượng file
    uploaded_at                 TEXT NOT NULL,             -- Thời điểm tải lên
    
    -- Bóc tách dữ liệu từ VLM (Vision-Language Model)
    proof_type                  TEXT NOT NULL,             -- MEDICAL_LEAVE_CERTIFICATE, HOSPITAL_DISCHARGE,...
    document_readability        TEXT NOT NULL,             -- READABLE, PARTIAL, ILLEGIBLE
    doc_patient_name            TEXT,                      -- Tên ghi trên chứng từ
    doc_issuer                  TEXT,                      -- Đơn vị/Bệnh viện cấp
    doc_diagnosis               TEXT,                      -- Chẩn đoán y khoa
    days_granted_by_doctor      INTEGER,                   -- Số ngày bác sĩ chỉ định nghỉ
    recommended_from_date       TEXT,                      -- Ngày bắt đầu chỉ định
    recommended_to_date         TEXT,                      -- Ngày kết thúc chỉ định
    
    -- Kiểm định tính pháp lý & Toàn vẹn
    has_red_stamp               INTEGER DEFAULT 0,         -- 1 = Có mộc đỏ hợp lệ, 0 = Không có
    has_doctor_signature        INTEGER DEFAULT 0,         -- 1 = Có chữ ký bác sĩ, 0 = Không có
    is_tampered                 INTEGER DEFAULT 0,         -- 1 = Phát hiện photoshop/AI, 0 = Thật
    ai_edited                   INTEGER DEFAULT 0,         -- 1 = Dấu vết can thiệp AI tạo sinh
    correlation_score           REAL DEFAULT 1.0,          -- Điểm tương quan khớp (0.0 -> 1.0)
    correlation_issues          TEXT DEFAULT '[]',         -- JSON danh sách lỗi lệch thông tin
    
    -- Kết quả xác minh
    verification_status         TEXT DEFAULT 'UNVERIFIED', -- VERIFIED, NEEDS_HR_REVIEW, REJECTED
    raw_vlm_json                TEXT,                      -- JSON gốc phản hồi từ mô hình VLM
    
    FOREIGN KEY (request_id) REFERENCES leave_requests(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_proof_req ON proof_documents(request_id);


-- ============================================================================
-- 4. BẢNG NHẬT KÝ GIẢI TRÌNH & DẤU VẾT HỆ THỐNG (audit_logs)
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id                  TEXT NOT NULL,             -- Mã đơn liên quan
    step_name                   TEXT NOT NULL,             -- INGEST, RULE_ENGINE, VLM_SCAN, HUMAN_DECISION
    actor_id                    TEXT,                      -- SYSTEM, AI_ORCHESTRATOR, hoặc mã NV duyệt
    action                      TEXT NOT NULL,             -- SUBMITTED, AUTO_APPROVED, ESCALATED, OVERRIDDEN, REJECTED
    details                     TEXT,                      -- Nội dung ghi chú chi tiết
    decision_trace_json         TEXT,                      -- Snapshot toàn bộ cây quyết định tại thời điểm đó
    created_at                  TEXT NOT NULL DEFAULT (datetime('now', '+7 hours')),
    
    FOREIGN KEY (request_id) REFERENCES leave_requests(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_audit_req ON audit_logs(request_id);
```
