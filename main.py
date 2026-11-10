#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""智慧图书馆数字资源平台 —— 命令行主程序（任务四 F7）。

菜单项与任务书功能一一对应：
 1 馆藏检索（6 类查询）      2 图书管理（增删改查）
 3 读者管理（检索/新增/删除）  4 借阅管理（借书/还书/逾期/流水/导出）
 5 统计分析（5 组聚合）        6 电子书与封面（GridFS）
 7 审计日志（最近 100 条）     8 数据库与集群状态
 9 统计结果导出              0 退出

运行前用环境变量指定连接信息，例如：
    export LIB_DB_HOST=127.0.0.1 LIB_DB_PORT=27017
    export LIB_DB_USER=lib_writer LIB_DB_PASSWORD=*** LIB_DB_AUTH_DB=library
    python3 main.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from bson import ObjectId

import audit_logger
import book_manager
import borrow_manager
import display
import gridfs_manager
import reader_manager
import stat_manager
from config import settings
from mongodb_connect import MongoConnection


def ask(prompt: str, default: str = "") -> str:
    try:
        value = input(f"{prompt}{f'（默认 {default}）' if default else ''}: ").strip()
    except EOFError:
        print()
        raise SystemExit(0)
    return value or default


def ask_int(prompt: str, default: int | None = None) -> int | None:
    raw = ask(prompt, "" if default is None else str(default))
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        print("  ! 请输入整数")
        return None


def pause() -> None:
    try:
        input("\n按回车继续…")
    except EOFError:
        raise SystemExit(0)


# ------------------------------------------------------------------ 启动横幅
def show_startup() -> None:
    conn = MongoConnection.instance()
    display.title("智慧图书馆数字资源平台 · 命令行管理程序")
    display.kv_block([
        ("连接串", settings.masked_uri.replace(settings.password, "***") if settings.user else settings.masked_uri),
        ("服务器", conn.server_line()),
        ("当前账号", settings.user or "匿名"),
        ("数据库", settings.db_name),
    ])
    rows = [[name, count if count >= 0 else "读取失败"] for name, count in conn.collection_counts()]
    display.section("集合文档数")
    display.table(["集合", "文档数"], rows, align={1: "right"})


# ------------------------------------------------------------------ 各功能
def menu_search() -> None:
    while True:
        display.title("1. 馆藏检索")
        print("  1) 分类 + 价格区间      2) 标签多选（任一 / 全部）")
        print("  3) 书名模糊查询          4) 出版年份区间")
        print("  5) 缺失 tags 的图书      6) 评分 Top10（仅三个字段）")
        print("  0) 返回")
        choice = ask("请选择")
        if choice in ("0", ""):
            return
        if choice == "1":
            category = ask("分类（留空=全部）")
            low = ask("最低价")
            high = ask("最高价")
            rows = book_manager.by_category_price(category or None,
                                                  float(low) if low else None,
                                                  float(high) if high else None)
            display.table(["ISBN", "书名", "分类", "价格", "库存", "评分"],
                          [[r["isbn"], r["title"], r["category"], f"{r['price']:.1f}", r["stock"], r["rating"]]
                           for r in rows], max_widths={1: 32})
        elif choice == "2":
            tags = [t for t in ask("标签（逗号分隔）").replace("，", ",").split(",") if t.strip()]
            mode = ask("匹配方式 or/and", "or")
            rows = book_manager.by_tags(tags, mode)
            display.table(["ISBN", "书名", "标签", "库存"],
                          [[r["isbn"], r["title"], ",".join(r.get("tags") or []), r["stock"]] for r in rows],
                          max_widths={1: 30, 2: 24})
        elif choice == "3":
            rows = book_manager.by_title_like(ask("书名关键字"))
            display.table(["ISBN", "书名", "作者", "出版社"],
                          [[r["isbn"], r["title"], r["author"], r["publisher"]] for r in rows],
                          max_widths={1: 30, 2: 16, 3: 18})
        elif choice == "4":
            y1 = ask_int("起始年份", 2020)
            y2 = ask_int("结束年份", 2023)
            rows = book_manager.by_publish_year(y1, y2)
            display.table(["ISBN", "书名", "出版日期"],
                          [[r["isbn"], r["title"], display.fmt_dt(r["publish_date"])] for r in rows],
                          max_widths={1: 34})
        elif choice == "5":
            rows = book_manager.missing_tags()
            display.table(["ISBN", "书名", "tags 字段"],
                          [[r["isbn"], r["title"], "缺失" if r.get("tags") is None else r.get("tags")] for r in rows],
                          max_widths={1: 34})
        elif choice == "6":
            rows = book_manager.top_rated(10)
            display.table(["书名", "作者", "评分", "借阅次数"],
                          [[r["title"], r["author"], r["rating"], r["borrow_count"]] for r in rows],
                          max_widths={0: 34, 1: 16}, align={2: "right", 3: "right"})
        pause()


