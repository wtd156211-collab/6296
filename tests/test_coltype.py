import unittest

from coltype import classify, normalize


class ClassifyTest(unittest.TestCase):
    def test_bool(self):
        for value in ("true", "false", "TRUE", "False", "tRuE"):
            self.assertEqual(classify(value), "bool", value)

    def test_int(self):
        for value in ("0", "1", "-1", "42", "-300", "1000000"):
            self.assertEqual(classify(value), "int", value)

    def test_int_rejects(self):
        for value in ("007", "01", "+3", "1e3", "-", "--1", "1 ", " 1"):
            self.assertNotEqual(classify(value), "int", value)

    def test_float(self):
        for value in ("0.5", "-0.5", "2.00", "10.25", "-3.140"):
            self.assertEqual(classify(value), "float", value)

    def test_float_rejects(self):
        for value in (".5", "1.", "+1.5", "1.5e3", "00.5", "01.5"):
            self.assertNotEqual(classify(value), "float", value)

    def test_date_separators(self):
        for value in ("2024-03-05", "2024/3/5", "2024.03.05",
                      "2024年3月5日", "2024年03月05日", "0001-01-01",
                      "9999-12-31", "2024-02-29", "2000-02-29"):
            self.assertEqual(classify(value), "date", value)

    def test_date_rejects(self):
        for value in ("2023-02-29", "1900-02-29", "2024-02-30", "2024-13-01",
                      "2024-00-10", "2024-01-00", "2024-04-31", "0000-01-01",
                      "2024-03/05", "2024年3月5", "202-03-05", "20240-03-05",
                      "2024年03月05", "2024-3-5 "):
            self.assertEqual(classify(value), "text", value)

    def test_text_fallback(self):
        for value in ("yes", "no", "NULL", "NA", "abc", "1.2.3", "true1"):
            self.assertEqual(classify(value), "text", value)


class NormalizeTest(unittest.TestCase):
    def test_bool(self):
        self.assertEqual(normalize("TRUE", "bool"), "true")
        self.assertEqual(normalize("False", "bool"), "false")

    def test_int(self):
        self.assertEqual(normalize("-0", "int"), "0")
        self.assertEqual(normalize("42", "int"), "42")
        self.assertEqual(normalize("-7", "int"), "-7")

    def test_float(self):
        cases = {
            "2.00": "2", "0.10": "0.1", "-0.0": "0", "-0.00": "0",
            "10.50": "10.5", "3.25": "3.25", "-2.0": "-2", "0.0001": "0.0001",
        }
        for raw, want in cases.items():
            self.assertEqual(normalize(raw, "float"), want, raw)

    def test_date(self):
        self.assertEqual(normalize("2024-3-5", "date"), "2024-03-05")
        self.assertEqual(normalize("2024/03/05", "date"), "2024-03-05")
        self.assertEqual(normalize("2024年3月5日", "date"), "2024-03-05")
        self.assertEqual(normalize("0001-1-1", "date"), "0001-01-01")

    def test_text_passthrough(self):
        self.assertEqual(normalize("重试,已通知", "text"), "重试,已通知")


if __name__ == "__main__":
    unittest.main()
