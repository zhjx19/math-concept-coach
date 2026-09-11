#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_card.py — 概念卡质量检查。

三类检查：
  1. **格式检查**：防「表格被拆散」「公式没闭合」「偷偷依赖 CDN」；
  2. **来源标注一致性**（对 .md）：卡片里出现〔待核〕就必须有「核对提示」块——
     存疑结论不得静默写进卡片（规范见 references/source-integrity.md）；
  3. **举证清单**（对 .md）：把所有需要人工验算的「具体举证」抽出来列成清单——
     因为格式检查**查不出数学笔误**（如把 (-1)^n 的奇/偶项说反）。
     列出 ≠ 通过：作者必须逐条重算后才可交付。

用法：
    python check_card.py 概念卡.md
    python check_card.py 概念卡.html

退出码：0 = 格式通过；1 = 有格式错误需修复。
"""

import re
import sys
from pathlib import Path

# 表格行里允许的「安全竖线」写法
SAFE_PIPE_MACROS = re.compile(r"\\[lLrR]?vert|\\Vert|\\lVert|\\rVert|\\mid|\\\|")


def check_markdown(text):
    errors, warnings = [], []
    in_code = False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue

        is_table_row = s.startswith("|") or " | " in line or s.endswith("|")

        # 1) 表格行内的行内公式含裸竖线 → 会破坏表格
        for m in re.finditer(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", line):
            seg = m.group(1)
            if "|" in seg and not SAFE_PIPE_MACROS.search(seg):
                if is_table_row:
                    errors.append(
                        f"L{i}: 表格单元格里的公式出现裸竖线 `{seg.strip()}`，"
                        f"会把表格拆散 → 改写为 \\lvert ... \\rvert"
                    )

        # 2) 未闭合的 $（含 $$）
        if not s.startswith("|") or True:
            stripped = re.sub(r"\\\$", "", line)
            if stripped.count("$$") % 2 == 1:
                warnings.append(f"L{i}: 疑似未闭合的 `$$` 显示公式")
            else:
                single = stripped.replace("$$", "")
                if single.count("$") % 2 == 1:
                    warnings.append(f"L{i}: 疑似未闭合的 `$` 行内公式")

    return errors, warnings


def check_html(text):
    errors, warnings = [], []
    for pat, msg in [
        (r'src\s*=\s*["\']https?://', "外部脚本/图片来源（src=http…）"),
        (r'href\s*=\s*["\']https?://[^"\']*\.(css|js)', "外部 CSS/JS 链接"),
        (r"cdn\.jsdelivr|cdnjs\.cloudflare|unpkg\.com|mathjax|katex", "疑似 CDN / 公式库依赖"),
    ]:
        if re.search(pat, text, re.I):
            warnings.append(f"{msg}：概念卡应为单文件离线，请改为内联或 MathML")

    if "<math" not in text:
        warnings.append("未检测到 MathML 公式（<math>）；若有公式，请确认用了 --mathml")
    if "__CSS__" in text or "__BODY__" in text:
        errors.append("模板占位符未替换，HTML 生成不完整")
    return errors, warnings


# ---------------- 数学举证清单（人工复核闸门） ----------------
# check_card.py 只能查「格式」，查不出数学对错——例如把 (-1)^n 的奇/偶项说反
# （"无穷多个奇数项贴近 1"；实际是偶数项）。因此这里把所有「具体举证」抽出来
# 列成清单，把"看不见的笔误风险"变成"看得见的待办项"，强制作者逐条重算。
EVIDENCE_PATTERNS = [
    (re.compile(r"奇数项|偶数项|奇项|偶项|n\s*为奇|n\s*为偶|奇数|偶数"), "奇偶性断言"),
    (re.compile(r"无穷多个|无穷多|有限多个|有限多|至多|至少|只有[^，。；]{0,8}个"), "数量断言"),
    (re.compile(r"边界例"), "边界例"),
    (re.compile(r"反例"), "反例"),
    (re.compile(r"删条件|能不能删"), "删条件实验"),
    (re.compile(r"取\s*[$\\{（(]*\s*[εεNnMmδaA]"), "具体取值"),
]


def collect_evidence(text):
    """抽取需要人工验算的「举证」行；返回 [(行号, 类别, 原文)]。
    跳过代码块与标题行（标题如「### 反例」本身不是一条举证）。"""
    items, in_code = [], False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code or not s or s.startswith("#"):
            continue
        for pat, tag in EVIDENCE_PATTERNS:
            if pat.search(s):
                items.append((i, tag, s))
                break
    return items


