# -*- coding: utf-8 -*-
"""统计分析模块：任务三要求的 5 组聚合 + 任务七的结果导出。

聚合尽量把过滤/分组下推到服务端，Python 只做展示，避免“把 3000 条拉回本地再算”。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from pymongo import DESCENDING

from audit_logger import log_action
from config import settings
from mongodb_connect import get_db

STATS_COLLECTION = "category_stats"


def _db():
    return get_db()


# ------------------------------------------------------------ 任务三：5 组聚合
def category_stats() -> list[dict]:
    """统计 1：按分类统计册数、均价、平均评分、总库存、被借次数。"""
    pipeline = [
        {"$group": {
            "_id": "$category",
            "book_count": {"$sum": 1},
            "avg_price": {"$avg": "$price"},
            "avg_rating": {"$avg": "$rating"},
            "total_stock": {"$sum": "$stock"},
            "borrow_total": {"$sum": "$borrow_count"},
        }},
        {"$sort": {"book_count": -1}},
        {"$project": {
            "_id": 0, "category": "$_id", "book_count": 1,
            "avg_price": {"$round": ["$avg_price", 2]},
            "avg_rating": {"$round": ["$avg_rating", 2]},
            "total_stock": 1, "borrow_total": 1,
        }},
    ]
    return list(_db()["books"].aggregate(pipeline))


def college_borrow_top5() -> list[dict]:
    """统计 2：学院借阅量 Top5（borrow_logs $lookup readers）。"""
    pipeline = [
        {"$lookup": {"from": "readers", "localField": "reader_card", "foreignField": "card_no", "as": "reader"}},
        {"$unwind": "$reader"},
        {"$group": {"_id": "$reader.college", "borrow_count": {"$sum": 1},
                    "reader_count": {"$addToSet": "$reader_card"}}},
        {"$project": {"_id": 0, "college": "$_id", "borrow_count": 1, "reader_count": {"$size": "$reader_count"}}},
        {"$sort": {"borrow_count": -1}},
        {"$limit": 5},
    ]
    return list(_db()["borrow_logs"].aggregate(pipeline))


def monthly_trend() -> list[dict]:
    """统计 3：按年月统计借阅量（趋势图数据）。"""
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": "$borrow_date"}},
            "borrow_count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "month": "$_id", "borrow_count": 1}},
    ]
    return list(_db()["borrow_logs"].aggregate(pipeline))


def top_borrowed_books(limit: int = 10) -> list[dict]:
    """统计 4：借阅次数最多的 10 本，并带出馆藏位置（floor/shelf）。"""
    pipeline = [
        {"$group": {"_id": "$book_isbn", "borrow_count": {"$sum": 1}}},
        {"$sort": {"borrow_count": -1}},
        {"$limit": limit},
        {"$lookup": {"from": "books", "localField": "_id", "foreignField": "isbn", "as": "book"}},
        {"$unwind": "$book"},
        {"$project": {
            "_id": 0, "isbn": "$_id", "title": "$book.title", "category": "$book.category",
            "borrow_count": 1, "floor": "$book.location.floor", "shelf": "$book.location.shelf",
        }},
    ]
    return list(_db()["borrow_logs"].aggregate(pipeline))


def write_category_stats() -> int:
    """统计 5：把分类统计结果写回新集合（$merge 可重复执行，不会重复累加）。"""
    pipeline = [
        {"$group": {
            "_id": "$category",
            "book_count": {"$sum": 1},
            "avg_price": {"$avg": "$price"},
            "total_borrow": {"$sum": "$borrow_count"},
        }},
        {"$project": {
            "book_count": 1,
            "avg_price": {"$round": ["$avg_price", 2]},
            "total_borrow": 1,
            "updated_at": "$$NOW",
        }},
        {"$merge": {"into": STATS_COLLECTION, "on": "_id", "whenMatched": "replace", "whenNotMatched": "insert"}},
    ]
    list(_db()["books"].aggregate(pipeline))
    count = _db()[STATS_COLLECTION].count_documents({})
    log_action("update", STATS_COLLECTION, "category_stats", f"重建分类统计集合，{count} 个分类")
    return count


# ------------------------------------------------------------ 附加统计（展示用）
def reader_level_stats() -> list[dict]:
    pipeline = [
        {"$lookup": {"from": "readers", "localField": "reader_card", "foreignField": "card_no", "as": "r"}},
        {"$unwind": "$r"},
        {"$group": {"_id": "$r.level", "borrow_count": {"$sum": 1}, "avg_days": {"$avg": "$duration_days"}}},
        {"$project": {"_id": 0, "level": "$_id", "borrow_count": 1, "avg_days": {"$round": ["$avg_days", 1]}}},
        {"$sort": {"borrow_count": -1}},
    ]
    return list(_db()["borrow_logs"].aggregate(pipeline))


def status_stats() -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1},
                    "avg_days": {"$avg": "$duration_days"}}},
        {"$project": {"_id": 0, "status": "$_id", "count": 1, "avg_days": {"$round": ["$avg_days", 1]}}},
        {"$sort": {"count": DESCENDING}},
    ]
    return list(_db()["borrow_logs"].aggregate(pipeline))


def active_readers(limit: int = 10) -> list[dict]:
    pipeline = [
        {"$group": {"_id": "$reader_card", "borrow_count": {"$sum": 1}}},
        {"$sort": {"borrow_count": -1}},
        {"$limit": limit},
        {"$lookup": {"from": "readers", "localField": "_id", "foreignField": "card_no", "as": "r"}},
        {"$unwind": "$r"},
        {"$project": {"_id": 0, "card_no": "$_id", "name": "$r.name", "college": "$r.college",
                      "borrow_count": 1}},
    ]
    return list(_db()["borrow_logs"].aggregate(pipeline))


# ------------------------------------------------------------ 任务七：导出
def export_all() -> str:
    """把全部统计结果导出成一份 JSON，交给文档/答辩材料引用。"""
    os.makedirs(settings.export_dir, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "category_stats": category_stats(),
        "college_borrow_top5": college_borrow_top5(),
        "monthly_trend": monthly_trend(),
        "top_borrowed_books": top_borrowed_books(10),
        "status_stats": status_stats(),
        "reader_level_stats": reader_level_stats(),
        "active_readers": active_readers(10),
    }
    path = os.path.join(settings.export_dir, "statistics_result.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, default=str)
    log_action("export", "statistics", os.path.basename(path), "导出统计结果 JSON")
    return path
