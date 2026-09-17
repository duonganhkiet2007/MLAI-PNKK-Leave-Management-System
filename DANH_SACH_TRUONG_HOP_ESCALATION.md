# DANH MỤC TOÀN BỘ CÁC TRƯỜNG HỢP PHẢI ĐƯA RA CHO CON NGƯỜI (HUMAN ESCALATION)
## THE ESCALATION REFEREE — HỆ THỐNG ĐIỀU PHỐI PHÊ DUYỆT NGHỈ PHÉP AI (TRACK A)

> **Mã tài liệu:** TAXONOMY-ESCALATION-2026  
> **Căn cứ pháp lý & quy chế:** `Leave_Application/policy_rules.md` (POL-HR-2026-01) & `Leave_Application/taxonomy.py`  
> **Kiến trúc vận hành:** Local LLM Qwen 2.5 7B Instruct (In-Process trên GPU RTX 4090, duy nhất 1 Port 8000, 100% AI thực thi không fallback).  
> **Nguyên tắc an toàn (Guardrail):** Hệ thống AI chỉ được tự động duyệt (`AUTO_APPROVE`) khi đơn thỏa mãn đồng thời 100% điều kiện an toàn. **Tất cả các trường hợp còn lại bắt buộc phải chuyển tiếp (`ESCALATE`) cho con người.**

---

## I. ĐIỀU KIỆN ĐỐI CHIẾU: KHI NÀO AI ĐƯỢC PHÉP TỰ DUYỆT?

Hệ thống AI (Tier 0) chỉ tự động phê duyệt khi **thỏa mãn đồng thời tất cả 6 điều kiện** sau:
1. **Thời lượng:** Nghỉ phép năm $\le 02$ ngày làm việc (hoặc nghỉ ốm $01$ ngày).
2. **Quỹ phép:** Số dư phép năm hiện có đủ để chi trả (`workdays <= remaining_leave_days`).
3. **Thời hạn báo trước:** Nộp đơn trước ca làm việc tối thiểu **24 giờ** (nghỉ ốm nộp trước **08:30 sáng** ngày nghỉ).
4. **Hạn mức vận hành:** Tỷ lệ vắng mặt trong ngày của bộ phận $\le 30\%$ tổng quân số.
5. **Chứng từ:** Có đầy đủ chứng từ hợp lệ (nếu là nghỉ ốm $\ge 2$ ngày phải có Giấy chứng nhận BHXH).
6. **Tính minh bạch dữ liệu:** Thông tin ngày tháng rõ ràng, lý do chính đáng, không có dấu hiệu vi phạm kỷ luật lao động.

> ⚠️ **Bất kỳ vi phạm hoặc sự không chắc chắn nào ngoài 6 điều kiện trên đều kích hoạt cơ chế chuyển tiếp (Escalation).**

---

## II. MA TRẬN 18 TRƯỜNG HỢP BẮT BUỘC CHUYỂN TIẾP CHO CON NGƯỜI

Hệ thống phân loại toàn bộ các trường hợp chuyển tiếp vào **3 nhóm mức độ không chắc chắn (Uncertainty Categories)** với **4 cấp thẩm quyền phê duyệt đích (Target Approver Roles)**.

```
                                  ┌─────────────────────────────┐
                                  │      YÊU CẦU NGHỈ PHÉP      │
                                  └──────────────┬──────────────┘
                                                 │
                                                 ▼
                                  ┌─────────────────────────────┐
                                  │  CÓ VẤN ĐỀ / CẦN XÉT DUYỆT  │
                                  └──────────────┬──────────────┘
                                                 │
            ┌────────────────────────────────────┼────────────────────────────────────┐
            ▼                                    ▼                                    ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐    ┌─────────────────────────────┐
│    1. UNCERTAIN_FACTS       │    │      2. OUT_OF_POLICY       │    │  3. AUTHORITY_ESCALATION    │
│  (Chưa rõ sự thật / Mơ hồ)  │    │  (Vi phạm quy định công ty) │    │  (Vượt thẩm quyền của AI)   │
│  • Cần xác minh chứng từ    │    │  • Cần xem xét ngoại lệ     │    │  • Đơn hợp lệ nhưng dài hạn │
│  • Cần làm rõ dữ liệu       │    │  • Cần quyết định đặc cách  │    │  • Cần Quản lý / HRD duyệt  │
└───────────┬─────────────────┘    └─────────────┬───────────────┘    └─────────────┬───────────────┘
            │                                    │                                  │
            ▼                                    ▼                                  ▼
      HR Operations /                     Trưởng phòng /                     Trưởng phòng /
      Trưởng phòng                        HR Operations                      HRD / Ban Giám đốc
```

