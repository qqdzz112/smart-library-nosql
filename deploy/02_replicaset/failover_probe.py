#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务五：主节点故障转移实测（在 nosql01 上执行）。

实测口径（可复现、可写进文档）：
1. 转移前打印三成员状态；
2. 启动一个 100ms 一次的后台探针，持续做「primary 读 + 写入」，记录成功/失败；
3. 向 rs1 发 SIGTERM（mongod 会先 stepDown 再 quiesce 15s），记录 t0；
4. 每 100ms 轮询另一个成员的 hello，直到出现新 PRIMARY，记下选举耗时；
5. 探针再跑 2s 后停止，统计「无主窗口」：首次失败时刻、最后失败时刻、持续时长、错误类型；
6. 等旧进程真正退出后再重启 rs1（否则 dbpath 锁会导致启动失败），
   计时它重新加入 + 追平复制；最后打印三成员状态。
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time

from urllib.parse import urlsplit, urlunsplit

from pymongo import MongoClient, ReadPreference
from pymongo.errors import PyMongoError

ADMIN_URI = os.environ.get("FAILOVER_ADMIN_URI", "")
WRITE_URI = os.environ.get("FAILOVER_WRITE_URI", "")
READ_URI = os.environ.get("FAILOVER_READ_URI", "")
RS1_CONF = os.environ.get("FAILOVER_RS1_CONF", os.path.expanduser("~/final/conf/rs1.conf"))
MONGOD = os.environ.get("FAILOVER_MONGOD", "/usr/bin/mongod")
RS1_PID = os.environ.get("FAILOVER_RS1_PID", os.path.expanduser("~/final/rs1/mongod.pid"))
MEMBERS = [("192.168.121.128", 27101), ("192.168.121.129", 27102), ("192.168.121.130", 27103)]


def rs_status() -> dict:
    """依次尝试三个成员：停主之后原主的连接必然失败，必须能回退到新主。"""
    last: PyMongoError | None = None
    for uri in admin_uris():
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        try:
            return client.admin.command("replSetGetStatus")
        except PyMongoError as exc:
            last = exc
        finally:
            client.close()
    raise last if last else RuntimeError("replSetGetStatus 全部成员均失败")


def admin_uris() -> list[str]:
    """把 FAILOVER_ADMIN_URI 的凭据套到三个成员地址上，依次重试。"""
    parts = urlsplit(ADMIN_URI)
    creds = parts.netloc.rsplit("@", 1)[0] if "@" in parts.netloc else ""
    uris = []
    for host, port in MEMBERS:
        netloc = f"{creds}@{host}:{port}" if creds else f"{host}:{port}"
        uris.append(urlunsplit((parts.scheme, netloc, "/admin", "authSource=admin", "")))
    return uris


def show_status(title: str) -> dict:
    st = rs_status()
    optimes = [m.get("optimeDate") for m in st["members"] if m.get("optimeDate")]
    newest = max(optimes) if optimes else None
    print(f"\n{title}   （集合 {st['set']}，成员 {len(st['members'])} 个）")
    for m in st["members"]:
        if newest and m.get("optimeDate") and m.get("stateStr") != "PRIMARY":
            lag = f"{(newest - m['optimeDate']).total_seconds():.0f}s"
        else:
            lag = "-"
        print(f"  id={m['_id']}  {m['name']:<24} {m['stateStr']:<24} health={m.get('health')} "
              f"uptime={m.get('uptime')}s  复制延迟={lag}")
    return st


def hello_direct(host: str, port: int, timeout_ms: int = 400) -> dict | None:
    uri = (f"mongodb://{host}:{port}/?directConnection=true"
           f"&serverSelectionTimeoutMS={timeout_ms}&connectTimeoutMS={timeout_ms}")
    client = MongoClient(uri)
    try:
        return client.admin.command("hello")
    finally:
        client.close()


def direct_read_128(timeout_ms: int = 400) -> str:
    """直连原主节点做一次读，不做重试，用来展示故障时的真实报错。"""
    uri = ("mongodb://192.168.121.128:27101/?directConnection=true"
           f"&serverSelectionTimeoutMS={timeout_ms}&connectTimeoutMS={timeout_ms}")
    client = MongoClient(uri)
    try:
        client["library"]["books"].find_one({}, {"title": 1})
        return "成功（原主仍可读）"
    except PyMongoError as exc:
        return f"{type(exc).__name__}: {str(exc).splitlines()[0][:72]}"
    finally:
        client.close()


class Probe(threading.Thread):
    """后台探针：每 100ms 做一次 primary 读和一次写入，记录结果。"""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop_flag = threading.Event()
        self.events: list[tuple[float, str, bool, str]] = []
        self.t0 = 0.0

    def run(self) -> None:
        reader = MongoClient(READ_URI, read_preference=ReadPreference.PRIMARY,
                             serverSelectionTimeoutMS=500, socketTimeoutMS=1000)
        writer = MongoClient(WRITE_URI, serverSelectionTimeoutMS=500, socketTimeoutMS=1000)
        try:
            while not self.stop_flag.is_set():
                for op, fn in (("read", lambda: reader["library"]["books"].find_one(
                        {}, {"title": 1, "_id": 0})),
                        ("write", lambda: writer["library"]["books"].update_one(
                        {"isbn": "9787115428028"}, {"$set": {"stock": 15}}))):
                    try:
                        fn()
                        self.events.append((time.monotonic() - self.t0, op, True, ""))
                    except PyMongoError as exc:
                        self.events.append((time.monotonic() - self.t0, op, False,
                                            f"{type(exc).__name__}: {str(exc).splitlines()[0][:60]}"))
                time.sleep(0.1)
        finally:
            reader.close()
            writer.close()


