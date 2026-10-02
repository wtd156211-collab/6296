"""流式扫表：逐格判型、逐列汇总、规范化输出、冲突与证据收集。

内存口径：只保留每列计数器与每列每类型最多 20 条证据行号/值，
峰值内存不随行数增长。所有产出对同一输入逐字节确定。
"""

import csv
import json
import os

from coltype import TYPES, ASCII_WS, classify, normalize

EVIDENCE_LIMIT = 20
DOMINANT_PCT = 75
MIN_SAMPLE = 3

PRIORITY = TYPES  # bool > int > float > date > text，仅用于排序与并列取舍


class TableError(Exception):
    """输入表不合法（表头空/重复、字段数不符、编码错误等）。"""


class _Column:
    __slots__ = ("name", "counts", "null_count", "evidence_rows", "evidence_values")

    def __init__(self, name):
        self.name = name
        self.counts = {}            # cell_type -> count（仅非空格）
        self.null_count = 0
        self.evidence_rows = {}     # cell_type -> [row_no, ...] 升序，最多 20
        self.evidence_values = {}   # cell_type -> [stripped_value, ...] 与上行对齐

    def add(self, cell_type, row_no, value):
        if cell_type is None:
            self.null_count += 1
            return
        self.counts[cell_type] = self.counts.get(cell_type, 0) + 1
        rows = self.evidence_rows.setdefault(cell_type, [])
        if len(rows) < EVIDENCE_LIMIT:
            rows.append(row_no)
            self.evidence_values.setdefault(cell_type, []).append(value)

    @property
    def non_null_count(self):
        return sum(self.counts.values())


def decide_column(counts, non_null):
    """列级判定：返回 (column_type, dominant_type)。

    dominant_type 为 None 表示该列无主导（empty/unknown）。
    """
    if non_null == 0:
        return "empty", None
    if non_null < MIN_SAMPLE:
        return "unknown", None
    present = [t for t in PRIORITY if counts.get(t)]
    if set(present) == {"int", "float"}:
        dominant = "int" if counts.get("int", 0) >= counts.get("float", 0) else "float"
        return "float", dominant
    if len(present) == 1:
        return present[0], present[0]
    dominant = max(present, key=lambda t: (counts[t], -PRIORITY.index(t)))
    if counts[dominant] * 100 >= DOMINANT_PCT * non_null:
        return dominant, dominant
    return "mixed", dominant


def _ordered_counts(counts):
    return {t: counts[t] for t in PRIORITY if counts.get(t)}


def _read_header(path):
    """校验编码与表头，返回 (header_names,)。非法输入抛 TableError。"""
    with open(path, "rb") as fh:
        prefix = fh.read(3)
    if prefix.startswith(b"\xef\xbb\xbf"):
        raise TableError("input is UTF-8 with BOM; UTF-8 without BOM is required")
    with open(path, "r", encoding="utf-8", newline="") as fh:
        try:
            for raw in csv.reader(fh):
                header = raw
                break
            else:
                raise TableError("empty csv: no header row")
        except UnicodeDecodeError as exc:
            raise TableError("input is not valid UTF-8: %s" % exc)
    names = [field.strip(ASCII_WS) for field in header]
    for name in names:
        if not name:
            raise TableError("header contains an empty column name")
    if len(set(names)) != len(names):
        raise TableError("header contains duplicate column names")
    return names


def process_table(csv_path, table_name, out_dir):
    """处理一份表，返回 (report_dict, evidence_payload)。

    规范化 CSV 先写临时文件，全部成功后替换目标，失败不留半成品。
    """
    header = _read_header(csv_path)
    columns = [_Column(name) for name in header]
    width = len(header)

    tmp_path = os.path.join(out_dir, table_name + ".normalized.tmp")
    final_path = os.path.join(out_dir, table_name + ".normalized.csv")
    row_count = 0
    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as src, \
                open(tmp_path, "w", encoding="utf-8", newline="") as dst:
            reader = csv.reader(src)
            writer = csv.writer(dst, lineterminator="\n")
            next(reader, None)  # 表头
            writer.writerow(header)
            for fields in reader:
                if len(fields) != width:
                    raise TableError(
                        "row %d has %d fields, expected %d"
                        % (row_count + 1, len(fields), width))
                row_count += 1
                out_row = []
                for index, raw in enumerate(fields):
                    value = raw.strip(ASCII_WS)
                    if not value:
                        columns[index].add(None, row_count, "")
                        out_row.append("")
                        continue
                    cell_type = classify(value)
                    columns[index].add(cell_type, row_count, value)
                    out_row.append(normalize(value, cell_type))
                writer.writerow(out_row)
    except UnicodeDecodeError as exc:
        _silent_remove(tmp_path)
        raise TableError("input is not valid UTF-8: %s" % exc)
    except BaseException:
        _silent_remove(tmp_path)
        raise
    os.replace(tmp_path, final_path)

    report_columns = []
    conflicts = []
    evidence_payload = {}
    for col in columns:
        non_null = col.non_null_count
        column_type, dominant = decide_column(col.counts, non_null)
        report_columns.append({
            "name": col.name,
            "type": column_type,
            "null_count": col.null_count,
            "non_null_count": non_null,
            "type_counts": _ordered_counts(col.counts),
        })
        present = [t for t in PRIORITY if col.counts.get(t)]
        if dominant is not None and len(present) >= 2:
            triples = []
            for cell_type in present:
                if cell_type == dominant:
                    continue
                for row_no, value in zip(col.evidence_rows.get(cell_type, []),
                                         col.evidence_values.get(cell_type, [])):
                    triples.append((row_no, value, cell_type))
            triples.sort(key=lambda item: item[0])
            total = sum(col.counts[t] for t in present if t != dominant)
            conflicts.append({
                "column": col.name,
                "types": present,
                "evidence_count": total,
                "evidence_rows": [item[0] for item in triples[:EVIDENCE_LIMIT]],
            })
            evidence_payload[col.name] = {
                "dominant": dominant,
                "rows": [
                    {"row": row_no, "value": value, "cell_type": cell_type}
                    for row_no, value, cell_type in triples
                ],
            }

    report = {
        "table": table_name + ".csv",
        "row_count": row_count,
        "column_count": width,
        "columns": report_columns,
        "conflicts": conflicts,
    }
    return report, evidence_payload


def _silent_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def write_report_json(report, path):
    text = json.dumps(report, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
        fh.write("\n")
