# ĐÁNH GIÁ CHI PHÍ, THỜI GIAN INFERENCE, TƯƠNG TÁC NGƯỜI DÙNG VÀ TỶ LỆ CHUYỂN THÀNH CÔNG

Bản này tách riêng khỏi report chính để tập trung vào KPI vận hành của hệ thống nghỉ phép AI-assisted.

## 1. Tổng quan đánh giá

Mô hình hiện tại là hybrid:
- Frontend thu thập thông tin và upload tài liệu
- Backend điều phối request
- LLM trích xuất dữ liệu từ text tự nhiên
- VLM trích xuất evidence từ giấy tờ
- Decision Tree / Rule Engine quyết định cuối cùng
- Department Head và CEO là tầng approval thực tế

Điểm quan trọng: AI không quyết định độc lập. AI chỉ hỗ trợ trích xuất, xác minh, và gợi ý route. Quyết định cuối cùng vẫn thuộc về rule engine + người thật.

## 2. Bảng đánh giá tổng thể

| Chỉ số | Frontend / UI | Backend / Orchestration | LLM | VLM | Decision Tree / Rule Engine | Ghi chú |
|---|---|---|---|---|---|---|
| Chi phí xử lý mỗi request | Rất thấp | Thấp đến trung bình | Trung bình | Trung bình đến cao | Rất thấp | Chi phí chủ yếu nằm ở LLM/VLM nếu chạy trên máy chủ AI |
| Chi phí phần cứng ước tính | Không đáng kể | Thấp | Trung bình nếu chạy local Ollama | Cao hơn LLM do xử lý ảnh | Rất thấp | Nếu dùng GPU, chi phí tăng nhưng latency giảm mạnh |
| Thời gian inference trung bình | 0.1 - 0.5s | 0.3 - 1.0s | 1 - 5s | 5 - 20s tùy ảnh / độ lớn file | 0.05 - 0.5s | Ảnh mờ, lớn, hoặc nhiều văn bản làm VLM chậm hơn |
| Tần suất tương tác người dùng | 1 - 2 bước | 0 - 1 bước | 0 bước | 0 bước | 0 bước | Người dùng chỉ tương tác khi cần bổ sung thông tin hoặc khi Escalate |
| Số vòng hỏi bổ sung thông tin | Thấp | Thấp | Trung bình | Trung bình | Thấp | Ví dụ: thiếu chứng từ, sai ngày, tên người bệnh không khớp |
| Tỷ lệ tự duyệt thành công | Cao nếu form hợp lệ | Cao | Cao nếu text sạch | Trung bình nếu chứng từ rõ | Cao | Đơn đơn giản dễ pass qua auto approve hoặc reviewer nhanh |
| Tỷ lệ cần bổ sung thông tin | Thấp | Thấp | Trung bình | Cao khi hồ sơ mờ | Thấp | VLM và LLM rủi ro lớn nhất ở dữ liệu không rõ |
| Tỷ lệ escalate | Không áp dụng | Thấp | Thấp | Trung bình | Trung bình | Xuất hiện khi policy phức tạp, dài hạn, hoặc chứng từ mơ hồ |
| Tỷ lệ từ chối chính thức | Không áp dụng | Thấp | Thấp | Thấp | Cao khi vi phạm rõ | Rule engine xử lý balance, overlap, missing proof, invalid request |
| Tỷ lệ xong quy trình theo đúng flow | 70% - 90% trên đơn đơn giản | 80% - 95% | 75% - 90% | 60% - 85% | 90%+ | Tỷ lệ phụ thuộc chất lượng ảnh, text rõ, và policy |
| Mức độ phụ thuộc vào người thật | Trung bình | Thấp | Thấp | Trung bình | Cao nếu rule engine là nguồn quyết định | Quá trình vẫn cần người review hoặc approval |
| Mức độ rủi ro về sai lệch | Thấp | Thấp | Trung bình | Cao nếu ảnh không rõ | Thấp | Rủi ro lớn nhất thường là VLM đọc nhầm hoặc LLM trích xuất thiếu trường |
| Mức độ dễ triển khai | Rất cao | Cao | Cao | Trung bình | Rất cao | Rule engine dễ triển khai hơn AI vì có tính xác định và kiểm toán |
| Độ tin cậy trong vận hành | Cao | Cao | Trung bình | Trung bình | Cao | Đây là mô hình hybrid: AI hỗ trợ, rule engine là trụ cột |

## 3. Ước tính theo từng loại nghỉ

| Loại đơn | Tỷ lệ tự approve | Tỷ lệ cần bổ sung thông tin | Tỷ lệ escalated | Tỷ lệ reject | Mức độ phụ thuộc VLM | Mức độ phụ thuộc LLM |
|---|---|---|---|---|---|---|
| ANNUAL | 60% - 80% | 10% - 20% | 10% - 20% | 5% - 10% | Thấp | Thấp |
| SPECIAL_PAID | 20% - 40% | 25% - 35% | 25% - 35% | 5% - 10% | Trung bình | Trung bình |
| SICK_MEDICAL | 50% - 75% | 15% - 25% | 10% - 20% | 5% - 10% | Cao | Trung bình |
| MEDICAL_EMERGENCY | 30% - 50% | 20% - 30% | 20% - 30% | 5% - 10% | Cao | Trung bình |
| WORK_ACCIDENT | 25% - 45% | 20% - 30% | 25% - 35% | 5% - 10% | Cao | Trung bình |
| MATERNITY | 15% - 30% | 20% - 30% | 30% - 45% | 10% - 15% | Cao | Trung bình |
| STATUTORY_UNPAID | 30% - 50% | 20% - 30% | 20% - 30% | 5% - 10% | Thấp đến trung bình | Trung bình |
| UNPAID_OTHER | 35% - 55% | 20% - 30% | 15% - 25% | 5% - 10% | Thấp | Trung bình |

## 4. Đánh giá hiệu quả vận hành

- Chi phí vận hành: thấp đến trung bình nếu chạy local, tăng nhanh nếu dùng AI cloud hoặc xử lý nhiều ảnh lớn cùng lúc.
- Thời gian inference: phần chậm nhất thường là VLM xử lý chứng từ, kế đến là LLM trích xuất text và chuẩn hóa dữ liệu.
- Tương tác người dùng: ít ở đơn chuẩn; tăng mạnh ở đơn thiếu thông tin hoặc chứng từ không rõ.
- Tỷ lệ chuyển đổi thành công: cao ở các đơn đơn giản; giảm ở các trường hợp có chứng từ phức tạp, dài ngày hoặc có yếu tố pháp lý cao.
- Điểm mạnh của mô hình: rõ ràng, dễ kiểm toán, dễ mở rộng, không phụ thuộc hoàn toàn vào AI quyết định.
- Điểm yếu: phụ thuộc vào chất lượng đầu vào, VLM đọc nhầm chứng từ, và người dùng phải bổ sung thông tin khi thiếu trường dữ liệu.

## 5. Kết luận ngắn gọn

Nếu triển khai ở môi trường local/demo với lượng request vừa phải, mô hình hybrid này cho hiệu suất tốt, chi phí kiểm soát được, và tỷ lệ hoàn tất quy trình cao trên đơn nghỉ chuẩn. Với các đơn dài ngày, chứng từ phức tạp hoặc có yếu tố pháp lý, hệ thống sẽ chuyển sang reviewer / escalated flow—đây là cách vận hành đúng với logic hiện tại của hệ thống.
