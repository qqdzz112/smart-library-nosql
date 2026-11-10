# -*- coding: utf-8 -*-
"""只重建 books 集合：按 data/raw/books.txt 重新导入 50 条并重建 books 索引。

用于修复 books 被误改（其余集合不动，audit_logs 与 borrow_logs 保持原样）。
用法：
    LIB_DB_URI=... python3 scripts/reimport_books.py [--data-dir data/raw]
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

BOOK_INDEXES = [
    (("isbn", 1), {"name": "uk_isbn", "unique": True}),
    ((("category", 1), ("price", 1)), {"name": "idx_category_price"}),
    (("tags", 1), {"name": "idx_tags"}),
    (("publish_date", -1), {"name": "idx_publish_date"}),
    ((("rating", -1), ("borrow_count", -1)), {"name": "idx_rating_borrow"}),
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
    docs = load(os.path.join(args.data_dir, "books.txt"))
    if len(docs) != 50:
        raise SystemExit(f"books.txt 应该有 50 条，实际 {len(docs)}")

    before = db.books.count_documents({})
    db.books.drop()
    db.books.insert_many(docs)
    for spec, options in BOOK_INDEXES:
        db.books.create_index([spec] if isinstance(spec, tuple) and isinstance(spec[0], str) else list(spec), **options)

    display.title("books 重建结果")
    display.kv_block([
        ("导入前", before), ("导入后", db.books.count_documents({})),
        ("示例 ISBN", db.books.find_one({"isbn": "9787115428028"})["title"]),
        ("索引", ", ".join(sorted(db.books.index_information()))),
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
