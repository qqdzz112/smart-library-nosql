# -*- coding: utf-8 -*-
"""图书管理模块：馆藏检索（6 类检索）与增删改。

所有检索函数都可以在 explain / 性能对比脚本里复用，保证“文档里写的查询”和
“程序里跑的查询”是同一条语句，避免文档与代码脱节。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from audit_logger import log_action
from mongodb_connect import get_db

COLLECTION = "books"


def _col():
    return get_db()[COLLECTION]


# --------------------------------------------------------------- 查询（任务三）
def by_category_price(category: str | None = None, min_price: float | None = None,
                      max_price: float | None = None, limit: int = 20) -> list[dict]:
    """检索 1：分类 + 价格区间（多条件组合，命中复合索引 category_1_price_1）。"""
    query: dict = {}
    if category:
        query["category"] = category
    price = {}
    if min_price is not None:
        price["$gte"] = float(min_price)
    if max_price is not None:
        price["$lte"] = float(max_price)
    if price:
        query["price"] = price
    return list(_col().find(query).sort("price", ASCENDING).limit(limit))


def by_tags(tags: list[str], mode: str = "or", limit: int = 20) -> list[dict]:
    """检索 2：标签多选。or=命中任一标签，and=同时包含全部标签（$all）。"""
    if not tags:
        return []
    query = {"tags": {"$in": tags}} if mode == "or" else {"tags": {"$all": tags}}
    return list(_col().find({"tags": {"$exists": True}, **query}).limit(limit))


def by_title_like(keyword: str, limit: int = 20) -> list[dict]:
    """检索 3：书名模糊查询。对用户输入做正则转义，避免恶意/破坏性正则。"""
    pattern = re.escape(keyword.strip())
    return list(_col().find({"title": {"$regex": pattern, "$options": "i"}}).limit(limit))


def by_publish_year(start_year: int, end_year: int, limit: int = 50) -> list[dict]:
    """检索 4：出版年份区间（用 bson Date 比较，而不是字符串比较）。"""
    start = datetime(start_year, 1, 1, tzinfo=timezone.utc)
    end = datetime(end_year + 1, 1, 1, tzinfo=timezone.utc)
    return list(_col().find({"publish_date": {"$gte": start, "$lt": end}}).sort("publish_date", -1).limit(limit))


def missing_tags(limit: int = 50) -> list[dict]:
    """检索 5：tags 缺失（含字段不存在、null、空数组三种形态）。"""
    query = {"$or": [{"tags": {"$exists": False}}, {"tags": None}, {"tags": []}]}
    return list(_col().find(query).limit(limit))


def top_rated(limit: int = 10) -> list[dict]:
    """检索 6：评分 Top10，只返回三个字段 + 次序键。

    任务书要求“只返回三个字段”。这里额外带上 borrow_count 作为次序键：
    数据中 4.9 分不止一本，只按 rating 排序时同分文档的顺序由存储顺序决定，
    每次执行可能不同；加次序键后结果稳定、可复现。
    """
    projection = {"_id": 0, "title": 1, "author": 1, "rating": 1, "borrow_count": 1}
    return list(_col().find({}, projection).sort([("rating", DESCENDING), ("borrow_count", DESCENDING)]).limit(limit))


# --------------------------------------------------------------- 增删改（任务四）
def get(isbn: str) -> dict | None:
    return _col().find_one({"isbn": isbn})


def list_all(limit: int = 50, skip: int = 0) -> list[dict]:
    return list(_col().find().sort("isbn", ASCENDING).skip(skip).limit(limit))


def add(doc: dict) -> bool:
    doc.setdefault("borrow_count", 0)
    doc.setdefault("tags", [])
    doc.setdefault("ebook_name", None)
    doc.setdefault("stock", 1)
    try:
        _col().insert_one(doc)
    except DuplicateKeyError:
        print(f"[失败] ISBN {doc.get('isbn')} 已存在（isbn 唯一索引生效）")
        log_action("create", COLLECTION, str(doc.get("isbn")), "重复 ISBN，插入被拒绝", result="failed")
        return False
    log_action("create", COLLECTION, str(doc.get("isbn")), f"新增图书《{doc.get('title')}》")
    return True


def update(isbn: str, fields: dict) -> bool:
    fields = {k: v for k, v in fields.items() if k not in ("_id", "isbn")}
    if not fields:
        return False
    result = _col().update_one({"isbn": isbn}, {"$set": fields})
    if result.matched_count == 0:
        return False
    log_action("update", COLLECTION, isbn, "修改字段：" + ",".join(fields.keys()))
    return True


def delete(isbn: str) -> bool:
    doc = get(isbn)
    if not doc:
        return False
    _col().delete_one({"isbn": isbn})
    log_action("delete", COLLECTION, isbn, f"删除图书《{doc.get('title')}》")
    return True


def categories() -> list[str]:
    return sorted(_col().distinct("category"))
