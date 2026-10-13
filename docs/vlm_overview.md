# Tổng quan VLM trong hệ thống

Tài liệu này tóm tắt cách Vision-Language Model (VLM) được thiết kế và tích hợp trong hệ thống xét duyệt đơn nghỉ phép, dựa trên mã nguồn hiện tại. Các phần nói về hành vi đang chạy được phân biệt với cấu hình persona/schema đã có nhưng chưa chắc được kích hoạt trong mọi luồng.

## VLM làm gì?

VLM đọc ảnh chứng từ và trích xuất thông tin có thể quan sát trên giấy, chẳng hạn tên, đơn vị cấp, ngày tháng, chẩn đoán, chữ ký, dấu và độ dễ đọc. Kết quả được chuẩn hóa thành các facts để backend đối chiếu với đơn nghỉ.

VLM không phải nguồn quyết định cuối cùng về quyền lợi, số dư phép hay thẩm quyền phê duyệt. Các quyết định nghiệp vụ được xử lý bởi rule engine cùng dữ liệu tin cậy từ hệ thống; trường đầu ra của mô hình cũng không được phép ghi các giá trị tin cậy như quyết định hoặc trạng thái xác minh chứng từ. Một số thông tin đối chiếu, như điểm tương quan và danh sách vấn đề, được tính bằng logic tất định trong `core/vlm_inspector.py`; chúng là tín hiệu hỗ trợ, không phải kết luận pháp lý.

## Kiến trúc và luồng xử lý

Mô hình mặc định là `qwen2.5vl:7b`, gọi qua Ollama `/api/generate`. Các thiết lập chính nằm trong `backend/ai/ai_stack.py` và `core/vlm_inspector.py`:

| Thiết lập | Giá trị mặc định |
|---|---|
| Model VLM | `qwen2.5vl:7b` |
| Ollama | `http://localhost:11434` |
| Timeout | 180 giây |
| Cạnh dài tối đa của ảnh | 1600 px |
| Context khi sinh | 8192 tokens |
| Nhiệt độ | 0.0 |

Luồng upload chứng từ thực hiện các bước sau:

1. API kiểm tra người dùng, loại tệp, MIME/magic bytes và giới hạn dung lượng 10 MB; tệp được lưu bằng tên UUID và tính SHA-256.
2. Backend tạo công việc kiểm tra bền vững trong SQLite và đưa chứng từ sang trạng thái `PENDING`.
3. Worker nền nhận công việc trong transaction ngắn. Phần suy luận VLM chạy ngoài transaction để không giữ khóa cơ sở dữ liệu trong thời gian chờ model.
4. Ảnh được kiểm tra độ mờ bằng biến thiên Laplacian (ngưỡng mặc định 50), đổi về RGB nếu cần, resize tối đa 1600 px, căn kích thước theo bội số 28, nén JPEG chất lượng 85 rồi mã hóa base64.
5. Inspector chọn prompt/schema, gọi Ollama với yêu cầu JSON, parse kết quả và chuẩn hóa vào `ProofExtraction`.
6. Kết quả JSON cùng một số trường phổ biến được lưu vào `proof_documents`; công việc đang chờ chứng từ được tiếp tục xử lý.

Worker có hàng đợi bền vững, khôi phục công việc còn `PROCESSING` sau khi khởi động lại và retry hữu hạn (mặc định tối đa 2 lần retry). Cấu hình `VLM_MAX_CONCURRENCY` hiện không tạo thêm worker; triển khai service đang có một worker nền.

## Persona và schema trích xuất

`core/vlm_inspector.py` định nghĩa schema riêng theo loại nghỉ/lý do để prompt tập trung vào facts phù hợp. Các schema bao gồm:

| Schema | Facts chính |
|---|---|
| `SICK_MEDICAL` | Bệnh nhân, chẩn đoán, ngày bác sĩ chỉ định, cơ sở cấp, chữ ký và dấu |
| `EMERGENCY` | Bằng chứng cấp cứu, ngày nhập viện/xuất viện, trạng thái chưa xác định ngày kết thúc và yêu cầu bổ sung giấy ra viện |
| `WEDDING` | Người liên quan, bạn đời, loại sự kiện, ngày cưới và đơn vị cấp |
| `BEREAVEMENT` | Người mất, quan hệ, ngày mất/tang lễ và đơn vị cấp |
| `STATUTORY` | Người liên quan, quan hệ với nhân viên, loại/ngày sự kiện, độ tin cậy và nhu cầu quản lý xem xét |
| `MATERNITY` | Giai đoạn thai sản, ngày dự sinh, thời gian nghỉ, mã BHXH và đơn vị cấp |
| `WORK_ACCIDENT` | Mô tả/ngày tai nạn, liên quan công việc, thời gian nghỉ và dấu BHXH |
| `ADMINISTRATIVE` | Mục đích giấy tờ, người đứng tên, thời hạn hiệu lực và đơn vị cấp |

