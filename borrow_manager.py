# -*- coding: utf-8 -*-
"""借阅管理：借书、还书、逾期标记、流水查询与导出。

borrow_logs 用**普通集合**（任务二论证见文档），因此可以自由地做「就地更新」：
还书时补 return_date、改 status、回填 duration_days——这正是时间序列集合做不到的。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from audit_logger import log_action
from config import settings
from mongodb_connect import get_db

COLLECTION = "borrow_logs"
LOAN_DAYS = 30          # 借阅期限（天），超过即逾期
OPEN_STATUS = ("借出", "逾期")


def _logs():
    return get_db()[COLLECTION]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """pymongo 读回的时间是 naive UTC，比较前补上时区。"""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ 写操作
def borrow(card_no: str, isbn: str) -> tuple[bool, str]:
    db = get_db()
    reader = db["readers"].find_one({"card_no": card_no})
    if not reader:
        return False, f"读者不存在：{card_no}"
    book = db["books"].find_one({"isbn": isbn})
    if not book:
        return False, f"图书不存在：{isbn}"
    if book.get("stock", 0) <= 0:
        return False, f"《{book['title']}》库存为 0，无法借出"
    opened = _logs().find_one({"reader_card": card_no, "book_isbn": isbn, "status": {"$in": list(OPEN_STATUS)}})
    if opened:
        return False, f"该读者尚未归还《{book['title']}》（{_as_aware(opened['borrow_date']):%Y-%m-%d} 借出）"

    now = _now()
    _logs().insert_one({
        "borrow_date": now,
        "return_date": None,
        "reader_card": card_no,
        "book_isbn": isbn,
        "status": "借出",
        "duration_days": 0,
    })
    db["books"].update_one({"isbn": isbn}, {"$inc": {"stock": -1, "borrow_count": 1}})
    log_action("create", COLLECTION, f"{card_no}/{isbn}", f"借出《{book['title']}》")
    return True, f"借阅成功：《{book['title']}》→ {reader['name']}（{card_no}），期限 {LOAN_DAYS} 天"


def return_book(card_no: str, isbn: str) -> tuple[bool, str]:
    log = _logs().find_one(
        {"reader_card": card_no, "book_isbn": isbn, "status": {"$in": list(OPEN_STATUS)}},
        sort=[("borrow_date", -1)],
    )
    if not log:
        return False, "未找到该读者对该书的未归还记录"
    now = _now()
    days = max(0, (now - _as_aware(log["borrow_date"])).days)
    _logs().update_one({"_id": log["_id"]}, {"$set": {
        "return_date": now,
        "status": "已归还",
        "duration_days": days,
    }})
    get_db()["books"].update_one({"isbn": isbn}, {"$inc": {"stock": 1}})
    overdue = "（逾期）" if days > LOAN_DAYS else ""
    log_action("update", COLLECTION, f"{card_no}/{isbn}", f"归还，借阅 {days} 天{overdue}")
    return True, f"归还成功：借阅 {days} 天{overdue}，库存已回补"


def mark_overdue() -> int:
    """把超过期限仍未归还的记录标记为逾期，并回填已借天数。

    使用「聚合管道更新」（MongoDB 4.2+）：duration_days 由服务端用 $$NOW 计算，
    避免应用端时钟与数据库时钟不一致。
    """
    deadline = _now() - timedelta(days=LOAN_DAYS)
    result = _logs().update_many(
        {"status": "借出", "borrow_date": {"$lt": deadline}},
        [{"$set": {
            "status": "逾期",
            "duration_days": {"$dateDiff": {"startDate": "$borrow_date", "endDate": "$$NOW", "unit": "day"}},
        }}],
    )
    if result.modified_count:
        log_action("update", COLLECTION, "-", f"批量标记逾期 {result.modified_count} 条")
    return result.modified_count


# ------------------------------------------------------------------ 查询
def list_logs(reader_card: str | None = None, book_isbn: str | None = None,
              status: str | None = None, limit: int = 20) -> list[dict]:
    query: dict = {}
    if reader_card:
        query["reader_card"] = reader_card
    if book_isbn:
        query["book_isbn"] = book_isbn
    if status:
        query["status"] = status
    return list(_logs().find(query).sort("borrow_date", -1).limit(limit))


def reader_history(card_no: str, limit: int = 20) -> list[dict]:
    """读者借阅史，联表带出书名（$lookup）。"""
    pipeline = [
        {"$match": {"reader_card": card_no}},
        {"$sort": {"borrow_date": -1}},
        {"$limit": limit},
        {"$lookup": {"from": "books", "localField": "book_isbn", "foreignField": "isbn", "as": "book"}},
        {"$unwind": {"path": "$book", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 0, "borrow_date": 1, "return_date": 1, "status": 1, "duration_days": 1,
            "book_isbn": 1, "title": "$book.title", "category": "$book.category",
        }},
    ]
    return list(_logs().aggregate(pipeline))


def open_loans(limit: int = 20) -> list[dict]:
    return list(_logs().find({"status": {"$in": list(OPEN_STATUS)}}).sort("borrow_date", 1).limit(limit))


# ------------------------------------------------------------------ 导出
def export_logs(fmt: str = "json", status: str | None = None) -> tuple[str, int]:
    """导出借阅流水到 exports/ 目录，并写审计日志。"""
    os.makedirs(settings.export_dir, exist_ok=True)
    query = {"status": status} if status else {}
    rows = list(_logs().find(query))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(settings.export_dir, f"borrow_logs_{stamp}.{ 'csv' if fmt == 'csv' else 'json' }")
    if fmt == "csv":
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["reader_card", "book_isbn", "borrow_date", "return_date", "status", "duration_days"])
            for row in rows:
                writer.writerow([
                    row.get("reader_card"), row.get("book_isbn"),
                    (row.get("borrow_date") or "").isoformat() if isinstance(row.get("borrow_date"), datetime) else "",
                    (row.get("return_date") or "").isoformat() if isinstance(row.get("return_date"), datetime) else "",
                    row.get("status"), row.get("duration_days"),
                ])
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([{**r, "_id": str(r["_id"]),
                        "borrow_date": r["borrow_date"].isoformat() if r.get("borrow_date") else None,
                        "return_date": r["return_date"].isoformat() if r.get("return_date") else None}
                       for r in rows], fh, ensure_ascii=False, indent=1)
    log_action("export", COLLECTION, os.path.basename(path), f"导出 {len(rows)} 条借阅流水（{fmt}）")
    return path, len(rows)
