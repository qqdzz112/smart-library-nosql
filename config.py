# -*- coding: utf-8 -*-
"""统一配置模块。

设计要点（对应任务书验收红线“硬编码连接串 / 绝对路径 → 不可交付”）：
1. 所有连接参数、库名、数据目录一律来自环境变量，代码中只保留“本机演示级”的缺省值；
2. 支持用 ``LIB_DB_URI`` 直接覆盖整条连接串（副本集、分片集群 mongos 场景用它最方便）；
3. 密码经过 ``quote_plus`` 转义，避免 ``@``、``#`` 等字符破坏 URI；
4. 数据目录缺省值基于本文件位置推导（相对路径），不写死 D:\\ 或 /home/xxx。
"""
from __future__ import annotations

import os
from urllib.parse import quote_plus

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


class Settings:
    """运行期配置，进程内只读。"""

    def __init__(self) -> None:
        # ---- 连接参数 ----
        self.host = _env("LIB_DB_HOST", "127.0.0.1")
        self.port = int(_env("LIB_DB_PORT", "27017"))
        self.user = _env("LIB_DB_USER", "")
        self.password = _env("LIB_DB_PASSWORD", "")
        self.auth_db = _env("LIB_DB_AUTH_DB", "library")
        self.db_name = _env("LIB_DB_NAME", "library")
        # 副本集名，单机/分片留空
        self.replica_set = _env("LIB_DB_REPLICA_SET", "")
        # 读取偏好：primary / primaryPreferred / secondary / secondaryPreferred / nearest
        self.read_preference = _env("LIB_DB_READ_PREF", "primaryPreferred")
        self.app_name = _env("LIB_APP_NAME", "smart-library-cli")

        # ---- 本地目录 ----
        self.data_dir = _env("LIB_DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
        self.export_dir = _env("LIB_EXPORT_DIR", os.path.join(PROJECT_ROOT, "exports"))

    # ------------------------------------------------------------------ URI
    @property
    def uri(self) -> str:
        """返回当前配置对应的连接串（含认证、副本集名，不含明文密码以外的敏感信息）。"""
        explicit = os.getenv("LIB_DB_URI")
        if explicit:
            return explicit
        credential = ""
        if self.user:
            credential = f"{quote_plus(self.user)}:{quote_plus(self.password)}@"
        params = [f"authSource={self.auth_db}", f"appName={self.app_name}"]
        if self.replica_set:
            params.append(f"replicaSet={self.replica_set}")
        return f"mongodb://{credential}{self.host}:{self.port}/{self.db_name}?" + "&".join(params)

    @property
    def masked_uri(self) -> str:
        """用于打印，密码替换为 ***，避免截图/日志泄露口令。"""
        if not self.user:
            return self.uri
        return self.uri.replace(quote_plus(self.password), "***")

    def as_dict(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user or "(匿名)",
            "auth_db": self.auth_db,
            "db": self.db_name,
            "replica_set": self.replica_set or "(单机)",
            "read_preference": self.read_preference,
            "data_dir": self.data_dir,
        }


settings = Settings()
