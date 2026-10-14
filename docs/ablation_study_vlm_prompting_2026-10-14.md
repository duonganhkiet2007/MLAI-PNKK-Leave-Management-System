# Ablation Study: Prompting cho VLM đọc chứng từ

**Ngày:** 2026-10-14  
**Trạng thái:** Bản minh họa thiết kế và kết quả giả lập, chưa phải kết quả benchmark chạy thật.

## 1. Mục tiêu

Đánh giá riêng và kết hợp hai kỹ thuật prompting cho VLM đọc chứng từ nghỉ phép:

1. **Persona / role-based prompting:** giao vai trò phù hợp với loại chứng từ, ví dụ chuyên viên hồ sơ y tế, xác minh hôn sự hoặc tang lễ.
2. **Chain-of-thought (CoT) prompting:** yêu cầu mô hình rà soát các bước quan sát theo thứ tự trước khi điền kết quả JSON.

Giả thuyết cần kiểm tra: Base VLM < Base + một kỹ thuật < Base + cả hai, xét chất lượng trích xuất tổng thể. Đây là giả thuyết, không phải điều được đảm bảo trước.

## 2. Hiện trạng trong repository

`core/vlm_inspector.py` hiện đã chọn persona, schema và thứ tự decision tree theo loại nghỉ/chứng từ. Đây là prompting có hướng dẫn vai trò và quy trình trích xuất. Tuy nhiên, prompt hiện tại **không yêu cầu CoT tường minh theo từng bước**; decision tree đang mô tả thứ tự trường cần kiểm tra, không tương đương với một thí nghiệm CoT độc lập. Vì vậy, không thể dùng kết quả hiện có để kết luận persona hay CoT đã cải thiện độ chính xác.

Bộ test **N=138** dưới đây là quy mô theo yêu cầu của nghiên cứu. Workspace hiện không có manifest xác nhận bộ 138 ID này: `benchmarks/datasets/unified_cases.json` có 158 case, trong đó 46 case có ảnh; bộ `applications.json` có 140 case. Tài liệu benchmark cũng nêu VLM real inference là opt-in và output mock không được tính là độ chính xác. Do đó, bảng kết quả ở mục 5 được **giả lập có chủ đích** để minh họa cách báo cáo, không được trích dẫn như số đo thực nghiệm.

## 3. Thiết kế ablation

### Các cấu hình

| Mã | Cấu hình | Thay đổi so với Base |
|---|---|---|
| A | Base VLM | Prompt chung, không giao persona chuyên biệt, không yêu cầu rà soát theo bước |
| B | Base + Persona | Giao vai trò chuyên môn theo loại chứng từ; giữ cùng schema đầu ra |
| C | Base + CoT | Không giao persona; thêm checklist rà soát tuần tự trước khi xuất JSON |
| D | Base + Persona + CoT | Kết hợp vai trò chuyên môn và checklist tuần tự |

Để ablation có ý nghĩa, giữ nguyên model, ảnh, ngữ cảnh đơn, schema JSON, tiền xử lý ảnh, giới hạn token, temperature và hậu xử lý giữa bốn cấu hình. Chỉ bật/tắt hai thành phần persona và CoT. Persona không được phép thay đổi ground truth hay đưa ra kết luận pháp lý. Checklist CoT chỉ hướng dẫn mô hình kiểm tra facts quan sát được; đầu ra cuối cùng vẫn là JSON, không yêu cầu công khai suy luận nội bộ.

### Bộ dữ liệu và quy trình đề xuất

- Cố định đúng **138 case** bằng manifest có `case_id`, loại chứng từ, nhãn gold và đường dẫn ảnh; ghi hash của manifest/ảnh trước khi chạy.
- Bao gồm ảnh đọc được, chất lượng thấp, trường bị che khuất, loại chứng từ gần giống nhau, ngày tháng mơ hồ, tên khác thứ tự/dấu và dữ kiện không xuất hiện trên giấy.
- Chạy cả bốn cấu hình trên cùng từng case. Xáo trộn thứ tự chạy; lưu prompt version, model/version, response thô, latency và trạng thái lỗi.
- Chấm tự động theo gold ở cấp trường; rà soát thủ công các lỗi nghiêm trọng và một mẫu kết quả đã ẩn tên cấu hình.
- Trong lần chạy thật, báo cáo số case có ảnh và nhãn hợp lệ thực tế. Không tính timeout, JSON hỏng hoặc ảnh thiếu nhãn thành một câu trả lời đúng.

