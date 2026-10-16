# BÁO CÁO KẾT QUẢ ĐỐI SÁNH HIỆU NĂNG (BENCHMARK)
### So sánh Thời gian Thao tác Thủ công vs Pipeline AI Tự động hóa
*Bộ dữ liệu kiểm định: 130 ca kiểm thử (STAFF_TEST_CASES) & 32 mẫu chứng từ y tế/hành chính*

---

## 🏆 Bảng 1: Tổng quan Kết quả Benchmark (Headline Results)

| Chỉ số đo lường | 👤 Thao tác Thủ công (Người dùng) | ⚡ Pipeline AI Tự động hóa | 🚀 Tốc độ Tăng & Hiệu quả |
| :--- | :--- | :--- | :--- |
| **Tổng thời gian hoàn thành (130 đơn)** | **4.952,0 giây** (~1,38 giờ) | **2,701 giây** (Tuần tự)<br>**6,540 giây** (Song song 5 luồng) | **Nhanh hơn 1.833,4 LẦN** (Tuần tự)<br>**Nhanh hơn 757,2 LẦN** (Song song) |
| **Thời gian trung bình mỗi đơn** | **35,4 giây** | **19,29 mili-giây (ms)** | **Nhanh hơn 1.833,6 lần** |
| **Quy trình truyền thống (E2E có duyệt tay)** | **30.152,0 giây** (~8,38 giờ) | **2,701 giây** | **Nhanh hơn 11.163,3 LẦN** |
| **Tổng thời gian tiết kiệm được** | — | **4.949,3 giây** (~1,37 giờ) | **Cắt giảm 99,95% độ trễ** |
| **Thông lượng xử lý (Throughput)** | ~0,03 đơn/giây | **21,41 đơn/giây** | **Năng lực xử lý gấp 713,7 lần** |

---

## 📂 Bảng 2: Chi tiết theo 10 Nhóm Kịch bản Kiểm thử (Category Breakdown)

| Mã | Mô tả kịch bản nghiệp vụ | Số đơn | Đơn có chứng từ | Thời gian Thủ công (s) | Thời gian Pipeline (s) | Tốc độ Tăng | Độ khớp Chính sách |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **VAL** | Đơn hợp lệ tiêu chuẩn (1–2 ngày tự duyệt) | 20 | 0 | 705,8s | 0,388s | **1.821,1x** | 100,0% |
| **BAL** | Đơn kiểm tra giới hạn số dư phép năm | 10 | 0 | 377,9s | 0,207s | **1.828,5x** | 100,0% |
| **NOT** | Đơn kiểm tra quy tắc thời hạn báo trước | 10 | 0 | 289,8s | 0,199s | **1.457,4x** | 80,0% |
| **QUO** | Đơn vượt hạn mức vắng mặt của phòng ban | 10 | 0 | 246,6s | 0,188s | **1.313,2x** | 0,0% |
| **EXC** | Đơn thuộc thẩm quyền cấp quản lý / ngoại lệ | 15 | 6 | 619,0s | 0,306s | **2.022,1x** | 100,0% |
| **PRF** | Đơn thẩm định chứng từ y tế / luật định | 15 | 10 | 680,0s | 0,271s | **2.505,3x** | 100,0% |
| **MIS** | Đơn sai lệch thông tin chứng từ / nghi vấn | 15 | 15 | 806,9s | 0,286s | **2.816,3x** | 33,3% |
| **DUP** | Đơn trùng lặp thời gian nghỉ đã duyệt | 10 | 0 | 245,1s | 0,193s | **1.269,8x** | 0,0% |
| **BND** | Đơn trường hợp biên (lễ, tết, cuối tuần) | 15 | 1 | 392,2s | 0,283s | **1.387,6x** | 86,7% |
| **LNG** | Đơn nộp bằng ngôn ngữ tự nhiên (NLP) | 20 | 0 | 588,8s | 0,380s | **1.549,4x** | 20,0% |

---

## 📑 Bảng 3: So sánh Đơn có Chứng từ vs Đơn không cần Chứng từ

| Nhóm hồ sơ kiểm định | Số lượng đơn | Thời gian Thao tác Thủ công | Thời gian Pipeline Tự động | Hệ số Tăng tốc |
| :--- | :---: | :---: | :---: | :---: |
| **Hồ sơ có đính kèm chứng từ** *(Nghỉ ốm, thai sản, cưới hỏi, tai nạn)* | 32 | **1.767,5 giây** (~29,5 phút) | **0,628 giây** | **Nhanh hơn 2.812,7 LẦN** |
| **Hồ sơ thường quy / không chứng từ** *(Phép năm, nghỉ không lương)* | 108 | **3.184,5 giây** (~53,1 phút) | **2,073 giây** | **Nhanh hơn 1.536,5 LẦN** |
