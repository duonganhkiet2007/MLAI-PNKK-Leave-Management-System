# Hướng dẫn viết lại phản hồi xử lý đơn nghỉ phép

> Tài liệu này dành cho agent chỉnh sửa template trong `orchestration.py`, `rule_engine.py`, `leave_router.py`.
> Mục tiêu: phản hồi cho nhân viên rõ ràng, nhất quán, đúng người nhận, không lộ chi tiết kỹ thuật nội bộ.

---

## 1. Nguyên tắc chung

1. **Nhân viên là người đọc chính.** Viết cho người không biết gì về VLM, Rule Engine, enum. Không hiển thị `decision = ESCALATE`, `PENDING_ESCALATION`, `SIBLING_MARRIAGE`, `READABLE`, tiền tố "VLM -"...
2. **Kết luận trước, chi tiết sau.** Dòng đầu tiên trả lời: đơn đang ở trạng thái nào, và việc tiếp theo là gì.
3. **Một lý do chính + các lưu ý phụ.** Tách rõ *nguyên nhân khiến đơn bị chuyển/trả lại* với *các điểm chỉ để tham khảo*. Không để dòng "ngày cưới ngoài khoảng nghỉ" nghe như nguyên nhân duy nhất nếu thực tế là do chứng từ chưa VERIFIED.
4. **Nói rõ ai làm gì tiếp.** Người nhận (Lead Team / HR / nhân viên) phải khớp ở mọi chỗ trong cùng một phản hồi.
5. **Không đổ lỗi, không mơ hồ.** Dùng giọng trung tính, lịch sự. Tránh "hệ thống không chấp nhận", dùng "cần bổ sung/điều chỉnh".
6. **Nhất quán định dạng.** Ngày `dd/mm/yyyy`, số ngày `1 ngày` (bỏ `.0`), trạng thái chỉ dùng 3 giá trị: `Đạt` / `Cần xem xét` / `Không đạt`.
7. **Ngắn.** Phần tóm tắt tối đa 3 câu. Bảng chỉ liệt kê tiêu chí thật sự cần.

---

## 2. Các lỗi hiện tại cần sửa (rút ra từ output mẫu)

| # | Lỗi | Cách sửa |
|---|-----|----------|
| 1 | Template `PROOF_REVIEW_REQUIRED` ghi "chứng từ y tế" và "HR" dù đơn là giấy kết hôn và người nhận là Lead Team | Tách template theo loại chứng từ (`{proof_label}`) và người nhận (`{reviewer_label}`), render từ biến, không hardcode |
| 2 | Cùng một đơn xuất hiện 2 đoạn giải thích gần giống nhau (câu tóm tắt + "Lý do escalate") | Chỉ giữ 1 câu giải thích; lý do chi tiết nằm trong bảng |
| 3 | Lộ mã nội bộ: `SIBLING_MARRIAGE`, `SELF_MARRIAGE`, `READABLE`, `decision`, `Trạng thái = ...` | Map sang nhãn tiếng Việt (mục 5); ẩn trường kỹ thuật |
| 4 | Mâu thuẫn nhãn sự kiện: câu giải thích ghi `SIBLING_MARRIAGE`, bảng chi tiết ghi `SELF_MARRIAGE` | Dùng **một** biến `event_type` duy nhất cho toàn bộ phản hồi; thêm assert/test |
| 5 | "Chứng từ: Đạt" nhưng "Xác minh chứng từ: Cần xem xét" gây khó hiểu | Đổi tên: **Đọc chứng từ** (đọc được thông tin) và **Xác minh chứng từ** (đối chiếu với quy chế/người có thẩm quyền) |
| 6 | Lý do escalate in thường, cuối câu có `..`, thiếu viết hoa | Chuẩn hóa: viết hoa đầu câu, một dấu chấm, không nối chuỗi thô |
| 7 | Ngày hiển thị lẫn `2026-10-12` và `12/10/2026` | Luôn format `dd/mm/yyyy` ở lớp hiển thị |
| 8 | `Số ngày phép còn lại: 18.0 ngày (Không trừ)` khó hiểu | `Còn 18 ngày phép. Đơn này chưa trừ phép vì đang chờ duyệt.` |
| 9 | Với `CHILD_MARRIAGE`, câu "không so tên" nghe như bỏ qua kiểm tra | `Với trường hợp con kết hôn, tên người nộp đơn không nằm trên giấy nên bước đối chiếu tên được bỏ qua theo quy chế.` |
| 10 | Tiền tố "VLM -" ở tên tiêu chí | Bỏ hẳn. Nguồn dữ liệu (VLM/code) chỉ ghi trong log nội bộ, không hiển thị cho nhân viên |

