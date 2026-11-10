# -*- coding: utf-8 -*-
"""任务三演示脚本：把任务书要求的 11 项检索 + 5 组统计一次性跑完并打印。

用途：
  1) 答辩/验收时逐屏截图；
  2) 生成 docs/evidence/task3_queries.txt，文档里的每条查询都能在代码里找到同一句。

运行：
  python3 scripts/task3_demo.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_manager as bm
import stat_manager as sm
from display import fmt_dt, section, table, title
from mongodb_connect import MongoConnection, get_db


def counts():
    db = get_db()
    return {
        "books": db.books.count_documents({}),
        "readers": db.readers.count_documents({}),
        "borrow_logs": db.borrow_logs.count_documents({}),
    }


def q1():
    rows = bm.by_category_price("计算机", 50, 120, limit=8)
    section("检索 1：分类=计算机 且 价格 50~120（复合索引 category+price）")
    table(["ISBN", "书名", "分类", "价格", "库存"],
          [[b["isbn"], b["title"], b["category"], b["price"], b["stock"]] for b in rows],
          max_widths={1: 34})


def q2():
    rows = bm.by_tags(["Python", "编程"], mode="or", limit=8)
    section("检索 2：标签多选（$in 命中任一：Python / 编程）")
    table(["书名", "标签", "评分"],
          [[b["title"], ",".join(b.get("tags") or []), b["rating"]] for b in rows],
          max_widths={0: 30, 1: 30})


def q3():
    rows = bm.by_title_like("数据", limit=8)
    section("检索 3：书名模糊匹配「数据」")
    table(["书名", "作者", "出版社"],
          [[b["title"], b["author"], b["publisher"]] for b in rows],
          max_widths={0: 34, 1: 20, 2: 22})


def q4():
    rows = bm.by_publish_year(2018, 2020, limit=8)
    section("检索 4：出版年份 2018—2020（Date 区间比较）")
    table(["书名", "出版日期", "分类"],
          [[b["title"], fmt_dt(b["publish_date"])[:10], b["category"]] for b in rows],
          max_widths={0: 34})


def q5():
    rows = bm.missing_tags()
    section("检索 5：tags 缺失（字段不存在 / null / 空数组）")
    table(["ISBN", "书名", "tags 原值"],
          [[b["isbn"], b["title"], repr(b.get("tags"))] for b in rows],
          max_widths={1: 34})
    print(f"  共 {len(rows)} 条缺失 tags")


def q6():
    rows = bm.top_rated(10)
    section("检索 6：评分 Top10，只返回 3 个字段（title/author/rating）")
    table(["书名", "作者", "评分"],
          [[b["title"], b["author"], b["rating"]] for b in rows],
          max_widths={0: 34, 1: 20})


def s1():
    rows = sm.category_stats()
    section("统计 1：按分类统计（$group 聚合）")
    table(["分类", "册数", "均价", "平均评分", "总库存", "累计借阅"],
          [[r["category"], r["book_count"], r["avg_price"], r["avg_rating"],
            r["total_stock"], r["borrow_total"]] for r in rows])


def s2():
    rows = sm.college_borrow_top5()
    section("统计 2：学院借阅量 Top5（borrow_logs $lookup readers）")
    table(["学院", "借阅次数", "参与读者数"],
          [[r["college"], r["borrow_count"], r["reader_count"]] for r in rows])


def s3():
    rows = sm.monthly_trend()
    section(f"统计 3：借阅量年月趋势（共 {len(rows)} 个月）")
    table(["年月", "借阅次数"], [[r["month"], r["borrow_count"]] for r in rows], limit_rows=12)


def s4():
    rows = sm.top_borrowed_books(10)
    section("统计 4：借阅次数最多的 10 本 + 馆藏位置（$lookup books）")
    table(["ISBN", "书名", "分类", "借阅", "楼层", "书架"],
          [[r["isbn"], r["title"], r["category"], r["borrow_count"], r["floor"], r["shelf"]] for r in rows],
          max_widths={1: 28})


def s5():
    n = sm.write_category_stats()
    section(f"统计 5：分类统计写入新集合 category_stats（$merge 共 {n} 个分类）")
    rows = list(get_db()["category_stats"].find({}).sort("book_count", -1))
    table(["分类", "册数", "均价", "累计借阅"],
          [[r["_id"], r.get("book_count"), r.get("avg_price"), r.get("total_borrow")] for r in rows])


def indexes():
    db = get_db()
    section("索引清单（三个集合）")
    total = 0
    for name in ("books", "readers", "borrow_logs"):
        idx = list(db[name].list_indexes())
        total += len(idx)
        print(f"  {name}: {len(idx)} 个索引")
        for i in idx:
            print(f"    - {i['name']:<28} {dict(i['key'])}")
    print(f"  合计 {total} 个索引（含默认 _id）")


def main() -> int:
    print("=" * 96)
    print("  智慧图书馆数字资源平台 —— 任务三：数据导入核对 / 检索统计 / 索引 / 访问控制")
    print("=" * 96)
    print(f"  服务器：{MongoConnection.instance().server_line()}")
    print(f"  集合计数：{counts()}")

    title("第一部分：11 项检索与统计")
    q1(); q2(); q3(); q4(); q5(); q6()
    s1(); s2(); s3(); s4(); s5()

    title("第二部分：索引清单")
    indexes()

    print("\n完成。审计日志最近 5 条：")
    for row in get_db().audit_logs.find().sort("$natural", -1).limit(5):
        print(f"  {fmt_dt(row.get('ts'))}  {row.get('action'):<8} {row.get('target')}  {row.get('detail')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
