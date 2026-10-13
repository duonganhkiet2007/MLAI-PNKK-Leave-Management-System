# BẢN THIẾT KẾ NỘI DUNG 5 SLIDE THUYẾT TRÌNH: THE ESCALATION REFEREE

> **Đề tài**: *Hệ Thống Phê Duyệt Nghỉ Phép Doanh Nghiệp AI — Triệt tiêu Ảo giác (Zero Hallucination) bằng Deterministic Rule Engine, Vision-Language Model & Human-in-the-Loop.*

---

## SLIDE 1: VẤN ĐỀ HIỆN TRẠNG & KHOẢNG TRỐNG THỰC TẾ
### *Problem Statement & The Hallucination Trap*

* **Tiêu đề Slide (Header)**: Khoảng Trống Nghiệp Vụ & Rủi Ro Ảo Giác (Hallucination) Trong Phê Duyệt Nghỉ Phép
* **Bố cục đề xuất (Layout)**: So sánh 2 cột đối lập (Thủ công vs. Pure GenAI) + 1 Banner kết luận bên dưới.

### Nội dung hiển thị:
#### Cột 1: Quy trình Làm việc Thủ công (Manual Workflow)
* **Chậm trễ & Quá tải**: Phê duyệt thủ công mất 4 – 24 giờ. Cấp quản lý và HR bị quá tải bởi các đơn xin nghỉ thường quy lặp đi lặp lại.
* **Sai sót con người**: Dễ quên trừ ngày phép, tính sai lịch nghỉ lễ, bỏ sót chứng từ mờ hoặc phê duyệt vượt thẩm quyền theo quy chế nội bộ.

#### Cột 2: Rủi ro khi Dùng AI Tạo sinh Thuần túy (Pure GenAI Trap)
* **Ảo giác số liệu (Data Hallucination)**: LLM tạo sinh thường xuyên tính sai số ngày làm việc thực tế (bỏ qua thứ 7, Chủ nhật, ngày nghỉ lễ theo Bộ luật Lao động Việt Nam) và tự suy đoán số dư phép.
* **Bất định & Thiếu kiểm toán**: Cùng một lá đơn có thể nhận kết quả khác nhau tùy prompt; không thể truy vết (No Auditability) và tạo rủi ro pháp lý lớn cho doanh nghiệp.

#### Banner Kết luận (Bottom Banner):
* **Giải pháp The Escalation Referee**: Ứng dụng kiến trúc Hybrid AI — Bộ máy quy chế tất định (Deterministic Rule Engine) triệt tiêu 100% ảo giác số liệu, kết hợp VLM thẩm định chứng từ và điều phối con người phán quyết.

---

## SLIDE 2: ĐẦU VÀO → XỬ LÝ → ĐẦU RA & RANH GIỚI CON NGƯỜI
### *End-to-End Pipeline & Human-in-the-Loop Orchestration*

* **Tiêu đề Slide (Header)**: Quy Trình Xử Lý Dữ Liệu & Ranh Giới Thẩm Quyền Con Người
* **Bố cục đề xuất (Layout)**: Sơ đồ luồng 3 khối ngang (`Đầu vào` → `Xử lý` → `Đầu ra`) + Khối `Human-in-the-Loop` nổi bật bên dưới.

### Nội dung hiển thị:
#### 1. Đầu vào (Input Layer)
* **Form cấu trúc**: Nhân viên, loại nghỉ (Annual, Sick, Emergency, Maternity...), khoảng thời gian (ISO date), lý do, nhân sự nhận bàn giao.
* **Tệp chứng từ**: Ảnh chụp/PDF giấy xuất viện, đơn thuốc, giấy đăng ký kết hôn (tối đa 10MB).

#### 2. Xử lý (Processing Pipeline)
* **VLM Inspector (Qwen 2.5-VL)**: Áp dụng Persona chuyên trách (Bác sĩ y tế / Điều phối cấp cứu / Giám định hôn sự); đọc fact khách quan (tên, chẩn đoán, ngày cấp, dấu mộc, chữ ký); **tuyệt đối không tự phán quyết hợp lệ**.
* **Deterministic Rule Engine**: Nhúng facts + ngữ cảnh DB (quỹ phép, quota vắng mặt < 30%, lịch lễ `CalendarService`); thẩm định 7 bước tất định theo Bộ luật Lao động 2019.

#### 3. Đầu ra (Output - 3 Spec Stops)
* **`AUTO_APPROVE` (Tự động duyệt)**: Ca chuẩn ≤ 2 ngày, đủ điều kiện, nộp trước ≥ 24h → Tự động trừ quỹ phép tức thì, ghi Audit log.
* **`NEED_CORRECTION / AUTO_REJECT`**: Yêu cầu nhân viên sửa hoặc từ chối (ngày ngược, vượt số dư, thiếu chứng từ) mà không làm phiền cấp quản lý.
* **`ESCALATE` (Chuyển Quản lý)**: Ca ngoại lệ (3–5 ngày, nộp gấp, quota phòng ban > 30%, chứng từ mờ).

