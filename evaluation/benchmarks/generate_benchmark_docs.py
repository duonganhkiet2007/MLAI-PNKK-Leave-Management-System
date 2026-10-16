import os
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Output directories
OUTPUT_DIR = Path('/workingspace_aiclub/WorkingSpace/Personal/phongnh/MLAI/reports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Helper function to style Word tables
def style_table_cell(cell, bg_color=None, bold=False, font_size=10, text_color=None, align=WD_ALIGN_PARAGRAPH.LEFT):
    tcPr = cell._tc.get_or_add_tcPr()
    if bg_color:
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg_color}"/>')
        tcPr.append(shading)
    
    # Padding
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:left w:w="160" w:type="dxa"/><w:right w:w="160" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    
    for p in cell.paragraphs:
        p.alignment = align
        for r in p.runs:
            r.font.name = "Arial"
            r.font.size = Pt(font_size)
            r.font.bold = bold
            if text_color:
                r.font.color.rgb = text_color

def set_table_borders(table, color="D1D5DB", sz="4", val="single"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

# -------------------------------------------------------------
# TABLE 1 DATA
# -------------------------------------------------------------
t1_headers = [
    "Chỉ số đo lường", 
    "Thao tác Thủ công (Người dùng)", 
    "Pipeline AI Tự động hóa", 
    "Tốc độ Tăng & Hiệu quả"
]
t1_rows = [
    [
        "Tổng thời gian hoàn thành (130 đơn)", 
        "4.952,0 giây (~1,38 giờ)", 
        "2,701 giây (Tuần tự)\n6,540 giây (Song song 5 luồng)", 
        "Nhanh hơn 1.833,4 LẦN (Tuần tự)\nNhanh hơn 757,2 LẦN (Song song)"
    ],
    [
        "Thời gian trung bình mỗi đơn", 
        "35,4 giây", 
        "19,29 mili-giây (ms)", 
        "Nhanh hơn 1.833,6 lần"
    ],
    [
        "Quy trình truyền thống (E2E có duyệt tay)", 
        "30.152,0 giây (~8,38 giờ)", 
        "2,701 giây", 
        "Nhanh hơn 11.163,3 LẦN"
    ],
    [
        "Tổng thời gian tiết kiệm được", 
        "—", 
        "4.949,3 giây (~1,37 giờ)", 
        "Cắt giảm 99,95% độ trễ"
    ],
    [
        "Thông lượng xử lý (Throughput)", 
        "~0,03 đơn/giây", 
        "21,41 đơn/giây", 
        "Năng lực xử lý gấp 713,7 lần"
    ]
]

# -------------------------------------------------------------
# TABLE 2 DATA
# -------------------------------------------------------------
t2_headers = [
    "Mã", 
    "Mô tả kịch bản nghiệp vụ", 
    "Số đơn", 
    "Đơn có chứng từ", 
    "Thời gian Thủ công (s)", 
    "Thời gian Pipeline (s)", 
    "Tốc độ Tăng", 
    "Độ khớp Chính sách"
]
t2_rows = [
    ["VAL", "Đơn hợp lệ tiêu chuẩn (1–2 ngày tự duyệt)", "20", "0", "705,8s", "0,388s", "1.821,1x", "100,0%"],
    ["BAL", "Đơn kiểm tra giới hạn số dư phép năm", "10", "0", "377,9s", "0,207s", "1.828,5x", "100,0%"],
    ["NOT", "Đơn kiểm tra quy tắc thời hạn báo trước", "10", "0", "289,8s", "0,199s", "1.457,4x", "80,0%"],
    ["QUO", "Đơn vượt hạn mức vắng mặt của phòng ban", "10", "0", "246,6s", "0,188s", "1.313,2x", "0,0%"],
    ["EXC", "Đơn thuộc thẩm quyền cấp quản lý / ngoại lệ", "15", "6", "619,0s", "0,306s", "2.022,1x", "100,0%"],
    ["PRF", "Đơn thẩm định chứng từ y tế / luật định", "15", "10", "680,0s", "0,271s", "2.505,3x", "100,0%"],
    ["MIS", "Đơn sai lệch thông tin chứng từ / nghi vấn", "15", "15", "806,9s", "0,286s", "2.816,3x", "33,3%"],
    ["DUP", "Đơn trùng lặp thời gian nghỉ đã duyệt", "10", "0", "245,1s", "0,193s", "1.269,8x", "0,0%"],
    ["BND", "Đơn trường hợp biên (lễ, tết, cuối tuần)", "15", "1", "392,2s", "0,283s", "1.387,6x", "86,7%"],
    ["LNG", "Đơn nộp bằng ngôn ngữ tự nhiên (NLP)", "20", "0", "588,8s", "0,380s", "1.549,4x", "20,0%"],
]

# -------------------------------------------------------------
# TABLE 3 DATA
# -------------------------------------------------------------
t3_headers = [
    "Nhóm hồ sơ kiểm định", 
    "Số lượng đơn", 
    "Thời gian Thao tác Thủ công", 
    "Thời gian Pipeline Tự động", 
    "Hệ số Tăng tốc"
]
t3_rows = [
    ["Hồ sơ có đính kèm chứng từ (Nghỉ ốm, thai sản, cưới hỏi, tai nạn)", "32", "1.767,5 giây (~29,5 phút)", "0,628 giây", "Nhanh hơn 2.812,7 LẦN"],
    ["Hồ sơ thường quy / không chứng từ (Phép năm, nghỉ không lương)", "108", "3.184,5 giây (~53,1 phút)", "2,073 giây", "Nhanh hơn 1.536,5 LẦN"],
]

# -------------------------------------------------------------
# CREATE WORD DOCUMENT (FULL REPORT)
# -------------------------------------------------------------
doc = Document()
for s in doc.sections:
    s.top_margin = Inches(0.8)
    s.bottom_margin = Inches(0.8)
    s.left_margin = Inches(0.8)
    s.right_margin = Inches(0.8)

# Title
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = title.add_run("BÁO CÁO KẾT QUẢ ĐỐI SÁNH HIỆU NĂNG (BENCHMARK)")
r.font.name = "Arial"
r.font.size = Pt(17)
r.font.bold = True
r.font.color.rgb = RGBColor(30, 58, 138) # Deep navy

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r_sub = sub.add_run("So sánh Thời gian Thao tác Thủ công vs Pipeline AI Tự động hóa duyệt đơn nghỉ phép\nBộ dữ liệu: 130 ca kiểm thử (STAFF_TEST_CASES) & 32 mẫu chứng từ y tế/hành chính")
r_sub.font.name = "Arial"
r_sub.font.size = Pt(10.5)
r_sub.font.italic = True
r_sub.font.color.rgb = RGBColor(100, 116, 139)

doc.add_paragraph().paragraph_format.space_after = Pt(10)

def add_styled_table(doc, headers, rows, col_widths=None):
    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl)
    
    # Header
    hdr_cells = tbl.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        style_table_cell(hdr_cells[i], bg_color="1E3A8A", bold=True, font_size=10, text_color=RGBColor(255, 255, 255), align=WD_ALIGN_PARAGRAPH.CENTER)
    
    # Rows
    for r_idx, row in enumerate(rows):
        row_cells = tbl.rows[r_idx + 1].cells
        bg = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row):
            row_cells[c_idx].text = str(val)
            align = WD_ALIGN_PARAGRAPH.LEFT if c_idx < 2 else WD_ALIGN_PARAGRAPH.CENTER
            bold = (c_idx == 0 or c_idx == len(row) - 1)
            style_table_cell(row_cells[c_idx], bg_color=bg, bold=bold, font_size=9.5, align=align)

    if col_widths:
        for row in tbl.rows:
            for i, w in enumerate(col_widths):
                row.cells[i].width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(14)
    return tbl

