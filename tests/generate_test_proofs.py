"""
generate_test_proofs.py
Tạo các phôi chứng từ y tế / minh chứng giả định chất lượng cao phục vụ kiểm thử và demo.
Chia đều cho 10 nhân sự nhân viên (EMP003 - EMP012), bao phủ đầy đủ các edge cases:
- Hợp lệ tiêu chuẩn (BV công lập, phòng khám đa khoa)
- Chữ ký số điện tử (Digital Certificate theo TT 25/2025/TT-BYT)
- Lệch ngày (Bác sĩ cho 1 ngày, nhân viên xin 3 ngày)
- Lệch tên bệnh nhân (Tên người khác / người nhà)
- Ảnh mờ nhòe không thể đọc (DOC_ILLEGIBLE)
- Chứng từ quá hạn (Khám từ vài tháng trước)
- Thiếu chữ ký bác sĩ điều trị
- Giấy ra viện điều trị nội trú
- Phiếu tiếp nhận cấp cứu khẩn cấp
- Giấy kết hôn bản thân (3 ngày nguyên lương)
- Giấy kết hôn của con (1 ngày nguyên lương)
- Giấy kết hôn của em gái (Không thuộc diện có lương theo luật)
- Trích lục khai tử cha/mẹ (3 ngày tang chế nguyên lương)
- Giấy khám thai định kỳ Mẫu C65-HD
- Giấy nghỉ chăm con ốm Mẫu 07
- Phiếu sơ cấp cứu tai nạn lao động
- Nhân viên thử việc nghỉ ốm BHXH

LƯU Ý PHÁP LÝ & ĐẠO ĐỨC: Tuyệt đối KHÔNG vẽ hay mô phỏng quốc huy.
Chỉ sử dụng tiêu đề bệnh viện, phòng khám, cơ quan dân sự và biểu tượng chữ thập đỏ y tế.
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Xuất ra cả 2 thư mục: tests/assets/proofs và frontend/assets/proofs
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

OUTPUT_DIRS = [
    BASE_DIR / "assets" / "proofs",
    FRONTEND_DIR / "assets" / "proofs"
]

for d in OUTPUT_DIRS:
    d.mkdir(parents=True, exist_ok=True)


def get_font(size=20, bold=False):
    """Tìm font hệ thống DejaVuSans để hiển thị tiếng Việt hoàn hảo."""
    try:
        font_path = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        )
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def draw_red_cross(draw, x, y, size=32):
    """Biểu tượng chữ thập y tế màu đỏ."""
    w = size // 3
    color = (210, 30, 30)
    draw.rectangle([x + w, y, x + 2 * w, y + size], fill=color)
    draw.rectangle([x, y + w, x + size, y + 2 * w], fill=color)


def draw_round_stamp(draw, cx, cy, radius=55, text="BỆNH VIỆN ĐA KHOA QUỐC TẾ", subtext="★ ĐÃ DUYỆT ★"):
    """Vẽ con dấu tròn đỏ mô phỏng cơ sở KCB hoặc cơ quan hành chính dân sự."""
    red = (215, 35, 35)
    # Vòng tròn ngoài
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=red, width=3)
    # Vòng tròn trong
    draw.ellipse([cx - radius + 7, cy - radius + 7, cx + radius - 7, cy + radius - 7], outline=red, width=1)
    # Nội dung ở tâm
    draw.text((cx - 24, cy - 20), "XÁC NHẬN", fill=red, font=get_font(12, bold=True))
    draw.text((cx - 32, cy - 2), "HỢP LỆ", fill=red, font=get_font(12, bold=True))
    draw.text((cx - radius + 15, cy + 18), subtext, fill=red, font=get_font(9, bold=True))


def draw_signature(draw, x, y, name="BS. Nguyễn"):
    """Vẽ chữ ký tay mô phỏng mực xanh."""
    blue = (25, 45, 140)
    points = [
        (x, y + 15), (x + 20, y - 10), (x + 35, y + 25),
        (x + 50, y - 5), (x + 75, y + 20), (x + 105, y - 15),
        (x + 130, y + 10), (x + 160, y + 5)
    ]
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=blue, width=2)
    draw.line([(x + 15, y + 28), (x + 150, y + 28)], fill=blue, width=2)


def save_image_to_all_dirs(img: Image.Image, filename: str):
    """Lưu ảnh ra cả thư mục tests và frontend."""
    for d in OUTPUT_DIRS:
        target_path = d / filename
        img.save(target_path, "PNG")
    print(f"✅ Generated: {filename}")


# -----------------------------------------------------------------------------
# 1. GIẤY CHỨNG NHẬN NGHỈ VIỆC HƯỞNG BHXH (MẪU 07 - PHỤ LỤC II TT 25/2025/TT-BYT)
# -----------------------------------------------------------------------------
def generate_medical_certificate(
    filename: str,
    patient_name: str,
    start_date: str,
    end_date: str,
    days_count: int,
    issuer: str = "BỆNH VIỆN ĐA KHOA QUỐC TẾ HÀ NỘI",
    diagnosis: str = "Viêm đường hô hấp trên cấp tính (J06.9)",
    has_stamp: bool = True,
    has_signature: bool = True,
    is_digital: bool = False,
    is_blurry: bool = False,
    extra_note: str = ""
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(253, 253, 250))
    draw = ImageDraw.Draw(img)

    # 1. Header (Logo chữ thập y tế + Tên BV)
    draw_red_cross(draw, 50, 45, size=40)
    f_h1 = get_font(17, bold=True)
    f_h2 = get_font(12)
    draw.text((105, 45), issuer.upper(), fill=(20, 30, 80), font=f_h1)
    draw.text((105, 72), "Khoa Khám Bệnh & Cấp Cứu • Hotline: 1900-6868", fill=(80, 80, 80), font=f_h2)
    draw.text((105, 92), "Mã cơ sở KCB: 01-089 • Cổng tiếp nhận BHXH: HỢP CHUẨN", fill=(80, 80, 80), font=f_h2)

    draw.line([(50, 125), (750, 125)], fill=(180, 180, 180), width=1)

    # Form Code
    f_code = get_font(12, bold=True)
    draw.text((530, 135), "Mẫu số: 07 - Phụ lục II", fill=(60, 60, 60), font=f_code)
    draw.text((530, 155), "Thông tư số 25/2025/TT-BYT", fill=(90, 90, 90), font=get_font(11))

    # 2. Document Title
    f_title = get_font(21, bold=True)
    title = "GIẤY CHỨNG NHẬN NGHỈ VIỆC HƯỞNG BẢO HIỂM XÃ HỘI"
    draw.text((80, 195), title, fill=(180, 20, 20), font=f_title)
    draw.text((275, 230), f"Số lưu trữ: GCN-2026-{days_count:02d}-{patient_name[:3].upper()}/BV", fill=(100, 100, 100), font=get_font(13))

    # 3. Patient Details
    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y_pos = 280
    spacing = 40

    rows = [
        ("I. Họ và tên người bệnh:", patient_name.upper()),
        ("Ngày sinh:", "15/08/1995        Giới tính: " + ("Nữ" if any(k in patient_name.lower() for k in ["thị", "my", "yến", "loan", "ngân"]) else "Nam")),
        ("Mã số BHXH / BHYT:", "DN 4 01 0987654321"),
        ("Đơn vị công tác:", "Công ty Cổ phần Công nghệ & Dịch vụ Số"),
        ("Chẩn đoán bệnh lý:", diagnosis),
        ("Phương pháp điều trị:", "Khám ngoại trú, dùng thuốc theo phác đồ chỉ định"),
        ("Số ngày được nghỉ:", f"{days_count} ngày"),
        ("Khoảng thời gian nghỉ:", f"Từ ngày {start_date} đến hết ngày {end_date}"),
    ]

    if extra_note:
        rows.append(("Ghi chú y khoa:", extra_note))

    for label, val in rows:
        draw.text((60, y_pos), label, fill=(30, 30, 30), font=f_label)
        draw.text((310, y_pos), val, fill=(10, 10, 10), font=f_val)
        y_pos += spacing

    # 4. Instructions Box
    draw.rectangle([(55, 650), (745, 730)], fill=(245, 247, 250), outline=(210, 215, 225), width=1)
    draw.text((70, 660), "LỜI DẶN CỦA BÁC SĨ ĐIỀU TRỊ:", fill=(150, 40, 40), font=get_font(13, bold=True))
    draw.text((70, 685), "• Nghỉ ngơi tại nơi cư trú, tuân thủ đơn thuốc và chế độ dinh dưỡng.", fill=(50, 50, 50), font=get_font(12))
    draw.text((70, 705), "• Tái khám ngay nếu có biểu hiện biến chứng hoặc sốt cao kéo dài.", fill=(50, 50, 50), font=get_font(12))

    # 5. Signatures and Stamps
    draw.text((490, 765), f"Hà Nội, ngày {start_date}", fill=(60, 60, 60), font=get_font(13))
    draw.text((100, 795), "NGƯỜI HÀNH NGHỀ KCB", fill=(30, 30, 30), font=get_font(13, bold=True))
    draw.text((95, 815), "(Ký, ghi rõ họ tên)", fill=(110, 110, 110), font=get_font(11))

    draw.text((515, 795), "THỦ TRƯỞNG ĐƠN VỊ", fill=(30, 30, 30), font=get_font(13, bold=True))
    draw.text((495, 815), "(Ký tên, đóng dấu hoặc ký số)", fill=(110, 110, 110), font=get_font(11))

    # Chữ ký bác sĩ
    if has_signature:
        draw_signature(draw, 90, 855)
        draw.text((90, 935), "BS.CKI. Nguyễn Quang Vinh", fill=(20, 20, 80), font=get_font(13, bold=True))
    else:
        draw.text((90, 890), "[CHƯA CÓ CHỮ KÝ BÁC SĨ]", fill=(180, 50, 50), font=get_font(12, bold=True))

    # Con dấu đỏ hoặc Ký số
    if is_digital:
        draw.rectangle([(465, 845), (735, 955)], fill=(240, 248, 255), outline=(0, 100, 200), width=2)
        draw.text((480, 855), "✔ KÝ BỞI: " + issuer[:25], fill=(0, 100, 200), font=get_font(12, bold=True))
        draw.text((480, 880), "CHỨNG THƯ SỐ: 5402.VN-CA.2026", fill=(50, 50, 50), font=get_font(11))
        draw.text((480, 902), f"NGÀY KÝ: 2026-10-{int(start_date[:2]):02d}T08:15:30", fill=(50, 50, 50), font=get_font(11))
        draw.text((480, 925), "TRẠNG THÁI: HỢP LỆ (DIGITAL VALID)", fill=(0, 140, 40), font=get_font(11, bold=True))
    elif has_stamp:
        draw_round_stamp(draw, 595, 895, radius=60, text=issuer)
        draw.text((515, 980), "BS.CKII. Trần Đình Trọng", fill=(20, 20, 80), font=get_font(13, bold=True))

    # Xử lý làm mờ (nếu test ảnh mờ)
    if is_blurry:
        img = img.filter(ImageFilter.GaussianBlur(radius=8))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 2. GIẤY RA VIỆN ĐIỀU TRỊ NỘI TRÚ (INPATIENT DISCHARGE)
# -----------------------------------------------------------------------------
def generate_discharge_certificate(
    filename: str,
    patient_name: str,
    admission_date: str,
    discharge_date: str,
    days_count: int,
    hospital: str = "BỆNH VIỆN BẠCH MAI",
    diagnosis: str = "Cơn đau quặn thận do sỏi niệu quản 1/3 dưới (N20.1)"
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(255, 255, 252))
    draw = ImageDraw.Draw(img)

    draw_red_cross(draw, 50, 45, size=40)
    draw.text((105, 45), hospital.upper(), fill=(18, 30, 85), font=get_font(18, bold=True))
    draw.text((105, 72), "Khoa Ngoại Tiết Niệu • Điện thoại: 024-3869-3731", fill=(80, 80, 80), font=get_font(12))
    draw.text((105, 92), "Địa chỉ: 78 Giải Phóng, Phương Mai, Đống Đa, Hà Nội", fill=(80, 80, 80), font=get_font(12))

    draw.line([(50, 125), (750, 125)], fill=(180, 180, 180), width=1)

    f_title = get_font(23, bold=True)
    draw.text((260, 175), "GIẤY RA VIỆN", fill=(180, 20, 20), font=f_title)
    draw.text((285, 215), f"Số lưu trữ: RV-{days_count:02d}/BA-CKN", fill=(100, 100, 100), font=get_font(13))

    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y = 265
    spacing = 42

    data = [
        ("Họ và tên người bệnh:", patient_name.upper()),
        ("Năm sinh / Giới tính:", "1988          Nam"),
        ("Số thẻ BHYT:", "DN 4 01 0888999111"),
        ("Ngày vào viện:", f"{admission_date} (Khoa Cấp Cứu)"),
        ("Ngày ra viện:", f"{discharge_date} (Xuất viện theo hẹn)"),
        ("Chẩn đoán:", diagnosis),
        ("Phương pháp phẫu thuật:", "Tán sỏi nội soi ngược dòng bằng Laser (Thành công)"),
        ("Số ngày điều trị nội trú:", f"{days_count} ngày"),
        ("Tình trạng ra viện:", "Hết đau quặn, dẫn lưu thông tốt, vết mổ ổn định"),
    ]

    for lbl, val in data:
        draw.text((60, y), lbl, fill=(35, 35, 35), font=f_label)
        draw.text((310, y), val, fill=(10, 10, 10), font=f_val)
        y += spacing

    # Hộp dặn dò
    draw.rectangle([(55, 660), (745, 745)], fill=(245, 248, 252), outline=(190, 205, 225), width=1)
    draw.text((70, 670), "CHỈ ĐỊNH ĐIỀU TRỊ TIẾP TỤC & NGHỈ NGƠI:", fill=(20, 40, 120), font=get_font(13, bold=True))
    draw.text((70, 695), "• Uống nhiều nước (trên 2.5 lít/ngày), dùng thuốc theo toa ra viện.", fill=(50, 50, 50), font=get_font(12))
    draw.text((70, 718), f"• Nghỉ ngơi tại nhà hưởng chế độ BHXH 07 ngày tiếp theo kể từ ngày {discharge_date}.", fill=(180, 20, 20), font=get_font(12, bold=True))

    draw.text((490, 775), f"Hà Nội, ngày {discharge_date}", fill=(60, 60, 60), font=get_font(13))
    draw.text((95, 805), "TRƯỞNG KHOA ĐIỀU TRỊ", fill=(30, 30, 30), font=get_font(13, bold=True))
    draw.text((505, 805), "GIÁM ĐỐC BỆNH VIỆN", fill=(30, 30, 30), font=get_font(13, bold=True))

    draw_signature(draw, 85, 860)
    draw.text((85, 940), "PGS.TS. Lê Bá Tùng", fill=(20, 20, 80), font=get_font(13, bold=True))

    draw_round_stamp(draw, 595, 895, radius=62, text=hospital)
    draw.text((515, 980), "GS.TS. Nguyễn Gia Bình", fill=(20, 20, 80), font=get_font(13, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 3. PHIẾU CẤP CỨU Y TẾ KHẨN CẤP (EMERGENCY ADMISSION SLIP)
# -----------------------------------------------------------------------------
def generate_emergency_slip(
    filename: str,
    patient_name: str,
    admission_datetime: str,
    hospital: str = "BỆNH VIỆN ĐA KHOA E TRUNG ƯƠNG",
    emergency_reason: str = "Đau hố chậu phải dữ dội, phản ứng thành bụng dương tính (Nghi viêm ruột thừa cấp)"
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(255, 253, 250))
    draw = ImageDraw.Draw(img)

    draw_red_cross(draw, 50, 45, size=40)
    draw.text((105, 45), hospital.upper(), fill=(160, 20, 20), font=get_font(17, bold=True))
    draw.text((105, 72), "KHOA CẤP CỨU HỒI SỨC TÍCH CỰC • Hotline: 024-3754-3650", fill=(70, 70, 70), font=get_font(12))

    draw.line([(50, 120), (750, 120)], fill=(200, 50, 50), width=2)

    # Dấu mộc vuông ĐỎ CẤP CỨU LƯU
    draw.rectangle([(560, 135), (740, 185)], outline=(220, 20, 20), width=3)
    draw.text((580, 142), "⚡ CẤP CỨU LƯU", fill=(220, 20, 20), font=get_font(14, bold=True))
    draw.text((585, 165), "ƯU TIÊN CẤP I", fill=(220, 20, 20), font=get_font(11, bold=True))

    draw.text((160, 205), "PHIẾU TIẾP NHẬN CẤP CỨU KHẨN CẤP", fill=(180, 20, 20), font=get_font(21, bold=True))
    draw.text((280, 240), f"Mã hồ sơ cấp cứu: CC-2026/0893", fill=(90, 90, 90), font=get_font(13))

    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y = 290
    spacing = 42

    items = [
        ("Họ và tên bệnh nhân:", patient_name.upper()),
        ("Thời điểm nhập cấp cứu:", admission_datetime),
        ("Hình thức tiếp nhận:", "Tự đến bằng xe cấp cứu 115"),
        ("Tình trạng lúc vào viện:", "Sốt 38.8°C, mạch 105 l/p, huyết áp 130/80 mmHg"),
        ("Chẩn đoán sơ bộ:", emergency_reason),
        ("Xử trí ban đầu:", "Lập đường truyền tĩnh mạch, siêu âm bụng cấp, xét nghiệm máu"),
        ("Bác sĩ trực cấp cứu:", "ThS.BS. Đặng Quốc Hùng (Trực ngoại khoa)"),
        ("Kết luận chuyên môn:", "CHỈ ĐỊNH NHẬP VIỆN PHẪU THUẬT NỘI SOI CẤP"),
    ]

    for lbl, val in items:
        draw.text((60, y), lbl, fill=(35, 35, 35), font=f_label)
        draw.text((305, y), val, fill=(10, 10, 10), font=f_val)
        y += spacing

    draw.rectangle([(55, 650), (745, 735)], fill=(255, 245, 245), outline=(230, 180, 180), width=1)
    draw.text((70, 660), "XÁC NHẬN CỦA KHOA CẤP CỨU:", fill=(180, 20, 20), font=get_font(13, bold=True))
    draw.text((70, 685), "• Người bệnh cần nằm viện phẫu thuật và theo dõi điều trị liên tục.", fill=(40, 40, 40), font=get_font(12))
    draw.text((70, 707), "• Gia đình/Công ty giải quyết thủ tục tạm hoãn công việc theo chế độ cấp cứu.", fill=(40, 40, 40), font=get_font(12))

    draw.text((480, 765), "Hà Nội, thời điểm cấp cứu tiếp nhận", fill=(60, 60, 60), font=get_font(13))
    draw.text((505, 795), "BÁC SĨ TRỰC TIẾP NHẬN", fill=(30, 30, 30), font=get_font(13, bold=True))

    draw_signature(draw, 490, 845)
    draw_round_stamp(draw, 585, 905, radius=58, text="KHOA CẤP CỨU BV E", subtext="★ KHẨN CẤP ★")
    draw.text((495, 980), "ThS.BS. Đặng Quốc Hùng", fill=(20, 20, 80), font=get_font(13, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 4. GIẤY CHỨNG NHẬN KẾT HÔN DÂN SỰ (UBND CẤP)
# -----------------------------------------------------------------------------
def generate_wedding_certificate(
    filename: str,
    husband: str,
    wife: str,
    note_relationship: str = "",
    wedding_date: str = "22/09/2026",
    is_expired_wedding: bool = False
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(255, 252, 245))
    draw = ImageDraw.Draw(img)

    # Khung viền hoa văn vàng kim
    draw.rectangle([(25, 25), (775, 1075)], outline=(180, 140, 60), width=3)
    draw.rectangle([(35, 35), (765, 1065)], outline=(210, 180, 110), width=1)

    draw.text((230, 60), "ỦY BAN NHÂN DÂN PHƯỜNG DỊCH VỌNG HẬU", fill=(140, 30, 30), font=get_font(14, bold=True))
    draw.text((310, 85), "BỘ PHẬN TƯ PHÁP - HỘ TỊCH", fill=(80, 80, 80), font=get_font(13))
    draw.line([(270, 110), (530, 110)], fill=(180, 140, 60), width=1)

    draw.text((185, 160), "GIẤY CHỨNG NHẬN KẾT HÔN", fill=(180, 30, 30), font=get_font(23, bold=True))
    draw.text((305, 200), "(BẢN SAO TRÍCH LỤC HỢP PHÁP)", fill=(100, 100, 100), font=get_font(13, bold=True))

    reg_date = "15/03/2026" if is_expired_wedding else wedding_date

    y = 270
    info = [
        ("Họ và tên người chồng:", husband.upper()),
        ("Ngày sinh / Quốc tịch:", "12/04/1996          Việt Nam"),
        ("Số CCCD người chồng:", "001096001234"),
        ("Họ và tên người vợ:", wife.upper()),
        ("Ngày sinh / Quốc tịch:", "20/09/1998          Việt Nam"),
        ("Số CCCD người vợ:", "001198005678"),
        ("Nơi đăng ký kết hôn:", "UBND Phường Dịch Vọng Hậu, Cầu Giấy, Hà Nội"),
        ("Ngày đăng ký chính thức:", reg_date),
        ("Số vào sổ đăng ký:", "Số: 128/2026/ĐKKH-KH"),
    ]

    if note_relationship:
        info.append(("Ghi chú về nhân thân:", note_relationship))

    for lbl, val in info:
        draw.text((80, y), lbl, fill=(40, 40, 40), font=get_font(14, bold=True))
        draw.text((320, y), val, fill=(10, 10, 10), font=get_font(14))
        y += 44

    draw_round_stamp(draw, 580, 850, radius=65, text="UBND PHƯỜNG DỊCH VỌNG HẬU", subtext="★ TƯ PHÁP ★")
    draw_signature(draw, 500, 820)
    draw.text((515, 930), "CHỦ TỊCH: Lê Hoàng Sơn", fill=(20, 20, 80), font=get_font(14, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 5. TRÍCH LỤC KHAI TỬ (TANG CHẾ TỨ THÂN PHỤ MẪU)
# -----------------------------------------------------------------------------
def generate_funeral_certificate(
    filename: str,
    deceased_name: str,
    relationship: str,
    applicant_name: str,
    death_date: str = "10/10/2026"
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(253, 253, 253))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(25, 25), (775, 1075)], outline=(80, 80, 80), width=2)
    draw.rectangle([(32, 32), (768, 1068)], outline=(180, 180, 180), width=1)

    draw.text((230, 60), "ỦY BAN NHÂN DÂN PHƯỜNG QUAN HOA", fill=(40, 40, 40), font=get_font(14, bold=True))
    draw.text((290, 85), "BỘ PHẬN ĐĂNG KÝ HỘ TỊCH DÂN SỰ", fill=(80, 80, 80), font=get_font(13))
    draw.line([(260, 110), (540, 110)], fill=(120, 120, 120), width=1)

    draw.text((195, 160), "TRÍCH LỤC KHAI TỬ (BẢN SAO)", fill=(20, 20, 20), font=get_font(23, bold=True))
    draw.text((275, 200), "Số: 45/TLKT-BS/2026 - Quyển số 01/2026", fill=(100, 100, 100), font=get_font(13))

    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y = 270
    spacing = 42

    items = [
        ("Họ và tên người qua đời:", deceased_name.upper()),
        ("Năm sinh / Giới tính:", "1952          Nữ"),
        ("Mối quan hệ với nhân viên:", f"{relationship} của {applicant_name.upper()}"),
        ("Ngày từ trần:", f"{death_date} (Hưởng thọ 74 tuổi)"),
        ("Nơi qua đời:", "Số 18 Ngõ 165 Cầu Giấy, Quan Hoa, Hà Nội"),
        ("Nguyên nhân qua đời:", "Tuổi già suy kiệt / Đột quỵ do tim mạch"),
        ("Người yêu cầu cấp trích lục:", applicant_name.upper()),
        ("Quan hệ với người quá cố:", f"Con ruột ({applicant_name})"),
    ]

    for lbl, val in items:
        draw.text((80, y), lbl, fill=(35, 35, 35), font=f_label)
        draw.text((330, y), val, fill=(10, 10, 10), font=f_val)
        y += spacing

    draw.rectangle([(60, 640), (740, 720)], fill=(245, 245, 245), outline=(200, 200, 200), width=1)
    draw.text((75, 650), "CHÍNH SÁCH CHẾ ĐỘ NGHỈ TANG CHẾ (ĐIỀU 115 BỘ LUẬT LAO ĐỘNG):", fill=(20, 20, 20), font=get_font(12, bold=True))
    draw.text((75, 675), "• Tứ thân phụ mẫu (cha mẹ đẻ, cha mẹ vợ/chồng) qua đời: Được nghỉ 03 ngày hưởng nguyên lương.", fill=(50, 50, 50), font=get_font(12))
    draw.text((75, 695), "• Doanh nghiệp có trách nhiệm hỗ trợ thủ tục giải quyết chế độ kịp thời.", fill=(50, 50, 50), font=get_font(12))

    draw.text((490, 760), f"Hà Nội, ngày {death_date}", fill=(60, 60, 60), font=get_font(13))
    draw.text((520, 790), "NGƯỜI KÝ CHỨNG THỰC", fill=(30, 30, 30), font=get_font(13, bold=True))

    draw_round_stamp(draw, 595, 870, radius=62, text="UBND PHƯỜNG QUAN HOA", subtext="★ HỘ TỊCH ★")
    draw_signature(draw, 500, 830)
    draw.text((520, 950), "PHÓ CHỦ TỊCH: Đỗ Quang Minh", fill=(20, 20, 80), font=get_font(13, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 6. GIẤY CHỨNG NHẬN KHÁM THAI ĐỊNH KỲ (MẪU C65-HD)
# -----------------------------------------------------------------------------
def generate_prenatal_certificate(
    filename: str,
    patient_name: str,
    visit_date: str = "15/10/2026",
    gestational_age: str = "28 tuần 4 ngày"
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(255, 250, 252))
    draw = ImageDraw.Draw(img)

    draw_red_cross(draw, 50, 45, size=40)
    draw.text((105, 45), "BỆNH VIỆN PHỤ SẢN HÀ NỘI", fill=(160, 20, 80), font=get_font(18, bold=True))
    draw.text((105, 72), "Khoa Khám Sản Phụ Khoa Tự Nguyện • Hotline: 1900-6922", fill=(80, 80, 80), font=get_font(12))
    draw.text((105, 92), "Cơ sở: 929 Đê La Thành, Ba Đình, Hà Nội", fill=(80, 80, 80), font=get_font(12))

    draw.line([(50, 120), (750, 120)], fill=(200, 100, 150), width=1)

    draw.text((540, 130), "Mẫu số: C65-HD", fill=(60, 60, 60), font=get_font(12, bold=True))
    draw.text((540, 150), "Luật BHXH - Thai sản", fill=(90, 90, 90), font=get_font(11))

    draw.text((185, 190), "GIẤY CHỨNG NHẬN NGHỈ KHÁM THAI", fill=(170, 20, 80), font=get_font(21, bold=True))
    draw.text((295, 225), "Số hồ sơ: KT-2026/0498/PSHN", fill=(100, 100, 100), font=get_font(13))

    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y = 275
    spacing = 42

    rows = [
        ("Họ và tên sản phụ:", patient_name.upper()),
        ("Năm sinh / Mã số BHXH:", "1994          DN 4 01 0777888999"),
        ("Nơi làm việc:", "Phòng Marketing & Operations"),
        ("Tuổi thai phát triển:", gestational_age),
        ("Tình trạng sản khoa:", "Tim thai rõ, ngôi đầu, các chỉ số sinh học đạt chuẩn"),
        ("Ngày khám thai thực tế:", visit_date),
        ("Số ngày nghỉ hưởng BHXH:", "01 (một) ngày theo quy định thai sản"),
        ("Lịch hẹn khám thai lần tới:", "Bốn tuần sau (Thai 32 tuần)"),
    ]

    for lbl, val in rows:
        draw.text((60, y), lbl, fill=(35, 35, 35), font=f_label)
        draw.text((310, y), val, fill=(10, 10, 10), font=f_val)
        y += spacing

    draw.rectangle([(55, 640), (745, 725)], fill=(255, 245, 248), outline=(230, 190, 205), width=1)
    draw.text((70, 650), "CHẾ ĐỘ THAI SẢN (ĐIỀU 32 LUẬT BẢO HIỂM XÃ HỘI):", fill=(160, 20, 80), font=get_font(12, bold=True))
    draw.text((70, 675), "• Lao động nữ được nghỉ việc đi khám thai 05 lần, mỗi lần 01 ngày.", fill=(50, 50, 50), font=get_font(12))
    draw.text((70, 695), "• Thời gian nghỉ việc hưởng chế độ thai sản tính theo ngày làm việc.", fill=(50, 50, 50), font=get_font(12))

    draw.text((490, 765), f"Hà Nội, ngày {visit_date}", fill=(60, 60, 60), font=get_font(13))
    draw.text((505, 795), "BÁC SĨ KHÁM SẢN KHOA", fill=(30, 30, 30), font=get_font(13, bold=True))

    draw_signature(draw, 490, 840)
    draw_round_stamp(draw, 585, 895, radius=58, text="BV PHỤ SẢN HÀ NỘI", subtext="★ SẢN KHOA ★")
    draw.text((495, 975), "BS.CKII. Vũ Thị Thanh Hương", fill=(20, 20, 80), font=get_font(13, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 7. GIẤY NGHỈ CHĂM CON ỐM MẪU 07 (CHẾ ĐỘ CON DƯỚI 7 TUỔI ỐM ĐAU)
# -----------------------------------------------------------------------------
def generate_child_care_certificate(
    filename: str,
    parent_name: str,
    child_name: str,
    child_age: str = "3 tuổi",
    days_count: int = 3,
    start_date: str = "18/10/2026",
    end_date: str = "20/10/2026"
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(252, 254, 252))
    draw = ImageDraw.Draw(img)

    draw_red_cross(draw, 50, 45, size=40)
    draw.text((105, 45), "BỆNH VIỆN NHI TRUNG ƯƠNG", fill=(10, 120, 60), font=get_font(18, bold=True))
    draw.text((105, 72), "Khoa Cấp Cứu & Điều Trị Ban Ngày • Hotline: 024-6273-8532", fill=(80, 80, 80), font=get_font(12))
    draw.text((105, 92), "Địa chỉ: 18/879 La Thành, Đống Đa, Hà Nội", fill=(80, 80, 80), font=get_font(12))

    draw.line([(50, 120), (750, 120)], fill=(100, 180, 120), width=1)

    draw.text((540, 130), "Mẫu số: 07-BHXH", fill=(60, 60, 60), font=get_font(12, bold=True))
    draw.text((540, 150), "Chế độ: Chăm con ốm", fill=(90, 90, 90), font=get_font(11))

    draw.text((140, 190), "GIẤY NGHỈ VIỆC CHĂM SÓC CON ỐM HƯỞNG BHXH", fill=(20, 120, 60), font=get_font(20, bold=True))
    draw.text((290, 225), "Số hồ sơ: GCN-CON-2026/0542", fill=(100, 100, 100), font=get_font(13))

    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y = 275
    spacing = 42

    rows = [
        ("I. Họ và tên người mẹ:", parent_name.upper()),
        ("Mã số BHXH người mẹ:", "DN 4 01 0666555444"),
        ("Đơn vị công tác:", "Bộ phận Chăm sóc khách hàng (Customer Support)"),
        ("II. Họ và tên con bị ốm:", child_name.upper()),
        ("Ngày sinh con / Độ tuổi:", f"2023 ({child_age}) - Dưới 7 tuổi theo Luật BHXH"),
        ("Chẩn đoán bệnh của con:", "Viêm phế quản co thắt cấp tính, sốt cao (J20.9)"),
        ("Số ngày người mẹ cần nghỉ:", f"{days_count} ngày để trực tiếp chăm sóc con"),
        ("Khoảng thời gian nghỉ:", f"Từ ngày {start_date} đến hết ngày {end_date}"),
    ]

    for lbl, val in rows:
        draw.text((60, y), lbl, fill=(35, 35, 35), font=f_label)
        draw.text((310, y), val, fill=(10, 10, 10), font=f_val)
        y += spacing

    draw.rectangle([(55, 640), (745, 725)], fill=(245, 252, 245), outline=(190, 225, 195), width=1)
    draw.text((70, 650), "QUY ĐỊNH CHẾ ĐỘ NGHỈ KHI CON ỐM ĐAU (ĐIỀU 25 LUẬT BHXH):", fill=(20, 120, 60), font=get_font(12, bold=True))
    draw.text((70, 675), "• Con dưới 03 tuổi: Thời gian nghỉ tối đa 20 ngày làm việc/năm cho mỗi con.", fill=(50, 50, 50), font=get_font(12))
    draw.text((70, 695), "• Con từ đủ 03 đến dưới 07 tuổi: Tối đa 15 ngày làm việc/năm. Quỹ BHXH chi trả.", fill=(50, 50, 50), font=get_font(12))

    draw.text((490, 765), f"Hà Nội, ngày {start_date}", fill=(60, 60, 60), font=get_font(13))
    draw.text((505, 795), "BÁC SĨ KHÁM NHI KHOA", fill=(30, 30, 30), font=get_font(13, bold=True))

    draw_signature(draw, 490, 840)
    draw_round_stamp(draw, 585, 895, radius=58, text="BV NHI TRUNG ƯƠNG", subtext="★ NHI KHOA ★")
    draw.text((495, 975), "BS.CKI. Nguyễn Hoàng Anh", fill=(20, 20, 80), font=get_font(13, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# 8. PHIẾU XỬ TRÍ SƠ CẤP CỨU TAI NẠN LAO ĐỘNG (WORK ACCIDENT)
# -----------------------------------------------------------------------------
def generate_work_accident_certificate(
    filename: str,
    victim_name: str,
    accident_date: str = "20/10/2026",
    location: str = "Văn phòng Tầng 6, Tòa nhà Công nghệ",
    injury_desc: str = "Trượt ngã cầu thang, chấn thương phần mềm cổ tay và khớp gối phải"
):
    width, height = 800, 1100
    img = Image.new("RGB", (width, height), color=(254, 253, 250))
    draw = ImageDraw.Draw(img)

    draw_red_cross(draw, 50, 45, size=40)
    draw.text((105, 45), "TRUNG TÂM Y TẾ LAO ĐỘNG & BỆNH NGHỀ NGHIỆP", fill=(180, 40, 20), font=get_font(16, bold=True))
    draw.text((105, 72), "Tổ Cấp Cứu Sơ Bộ & Giám Định Tai Nạn Lao Động • ĐT: 024-3838-2211", fill=(80, 80, 80), font=get_font(12))

    draw.line([(50, 120), (750, 120)], fill=(200, 100, 50), width=1)

    draw.text((170, 185), "PHIẾU SƠ CẤP CỨU TAI NẠN LAO ĐỘNG", fill=(180, 40, 20), font=get_font(21, bold=True))
    draw.text((275, 220), "Mã hồ sơ TNLĐ: TNLD-2026/10-001", fill=(100, 100, 100), font=get_font(13))

    f_label = get_font(14, bold=True)
    f_val = get_font(14)
    y = 270
    spacing = 42

    rows = [
        ("Họ và tên người bị nạn:", victim_name.upper()),
        ("Thời điểm xảy ra tai nạn:", f"{accident_date} lúc 09:30 sáng"),
        ("Địa điểm xảy ra sự cố:", location),
        ("Mô tả chấn thương thực tế:", injury_desc),
        ("Xử lý cấp cứu ban đầu:", "Bất động cổ tay, chườm lạnh, chụp X-quang loại trừ gãy xương"),
        ("Kết luận giám định ban đầu:", "Tổn thương mô mềm tạm thời, giảm khả năng vận động chi"),
        ("Chỉ định nghỉ dưỡng thương:", "Nghỉ việc 03 ngày điều trị phục hồi có hưởng chế độ TNLĐ"),
        ("Trách nhiệm người sử dụng LĐ:", "Chi trả đầy đủ tiền lương & viện phí theo Điều 38 Luật ATVSLĐ"),
    ]

    for lbl, val in rows:
        draw.text((60, y), lbl, fill=(35, 35, 35), font=f_label)
        draw.text((310, y), val, fill=(10, 10, 10), font=f_val)
        y += spacing

    draw.rectangle([(55, 640), (745, 725)], fill=(255, 248, 245), outline=(230, 200, 180), width=1)
    draw.text((70, 650), "CĂN CỨ LUẬT AN TOÀN VỆ SINH LAO ĐỘNG NĂM 2015:", fill=(180, 40, 20), font=get_font(12, bold=True))
    draw.text((70, 675), "• Tai nạn xảy ra tại nơi làm việc trong giờ làm việc được xác lập hồ sơ TNLĐ.", fill=(50, 50, 50), font=get_font(12))
    draw.text((70, 695), "• Người lao động được hưởng 100% tiền lương trong thời gian nghỉ điều trị thương tật.", fill=(50, 50, 50), font=get_font(12))

    draw.text((490, 765), f"Hà Nội, ngày {accident_date}", fill=(60, 60, 60), font=get_font(13))
    draw.text((505, 795), "BÁC SĨ SƠ CẤP CỨU TNLĐ", fill=(30, 30, 30), font=get_font(13, bold=True))

    draw_signature(draw, 490, 840)
    draw_round_stamp(draw, 585, 895, radius=58, text="TT Y TẾ LAO ĐỘNG", subtext="★ SƠ CẤP CỨU ★")
    draw.text((495, 975), "BS.CKI. Phạm Hoàng Nam", fill=(20, 20, 80), font=get_font(13, bold=True))

    save_image_to_all_dirs(img, filename)
    return filename


# -----------------------------------------------------------------------------
# MAIN GENERATOR: 20 TẤM ẢNH PHỦ ĐỀU 10 STAFF (EMP003 -> EMP012) + CÁC EDGE CASES
# -----------------------------------------------------------------------------
def main():
    print("🚀 Bắt đầu sinh 20 chứng từ y tế / minh chứng giả định phủ đều 10 nhân sự...")

    # 1. EMP003 - Trần Quốc Hưng (Principal Architect, Engineering)
    # Ảnh 1: SPECIAL_PAID - Con kết hôn (1 ngày theo Điều 115 BLLĐ)
    generate_wedding_certificate(
        filename="proof_emp003_wedding_child.png",
        husband="Trần Quốc Anh",
        wife="Đặng Mai Phương",
        note_relationship="Trần Quốc Anh là con ruột của ông Trần Quốc Hưng (EMP003)"
    )
    # Ảnh 2: SICK_MEDICAL - Giấy ra viện điều trị sỏi thận 4 ngày (Nội trú BV Bạch Mai)
    generate_discharge_certificate(
        filename="proof_emp003_discharge_inpatient.png",
        patient_name="Trần Quốc Hưng",
        admission_date="08/10/2026",
        discharge_date="11/10/2026",
        days_count=4,
        hospital="BỆNH VIỆN BẠCH MAI"
    )

    # 2. EMP004 - Lê Văn Nam (Senior Software Engineer, Engineering)
    # Ảnh 3: SICK_MEDICAL - Giấy nghỉ ốm có chữ ký số điện tử hợp pháp (TT 25/2025/TT-BYT)
    generate_medical_certificate(
        filename="proof_emp004_sick_digital_valid.png",
        patient_name="Lê Văn Nam",
        start_date="12/10/2026",
        end_date="14/10/2026",
        days_count=3,
        issuer="BỆNH VIỆN ĐA KHOA HỒNG NGỌC",
        diagnosis="Viêm xoang hàm cấp tính có mủ (J01.0)",
        is_digital=True
    )
    # Ảnh 4: SICK_MEDICAL (BẪY LỆCH NGÀY) - Bác sĩ chỉ cho 1 ngày, nhân viên xin 3 ngày
    generate_medical_certificate(
        filename="proof_emp004_sick_days_mismatch.png",
        patient_name="Lê Văn Nam",
        start_date="12/10/2026",
        end_date="12/10/2026",
        days_count=1,
        issuer="BỆNH VIỆN ĐA KHOA QUỐC TẾ HÀ NỘI",
        diagnosis="Rối loạn tiêu hóa nhẹ, theo dõi ngộ độc thức ăn",
        has_stamp=True
    )

    # 3. EMP005 - Nguyễn Văn An (Software Engineer, Engineering)
    # Ảnh 5: SICK_MEDICAL - Phòng khám tư nhân Medlatec hợp chuẩn KCB BHYT
    generate_medical_certificate(
        filename="proof_emp005_sick_clinic_valid.png",
        patient_name="Nguyễn Văn An",
        start_date="14/10/2026",
        end_date="17/10/2026",
        days_count=4,
        issuer="PHÒNG KHÁM ĐA KHOA MEDLATEC",
        diagnosis="Sốt xuất huyết Dengue cảnh báo ngày thứ 3 (A97.1)",
        has_stamp=True
    )
    # Ảnh 6: SICK_MEDICAL (BẪY QUÁ HẠN) - Giấy khám từ tháng 5/2026 (cách đây 5 tháng)
    generate_medical_certificate(
        filename="proof_emp005_sick_expired.png",
        patient_name="Nguyễn Văn An",
        start_date="15/05/2026",
        end_date="18/05/2026",
        days_count=4,
        issuer="BỆNH VIỆN ĐA KHOA QUỐC TẾ HÀ NỘI",
        diagnosis="Viêm họng phế quản cấp",
        has_stamp=True,
        extra_note="[LƯU Ý: Giấy cấp đợt khám bệnh tháng 05/2026 đã quá hạn áp dụng]"
    )

    # 4. EMP006 - Bùi Tuấn Kiệt (Frontend Engineer, Engineering)
    # Ảnh 7: SICK_MEDICAL - Nghỉ ốm 2 ngày chuẩn
    generate_medical_certificate(
        filename="proof_emp006_sick_standard_2days.png",
        patient_name="Bùi Tuấn Kiệt",
        start_date="15/10/2026",
        end_date="16/10/2026",
        days_count=2,
        issuer="BỆNH VIỆN GIAO THÔNG VẬN TẢI",
        diagnosis="Viêm amidan hốc mủ cấp tính (J03.9)",
        has_stamp=True
    )
    # Ảnh 8: MEDICAL_EMERGENCY - Phiếu cấp cứu lưu khẩn cấp viêm ruột thừa
    generate_emergency_slip(
        filename="proof_emp006_emergency_slip.png",
        patient_name="Bùi Tuấn Kiệt",
        admission_datetime="15/10/2026 lúc 06:15 sáng",
        hospital="BỆNH VIỆN ĐA KHOA E TRUNG ƯƠNG",
        emergency_reason="Đau bụng cấp hố chậu phải dữ dội nghi ruột thừa vỡ"
    )

    # 5. EMP007 - Lê Thị Hương (Junior QA Engineer, Thử việc, Engineering)
    # Ảnh 9: SICK_MEDICAL - Thử việc nghỉ ốm có BHXH (duyệt nghỉ ốm không trừ phép năm)
    generate_medical_certificate(
        filename="proof_emp007_sick_probation_valid.png",
        patient_name="Lê Thị Hương",
        start_date="16/10/2026",
        end_date="17/10/2026",
        days_count=2,
        issuer="BỆNH VIỆN ĐẠI HỌC Y HÀ NỘI",
        diagnosis="Hội chứng Migraine tiền đình cấp, hạ đường huyết",
        has_stamp=True
    )
    # Ảnh 10: SICK_MEDICAL (BẪY THIẾU CHỮ KÝ BÁC SĨ) - Có dấu mộc nhưng thiếu chữ ký người KCB
    generate_medical_certificate(
        filename="proof_emp007_sick_missing_signature.png",
        patient_name="Lê Thị Hương",
        start_date="16/10/2026",
        end_date="17/10/2026",
        days_count=2,
        issuer="BỆNH VIỆN ĐA KHOA QUỐC TẾ HÀ NỘI",
        diagnosis="Cúm mùa A (J10.1)",
        has_stamp=True,
        has_signature=False
    )

    # 6. EMP008 - Nguyễn Thị Kim Ngân (Operations Lead, Marketing & Ops)
    # Ảnh 11: MATERNITY - Khám thai định kỳ C65-HD (1 ngày)
    generate_prenatal_certificate(
        filename="proof_emp008_maternity_prenatal.png",
        patient_name="Nguyễn Thị Kim Ngân",
        visit_date="19/10/2026",
        gestational_age="28 tuần 4 ngày"
    )
    # Ảnh 12: SPECIAL_PAID - Tang chế mẹ ruột 3 ngày hưởng nguyên lương
    generate_funeral_certificate(
        filename="proof_emp008_funeral_direct.png",
        deceased_name="Trần Thị Lan",
        relationship="Mẹ ruột",
        applicant_name="Nguyễn Thị Kim Ngân",
        death_date="18/10/2026"
    )

    # 7. EMP009 - Võ Minh Khang (Content Specialist, Marketing & Ops)
    # Ảnh 13: SPECIAL_PAID - Kết hôn bản thân 3 ngày nguyên lương
    generate_wedding_certificate(
        filename="proof_emp009_wedding_valid.png",
        husband="Võ Minh Khang",
        wife="Nguyễn Thu Thảo",
        wedding_date="20/10/2026"
    )
    # Ảnh 14: SICK_MEDICAL (BẪY LỆCH TÊN) - Nhân viên nộp giấy nhưng tên bệnh nhân là người nhà
    generate_medical_certificate(
        filename="proof_emp009_sick_name_mismatch.png",
        patient_name="Võ Hoàng Long",
        start_date="20/10/2026",
        end_date="22/10/2026",
        days_count=3,
        issuer="BỆNH VIỆN BẠCH MAI",
        diagnosis="Viêm họng hạt cấp tính",
        has_stamp=True
    )

    # 8. EMP010 - Phan Thảo My (Digital Marketing, Marketing & Ops)
    # Ảnh 15: SICK_MEDICAL - Nghỉ ốm 3 ngày tiêu chuẩn
    generate_medical_certificate(
        filename="proof_emp010_sick_standard_3days.png",
        patient_name="Phan Thảo My",
        start_date="21/10/2026",
        end_date="23/10/2026",
        days_count=3,
        issuer="BỆNH VIỆN THANH NHÀN",
        diagnosis="Sốt virus nhiễm khuẩn hô hấp cấp",
        has_stamp=True
    )
    # Ảnh 16: SICK_MEDICAL (BẪY ẢNH MỜ NHÒE) - Rung lắc ống kính camera không thể đọc
    generate_medical_certificate(
        filename="proof_emp010_sick_blurry.png",
        patient_name="Phan Thảo My",
        start_date="21/10/2026",
        end_date="23/10/2026",
        days_count=3,
        issuer="BỆNH VIỆN THANH NHÀN",
        diagnosis="Sốt virus",
        is_blurry=True
    )

    # 9. EMP011 - Hoàng Kim Yến (Operations Specialist, Marketing & Ops)
    # Ảnh 17: SICK_MEDICAL - Nghỉ ốm sáng sớm có đơn thuốc BV Thu Cúc
    generate_medical_certificate(
        filename="proof_emp011_sick_morning_valid.png",
        patient_name="Hoàng Kim Yến",
        start_date="22/10/2026",
        end_date="22/10/2026",
        days_count=1,
        issuer="BỆNH VIỆN ĐA KHOA QUỐC TẾ THU CÚC",
        diagnosis="Viêm dạ dày ruột cấp tính, mất nước nhẹ",
        has_stamp=True
    )
    # Ảnh 18: WORK_ACCIDENT - Phiếu tiếp nhận sơ cứu tai nạn lao động tại văn phòng
    generate_work_accident_certificate(
        filename="proof_emp011_work_accident.png",
        victim_name="Hoàng Kim Yến",
        accident_date="22/10/2026",
        location="Cầu thang bộ Tầng 6, Tòa nhà Công ty",
        injury_desc="Trượt ngã bong gân cổ chân phải, chấn thương mô mềm"
    )

    # 10. EMP012 - Lê Mai Loan (Customer Support, Marketing & Ops)
    # Ảnh 19: SICK_MEDICAL - Nghỉ chăm con ốm Mẫu 07 (con 3 tuổi)
    generate_child_care_certificate(
        filename="proof_emp012_child_sick_care.png",
        parent_name="Lê Mai Loan",
        child_name="Đặng Minh Khôi",
        child_age="3 tuổi",
        days_count=3,
        start_date="23/10/2026",
        end_date="25/10/2026"
    )
    # Ảnh 20: SPECIAL_PAID (BẪY QUY CHẾ) - Giấy kết hôn của em gái (Không được nghỉ có lương tự động theo luật)
    generate_wedding_certificate(
        filename="proof_emp012_wedding_sibling.png",
        husband="Đỗ Tuấn Minh",
        wife="Lê Mai Linh",
        note_relationship="Lê Mai Linh là em gái ruột của nhân viên Lê Mai Loan (EMP012)",
        wedding_date="24/10/2026"
    )

    # Giữ nguyên 6 ảnh gốc cho backwards compatibility
    generate_medical_certificate("proof_sick_valid_3days.png", "Nguyễn Văn An", "22/09/2026", "24/09/2026", 3)
    generate_medical_certificate("proof_name_mismatch.png", "Phạm Quốc Dũng", "22/09/2026", "24/09/2026", 3, issuer="Bệnh viện Đa khoa Medlatec")
    generate_medical_certificate("proof_days_mismatch.png", "Nguyễn Văn An", "22/09/2026", "23/09/2026", 2)
    generate_medical_certificate("proof_blurry_illegible.png", "Nguyễn Văn An", "22/09/2026", "24/09/2026", 3, is_blurry=True)
    generate_medical_certificate("proof_digital_signed.png", "Nguyễn Văn An", "22/09/2026", "24/09/2026", 3, is_digital=True)
    generate_wedding_certificate("proof_wedding_cert.png", "Võ Minh Khang", "Nguyễn Thu Thảo")

    print("🎉 Hoàn tất sinh toàn bộ 26 chứng từ y tế và minh chứng mẫu chất lượng cao!")


if __name__ == "__main__":
    main()
