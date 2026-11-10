#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务四（F8）：GridFS 电子书 / 封面上传、列举、按书名下载与字节校验。

运行：python3 scripts/gridfs_demo.py --data-dir data/raw
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from display import fmt_dt, table  # noqa: E402
from gridfs_manager import (  # noqa: E402
    download_by_title,
    list_files,
    stats,
    upload_manifest_files,
)


def load_manifest(data_dir: str) -> dict:
    path = os.path.join(data_dir, "gridfs_files", "files_manifest.txt")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    if not args.skip_upload:
        manifest = load_manifest(args.data_dir)
        print("[1/4] 上传 3 本电子书 + 3 张封面")
        for item in upload_manifest_files(args.data_dir, manifest):
            print(f"      + {item['filename']:<14} {item['bytes']:>7} 字节  file_id={item['file_id']}")

    print("\n[2/4] 列举 fs.files（含元数据 ISBN / 类型 / 原始文件名）")
    rows = [[r["filename"], r["isbn"], r["type"], r["bytes"], r["md5"], fmt_dt(r["upload"])]
            for r in list_files()]
    table(["文件名", "ISBN", "类型", "字节数", "md5(前12)", "上传时间"], rows)

    print("\n[3/4] 按书名查询并下载，做字节数 + MD5 双校验")
    for title in ("Python编程", "深入理解计算机系统", "算法图解"):
        result = download_by_title(title)
        if result.get("ok"):
            print(f"      ✓ 《{result['book']}》 isbn={result['isbn']} "
                  f"{result['actual_bytes']}/{result['expected_bytes']} 字节 MD5一致={result['md5_match']}")
        else:
            print(f"      ✗ {title}: {result.get('reason')}")

    print("\n[4/4] GridFS 统计")
    s = stats()
    print(f"      fs.files={s['files']}  fs.chunks={s['chunks']}  总字节={s['total_bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
