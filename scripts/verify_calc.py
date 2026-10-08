#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_calc.py —— calc / sim 块的双语言实跑与逐字节对账

用法
    python3 scripts/verify_calc.py <card.md>            # 校验 + 程序化填充占位符
    python3 scripts/verify_calc.py <card.md> --dry-run  # 只跑双语言并报 diff，不写回
    python3 scripts/verify_calc.py <card.md> --check    # 只校验（占位符已填过）
    python3 scripts/verify_calc.py <card.md> --replay   # 回放验证（见下）

关于 --replay
    --dry-run 只证明「Python 与 R 互相一致」，**从不核对卡里已写入的「预期输出」
    是否还与今天的实跑一致** —— 那段注释可能早就过期了却没人发现。
    --replay 补上这一层：把两段已填的预期输出**打回占位符**，用实跑结果重建，
    再与原卡**逐字节**对账。逐字节（不是「行数相同」）才能抓住空格数、
    字段宽度、小数位数的漂移。只需要 Python 侧，故 R 可选。

它替你做掉四件容易出错的事：
  1. 从 ```calc 块里切出 Python 段与 R 段，各自实跑；
  2. **逐字节**比对两侧输出，并打印「比的是哪两个文件」；
  3. 若卡里有 <<<EXPECTED>>> / <<<EXPECTED2>>> 占位符，**程序化**把实跑输出填进去
     （绝不手抄 —— 手抄格式串的空格数必错，而错会引发「怀疑 diff 脚本」的连锁反应）；
  4. 写回前断言：必需章节齐全、围栏成对、占位符已全部替换、〔教材口径〕≤ 6、无 CRLF。

陷阱与背景见 references/pitfalls.md。
"""

import argparse
import glob
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

PY_MARK, R_MARK = "# PYTHON", "# R"
EXP_MARK = "# 预期输出:"
PH1, PH2 = "<<<EXPECTED>>>", "<<<EXPECTED2>>>"

REQUIRED = [
    "## F6 联系其它概念", "闭卷 60 秒", "## 自检", "## 常见错位清单",
    "## 学完自测", "两头往中间", "核对提示", "```concept-map",
    "```interactive", "```geogebra", "```calc",
    "### 附：拿到题目怎么开局 ——「两头往中间」四步",
]
MAX_KOUJING = 6

DIFF_SHOWN = 5


# ---------------------------------------------------------------- 工具

def find_rscript(override=None):
    """R 是可选依赖：找不到就跳过 R 侧，绝不让整条流水线挂掉。

    本机 R 常装在非标准位置而**不在 PATH** 上，所以额外接受 --rscript / $RSCRIPT。
    """
    for cand in (override, os.environ.get("RSCRIPT")):
        if cand and pathlib.Path(cand).exists():
            return cand
    w = shutil.which("Rscript")
    if w:
        return w
    pats = [
        "C:/Program Files/R/R-*/bin/Rscript.exe",
        "C:/Program Files/R/R-*/bin/Rscript",
        "/usr/local/bin/Rscript", "/opt/homebrew/bin/Rscript",
    ]
    for p in pats:
        hits = sorted(glob.glob(p))
        if hits:
            return hits[-1]
    return None


