#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_card.py — 概念卡质量检查。

四类检查：
  1. **格式检查**：防「表格被拆散」「公式没闭合」「偷偷依赖 CDN」；
  2. **来源标注一致性**（对 .md）：卡片里出现〔待核〕就必须有「核对提示」块——
     存疑结论不得静默写进卡片（规范见 references/source-integrity.md）；
  3. **代码块检查**（对 .md）：` ```sim ` 块必须 Python / R 两段齐全、随机模拟固定种子、
     抽样向量化、不依赖绘图窗口、每段有「预期输出」注释；` ```calc `（概念计算器）同样两段齐全、
     有预期输出，但要求**确定性**（要用随机数的现象归 sim）——结果不可复现 = 没有证据
     （规范见 references/widget-spec.md 第九节）；
  4. **举证清单**（对 .md）：把所有需要人工验算的「具体举证」抽出来列成清单——
     因为格式检查**查不出数学笔误**（如把 (-1)^n 的奇/偶项说反）。
     列出 ≠ 通过：作者必须逐条重算后才可交付。

用法：
    python check_card.py 概念卡.md
    python check_card.py 概念卡.html
    python check_card.py 概念卡.md --run   # 本机有 Python/R 就实跑 sim / calc 块（会执行卡内代码）

退出码：0 = 格式通过；1 = 有格式错误需修复。 --run 模式下 sim 块实跑失败也算错误。
"""

import re
import sys
from pathlib import Path

# ---------------- 控制台编码（跨平台） ----------------
# Windows 下标准输出被管道/重定向捕获时，Python 默认用本地编码（简体中文为 GBK）。
# 此时打印卡片内容里的 emoji（🎯 / 💡）或本脚本的 ⚠ / ✓ / ✗ 会抛 UnicodeEncodeError——
# 而 Agent 正是通过管道读输出的，不修则质检在中文 Windows 上直接崩、举证清单打印一半就断。
def _configure_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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


# ---------------- sim 模拟代码检查（预期结果必须可复现） ----------------
# 规范见 references/widget-spec.md 第十节。
# 设计意图：模拟代码的证据力全在「可复现」上——不固定种子的随机实验、
# 依赖学生机器上未必有的第三方库、写不出真实输出的模拟，都不构成证据。
SIM_PY_MARKER = re.compile(r"^[ \t]*#[ \t]*PYTHON[ \t]*$", re.IGNORECASE)
SIM_R_MARKER = re.compile(r"^[ \t]*#[ \t]*R[ \t]*$", re.IGNORECASE)
SIM_EXPECTED = re.compile(r"#\s*预期输出|#\s*expected", re.IGNORECASE)
PY_RANDOM_USE = re.compile(
    r"\b(random\.|randint|uniform|choice|shuffle|gauss|normalvariate)\b"
    r"|\bnp\.random\b|\brng\.|\bnumpy\b"
)
PY_SEED = re.compile(r"\.seed\s*\(|default_rng\s*\(")
# calc 专用：只认「真的调用了随机数」，别把 `import numpy`（计算器常用 numpy.linalg）误判为随机
CALC_PY_RANDOM = re.compile(
    r"\bnp\.random\b|\bdefault_rng\s*\(|\brandom\.\w|\brandint\b|\bnormalvariate\b|\bgauss\b"
)
# 绘图库会弹窗 / 依赖显示环境，违背「只输出文本」；深度库与符号库在教学模拟里没有正当用途
PY_PLOT_OR_HEAVY = re.compile(
    r"^\s*(import|from)\s+(matplotlib|seaborn|plotly|torch|tensorflow|sympy)\b",
    re.MULTILINE,
)
R_RANDOM_USE = re.compile(r"\b(runif|rnorm|rbinom|rpois|rexp|rchisq|rt|rf|sample)\s*\(")
R_SEED = re.compile(r"set\.seed\s*\(", re.IGNORECASE)


def _split_sim_sections(body):
    """按 `# PYTHON` / `# R` 标记切分块内容，返回 (python_lines, r_lines)。"""
    sections, current = {"python": [], "r": []}, None
    for line in body:
        if SIM_PY_MARKER.match(line):
            current = "python"
            continue
        if SIM_R_MARKER.match(line):
            current = "r"
            continue
        if current is not None:
            sections[current].append(line)
    return sections["python"], sections["r"]


def extract_blocks(text, kind):
    """抽出所有 ```<kind> 块，返回 [(首行行号, [块内各行])]。"""
    blocks, lines, i, n = [], text.splitlines(), 0, len(text.splitlines())
    pat = re.compile(rf"^\s*```\s*{re.escape(kind)}\s*$", re.IGNORECASE)
    while i < n:
        if pat.match(lines[i]):
            j, body = i + 1, []
            while j < n and not re.match(r"^\s*```\s*$", lines[j]):
                body.append(lines[j])
                j += 1
            blocks.append((i + 2, body))
            i = j + 1
        else:
            i += 1
    return blocks


