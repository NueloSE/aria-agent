"""Normalizers for CMC's display-string formats (observed in Stage-1 fixtures):
USD values arrive like "2.15 T" / "75.6 B" / "294.15 M", percentages like
"+0.24838%" / "-3.86%". Strategy gates need real numbers; the brain gets both."""
from __future__ import annotations

import re
from typing import Optional

_SCALE = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_USD_RE = re.compile(r"^\s*\$?\s*([+-]?[0-9][0-9,]*\.?[0-9]*)\s*([KMBT])?\s*$", re.I)


def parse_usd(value: object) -> Optional[float]:
    """'2.15 T' -> 2.15e12, '$75.6B' -> 7.56e10, 1234.5 -> 1234.5. None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _USD_RE.match(str(value))
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").upper()
    return num * _SCALE.get(suffix, 1.0)


def parse_pct(value: object) -> Optional[float]:
    """'+0.24838%' -> 0.24838, '-3.86%' -> -3.86, 1.5 -> 1.5. None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("%", "").replace("+", "")
    try:
        return float(s)
    except ValueError:
        return None


def rows_to_dicts(table: object) -> list[dict]:
    """CMC's table format {'headers': [...], 'rows': [[...], ...]} -> list of dicts.
    Used by quotes (multi-id), narratives, and macro events. Non-tables -> []."""
    if not isinstance(table, dict):
        return []
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    if not headers or not isinstance(rows, list):
        return []
    return [dict(zip(headers, row)) for row in rows]


def parse_float(value: object) -> Optional[float]:
    """Plain numeric strings like '590.63' (TA fields). None if unparseable."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None
