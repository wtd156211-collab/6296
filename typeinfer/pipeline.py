"""单表处理流水线：流式读取，逐格判型，产出报告、规范化 CSV 与 HTML。"""

import csv
import json
import os

from .core import TYPE_PRIORITY, classify, column_type, dominant_type
from .page import render_html

MAX_EVIDENCE = 20
BOM = b"\xef\xbb\xbf"


class InputError(Exception):
    """输入不合法（表头问题、字段数不一致、非 UTF-8 等）。"""


class ColumnState:
    __slots__ = ("name", "null_count", "counts", "evidence_rows", "evidence_values")

    def __init__(self, name):
        self.name = name
        self.null_count = 0
        self.counts = {}
        self.evidence_rows = {}
        self.evidence_values = {}

    def add(self, kind, normalized, row_no):
        if kind is None:
            self.null_count += 1
            return
        self.counts[kind] = self.counts.get(kind, 0) + 1
        rows = self.evidence_rows.get(kind)
        if rows is None:
            rows = []
            self.evidence_rows[kind] = rows
            self.evidence_values[kind] = []
        if len(rows) < MAX_EVIDENCE:
            rows.append(row_no)
            self.evidence_values[kind].append(normalized)


def _read_header(path):
    with open(path, "rb") as binary:
        if binary.read(3) == BOM:
            raise InputError("%s: 不支持带 BOM 的文件" % path)
    text_stream = open(path, "r", encoding="utf-8", newline="")
    reader = csv.reader(text_stream, strict=True)
    try:
        header = next(reader)
    except StopIteration:
        text_stream.close()
        raise InputError("%s: 空文件，缺少表头" % path)
    except (UnicodeDecodeError, csv.Error) as exc:
        text_stream.close()
        raise InputError("%s: 输入不合法: %s" % (path, exc))
    return text_stream, reader, header


def _build_report(table_name, header, states, row_count):
    columns = []
    conflicts = []
    for state in states:
        non_null = row_count - state.null_count
        resolved = column_type(state.counts, non_null)
        type_counts = {kind: state.counts[kind] for kind in TYPE_PRIORITY if state.counts.get(kind)}
        columns.append({
            "name": state.name,
            "type": resolved,
            "null_count": state.null_count,
            "non_null_count": non_null,
            "type_counts": type_counts,
        })
        present = [kind for kind in TYPE_PRIORITY if state.counts.get(kind)]
        if non_null >= 3 and len(present) >= 2:
            dominant = dominant_type(state.counts)
            rows = []
            for kind in present:
                if kind == dominant:
                    continue
                rows.extend(state.evidence_rows[kind])
            paired = sorted(rows)
            conflicts.append({
                "column": state.name,
                "types": present,
                "evidence_count": non_null - state.counts[dominant],
                "evidence_rows": paired[:MAX_EVIDENCE],
            })
    return {
        "table": table_name,
        "row_count": row_count,
        "column_count": len(header),
        "columns": columns,
        "conflicts": conflicts,
    }


def _evidence_detail(states):
    """供页面使用的证据明细：列名 -> [{row, type, value}]，与 evidence_rows 对齐。"""
    detail = {}
    for state in states:
        total = sum(state.counts.values())
        present = [kind for kind in TYPE_PRIORITY if state.counts.get(kind)]
        if total < 3 or len(present) < 2:
            continue
        dominant = dominant_type(state.counts)
        entries = []
        for kind in TYPE_PRIORITY:
            if kind == dominant or kind not in state.evidence_rows:
                continue
            entries.extend(zip(state.evidence_rows[kind],
                               state.evidence_values[kind],
                               (kind,) * len(state.evidence_rows[kind])))
        entries.sort(key=lambda item: item[0])
        detail[state.name] = [
            {"row": row, "type": kind, "value": value}
            for row, value, kind in entries[:MAX_EVIDENCE]
        ]
    return detail


def process_table(path, out_dir, table_name=None):
    if table_name is None:
        table_name = os.path.basename(path)
    text_stream, reader, raw_header = _read_header(path)
    try:
        header = [name.strip(" \t\r\n") for name in raw_header]
        if any(not name for name in header):
            raise InputError("%s: 表头存在空列名" % path)
        if len(set(header)) != len(header):
            raise InputError("%s: 表头存在重复列名" % path)
        states = [ColumnState(name) for name in header]

        base_name = table_name[:-4] if table_name.endswith(".csv") else table_name
        normalized_path = os.path.join(out_dir, base_name + ".normalized.csv")
        with open(normalized_path, "w", encoding="utf-8", newline="") as normalized_file:
            writer = csv.writer(normalized_file, lineterminator="\n")
            writer.writerow(header)
            row_count = 0
            try:
                for row in reader:
                    if len(row) != len(header):
                        raise InputError(
                            "%s: 第 %d 行字段数 %d 与表头 %d 不一致"
                            % (path, row_count + 1, len(row), len(header)))
                    normalized_row = []
                    for index, field in enumerate(row):
                        kind, normalized = classify(field)
                        states[index].add(kind, normalized, row_count + 1)
                        normalized_row.append(normalized)
                    writer.writerow(normalized_row)
                    row_count += 1
            except (UnicodeDecodeError, csv.Error) as exc:
                raise InputError("%s: 输入不合法: %s" % (path, exc))
    finally:
        text_stream.close()

    report = _build_report(table_name, header, states, row_count)
    detail = _evidence_detail(states)

    json_path = os.path.join(out_dir, base_name + ".json")
    with open(json_path, "w", encoding="utf-8", newline="") as json_file:
        json_file.write(json.dumps(report, ensure_ascii=False, indent=2))
        json_file.write("\n")

    html_path = os.path.join(out_dir, base_name + ".html")
    with open(html_path, "w", encoding="utf-8", newline="") as html_file:
        html_file.write(render_html(report, detail))
    return report