def summarize(events: list[tuple[float, str, bool, str]]) -> None:
    print("\n   故障窗口内的应用请求（每 100ms 一次读 + 一次写）：")
    for op, label in (("read", "primary 读"), ("write", "写入")):
        items = [e for e in events if e[1] == op]
        failed = [e for e in items if not e[2]]
        if not failed:
            print(f"   - {label}：全程成功 {len(items)} 次（未捕捉到失败，说明切换快于探测精度）")
            continue
        first, last = failed[0][0], failed[-1][0]
        reasons = sorted({e[3] for e in failed})
        print(f"   - {label}：共 {len(items)} 次，失败 {len(failed)} 次；"
              f"首次失败 +{first * 1000:.0f} ms，最后失败 +{last * 1000:.0f} ms，"
              f"持续 {last * 1000 - first * 1000:.0f} ms")
        for r in reasons[:2]:
            print(f"       错误样例：{r}")


def main() -> int:
    show_status("1. 故障转移前三成员状态")

    pid = int(open(RS1_PID).read().strip())
    probe = Probe()
    probe.t0 = time.monotonic()
    probe.start()
    time.sleep(0.5)
    os.kill(pid, signal.SIGTERM)
    t0 = probe.t0
    print(f"\n2. 已向 rs1（pid={pid}）发送 SIGTERM，t0={time.strftime('%H:%M:%S')}")

    # ---- 旧主直连采样：证明「原主不可用」在网络上是什么样 ----
    print("   旧主直连采样（directConnection=true，绕过副本集路由，不做重试）：")
    for _ in range(5):
        started = time.monotonic() - t0
        print(f"     +{started * 1000:5.0f} ms  {direct_read_128()}")
        time.sleep(0.35)

    elected_at = None
    while time.monotonic() - t0 < 30:
        for host, port in MEMBERS[1:]:
            try:
                h = hello_direct(host, port, 300)
            except PyMongoError:
                h = None
            if h and h.get("isWritablePrimary"):
                elected_at = time.monotonic() - t0
                print(f"   新主节点已选出：{h['me']}   选举耗时 {elected_at * 1000:.0f} ms")
                break
        if elected_at is not None:
            break
        time.sleep(0.1)

    time.sleep(2.0)
    probe.stop_flag.set()
    probe.join(timeout=3)
    summarize(probe.events)

    if elected_at is None:
        print("\n!! 30 秒内没有选出新主节点，请检查")
        return 1

    st = show_status("3. 新主节点选出后的状态")
    new_primary = [m for m in st["members"] if m["stateStr"] == "PRIMARY"][0]["name"]
    print(f"\n   新主 = {new_primary}；原主 192.168.121.128:27101 已不可写入")

    # ---- 等旧进程彻底退出，否则 dbpath 锁会让重启失败 ----
    print("\n4. 等待原 rs1 进程完全退出（mongod 静默期最长 15s）")
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            print(f"   进程已退出，用时 {time.monotonic() - t0:.1f} s")
            break
        time.sleep(0.5)
    else:
        print("   !! 进程仍未退出")

    print("\n5. 重启 rs1 并等待重新加入")
    t_restart = time.monotonic()
    log_path = os.path.expanduser("~/final/rs1/log/restart.log")
    with open(log_path, "wb") as log:
        subprocess.Popen([MONGOD, "-f", RS1_CONF], stdout=log, stderr=log,
                         start_new_session=True)
    rejoined = None
    while time.monotonic() - t_restart < 120:
        try:
            h = hello_direct("192.168.121.128", 27101, 500)
        except PyMongoError:
            h = None
        if h and h.get("secondary"):
            rejoined = time.monotonic() - t_restart
            print(f"   rs1 已重新加入并成为从节点，重启耗时 {rejoined:.1f} s")
            break
        time.sleep(0.5)
    if rejoined is None:
        print(f"   !! rs1 未能在 120s 内重新加入，检查 {log_path}")
        print(open(log_path, "r", errors="ignore").read()[-800:])
        return 1

    time.sleep(4)
    try:
        st = show_status("6. rs1 重新加入后的最终状态")
        print(f"\n   当前主节点 = {[m['name'] for m in st['members'] if m['stateStr'] == 'PRIMARY'][0]}"
              "（不会自动切回原主，避免服务抖动）")
        print(f"   三成员状态：{', '.join(m['stateStr'] for m in st['members'])}")
    except PyMongoError as exc:
        print(f"   最终状态查询超时（连接正在刷新，属正常现象）：{type(exc).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