def extract_sim_blocks(text):
    """抽出所有 ```sim 块。"""
    return extract_blocks(text, "sim")


def extract_calc_blocks(text):
    """抽出所有 ```calc 块（概念计算器）。"""
    return extract_blocks(text, "calc")


def check_sim_blocks(text):
    errors, warnings = [], []
    blocks = extract_sim_blocks(text)
    for idx, (ln0, body) in enumerate(blocks, 1):
        where = f"sim 块 #{idx}（L{ln0} 起）"
        has_py = any(SIM_PY_MARKER.match(l) for l in body)
        has_r = any(SIM_R_MARKER.match(l) for l in body)
        if not has_py and not has_r:
            errors.append(
                f"{where}没有 `# PYTHON` / `# R` 语言段标记 → 无法生成选项卡，"
                f"写法见 references/widget-spec.md 第九节"
            )
            continue
        py, r = _split_sim_sections(body)
        # ① 两段齐全：默认选项卡是 Python，R 可切换——缺一段就不成「双语」
        if not has_py:
            errors.append(f"{where}缺 `# PYTHON` 段（Python 是默认选项卡，必须给）")
        elif not any(l.strip() and not SIM_R_MARKER.match(l) for l in py):
            errors.append(f"{where}的 `# PYTHON` 段是空的")
        if not has_r:
            errors.append(f"{where}缺 `# R` 段（两种语言都要给，供学生切换）")
        elif not any(l.strip() for l in r):
            errors.append(f"{where}的 `# R` 段是空的")
        # ② 空行会截断 pandoc 的原始 HTML 块（md2card 会自动改成 #，但源文件应干净）
        for name, sec in (("PYTHON", py), ("R", r)):
            if any(not l.strip() for l in sec):
                warnings.append(
                    f"{where}的 {name} 段有空行 → 渲染会被截断，改用 `#` 注释行分段"
                )
        # ③ 随机模拟必须固定种子，否则「预期输出」不可复现
        if py and PY_RANDOM_USE.search("\n".join(py)) and not PY_SEED.search("\n".join(py)):
            warnings.append(
                f"{where}的 PYTHON 段用了随机数但没固定种子 → "
                f"加 np.random.default_rng(seed)（或 random.seed(...)），否则预期输出不可复现"
            )
        if r and R_RANDOM_USE.search("\n".join(r)) and not R_SEED.search("\n".join(r)):
            warnings.append(
                f"{where}的 R 段用了随机数但没固定种子 → 加 set.seed(...)，否则预期输出不可复现"
            )
        # ④ 只输出文本：绘图库弹窗依赖显示环境，深度库在教学模拟里没有正当用途
        if py and PY_PLOT_OR_HEAVY.search("\n".join(py)):
            m = PY_PLOT_OR_HEAVY.search("\n".join(py))
            warnings.append(
                f"{where}的 PYTHON 段 import 了 {m.group(2)} → "
                f"模拟代码只输出文本（print），要「看图」交给卡片里的 interactive 组件"
            )
        # ⑤ 向量化：抽样与统计计算不写逐元素循环（展示用的小循环与真正的迭代递推除外）
        if py and re.search(r"for\s+\w+\s+in\s+range\s*\(\s*\d{3,}\s*\)", "\n".join(py)):
            warnings.append(
                f"{where}的 PYTHON 段在用 for 逐个抽样（range 上千次）→ "
                f"向量化：一次生成 rng.uniform / rng.binomial(...)，再整体求均值"
            )
        if r and re.search(r"for\s*\(\s*\w+\s+in\s+1\s*:\s*\d{3,}\s*\)", "\n".join(r)):
            warnings.append(
                f"{where}的 R 段在用 for 逐个抽样 → 函数式向量化："
                f"map_dbl(1:B, \\(b) ...) 或 rbinom(B, n, p) 一步到位"
            )
        # ⑥ 预期输出：模拟的价值就在「跑出来是什么」，必须有可对照的注释
        for name, sec in (("PYTHON", py), ("R", r)):
            if sec and not any(SIM_EXPECTED.search(l) for l in sec):
                warnings.append(
                    f"{where}的 {name} 段缺「# 预期输出:」注释 → "
                    f"生成卡时实跑代码，把真实输出写进注释（跑不了就定性描述，不写假数字）"
                )
    if len(blocks) > 2:
        warnings.append(
            f"本卡共 {len(blocks)} 个 sim 块（建议 ≤ 2）——模拟是调味不是主菜，"
            f"多了挤占六面拆解本身；确定性几何关系请用 interactive 组件"
        )
    return errors, warnings