def run(code, tag, rscript):
    suffix = ".py" if tag == "PY" else ".R"
    path = pathlib.Path(tempfile.gettempdir()) / ("_verify_calc_%s%s" % (tag, suffix))
    path.write_text(code + "\n", encoding="utf-8", newline="\n")
    cmd = [sys.executable, str(path)] if tag == "PY" else [rscript, str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        raise SystemExit("[%s] 超时（900s）" % tag)
    err = (r.stderr or "").strip()
    if r.returncode != 0 and err:
        sys.stderr.write("[%s] 运行失败：\n%s\n" % (tag, err[:800]))
    out = [l.rstrip() for l in (r.stdout or "").split("\n") if l.strip()]
    return out


def slice_block(lines):
    """切出 Python 段与 R 段。

    段边界用「# 预期输出:」标记定位，**不要**用 <<<EXPECTED>>> 占位符定位：
    占位符在标记的**下一行**，按占位符切会把那行标记本身吞进 R 段
    （R 里它是注释，于是照样跑通 —— 这种 bug 能藏很久）。
    两种卡态（已填 / 未填）都能正确切分。
    """
    try:
        i0 = lines.index("```calc")
    except ValueError:
        raise SystemExit("没找到 ```calc 块")
    j1 = next((i for i in range(i0 + 1, len(lines)) if lines[i] == "```"), None)
    if j1 is None:
        raise SystemExit("```calc 块没有闭合围栏")
    c = lines[i0 + 1:j1]
    idx = lambda m: next((k for k, l in enumerate(c) if l.strip() == m), None)
    pyi, rei = idx(PY_MARK), idx(R_MARK)
    if pyi is None or rei is None:
        raise SystemExit("calc 块里找不到 `%s` / `%s` 划段标记" % (PY_MARK, R_MARK))
    exps = [k for k, l in enumerate(c) if l.strip() == EXP_MARK]
    if len(exps) != 2:
        raise SystemExit("calc 块里 `%s` 标记数 %d，应为 2" % (EXP_MARK, len(exps)))
    p1, p2 = exps
    if not (pyi < p1 <= rei < p2):
        raise SystemExit("calc 块结构异常：期望 PYTHON … %s … R … %s 的顺序" % (EXP_MARK, EXP_MARK))
    py = [l for l in c[pyi + 1:p1] if l.strip()]
    rr = [l for l in c[rei + 1:p2] if l.strip()]
    has1, has2 = PH1 in c, PH2 in c
    return py, rr, c, has1, has2


def diff_lines(a, b):
    bad = []
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<缺失>"
        y = b[i] if i < len(b) else "<缺失>"
        if x != y:
            bad.append((i + 1, x, y))
    return bad


def blank_expected(lines):
    """把两段已填的「预期输出」打回 <<<EXPECTED>>> / <<<EXPECTED2>>>。

    段的范围 = 紧随 `# 预期输出:` 之后、**连续**的 `# ` 开头的行。
    终止条件必须显式排除划段标记 —— `# R` 与 `# PYTHON` 本身也以 `# ` 开头，
    漏掉这一条会把整个 R 段一起吞进占位符（表现为「R 实跑 → 0 行」而不报错）。
    """
    out, i, seen = [], 0, 0
    while i < len(lines):
        l = lines[i]
        out.append(l)
        if l.strip() != EXP_MARK:
            i += 1
            continue
        seen += 1
        i += 1
        while i < len(lines):
            s = lines[i]
            if s.strip() in (PY_MARK, R_MARK, EXP_MARK) or not s.startswith("# "):
                break
            i += 1
        out.append(PH1 if seen == 1 else PH2)
    return out, seen


# ---------------------------------------------------------------- 护栏

def guard(new_lines):
    miss = [k for k in REQUIRED if not any(k in l for l in new_lines)]
    assert not miss, "缺失必需章节：%s" % miss
    a = new_lines.index("```calc")
    b = next(i for i in range(a + 1, len(new_lines)) if new_lines[i] == "```")
    assert sum(1 for l in new_lines[a:b] if l.strip() == EXP_MARK) == 2, \
        "calc 块里的「%s」标记数应为 2" % EXP_MARK
    fence = sum(1 for l in new_lines if l.strip() == "```")
    assert fence % 2 == 0, "围栏数不成对：%d" % fence
    assert PH1 not in new_lines and PH2 not in new_lines, "仍有未替换的占位符"
    koujing = sum(1 for l in new_lines if "〔教材口径〕" in l)
    assert koujing <= MAX_KOUJING, "〔教材口径〕%d 条，超过 %d" % (koujing, MAX_KOUJING)
    return len(miss), fence, koujing


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="calc/sim 块双语言实跑与逐字节对账")
    ap.add_argument("card", help="概念卡 .md 路径")
    ap.add_argument("--dry-run", action="store_true", help="只跑对账，不写回")
    ap.add_argument("--check", action="store_true", help="只校验（不填占位符）")
    ap.add_argument("--replay", action="store_true",
                    help="回放验证：把已填的预期输出打回占位符、用实跑重建、与原卡逐字节对账")
    ap.add_argument("--rscript", help="Rscript 可执行文件路径（本机 R 常不在 PATH 上）")
    a = ap.parse_args()

    f = pathlib.Path(a.card)
    if not f.exists():
        raise SystemExit("找不到卡片：%s" % f)
    text = f.read_text(encoding="utf-8")
    lines = text.split("\n")
    py, rr, _c, has1, has2 = slice_block(lines)

    print("卡片：%s" % f.name)
    print("  Python 段 %d 行 ； R 段 %d 行" % (len(py), len(rr)))

    rscript = find_rscript(a.rscript)
    if rscript is None and not a.check:
        print("  ⚠ 没找到 Rscript —— 只跑 Python 侧，跳过逐字节对账")
        print("    （SKILL.md 已声明 R 为可选依赖；此时预期输出请改为定性描述）")
        print("    （若本机装了 R，用 --rscript <路径> 或设 $RSCRIPT 重新跑）")
    out_py = run("\n".join(py), "PY", rscript)
    print("  Python 实跑 → %d 行" % len(out_py))

    ok = True
    out_r = []
    if rscript:
        print("  Rscript：%s" % rscript)
        out_r = run("\n".join(rr), "R", rscript)
        print("  R 实跑 → %d 行" % len(out_r))
        bad = diff_lines(out_py, out_r)
        print("  对账文件：PY=_verify_calc_PY.py 的 stdout ／ R=_verify_calc_R.R 的 stdout")
        if bad:
            ok = False
            print("  ✗ 逐字节不一致：%d 行不同（共 %d/%d 行）" % (len(bad), len(out_py), len(out_r)))
            for i, x, y in bad[:DIFF_SHOWN]:
                print("      L%-4d PY: %s\n           R : %s" % (i, x, y))
            print("      → 见 references/pitfalls.md 第一节（R 的 1:0 / 整除 / sprintf 自动打印 / 宽度补位）")
        else:
            print("  ✓ 逐字节一致（%d/%d 行）" % (len(out_py), len(out_r)))

    if a.replay:
        blanked, seen = blank_expected(lines)
        if seen != 2:
            raise SystemExit("--replay 要求恰好 2 处 `%s`，实为 %d" % (EXP_MARK, seen))
        block = "\n".join("# " + l for l in out_py)
        rebuilt = "\n".join(blanked).replace(PH1, block).replace(PH2, block)
        if "\r\n" in rebuilt:
            rebuilt = rebuilt.replace("\r\n", "\n")
        if rebuilt == text:
            print("  ✓ 回放一致：重建结果与原卡**逐字节相同**（%d 字符）" % len(text))
            return 0 if ok else 1
        print("  ✗ 回放不一致：卡里已写入的『预期输出』与今天的实跑对不上")
        d = diff_lines(text.split("\n"), rebuilt.split("\n"))
        print("    %d 行不同（共 %d 行）" % (len(d), len(text.split("\n"))))
        for i, x, y in d[:DIFF_SHOWN]:
            print("      L%-5d 卡内: %s" % (i, x[:100]))
            print("             实跑: %s" % y[:100])
        print("      → 不带 --replay 重跑一次，即可用实跑结果覆盖过期的那段")
        return 1

    if a.dry_run:
        print("  --dry-run：不写回")
        print("\n".join(out_py))
        return 0 if ok else 1

    if not (has1 or has2):
        print("  （卡里没有 <<<EXPECTED>>> 占位符，跳过填充）")
        n = 0
        fence = sum(1 for l in lines if l.strip() == "```")
        koujing = sum(1 for l in lines if "〔教材口径〕" in l)
        print("  ✓ 护栏通过：必需章节齐全 ／ %d 个围栏成对 ／ 〔教材口径〕%d 条" % (fence, koujing))
        return 0 if ok else 1

    if a.check:
        raise SystemExit("--check 模式下不允许填充占位符；去掉 --check")

    block = "\n".join("# " + l for l in out_py)
    new = text.replace(PH1, block).replace(PH2, block)
    nl = new.split("\n")
    _m, fence, koujing = guard(nl)
    if "\r\n" in new:
        new = new.replace("\r\n", "\n")
    f.write_text(new, encoding="utf-8", newline="\n")
    print("  ✓ 已填入 %d 行 × 2 ；%d 个必需标记齐全 ；%d 个围栏成对 ；〔教材口径〕%d 条"
          % (len(out_py), len(REQUIRED), fence, koujing))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())