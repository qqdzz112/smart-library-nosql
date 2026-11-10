# -*- coding: utf-8 -*-
"""性能对比：同一查询在“无索引 / 有索引”下的执行计划与耗时（任务三 F5）。

做法：对每个查询先删除对应索引，采样 N 次取中位数；再创建索引，同样采样 N 次。
指标取 MongoDB 的 executionStats：nReturned / totalKeysExamined /
totalDocsExamined / executionTimeMillis，并额外用 perf_counter 批量计时，
因为只有 50/3000 条数据时 executionTimeMillis 常常是 0 ms，无法比较倍数。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mongodb_connect import get_db  # noqa: E402
from scripts.create_indexes import create_all  # noqa: E402

QUERIES = [
    {
        "name": "Q1 分类+价格区间",
        "coll": "books",
        "filter": {"category": "计算机", "price": {"$gte": 50, "$lte": 100}},
        "sort": [("price", 1)],
        "limit": 20,
        "index": ("books", "idx_category_price", [("category", 1), ("price", 1)]),
    },
    {
        "name": "Q2 读者借阅流水（按时间倒序）",
        "coll": "borrow_logs",
        "filter": {"reader_card": "R20240007"},
        "sort": [("borrow_date", -1)],
        "limit": 20,
        "index": ("borrow_logs", "idx_reader_borrowdate", [("reader_card", 1), ("borrow_date", -1)]),
    },
    {
        "name": "Q3 状态过滤（已归还，按借阅时间倒序取 20 条）",
        "coll": "borrow_logs",
        "filter": {"status": "已归还"},
        "sort": [("borrow_date", -1)],
        "limit": 20,
        "index": ("borrow_logs", "idx_status_borrowdate", [("status", 1), ("borrow_date", -1)]),
    },
    {
        "name": "Q4 借阅日期区间（2024 上半年）",
        "coll": "borrow_logs",
        "filter": {"borrow_date": {"$gte": datetime(2024, 1, 1, tzinfo=timezone.utc),
                                   "$lt": datetime(2024, 7, 1, tzinfo=timezone.utc)}},
        "sort": [("borrow_date", -1)],
        "limit": 50,
        "index": ("borrow_logs", "idx_borrowdate", [("borrow_date", -1)]),
    },
]


def run_once(coll, spec: dict) -> dict:
    # 用 explain 命令而不是 cursor.explain("executionStats")：pymongo 4 的
    # Cursor.explain() 只接受 1 个参数（TypeError: takes 1 positional argument but 2 were given）。
    cmd = {"find": coll.name, "filter": spec["filter"], "limit": spec["limit"]}
    if spec.get("sort"):
        cmd["sort"] = dict(spec["sort"])
    plan = coll.database.command({"explain": cmd, "verbosity": "executionStats"})
    stats = plan.get("executionStats", {})
    return {
        "nReturned": stats.get("nReturned"),
        "keys": stats.get("totalKeysExamined"),
        "docs": stats.get("totalDocsExamined"),
        "ms": stats.get("executionTimeMillis"),
        "stage": plan.get("queryPlanner", {}).get("winningPlan", {}).get("stage"),
    }


def _timed_batch(coll, spec: dict, iters: int) -> float:
    """跑 iters 次查询，返回单次平均耗时（毫秒）。"""
    start = time.perf_counter()
    for _ in range(iters):
        cursor = coll.find(spec["filter"])
        if spec.get("sort"):
            cursor = cursor.sort(spec["sort"])
        list(cursor.limit(spec["limit"]))
    return (time.perf_counter() - start) * 1000.0 / iters


def sample(coll, spec: dict, repeat: int) -> dict:
    plan = run_once(coll, spec)
    batches = [_timed_batch(coll, spec, 50) for _ in range(repeat)]
    return {
        "ms_median": round(statistics.median(batches), 3),
        "ms_min": round(min(batches), 3),
        "docs": plan["docs"] or 0,
        "keys": plan["keys"] or 0,
        "nReturned": plan["nReturned"],
        "stage": plan["stage"],
        "samples": [round(b, 3) for b in batches],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                      "docs", "evidence", "perf_index.json"))
    args = parser.parse_args()
    db = get_db()
    create_all(db, verbose=False)
    results = []
    for spec in QUERIES:
        coll_name, index_name, keys = spec["index"]
        coll = db[coll_name]
        if index_name in coll.index_information():
            coll.drop_index(index_name)
        before = sample(coll, spec, args.repeat)
        coll.create_index(keys, name=index_name)
        after = sample(coll, spec, args.repeat)
        speedup = (before["ms_median"] / after["ms_median"]) if after["ms_median"] else float("inf")
        doc_reduce = (before["docs"] / after["docs"]) if after["docs"] else float("inf")
        results.append({
            "query": spec["name"], "collection": coll_name, "index": index_name,
            "filter": json.loads(json.dumps(spec["filter"], default=str)),
            "before": before, "after": after,
            "speedup": round(speedup, 2), "docs_reduced": round(doc_reduce, 2),
        })
        print(f"\n{spec['name']}  （{coll_name}.{index_name}）")
        print(f"  建索引前：命中 {before['nReturned']} 条，扫描文档 {before['docs']:.0f}，"
              f"单次平均 {before['ms_median']:.3f} ms（中位数），计划阶段 {before['stage']}")
        print(f"  建索引后：命中 {after['nReturned']} 条，扫描文档 {after['docs']:.0f}，"
              f"单次平均 {after['ms_median']:.3f} ms（中位数），计划阶段 {after['stage']}")
        print(f"  提速 {speedup:.2f} 倍，扫描文档数降为 1/{doc_reduce:.2f}")
        create_all(db, verbose=False)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now().isoformat(timespec="seconds"),
                   "repeat": args.repeat, "results": results}, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已写入 {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