# Section 1
h1 = doc.add_heading(level=2)
r1 = h1.add_run("Bảng 1: Tổng quan Kết quả Đối sánh Thời gian (Headline Results)")
r1.font.name = "Arial"
r1.font.color.rgb = RGBColor(15, 23, 42)
add_styled_table(doc, t1_headers, t1_rows, [1.8, 1.8, 1.8, 1.8])

# Section 2
h2 = doc.add_heading(level=2)
r2 = h2.add_run("Bảng 2: Chi tiết theo 10 Nhóm Kịch bản Nghiệp vụ (Category Breakdown)")
r2.font.name = "Arial"
r2.font.color.rgb = RGBColor(15, 23, 42)
add_styled_table(doc, t2_headers, t2_rows, [0.6, 2.2, 0.6, 0.8, 0.9, 0.9, 0.7, 0.8])

# Section 3
h3 = doc.add_heading(level=2)
r3 = h3.add_run("Bảng 3: So sánh Đơn có Chứng từ vs Đơn không cần Chứng từ")
r3.font.name = "Arial"
r3.font.color.rgb = RGBColor(15, 23, 42)
add_styled_table(doc, t3_headers, t3_rows, [2.5, 0.8, 1.6, 1.1, 1.2])

full_doc_path = OUTPUT_DIR / "Bao_Cao_Benchmark_Thoi_Gian_3_Bang.docx"
doc.save(str(full_doc_path))
print(f"Created Word Document: {full_doc_path}")

