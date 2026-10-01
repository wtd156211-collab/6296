import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from typeinfer.core import classify, column_type, dominant_type  # noqa: E402
from typeinfer.pipeline import InputError, process_table  # noqa: E402

TABLES_DIR = os.path.join(ROOT, "samples", "tables")
EXPECTED_DIR = os.path.join(ROOT, "samples", "expected")


class ClassifyTest(unittest.TestCase):
    def check(self, raw, kind, normalized):
        self.assertEqual(classify(raw), (kind, normalized))

    def test_basic_types(self):
        self.check("1", "int", "1")
        self.check("0", "int", "0")
        self.check("-12", "int", "-12")
        self.check("19.90", "float", "19.9")
        self.check("0.10", "float", "0.1")
        self.check("2.00", "float", "2")
        self.check("-0.0", "float", "0")
        self.check("true", "bool", "true")
        self.check("FALSE", "bool", "false")
        self.check("  hello ", "text", "hello")
        self.check("", None, "")
        self.check(" \t\r\n", None, "")

    def test_text_fallbacks(self):
        for raw in ("007", "+3", "1e3", ".5", "1.", "yes", "no", "NULL", "NA", "1,000"):
            self.assertEqual(classify(raw), ("text", raw.strip()))

    def test_ints_normalization(self):
        self.check("-0", "int", "0")
        self.check("010", "text", "010")

    def test_dates(self):
        self.check("2024-03-05", "date", "2024-03-05")
        self.check("2024/3/5", "date", "2024-03-05")
        self.check("2024.3.5", "date", "2024-03-05")
        self.check("2024年3月5日", "date", "2024-03-05")
        self.check("2024年03月17日", "date", "2024-03-17")
        self.check("2024-02-29", "date", "2024-02-29")
        self.check("2023-02-29", "text", "2023-02-29")
        self.check("2024-13-01", "text", "2024-13-01")
        self.check("2024/04/31", "text", "2024/04/31")
        self.check("0000-01-01", "text", "0000-01-01")
        self.check("2024-1.01", "text", "2024-1.01")

    def test_one_minus_zero_float(self):
        self.assertEqual(classify("-0.5"), ("float", "-0.5"))
        self.assertEqual(classify("-0.000"), ("float", "0"))


