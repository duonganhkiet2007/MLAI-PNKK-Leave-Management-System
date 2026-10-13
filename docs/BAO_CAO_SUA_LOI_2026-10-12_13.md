# Báo cáo sửa lỗi hệ thống — 12/10 → 13/10/2026

Phạm vi: các lỗi tìm thấy khi dùng thử trang https://pnkk-uit.lol/, khi rà soát báo cáo `system_critical_bugs_summary.txt` và khi chạy kiểm thử đầu-cuối trên một bản sao server riêng (DB riêng, không đụng dữ liệu live).

- **Commit:** `6a9a3f5` trên nhánh `fix/system-bugs-and-sync` (tách từ `main`, **chưa push**).
- **Kiểm thử:** **212/212 test đạt** (2 test lỗi từ trước đã được sửa, xem mục 6). Lần kiểm thử lại toàn bộ trên bản sao server không còn lỗi JS, lỗi HTTP hay exception phía server.
- **Tab Test:** 17/38 → **35/38** kịch bản cho kết quả đúng như mong đợi khi nộp qua giao diện.
- **Lưu ý:** commit gộp cả một số thay đổi chưa commit của thành viên khác trong thư mục làm việc chung (câu thông báo mới trong `core/rule_engine.py`, `backend/migrations.py`, `tests/test_phase1_async_vlm_tx.py`, `tests/test_new_org_workflow.py`).

---

## 1. Giao diện (theo yêu cầu)

| Thay đổi | File |
|---|---|
| **Hồ sơ đơn**: đổi danh sách thẻ sang bảng (Nhân viên, Thời gian nghỉ, Số ngày, Trạng thái, Chi tiết, Quyền kiểm soát). Bỏ cột Phòng ban và Loại nghỉ. Nhãn trạng thái cùng khung với nút "Chi tiết". Thay ô tìm kiếm và 5 nút lọc bằng một ô **Filter** 5 trạng thái. | `frontend/index.html`, `app.js`, `styles.css` |
| **Modal Chi tiết đơn**: thiết kế lại thành các khung có icon và **thu gọn được**: Thông tin đơn, Thông tin trích xuất từ chứng từ, Kết quả kiểm tra. Trạng thái và rủi ro đưa lên thanh tiêu đề. Ô chứng từ chưa khớp có viền cam kèm giải thích. Bỏ tên/mã đơn dưới tiêu đề, nút "Nhật ký xử lý" và các khối lặp thông tin. Kết luận và câu hỏi cho quản lý nằm đầu khung Kết quả kiểm tra. | `app.js` (`openRequestDetailModal`), `styles.css` (`rd-*`) |
| Nội dung người dùng nhập (lý do nghỉ, người bàn giao...) được mã hóa HTML trước khi hiển thị trong modal. | `app.js` |
| **Giao diện điện thoại**: trước đây tràn ngang 588px ở bề rộng 390px. Giờ menu trái thành dải ngang cuộn được, thanh trên cùng xuống dòng, không còn tràn. | `styles.css` |
| Thông báo lỗi API hiện thành câu dễ đọc thay vì chuỗi JSON thô. | `app.js` (`formatApiError`) |

---