---

### NHÓM 1: `UNCERTAIN_FACTS` — DỮ LIỆU CHƯA RÕ RÀNG / THIẾU SÓT / LÝ DO BẤT HỢP LỆ
*Áp dụng khi dữ liệu đầu vào bị thiếu, mờ, mâu thuẫn, hoặc lý do xin nghỉ không hợp lệ / vi phạm chuẩn mực lao động.*

| STT | Mã lỗi (Error Code) | Tên tình huống cụ thể | Mô tả chi tiết & Căn cứ quy chế | Cấp thẩm quyền xử lý | Câu hỏi hành động mẫu (Qwen 7B sinh tự động) |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | `AMBIGUOUS_REQUEST` | **Dữ liệu đơn mơ hồ, thiếu ngày cụ thể** | Nhân viên gửi đơn qua chat dùng từ ngữ mơ hồ (*"cho em nghỉ vài hôm"*, *"ít ngày nữa em đi làm lại"*). Hệ thống tuyệt đối không đoán mò ngày tháng. | **HR Operations / Quản lý** | *\"Đơn của nhân viên chưa xác định được ngày bắt đầu và kết thúc cụ thể. Nhân sự có yêu cầu nhân viên nộp lại đơn kèm lịch nghỉ chuẩn xác không?\"* |
| **2** | `DOC_ILLEGIBLE` | **Lý do bất hợp lệ / Vi phạm kỷ luật** | Nhân viên xin nghỉ với lý do không chính đáng (*"lười biếng"*, *"không thích đi làm"*, *"thích thì nghỉ"*, *"chán đi làm"*). Guardrail của Agent bắt cờ `is_ambiguous=True`. | **Trưởng bộ phận (Manager)** | *\"Nhân viên nộp đơn với lý do 'nghỉ vì lười biếng không thích làm việc nữa' không có căn cứ chính đáng. Quản lý có yêu cầu giải trình lý do hợp lệ hoặc từ chối đơn không?\"* |
| **3** | `DATE_LOGIC_INVALID` | **Nghịch lý logic ngày tháng** | Ngày kết thúc trước ngày bắt đầu (`from_date > to_date`), hoặc số ngày làm việc tính ra $\le 0$ (ví dụ: xin nghỉ rơi trúng Thứ Bảy & Chủ Nhật). | **Trưởng bộ phận (Manager)** | *\"Đơn có ngày kết thúc trước ngày bắt đầu (hoặc 0 ngày làm việc). Quản lý có từ chối để nhân sự cập nhật lại lịch nghỉ chính xác không?\"* |
| **4** | `DOC_ILLEGIBLE` | **Chứng từ y tế mờ / Không đúng mẫu BHXH** | Nghỉ ốm $\ge 2$ ngày nhưng chỉ đính kèm toa thuốc/phiếu khám thông thường; hoặc ảnh chụp Giấy chứng nhận nghỉ BHXH bị mờ, mất góc, thiếu mộc đỏ cơ sở y tế. | **Trưởng bộ phận / HR Ops** | *\"Nhân sự xin nghỉ ốm 3 ngày nhưng chứng từ chưa đạt chuẩn mẫu BHXH. Quản lý yêu cầu bổ sung giấy nghỉ đúng mẫu hay đồng ý chuyển sang trừ phép năm?\"* |
| **5** | `DOC_SUSPICIOUS` | **Nghi vấn chỉnh sửa chứng từ** | Ảnh chứng từ có dấu hiệu can thiệp photoshop, chỉnh sửa con số ngày tháng, hoặc trùng lặp mã hồ sơ bệnh án cũ. | **Chuyên viên Nhân sự (HR Ops)** | *\"Phát hiện chứng từ có dấu hiệu bất thường về số liệu. Chuyên viên C&B có yêu cầu nhân viên xuất trình bản gốc giấy khám để đối soát không?\"* |
| **6** | `HANDOVER_INVALID` | **Người bàn giao không hợp lệ** | Đơn nghỉ $\ge 3$ ngày nhưng không ghi người bàn giao, hoặc người nhận bàn giao đã nghỉ việc, không thuộc cùng phòng ban, hoặc trùng với người làm đơn. | **Trưởng bộ phận (Manager)** | *\"Đơn nghỉ 4 ngày nhưng nhân sự bàn giao không hợp lệ. Trưởng phòng có yêu cầu nhân sự chỉ định lại người backup trước khi duyệt không?\"* |
| **7** | `HANDOVER_CIRCULAR_LOOP` | **Vòng lặp bàn giao chéo** | Nhân sự A làm đơn chỉ định bàn giao cho B, nhưng B cũng nộp đơn xin nghỉ trùng khoảng thời gian đó và chỉ định ngược lại cho A. | **Trưởng bộ phận (Manager)** | *\"Phát hiện nhân sự A và B cùng vắng mặt và chỉ định bàn giao chéo cho nhau. Trưởng phòng có yêu cầu phân công lại người trực thay không?\"* |
| **8** | `MEDICAL_DAYS_MISMATCH` | **Lệch số ngày chỉ định y khoa** | Giấy chứng nhận nghỉ việc hưởng BHXH bác sĩ chỉ định nghỉ 2 ngày, nhưng nhân viên nộp đơn xin nghỉ ốm 4 ngày. | **Trưởng bộ phận / HR Ops** | *\"Bác sĩ chỉ định nghỉ 2 ngày nhưng nhân sự xin nghỉ 4 ngày. Quản lý có đồng ý duyệt 2 ngày ốm, 2 ngày còn lại chuyển thành phép năm không?\"* |

