"""列类型推断与冲突报告工具入口。

用法：python3 main.py --tables <输入目录> --out <输出目录>
退出码：0 全部成功；1 输入表不合法或处理失败；2 参数/目录错误。
"""

import argparse
import os
import sys

from page import write_html
from report import TableError, process_table, write_report_json


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="逐列推断 CSV 类型，输出报告 JSON、规范化 CSV 与自包含 HTML 页面。")
    parser.add_argument("--tables", required=True, help="输入目录（只取顶层 .csv，不递归）")
    parser.add_argument("--out", required=True, help="输出目录（不存在则创建）")
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if not os.path.isdir(args.tables):
        print("error: --tables directory does not exist: %s" % args.tables,
              file=sys.stderr)
        return 2
    try:
        os.makedirs(args.out, exist_ok=True)
    except OSError as exc:
        print("error: cannot create --out directory: %s" % exc, file=sys.stderr)
        return 2

    names = sorted(name for name in os.listdir(args.tables)
                   if name.endswith(".csv")
                   and os.path.isfile(os.path.join(args.tables, name)))
    for name in names:
        stem = name[:-4]
        csv_path = os.path.join(args.tables, name)
        try:
            report, evidence = process_table(csv_path, stem, args.out)
        except TableError as exc:
            print("error: %s: %s" % (name, exc), file=sys.stderr)
            return 1
        except OSError as exc:
            print("error: %s: %s" % (name, exc), file=sys.stderr)
            return 1
        write_report_json(report, os.path.join(args.out, stem + ".json"))
        write_html(report, evidence, os.path.join(args.out, stem + ".html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