---

## 3. Cấu trúc phản hồi chuẩn

```
[Tiêu đề trạng thái]  (1 dòng, có icon trạng thái)

[Tóm tắt]  (1-3 câu: chuyện gì xảy ra → vì sao → bước tiếp theo, ai xử lý)

[Việc bạn cần làm]  (chỉ hiện nếu nhân viên phải hành động; tối đa 3 gạch đầu dòng)

[Bảng kiểm tra]
| Hạng mục | Kết quả | Ghi chú |

[Thông tin đơn]  (tùy chọn, thu gọn: loại nghỉ, ngày nghỉ, số ngày)
```

### Icon trạng thái đơn
- ✅ Đã tự động duyệt
- 🔄 Đã chuyển cấp duyệt (chờ người có thẩm quyền)
- ✏️ Cần bạn chỉnh sửa/bổ sung
- ❌ Không đủ điều kiện

### Icon trong bảng
- Đạt → ✅   Cần xem xét → ⚠️   Không đạt → ❌

---

## 4. Quy tắc giọng văn

- Xưng hô: dùng "bạn" (nhân viên), "chúng tôi/hệ thống" cho bên xử lý. Không dùng "đương sự", "người nộp đơn" trong phần nhân viên đọc.
- Câu chủ động, mỗi câu một ý, dưới 25 từ.
- Không dùng thuật ngữ: escalate, VERIFIED, rule engine, decision, enum, payload.
- Nếu trích dẫn pháp lý: ghi ngắn gọn, ví dụ `(Điều 115 BLLĐ 2019)`, không chép nguyên văn dài.
- Khi chuyển cấp: luôn nêu **tên vai trò** người sẽ xem (Lead Team / HR) và **lý do ở mức nghiệp vụ**.
- Khi trả lại đơn: luôn nêu **cách sửa cụ thể** (đổi loại nghỉ nào, bổ sung giấy gì).

---

## 5. Bảng map mã nội bộ sang nhãn hiển thị

| Mã nội bộ | Nhãn hiển thị |
|-----------|---------------|
| `SELF_MARRIAGE` | Bản thân kết hôn |
| `CHILD_MARRIAGE` | Con kết hôn |
| `SIBLING_MARRIAGE` | Anh/chị/em ruột kết hôn |
| `READABLE` | Rõ nét |
| `PENDING_ESCALATION` | Chờ {reviewer_label} xem xét |
| `WAITING_EMPLOYEE` | Chờ bạn chỉnh sửa |
| `ESCALATE` | (không hiển thị; dùng câu giải thích) |
| `NEED_CORRECTION` | (không hiển thị; dùng câu giải thích + "Việc bạn cần làm") |

## 6. Bảng map lý do chuyển cấp sang câu giải thích

| Reason code | Câu giải thích (biến trong `{}`) |
|-------------|----------------------------------|
| `PROOF_REVIEW_REQUIRED` | Chúng tôi đã đọc {proof_label} của bạn, nhưng chứng từ cần {reviewer_label} đối chiếu trước khi duyệt. |
| `EXCEED_AUTO_APPROVE_CAP` | Đơn {n} ngày vượt hạn mức tự duyệt ({cap} ngày), nên cần {reviewer_label} phê duyệt. |
| `EVENT_NOT_PAID_LEAVE` | {event_label} chỉ được nghỉ không hưởng lương tối đa {max_days} ngày ({legal_ref}). |
| `DATE_MISMATCH` | Ngày trên chứng từ ({doc_date}) nằm ngoài khoảng nghỉ ({leave_range}). |
| `MISSING_SIGNATURE` | Chứng từ thiếu chữ ký của người có thẩm quyền. |
| `NAME_MISMATCH` | Tên trên chứng từ không khớp với hồ sơ nhân sự. |

---

## 7. Few-shot examples

### Ví dụ 1: Chuyển cấp vì chứng từ chưa được xác minh (giấy kết hôn)

