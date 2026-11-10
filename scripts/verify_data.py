# -*- coding: utf-8 -*-
"""数据核对脚本（任务三、任务七验收用）：数量、类型、索引、数据质量、GridFS。"""
from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import display  # noqa: E402
from mongodb_connect import MongoConnection, get_db  # noqa: E402

EXPECTED = {"books": 50, "readers": 30, "borrow_logs": 3000}


def main() -> int:
    conn = MongoConnection.instance()
    db = conn.get_database()
    display.title("数据核对报告")
    display.kv_block([("服务器", conn.server_line()), ("目标库", db.name)])

    display.section("1. 集合文档数")
    rows, ok = [], True
    for collection, expected in EXPECTED.items():
        actual = db[collection].count_documents({})
        ok = ok and actual == expected
        rows.append([collection, expected, actual, "通过" if actual == expected else "不一致"])
    rows.append(["audit_logs", "-", db["audit_logs"].count_documents({}), "固定集合"])
    rows.append(["fs.files", "-", db["fs.files"].count_documents({}), "GridFS 元数据"])
    rows.append(["fs.chunks", "-", db["fs.chunks"].count_documents({}), "GridFS 分块"])
    display.table(["集合", "期望", "实际", "结论"], rows)

    display.section("2. 字段类型抽查（BSON Date 转换是否正确）")
    book = db["books"].find_one({"isbn": "9787115428028"})
    reader = db["readers"].find_one({"card_no": "R20240001"})
    log = db["borrow_logs"].find_one({"status": "已归还"})
    checks = [
        ["books.publish_date", type(book["publish_date"]).__name__, isinstance(book["publish_date"], datetime)],
        ["readers.register_date", type(reader["register_date"]).__name__, isinstance(reader["register_date"], datetime)],
        ["borrow_logs.borrow_date", type(log["borrow_date"]).__name__, isinstance(log["borrow_date"], datetime)],
        ["borrow_logs.return_date", type(log.get("return_date")).__name__, log.get("return_date") is None or isinstance(log["return_date"], datetime)],
        ["books.location", type(book["location"]).__name__, isinstance(book["location"], dict)],
        ["books.tags", type(book.get("tags")).__name__, isinstance(book.get("tags"), list)],
    ]
    display.table(["字段", "Python 类型", "通过"], [[a, b, "是" if c else "否"] for a, b, c in checks])

    display.section("3. 数据质量")
    quality = [
        ["books.tags 缺失/null", db["books"].count_documents({"$or": [{"tags": {"$exists": False}}, {"tags": None}]})],
        ["books.ebook_name 为 null", db["books"].count_documents({"ebook_name": None})],
        ["readers.email 为 null", db["readers"].count_documents({"email": None})],
        ["readers.fav_categories 为 null", db["readers"].count_documents({"fav_categories": None})],
        ["borrow_logs.return_date 缺失", db["borrow_logs"].count_documents({"return_date": None})],
        ["borrow_logs 已归还", db["borrow_logs"].count_documents({"status": "已归还"})],
        ["borrow_logs 借出", db["borrow_logs"].count_documents({"status": "借出"})],
        ["borrow_logs 逾期", db["borrow_logs"].count_documents({"status": "逾期"})],
    ]
    display.table(["检查项", "数量"], quality, align={1: "right"})

    display.section("4. 索引清单")
    for collection in ("books", "readers", "borrow_logs", "audit_logs"):
        indexes = db[collection].index_information()
        print(f"  [{collection}] 共 {len(indexes)} 个索引")
        for name, info in indexes.items():
            print(f"    - {name:<26} {info['key']}")

    display.section("5. 文档示例")
    print("  books:", {k: book[k] for k in ("isbn", "title", "category", "price", "publish_date")})
    print("  location:", book["location"], " tags:", book.get("tags"), " ebook:", book.get("ebook_name"))
    print("  readers:", {k: reader[k] for k in ("card_no", "name", "college", "level", "email")})

    print("\n数据核对通过。" if ok else "\n数据量不一致，请重新导入。")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
