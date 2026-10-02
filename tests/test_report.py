import csv
import json
import os
import tempfile
import unittest

from report import TableError, decide_column, process_table, write_report_json


class DecideColumnTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(decide_column({}, 0), ("empty", None))

    def test_unknown_when_sample_too_small(self):
        self.assertEqual(decide_column({"int": 2}, 2), ("unknown", None))

    def test_single_type(self):
        self.assertEqual(decide_column({"int": 3}, 3), ("int", "int"))

    def test_int_float_promotion_still_conflict(self):
        column_type, dominant = decide_column({"int": 5, "float": 5}, 10)
        self.assertEqual(column_type, "float")
        self.assertEqual(dominant, "int")  # 并列取优先级高者

    def test_dominant_at_exactly_75_percent(self):
        column_type, _ = decide_column({"bool": 9, "text": 3}, 12)
        self.assertEqual(column_type, "bool")

    def test_mixed_below_75_percent(self):
        column_type, dominant = decide_column({"text": 7, "date": 3}, 10)
        self.assertEqual(column_type, "mixed")
        self.assertEqual(dominant, "text")


class ProcessTableTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.in_dir = os.path.join(self.tmp.name, "in")
        self.out_dir = os.path.join(self.tmp.name, "out")
        os.makedirs(self.in_dir)
        os.makedirs(self.out_dir)

    def _write(self, name, rows):
        path = os.path.join(self.in_dir, name)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerows(rows)
        return path

    def test_conflict_evidence_rows_match_source(self):
        # 异常值放在第 3、7 行（数据行号，从 1 起）
        rows = [["id", "val"]] + [[str(i), "1.5" if i in (3, 7) else str(i)]
                                  for i in range(1, 11)]
        path = self._write("t.csv", rows)
        report, evidence = process_table(path, "t", self.out_dir)
        self.assertEqual(report["row_count"], 10)
        col = report["columns"][1]
        self.assertEqual(col["type"], "float")  # int+float 数值提升
        self.assertEqual(col["type_counts"], {"int": 8, "float": 2})
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["column"], "val")
        self.assertEqual(conflict["types"], ["int", "float"])
        self.assertEqual(conflict["evidence_count"], 2)
        self.assertEqual(conflict["evidence_rows"], [3, 7])
        ev_rows = evidence["val"]["rows"]
        self.assertEqual([r["row"] for r in ev_rows], [3, 7])
        self.assertEqual([r["value"] for r in ev_rows], ["1.5", "1.5"])
        self.assertEqual([r["cell_type"] for r in ev_rows], ["float", "float"])

    def test_evidence_capped_at_20(self):
        rows = [["v"]] + [["x"] if i <= 30 else ["1"] for i in range(1, 71)]
        path = self._write("t.csv", rows)
        report, evidence = process_table(path, "t", self.out_dir)
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["evidence_count"], 30)
        self.assertEqual(len(conflict["evidence_rows"]), 20)
        self.assertEqual(conflict["evidence_rows"], list(range(1, 21)))
        self.assertEqual(len(evidence["v"]["rows"]), 20)

    def test_empty_and_unknown_not_in_conflicts(self):
        rows = [["a", "b", "c"], ["1", "", "x"], ["2", "", "y"], ["3", "", ""]]
        path = self._write("t.csv", rows)
        report, _ = process_table(path, "t", self.out_dir)
        types = {c["name"]: c["type"] for c in report["columns"]}
        self.assertEqual(types, {"a": "int", "b": "empty", "c": "unknown"})
        self.assertEqual(report["conflicts"], [])

    def test_nulls_not_counted_and_stripped(self):
        rows = [["v"], [" 1 "], [""], ["\t"], ["2"], ["3"]]
        path = self._write("t.csv", rows)
        report, _ = process_table(path, "t", self.out_dir)
        col = report["columns"][0]
        self.assertEqual(col["null_count"], 2)
        self.assertEqual(col["non_null_count"], 3)
        self.assertEqual(col["type"], "int")
        with open(os.path.join(self.out_dir, "t.normalized.csv"),
                  encoding="utf-8", newline="") as fh:
            parsed = list(csv.reader(fh))
        self.assertEqual(parsed, [["v"], ["1"], [""], [""], ["2"], ["3"]])

    def test_normalized_quoting(self):
        rows = [["note"], ["plain"], ["with,comma"], ['say "hi"'], ["multi\nline"]]
        path = self._write("t.csv", rows)
        process_table(path, "t", self.out_dir)
        with open(os.path.join(self.out_dir, "t.normalized.csv"),
                  encoding="utf-8", newline="") as fh:
            parsed = list(csv.reader(fh))
        self.assertEqual(parsed, rows)

    def test_ragged_rows_rejected(self):
        path = self._write("t.csv", [["a", "b"], ["1", "2", "3"]])
        with self.assertRaises(TableError):
            process_table(path, "t", self.out_dir)
        self.assertFalse(os.path.exists(
            os.path.join(self.out_dir, "t.normalized.csv")))

    def test_bad_headers_rejected(self):
        for header in (["", "b"], ["a", "a"], [" ", "b"]):
            path = self._write("t.csv", [header, ["1", "2"]])
            with self.assertRaises(TableError, msg=repr(header)):
                process_table(path, "t", self.out_dir)

    def test_bom_rejected(self):
        path = os.path.join(self.in_dir, "t.csv")
        with open(path, "wb") as fh:
            fh.write(b"\xef\xbb\xbfa,b\n1,2\n")
        with self.assertRaises(TableError):
            process_table(path, "t", self.out_dir)

    def test_non_utf8_rejected(self):
        path = os.path.join(self.in_dir, "t.csv")
        with open(path, "wb") as fh:
            fh.write("a,b\n1,\xff\xfe\n".encode("latin-1"))
        with self.assertRaises(TableError):
            process_table(path, "t", self.out_dir)

    def test_json_format_stable(self):
        rows = [["a"], ["1"], ["2"], ["3"]]
        path = self._write("t.csv", rows)
        report, _ = process_table(path, "t", self.out_dir)
        out = os.path.join(self.out_dir, "t.json")
        write_report_json(report, out)
        with open(out, "rb") as fh:
            data = fh.read()
        self.assertTrue(data.endswith(b"\n"))
        self.assertNotIn(b"\r", data)
        self.assertEqual(json.loads(data.decode("utf-8")), report)
        self.assertEqual(list(report.keys()),
                         ["table", "row_count", "column_count",
                          "columns", "conflicts"])
        self.assertEqual(list(report["columns"][0].keys()),
                         ["name", "type", "null_count", "non_null_count",
                          "type_counts"])

    def test_whitespace_only_cells_are_null(self):
        rows = [["v"], ["  "], ["\t\r\n"], ["1"], ["2"], ["3"]]
        path = self._write("t.csv", rows)
        report, _ = process_table(path, "t", self.out_dir)
        self.assertEqual(report["columns"][0]["null_count"], 2)


if __name__ == "__main__":
    unittest.main()
