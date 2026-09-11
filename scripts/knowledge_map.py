#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
knowledge_map.py — 生成「概念知识图谱」内联 SVG。

一张图回答 F6「联系其它概念」：
    · 左侧 = 下楼（前置概念，箭头指向中心）
    · 中间 = 本概念（高亮）
    · 右侧 = 上楼（由它推出的后续结论，箭头离开中心）
    · 下方 = 平移（同类 / 对偶概念，双向虚线）

被 md2card.py 调用；也可单独运行做自测：
    python knowledge_map.py
"""

import html
import json
import re

# ---------- 配色（与概念卡 CSS 保持一致） ----------
C_DOWN = dict(fill="#eef2f6", stroke="#b9c4cf", text="#33414d")
C_UP = dict(fill="#e8f5ef", stroke="#a9d3c1", text="#17674a")
C_LAT = dict(fill="#f1ecfa", stroke="#c3b0e0", text="#5b3f8f")
C_MID = dict(fill="#2f6fb3", stroke="#20507f", text="#ffffff")

BOX_W, BOX_H = 178, 36
MID_W, MID_H = 196, 46
GAP = 14
LEGEND_H = 34
ROWS_TOP = 8


def text_w(s, fs):
    """粗略估算文本宽度（CJK 按 1em，其余按 0.56em）。"""
    w = 0.0
    for ch in s:
        w += fs if ord(ch) > 0x2E80 else fs * 0.56
    return w


def fit_font(s, box_w, start=13.0, floor=9.0):
    fs = start
    while fs > floor and text_w(s, fs) > box_w - 22:
        fs -= 0.5
    return fs


def esc(s):
    return html.escape(str(s), quote=True)


def parse_spec(text):
    """接受 JSON，或简单的 `key: value` 行格式（更手写友好）。"""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    spec = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_]+)\s*[:：]\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip()
        if key in ("down", "up", "lateral"):
            parts = re.split(r"[,，、;；]", val)
            spec[key] = [p.strip() for p in parts if p.strip()]
        else:
            spec[key] = val
    return spec


def render_svg(spec):
    concept = spec.get("concept") or "本概念"
    down = list(spec.get("down") or [])
    up = list(spec.get("up") or [])
    lateral = list(spec.get("lateral") or [])
    note = spec.get("note") or ""
    course = spec.get("course") or ""

    rows = max(len(down), len(up), 1)
    main_h = rows * BOX_H + (rows - 1) * GAP
    lat_h = (26 + BOX_H) if lateral else 0
    H = ROWS_TOP + LEGEND_H + main_h + 28 + lat_h + 26

    # 中心
    cx = 340.0
    cy = ROWS_TOP + LEGEND_H + main_h / 2.0
    # 左右列中心
    lx = 108.0
    rx = 572.0
    # 汇流竖干线
    trunk_l = cx - MID_W / 2.0 - 26
    trunk_r = cx + MID_W / 2.0 + 26

    P = []
    # 注意：SVG 必须逐元素换行（不能挤成一行），否则 pandoc 会在空格处折断长行。
    P.append(
        f'<svg class="km-svg" viewBox="0 0 680 {H:.0f}" width="100%" role="img" '
        f'aria-label="{esc(concept)} 的知识图谱">'
    )
    P.append(f'<rect class="km-bg" x="0" y="0" width="680" height="{H:.0f}"/>')
    P.append(
        '<defs>'
        '<marker id="km-ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#8a97a3"/></marker>'
        '<marker id="km-ar2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
        'markerHeight="6" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="#a693cc"/></marker>'
        '</defs>'
    )

    # ---- 图例 ----
    P.append(f'<text class="km-ttl" x="18" y="20">{esc(concept)} · 知识图谱</text>')
    lgd = [("下楼 · 前置", C_DOWN), ("本概念", C_MID), ("上楼 · 后续", C_UP)]
    if lateral:
        lgd.append(("平移 · 对偶", C_LAT))
    bx = 18
    for label, col in lgd:
        P.append(f'<rect x="{bx}" y="25" width="11" height="11" rx="3" '
                 f'fill="{col["fill"]}" stroke="{col["stroke"]}"/>')
        P.append(f'<text class="km-lg" x="{bx + 16}" y="35">{esc(label)}</text>')
        bx += 16 + text_w(label, 11) + 20

    # ---- 左侧：前置 ----
    for i, name in enumerate(down):
        y = cy - main_h / 2.0 + i * (BOX_H + GAP)
        P.append(_box(lx, y + BOX_H / 2.0, BOX_W, BOX_H, name, C_DOWN))
        P.append(f'<path d="M{lx + BOX_W / 2:.1f},{y + BOX_H / 2:.1f} H{trunk_l:.1f}" '
                 f'fill="none" stroke="#8a97a3" stroke-width="1.4"/>')

    # ---- 右侧：后续 ----
    for i, name in enumerate(up):
        y = cy - main_h / 2.0 + i * (BOX_H + GAP)
        P.append(_box(rx, y + BOX_H / 2.0, BOX_W, BOX_H, name, C_UP))
        P.append(f'<path d="M{trunk_r:.1f},{y + BOX_H / 2:.1f} H{rx - BOX_W / 2:.1f}" '
                 f'fill="none" stroke="#8a97a3" stroke-width="1.4" marker-end="url(#km-ar)"/>')

    # ---- 汇流干线 + 到中心 ----
    if down:
        P.append(f'<path d="M{trunk_l:.1f},{cy - main_h / 2:.1f} V{cy + main_h / 2:.1f}" '
                 f'fill="none" stroke="#8a97a3" stroke-width="1.4"/>')
        P.append(f'<path d="M{trunk_l:.1f},{cy:.1f} H{cx - MID_W / 2:.1f}" '
                 f'fill="none" stroke="#8a97a3" stroke-width="1.6" marker-end="url(#km-ar)"/>')
    if up:
        P.append(f'<path d="M{trunk_r:.1f},{cy - main_h / 2:.1f} V{cy + main_h / 2:.1f}" '
                 f'fill="none" stroke="#8a97a3" stroke-width="1.4"/>')
        P.append(f'<path d="M{cx + MID_W / 2:.1f},{cy:.1f} H{trunk_r:.1f}" '
                 f'fill="none" stroke="#8a97a3" stroke-width="1.6" marker-end="url(#km-ar)"/>')

    # ---- 中心节点 ----
    if course:
        P.append(f'<text class="km-cap" x="{cx:.1f}" y="{cy - MID_H / 2 - 10:.1f}">'
                 f'{esc(course)}</text>')
    P.append(_box(cx, cy, MID_W, MID_H, concept, C_MID, bold=True))

    # ---- 下方：平移（对偶） ----
    if lateral:
        ly = cy + main_h / 2 + 28 + BOX_H / 2.0
        P.append(f'<text class="km-cap" x="{cx:.1f}" y="{ly - BOX_H / 2 - 8:.1f}">'
                 f'平移 · 同类或对偶概念（双向）</text>')
        n = len(lateral)
        total_w = n * BOX_W + (n - 1) * GAP
        start = cx - total_w / 2.0
        for i, name in enumerate(lateral):
            x = start + i * (BOX_W + GAP) + BOX_W / 2.0
            P.append(_box(x, ly, BOX_W, BOX_H, name, C_LAT))
            P.append(f'<path d="M{x:.1f},{ly - BOX_H / 2 - 4:.1f} V{cy + MID_H / 2 + 4:.1f}" '
                     f'fill="none" stroke="#a693cc" stroke-width="1.4" stroke-dasharray="5 4" '
                     f'marker-start="url(#km-ar2)" marker-end="url(#km-ar2)"/>')

    # ---- 注解 ----
    if note:
        P.append(f'<text class="km-note" x="{cx:.1f}" y="{H - 10:.0f}">{esc(note)}</text>')

    P.append("</svg>")
    svg = "\n".join(P)
    assert "\n\n" not in svg, "SVG 不能含空行"
    return svg


def _box(cx, cy, w, h, label, col, bold=False):
    fs = fit_font(label, w, 13.5 if not bold else 15.0)
    x, y = cx - w / 2.0, cy - h / 2.0
    weight = "700" if bold else "600"
    rect = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="9" '
            f'fill="{col["fill"]}" stroke="{col["stroke"]}" stroke-width="1.4"/>')
    text = (f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="{fs:.1f}" font-weight="{weight}" '
            f'fill="{col["text"]}" text-anchor="middle" dominant-baseline="central">'
            f'{esc(label)}</text>')
    return rect + "\n" + text


if __name__ == "__main__":
    demo = {
        "concept": "一致连续",
        "course": "数学分析 · 函数连续性",
        "down": ["函数", "极限", "连续", "区间"],
        "up": ["闭区间上连续函数性质", "一致收敛", "可积性"],
        "lateral": ["连续"],
        "note": "从「局部」走向「整体」的第一个范例",
    }
    svg = render_svg(demo)
    import os
    import tempfile
    out = os.path.join(tempfile.gettempdir(), "km_demo.svg")
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"OK -> {out}  ({len(svg)} chars, height lines: {svg.count(chr(10))})")
    assert "\n\n" not in svg, "SVG 不能含空行（会中断 pandoc 原始 HTML 块）"
    print("no blank lines: OK")