---

### NHÓM 2: `OUT_OF_POLICY` — VI PHẠM QUY ĐỊNH & HẠN MỨC QUY CHẾ
*Áp dụng khi dữ liệu rất minh bạch, đầy đủ nhưng vi phạm chính sách công ty. Cần con người xem xét tính cấp thiết để phê duyệt đặc cách (Override) hoặc từ chối.*

| STT | Mã lỗi (Error Code) | Tên tình huống cụ thể | Mô tả chi tiết & Căn cứ quy chế | Cấp thẩm quyền xử lý | Câu hỏi hành động mẫu |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **9** | `NOTICE_PERIOD_VIOLATED` | **Vi phạm thời hạn nộp trước** | • Nghỉ $\le 2$ ngày nhưng nộp gấp (dưới 24h).<br>• Nghỉ 3-5 ngày nhưng nộp dưới 3 ngày làm việc.<br>• Nghỉ ốm đột xuất nộp sau **08:30 sáng** của ca làm việc đầu tiên. | **Trưởng bộ phận (Manager)** | *\"Nhân sự nộp đơn xin nghỉ gấp vi phạm quy định báo trước 24 giờ. Trưởng phòng có xem xét phê duyệt ngoại lệ do lý do khẩn cấp không?\"* |
| **10** | `BALANCE_EXCEEDED` | **Vượt / Hết quỹ ngày phép năm** | Số ngày xin nghỉ nhiều hơn số dư phép năm hiện có (`workdays > remaining_leave_days`). Cần quyết định cho nợ phép, trừ vào nghỉ không lương hay từ chối. | **Trưởng bộ phận (Manager)** | *\"Nhân sự xin nghỉ 3 ngày nhưng chỉ còn 1 ngày phép năm. Quản lý có đồng ý trừ hết 1 ngày phép và chuyển 2 ngày dôi ra thành Nghỉ không lương không?\"* |
| **11** | `TEAM_QUOTA_EXCEEDED` | **Vượt hạn mức vắng mặt phòng ban (> 30%)** | Số nhân sự vắng mặt trong ngày của phòng ban vượt quá **30% tổng quân số**. Nguy cơ gây tê liệt hoặc gián đoạn hoạt động kinh doanh/vận hành. | **Trưởng bộ phận (Manager)** | *\"Ngày 20/09 phòng đã có 3/8 người nghỉ (tỷ lệ 50% > 30%). Trưởng phòng có chấp thuận cho nghỉ trùng lịch hay yêu cầu nhân sự dời ngày?\"* |
| **12** | `UNQUALIFIED_SPECIAL_LEAVE` | **Nghỉ việc riêng có lương sai luật** | Xin nghỉ việc riêng hưởng nguyên lương nhưng lý do không thuộc Điều 115 Bộ luật Lao động 2019 (ví dụ: đám cưới bạn bè, giỗ họ, người thân xa mất). | **Chuyên viên HR / Manager** | *\"Lý do nghỉ việc riêng không thuộc diện hưởng nguyên lương theo Điều 115 BLLĐ. Nhân sự có đồng ý chuyển đơn sang trừ phép năm không?\"* |
| **13** | `CONSECUTIVE_SPLIT_DETECTED` | **Lách luật chia nhỏ đơn liên tiếp (Salami slicing)** | Nộp liên tục 2 đến 3 đơn nghỉ 1-2 ngày sát nhau nhằm lách trần tự duyệt 2 ngày của hệ thống và né yêu cầu chỉ định người bàn giao. | **Trưởng bộ phận (Manager)** | *\"Phát hiện nhân sự chia nhỏ nhiều đơn nghỉ 2 ngày liên tiếp. Trưởng phòng có yêu cầu gom thành đợt nghỉ dài ngày và bổ sung người bàn giao không?\"* |
| **14** | `CLUSTER_ABSENCE_ANOMALY` | **Bất thường vắng mặt tập thể** | Nhiều nhân sự trong cùng một nhóm/dự án nộp đơn xin nghỉ sát giờ cùng thời điểm, có dấu hiệu bất thường về tổ chức hoặc đình công ngầm. | **Giám đốc Nhân sự (HRD)** | *\"Phát hiện 5 nhân sự thuộc cùng tổ dự án nộp đơn nghỉ đồng loạt. Giám đốc Nhân sự có yêu cầu tạm hoãn các đơn để rà soát vận hành không?\"* |