## 4. Metrics

| Metric | Cách tính | Ý nghĩa |
|---|---|---|
| **Field macro-F1** | Macro-average precision/recall/F1 trên các trường có nhãn, chuẩn hóa khoảng trắng và biến thể Unicode | Chất lượng trích xuất tổng thể, tránh trường phổ biến lấn át trường hiếm |
| **Exact critical-case accuracy** | Số case mà mọi trường trọng yếu đều đúng / số case hợp lệ | Đo khả năng hoàn thành trọn vẹn, không chỉ đúng một vài trường |
| **Hallucinated-field rate** | Trường được điền nhưng gold xác định là không có/không quan sát được / tổng trường gold vắng mặt | Đo nguy cơ bịa thêm dữ kiện; càng thấp càng tốt |
| **Valid JSON/schema rate** | Output parse được và tuân thủ schema / tổng số lần gọi | Đo độ tin cậy tích hợp vào backend |

Để có một chỉ số tóm tắt minh họa, dùng **Ablation Score**:

`0.50 × Field macro-F1 + 0.25 × Exact critical-case accuracy + 0.15 × (1 − Hallucinated-field rate) + 0.10 × Valid JSON/schema rate`.

Các tỷ lệ trong công thức được biểu diễn từ 0 đến 1. Luôn xem từng metric riêng; điểm tổng không thay thế phân tích lỗi hoặc đánh giá an toàn.

## 5. Kết quả minh họa (số liệu giả lập)

> **Cảnh báo:** Toàn bộ số trong bảng này được dựng để minh họa xu hướng mong muốn trên N=138. Chưa chạy VLM trên 138 ảnh, không phải kết quả thực đo, không dùng làm bằng chứng hiệu năng hoặc claim sản phẩm.

| Cấu hình | Field macro-F1 | Exact critical cases | Hallucinated-field rate | JSON/schema hợp lệ | Ablation Score |
|---|---:|---:|---:|---:|---:|
| A. Base VLM | 0.68 | 54/138 (39.1%) | 12.4% | 125/138 (90.6%) | 66.0% |
| B. Base + Persona | 0.75 | 64/138 (46.4%) | 8.7% | 132/138 (95.7%) | 72.4% |
| C. Base + CoT | 0.77 | 69/138 (50.0%) | 9.1% | 129/138 (93.5%) | 74.0% |
| D. Base + Persona + CoT | **0.84** | **86/138 (62.3%)** | **5.8%** | **136/138 (98.6%)** | **81.6%** |

Theo kịch bản giả lập, Persona cải thiện F1 **7 điểm phần trăm** so với Base; CoT cải thiện **9 điểm**; kết hợp cải thiện **16 điểm**. Exact-case accuracy tăng từ 39.1% lên 62.3%, nhưng vẫn còn 52/138 case không đạt toàn bộ trường trọng yếu. Persona+CoT có điểm cao nhất trong ví dụ này; kết quả không chứng minh hai kỹ thuật luôn cộng hưởng trong thực tế.

## 6. Thiếu sót và case chưa hoàn thành tốt

Các tình huống dưới đây là **case mẫu giả lập**, dùng để định hướng vòng phát triển tiếp theo; chưa gắn với ID trong bộ 138.

