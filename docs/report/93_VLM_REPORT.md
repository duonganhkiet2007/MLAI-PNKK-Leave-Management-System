# VLM Report

## 1. Mục đích

VLM được dùng để phân tích chứng từ đính kèm như:

- giấy khám bệnh
- giấy nghỉ ốm
- giấy chứng tử
- giấy cưới
- giấy thai sản
- hồ sơ tai nạn lao động

Mục tiêu: trích xuất thông tin có thể so khớp với leave request, nhưng không tự động xác thực tính hợp lệ của chứng từ.

## 2. File chính

- [Leave_Application/vlm_inspector.py](../../Leave_Application/vlm_inspector.py)
- [backend/ai/ai_stack.py](../../backend/ai/ai_stack.py)
- [backend/services/orchestration.py](../../backend/services/orchestration.py)

## 3. Model dùng

Theo code hiện tại:

- model VLM mặc định: `qwen2.5vl:7b`
- gọi qua Ollama
- API endpoint dùng generate với `images` payload

## 4. Chức năng thực tế

VLM trích xuất:

- loại chứng từ
- tên người được nhắc tới
- chẩn đoán / diễn giải
- nơi cấp / issuer
- issue date
- recommended date range
- chữ ký, dấu đỏ, độ đọc được
- tín hiệu ai_generated / tampered / mờ / không rõ

## 5. Vị trí trong luồng

- khi request có attachment hoặc `proof_id`
- backend gọi `inspect_document_with_vlm`
- kết quả được merge vào context
- rule engine tiếp tục đánh giá ở bước `PROOF`

## 6. Kiểm tra trạng thái thực tế

Chúng tôi đã thực hiện gọi runtime trực tiếp:

- endpoint: `/api/generate`
- model: `qwen2.5vl:7b`
- kết quả: `HTTP Error 500: Internal Server Error`

Đây là bằng chứng thực tế rằng VLM đang không hoạt động ổn định trong môi trường hiện tại, dù model đã có sẵn trong Ollama.

## 7. Cách hiểu kết luận

VLM có code và model đã được cài đặt, nhưng tại thời điểm kiểm tra thực tế nó chưa chạy ổn định. Có khả năng:

- lỗi payload hình ảnh
- lỗi runtime model / Ollama adapter
- lỗi xử lý trong layer `vlm_inspector.py`
- lỗi dependency / image processing

## 8. Kết luận module VLM

VLM hiện chưa ở trạng thái “hoạt động bình thường” theo kiểm tra runtime; nó đang thiếu chứng thực hoạt động stable.

## 9. Điểm mạnh

- cấu trúc extraction rõ ràng
- có fallback mock nếu cần
- tích hợp vào context quyết định

## 10. Hạn chế

- runtime không ổn định ở thời điểm kiểm tra
- output từ VLM không phải là evidence đã xác thực
- có tính chất “gợi ý / nhận diện” chứ không phải “xác nhận chính thức”