---

### NHÓM 3: `AUTHORITY_ESCALATION` — VƯỢT THẨM QUYỀN TỰ DUYỆT CỦA AI
*Áp dụng khi hồ sơ **hoàn toàn hợp lệ 100%**, có người bàn giao, đủ phép, nộp sớm nhưng quy mô/thời lượng vượt quá giới hạn ủy quyền của hệ thống tự động Tier 0.*

| STT | Mã lỗi (Error Code) | Tên tình huống cụ thể | Mô tả chi tiết & Căn cứ quy chế | Cấp thẩm quyền xử lý | Câu hỏi hành động mẫu |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **15** | `DURATION_OVER_AI_LIMIT` | **Nghỉ phép năm từ 3 đến 5 ngày làm việc** | Đơn hợp lệ, đã có người nhận bàn giao công việc nhưng thời lượng từ 3 đến 5 ngày (vượt trần tự duyệt 2 ngày của AI). Thuộc thẩm quyền Trưởng phòng. | **Trưởng bộ phận (Manager)** | *\"Nhân sự xin nghỉ 4 ngày làm việc, hồ sơ đầy đủ hợp lệ và đã bàn giao công việc cho bạn B. Trưởng phòng có phê duyệt đợt nghỉ này không?\"* |
| **16** | `DURATION_OVER_MANAGER_LIMIT` | **Nghỉ dài hạn trên 5 ngày liên tục** | Đơn nghỉ phép năm dài hạn $> 5$ ngày làm việc. Vượt quá trần thẩm quyền phê duyệt của Trưởng phòng $\rightarrow$ Phải lên cấp Giám đốc khối / HRD. | **Giám đốc Khối / HRD** | *\"Nhân sự xin nghỉ phép năm dài hạn 8 ngày làm việc liên tiếp. Trưởng phòng đã đồng thuận, Giám đốc Khối có phê duyệt chính thức không?\"* |
| **17** | `LONG_TERM_UNPAID` | **Nghỉ việc riêng không lương dài hạn** | Đơn xin nghỉ việc riêng không hưởng lương kéo dài $> 14$ ngày làm việc. Ảnh hưởng tới việc đóng BHXH và hợp đồng lao động. | **Giám đốc Nhân sự (HRD)** | *\"Nhân sự xin nghỉ không hưởng lương 20 ngày vì việc gia đình. Giám đốc Nhân sự có đồng ý duyệt thỏa thuận tạm hoãn HĐLĐ này không?\"* |
| **18** | `MANAGER_SELF_APPROVAL` | **Trưởng phòng tự nộp đơn nghỉ** | Bản thân Trưởng bộ phận nộp đơn xin nghỉ phép $\rightarrow$ Hệ thống không để Trưởng phòng tự duyệt cho chính mình, điều phối lên cấp trên trực tiếp. | **Ban Giám đốc (Executive Board)** | *\"Trưởng bộ phận nộp đơn xin nghỉ phép 3 ngày và đã bàn giao phó bộ phận. Ban Giám đốc có phê duyệt đợt nghỉ này của Trưởng phòng không?\"* |