**Input (rút gọn)**
- Loại nghỉ: Việc riêng hưởng lương, 1 ngày
- Sự kiện: CHILD_MARRIAGE, proof_status = chưa VERIFIED
- Ngày cưới 22/09/2026, ngày nghỉ 12/10/2026 (ngoài khoảng)
- Dấu đỏ: có, rõ nét; số dư phép 18 ngày
- decision = ESCALATE, reviewer = Lead Team

**Output mong muốn**
```markdown
### 🔄 Đơn đã chuyển Lead Team xem xét

Chúng tôi đã đọc Giấy chứng nhận kết hôn của bạn. Chứng từ cần được Lead Team đối chiếu trước khi duyệt, và ngày cưới trên giấy (22/09/2026) nằm ngoài ngày bạn xin nghỉ (12/10/2026). Bạn không cần làm gì thêm; chúng tôi sẽ thông báo ngay khi có kết quả.

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| Thông tin nhân sự & ngày nghỉ | ✅ Đạt | Hợp lệ |
| Số dư phép | ✅ Đạt | Còn 18 ngày; đơn này chưa bị trừ phép |
| Đọc chứng từ | ✅ Đạt | Giấy chứng nhận kết hôn · UBND Phường Dịch Vọng Hậu, Cầu Giấy, Hà Nội · cấp 11/10/2026 · có dấu đỏ · rõ nét |
| Đối chiếu ngày cưới | ⚠️ Cần xem xét | Ngày cưới 22/09/2026, ngày nghỉ 12/10/2026 |
| Xác minh chứng từ | ⚠️ Cần xem xét | Chờ Lead Team đối chiếu |

*Trường hợp con kết hôn: tên bạn không nằm trên giấy nên bước đối chiếu tên được bỏ qua theo quy chế.*
```

### Ví dụ 2: Trả lại để chỉnh sửa (sai loại nghỉ)

**Input (rút gọn)**
- Loại nghỉ: Việc riêng hưởng lương, 23/10/2026, 1 ngày
- Lý do: dự lễ thành hôn của em gái ruột
- Sự kiện: SIBLING_MARRIAGE; ngày cưới 24/10/2026 (ngoài khoảng); thiếu chữ ký cơ quan
- decision = NEED_CORRECTION

**Output mong muốn**
```markdown
### ✏️ Cần bạn điều chỉnh đơn

Đơn nghỉ dự lễ cưới của em gái ruột không thuộc diện nghỉ hưởng lương. Theo Điều 115 khoản 2 BLLĐ 2019, bạn chỉ được nghỉ không hưởng lương tối đa 1 ngày cho trường hợp này.

**Việc bạn cần làm**
- Gửi lại đơn với loại nghỉ **"Việc riêng không lương luật định"**, hoặc dùng **phép năm**.
- Kiểm tra lại ngày nghỉ: ngày cưới trên giấy là 24/10/2026, ngày bạn xin nghỉ là 23/10/2026.
- Bổ sung bản chứng từ có chữ ký của cơ quan cấp (bản hiện tại thiếu chữ ký).

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| Thông tin nhân sự & ngày nghỉ | ✅ Đạt | Hợp lệ |
| Số dư phép | ✅ Đạt | Còn 12 ngày; đơn này chưa bị trừ phép |
| Loại nghỉ so với sự kiện | ❌ Không đạt | Anh/chị/em ruột kết hôn không thuộc diện nghỉ có lương |
| Ngày cưới so với ngày nghỉ | ⚠️ Cần xem xét | 24/10/2026 so với 23/10/2026 |
| Chứng từ | ⚠️ Cần xem xét | Có dấu đỏ, rõ nét, thiếu chữ ký cơ quan |
```

### Ví dụ 3: Chuyển cấp vì vượt hạn mức tự duyệt (nghỉ ốm 2 ngày)

**Input (rút gọn)**
- Nghỉ ốm 15-16/10/2026, 2 ngày; bác sĩ chỉ định 15-16/10 (khớp); tên khớp
- Số dư phép 1 ngày; chứng từ hợp lệ
- decision = ESCALATE, reason = EXCEED_AUTO_APPROVE_CAP, reviewer = Quản lý trực tiếp

