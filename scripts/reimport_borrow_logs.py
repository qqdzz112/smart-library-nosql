# -*- coding: utf-8 -*-
"""只重建 borrow_logs 集合：按 data/raw/borrow_logs.txt 重新导入 3000 条并重建索引。

用于修复演示脚本把"借出"批量标记成"逾期"后造成的状态偏移（其余集合不动）。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bson import json_util  # noqa: E402

import display  # noqa: E402
from mongodb_connect import MongoConnection  # noqa: E402

DATE_FIELDS = ("publish_date", "register_date", "borrow_date", "return_date")

LOG_INDEXES = [
    ((("reader_card", 1), ("borrow_date", -1)), {"name": "idx_reader_borrowdate"}),
    ((("book_isbn", 1), ("borrow_date", -1)), {"name": "idx_book_borrowdate"}),
    ((("status", 1), ("borrow_date", -1)), {"name": "idx_status_borrowdate"}),
    ((("borrow_date", -1),), {"name": "idx_borrowdate"}),
]


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        docs = json_util.loads(f.read())
    for doc in docs:
        for field in DATE_FIELDS:
            value = doc.get(field)
            if isinstance(value, str):
                doc[field] = datetime.fromisoformat(value)
    return docs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/raw")
    args = ap.parse_args()

    db = MongoConnection.instance().get_database()
    docs = load(os.path.join(args.data_dir, "borrow_logs.txt"))
    if len(docs) != 3000:
        raise SystemExit(f"borrow_logs.txt 应该有 3000 条，实际 {len(docs)}")

    db.borrow_logs.drop()
    db.borrow_logs.insert_many(docs, ordered=False)
    for spec, options in LOG_INDEXES:
        db.borrow_logs.create_index(list(spec), **options)

    counts = list(db.borrow_logs.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]))
    display.title("borrow_logs 重建结果")
    display.kv_block([
        ("文档数", db.borrow_logs.count_documents({})),
        ("状态分布", ", ".join(f"{c['_id']}={c['n']}" for c in counts)),
        ("无 return_date", db.borrow_logs.count_documents({"return_date": None})),
        ("索引", ", ".join(sorted(db.borrow_logs.index_information()))),
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