---

## III. MA TRẬN PHÂN QUYỀN ĐÍCH ĐẾN (TARGET APPROVER MATRIX)

Để bảo đảm câu hỏi chuyển tiếp được gửi đến **đúng người, đúng thẩm quyền**, hệ thống định tuyến tự động theo ma trận sau:

| Cấp thẩm quyền (Target Role) | Danh sách các tình huống tiếp nhận xử lý |
| :--- | :--- |
| **Chuyên viên Nhân sự / HR Ops** | • `AMBIGUOUS_REQUEST`: Dữ liệu đơn mơ hồ.<br>• `DOC_SUSPICIOUS`: Nghi vấn chứng từ y tế gian lận.<br>• `UNQUALIFIED_SPECIAL_LEAVE`: Nghỉ việc riêng hưởng lương sai luật định.<br>• `MEDICAL_DAYS_MISMATCH`: Lệch số ngày hưởng chế độ BHXH. |
| **Trưởng bộ phận (Manager)** | • `DOC_ILLEGIBLE`: Lý do nghỉ không hợp lệ / vi phạm kỷ luật.<br>• `DURATION_OVER_AI_LIMIT`: Đơn hợp lệ từ 3 đến 5 ngày làm việc.<br>• `NOTICE_PERIOD_VIOLATED`: Nộp đơn gấp / vi phạm báo trước.<br>• `BALANCE_EXCEEDED`: Hết hoặc thiếu ngày phép năm.<br>• `TEAM_QUOTA_EXCEEDED`: Vượt ngưỡng vắng mặt an toàn 30%.<br>• `HANDOVER_INVALID` & `HANDOVER_CIRCULAR_LOOP`: Vấn đề người bàn giao.<br>• `DATE_LOGIC_INVALID`: Nghịch lý ngày tháng.<br>• `CONSECUTIVE_SPLIT_DETECTED`: Chia nhỏ đơn liên tiếp. |
| **Giám đốc Nhân sự / Giám đốc Khối (HRD)** | • `DURATION_OVER_MANAGER_LIMIT`: Đơn nghỉ phép dài hạn $> 5$ ngày.<br>• `LONG_TERM_UNPAID`: Đơn nghỉ không hưởng lương $> 14$ ngày.<br>• `CLUSTER_ABSENCE_ANOMALY`: Bất thường vắng mặt tập thể cùng lúc. |
| **Ban Giám đốc (Executive Board / BOD)** | • `MANAGER_SELF_APPROVAL`: Đơn xin nghỉ phép của chính các Trưởng bộ phận / Quản lý cấp cao. |

---

## IV. CƠ CHẾ SINH CÂU HỎI & LỰA CHỌN NHANH (QUICK ACTIONS)

Khi một đơn rơi vào bất kỳ trường hợp nào trong 18 trường hợp trên, mô hình **Qwen 2.5 7B Instruct** tự động phân tích và sinh ra gói tin chuyển tiếp:

1. **Ngữ cảnh minh bạch (Transparency):** Giải thích rõ lý do dừng tự động hóa kèm trích dẫn điều khoản quy chế (ví dụ: *Điều 3.1 Quy chế POL-HR-2026-01*).
2. **Câu hỏi trực diện (Actionable Question):** Đầy đủ các biến số (Tên nhân viên, số ngày, tỷ lệ vắng mặt hiện tại, tên người bàn giao, lý do thực tế).
3. **Các nút tùy chọn nhanh (Quick Actions - 1 chạm):**
   * *Nút 1:* Phê duyệt đặc cách / Đồng ý ngoại lệ.
   * *Nút 2:* Từ chối đơn và nêu rõ yêu cầu dời lịch / cập nhật.
   * *Nút 3:* Phương án thỏa hiệp (ví dụ: Chuyển số ngày thiếu sang nghỉ không lương; hoặc yêu cầu bổ sung người trực thay).