def check_calc_blocks(text):
    """```calc（概念计算器）检查：两语言段齐全、有预期输出、宜确定性。

    与 sim 的分工：calc 给「函数/指令 → 确定性结果」（ε→N、秩、界、近似值），
    是**概念量化**的现成工具；随机 / 迭代现象留给 sim（那里才需要固定种子与向量化）。
    """
    errors, warnings = [], []
    for idx, (ln0, body) in enumerate(extract_calc_blocks(text), 1):
        where = f"calc 块 #{idx}（L{ln0} 起）"
        has_py = any(SIM_PY_MARKER.match(l) for l in body)
        has_r = any(SIM_R_MARKER.match(l) for l in body)
        if not has_py and not has_r:
            errors.append(
                f"{where}没有 `# PYTHON` / `# R` 语言段标记 → 无法生成选项卡，"
                f"写法见 references/widget-spec.md 第九节"
            )
            continue
        py, r = _split_sim_sections(body)
        if not has_py:
            errors.append(f"{where}缺 `# PYTHON` 段（Python 是默认选项卡，必须给）")
        elif not any(l.strip() and not SIM_R_MARKER.match(l) for l in py):
            errors.append(f"{where}的 `# PYTHON` 段是空的")
        if not has_r:
            errors.append(f"{where}缺 `# R` 段（两种语言都要给，供学生切换）")
        elif not any(l.strip() for l in r):
            errors.append(f"{where}的 `# R` 段是空的")
        for name, sec in (("PYTHON", py), ("R", r)):
            if any(not l.strip() for l in sec):
                warnings.append(
                    f"{where}的 {name} 段有空行 → 渲染会被截断，改用 `#` 注释行分段"
                )
            if sec and not any(SIM_EXPECTED.search(l) for l in sec):
                warnings.append(
                    f"{where}的 {name} 段缺「# 预期输出:」注释 → "
                    f"生成卡时实跑代码，把真实输出写进注释（跑不了就定性描述，不写假数字）"
                )
        # 计算器宜确定性：随机数会削弱「函数 → 结果」的可复现性
        if py and CALC_PY_RANDOM.search("\n".join(py)):
            warnings.append(
                f"{where}的 PYTHON 段用了随机数 → 计算器应给确定性结果；"
                f"随机 / 迭代现象请改用 sim 块（那里要固定种子）"
            )
        if r and R_RANDOM_USE.search("\n".join(r)):
            warnings.append(
                f"{where}的 R 段用了随机数 → 计算器应给确定性结果；随机 / 迭代现象请改用 sim 块"
            )
        if py and PY_PLOT_OR_HEAVY.search("\n".join(py)):
            m = PY_PLOT_OR_HEAVY.search("\n".join(py))
            warnings.append(
                f"{where}的 PYTHON 段 import 了 {m.group(2)} → 计算器只输出文本（print）"
            )
    return errors, warnings


