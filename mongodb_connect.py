# -*- coding: utf-8 -*-
"""统一数据库连接模块（任务四要求“数据库连接模块统一管理”）。

- 进程内单例：整个菜单程序只创建一个 MongoClient，避免每个功能模块各连一次；
- 支持按需切换读取偏好（任务五：primary / secondaryPreferred 演示）；
- 提供 ping / 服务器信息 / 集合计数等运维辅助方法，便于截图与排错。
"""
from __future__ import annotations

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from pymongo.read_preferences import ReadPreference

from config import settings

_PREFERENCES = {
    "primary": ReadPreference.PRIMARY,
    "primarypreferred": ReadPreference.PRIMARY_PREFERRED,
    "secondary": ReadPreference.SECONDARY,
    "secondarypreferred": ReadPreference.SECONDARY_PREFERRED,
    "nearest": ReadPreference.NEAREST,
}


class MongoConnection:
    """MongoClient 的单例封装。"""

    _instance: "MongoConnection | None" = None

    def __init__(self) -> None:
        self._client = MongoClient(
            settings.uri,
            serverSelectionTimeoutMS=4000,
            connectTimeoutMS=4000,
            socketTimeoutMS=15000,
            read_preference=_PREFERENCES.get(settings.read_preference.lower(), ReadPreference.PRIMARY_PREFERRED),
            retryWrites=True,
        )

    # ------------------------------------------------------------- 单例入口
    @classmethod
    def instance(cls) -> "MongoConnection":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试/切换读取偏好时重建连接。"""
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

    # ------------------------------------------------------------- 基本访问
    @property
    def client(self) -> MongoClient:
        return self._client

    def get_database(self, name: str | None = None, read_preference: str | None = None):
        db = self._client[name or settings.db_name]
        if read_preference:
            db = db.with_options(
                read_preference=_PREFERENCES.get(read_preference.lower(), ReadPreference.PRIMARY_PREFERRED)
            )
        return db

    def get_collection(self, name: str, read_preference: str | None = None):
        return self.get_database(read_preference=read_preference)[name]

    # ------------------------------------------------------------- 运维辅助
    def ping(self) -> bool:
        try:
            self._client.admin.command("ping")
            return True
        except (ConnectionFailure, OperationFailure) as exc:
            print(f"[连接失败] {exc}")
            return False

    def server_line(self) -> str:
        """单行服务器信息：版本 / 角色 / 读取偏好，用于启动横幅。"""
        try:
            info = self._client.server_info()
            hello = self._client.admin.command("hello")
            role = "mongos" if hello.get("msg") == "isdbgrid" else ("副本集成员" if hello.get("setName") else "单机")
            return (
                f"MongoDB {info.get('version')} | 角色:{role} | "
                f"副本集:{hello.get('setName', '-')} | 读取偏好:{settings.read_preference}"
            )
        except Exception as exc:  # noqa: BLE001 - 演示程序需要给出可读提示
            return f"无法获取服务器信息: {exc}"

    def collection_counts(self) -> list[tuple[str, int]]:
        db = self.get_database()
        rows = []
        for name in ("books", "readers", "borrow_logs", "audit_logs"):
            try:
                rows.append((name, db[name].estimated_document_count()))
            except Exception:  # noqa: BLE001
                rows.append((name, -1))
        return rows

    def close(self) -> None:
        self._client.close()


def get_db(read_preference: str | None = None):
    """便捷函数：其它模块统一用它取库对象。"""
    return MongoConnection.instance().get_database(read_preference=read_preference)