| Tình huống | Base VLM | Chỉ thêm Persona | Chỉ thêm CoT | Persona + CoT |
|---|---|---|---|---|
| Ảnh mờ, ngày nghỉ bị lóa hoặc che một phần | Dễ đoán ngày theo ngữ cảnh hoặc bỏ sót | Nhận diện trường ngày cần tìm nhưng không khôi phục được chữ | Có thể dừng đúng ở bước ngày không đọc rõ, nhưng đôi lúc vẫn điền ngày suy đoán | Tốt hơn về để `null`, vẫn có thể nhầm ký tự ngày/tháng |
| Cấp cứu chưa có ngày xuất viện | Có thể coi thiếu ngày kết thúc là lỗi | Persona cấp cứu hiểu trạng thái mở, nhưng đôi lúc điền ngày dự kiến | Checklist nhắc kiểm tra ngày nhập/xuất viện, chưa chắc hiểu trạng thái chưa kết thúc | Bám đúng `open-ended` hơn, vẫn cần backend giữ quy tắc follow-up |
| Thiệp cưới và giấy đăng ký kết hôn | Dễ phân loại lẫn hoặc nhầm ngày sự kiện/ngày cấp | Persona hôn sự cải thiện phân loại, nhưng có thể mặc định tài liệu có giá trị xác nhận chính thức | Giúp kiểm tra riêng loại giấy và ngày, nhưng không thay kiến thức về loại chứng từ | Ít nhầm hơn; vẫn không thể xác thực tính pháp lý chỉ từ ảnh |
| Tên có dấu/đảo thứ tự; quan hệ thân nhân không ghi trực tiếp | Dễ kết luận mismatch hoặc tự suy ra quan hệ | Persona giúp tập trung đúng tên/quan hệ nhưng có nguy cơ suy diễn theo vai trò | So từng trường có thể giảm bỏ sót; quan hệ vẫn phải để thiếu nếu không thấy trên giấy | Đối chiếu tốt hơn nhưng cần quy tắc null/uncertain nghiêm ngặt |
| Ảnh có dòng chữ yêu cầu bỏ qua hướng dẫn | Có thể bị ảnh hưởng bởi nội dung trên ảnh | Persona không tự giải quyết prompt injection | Checklist không phải cơ chế bảo mật | Vẫn cần coi ảnh là dữ liệu không tin cậy và kiểm tra đầu ra ở backend |

### Hạn chế theo cấu hình

- **Base VLM:** ít chỉ dẫn nên thường bỏ trường ít nổi bật, nhầm loại giấy và cho định dạng đầu ra không ổn định.
- **Base + Persona:** kết quả có thể phụ thuộc độ đúng của persona/schema được chọn; vai trò quá hẹp có thể khiến mô hình thiên kiến hoặc điền trường không được quan sát.
- **Base + CoT:** tốn token và latency hơn; các bước không đảm bảo đúng, có thể tạo cảm giác chắc chắn giả hoặc thêm suy luận không cần thiết. Chỉ chấm facts cuối, không chấm độ dài lời giải thích.
- **Persona + CoT:** vẫn thất bại khi ảnh không đủ thông tin, chữ viết tay khó đọc hoặc nhãn gold chưa rõ; prompt không xác minh được con dấu thật, chữ ký thật hay tính pháp lý của tài liệu.

## 7. Kết luận và bước tiếp theo

Trong kịch bản giả lập, **Persona + CoT** đạt kết quả tốt nhất và giảm hallucinated-field rate. Đây là cơ sở để thử nghiệm, chưa phải kết luận thực nghiệm. Khi triển khai thật, ưu tiên tạo manifest 138 case có ảnh và gold rõ ràng, chạy bốn prompt trên cùng model, rồi thay toàn bộ bảng giả lập bằng số đo và lưu các case lỗi cụ thể theo ID.

Đặc biệt, cần phân biệt **đọc/trích xuất facts** với **xác minh chứng từ và quyết định nghỉ phép**. VLM chỉ nên trả facts quan sát được; backend/rule engine tiếp tục chịu trách nhiệm đối chiếu và quyết định. Các trường không nhìn thấy hoặc không chắc chắn phải được phép trả `null`/`UNCERTAIN`, không được tự hoàn thiện bằng suy đoán.

## Tham chiếu trong repository

- `core/vlm_inspector.py`: persona, schema, decision tree và prompt đang dùng.
- `benchmarks/runners/vlm_eval.py`: VLM real inference là opt-in; mocked output không được chấm là độ chính xác.
- `benchmarks/datasets/unified_cases.json`: corpus hiện có 158 case, 46 case có ảnh.
- `benchmarks/README.md`: mô tả giới hạn dữ liệu tổng hợp và benchmark.