def menu_books() -> None:
    while True:
        display.title("2. 图书管理")
        print("  1) 浏览藏书   2) 按 ISBN 查看   3) 新增图书   4) 修改库存/价格   5) 删除图书   0) 返回")
        choice = ask("请选择")
        if choice in ("0", ""):
            return
        if choice == "1":
            rows = book_manager.list_all(30)
            display.table(["ISBN", "书名", "分类", "库存", "价格"],
                          [[r["isbn"], r["title"], r["category"], r["stock"], f"{r['price']:.1f}"] for r in rows],
                          max_widths={1: 32})
        elif choice == "2":
            doc = book_manager.get(ask("ISBN"))
            if doc:
                display.kv_block([(k, doc.get(k)) for k in
                                  ("isbn", "title", "author", "publisher", "category", "price", "stock",
                                   "rating", "borrow_count", "tags", "ebook_name", "location")])
            else:
                print("  未找到该 ISBN")
        elif choice == "3":
            doc = {
                "isbn": ask("ISBN"),
                "title": ask("书名"),
                "author": ask("作者"),
                "publisher": ask("出版社", "未知"),
                "category": ask("分类", "计算机"),
                "price": float(ask("价格", "0")),
                "rating": float(ask("评分", "4.5")),
                "stock": int(ask("库存", "1")),
                "publish_date": datetime.now(timezone.utc),
                "borrow_count": 0,
                "tags": [t for t in ask("标签（逗号分隔）").split(",") if t.strip()],
                "location": {"floor": ask("楼层区域", "二楼专业图书区"), "shelf": ask("书架号", "Z-01"), "copies": 1},
                "ebook_name": None,
            }
            print("  新增成功" if book_manager.add(doc) else "  新增失败")
        elif choice == "4":
            isbn = ask("ISBN")
            stock = ask("新库存（回车跳过）")
            price = ask("新价格（回车跳过）")
            fields = {}
            if stock:
                fields["stock"] = int(stock)
            if price:
                fields["price"] = float(price)
            print("  修改成功" if fields and book_manager.update(isbn, fields) else "  未修改")
        elif choice == "5":
            isbn = ask("要删除的 ISBN")
            print("  已删除" if book_manager.delete(isbn) else "  未找到或删除失败")
        pause()


def menu_readers() -> None:
    while True:
        display.title("3. 读者管理")
        print("  1) 检索读者   2) 读者借阅史   3) 新增读者   4) 删除读者   0) 返回")
        choice = ask("请选择")
        if choice in ("0", ""):
            return
        if choice == "1":
            rows = reader_manager.search(ask("姓名/卡号关键字"), ask("学院（可空）"), ask("等级（可空）"))
            display.table(["借书证号", "姓名", "学院", "等级", "邮箱", "注册日期"],
                          [[r["card_no"], r["name"], r["college"], r["level"], r.get("email") or "-",
                            display.fmt_dt(r.get("register_date"))] for r in rows],
                          max_widths={2: 16, 4: 20})
        elif choice == "2":
            rows = borrow_manager.reader_history(ask("借书证号"))
            display.table(["借阅日期", "书名", "状态", "天数"],
                          [[display.fmt_dt(r["borrow_date"]), r.get("title", "-"), r["status"], r["duration_days"]]
                           for r in rows], max_widths={1: 30})
        elif choice == "3":
            doc = {
                "card_no": ask("借书证号"),
                "name": ask("姓名"),
                "college": ask("学院", "计算机学院"),
                "email": ask("邮箱", "") or None,
                "phone": ask("电话", ""),
                "level": ask("等级 普通/高级/教师", "普通"),
                "register_date": datetime.now(timezone.utc),
                "fav_categories": [c for c in ask("偏好分类（逗号分隔）").split(",") if c.strip()],
            }
            print("  新增成功" if reader_manager.add(doc) else "  新增失败")
        elif choice == "4":
            print("  已删除" if reader_manager.delete(ask("借书证号")) else "  未找到")
        pause()