# ---------------- sim 实跑验证（--run：本地有 Python/R 就执行并核对预期输出） ----------------
# 设计意图：把「预期输出必须实跑」从纪律升级为程序——解释器找得到就当场跑，
# 预期输出注释里的数值必须真实出现在运行结果中；找不到解释器则退回人工验证并明说。
_FLOAT_RE = re.compile(r"-?\d+\.\d+")


def _find_interpreters():
    """先读环境变量 SIM_PYTHON / SIM_RSCRIPT（与 md2card 找 pandoc 的 PANDOC 同一约定），
    再查 PATH，最后按「通用盘符 × 通用程序目录」逐盘探测（刻意不含任何作者本机私有路径）。"""
    import glob
    import os
    import shutil

    def drive_globs(*pats):
        out = []
        for drv in "CDEFG":
            for pat in pats:
                out += glob.glob(rf"{drv}:\{pat}")
        return out

    py = os.environ.get("SIM_PYTHON") or shutil.which("python3") or shutil.which("python")
    if not py or not os.path.isfile(py):
        cands = (
            drive_globs("Python*\\python.exe", "Program Files\\Python*\\python.exe")
            + glob.glob(os.path.expandvars(r"%APPDATA%\uv\python\cpython-*\python.exe"))
        )
        py = next((c for c in cands if os.path.isfile(c)), None)
    r = os.environ.get("SIM_RSCRIPT") or shutil.which("Rscript")
    if not r or not os.path.isfile(r):
        cands = drive_globs(
            "R-*\\bin\\Rscript.exe",
            "Program Files\\R\\R-*\\bin\\Rscript.exe",
            "Program Files\\R\\*\\bin\\Rscript.exe",
        )
        r = next((c for c in cands if os.path.isfile(c)), None)
    return py, r


def _expected_floats(section_lines):
    """从「# 预期输出」注释行抽数值（剥掉括注，防止「R 4.6.1 实跑」这类说明被当成待核数值）。"""
    out = []
    in_expected = False
    for line in section_lines:
        s = line.strip()
        if not s.startswith("#"):
            continue
        if re.search(r"#\s*预期输出", s, re.IGNORECASE):
            in_expected = True
        if in_expected:
            cleaned = re.sub(r"[（(][^）)]*[）)]", "", s)
            out += _FLOAT_RE.findall(cleaned)
    return out


