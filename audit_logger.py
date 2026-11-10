# -*- coding: utf-8 -*-
"""审计日志模块（任务四：新增 / 删除 / 导出必须写 audit_logs）。

集合类型选择：**固定集合（capped collection）**
- 审计数据只追加、不修改，天然契合 capped「写入即顺序追加」的语义；
- 容量固定（16 MB / 最多 50000 条），自动淘汰最旧记录，避免审计表无限膨胀；
- 固定集合的插入顺序就是物理顺序，用 ``$natural: -1`` 逆序取「最近 100 条」
  不需要额外索引，正好满足任务二对 audit_logs 的查询要求。

文档结构（任务二要求给出完整字段）：
    ts          Date    操作时间（UTC 存储）
    actor       String  操作账号名
    role        String  账号角色（readonly / readwrite / admin）
    action      String  动作类型：create / update / delete / export / upload / download
    collection  String  目标集合
    target      String  目标业务主键（isbn、card_no 等）
    detail      String  可读描述
    result      String  success / failed
    source      String  客户端标识（主机名:进程号）
"""
from __future__ import annotations

import getpass
import os
import socket
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING

from config import settings
from mongodb_connect import get_db

COLLECTION = "audit_logs"
CAPPED_SIZE = 16 * 1024 * 1024
CAPPED_MAX = 50000


def _source() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def ensure_collection(db=None) -> None:
    """首次运行时创建固定集合（已存在则跳过）。"""
    if db is None:  # pymongo 4.x 的 Database 不支持真值判断
        db = get_db()
    if COLLECTION not in db.list_collection_names():
        db.create_collection(COLLECTION, capped=True, size=CAPPED_SIZE, max=CAPPED_MAX)
        db[COLLECTION].create_index([("ts", DESCENDING)])
        db[COLLECTION].create_index([("action", ASCENDING), ("ts", DESCENDING)])


def log_action(action: str, collection: str, target: str, detail: str,
               role: str | None = None, result: str = "success", actor: str | None = None) -> None:
    """写一条审计记录；审计失败不能掩盖业务成功，因此异常只提示不抛出。"""
    try:
        db = get_db()
        ensure_collection(db)
        db[COLLECTION].insert_one({
            "ts": datetime.now(timezone.utc),
            "actor": actor or settings.user or getpass.getuser(),
            "role": role or ("admin" if settings.user.endswith("admin") else "readwrite"),
            "action": action,
            "collection": collection,
            "target": target,
            "detail": detail,
            "result": result,
            "source": _source(),
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 审计日志写入失败（不影响业务结果）：{exc}")


def recent(limit: int = 100) -> list[dict]:
    """按时间倒序返回最近 limit 条（固定集合物理顺序逆序，无需排序字段）。"""
    db = get_db()
    ensure_collection(db)
    return list(db[COLLECTION].find().sort([("$natural", -1)]).limit(limit))


def summary() -> list[dict]:
    """按动作统计，用于验收截图。"""
    db = get_db()
    ensure_collection(db)
    pipeline = [
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return list(db[COLLECTION].aggregate(pipeline))