def menu_borrow() -> None:
    while True:
        display.title("4. 借阅管理")
        print("  1) 办理借书   2) 办理还书   3) 扫描并标记逾期   4) 借阅流水查询   5) 导出流水   0) 返回")
        choice = ask("请选择")
        if choice in ("0", ""):
            return
        if choice == "1":
            ok, msg = borrow_manager.borrow(ask("借书证号"), ask("ISBN"))
            print(("  ✓ " if ok else "  ✗ ") + msg)
        elif choice == "2":
            ok, msg = borrow_manager.return_book(ask("借书证号"), ask("ISBN"))
            print(("  ✓ " if ok else "  ✗ ") + msg)
        elif choice == "3":
            print(f"  已标记逾期 {borrow_manager.mark_overdue()} 条")
        elif choice == "4":
            rows = borrow_manager.list_logs(ask("借书证号（可空）"), ask("ISBN（可空）"),
                                            ask("状态 已归还/借出/逾期（可空）"), 20)
            display.table(["借阅日期", "读者", "ISBN", "状态", "天数", "归还日期"],
                          [[display.fmt_dt(r["borrow_date"]), r["reader_card"], r["book_isbn"], r["status"],
                            r["duration_days"], display.fmt_dt(r.get("return_date"))] for r in rows])
        elif choice == "5":
            path, count = borrow_manager.export_logs(ask("格式 json/csv", "csv"))
            print(f"  已导出 {count} 条 → {path}")
        pause()


def menu_stats() -> None:
    while True:
        display.title("5. 统计分析")
        print("  1) 分类统计   2) 学院借阅 Top5   3) 年月趋势   4) 借阅最多的 10 本")
        print("  5) 生成分类统计集合 category_stats   6) 读者等级/状态/活跃读者   0) 返回")
        choice = ask("请选择")
        if choice in ("0", ""):
            return
        if choice == "1":
            rows = stat_manager.category_stats()
            display.table(["分类", "册数", "均价", "平均评分", "总库存", "被借次数"],
                          [[r["category"], r["book_count"], f"{r['avg_price']:.2f}", f"{r['avg_rating']:.2f}",
                            r["total_stock"], r["borrow_total"]] for r in rows], align={1: "right", 4: "right", 5: "right"})
        elif choice == "2":
            rows = stat_manager.college_borrow_top5()
            display.table(["学院", "借阅次数", "读者数"],
                          [[r["college"], r["borrow_count"], r["reader_count"]] for r in rows],
                          align={1: "right", 2: "right"})
        elif choice == "3":
            rows = stat_manager.monthly_trend()
            display.table(["年月", "借阅次数"], [[r["month"], r["borrow_count"]] for r in rows],
                          align={1: "right"})
        elif choice == "4":
            rows = stat_manager.top_borrowed_books(10)
            display.table(["ISBN", "书名", "分类", "借阅次数", "馆藏位置"],
                          [[r["isbn"], r["title"], r["category"], r["borrow_count"], f"{r['floor']} {r['shelf']}"]
                           for r in rows], max_widths={1: 28, 4: 22}, align={3: "right"})
        elif choice == "5":
            print(f"  category_stats 已重建，共 {stat_manager.write_category_stats()} 个分类文档")
        elif choice == "6":
            print("  [读者等级]")
            display.table(["等级", "借阅次数", "平均借阅天数"],
                          [[r["level"], r["borrow_count"], r["avg_days"]] for r in stat_manager.reader_level_stats()],
                          align={1: "right", 2: "right"})
            print("  [借阅状态]")
            display.table(["状态", "条数", "平均天数"],
                          [[r["status"], r["count"], r["avg_days"]] for r in stat_manager.status_stats()],
                          align={1: "right", 2: "right"})
            print("  [活跃读者 Top10]")
            display.table(["借书证号", "姓名", "学院", "借阅次数"],
                          [[r["card_no"], r["name"], r["college"], r["borrow_count"]] for r in stat_manager.active_readers()],
                          max_widths={2: 16}, align={3: "right"})
        pause()


