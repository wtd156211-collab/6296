"""逐格判型与列级类型判定，口径见 README 第二节。"""

import re

TYPE_PRIORITY = ("bool", "int", "float", "date", "text")

_INT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)")
_FLOAT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+")
_DATE_NUM_RE = re.compile(r"([0-9]{4})([-/.])([0-9]{1,2})\2([0-9]{1,2})")
_DATE_CJK_RE = re.compile(r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日")

ASCII_WHITESPACE = " \t\r\n"

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _valid_date(year, month, day):
    if not (1 <= year <= 9999 and 1 <= month <= 12):
        return False
    limit = _MONTH_DAYS[month - 1]
    if month == 2 and _is_leap(year):
        limit += 1
    return 1 <= day <= limit


def _normalize_float(text):
    int_part, frac_part = text.split(".")
    frac_part = frac_part.rstrip("0")
    normalized = int_part if not frac_part else int_part + "." + frac_part
    if normalized == "-0":
        normalized = "0"
    return normalized


def classify(raw):
    """对单个字段判型并给出规范化值。

    返回 (kind, normalized)；kind 为 TYPE_PRIORITY 之一，空值返回 (None, "")。
    """
    text = raw.strip(ASCII_WHITESPACE)
    if not text:
        return None, ""
    first = text[0]
    if first in "tTfF":
        lowered = text.lower()
        if lowered == "true" or lowered == "false":
            return "bool", lowered
    elif first in "0123456789-":
        if _INT_RE.fullmatch(text):
            return "int", "0" if text == "-0" else text
        if _FLOAT_RE.fullmatch(text):
            return "float", _normalize_float(text)
        match = _DATE_NUM_RE.fullmatch(text)
        if match:
            year, month, day = int(match[1]), int(match[3]), int(match[4])
        else:
            match = _DATE_CJK_RE.fullmatch(text)
            if match:
                year, month, day = int(match[1]), int(match[2]), int(match[3])
        if match and _valid_date(year, month, day):
            return "date", "%04d-%02d-%02d" % (year, month, day)
    return "text", text


def dominant_type(counts):
    """计数最大者；并列时取优先级高者（TYPE_PRIORITY 靠前优先）。"""
    best = None
    best_count = -1
    for kind in TYPE_PRIORITY:
        count = counts.get(kind, 0)
        if count > best_count:
            best = kind
            best_count = count
    return best


def column_type(counts, non_null_count):
    """按列级规则给出列类型：empty / unknown / 五型之一 / mixed。"""
    if non_null_count == 0:
        return "empty"
    if non_null_count < 3:
        return "unknown"
    present = {kind for kind, count in counts.items() if count > 0}
    if present == {"int", "float"}:
        return "float"
    if len(present) == 1:
        return next(iter(present))
    dominant = dominant_type(counts)
    if counts[dominant] * 100 >= 75 * non_null_count:
        return dominant
    return "mixed"
