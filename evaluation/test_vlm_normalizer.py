import pytest
from vlm_normalizer import (
    normalize_vietnamese_date,
    normalize_vietnamese_name,
    check_date_consistency,
)


def test_normalize_vietnamese_date_formats():
    # Standard DD/MM/YYYY
    d, amb = normalize_vietnamese_date("15/10/2026")
    assert d == "2026-10-15"
    assert amb is False

    # Ambiguous date (day <= 12 and month <= 12 and day != month)
    d, amb = normalize_vietnamese_date("10/11/2026")
    assert d == "2026-11-10"
    assert amb is True

    # Same day & month
    d, amb = normalize_vietnamese_date("05/05/2026")
    assert d == "2026-05-05"
    assert amb is False

    # Vietnamese words: ngày 20 tháng 11 năm 2026
    d, amb = normalize_vietnamese_date("ngày 20 tháng 11 năm 2026")
    assert d == "2026-11-20"
    assert amb is False

    # 2-digit year: 20/11/26 -> 2026-11-20
    d, amb = normalize_vietnamese_date("20-11-26")
    assert d == "2026-11-20"
    assert amb is False

    # ISO format YYYY-MM-DD
    d, amb = normalize_vietnamese_date("2026-12-25")
    assert d == "2026-12-25"
    assert amb is False

    # Invalid / unparseable
    d, amb = normalize_vietnamese_date("chữ mờ không đọc được")
    assert d is None
    assert amb is False


def test_normalize_vietnamese_name():
    assert normalize_vietnamese_name("Nguyễn Văn A") == "nguyen van a"
    assert normalize_vietnamese_name("ĐẶNG THỊ THU HƯƠNG") == "dang thi thu huong"
    assert normalize_vietnamese_name("  Lê   Văn   Nam  ") == "le van nam"
    assert normalize_vietnamese_name(None) is None
    assert normalize_vietnamese_name("") is None


def test_check_date_consistency():
    warn = check_date_consistency("15/10/2026", "2026-10-15")
    assert warn is None

    warn = check_date_consistency("15/10/2026", "2026-10-16")
    assert warn is not None
    assert "DATE_RAW_NORMALIZED_INCONSISTENT" in warn
