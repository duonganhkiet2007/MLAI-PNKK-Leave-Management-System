<div align="center">
<h1>The Escalation Referee — Hệ Thống AI Phê Duyệt Nghỉ Phép Doanh Nghiệp 
</div>
<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Qwen 2.5-VL](https://img.shields.io/badge/VLM-Qwen_2.5--VL-7928CA?style=for-the-badge&logo=openai&logoColor=white)](https://github.com/QwenLM/Qwen2.5-VL)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)




**Link video demo: https://youtu.be/FjoYJwa732c**

**Link kiểm thử hệ thống: https://pnkk-uit.lol/**

**Link dataset:** [dataset google sheets](https://docs.google.com/spreadsheets/d/1_d9vUImx0TX7yeGoFwtnWIQRDaDFpi_XKqALEeNs1KA/edit?usp=sharing)

**Link báo cáo tổng hợp:** [báo cáo tổng hợp](https://docs.google.com/document/d/1IUXfhizn1Xjo514ArIZ5kM0WyxalhPdWRSEZG86i3WI/edit?tab=t.0)




</div>

## 1. Tổng quan

Phê duyệt nghỉ phép là một quy trình lặp lại nhưng không hề đơn giản: mỗi đơn đòi hỏi đối chiếu đồng thời lịch làm việc, số dư phép, chứng từ, tỷ lệ vắng mặt và thẩm quyền phê duyệt. Dù được hỗ trợ bởi tự động hóa, quyền quyết định cuối cùng vẫn phải thuộc về đúng người có thẩm quyền.

Hệ thống hướng tới một cơ chế phân xử giúp giảm tải các ca thường quy mà không bỏ qua các điều kiện rủi ro thật — tránh đồng thời hai thất bại kinh điển của tự động hóa nhân sự: **duyệt mù** và **chuyển tiếp thừa**.

![Tổng quan hệ thống](docs/report/Screenshot%202026-09-22%20195205.png)

## 2. Kiến trúc hệ thống

![Luồng hoạt động chính](docs/report/6168185353823522853.jpg)

### 2.1. Tầng Backend

FastAPI, dựng app, đăng ký CORS, router, phục vụ frontend tĩnh, và làm nóng (warm-up) mô hình AI ngay lúc khởi động.

![Giao diện](docs/report/Screenshot%202026-09-22%20224316.png)

Bộ điều phối: nạp ngữ cảnh tin cậy từ DB → đọc facts (từ form hoặc gọi LLM nếu là văn bản tự do) → gọi VLM nếu có chứng từ → gọi rule engine → cập nhật trạng thái → lưu decision/giải trình/điều khoản chính sách → ghi audit.

### 2.2. Tầng Frontend

Trang tĩnh HTML/JavaScript thuần túy và không sử dụng framework.

| **File** | **Nội dung** |
|---|---|
| `index.html` | Bố cục: nav, form, hàng đợi người duyệt, trang chính sách, khu kiểm thử |
| `app.js` | Gọi API, nhãn vai trò/quyết định, khởi tạo tab, render danh sách đơn, submit form |
| `styles.css` | Giao diện, bảng, thẻ hiển thị |

Bốn chế độ dùng chung giao diện: cổng nhân viên, cổng người duyệt, trang chính sách, khu kiểm thử. Không gọi AI trực tiếp — mọi tương tác đều đi qua API backend.

### 2.3. Mô hình ngôn ngữ LLM

Sau khi Decision Tree kiểm tra đơn nghỉ, hệ thống đã có kết quả rõ ràng như tự động duyệt, từ chối, cần bổ sung thông tin hoặc chuyển cho người quản lý

Ở bước này, LLM không được quyết định lại kết quả mà chỉ làm nhiệm vụ tóm tắt kết quả và giải thích cho người dùng hoặc người quản lý dễ hiểu hơn.


**Persona & Prompt hệ thống**

Prompt hệ thống ràng buộc rất chặt, và nguyên văn logic:

> *"Prompt hệ thống: Vai trò của bạn là Trợ lý tổng hợp kết quả xử lý đơn nghỉ phép. Dựa hoàn toàn vào dữ liệu đầu vào (thông tin đơn, kết quả Decision Tree, và dữ liệu chứng từ), hãy tạo ra một bản tóm tắt ngắn gọn, dễ hiểu để trình bày cho nhân viên hoặc cấp quản lý.
"*


### 2.4. Mô hình thị giác (VLM) 

VLM nó chỉ đọc chứng từ hình ảnh và trích xuất facts khách quan có trên giấy, tuyệt đối không tự đưa ra phán xét về tính hợp lệ.

**Persona theo loại chứng từ**

Kỹ thuật phân vai của VLM là: gán một **persona chuyên biệt** phù hợp với loại chứng từ đang xử lý, áp fixed rule chống bịa dữ liệu, và bắt buộc output theo đúng schema JSON. Ba persona điển hình:

| **Loại chứng từ** | **Persona / Prompt hệ thống** |
|---|---|
| Hồ sơ y tế | "Bạn là chuyên gia kiểm tra hồ sơ y tế. Chỉ đọc thông tin trực tiếp có trên chứng từ, không suy diễn, không bịa dữ liệu. Nếu tên trên giấy không rõ, trả null. Nếu giấy mờ, đánh dấu `document_readability = UNREADABLE`. Không tự xác nhận chứng từ hợp lệ hay không hợp lệ. Chỉ trả về JSON theo schema đã định nghĩa." |
| Hồ sơ thai sản | "Bạn là chuyên gia kiểm tra hồ sơ thai sản. Chỉ xuất các trường hiện có trên giấy: tên bệnh nhân, nơi cấp, ngày cấp, chẩn đoán, khoảng thời gian chỉ định. Không suy luận về chính sách. Không tự quyết định phê duyệt. Trả JSON theo schema chuẩn." |
| Sự kiện gia đình | "Bạn là chuyên gia xác minh hồ sơ sự kiện gia đình. Chỉ trích xuất thông tin hình ảnh quan sát được: tên, quan hệ, thời gian, nơi tổ chức, chữ ký, dấu đỏ. Nếu thông tin thiếu hoặc mờ, trả null. Không thêm nhận định ngoài phạm vi giấy tờ." |

**Đầu vào:**

Đầu vào của VLM là file/ảnh chứng từ kèm metadata của đơn nghỉ liên quan:

```json
{
  "file": "/uploads/proof_123.jpg",
  "leave_type": "SICK_MEDICAL",
  "employee_name": "Nguyen Van A",
  "from_date": "2026-09-20",
  "to_date": "2026-09-21",
  "reason": "Đau bụng, cần nghỉ điều trị",
  "proof_type_hint": "MEDICAL_LEAVE_CERTIFICATE",
  "document_readability": "READABLE"
}
```

**Đầu ra**, gồm các fact đọc được trên giấy, cùng điểm đối chiếu với đơn xin nghỉ:

```json
{
  "patient_name_on_doc": "Nguyễn Văn A",
  "diagnosis": "Viêm ruột thừa",
  "issuer": "Bệnh viện Đa khoa X",
  "issue_date": "2026-09-19",
  "recommended_from_date": "2026-09-20",
  "recommended_to_date": "2026-09-21",
  "has_red_stamp": true,
  "has_doctor_signature": true,
  "document_readability": "READABLE",
  "is_tampered": false,
  "correlation_score": 0.92,
  "proof_type": "MEDICAL_LEAVE_CERTIFICATE",
  "correlation_issues": [],
  "raw_fields_detected": {
    "clinic_name": "Bệnh viện Đa khoa X",
    "doctor_name": "BS. Lê Hùng",
    "diagnosis_code": "K80",
    "prescribed_days": 2
  }
}
```

### 2.5. Cây quyết định (Decision Tree / Rule Engine)

Đây là nơi ra quyết định cuối cùng, nhận dữ liệu ghép từ ba nguồn: facts chứng từ từ VLM, và ngữ cảnh tin cậy từ cơ sở dữ liệu (số dư phép, lịch làm việc, các ngày nghỉ đã duyệt, người bàn giao, trạng thái nhân viên), cộng thêm định danh của người đang thao tác.

**Trình tự đánh giá gồm ba bước:**

1. **Kiểm tra đầu vào** — thiếu ngày, sai định dạng, thiếu loại nghỉ, thiếu lý do → cần sửa.
2. **Tuân thủ chính sách** — thiếu chứng từ → cần sửa/chuyển tiếp; vượt số dư → từ chối; chồng lấn ngày → từ chối; chứng từ mờ → chuyển tiếp; vi phạm báo trước → chuyển tiếp; vượt quota → chuyển tiếp/cảnh báo.
3. **Định tuyến theo thẩm quyền** — đủ điều kiện và nhỏ → tự động duyệt; lớn/phức tạp/vượt ngưỡng → chuyển tiếp đến Department Head hoặc CEO.


![Giao diện](docs/report/1790147054592_4749324530369031024_4749324530369031024_918bcfe1194de52ccc8764016ece0b5d.jpg)


Ví dụ output khi cần chuyển tiếp:

```json
{
  "decision": "ESCALATE",
  "target_role": "DEPARTMENT_HEAD",
  "uncertainty_category": "AUTHORITY_ESCALATION",
  "error_code": "DURATION_OVER_AI_LIMIT",
  "human_readable_explanation": "Đơn nghỉ vượt mức tự duyệt cần xem xét bởi Department Head.",
  "actionable_question": "Bạn có đồng ý cho phép đơn này không?",
  "quick_action_options": ["APPROVE", "REJECT", "REQUEST_MORE_INFO"]
}
```


## 3. Giao diện

### Giao Diện 3 Chế Độ

Hệ thống cung cấp thanh chuyển đổi nhanh giữa 3 đối tượng người dùng:


**TEST**: Đánh giá & demo, khởi chạy Verify tự động 5 ca chuẩn; tra cứu kho dữ liệu 38 kịch bản

![Giao diện](docs/report/Screenshot%202026-09-22%20222018.png)

**MANAGER**: Escalation Inbox nhận ca ngoại lệ kèm Actionable Question, phê duyệt 1-chạm; xem nhật ký AI tự duyệt và tổng số hồ sơ submit

![Giao diện](docs/report/Screenshot%202026-09-22%20221958.png)


**STAFF**: Nộp đơn có tính ngày tự động, chọn nhân sự bàn giao, đính kèm chứng từ, theo dõi số dư phép tồn và lịch vắng mặt phòng ban



![Giao diện](docs/report/Screenshot%202026-09-22%20221850.png)


## 4. Cấu trúc dự án

```
MLAI/
├── backend/                      # Backend API Server (FastAPI + SQLite)
│   ├── main.py                   # Cấu hình FastAPI, static mount, CORS
│   ├── database.py               # Khởi tạo SQLite schema & ORM
│   ├── run_server.sh             # Script khởi động nhanh server
│   ├── routers/                  # API endpoints: leave, verify, meta
│   └── services/orchestration.py # Điều phối tương tác giữa Rule Engine, VLM & LLM
├── frontend/                     # Single Page Application (SPA)
│   ├── index.html                # Giao diện chính (Test, Staff, Manager)
│   ├── app.js                    # Xử lý logic nghiệp vụ, gọi API, quản lý Modal
│   ├── styles.css                # Thiết kế giao diện hiện đại, responsive
│   └── assets/proofs/            # Bộ chứng từ mẫu thực tế (y tế, kết hôn...)
├── Leave_Application/             # Bộ máy Quy chế Tất định (Deterministic Engine)
│   ├── policy_rules.md           # Bản quy chế nội bộ (Single Source of Truth)
│   ├── rule_engine.py            # Bộ quy tắc 7 bước thẩm định
│   └── vlm_inspector.py          # Module tích hợp Vision-Language Model
├── LLM-KIET/                      # Tác tử LLM (Agent Orchestrator)
│   ├── agent_orchestrator.py     # Suy luận ngữ cảnh tự nhiên, sinh câu hỏi tham vấn
│   └── prompts.py                # Prompts tối ưu hóa cho Qwen 2.5
└── tests/                         # Kịch bản kiểm thử tự động e2e & benchmark
```


## 5. Cài đặt và khởi chạy

Hệ thống được kiến trúc theo mô hình monolith hiện đại: Backend xử lý logic bằng **FastAPI**, đồng thời đảm nhận việc mount và phục vụ trực tiếp Frontend (Vanilla JS/HTML/CSS) để tối ưu hóa quá trình triển khai.

**Bước 1: Sao chép mã nguồn**

Đưa dự án về máy tính cục bộ của bạn bằng Git:

```bash
git clone https://github.com/duonganhkiet2007/MLAI-PNKK-Leave-Management-System.git
cd MLAI
```

**Bước 2: Cài đặt thư viện phụ thuộc**

Cài đặt toàn bộ các thư viện cần thiết đã được định nghĩa sẵn trong hệ thống:

```bash
pip install -r requirements.txt
```

**Bước 3: Khởi chạy Server**

Di chuyển vào thư mục lõi của hệ thống (backend) và khởi động API Server.

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---



