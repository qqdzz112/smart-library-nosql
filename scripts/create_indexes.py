# -*- coding: utf-8 -*-
"""索引清单（任务三 F5）：定义、创建、删除与说明。

每条索引都对应文档里的一个查询场景，避免“为了建索引而建索引”。
运行：
    python3 scripts/create_indexes.py            # 创建缺失索引
    python3 scripts/create_indexes.py --list     # 只打印清单
    python3 scripts/create_indexes.py --drop QUERY_PERF  # 性能对比前删除
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import ASCENDING, DESCENDING  # noqa: E402

from mongodb_connect import get_db  # noqa: E402

# (集合, 索引名, 键, 唯一?, 说明)
INDEX_SPECS = [
    ("books", "uk_isbn", [("isbn", ASCENDING)], True, "ISBN 唯一，借还书与 GridFS 关联都按 isbn 精确匹配"),
    ("books", "idx_category_price", [("category", ASCENDING), ("price", ASCENDING)], False,
     "检索 1：分类 + 价格区间，等值在前、范围在后，可直接用索引范围扫描"),
    ("books", "idx_tags", [("tags", ASCENDING)], False, "检索 2：标签多选（多键索引，$in / $all 均可命中）"),
    ("books", "idx_publish_date", [("publish_date", DESCENDING)], False,
     "检索 4：出版年份区间 + 按出版日期倒序"),
    ("books", "idx_rating_borrow", [("rating", DESCENDING), ("borrow_count", DESCENDING)], False,
     "检索 6：评分 Top10；borrow_count 作次序键保证同分结果稳定"),
    ("readers", "uk_card_no", [("card_no", ASCENDING)], True, "借书证号唯一，借还书按卡号定位读者"),
    ("readers", "idx_college_level", [("college", ASCENDING), ("level", ASCENDING)], False,
     "读者按学院 + 等级组合筛选"),
    ("readers", "idx_name", [("name", ASCENDING)], False, "按姓名精确/前缀查找"),
    ("borrow_logs", "idx_reader_borrowdate", [("reader_card", ASCENDING), ("borrow_date", DESCENDING)], False,
     "读者借阅史：等值 reader_card + 按时间倒序，可避免排序阶段"),
    ("borrow_logs", "idx_book_borrowdate", [("book_isbn", ASCENDING), ("borrow_date", DESCENDING)], False,
     "图书借阅流水：某本书的借阅时间线"),
    ("borrow_logs", "idx_status_borrowdate", [("status", ASCENDING), ("borrow_date", DESCENDING)], False,
     "按状态（借出/逾期）巡检 + 时间排序"),
    ("borrow_logs", "idx_borrowdate", [("borrow_date", DESCENDING)], False,
     "年月趋势统计、最近 N 条流水"),
]

# 性能对比要临时删除的索引（非唯一）
QUERY_PERF = ("books", "idx_category_price")


def create_all(db=None, verbose: bool = True) -> list[str]:
    if db is None:  # pymongo 4.x 的 Database 不支持真值判断
        db = get_db()
    created = []
    for coll, name, keys, unique, _desc in INDEX_SPECS:
        existing = db[coll].index_information()
        if name in existing:
            if verbose:
                print(f"  = {coll}.{name} 已存在，跳过")
            continue
        db[coll].create_index(keys, name=name, unique=unique)
        created.append(f"{coll}.{name}")
        if verbose:
            print(f"  + {coll}.{name} 创建成功")
    return created


def print_specs() -> None:
    print(f"{'集合':<12}{'索引名':<26}{'唯一':<6}说明")
    print("-" * 110)
    for coll, name, keys, unique, desc in INDEX_SPECS:
        print(f"{coll:<12}{name:<26}{'是' if unique else '否':<6}{desc}")
        print(f"  键: {dict(keys)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="只打印索引清单")
    parser.add_argument("--drop", metavar="INDEX_NAME", help="删除指定索引（性能对比用）")
    args = parser.parse_args()
    if args.list:
        print_specs()
        return 0
    if args.drop:
        for coll, name, _keys, _u, _d in INDEX_SPECS:
            if name == args.drop:
                get_db()[coll].drop_index(name)
                print(f"已删除 {coll}.{name}")
                return 0
        print(f"索引 {args.drop} 不在清单中")
        return 1
    create_all()
    print(f"\n当前 books 索引：{sorted(get_db()['books'].index_information())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
