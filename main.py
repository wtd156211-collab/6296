#!/usr/bin/env python3
"""列类型推断与冲突报告工具入口。

用法: python3 main.py --tables <输入目录> --out <输出目录>
"""

import argparse
import os
import sys

from typeinfer.pipeline import InputError, process_table


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="对目录下的 CSV 逐列推断类型，输出报告 JSON、规范化 CSV 与 HTML 页面。")
    parser.add_argument("--tables", required=True, help="CSV 输入目录（只取顶层 .csv）")
    parser.add_argument("--out", required=True, help="输出目录（不存在则创建）")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.tables):
        parser.error("输入目录不存在: %s" % args.tables)
    os.makedirs(args.out, exist_ok=True)

    names = sorted(
        name for name in os.listdir(args.tables)
        if name.endswith(".csv") and os.path.isfile(os.path.join(args.tables, name))
    )
    try:
        for name in names:
            process_table(os.path.join(args.tables, name), args.out, name)
    except InputError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