## 2. Đồng bộ Staff ↔ Manager

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| **Trang không chạy được** | Biến `const leaveType` bị khai báo 2 lần trong `handleStandardFormSubmit`. | Bỏ khai báo thứ hai. |
| Thẻ "Chờ xử lý" = 1 nhưng hàng đợi trống | Bộ đếm và hàng đợi dùng điều kiện khác nhau. | Dùng chung hàm `isActionablePending`. Thêm mục chỉ xem "Đang chờ cấp khác xử lý". |
| Manager duyệt xong, Hồ sơ đơn vẫn hiện "AI Tự duyệt" | Nhãn dựa vào `decision`; sau khi duyệt, `decision` vẫn là AUTO_APPROVE. | Thêm hàm `getRecordState` dùng chung cho nhãn, bộ lọc, nút Hủy Lệnh AI, thẻ thống kê và modal. Thêm nhãn "Quản lý đã duyệt / Quản lý từ chối / Chờ bàn giao / Chờ bổ sung / Bàn giao bị từ chối / Chờ Tổng Giám đốc". |
| Danh sách đơn của người này hiện sang giao diện người kia | Staff và Manager dùng chung `activeRequests`; kết quả tải về chậm vẫn được vẽ. | Nhớ danh sách thuộc người nào, bỏ kết quả cũ, luôn tải lại khi đổi người. |
| Phải tải lại trang mới thấy đơn mới | Khóa ký token **ngẫu nhiên mỗi lần server khởi động** nên mọi lần tự cập nhật bị 401 (hơn 1000 lần trong log). | Lưu khóa cố định (`data/.auth_secret`). Frontend tự xin token mới khi gặp 401. |
| Thao tác xong danh sách chưa đổi ngay | Lần tải bị bỏ qua nếu đang có lần tự cập nhật chạy dở. | Lần tải do người dùng thao tác luôn chạy. |
| Ý kiến quản lý đang gõ bị xóa | Hàng đợi bị vẽ lại 4 giây một lần. | Không vẽ lại khi dữ liệu không đổi; giữ nội dung đang gõ. |
| Số dư phép không cập nhật sau khi được cấp, bị thu hồi hoặc được duyệt | Chỉ tải lại khi danh sách đơn đổi. | Tải lại số dư khi đơn đổi trạng thái và định kỳ khoảng 12 giây. |
| Reset DB chỉ làm mới một bên | Chỉ vẽ lại chế độ đang mở. | Vẽ lại cả Staff và Manager; sửa câu xác nhận ghi sai. |
| Nộp 1 lần ra 2 đơn | Nhấn Enter lúc đơn trước chưa xử lý xong. | Chặn gửi form lần hai. |
| Nút **"Hủy Lệnh AI"** không có tác dụng | Hàm `revokeAiApproval` bị mất khỏi `app.js`. | Khôi phục hàm. |
| **Không bổ sung được đơn** khi quản lý "Yêu cầu bổ sung" | Không có nút nào gọi `correctRequest`; API `/resubmit` luôn lỗi 422 vì frontend gửi trường thừa `employee_id`. | Thêm nút **"Bổ sung"** (banner hiện lý do của người duyệt, cho tải chứng từ mới); chỉ gửi đúng các trường API nhận. |

---

## 3. Luồng duyệt và chọn người duyệt

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Đơn kẹt mãi ở **HR / Trưởng bộ phận** | Rule engine chọn vai trò mà tổ chức không có người giữ (chỉ có Lead Team và CEO). | Hàm `_route_to_staffed_roles` đi theo chuỗi thay thế: HR → Lead Team → CEO; Trưởng bộ phận / HRD → CEO. Thai sản → CEO, đúng quy chế §3.1. |
| Lead Team duyệt xong, đơn lại quay về HR | Khi đánh giá lại, hệ thống bỏ qua dữ liệu VLM nên chứng từ bị coi là chưa xác minh. | Dùng lại kết quả VLM đã lưu trên đơn (`_vlm_output_from_json`). Lead Team duyệt thì tính là đã xem chứng từ. |
| **CEO duyệt bị lặp vòng** | Rule engine vẫn đòi vai trò gốc (Trưởng bộ phận). | Người duyệt thay được tính là đã duyệt vai trò gốc. |
| **Quản lý tự nộp đơn thì kẹt** | Đơn giao cho chính họ, mà họ không được tự duyệt. | Bỏ qua chính người nộp khi chọn người duyệt, nên đơn được chuyển lên CEO kèm câu giải thích. |
| Manager không thấy đơn AI từ chối hoặc đã thu hồi của phòng mình | Quyền xem chỉ theo chuỗi người duyệt. | Lead Team xem được mọi đơn trong phòng ban mình; quyền thao tác giữ nguyên. |
| Nghỉ ốm sai thẩm quyền | 2 ngày thì AI tự duyệt, trên 5 ngày chỉ chuyển Lead Team. | Theo quy chế §3.1: 1 ngày → AI (nếu chứng từ hợp lệ); 2–5 ngày → Lead Team; trên 5 ngày → CEO. |
| Ý kiến mơ hồ bị hiểu là DUYỆT (API) | Mặc định là duyệt. | Chỉ duyệt khi có từ khóa duyệt rõ ràng và không có phủ định hay do dự; còn lại trả lỗi 422. |
| Xin nghỉ có lương để dự cưới em gái thì bị báo "chưa chọn sự kiện" | Không phân biệt sự kiện chỉ được nghỉ không lương. | Báo rõ "không thuộc diện có lương" và hướng dẫn đổi loại nghỉ. |

