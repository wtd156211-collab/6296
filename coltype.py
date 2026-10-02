"""逐格类型判定与规范化（README 第二节口径）。

五种语法互不重叠，优先级 bool > int > float > date > text。
全程按十进制文本处理，不转二进制浮点。
"""

import re

TYPES = ("bool", "int", "float", "date", "text")

ASCII_WS = " \t\r\n"

_INT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_FLOAT_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]+\Z")
_DATE_NUM_RE = re.compile(r"([0-9]{4})([-/.])([0-9]{1,2})\2([0-9]{1,2})\Z")
_DATE_CJK_RE = re.compile(r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日\Z")

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _valid_date(year, month, day):
    if not (1 <= year <= 9999 and 1 <= month <= 12 and day >= 1):
        return False
    limit = _DAYS_IN_MONTH[month - 1]
    if month == 2 and _is_leap(year):
        limit = 29
    return day <= limit


def _parse_date(value):
    """返回 (y, m, d) 或 None。分隔符 -、/、. 或 年/月/日，一个值内写同一种。"""
    match = _DATE_NUM_RE.match(value)
    if match is not None:
        year, month, day = int(match[1]), int(match[3]), int(match[4])
    else:
        match = _DATE_CJK_RE.match(value)
        if match is None:
            return None
        year, month, day = int(match[1]), int(match[2]), int(match[3])
    if _valid_date(year, month, day):
        return (year, month, day)
    return None


def classify(value):
    """对未去空白的原始字段判型；调用方保证 value 非空（去空白后）。"""
    if value.lower() in ("true", "false"):
        return "bool"
    if _INT_RE.match(value):
        return "int"
    if _FLOAT_RE.match(value):
        return "float"
    if _parse_date(value) is not None:
        return "date"
    return "text"


def normalize(value, cell_type):
    """按判定的类型规范化（value 已去首尾 ASCII 空白）。"""
    if cell_type == "bool":
        return value.lower()
    if cell_type == "int":
        return "0" if value == "-0" else value
    if cell_type == "float":
        head, _, frac = value.partition(".")
        frac = frac.rstrip("0")
        if not frac:
            if head in ("0", "-0"):
                return "0"
            return head
        return head + "." + frac
    if cell_type == "date":
        year, month, day = _parse_date(value)
        return "%04d-%02d-%02d" % (year, month, day)
    return value
