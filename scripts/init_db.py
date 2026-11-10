# -*- coding: utf-8 -*-
"""数据初始化：导入三份 JSON 数据 → 类型转换 → 建索引 → 建账号 → 上传 GridFS。

任务书要求“不得修改原始数据”，因此本脚本是**只读原始文件**、在内存里做类型转换
（ISO8601 字符串 → BSON Date），再写入数据库；原文件保持原样。

用法（无认证启动的实例）：
    python3 scripts/init_db.py --data-dir ./data --drop --with-users
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient  # noqa: E402
from pymongo.errors import OperationFailure  # noqa: E402

from config import settings  # noqa: E402
from scripts.create_indexes import create_all  # noqa: E402

DATE_FIELDS = {
    "books": ("publish_date",),
    "readers": ("register_date",),
    "borrow_logs": ("borrow_date", "return_date"),
}
EXPECTED = {"books": 50, "readers": 30, "borrow_logs": 3000}

DATASETS = {
    "books": "books.txt",
    "readers": "readers.txt",
    "borrow_logs": "borrow_logs.txt",
}

USERS = [
    ("lib_reader", os.getenv("LIB_PWD_READONLY", ""),
     [{"role": "read", "db": "library"}], "只读账号：只能查询，不能写入"),
    ("lib_writer", os.getenv("LIB_PWD_READWRITE", ""),
     [{"role": "readWrite", "db": "library"}], "读写账号：业务程序使用"),
    ("lib_admin", os.getenv("LIB_PWD_ADMIN", ""),
     [{"role": "dbAdmin", "db": "library"}, {"role": "userAdmin", "db": "library"},
      {"role": "readWrite", "db": "library"}], "管理账号：建索引/建账号/维护"),
]


def parse_dt(value):
    """把 ISO8601 字符串转成带时区的 datetime；空值保持 None。"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def load_documents(path: str, collection: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    for row in rows:
        for field in DATE_FIELDS.get(collection, ()):
            if field in row:
                row[field] = parse_dt(row[field])
    return rows


def import_collection(db, collection: str, docs: list[dict]) -> int:
    if not docs:
        return 0
    result = db[collection].insert_many(docs, ordered=False)
    return len(result.inserted_ids)


def create_users(db) -> None:
    # 口令一律来自环境变量，仓库中不保存明文
    missing = [name for name, password, _roles, _desc in USERS if not password]
    if missing:
        print("  ! 口令未设置，跳过：" + ", ".join(missing))
        print("    请先 export LIB_PWD_READONLY / LIB_PWD_READWRITE / LIB_PWD_ADMIN")
        return
    for name, password, roles, desc in USERS:
        try:
            db.command("createUser", name, pwd=password, roles=roles)
            print(f"  + 账号 {name:<12} 创建成功  {desc}")
        except OperationFailure as exc:
            print(f"  = 账号 {name:<12} 已存在或创建失败：{exc.details.get('errmsg', exc)}")


def upload_gridfs(data_dir: str) -> None:
    import gridfs_manager
    manifest_path = os.path.join(data_dir, "gridfs_files", "files_manifest.txt")
    if not os.path.exists(manifest_path):
        print("  ! 未找到 files_manifest.txt，跳过 GridFS 上传")
        return
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    results = gridfs_manager.upload_manifest_files(data_dir, manifest)
    for item in results:
        print(f"  + GridFS {item['filename']:<14} {item['bytes']:>6} 字节  id={item['file_id']}")
    print(f"  GridFS 合计：{gridfs_manager.stats()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="导入图书馆数据")
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    parser.add_argument("--drop", action="store_true", help="先删除同名集合")
    parser.add_argument("--with-users", action="store_true", help="创建三个业务账号（需无认证状态执行）")
    parser.add_argument("--skip-gridfs", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    args = parser.parse_args()

    client = MongoClient(settings.uri, serverSelectionTimeoutMS=5000)
    db = client[settings.db_name]
    print(f"目标库：{settings.masked_uri}")
    print(f"数据目录：{args.data_dir}")

    print("\n[1/4] 导入集合")
    total = 0
    for collection, filename in DATASETS.items():
        path = os.path.join(args.data_dir, filename)
        if args.drop:
            db[collection].drop()
        docs = load_documents(path, collection)
        inserted = import_collection(db, collection, docs)
        total += inserted
        print(f"  {collection:<12} 读入 {len(docs):>5} 条，写入 {inserted:>5} 条")

    print("\n[2/4] 数据量核对")
    ok = True
    for collection, expected in EXPECTED.items():
        actual = db[collection].count_documents({})
        flag = "OK" if actual == expected else "不一致"
        ok = ok and actual == expected
        print(f"  {collection:<12} 期望 {expected:>5} / 实际 {actual:>5}  {flag}")
    print(f"  合计写入 {total} 条")

    if not args.skip_index:
        print("\n[3/4] 创建索引")
        create_all(db)

    if args.with_users:
        print("\n[4/4] 创建业务账号（须在未启用认证时执行）")
        create_users(db)
        cluster_pwd = os.getenv("LIB_PWD_CLUSTER", "")
        if not cluster_pwd:
            print("  ! 未设置 LIB_PWD_CLUSTER，跳过 cluster_admin")
        else:
            try:
                admin_db = client["admin"]
                admin_db.command("createUser", "cluster_admin",
                                 pwd=cluster_pwd,
                                 roles=["root"])
                print("  + 账号 cluster_admin  创建成功  集群管理（副本集/分片运维）")
            except OperationFailure as exc:
                print(f"  = 账号 cluster_admin  已存在或创建失败：{exc.details.get('errmsg', exc)}")

    if not args.skip_gridfs:
        print("\n[附加] 上传电子书与封面到 GridFS")
        upload_gridfs(args.data_dir)

    print("\n初始化完成。" if ok else "\n初始化完成，但数据量与期望不一致，请检查原始文件。")
    client.close()
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