# -------------------------------------------------------------
# CREATE 3 INDIVIDUAL WORD DOCS
# -------------------------------------------------------------
def create_single_table_doc(filename, title_text, headers, rows, col_widths):
    d = Document()
    for s in d.sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)
    
    t_p = d.add_paragraph()
    t_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_t = t_p.add_run(title_text)
    r_t.font.name = "Arial"
    r_t.font.size = Pt(14)
    r_t.font.bold = True
    r_t.font.color.rgb = RGBColor(30, 58, 138)
    d.add_paragraph().paragraph_format.space_after = Pt(10)
    
    add_styled_table(d, headers, rows, col_widths)
    p = OUTPUT_DIR / filename
    d.save(str(p))
    print(f"Created: {p}")

create_single_table_doc("Bang_1_Tong_Quan_Benchmark.docx", "BẢNG 1: TỔNG QUAN KẾT QUẢ ĐỐI SÁNH THỜI GIAN", t1_headers, t1_rows, [1.8, 1.8, 1.8, 1.8])
create_single_table_doc("Bang_2_Chi_Tiet_10_Nhom_Kich_Ban.docx", "BẢNG 2: CHI TIẾT THEO 10 NHÓM KỊCH BẢN KIỂM THỬ", t2_headers, t2_rows, [0.6, 2.2, 0.6, 0.8, 0.9, 0.9, 0.7, 0.8])
create_single_table_doc("Bang_3_So_Sanh_Chung_Tu.docx", "BẢNG 3: SO SÁNH ĐƠN CÓ CHỨNG TỪ VS KHÔNG CHỨNG TỪ", t3_headers, t3_rows, [2.5, 0.8, 1.6, 1.1, 1.2])

# -------------------------------------------------------------
# CREATE EXCEL WORKBOOK (3 TABS)
# -------------------------------------------------------------
wb = openpyxl.Workbook()
wb.remove(wb.active) # Remove default sheet

def add_excel_sheet(wb, title, headers, rows):
    ws = wb.create_sheet(title=title)
    ws.views.sheetView[0].showGridLines = True
    
    # Header styling
    hdr_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    hdr_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )
    
    ws.append(headers)
    ws.row_dimensions[1].height = 28
    
    for col_idx, cell in enumerate(ws[1], start=1):
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = center_align
        cell.border = thin_border
        
    for r_idx, row in enumerate(rows, start=2):
        ws.append(row)
        ws.row_dimensions[r_idx].height = 24
        fill_color = "F8FAFC" if r_idx % 2 == 1 else "FFFFFF"
        row_fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
        
        for col_idx, cell in enumerate(ws[r_idx], start=1):
            cell.font = Font(name="Arial", size=10, bold=(col_idx == 1 or col_idx == len(row)))
            cell.fill = row_fill
            cell.border = thin_border
            cell.alignment = left_align if col_idx <= 2 else center_align

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 15)

add_excel_sheet(wb, "Tổng Quan Benchmark", t1_headers, t1_rows)
add_excel_sheet(wb, "10 Nhóm Kịch Bản", t2_headers, t2_rows)
add_excel_sheet(wb, "So Sánh Chứng Từ", t3_headers, t3_rows)

excel_path = OUTPUT_DIR / "Bao_Cao_Benchmark_Thoi_Gian_3_Bang.xlsx"
wb.save(str(excel_path))
print(f"Created Excel Workbook: {excel_path}")

# -------------------------------------------------------------
# CREATE STANDALONE MARKDOWN FILE
# -------------------------------------------------------------
md_content = """# BÁO CÁO KẾT QUẢ ĐỐI SÁNH HIỆU NĂNG (BENCHMARK)
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
"""

md_path = OUTPUT_DIR / "Bao_Cao_Benchmark_Thoi_Gian_3_Bang.md"
with open(md_path, "w", encoding="utf-8") as f:
    f.write(md_content)
print(f"Created Markdown File: {md_path}")