def menu_gridfs() -> None:
    display.title("6. 电子书与封面（GridFS）")
    print("  1) 查看文件列表   2) 上传文件   3) 按书名下载并校验   4) 存储统计   0) 返回")
    choice = ask("请选择")
    if choice == "1":
        kind = ask("类型 ebook/cover（可空）") or None
        rows = gridfs_manager.list_files(kind)
        display.table(["文件名", "ISBN", "类型", "字节数", "MD5前12位", "上传时间"],
                      [[r["filename"], r["isbn"], r["type"], r["bytes"], r["md5"], display.fmt_dt(r["upload"])]
                       for r in rows], align={3: "right"})
    elif choice == "2":
        path = ask("本地文件路径")
        isbn = ask("ISBN")
        kind = ask("类型 ebook/cover", "ebook")
        info = gridfs_manager.upload(path, isbn, kind)
        print(f"  ✓ 已上传 {info['filename']}（{info['bytes']} 字节），file_id={info['file_id']}")
    elif choice == "3":
        result = gridfs_manager.download_by_title(ask("书名关键字"), ask("类型 ebook/cover", "ebook"))
        if result.get("ok"):
            print(f"  ✓ 下载完成：{result['book']} → {result['path']}")
            print(f"    期望 {result['expected_bytes']} 字节 / 实际 {result['actual_bytes']} 字节，MD5 一致：{result['md5_match']}")
        else:
            print(f"  ✗ {result.get('reason') or '字节数或 MD5 校验失败'}")
    elif choice == "4":
        display.kv_block(list(gridfs_manager.stats().items()))
    pause()


def menu_audit() -> None:
    display.title("7. 审计日志（最近 100 条，按时间倒序）")
    rows = audit_logger.recent(100)
    display.table(["时间", "账号", "动作", "集合", "目标", "结果"],
                  [[display.fmt_dt(r["ts"]), r["actor"], r["action"], r["collection"],
                    display.truncate(r["target"], 28), r["result"]] for r in rows],
                  max_widths={4: 28})
    display.section("按动作统计")
    display.table(["动作", "条数"], [[r["_id"], r["count"]] for r in audit_logger.summary()], align={1: "right"})
    pause()


def menu_status() -> None:
    conn = MongoConnection.instance()
    db = conn.get_database()
    display.title("8. 数据库与集群状态")
    display.kv_block([
        ("服务器", conn.server_line()),
        ("连接串", settings.masked_uri),
        ("数据库", settings.db_name),
    ])
    display.section("集合与索引")
    for name in sorted(db.list_collection_names()):
        indexes = [f"{k}:{v}" for k, v in db[name].index_information().items()]
        print(f"  {name:<16} 文档 {db[name].count_documents({}):>6}  索引 {len(indexes)}  {', '.join(sorted(indexes))}")
    pause()


def menu_export() -> None:
    display.title("9. 统计结果导出")
    path = stat_manager.export_all()
    print(f"  ✓ 已导出统计结果：{path}")
    pause()


def main() -> int:
    if not MongoConnection.instance().ping():
        print("请检查数据库是否已启动、账号密码是否正确。")
        return 1
    os.makedirs(settings.export_dir, exist_ok=True)
    show_startup()
    handlers = {
        "1": menu_search, "2": menu_books, "3": menu_readers, "4": menu_borrow,
        "5": menu_stats, "6": menu_gridfs, "7": menu_audit, "8": menu_status, "9": menu_export,
    }
    while True:
        display.title("主菜单")
        print("  1 馆藏检索     2 图书管理     3 读者管理")
        print("  4 借阅管理     5 统计分析     6 电子书与封面(GridFS)")
        print("  7 审计日志     8 数据库状态   9 统计结果导出      0 退出")
        choice = ask("请选择")
        if choice in ("0", "q"):
            print("再见。")
            return 0
        handler = handlers.get(choice)
        if handler:
            try:
                handler()
            except Exception as exc:  # noqa: BLE001 - 演示程序不因单次操作崩溃
                print(f"  [操作失败] {exc}")
                pause()
        else:
            print("  无效选项")


if __name__ == "__main__":
    sys.exit(main())
