#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2card.py — 把 Markdown 概念卡转成「单文件、离线可读、可交互」的 HTML。

三类特殊代码块会被自动渲染（不是原样显示）：

  ```interactive        → 自绘交互组件（Canvas + 滑块，可拖动）
  {"type":"plot", ...}

  ```concept-map        → 概念知识图谱（内联 SVG）
  concept: 一致连续
  down: 函数, 极限, 连续
  up:   闭区间上连续函数性质, 一致收敛

  ```geogebra           → GeoGebra 复现指令（带「复制指令」按钮）
  f(x)=sin(1/x)
  d=Slider(0.01,1,0.01)

其余内容按正常 Markdown 处理；公式用 pandoc --mathml 转 MathML（离线可渲染）。

用法：
    python md2card.py 概念卡.md
    python md2card.py 概念卡.md -o 一致连续.html --title "一致连续 · 概念卡"
"""

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
CSS_FILE = SKILL_DIR / "assets" / "concept-card.css"
JS_FILE = SKILL_DIR / "assets" / "card-widgets.js"

sys.path.insert(0, str(HERE))
try:
    import knowledge_map  # noqa: E402
except Exception:  # pragma: no cover
    knowledge_map = None
try:
    import texmath  # noqa: E402
except Exception:  # pragma: no cover
    texmath = None

def _windows_pandoc_candidates():
    """Windows 常见安装位置。

    刻意不含任何作者本机私有路径：只由「通用盘符 × 通用程序目录」组合而成，
    逐盘探测，因此 C/D/E 盘装的 RStudio、Quarto、Pandoc 都能被找到。
    """
    cands = []
    for drv in "CDEFG":
        cands += [
            rf"{drv}:\Program Files\Pandoc\pandoc.exe",
            rf"{drv}:\Program Files (x86)\Pandoc\pandoc.exe",
            rf"{drv}:\Program Files\RStudio\resources\app\bin\quarto\bin\tools\pandoc.exe",
            rf"{drv}:\Program Files\Quarto\bin\tools\pandoc.exe",
        ]
    for var in ("%LOCALAPPDATA%", "%ProgramFiles%"):
        cands.append(os.path.expandvars(rf"{var}\Pandoc\pandoc.exe"))
    cands.append(os.path.expanduser(r"~\AppData\Local\Pandoc\pandoc.exe"))
    return cands


PANDOC_CANDIDATES = _windows_pandoc_candidates() + [
    "/usr/local/bin/pandoc",
    "/opt/homebrew/bin/pandoc",
    "/usr/bin/pandoc",
]

HTML_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
__CSS__
</style>
</head>
<body>
<main class="card">
__BODY__
</main>
<script>
__JS__
</script>
</body>
</html>
"""

# ```interactive / ```concept-map / ```geogebra 代码块
BLOCK_RE = re.compile(
    r"^[ \t]*```[ \t]*(interactive|concept-map|concept_map|geogebra|ggb)[ \t]*\r?\n"
    r"(.*?)\r?\n[ \t]*```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def find_pandoc():
    env = os.environ.get("PANDOC")
    if env and Path(env).exists():
        return env
    found = shutil.which("pandoc")
    if found:
        return found
    for cand in PANDOC_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def read_text(p):
    return Path(p).read_text(encoding="utf-8")


# ---------------- 三类块的渲染 ----------------
def widget_html(body):
    """```interactive → 自绘交互组件（base64 传参，绝不被 Markdown 破坏）"""
    try:
        spec = json.loads(body.strip())
    except Exception as e:
        return f'<div class="wb-widget"><p class="wb-err">interactive 块不是合法 JSON：{html.escape(str(e))}</p></div>'
    kind = str(spec.get("type", ""))
    b64 = base64.b64encode(
        json.dumps(spec, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    return f'<div class="wb-widget" data-wb="{html.escape(kind, quote=True)}" data-spec="{b64}"></div>'


def concept_map_html(body):
    """```concept-map → 内联 SVG 知识图谱"""
    if knowledge_map is None:
        return f"<pre><code>{html.escape(body.strip())}</code></pre>"
    try:
        spec = knowledge_map.parse_spec(body)
        svg = knowledge_map.render_svg(spec)
    except Exception as e:
        return f'<p class="wb-err">concept-map 渲染失败：{html.escape(str(e))}</p>'
    # 直接输出 SVG（不加 <div>/<figure> 外壳：pandoc 会解析容器内的 Markdown，裸 SVG 才原样保留）
    return svg


def geogebra_html(body):
    """```geogebra → 指令块 + 复制按钮"""
    code = html.escape(body.strip())
    return (
        '<div class="gb-block">'
        '<div class="gb-head">'
        '<span>在 GeoGebra 里自己复现（把下面指令逐行粘贴到输入栏，回车）</span>'
        '<button type="button" class="gb-copy">复制指令</button>'
        '</div>'
        f'<pre><code>{code}</code></pre>'
        '</div>'
    )


def preprocess(md_text):
    """把三类特殊块替换为真实 HTML。"""
    stats = {"widget": 0, "map": 0, "ggb": 0, "err": 0}

    def repl(m):
        lang = m.group(1).lower()
        body = m.group(2)
        if lang == "interactive":
            stats["widget"] += 1
            return widget_html(body)
        if lang in ("concept-map", "concept_map"):
            stats["map"] += 1
            return concept_map_html(body)
        stats["ggb"] += 1
        return geogebra_html(body)

    out = BLOCK_RE.sub(repl, md_text)
    return out, stats


# ---------------- pandoc ----------------
def convert_md_to_html(pandoc, md_path):
    cmd = [
        pandoc, str(md_path),
        "-f", "markdown+pipe_tables+fenced_divs+tex_math_dollars",
        "-t", "html",
        "--mathml",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("pandoc 转换失败：\n" + (proc.stderr or "").strip())
    return proc.stdout


def first_heading(md_text):
    m = re.search(r"^\s*#\s+(.+)$", md_text, re.MULTILINE)
    return m.group(1).strip() if m else "数学概念卡"


# ---------------- 降级转换器（未安装 pandoc 时启用） ----------------
# 设计原则：任何机器上都「跑得出东西」。交互组件与知识图谱由本脚本自己渲染，
# 不依赖 pandoc，因此降级模式下依然完全可用；只有数学公式退化为 LaTeX 源码。
_PRERENDERED_ONE = ('<div class="wb-widget"', '<div class="gb-block">', '<p class="wb-err">')
_PRERENDERED_MULTI_START = ('<svg',)
_PRERENDERED_MULTI_END = ('</svg>',)

FALLBACK_NOTE = (
    '<div class="fb-note"><strong>降级模式</strong>：本机未找到 pandoc，'
    '本卡片由技能内置转换器生成。'
    '<b>交互图形、知识图谱与数学公式（MathML）均正常渲染</b>；'
    '个别超出内置转换器能力的复杂公式会以 LaTeX 源码显示。'
    '安装 pandoc 后重新运行，可支持更完整的公式语法（见 README「环境依赖」）。</div>'
)


def split_prerendered(md_text):
    """把已渲染好的 HTML 块（组件/图谱/指令块）抽出换成占位符，
    使降级转换器无需理解它们，也不会把它们当 Markdown 转义掉。"""
    blocks, out_lines, lines, i = [], [], md_text.split("\n"), 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if any(stripped.startswith(s) for s in _PRERENDERED_ONE):
            blocks.append(lines[i])
            out_lines.append(f"@@PRERENDERED{len(blocks) - 1}@@")
            i += 1
        elif any(stripped.startswith(s) for s in _PRERENDERED_MULTI_START):
            buf, j = [lines[i]], i + 1
            while j < len(lines) and not lines[j].rstrip().endswith(_PRERENDERED_MULTI_END):
                buf.append(lines[j])
                j += 1
            if j < len(lines):
                buf.append(lines[j])
            blocks.append("\n".join(buf))
            out_lines.append(f"@@PRERENDERED{len(blocks) - 1}@@")
            i = j + 1
        else:
            out_lines.append(lines[i])
            i += 1
    return "\n".join(out_lines), blocks


def restore_prerendered(html_text, blocks):
    for k, b in enumerate(blocks):
        html_text = html_text.replace(f"@@PRERENDERED{k}@@", b)
    return html_text


def _math_node(src):
    """把 $...$ / $$...$$ 渲染为 MathML。

    内置转换器（scripts/texmath.py）覆盖大学数学常用语法；
    解析不了的结构**不做猜测**，原样显示 LaTeX 源码——公式出错比公式难看严重。
    """
    disp = src.startswith("$$")
    tex = src[2:-2] if disp else src[1:-1]
    if texmath is not None:
        try:
            return texmath.tex_to_mathml(html.unescape(tex), display=disp)
        except Exception:
            pass
    return f'<code class="math-src">{src}</code>'


def _inline(t):
    """行内：公式 → MathML（失败回落源码）；反引号、`**粗**`、*斜*、[链接]。"""
    out = []
    for p in re.split(r"(\$\$?[^$]+\$\$?)", html.escape(t, quote=False)):
        if re.fullmatch(r"\$\$?[^$]+\$\$?", p):
            out.append(_math_node(p))
            continue
        p = re.sub(r"`([^`]+)`", r"<code>\1</code>", p)
        p = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", p)
        p = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', p)
        out.append(p)
    return "".join(out)


def fallback_md_to_html(md_text):
    """纯标准库 Markdown 转换器。覆盖概念卡用到的语法：
    标题 / 段落 / 表格 / 列表 / 引用 / 代码块 / 分隔线 / 行内强调与公式。"""
    text, blocks = split_prerendered(md_text)
    lines, out, para, i = text.split("\n"), [], [], 0

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            flush()
            i += 1
            continue
        if s.startswith("```"):                                    # 代码块
            flush()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)                       # 标题
        if m:
            flush()
            out.append(f"<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>")
            i += 1
            continue
        if re.fullmatch(r"@@PRERENDERED\d+@@", s):                  # 预渲染块占位符
            flush()
            out.append(s)
            i += 1
            continue
        if (re.match(r"^\|.*\|$", s) and i + 1 < len(lines)
                and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip())):   # 表格
            flush()
            head = [c.strip() for c in s.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and re.match(r"^\|.*\|$", lines[i].strip()):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                          for r in rows)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>")
            continue
        if re.match(r"^([-*_]\s*){3,}$", s):                        # 分隔线
            flush()
            out.append("<hr/>")
            i += 1
            continue
        if re.match(r"^>\s?", s):                                   # 引用
            flush()
            buf = []
            while i < len(lines) and re.match(r"^>\s?", lines[i].strip()):
                buf.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            out.append("<blockquote>" + _inline(" ".join(buf)) + "</blockquote>")
            continue
        if re.match(r"^[-*+]\s+", s):                               # 无序列表
            flush()
            items = []
            while i < len(lines) and re.match(r"^[-*+]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*+]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^\d+[.)]\s+", s):                             # 有序列表
            flush()
            items = []
            while i < len(lines) and re.match(r"^\d+[.)]\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+[.)]\s+", "", lines[i].strip()))
                i += 1
            out.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ol>")
            continue
        para.append(s)
        i += 1
    flush()
    return FALLBACK_NOTE + "\n" + restore_prerendered("\n".join(out), blocks)


# ---------------- 渐进揭示（把 F1–F6 折成可展开面板） ----------------
# 依据：卡片一次性摊开全六面 + 交互 + 图谱 + 自检，元素交互性高而无图式支撑，
# 易造成外在认知负荷（Sweller）。折叠后默认只展开 F1，学生按需展开其余各面。
# 打印时由 card-widgets.js 的 beforeprint 自动全部展开，内容一字不漏。
_FACET_H2 = re.compile(r"<h2[^>]*>(.*?)</h2>", re.DOTALL)


def _facet_num(inner_html):
    txt = re.sub(r"<[^>]+>", "", inner_html)
    m = re.match(r"\s*F\s*([0-9])", txt)
    return int(m.group(1)) if m else None


def _facet_label(inner_html):
    return re.sub(r"<[^>]+>", "", inner_html).strip()


def apply_progressive_disclosure(body_html):
    """把每个 F1–F6 面包进 <details>：默认只展开 F1，其余折叠，顶部给一键展开。

    只处理顶层 <h2>F{0..9}…</h2> 形式的标题；非「面」的小节（自检、错位清单）
    原样保留。找不到任何「面」标题时原样返回（对非概念卡文档零影响）。
    """
    heads = [(m, _facet_num(m.group(1))) for m in _FACET_H2.finditer(body_html)]
    facets = [(m, n) for (m, n) in heads if n is not None]
    if not facets:
        return body_html

    out, cursor = [], 0
    for m, num in facets:
        start = m.start()
        nxt = None
        for m2, _n2 in facets:
            if m2.start() > start:
                nxt = m2.start()
                break
        seg_end = nxt if nxt is not None else len(body_html)
        out.append(body_html[cursor:start])
        label = html.escape(_facet_label(m.group(1)))
        inner = body_html[m.end():seg_end]
        openattr = " open" if num <= 1 else ""
        out.append(
            f'<details class="facet"{openattr}>'
            f'<summary class="facet-h f{num}">{label}</summary>'
            f'<div class="facet-body">{inner}</div>'
            f"</details>"
        )
        cursor = seg_end
    out.append(body_html[cursor:])
    result = "".join(out)

    toolbar = (
        '<div class="facet-toolbar">'
        '<button type="button" class="facet-toggle" data-open="1">收起全部</button>'
        "</div>"
    )
    idx = result.find('<details class="facet"')
    if idx >= 0:
        result = result[:idx] + toolbar + result[idx:]
    return result


def main():
    ap = argparse.ArgumentParser(description="Markdown 概念卡 → 离线单文件可交互 HTML")
    ap.add_argument("input", help="输入 Markdown 文件")
    ap.add_argument("-o", "--output", help="输出 HTML 路径（默认同名 .html）")
    ap.add_argument("--title", help="HTML 标题（默认取首个一级标题）")
    ap.add_argument("--css", help="自定义 CSS（默认 assets/concept-card.css）")
    args = ap.parse_args()

    md_path = Path(args.input)
    if not md_path.exists():
        print(f"[x] 找不到输入文件：{md_path}", file=sys.stderr)
        return 1

    pandoc = find_pandoc()

    css_path = Path(args.css) if args.css else CSS_FILE
    for p in (css_path, JS_FILE):
        if not p.exists():
            print(f"[x] 缺少资源文件：{p}", file=sys.stderr)
            return 1

    md_text = read_text(md_path)
    title = args.title or first_heading(md_text)

    pre, stats = preprocess(md_text)
    if pandoc:
        tmp_md = md_path.with_suffix(".pre.md")
        tmp_md.write_text(pre, encoding="utf-8")
        try:
            body = convert_md_to_html(pandoc, tmp_md)
        except RuntimeError as e:
            print(f"[x] {e}", file=sys.stderr)
            return 1
        finally:
            try:
                tmp_md.unlink()
            except OSError:
                pass
        mode = f"pandoc: {pandoc}"
    else:
        # 降级：任何机器上都跑得出东西。组件与图谱由本脚本自行渲染，不受影响。
        body = fallback_md_to_html(pre)
        mode = ("降级模式：未找到 pandoc，已用内置转换器出卡。"
                "交互图形 / 知识图谱 / 公式(MathML) 均正常；"
                "装 pandoc 后重跑可支持更完整的公式语法（见 README「环境依赖」）")

    out_text = (
        HTML_SHELL
        .replace("__TITLE__", title.replace("<", "&lt;").replace(">", "&gt;"))
        .replace("__CSS__", read_text(css_path))
        .replace("__JS__", read_text(JS_FILE))
        .replace("__BODY__", apply_progressive_disclosure(body))
    )
    out_path = Path(args.output) if args.output else md_path.with_suffix(".html")
    out_path.write_text(out_text, encoding="utf-8")

    print(f"[OK] 概念卡已生成：{out_path}")
    print(f"     交互组件 {stats['widget']} 个 | 知识图谱 {stats['map']} 张 | "
          f"GeoGebra 指令块 {stats['ggb']} 个 | "
          f"折叠面板 {out_text.count('<details class=\"facet\"')} 个（默认展开 F1，打印自动全展开）")
    if pandoc:
        print(f"     公式(MathML) {out_text.count('<math')} 处 | "
              f"表格 {out_text.count('<table')} 个 | 单文件离线可交互")
    else:
        print(f"     公式(MathML) {out_text.count('<math')} 处"
              f"（源码回落 {out_text.count('class=\"math-src\"')} 处）| "
              f"表格 {out_text.count('<table')} 个 | 单文件离线可交互")
    print(f"     {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
