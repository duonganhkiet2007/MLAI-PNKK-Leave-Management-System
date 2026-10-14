"""Utility module for deterministic normalization of raw extracted VLM fields (dates, patient names).

Adheres to Vietnamese administrative formats:
- Default date format: DD/MM/YYYY
- 2-digit years convention: 2000 + YY
- Ambiguous date flagging: day <= 12 and month <= 12 and day != month
- Full Unicode diacritic stripping for name matching
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional, Tuple


def normalize_vietnamese_date(raw: Optional[str]) -> Tuple[Optional[str], bool]:
    """Parse raw date string into ISO YYYY-MM-DD format.

    Returns:
        (iso_date_str_or_none, is_ambiguous)
    """
    if not raw or not isinstance(raw, str):
        return None, False

    text = raw.strip()
    if not text:
        return None, False

    # First check ISO YYYY-MM-DD
    m_iso = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if m_iso:
        y_str, m_str, d_str = m_iso.groups()
        return _validate_and_format_date(d_str, m_str, y_str)

    # Check for Vietnamese phrase with explicit words: "ngày DD tháng MM năm YYYY"
    m_vn = re.search(
        r"(?:ngày|ngay)\s*(\d{1,2})\s*(?:tháng|thang)\s*(\d{1,2})\s*(?:năm|nam)\s*(\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if m_vn:
        d_str, m_str, y_str = m_vn.groups()
        return _validate_and_format_date(d_str, m_str, y_str)

    # Standard slash/hyphen/dot patterns: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m_dmy = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", text)
    if m_dmy:
        d_str, m_str, y_str = m_dmy.groups()
        return _validate_and_format_date(d_str, m_str, y_str)

    return None, False


def _validate_and_format_date(
    d_str: str, m_str: str, y_str: str, assume_dmy: bool = True
) -> Tuple[Optional[str], bool]:
    try:
        d = int(d_str)
        m = int(m_str)
        y = int(y_str)
    except (ValueError, TypeError):
        return None, False

    # 2-digit year conversion: 2000 + yy
    if y < 100:
        y = 2000 + y

    # Sanity checks
    if not (1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
        return None, False

    try:
        dt = date(y, m, d)
    except ValueError:
        return None, False

    is_ambiguous = (d <= 12 and m <= 12 and d != m)
    return dt.isoformat(), is_ambiguous


def normalize_vietnamese_name(name: Optional[str]) -> Optional[str]:
    """Normalize a Vietnamese person name:
    - Unicode NFD normalization + strip combining diacritics
    - Map đ/Đ -> d/D
    - Lowercase, strip punctuation, collapse whitespace
    """
    if not name or not isinstance(name, str):
        return None

    s = name.strip()
    if not s:
        return None

    # Replace specific Vietnamese consonants before NFD
    s = s.replace("đ", "d").replace("Đ", "D")
    # Decompose Unicode
    s = unicodedata.normalize("NFD", s)
    # Strip diacritics
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Lowercase
    s = s.lower()
    # Strip non-alphanumeric except spaces
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    # Collapse multiple spaces
    s = " ".join(s.split())
    return s or None


def check_date_consistency(raw_date: Optional[str], normalized_date: Optional[str]) -> Optional[str]:
    """Compare date extracted directly by VLM vs date parsed from _raw string.
    Returns warning message if inconsistency detected, else None.
    """
    if not raw_date or not normalized_date:
        return None

    parsed_from_raw, _ = normalize_vietnamese_date(raw_date)
    if parsed_from_raw and parsed_from_raw != normalized_date:
        return (
            f"DATE_RAW_NORMALIZED_INCONSISTENT: raw '{raw_date}' parsed to '{parsed_from_raw}', "
            f"but direct field had '{normalized_date}'"
        )
    return None
