import csv
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN = os.path.join(ROOT, "main.py")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.in_dir = os.path.join(self.tmp.name, "in")
        self.out_dir = os.path.join(self.tmp.name, "out")
        os.makedirs(self.in_dir)

    def _write_csv(self, name, rows):
        with open(os.path.join(self.in_dir, name), "w",
                  encoding="utf-8", newline="") as fh:
            csv.writer(fh, lineterminator="\n").writerows(rows)

    def _run(self, *extra):
        return subprocess.run(
            [sys.executable, MAIN, "--tables", self.in_dir,
             "--out", self.out_dir] + list(extra),
            cwd=ROOT, capture_output=True, text=True)

    def test_success_and_outputs(self):
        self._write_csv("b.csv", [["a"], ["1"]])
        self._write_csv("a.csv", [["a"], ["1"]])
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        names = sorted(os.listdir(self.out_dir))
        self.assertEqual(names,
                         ["a.html", "a.json", "a.normalized.csv",
                          "b.html", "b.json", "b.normalized.csv"])

    def test_missing_tables_dir_exit_2(self):
        proc = subprocess.run(
            [sys.executable, MAIN, "--tables",
             os.path.join(self.tmp.name, "nope"), "--out", self.out_dir],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_missing_arg_exit_2(self):
        proc = subprocess.run(
            [sys.executable, MAIN, "--out", self.out_dir],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)

    def test_bad_input_exit_1(self):
        self._write_csv("bad.csv", [["a", "b"], ["1"]])
        proc = self._run()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("bad.csv", proc.stderr)

    def test_non_csv_ignored_and_top_level_only(self):
        self._write_csv("ok.csv", [["a"], ["1"]])
        with open(os.path.join(self.in_dir, "notes.txt"), "w") as fh:
            fh.write("ignore me")
        nested = os.path.join(self.in_dir, "sub")
        os.makedirs(nested)
        with open(os.path.join(nested, "deep.csv"), "w", newline="") as fh:
            csv.writer(fh).writerow(["z"])
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(sorted(os.listdir(self.out_dir)),
                         ["ok.html", "ok.json", "ok.normalized.csv"])

    def test_deterministic_two_runs(self):
        self._write_csv("t.csv", [["id", "v"]] +
                       [[str(i), "x" if i == 5 else "1"] for i in range(1, 11)])
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        first = {n: open(os.path.join(self.out_dir, n), "rb").read()
                 for n in os.listdir(self.out_dir)}
        self.out_dir = os.path.join(self.tmp.name, "out2")
        proc = self._run()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        second = {n: open(os.path.join(self.out_dir, n), "rb").read()
                  for n in os.listdir(self.out_dir)}
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