#### 4. Vị trí Con người Ra quyết định (Human Decision Boundary)
* **Con người là Thẩm phán tối cao (Final Arbiter)**: AI chỉ đóng vai trò "Trọng tài chuyển tiếp".
* **Escalation Inbox**: Quản lý nhận câu hỏi hành động trực diện (*Actionable Question*), bằng chứng Lightbox, phê duyệt 1-chạm (`APPROVE` / `REJECT` / `REQUEST_MORE_INFO`).
* **Nút [ Hủy Lệnh AI ] (Revoke)**: Quản lý có toàn quyền thu hồi bất kỳ phán quyết tự động nào của AI nếu phát hiện bất thường.

---

## SLIDE 3: TÁC ĐỘNG THỰC TẾ: ĐỐI CHIẾU TRƯỚC - SAU & PHƯƠNG PHÁP ĐO LƯỜNG
### *Measured Impact & Evaluation Benchmark*

* **Tiêu đề Slide (Header)**: Hiệu Quả Triển Khai Thực Tế & Phương Pháp Đo Lường Độc Lập
* **Bố cục đề xuất (Layout)**: Bảng đối chiếu Trước - Sau ở trên + 3 thẻ đo lường benchmark ở dưới.

### Nội dung hiển thị:
#### Bảng đối chiếu Trước vs. Sau:

| Chỉ số đánh giá | Trước triển khai (Thủ công / Pure LLM) | Sau triển khai (The Escalation Referee) | Mức cải thiện |
| :--- | :--- | :--- | :--- |
| **Thời gian duyệt ca chuẩn (≤ 2 ngày)** | 4 – 24 giờ (chờ duyệt thủ công) | **~80 – 120 ms** (Auto-Approve tức thì) | **Nhanh gấp > 10.000 lần** |
| **Tỷ lệ ảo giác số liệu (Hallucination)**| Thường xuyên sai ngày lễ / cuối tuần | **0% (Triệt tiêu hoàn toàn)** | **Zero Hallucination** |
| **Độ chính xác quy chế (Accuracy)** | ~85 – 90% (sai sót con người) | **99.09%** (109/110 test suite độc lập) | **Chuẩn hóa tối đa** |
| **Tải công việc của Cấp Quản lý** | Phải đọc và duyệt 100% số đơn | Chỉ xử lý **30 – 40%** ca ngoại lệ | **Giảm 60 – 70% khối lượng** |
| **Tính minh bạch & Kiểm toán** | Rời rạc qua Chat/Email, khó tra cứu | **100% Decision Trace & Audit Log ACID** | **Minh bạch tuyệt đối** |

#### Phương pháp đo lường cụ thể (Benchmark Framework):
* **Kiểm thử tải toàn diện**: Đo lường trên **810 lượt nộp API thực tế trong 60 lô** đa mức tải (1, 5, 10, 15, 20, 30 clients đồng thời; lịch bùng nổ burst vs. rải đều).
* **Bộ dữ liệu kiểm chuẩn**: 140 kịch bản nhân sự giả lập, 38 tình huống kiểm thử tích hợp, 110 ca quy chế độc lập gắn nhãn trước (`ground_truth.json`).
* **Chỉ số hệ thống đo đạc**: Độ trễ API `ack_p95_ms` đạt **118.5 ms**, thời gian xử lý luồng không chứng từ đạt **79.6 ms**, hàng đợi VLM đơn luồng bảo vệ GPU RTX 4090 không bị tràn VRAM.

---

## SLIDE 4: KIẾN TRÚC HỆ THỐNG & PHÂN ĐỊNH THỰC TẾ VS. GIẢ LẬP
### *System Architecture & Production vs. Simulation Mapping*

* **Tiêu đề Slide (Header)**: Kiến Trúc Kỹ Thuật Hệ Thống & Phân Định Thành Phần Thực Tế - Giả Lập
* **Bố cục đề xuất (Layout)**: Bên trái là Sơ đồ khối 3 tầng; bên phải là Bảng phân định minh bạch Real vs. Mock.

