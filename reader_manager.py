# -*- coding: utf-8 -*-
"""读者管理模块。"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from audit_logger import log_action
from mongodb_connect import get_db

COLLECTION = "readers"


def _col():
    return get_db()[COLLECTION]


def search(keyword: str = "", college: str | None = None, level: str | None = None,
           limit: int = 30) -> list[dict]:
    """按姓名/卡号模糊 + 学院 + 等级组合检索。"""
    query: dict = {}
    if keyword:
        pattern = re.escape(keyword.strip())
        query["$or"] = [{"name": {"$regex": pattern}}, {"card_no": {"$regex": pattern, "$options": "i"}}]
    if college:
        query["college"] = college
    if level:
        query["level"] = level
    return list(_col().find(query).sort("card_no", 1).limit(limit))


def get(card_no: str) -> dict | None:
    return _col().find_one({"card_no": card_no})


def list_all(limit: int = 30) -> list[dict]:
    return list(_col().find().sort("card_no", 1).limit(limit))


def add(doc: dict) -> bool:
    doc.setdefault("register_date", datetime.now(timezone.utc))
    doc.setdefault("fav_categories", [])
    doc.setdefault("email", None)
    try:
        _col().insert_one(doc)
    except DuplicateKeyError:
        print(f"[失败] 借书证号 {doc.get('card_no')} 已存在（card_no 唯一索引生效）")
        log_action("create", COLLECTION, str(doc.get("card_no")), "重复借书证号，插入被拒绝", result="failed")
        return False
    log_action("create", COLLECTION, str(doc.get("card_no")), f"新增读者 {doc.get('name')}")
    return True


def delete(card_no: str) -> bool:
    doc = get(card_no)
    if not doc:
        return False
    _col().delete_one({"card_no": card_no})
    log_action("delete", COLLECTION, card_no, f"删除读者 {doc.get('name')}")
    return True


def colleges() -> list[str]:
    return sorted(_col().distinct("college"))


def levels() -> list[str]:
    return sorted(_col().distinct("level"))