class ColumnTypeTest(unittest.TestCase):
    def test_empty_and_unknown(self):
        self.assertEqual(column_type({}, 0), "empty")
        self.assertEqual(column_type({"int": 1}, 1), "unknown")
        self.assertEqual(column_type({"int": 2}, 2), "unknown")

    def test_int_float_promotion(self):
        self.assertEqual(column_type({"int": 5, "float": 5}, 10), "float")
        self.assertEqual(column_type({"int": 1, "float": 9}, 10), "float")

    def test_dominant_and_mixed(self):
        self.assertEqual(column_type({"bool": 8, "text": 2}, 10), "bool")
        self.assertEqual(column_type({"date": 3, "text": 7}, 10), "mixed")
        self.assertEqual(column_type({"int": 3, "text": 1}, 4), "int")
        self.assertEqual(column_type({"int": 2, "text": 1}, 3), "mixed")

    def test_dominant_tie_uses_priority(self):
        self.assertEqual(dominant_type({"bool": 2, "text": 2}), "bool")
        self.assertEqual(dominant_type({"int": 5, "float": 5}), "int")


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_pipeline(self):
        for name in sorted(os.listdir(TABLES_DIR)):
            process_table(os.path.join(TABLES_DIR, name), self.tmp, name)

    def test_samples_byte_identical(self):
        self.run_pipeline()
        for name in sorted(os.listdir(EXPECTED_DIR)):
            with open(os.path.join(EXPECTED_DIR, name), "rb") as expected, \
                 open(os.path.join(self.tmp, name), "rb") as actual:
                self.assertEqual(actual.read(), expected.read(), "文件不一致: %s" % name)

    def test_report_shape(self):
        self.run_pipeline()
        with open(os.path.join(self.tmp, "01-numeric-mix.json"), encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual(report["table"], "01-numeric-mix.csv")
        self.assertEqual(report["row_count"], 10)
        self.assertEqual(report["columns"][2]["type"], "float")
        self.assertEqual(report["conflicts"][0]["evidence_rows"], [1, 3, 5, 7, 10])

    def test_evidence_rows_are_original_line_numbers(self):
        self.run_pipeline()
        with open(os.path.join(self.tmp, "04-tail-outlier.json"), encoding="utf-8") as f:
            report = json.load(f)
        self.assertEqual(report["conflicts"][0]["evidence_rows"], [11])
        self.assertEqual(report["conflicts"][2]["evidence_rows"], [11, 12])

    def test_deterministic_outputs(self):
        self.run_pipeline()
        first = {}
        for name in os.listdir(self.tmp):
            with open(os.path.join(self.tmp, name), "rb") as f:
                first[name] = f.read()
        shutil.rmtree(self.tmp)
        os.makedirs(self.tmp)
        self.run_pipeline()
        self.assertEqual(sorted(os.listdir(self.tmp)), sorted(first))
        for name, content in first.items():
            with open(os.path.join(self.tmp, name), "rb") as f:
                self.assertEqual(f.read(), content, "重跑结果不一致: %s" % name)

    def test_html_self_contained_and_matches_report(self):
        self.run_pipeline()
        with open(os.path.join(self.tmp, "01-numeric-mix.html"), encoding="utf-8") as f:
            html = f.read()
        for forbidden in ("http://", "https://", "<link", "fetch(", "src="):
            self.assertNotIn(forbidden, html)
        with open(os.path.join(self.tmp, "01-numeric-mix.json"), encoding="utf-8") as f:
            report = json.load(f)
        marker = "const REPORT = "
        start = html.index(marker) + len(marker)
        end = html.index(";\nconst EVIDENCE", start)
        self.assertEqual(json.loads(html[start:end]), report)
        marker = "const EVIDENCE = "
        start2 = html.index(marker) + len(marker)
        end2 = html.index(";\nconst TYPE_COLORS", start2)
        evidence = json.loads(html[start2:end2])
        self.assertEqual(evidence["unit_price"][0]["row"], 1)

    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return path

    def test_duplicate_header_rejected(self):
        path = self._write("bad.csv", "a,a\n1,2\n")
        with self.assertRaises(InputError):
            process_table(path, self.tmp, "bad.csv")

    def test_field_count_mismatch_rejected(self):
        path = self._write("bad.csv", "a,b\n1,2,3\n")
        with self.assertRaises(InputError):
            process_table(path, self.tmp, "bad.csv")

    def test_bom_rejected(self):
        path = os.path.join(self.tmp, "bom.csv")
        with open(path, "wb") as f:
            f.write(b"\xef\xbb\xbfa,b\n1,2\n")
        with self.assertRaises(InputError):
            process_table(path, self.tmp, "bom.csv")

    def test_non_utf8_rejected(self):
        path = os.path.join(self.tmp, "latin.csv")
        with open(path, "wb") as f:
            f.write(b"a,b\n1,\xff\n")
        with self.assertRaises(InputError):
            process_table(path, self.tmp, "latin.csv")

    def test_cli_exit_codes(self):
        env = dict(os.environ, PYTHONPATH=ROOT)
        bad = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"),
             "--tables", os.path.join(self.tmp, "missing"), "--out", self.tmp],
            capture_output=True, env=env)
        self.assertEqual(bad.returncode, 2)
        good = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"),
             "--tables", TABLES_DIR, "--out", os.path.join(self.tmp, "out")],
            capture_output=True, env=env)
        self.assertEqual(good.returncode, 0, good.stderr)


if __name__ == "__main__":
    unittest.main()