---

## 4. Chứng từ và VLM

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| Chứng từ sai rõ ràng (tên khác người, ngày lệch, thiếu chữ ký) bị chuyển thẳng cho quản lý | Bước "cần đối chiếu" chạy trước các bước kiểm tra cụ thể. | Báo cho nhân viên tự sửa trước, dựa trên thông tin VLM đã đọc được. |
| Phiếu cấp cứu hợp lệ bị báo "thiếu thông tin" | `EMERGENCY_ADMISSION` và `SURGERY_NOTICE` không có trong danh sách chứng từ y tế. | Thêm hai loại này; khi loại chứng từ không phù hợp thì báo đúng lý do. |
| Chữ ký "không đọc được" bị coi là "không có" | Code dùng `bool(None)`, ra `False`. | Giữ `None` (chưa rõ) khác với `False` (không có). |
| So khớp tên quá lỏng | Chỉ cần trùng chữ cuối, ví dụ "Nguyễn Văn An" = "Trần Thị An". Ngoài ra chữ "Anh" trong tên bị bỏ như một danh xưng. | Họ và tên đều phải khớp; tên đệm có thì phải khớp. Chỉ bỏ danh xưng ở đầu tên. |
| Mất tín hiệu đánh thức, đơn treo ở PROCESSING | Worker xong việc giữa lúc API đọc trạng thái và lúc lưu đơn. | Kiểm tra lại trạng thái ngay trong transaction lưu đơn. |
| Job lỗi cũ ghi đè chứng từ đã READY | Bước xử lý lỗi không so khớp version. | So version và trạng thái; job cũ được đánh dấu `SUPERSEDED`. |
| Khởi động lại thì đơn treo | Phục hồi chỉ xử lý job, không xử lý đơn. | Đánh giá lại đơn có chứng từ đã xong; xếp lại job cho chứng từ chưa xong. |
| Cache VLM khi thiếu loại nghỉ | (Mức độ thấp.) | Không đọc hay ghi cache khi thiếu loại nghỉ. |

---

## 5. Bảo mật và vận hành

| Lỗi | Cách sửa |
|---|---|
| `reset-database` và `vlm-restart` **gọi được không cần đăng nhập** (ai có URL cũng xóa được DB) | Bắt buộc đăng nhập; `vlm-restart` chỉ dành cho quản lý hoặc CEO. |
| `server-logs` lộ IP và đường dẫn nội bộ | Chỉ CEO xem được; đọc đúng file log. |
| `attachment_type="clean_hospital"` tạo được chứng từ VERIFIED giả | API bỏ qua trường này, trừ khi `APP_ENV=test`. |
| Lộ traceback, đường dẫn máy chủ, cổng Ollama ra client | Lọc thông báo lỗi ở API trạng thái chứng từ, danh sách và chi tiết đơn, `analysis`. |
| "Cấp phép" chỉ cho HRD (không ai có) | Cho phép CEO. |
| Upload chứng từ chặn event loop | Chạy trong threadpool. |
| SQLite WAL trên NFS | Tự tắt WAL khi DB nằm trên ổ mạng. `run_server.sh` lưu dữ liệu ở `~/.local/share/mlai-pnkk/data` (ổ cục bộ), có tự chép dữ liệu cũ. |
| **VLM bị gỡ khỏi GPU dẫn đến OOM** | Mỗi lần reload hoặc chạy test, server chạy `ollama stop`. Giờ chỉ gỡ khi bật `VLM_UNLOAD_ON_SHUTDOWN=1`. |
| Reset DB để sót job kiểm định và xóa file ở sai thư mục | Xóa cả bảng `proof_inspection_jobs`; dọn đúng `LEAVE_UPLOAD_DIR`. |
| Nút **Verify lỗi 500 trên DB tạo mới** | Chỉ ghi vào những cột thực sự có trong bảng. |

