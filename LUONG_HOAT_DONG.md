# 📋 LUỒNG HOẠT ĐỘNG HỆ THỐNG PHÊ DUYỆT NGHỈ PHÉP AI
**Hệ thống:** The Escalation Referee · **Team:** PNKK

---

## 🧭 SƠ ĐỒ LUỒNG TỔNG QUAN

```
[ NHÂN VIÊN ]                 [ TRỢ LÝ AI ]                    [ QUẢN LÝ ]
 (Staff UI)              (Agent Orchestrator)                 (Admin UI)
     │                             │                              │
     │ 1. Nộp đơn xin nghỉ         │                              │
     ├────────────────────────────►│                              │
     │                             │                              │
     │                             ├─► Phân tích & Đối chiếu      │
     │                             │   (Quỹ phép, ngày, file...)  │
     │                             │                              │
     │                             ├───[ Nhánh A: Thường quy ]───►│ (Ghi Audit Log)
     │ 2a. Nhận kết quả:           │    TỰ ĐỘNG DUYỆT             │
     │◄─── 🟢 Tự duyệt             │                              │
     │                             │                              │
     │                             └───[ Nhánh B: Ngoại lệ ]─────►│ (Đẩy Hàng đợi)
     │ 2b. Nhận trạng thái:             CHUYỂN TIẾP QUẢN LÝ       │
     │◄─── 🟡 Đang chờ                                            │
     │                                                            │
     │                                                            │ 3. Xem tham vấn AI &
     │                                                            │    Ra quyết định:
     │                                                            │    [Duyệt/Từ chối]
     │                                                            │
     │ 4. Nhận kết quả mới                                        │
     │◄─── 🔵 Quản lý duyệt / 🔴 Từ chối ─────────────────────────┤
     │                                                            │
     │                                                            │ (Quyền can thiệp)
     │ 5. Bị hủy duyệt & hoàn phép                                │ 🛑 HỦY LỆNH AI
     │◄─── 🔴 Đã thu hồi ─────────────────────────────────────────┤
```

---

## 🔄 5 BƯỚC THỰC THI CHI TIẾT

### Bước 1: Nhân viên nộp đơn (Giao diện Nhân viên)
- Nhân viên điền biểu mẫu (hoặc gõ chat tự do) kèm file chứng từ (PDF/Ảnh).
- Hệ thống gửi yêu cầu sang **Trợ lý AI (Agent Orchestrator)**.

### Bước 2: AI Phân tích & Rẽ nhánh quyết định
Tác tử AI đối chiếu dữ liệu nhân viên, quỹ phép và quy chế nội bộ:
- **Nhánh A (Thường quy) ➔ TỰ ĐỘNG DUYỆT:**
  - Áp dụng khi: Đủ số dư phép, đúng số ngày quy định, có bàn giao công việc.
  - Kết quả trả về ngay cho Nhân viên: `🟢 Tự động duyệt`.
  - Tự động ghi nhật ký sang mục **Nhật ký AI tự duyệt** của Quản lý.
- **Nhánh B (Ngoại lệ) ➔ CHUYỂN TIẾP (Pending Admin):**
  - Áp dụng khi: Nghỉ dài ngày vượt hạn mức, thiếu chứng từ BHXH, hoặc hết phép.
  - Cập nhật trạng thái cho Nhân viên: `🟡 Đang chờ Quản lý`.
  - Đẩy hồ sơ kèm câu hỏi tham vấn vào **Hàng đợi xử lý** của Quản lý.

### Bước 3: Quản lý ra quyết định (Giao diện Quản lý)
- Quản lý mở **Hàng đợi xử lý**, xem tóm tắt đơn, xem file đính kèm và đọc **Khung tham vấn AI**.
- Lựa chọn 1 trong 3 hành động:
  - `✅ Duyệt đặc cách`
  - `❌ Từ chối đơn`
  - `🔄 Yêu cầu bổ sung chứng từ`

### Bước 4: Đồng bộ trạng thái & Cập nhật Lịch tuần
- Trạng thái mới (`🔵 Quản lý đã duyệt` hoặc `🔴 Từ chối`) được gửi về màn hình Nhân viên.
- Nếu được duyệt: Tự động trừ quỹ phép và gắn thẻ tên vào **Lịch vắng mặt trong tuần**.

### Bước 5: Quyền kiểm soát tối cao (Override của Quản lý)
- Tại mục **Nhật ký AI tự duyệt**, nếu phát hiện xung đột lịch trực hoặc rủi ro, Quản lý có thể bấm **`🛑 Hủy lệnh AI`**.
- Hệ thống lập tức thu hồi phê duyệt, hoàn trả ngày phép và thông báo cho nhân viên.