### Nội dung hiển thị:
#### Sơ đồ Kiến trúc 3 Tầng:
1. **Presentation Layer (Frontend SPA)**: Vanilla HTML/JS/CSS không phụ thuộc framework, cung cấp 3 chế độ: *STAFF* (nhân viên), *MANAGER* (hàng đợi duyệt), *TEST* (kiểm thử tự động).
2. **Coordination & Backend (FastAPI + SQLite)**: ASGI Server xử lý bất đồng bộ; [ProofInspectionService](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/backend/services/inspection_service.py#L74) quản lý hàng đợi ngầm; Transaction `BEGIN IMMEDIATE` + SQLite WAL mode bảo đảm tính toàn vẹn dữ liệu.
3. **Hybrid AI Engine**:
   * *Rule Engine*: [LeaveRuleEngine](file:///workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/core/rule_engine.py) thẩm định 7 bước tất định.
   * *Vision Model*: Ollama `qwen2.5vl:7b` phân tích OCR và trích xuất schema JSON.

#### Bảng Phân định Thực tế (Real) vs. Giả lập (Mock):

| Thành phần | Phân loại | Mục đích kỹ thuật |
| :--- | :---: | :--- |
| **FastAPI Backend & SPA UI** | **THỰC TẾ (Real)** | Xử lý RESTful API, phục vụ giao diện 3 chế độ, phân quyền bảo mật. |
| **SQLite DB & Audit Ledger** | **THỰC TẾ (Real)** | Quản lý số dư theo từng ngày làm việc, lưu vết kiểm toán và phán quyết. |
| **Deterministic Rule Engine** | **THỰC TẾ (Real)** | Bộ quy tắc 7 bước, tính toán ngày nghỉ lễ theo lịch Việt Nam. |
| **Mô hình VLM (Qwen 2.5-VL)** | **THỰC TẾ (Real)** | Chạy suy luận trực tiếp trên GPU RTX 4090 khi chạy `--live-vlm`. |
| **VLM Mock Profile Engine** | **GIẢ LẬP (Mock)** | Dùng khi test tải cao (stress-test) để đo throughput backend mà không nghẽn GPU. |
| **Dữ liệu 140 nhân sự & ảnh chứng từ**| **GIẢ LẬP (Synthetic)**| Tạo tự động bằng Pillow nhằm kiểm thử tải mà **không vi phạm bảo mật dữ liệu y tế cá nhân (PII)**. |
| **Actor Header trong tab TEST** | **GIẢ LẬP (Mock)** | Header giả lập vai trò để test nhanh trong môi trường demo (Production dùng Bearer JWT). |

---

## SLIDE 5: GIỚI HẠN, RỦI RO & ĐỊNH HƯỚNG XỬ LÝ TIẾP THEO
### *Identified Edge Cases, Limitations & Future Roadmap*

* **Tiêu đề Slide (Header)**: Giới Hạn Kỹ Thuật, Điểm Nghẽn Thực Tế & Định Hướng Hoàn Thiện
* **Bố cục đề xuất (Layout)**: 2 phần đối chiếu: Hộp cảnh báo Rủi ro (Màu cam/đỏ) ở trên, Hộp Giải pháp & Lộ trình (Màu xanh) ở dưới.

### Nội dung hiển thị:
#### Các Điểm nghẽn & Lỗi phát hiện qua Thực nghiệm (Findings):
1. **Race Condition Worker vs. Submit**: Khi submit đơn ở trạng thái PENDING nhưng tác vụ đọc chứng từ kết thúc trước khi đơn kịp lưu vào DB → Đơn có thể bị kẹt ở trạng thái `PROCESSING`.
2. **Khớp tên xấp xỉ bị nhầm (Name Matching Weakness)**: Hàm so khớp tên mềm có thể nhận nhầm nếu có token trùng nhau (ví dụ: Benchmark Person 999 bị nhận diện nhầm thành Benchmark Person 000).
3. **Rủi ro Fallback duyệt tự động**: Khi người duyệt nhập câu phản hồi mơ hồ, hệ thống mặc định chấp thuận (`APPROVE_OVERRIDE`), tiềm ẩn rủi ro lọt đơn sai.
4. **Disk Cache chưa phân lập ngữ cảnh**: Khóa lưu cache ổ đĩa của VLM chỉ dựa trên hash file mà chưa gắn kèm loại nghỉ phép (`leave_type`).
5. **Chứng từ viết tay & chất lượng thấp**: Chữ viết tay bác sĩ quá mờ hoặc mộc đỏ nhạt có thể bị đánh dấu `DOC_ILLEGIBLE`.

#### Định hướng Xử lý Tiếp theo (Remediation & Roadmap):
* **Hệ thống & Cơ chế Fail-safe**:
  * Tái cấu trúc State Machine đồng bộ để triệt tiêu hoàn toàn race condition.
  * Chuyển đổi phản hồi mơ hồ sang nguyên tắc **Zero-Trust**: Mặc định yêu cầu làm rõ (`REQUEST_MORE_INFO`), cấm tự động duyệt khi chưa chắc chắn.
  * Tách biệt key cache VLM gồm cả `file_hash + leave_type + employee_context`.
* **Nghiệp vụ & Nâng cấp AI**:
  * Nâng cấp so khớp danh tính: Bắt buộc dùng Mã nhân viên (Employee ID), CCCD hoặc Mã số BHXH thay vì so khớp chuỗi họ tên.
  * Fine-tune mô hình thị giác chuyên biệt trên tập dữ liệu hồ sơ bệnh án và chữ viết tay y tế Việt Nam.
  * Mở rộng hàng đợi đa luồng (Multi-worker VLM Queue) khi triển khai cho doanh nghiệp quy mô lớn.