def run_sim_blocks(text, timeout=120):
    """实跑所有 sim / calc 块。返回 (errors, report_lines)。会执行卡内代码——只在 --run 时调用。"""
    import subprocess
    import tempfile

    errors, report = [], []
    py, r = _find_interpreters()
    report.append(
        f"解释器：Python = {py or '未找到（跳过实跑，预期输出需人工验证）'} | "
        f"R = {r or '未找到（跳过实跑，预期输出需人工验证）'}"
    )
    jobs = [("sim 块", extract_sim_blocks), ("calc 块", extract_calc_blocks)]
    if not any(extractor(text) for _, extractor in jobs):
        return errors, report

    counter = 0
    with tempfile.TemporaryDirectory() as tmp:
        for kind_label, extractor in jobs:
            for idx, (ln0, body) in enumerate(extractor(text), 1):
                counter += 1
                py_lines, r_lines = _split_sim_sections(body)
                for lang, interp, lines in (("Python", py, py_lines), ("R", r, r_lines)):
                    if not interp or not any(l.strip() for l in lines):
                        continue
                    suffix = "py" if lang == "Python" else "R"
                    src = Path(tmp) / f"blk{counter}_{lang}.{suffix}"
                    src.write_text("\n".join(lines), encoding="utf-8")
                    try:
                        proc = subprocess.run(
                            [interp, str(src)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout,
                        )
                        ok = proc.returncode == 0
                    except subprocess.TimeoutExpired:
                        ok, proc = False, None
                    if not ok:
                        tail = ""
                        if proc is not None:
                            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
                            tail = tail[-1] if tail else ""
                        errors.append(
                            f"{kind_label} #{idx} 的 {lang} 段实跑失败（L{ln0} 起）"
                            + (f"：{tail[:160]}" if tail else "")
                        )
                        report.append(f"  {kind_label} #{idx} {lang}：实跑 ✗")
                        continue
                    want = _expected_floats(lines)
                    missing = [v for v in want if v not in (proc.stdout or "")]
                    if missing:
                        errors.append(
                            f"{kind_label} #{idx} 的 {lang} 段预期输出与实跑不符（L{ln0} 起）："
                            f"未出现 {', '.join(missing)}——不许编造数字，请以实跑结果为准"
                        )
                        report.append(
                            f"  {kind_label} #{idx} {lang}：可运行 ✓，"
                            f"预期数值 {len(want) - len(missing)}/{len(want)} 出现 ✗"
                        )
                    else:
                        report.append(
                            f"  {kind_label} #{idx} {lang}：可运行 ✓，"
                            f"预期数值 {len(want)}/{len(want)} 出现 ✓"
                        )
    return errors, report


def main():
    _configure_console()
    argv = [a for a in sys.argv[1:] if a != "--run"]
    run_mode = "--run" in sys.argv[1:]
    if len(argv) != 1:
        print("用法: python check_card.py <概念卡.md|概念卡.html> [--run]")
        return 1
    path = Path(argv[0])
    if not path.exists():
        print(f"[x] 找不到文件：{path}")
        return 1

    text = path.read_text(encoding="utf-8")
    is_md = path.suffix.lower() not in (".html", ".htm")
    if is_md:
        errors, warnings = check_markdown(text)
        e2, w2 = check_source_marks(text)
        errors, warnings = errors + e2, warnings + w2
        e3, w3 = check_sim_blocks(text)
        errors, warnings = errors + e3, warnings + w3
        e4, w4 = check_calc_blocks(text)
        errors, warnings = errors + e4, warnings + w4
    else:
        errors, warnings = check_html(text)

    for e in errors:
        print(f"[错误] {e}")
    for w in warnings:
        print(f"[警告] {w}")
    if is_md:
        items = collect_evidence(text)
        # sim / calc 块的「预期输出」也是举证：必须实跑验证，不能凭感觉写数
        for idx, (ln0, _body) in enumerate(extract_sim_blocks(text), 1):
            items.append((ln0, "模拟代码",
                          f"sim 块 #{idx}：Python/R 的「预期输出」必须实跑验证——"
                          f"本机跑不了就改为定性描述，绝不写编造的数字"))
        for idx, (ln0, _body) in enumerate(extract_calc_blocks(text), 1):
            items.append((ln0, "概念计算器",
                          f"calc 块 #{idx}：函数/指令算出的结果必须实跑核对——"
                          f"手算容易错，以程序输出为准写进「预期输出」"))
        report_evidence(items)
        if run_mode:
            run_errors, run_report = run_sim_blocks(text)
            print("\n—— 代码实跑验证（--run）：会执行卡内 sim / calc 代码 ——")
            for line in run_report:
                print(line)
            errors += run_errors
            for e in run_errors:
                print(f"[错误] {e}")

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
