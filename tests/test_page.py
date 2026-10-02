import json
import os
import re
import tempfile
import unittest

from page import render_html, write_html


def _sample_report():
    return {
        "table": "t.csv",
        "row_count": 4,
        "column_count": 2,
        "columns": [
            {"name": "id", "type": "int", "null_count": 0,
             "non_null_count": 4, "type_counts": {"int": 4}},
            {"name": "v", "type": "mixed", "null_count": 0,
             "non_null_count": 4, "type_counts": {"int": 3, "text": 1}},
        ],
        "conflicts": [
            {"column": "v", "types": ["int", "text"], "evidence_count": 1,
             "evidence_rows": [4]},
        ],
    }


def _sample_evidence():
    return {
        "v": {"dominant": "int",
              "rows": [{"row": 4, "value": "oops", "cell_type": "text"}]},
    }


class PageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_self_contained(self):
        html = render_html(_sample_report(), _sample_evidence())
        for pattern in (r"https?://", r"\bfetch\(", r"<script[^>]*src=",
                        r"<link\b", r"@import", r"\.css\b"):
            self.assertIsNone(re.search(pattern, html), pattern)
        self.assertTrue(html.endswith("\n"))
        self.assertIn('<canvas id="chart">', html)
        self.assertIn("2d", html)

    def test_inline_data_equals_report(self):
        report = _sample_report()
        html = render_html(report, _sample_evidence())
        match = re.search(r"const REPORT = (\{.*?\});\nconst EVIDENCE",
                          html, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match.group(1)), report)

    def test_fixed_palette(self):
        html = render_html(_sample_report(), _sample_evidence())
        for color in ("#4e79a7", "#59a14f", "#f28e2b", "#e15759",
                      "#9c755f", "#e8e8e8", "#d62728"):
            self.assertIn(color, html)

    def test_conflict_and_evidence_rendered(self):
        html = render_html(_sample_report(), _sample_evidence())
        self.assertIn("oops", html)

    def test_no_volatile_content(self):
        first = render_html(_sample_report(), _sample_evidence())
        second = render_html(_sample_report(), _sample_evidence())
        self.assertEqual(first, second)
        for marker in ("Date(", "new Date", "timeStamp", "timestamp"):
            self.assertNotIn(marker, first)

    def test_script_closing_escaped(self):
        report = _sample_report()
        evidence = {"v": {"dominant": "int", "rows": [
            {"row": 4, "value": "</script><img src=x>", "cell_type": "text"}]}}
        html = render_html(report, evidence)
        self.assertNotIn("</script><img", html)

    def test_write_html_file(self):
        path = os.path.join(self.tmp.name, "t.html")
        write_html(_sample_report(), _sample_evidence(), path)
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertTrue(data.endswith(b"\n"))
        self.assertNotIn(b"\r", data)


if __name__ == "__main__":
    unittest.main()
