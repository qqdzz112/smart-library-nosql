#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务五：读取偏好演示（三种典型偏好在同一份数据上的表现）。

说明：hello 命令返回驱动协商出的目标节点，它本身不能证明某次 find 由哪个成员服务；
要证明“从节点真的在提供读服务”，靠的是故障转移实验：主节点停掉后
secondaryPreferred 仍读得到、primary 直接报错。本脚本另外用 directConnection
直连两个从节点各读一次，证明副本数据可读。
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient, ReadPreference  # noqa: E402
from pymongo.errors import ServerSelectionTimeoutError  # noqa: E402

from config import settings  # noqa: E402

PREFS = [
    ("primary", ReadPreference.PRIMARY, "强一致：借还书后立即回显库存"),
    ("primaryPreferred", ReadPreference.PRIMARY_PREFERRED, "主优先：主挂了降级读从，保证可用"),
    ("secondaryPreferred", ReadPreference.SECONDARY_PREFERRED, "报表/榜单：容忍毫秒级延迟，分摊主节点压力"),
]

SECONDARIES = ["192.168.121.129:27102", "192.168.121.130:27103"]


def run(pref_name: str, pref, note: str) -> None:
    kwargs = dict(serverSelectionTimeoutMS=4000, socketTimeoutMS=8000, read_preference=pref)
    if settings.replica_set:
        kwargs["replicaSet"] = settings.replica_set
    client = MongoClient(settings.uri, **kwargs)
    started = time.perf_counter()
    try:
        hello = client.admin.command("hello")
        docs = []
        for _ in range(3):
            docs.append(client[settings.db_name]["books"].find_one({}, {"title": 1, "_id": 0}))
        elapsed = (time.perf_counter() - started) * 1000 / 3
        print(f"{pref_name:<19} 驱动协商节点={hello.get('me', '-'):<22} "
              f"isWritablePrimary={'是' if hello.get('isWritablePrimary') else '否'}  "
              f"读到《{(docs[0] or {}).get('title', '无')}》 平均 {elapsed:6.1f} ms   {note}")
    except ServerSelectionTimeoutError as exc:
        print(f"{pref_name:<19} 读取失败：{str(exc).splitlines()[0][:90]}")
    finally:
        client.close()


def _direct_uri(hp: str) -> str:
    """把连接串改写成直连某个成员：去掉 replicaSet，加 directConnection。"""
    scheme, rest = settings.uri.split("://", 1)
    credential = ""
    if "@" in rest.split("/", 1)[0]:
        credential, rest = rest.split("@", 1)
        credential += "@"
    path, _, query = rest.partition("?")
    db_name = path.split("/", 1)[1] if "/" in path else settings.db_name
    params = [p for p in query.split("&") if p and not p.startswith("replicaSet=")]
    params.insert(0, "directConnection=true")
    return f"{scheme}://{credential}{hp}/{db_name}?" + "&".join(params)


def direct_reads() -> None:
    print("\n从节点直读（directConnection=true，绕过副本集路由）")
    for hp in SECONDARIES:
        client = MongoClient(_direct_uri(hp), serverSelectionTimeoutMS=4000)
        try:
            doc = client[settings.db_name]["books"].find_one({}, {"title": 1, "_id": 0})
            print(f"  {hp:<22} 读到《{(doc or {}).get('title', '无')}》")
        except Exception as exc:  # noqa: BLE001
            print(f"  {hp:<22} 失败：{str(exc).splitlines()[0][:80]}")
        finally:
            client.close()


def main() -> int:
    print("副本集读偏好演示  连接串：" + settings.masked_uri)
    print("-" * 118)
    for name, pref, note in PREFS:
        run(name, pref, note)
    direct_reads()
    print("\n结论：主节点健康时三种偏好都能读到数据；差异体现在主节点故障时"
          "（primary 直接报错、secondaryPreferred 继续读从节点），见故障转移记录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