Nếu tài liệu được đánh dấu `UNREADABLE`, parser chủ động xóa các trường văn bản/ngày tháng thay vì sử dụng nội dung không đáng tin cậy. Ảnh quá mờ có thể bị chặn trước khi gọi model. Kết quả chuẩn hóa dùng Pydantic `ProofExtraction`, có các trường mở rộng cho các schema trên và từ chối trường ngoài hợp đồng.

### Khác biệt giữa cấu hình và luồng đang chạy

Inspector chọn persona bằng `leave_type` và `reason_category`. Luồng upload gửi hai giá trị này từ form vào job; worker ưu tiên ngữ cảnh của đơn đã liên kết nếu đơn được submit trong lúc job còn chờ. Với client cũ không gửi ngữ cảnh, worker suy ra loại nghỉ gần nhất từ `proof_type` thay vì mặc định `SICK_MEDICAL`. Một số chứng từ, như giấy chứng tử hoặc giấy kết hôn, vẫn có thể thuộc nhiều loại nghỉ khác nhau; khi đó cần cung cấp `leave_type`/`reason_category` từ đơn để chọn đúng schema. Kết quả đã lưu chỉ được tái sử dụng khi ngữ cảnh khớp; các kết quả cũ không có ngữ cảnh chỉ được dùng lại trong trường hợp y tế tương thích rõ ràng.

## Đầu ra và đối chiếu

Đầu ra đầy đủ được lưu theo cấu trúc gồm:

- `document_summary`: tên, chẩn đoán, nơi/ngày cấp, khoảng ngày nghỉ và một số trường sự kiện.
- `flags`: dấu, chữ ký, độ dễ đọc, cùng cờ model nhận diện sửa đổi/giả mạo.
- `correlation_analysis`: điểm và vấn đề khi so sánh dữ liệu trên giấy với thông tin đơn.
- `escalation_flags`: lý do cần xem xét thêm.
- `raw_fields_detected`: tên các trường được nhận diện.

Điểm tương quan được tính trong code dựa trên tên, chẩn đoán/lý do, khoảng ngày và số ngày. Với các loại nghỉ không mang tính y tế, logic bỏ qua đối chiếu từ khóa chẩn đoán. Điểm này không xác minh con dấu/chữ ký với cơ quan phát hành và không chứng minh tài liệu là thật.

## Cache, lỗi và chế độ mock

- Cache dùng SHA-256 cùng loại nghỉ/lý do để tránh suy luận lặp lại mà không trộn kết quả giữa các ngữ cảnh; kết quả có thể được giữ trong bộ nhớ, trên đĩa và trong bản ghi chứng từ.
- Trong worker upload, `allow_mock_fallback=False`. Nếu Ollama không sẵn sàng, model chưa được tải, tệp không đọc được hoặc phản hồi không parse được, công việc sẽ retry rồi có thể chuyển `FAILED`; backend không nên xem lỗi đó là bằng chứng gian lận.
- Inspector có chế độ mock tường minh và biến môi trường `VLM_FORCE_MOCK` / `VLM_ALLOW_MOCK_FALLBACK` cho phát triển, kiểm thử hoặc fallback được cho phép. Mock không phải kết quả đọc ảnh thật.

## Kiểm tra liên quan

Các bài test hiện có bao phủ việc resize ảnh và căn kích thước theo bội số 28 (`tests/test_vlm_resize.py`), workflow worker/transaction/retry/cache (`tests/test_phase1_async_vlm_tx.py`), số lần gọi model (`tests/test_model_invocation_counts.py`) và một số bất biến về prompt, trường tin cậy, lỗi VLM trong `tests/test_decision_tree.py`.

## Mã nguồn tham khảo

- `core/vlm_inspector.py`: persona, prompt, preprocessing, gọi Ollama, parse và chuẩn hóa kết quả.
- `backend/ai/ai_stack.py`: model và thiết lập kết nối Ollama.
- `backend/services/inspection_service.py`: hàng đợi nền, retry, lưu kết quả và tiếp tục đơn chờ.
- `backend/routers/leave_router.py`: upload chứng từ và endpoint trạng thái kiểm tra.
- `core/domain.py`: enum `ProofType` và schema `ProofExtraction`.
- `docs/persona_vlm_md.md`: tài liệu thiết kế persona/schema chi tiết.