# Frontend Report

## 1. Mục đích

Frontend là giao diện người dùng demo cho nhân viên và quản lý. Nó tương tác với API backend để:

- tạo đơn nghỉ
- tải file chứng từ
- xem decision / explanation
- giao việc cho manager / HR
- theo dõi trạng thái đơn

## 2. File quan trọng

- [frontend/index.html](../../frontend/index.html)
- [frontend/app.js](../../frontend/app.js)
- [frontend/styles.css](../../frontend/styles.css)

## 3. Mô hình UI

Frontend là static SPA (HTML + JS), không dùng framework lớn. Nó thực chất là UI web kiểu dashboard:

- nhập thông tin nhân viên
- chọn loại nghỉ
- nhập ngày / lý do / người bàn giao
- upload chứng từ
- xem kết quả phê duyệt

## 4. Phân loại chức năng

### 4.1 Form nhân viên

- nhập ngày bắt đầu / kết thúc
- chọn `leave_type`
- chọn lý do
- cho phép gửi text tự nhiên hoặc form structured
- chọn `actor_id` để mô phỏng vai trò người dùng

### 4.2 Flow human approval

- manager / HR / CEO xem request
- gửi action như: approve / reject / request more info
- frontend có thể gọi các endpoint decision

### 4.3 Xem data / báo cáo

- status request
- explanation
- quick action options
- result JSON / policy clause

## 5. Giao tiếp với backend

Frontend chủ yếu gọi các API trên FastAPI. Tương tác nhận dạng qua:

- `X-Actor-ID` header
- `actor_id` query/body fields
- route `leave`, `verify`, `meta`

## 6. Điểm mạnh

- Dễ demo, dễ chạy local
- Tương tác trực quan cho người dùng
- Ít dependencies, nhanh triển khai

## 7. Hạn chế

- Không có auth thực tế
- Không có bảo mật production
- Không có phân quyền nghiêm ngặt
- UI đang tập trung demo hơn là sản phẩm cuối cùng

## 8. Kết luận

Frontend là lớp giao diện demo cho hệ thống, rất phù hợp cho validation logic nhưng chưa đủ để coi là app production-grade.