---

## 6. Dữ liệu và kịch bản test

| Lỗi | Cách sửa |
|---|---|
| Đơn mẫu tự nạp với **mã nhân viên sai** (ví dụ "Nguyễn Văn An" mang mã EMP012) | `SEED_DEMO_DATA` mặc định tắt. |
| Reset hoặc khởi tạo **làm mất trạng thái thử việc** | Đồng bộ các trường thử việc từ `employees.json`. |
| Đơn "AI tự duyệt" ở tab Test thành "Chờ duyệt" (ngày nghỉ đã qua) | Đơn nạp từ kịch bản dùng thời điểm nộp giả lập (`simulated_submitted_at`, chỉ ở chế độ demo). |
| 17/20 kịch bản có chứng từ **lệch ngày, tên hoặc nội dung** với ảnh mẫu; 3 mã lỗi mong đợi không tồn tại; loại sự kiện `PARENT_FUNERAL` không hợp lệ | Sửa `STAFF_TEST_CASES` cho khớp ảnh mẫu, giữ đúng ý đồ từng kịch bản. |
| 2 test VLM luôn lỗi (`test_vlm_unavailable_does_not_invent_valid_proof`, `test_tc_vlm_06_blur_gate_early_exit_no_hallucination`) | Không phải lỗi hệ thống: `conftest.py` bật `VLM_FORCE_MOCK=1` cho mọi test nên chế độ giả lập chạy trước luồng thật. Hai test này giờ tự tắt chế độ giả lập (giống TC-VLM-07). Đã xác nhận luồng thật không bịa dữ liệu khi VLM lỗi (dự phòng giả lập mặc định tắt, mọi chỗ gọi đều `allow_mock_fallback=False`). |
| Test được cập nhật theo quy chế | TC15 và test ốm 2 ngày giờ mong đợi chuyển Lead Team; bỏ trường hợp "Nam" một chữ được coi là khớp tên. Thêm `tests/test_critical_bug_fixes.py` (hồi quy). |

---

## 7. Việc còn tồn đọng / cần quyết định

1. **Nghỉ chăm con ốm** (TC-EMP012-02): giấy khám đứng tên đứa trẻ nên hệ thống báo sai tên. Rule engine chưa có chế độ này.
2. **TC-HARD-04 và TC-HARD-05** cần sẵn dữ liệu nền (lịch sử nghỉ nhiều lần, phòng ban đang đông người nghỉ), nên chỉ kiểm tra được bằng nút Verify.
3. Một số kịch bản đã đổi kết quả mong đợi theo quy chế §3.1 (ví dụ ốm 1 ngày có chứng từ hợp lệ → AI tự duyệt). Cần nhóm xác nhận cách hiểu này.
4. Demo **chưa có đăng nhập thật**: ai cũng chọn được tài khoản CEO rồi Reset DB, và mọi người dùng chung một DB.
5. README vẫn nhắc `data/server.log`. Log hiện nằm ở `~/.local/share/mlai-pnkk/data/server.log`. Thư mục `backend/data` cũ vẫn còn, làm bản sao lưu.
6. Commit `6a9a3f5` **chưa push** và chưa gộp vào `main`. Phần sửa 2 test VLM và file báo cáo này chưa được commit.
