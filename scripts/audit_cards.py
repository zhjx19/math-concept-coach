#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_cards.py —— 概念卡「跑偏」体检（比 lint_skill.py 更宽的一层）。

lint_skill.py 查「用了超纲工具」；本脚本查六类它查不出的跑偏：

  A 结构完整性   F1-F6 / F0 块 / 邀请语 / 闭卷 / 自检 / 错位清单 / 自测 / 附四步 / 核对提示
  B 难度配比     各面字数占比（F3 是否压倒 F2）
  C 自造抽象框架 用户点过名的毛病（累加器/标准化器/首达时间…）
  D 专有名词     数学家人名拼写（脚本能查的一类硬错）
  E 硬约束       〔教材口径〕≤6 / CRLF / 表格内裸竖线
  F 入口句       一句话钩子在不在、形态如何

**三个已知陷阱（都在本脚本里修掉了，勿重蹈）**
  陷阱1 「⚠️ 核对提示」的 emoji 带变体选择符 U+FE0F；只写 `^##\\s*⚠\\s*核对提示`
         会漏掉一半卡片，误报「缺核对提示」。
  陷阱2 数「裸竖线」时若统计整行的 `|`，会把 Markdown 表格的列分隔符全数进去，
         22 张卡全假阳性。正确口径：**只查表格单元格里 `$...$` 内的字面 `|`**。
  陷阱3 F5/F6 里常有 calc 与图谱，长度天然偏大；F3 占比要用**六面总长**做分母，
         不能拿 F1..F6 之外的正文去比。

用法：
    python audit_cards.py 概念卡/
    python audit_cards.py 概念卡/ -o 报告.txt