**Output mong muốn**
```markdown
### 🔄 Đơn đã chuyển Quản lý trực tiếp phê duyệt

Giấy chứng nhận nghỉ ốm của bạn hợp lệ và khoảng nghỉ nằm trong chỉ định của bác sĩ. Do đơn nghỉ 2 ngày vượt hạn mức tự duyệt, đơn cần Quản lý trực tiếp phê duyệt.

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| Thông tin nhân sự & ngày nghỉ | ✅ Đạt | Hợp lệ |
| Chứng từ | ✅ Đạt | Giấy nghỉ ốm · Bệnh viện Giao thông Vận tải · cấp 15/10/2026 · có dấu đỏ, chữ ký bác sĩ · rõ nét |
| Tên trên giấy | ✅ Đạt | Khớp hồ sơ nhân sự |
| Khoảng nghỉ so với chỉ định bác sĩ | ✅ Đạt | 15-16/10/2026, nằm trong chỉ định |
| Hạn mức tự duyệt | ⚠️ Cần xem xét | Đơn 2 ngày, cần quản lý phê duyệt |
```

### Ví dụ 4: Tự động duyệt (không cần chứng từ)

**Output mong muốn**
```markdown
### ✅ Đơn đã được duyệt tự động

Đơn nghỉ phép năm 1 ngày (05/10/2026) hợp lệ theo quy chế. Hệ thống đã duyệt và trừ 1 ngày phép; bạn còn **7 ngày**.

| Hạng mục | Kết quả | Ghi chú |
|---|---|---|
| Thông tin nhân sự & ngày nghỉ | ✅ Đạt | Hợp lệ |
| Số dư phép | ✅ Đạt | Còn 7 ngày sau khi trừ |
```

### Ví dụ 5: Không đủ điều kiện (tên không khớp)

**Input**: nghỉ ốm, tên trên giấy khác hồ sơ nhân sự. decision = REJECT_RESUBMIT

**Output mong muốn**
```markdown
### ❌ Chứng từ chưa hợp lệ, cần nộp lại

Tên trên giấy chứng nhận nghỉ ốm ("NGUYỄN VĂN A") không khớp với hồ sơ nhân sự của bạn, nên chúng tôi chưa thể xử lý đơn.

**Việc bạn cần làm**
- Kiểm tra lại chứng từ đã tải lên có đúng của bạn không.
- Tải lên chứng từ đúng tên, hoặc liên hệ HR nếu hồ sơ nhân sự có sai sót.
```

---

## 8. Ví dụ xấu (không viết như vậy)

**Xấu 1: lộ kỹ thuật, trùng lặp, sai người nhận**
> Kết quả bước này: decision = ESCALATE. Trạng thái = PENDING_ESCALATION. Giải thích: [Chứng từ cần HR đối chiếu] ... Đơn chuyển tới Lead Team ... Lý do escalate: [chứng từ y tế cần đối chiếu] ... cần phòng nhân sự (hr) đối soát...

Vấn đề: lộ mã nội bộ, nhắc HR và Lead Team cùng lúc, gọi giấy kết hôn là "chứng từ y tế", lý do lặp hai lần.

**Xấu 2: mâu thuẫn nhãn**
> Sự kiện SIBLING_MARRIAGE ... | Sự kiện: SELF_MARRIAGE

Vấn đề: một đơn có hai loại sự kiện khác nhau trong cùng phản hồi.

---

## 9. Checklist cho agent sau khi sửa

- [ ] Không còn chuỗi cứng "chứng từ y tế" / "HR" trong template dùng chung; mọi chỗ dùng biến.
- [ ] Không còn mã enum nào xuất hiện trong text hiển thị (grep `[A-Z]+_[A-Z]+`).
- [ ] Mỗi phản hồi chỉ có **một** câu giải thích chính.
- [ ] Người nhận (reviewer) nhất quán trong tiêu đề, tóm tắt và bảng.
- [ ] Ngày luôn `dd/mm/yyyy`; số ngày không có `.0`.
- [ ] Có unit test snapshot cho 5 ví dụ ở mục 7 (so khớp cấu trúc, không cần khớp từng chữ).
- [ ] Phản hồi vẫn được dựng từ template xác định (không gọi LLM), trừ khi có yêu cầu khác.
- [ ] Dữ liệu từ VLM và kết quả từ code/rule vẫn được ghi nguồn trong log nội bộ, không hiển thị cho nhân viên.