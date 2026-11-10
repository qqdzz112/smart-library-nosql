# -*- coding: utf-8 -*-
"""终端输出辅助：中文宽度对齐的表格、分节标题、键值块。

MongoDB 里的书名/作者是中文，用 len() 对齐会错位，这里按东亚宽字符算 2 列宽。
"""
from __future__ import annotations

import unicodedata

WIDE = ("W", "F")


def char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in WIDE else 1


def text_width(text: object) -> int:
    return sum(char_width(ch) for ch in str(text))


def truncate(text: object, width: int) -> str:
    """按显示宽度截断，超出用 … 结尾。"""
    text = str(text)
    if text_width(text) <= width:
        return text
    out, used = [], 0
    for ch in text:
        w = char_width(ch)
        if used + w > width - 1:
            break
        out.append(ch)
        used += w
    return "".join(out) + "…"


def pad(text: object, width: int, align: str = "left") -> str:
    text = str(text)
    space = max(0, width - text_width(text))
    if align == "right":
        return " " * space + text
    return text + " " * space


def title(text: str, width: int = 96) -> None:
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def section(text: str) -> None:
    print(f"\n--- {text} " + "-" * max(0, 60 - text_width(text)))


def kv_block(pairs: list[tuple[str, object]]) -> None:
    key_width = max(text_width(k) for k, _ in pairs) + 2
    for key, value in pairs:
        print(f"  {pad(key + ':', key_width)}{value}")


def table(headers: list[str], rows: list[list[object]], max_widths: dict[int, int] | None = None,
          align: dict[int, str] | None = None, limit_rows: int = 50) -> None:
    """打印表格；max_widths 指定某列最大显示宽度，超出截断。"""
    max_widths = max_widths or {}
    align = align or {}
    shown = rows[:limit_rows]
    cells = [[truncate(c, max_widths.get(i, 60)) for i, c in enumerate(r)] for r in shown]
    widths = []
    for i, head in enumerate(headers):
        col = [text_width(r[i]) for r in cells] or [0]
        widths.append(max(text_width(head), max(col)))
    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(line)
    print("| " + " | ".join(pad(h, widths[i]) for i, h in enumerate(headers)) + " |")
    print(line)
    for row in cells:
        print("| " + " | ".join(pad(c, widths[i], align.get(i, "left")) for i, c in enumerate(row)) + " |")
    print(line)
    if len(rows) > len(shown):
        print(f"  （共 {len(rows)} 条，仅显示前 {len(shown)} 条）")
    elif not rows:
        print("  （无匹配记录）")


def fmt_dt(value: object) -> str:
    """把 datetime 显示成 2024-03-01 10:00，缺失显示 -。"""
    if value is None:
        return "-"
    try:
        return value.strftime("%Y-%m-%d %H:%M")
    except AttributeError:
        return str(value)
