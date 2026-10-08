#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_refs.py —— 全目录跨卡引用审计

一张卡改名 / 拆分 / 归档之后，其他卡里指向它的引用会**静默失效**：
那段文本仍在、只是名字不对，所以 check_card.py 与 audit_cards.py **都查不出来**。
本脚本把这类错误变成可执行断言。

用法
    python3 scripts/audit_refs.py <卡片目录> [-o 报告.txt]

三层判据
    L1 卡存在     —— 引用的卡在目录里
    L2 位置存在   —— 边界例 N / F1..F6 在那张卡里真的存在
    L3 简称归一   —— 《泰勒》这类简称、以及《求导法则》这类「定理名套了书名号」会被点名

白名单（合法、故意不报错）
    · 教材章节名（教材本来就叫「函数极限与连续」这类名字）
    · 外部文献名（如《分析论》）
    · 「本卡由原《X》拆出」这类拆分说明句
    · 本卡自引
"""

import argparse
import pathlib
import re
import sys

# 卡名简称 → 规范卡名（报告时提示，不自动改）
ALIAS = {"泰勒": "泰勒展开", "洛必达": "洛必达法则", "导数": "导数", "微分": "微分"}
# 不是卡名的书名号内容 —— 分两类，处置相反
#   NOT_CARD_FIX  : 定理名/法则名 —— **不该**套书名号（读���会去找一张不存在的卡）
#   NOT_CARD_KEEP : 外部书名/篇名 —— **该**套书名号，合法，不要报
NOT_CARD_FIX = ("拉格朗日", "求导法则", "柯西", "罗尔", "泰勒公式")
NOT_CARD_KEEP = ("【", "分析论", "原理")

POS = re.compile(r"(F[1-6]|边界例\s*\d+|闭卷|自检|错位清单|自测|附四步|核对提示|F3\s*[高中低]档)")
BRACKET = re.compile(r"《([^》]+)》")


def sections(path):
    out = {"边界例": set(), "F": set()}
    for l in path.read_text(encoding="utf-8").split("\n"):
        m = re.match(r"^## (F[1-6])", l)
        if m:
            out["F"].add(m.group(1))
        m = re.search(r"边界例\s*(\d+)", l)
        if m:
            out["边界例"].add(int(m.group(1)))
    return out


def main():
    ap = argparse.ArgumentParser(description="跨卡引用审计（L1 卡存在 / L2 位置存在 / L3 简称与定理名）")
    ap.add_argument("cards", help="概念卡目录")
    ap.add_argument("-o", "--out", help="报告输出路径")
    a = ap.parse_args()

    C = pathlib.Path(a.cards)
    files = sorted(C.glob("*.md"))
    if not files:
        raise SystemExit("目录里没有 .md：%s" % C)
    names = {p.stem.replace("-概念卡", "") for p in files}
    SEC = {p.stem.replace("-概念卡", ""): sections(p) for p in files}

    L1, L2, L3 = [], [], []
    total = 0
    for p in files:
        src = p.stem.replace("-概念卡", "")
        for i, l in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            if "《" not in l:
                continue
            for m in BRACKET.finditer(l):
                tgt = m.group(1)
                if tgt == src or "拆出" in l or "拆自" in l:
                    continue
                total += 1
                tail = l[m.end():m.end() + 40]
                pm = POS.search(tail)
                pos = pm.group(1).replace(" ", "") if pm else ""

                if tgt not in SEC:
                    if any(k in tgt for k in NOT_CARD_KEEP):
                        pass                                    # 外部书名/篇名，合法
                    elif any(k in tgt for k in NOT_CARD_FIX):
                        L3.append((src, i, tgt, "定理名/法则名，不该套书名号（读者会去找一张不存在的卡）"))
                    elif tgt in ALIAS:
                        L1.append((src, i, tgt, "简称 → 应写《%s》" % ALIAS[tgt]))
                    else:
                        L1.append((src, i, tgt, "**引用了不存在的卡**"))
                    continue

                if pos:
                    mm = re.match(r"边界例(\d+)", pos)
                    if mm and int(mm.group(1)) not in SEC[tgt]["边界例"]:
                        L2.append((src, i, tgt, "边界例 %s 在《%s》里不存在" % (mm.group(1), tgt)))
                    elif re.match(r"F[1-6]$", pos) and pos not in SEC[tgt]["F"]:
                        L2.append((src, i, tgt, "%s 在《%s》里不存在" % (pos, tgt)))

    o = ["=" * 78, "跨卡引用审计：%s" % C, "=" * 78,
         "卡片 %d 张 ；跨卡引用 %d 条" % (len(files), total), ""]
    for title, rows, hint in (
        ("L1 卡名对不上", L1, "改成规范卡名；若是定理名则去掉书名号"),
        ("L2 位置对不上", L2, "改小节号，或改引用的那一节"),
        ("L3 定理名套了书名号", L3, "去掉书名号（外部书名/篇名不在此列）"),
    ):
        o.append("── %s：%d 条 ──" % (title, len(rows)))
        if not rows:
            o.append("  ✓ 无")
        for src, i, tgt, why in rows:
            o.append("  %-16s L%-5d → 《%s》   %s" % (src, i, tgt, why))
        o.append("")
    bad = len(L1) + len(L2) + len(L3)
    o.append("结论：%s（L1+L2+L3 = %d）"
             % ("全部通过" if bad == 0 else "有问题，需修", bad))

    text = "\n".join(o)
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())