退出码：有硬约束问题返回 1，否则 0。
"""

import argparse
import pathlib
import re
import sys
from collections import Counter

# ── 结构要件 ──
REQUIRED = [
    ("F1", r"^##\s*F1\b"),
    ("F2", r"^##\s*F2\b"),
    ("F3", r"^##\s*F3\b"),
    ("F4", r"^##\s*F4\b"),
    ("F5", r"^##\s*F5\b"),
    ("F6", r"^##\s*F6\b"),
    ("闭卷60秒", r"闭卷\s*60\s*秒"),
    ("自检", r"^##\s*自检"),
    ("常见错位清单", r"常见错位清单"),
    ("学完自测", r"学完自测"),
    ("附四步", r"两头往中间"),
    # 陷阱1：⚠ 与 ⚠️ 都认
    ("核对提示", r"^##\s*⚠\ufe0f?\s*核对提示"),
]

FABRICATED = r"累加器|标准化器|首达时间|三角色|流水线式|管道模型"

# 专有名词：(标准拼写, 变体正则, 中文名)  —— 只报「非标准写法」
NAMES = [
    ("Vitali",     r"Vitalic|Vitalli|Vitalii|Vitaly\b",       "维塔利"),
    ("Borel",      r"Boreal\b|Borlet",                        "博雷尔"),
    ("Lebesgue",   r"Lebesgne|Lebesue|Lebesguey",             "勒贝格"),
    ("Kolmogorov", r"Kolmogaroff|Kmogorov",                    "柯尔莫哥洛夫"),
    ("Cholesky",   r"Choleaky|Cholesk(?!y)",                  "乔列斯基"),
    ("Gram",       r"Grams\b|格拉姆|格兰姆",                    "格拉姆"),
    ("Hadamard",   r"Hadamart|Hadamard",                      "哈达玛"),
    ("Cauchy",     r"Causshy|Cauchyy",                        "柯西"),
    ("Simpson",    r"Simpon|Sympson",                         "辛普森"),
    ("Chebyshev",  r"Chebychev|Chebyshef",                    "切比雪夫"),
    ("Markov",     r"Markovv|Markoff",                        "马尔可夫"),
    ("Bernoulli",  r"Bernouilli",                             "伯努利"),
    ("Riemann",    r"Riman\b|Riemman",                        "黎曼"),
    ("Jordan",     r"Jorden\b",                               "若尔当"),
]

# 已知别名，视为正确
OK_ALIAS = {"Tchebycheff", "Cholesky"}


# 陷阱2（已在第 4 轮被数据否掉）：**不要**在源文本上用正则数竖线。
#   md2card 的转换器对 $...$ 是原子的，`\bigr|` 与 GFM 的 `\|` 都能正确处理；
#   「表格行 + $...$ 内有 |」并不等于单元格被撑破。
#   唯一可靠的判据是渲染产物：逐表比对表头列数与每行 <td> 数。见 table_report()。

_TBL = re.compile(r"<table[^>]*>(.*?)</table>", flags=re.S)
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", flags=re.S)
_CELL = re.compile(r"<t[dh][ >]")
_HEAD = re.compile(r"<th[ >]")


def table_report(html_path):
    """以渲染后的 HTML 为地面真值，返回 (不一致的表数, 公式回落数, 表总数)。"""
    if not html_path.exists():
        return (None, None, 0)
    h = html_path.read_text(encoding="utf-8")
    from collections import Counter as _C
    bad = tot = 0
    for tm in _TBL.finditer(h):
        rows = _ROW.findall(tm.group(1))
        if not rows:
            continue
        tot += 1
        widths = {}
        for r in rows:
            k = len(_CELL.findall(r))
            widths[k] = widths.get(k, 0) + 1
        common, cnt = max(widths.items(), key=lambda kv: kv[1])
        if cnt > 1 and len(widths) > 1:
            bad += 1
    return (bad, h.count('class="math-src"'), tot)


def faces_of(lines):
    faces, cur = {}, None
    for i, l in enumerate(lines):
        m = re.match(r"^##\s*(F\d)\b", l)
        if m:
            cur = m.group(1)
            faces[cur] = [i, i]
        elif cur:
            faces[cur][1] = i
    return {k: v[1] - v[0] for k, v in faces.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    root = pathlib.Path(a.target)
    files = sorted(root.glob("*.md")) if root.is_dir() else [root]

    rows = []
    for f in files:
        t = f.read_text(encoding="utf-8")
        L = t.split("\n")
        fl = faces_of(L)
        tot = sum(fl.values()) or 1
        rows.append(dict(
            name=f.stem.replace("-概念卡", ""),
            miss=[tag for tag, pat in REQUIRED if not re.search(pat, t, flags=re.M)],
            has_f0=("假设基底" in t) or ("学完你应该能" in t),
            has_ask="你觉得自己会吗" in t,
            hook=(re.search(r"^>\s*💡\s*\*\*一句话钩子\*\*：(.+)$", t, flags=re.M) or [None, ""])[1]
                if re.search(r"^>\s*💡\s*\*\*一句话钩子\*\*：(.+)$", t, flags=re.M) else "",
            fab=sorted(set(re.findall(FABRICATED, t))),
            names=[(canon, cn, i + 1, m.group(0))
                   for canon, pat, cn in NAMES
                   for i, l in enumerate(L)
                   for m in re.finditer(pat, l)
                   if m.group(0) != canon and m.group(0) not in OK_ALIAS and m.group(0) != cn],
            face=fl, f3=fl.get("F3", 0) / tot,
            note=len(re.findall(r"〔教材口径〕", t)),
            tbl_bad=table_report(f.with_suffix(".html"))[0],
            math_fb=table_report(f.with_suffix(".html"))[1],
            crlf="\r\n" in t,
            lines=len(L),
        ))

    O = []
    W = O.append
    W("=" * 92)
    W("概念卡「跑偏」体检：%d 张" % len(rows))
    W("=" * 92)

    W("\n【A】结构完整性")
    W("-" * 92)
    bad = [r for r in rows if r["miss"] or not r["has_f0"] or not r["has_ask"]]
    if not bad:
        W("  ✓ 全部齐备：F1–F6 + F0 块 + 邀请语 + 闭卷 + 自检 + 错位清单 + 自测 + 附四步 + 核对提示")
    for r in bad:
        why = []
        if r["miss"]:
            why.append("缺 " + "、".join(r["miss"]))
        if not r["has_f0"]:
            why.append("缺 F0 块")
        if not r["has_ask"]:
            why.append("缺邀请语")
        W("  ✗ %-26s %s" % (r["name"][:26], "；".join(why)))

    W("\n【B】难度配比（F3 占六面总长；分母只算 F1–F6，见文件头陷阱3）")
    W("-" * 92)
    W("  %-26s %5s %5s %5s %5s %5s %5s  %6s" % ("卡", "F1", "F2", "F3", "F4", "F5", "F6", "F3占比"))
    for r in sorted(rows, key=lambda x: -x["f3"]):
        f = r["face"]
        W("  %-26s %5d %5d %5d %5d %5d %5d  %5.1f%%%s"
          % (r["name"][:26], f.get("F1", 0), f.get("F2", 0), f.get("F3", 0),
             f.get("F4", 0), f.get("F5", 0), f.get("F6", 0), r["f3"] * 100,
             "  ★ 压过 F2 两倍+" if r["f3"] > 0.40 else ""))
    over = [r["name"] for r in rows if r["f3"] > 0.40]
    W("  → F3 占比 >40%% 的卡：%d 张%s" % (len(over), ("：" + "、".join(over)) if over else ""))

    W("\n【C】自造抽象框架")
    W("-" * 92)
    fab = [r for r in rows if r["fab"]]
    W("  ✓ 无" if not fab else "")
    for r in fab:
        W("  ✗ %-26s %s" % (r["name"][:26], "、".join(r["fab"])))

    W("\n【D】专有名词拼写")
    W("-" * 92)
    nm = [r for r in rows if r["names"]]
    W("  ✓ 全部正确" if not nm else "")
    for r in nm:
        W("  ✗ %s" % r["name"])
        for canon, cn, ln, s in r["names"][:8]:
            W("      L%-4d 「%s」→「%s」（%s）" % (ln, s, canon, cn))

    W("\n【E】硬约束：〔教材口径〕≤6 · 无 CRLF · **表格列数一致 + 公式零回落**")
    W("     （表格与公式两项以渲染后的 HTML 为准，见文件头陷阱2）")
    W("-" * 92)
    W("  %-26s %8s %8s %8s %7s  %s"
      % ("卡", "教材口径", "表格异常", "公式回落", "CRLF", "判定"))
    hard = []
    for r in sorted(rows, key=lambda x: x["name"]):
        pr = []
        if r["note"] > 6:
            pr.append("教材口径 %d>6" % r["note"])
        if r["tbl_bad"]:
            pr.append("表格列数不一致 ×%d" % r["tbl_bad"])
        if r["math_fb"]:
            pr.append("公式回落 %d" % r["math_fb"])
        if r["crlf"]:
            pr.append("CRLF")
        if pr:
            hard.append((r["name"], pr))
        W("  %-26s %8d %8s %8s %7s  %s"
          % (r["name"][:26], r["note"],
             r["tbl_bad"] if r["tbl_bad"] is not None else "无HTML",
             r["math_fb"] if r["math_fb"] is not None else "-",
             "YES" if r["crlf"] else "-",
             ("★ " + "、".join(pr)) if pr else "ok"))
    W("  → 有硬约束问题的卡：%d 张" % len(hard))

    W("\n【F】入口句「一句话钩子」")
    W("-" * 92)
    nohook = [r["name"] for r in rows if not r["hook"]]
    W("  → 缺失的卡：%d 张%s" % (len(nohook), ("：" + "、".join(nohook)) if nohook else ""))
    longest = sorted(rows, key=lambda x: -len(x["hook"]))[:3]
    W("  → 最长的三个（**仅供参考**：长钩子常是有意的递进结构，不是缺陷）：")
    for r in longest:
        W("      %-26s %3d 字  %s…" % (r["name"][:26], len(r["hook"]), r["hook"][:44]))

    W("\n" + "=" * 92)
    W("汇总：缺件 %d ｜ F3 过重 %d ｜ 自造框架 %d ｜ 专有名词错 %d 处 ｜ 硬约束问题 %d ｜ 缺钩子 %d"
      % (len(bad), len(over), len(fab),
         sum(len(r["names"]) for r in rows), len(hard), len(nohook)))

    txt = "\n".join(O)
    if a.out:
        pathlib.Path(a.out).write_text(txt, encoding="utf-8", newline="\n")
        print("（报告见 %s）" % a.out)
    else:
        print(txt)
    return 1 if (bad or hard or fab or nm) else 0


if __name__ == "__main__":
    sys.exit(main())