def report_evidence(items, limit=40):
    if not items:
        return
    print(f"\n—— 举证清单（{len(items)} 条）：**逐条重新验算后**才可交付 ——")
    for i, tag, s in items[:limit]:
        print(f"  L{i} [{tag}] {s[:74]}")
    if len(items) > limit:
        print(f"  … 另有 {len(items) - limit} 条未列出")
    print("  ⚠️ 本脚本查不出数学笔误：每一条都要当场重算——")
    print("     尤其「某个数列/函数的某一项到底是什么」（如 (-1)^n：奇数项 = -1，偶数项 = +1）。")
    print("     算不出来的举证，删掉或改成「请你试着构造一个反例」。")



# ---------------- 来源标注一致性（存疑不得静默写进卡片） ----------------
# 规范见 references/source-integrity.md。
# 设计意图：把「有存疑就必须给出核对提示」这条**纪律**变成机械闸门，
# 而不是指望每次写卡的人都记得。
PENDING_MARK = "〔待核〕"
FLAVOR_MARK = "〔教材口径〕"
VERIFY_BLOCK_MARK = "核对提示"


def check_source_marks(text):
    errors, warnings = [], []
    body = re.sub(r"```.*?```", "", text, flags=re.S)   # 示例代码块内的标记不算
    n_pending = body.count(PENDING_MARK)
    n_flavor = body.count(FLAVOR_MARK)
    n_marked = n_pending + n_flavor
    has_block = VERIFY_BLOCK_MARK in body

    # ①〔待核〕是"我不给结论"的最强信号 → 必须告诉学生去哪里对
    if n_pending and not has_block:
        errors.append(
            f"出现 {n_pending} 处 {PENDING_MARK}，但全文没有「核对提示」块 → "
            f"存疑结论不得静默写进卡片。请补一段「⚠️ 核对提示（请以你所用教材为准）」"
            f"（写法见 references/source-integrity.md 第四节）"
        )
    # ②〔教材口径〕只是"讲法不同" → 建议集中列出，但不拦交付
    elif n_flavor and not has_block:
        warnings.append(
            f"出现 {n_flavor} 处 {FLAVOR_MARK} 但没有「核对提示」块 → "
            f"建议集中列到文末，让学生一眼看到「哪里要照自己教材写」"
        )
    # ③ 反向噪声：没有标记却堆了核对提示
    if has_block and not n_marked:
        warnings.append(
            "有「核对提示」块，但全文没有任何〔待核〕/〔教材口径〕标记——"
            "确认这些提示确实必要（不是噪声）"
        )
    if n_marked > 6:
        warnings.append(
            f"存疑标记共 {n_marked} 处（{PENDING_MARK} {n_pending} + {FLAVOR_MARK} {n_flavor}），"
            f"疑似过度标注。这段是给学生看的，通篇「请核对教材」等于没讲——只在真有分歧处标。"
        )
    return errors, warnings


def main():
    if len(sys.argv) != 2:
        print("用法: python check_card.py <概念卡.md|概念卡.html>")
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"[x] 找不到文件：{path}")
        return 1

    text = path.read_text(encoding="utf-8")
    is_md = path.suffix.lower() not in (".html", ".htm")
    if is_md:
        errors, warnings = check_markdown(text)
        e2, w2 = check_source_marks(text)
        errors, warnings = errors + e2, warnings + w2
    else:
        errors, warnings = check_html(text)

    for e in errors:
        print(f"[错误] {e}")
    for w in warnings:
        print(f"[警告] {w}")
    if is_md:
        report_evidence(collect_evidence(text))

    if is_md and not errors:
        print("\n[OK] 格式检查通过。**注意：格式通过 ≠ 数学无误**——请先逐条核对上方「举证清单」。")
        return 0
    if not errors and not warnings:
        print("[OK] 检查通过，未发现问题。")
    elif not errors:
        print(f"[OK] 无错误，{len(warnings)} 条警告。")
    else:
        print(f"[x] {len(errors)} 个错误，{len(warnings)} 条警告，请修复后重试。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
