#!/usr/bin/env python3
"""扫描 examples/ 下的概念卡，生成画廊首页 examples/index.html。

设计要点
--------
- **可复现**：画廊不手写，任何人增删卡片后重跑本脚本即可重建，产物与数据同源。
- **零依赖**：只用标准库；生成的 index.html 单文件、内联 CSS、离线可用。
- **信息来自卡片本身**：标题、一句话钩子、所属课程从 `.md` 提取；
  文件大小、公式数、交互组件类型从生成的 `.html` 统计——不另外维护清单。

用法：python scripts/make_gallery.py
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent / "examples"

CARDS = [
    ("一致连续-概念卡", "数学分析", "连续"),
    ("数列极限-概念卡", "数学分析", "逼近（离散）"),
    ("矩阵的秩-概念卡", "高等代数", "变换"),
]

BADGE = {
    "plot": ("函数图像", "#2f6fb3"),
    "seq": ("数列 ε–N", "#1f8a63"),
    "riemann": ("黎曼和", "#c2582a"),
    "matrix2": ("线性变换", "#7a5ea8"),
    "vectors2": ("向量/张成", "#b23a2e"),
}

CSS = """
:root { --line:#e3e8ee; --muted:#5b6570; --accent:#2f6fb3; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 36px 20px 56px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei",
               "PingFang SC", "Noto Sans CJK SC", sans-serif;
  background: #f6f8fa; color: #1f2328; line-height: 1.7;
}
.wrap { max-width: 1040px; margin: 0 auto; }
h1 { font-size: 1.8em; margin: 0 0 6px; }
.sub { color: var(--muted); margin: 0 0 4px; }
.howto {
  margin: 20px 0 28px; padding: 14px 18px; background: #fff;
  border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 10px;
}
.howto code { background:#f2f4f7; padding:1px 6px; border-radius:4px; font-size:.92em; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 18px; }
.card {
  background: #fff; border: 1px solid var(--line); border-radius: 12px;
  padding: 18px 20px 16px; display: flex; flex-direction: column;
  box-shadow: 0 1px 3px rgba(16,24,40,.05);
}
.card:hover { box-shadow: 0 4px 14px rgba(16,24,40,.09); }
.card h2 { margin: 0 0 4px; font-size: 1.22em; }
.card h2 a { color: #1f2328; text-decoration: none; }
.card h2 a:hover { color: var(--accent); }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
.tag {
  display:inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px;
  color: #fff; margin-right: 6px;
}
.tag.course { background: #6b7684; }
.tag.act { background: #eef2f7; color: #46505c; border: 1px solid var(--line); }
.hook {
  font-size: 14px; color: #333c46; background: #fbfcfe;
  border-left: 3px solid #cfe0f2; padding: 8px 12px; border-radius: 6px; margin: 8px 0 12px;
}
.stats { margin-top: auto; font-size: 12.5px; color: var(--muted); border-top: 1px dashed var(--line); padding-top: 10px; }
.stats b { color: #333c46; font-weight: 600; }
footer { margin-top: 34px; color: var(--muted); font-size: 13px; text-align: center; }
@media (max-width: 640px) { body { padding: 20px 12px 36px; } }
"""


def read(p):
    return Path(p).read_text(encoding="utf-8")


def meta_from_md(md_path):
    """从 .md 提取一句话钩子与所属课程。"""
    hook = course = ""
    if md_path.exists():
        t = read(md_path)
        m = re.search(r"一句话钩子[」\*]*[:：]\s*(.+)$", t, re.M)
        if m:
            hook = re.sub(r"[*_`]", "", m.group(1)).strip()
        m = re.search(r"所属[:：]\s*(.+?)\s*[|｜]", t)
        if m:
            course = m.group(1).strip()
    return hook, course


def stats_from_html(html_path):
    """从生成的 .html 统计真实产物指标（跳过 <style> 段，避免把 CSS 选择器算进去）。"""
    h = read(html_path)
    body = h.split("</style>", 1)[-1]
    m = re.search(r'data-wb="(\w+)"', body)
    return {
        "kb": len(h.encode("utf-8")) / 1024,
        "widget": m.group(1) if m else "",
        "maps": body.count('class="km-svg"'),
        "ggb": body.count('class="gb-block"'),
        "maths": body.count("<math"),
    }


def main():
    if not EXAMPLES.exists():
        print(f"[x] 找不到目录：{EXAMPLES}", file=sys.stderr)
        return 1

    items, missing = [], []
    for stem, course_fb, action in CARDS:
        html, md = EXAMPLES / f"{stem}.html", EXAMPLES / f"{stem}.md"
        if not html.exists():
            missing.append(stem)
            continue
        st = stats_from_html(html)
        hook, course = meta_from_md(md)
        items.append({
            "file": html.name, "title": stem.replace("-概念卡", ""),
            "course": course or course_fb, "action": action,
            "hook": hook, **st,
        })

    cards = []
    for it in items:
        wname, wcolor = BADGE.get(it["widget"], ("—", "#6b7684"))
        cards.append(f"""      <div class="card">
        <h2><a href="{it['file']}">{it['title']}</a></h2>
        <div class="meta">
          <span class="tag course">{it['course']}</span>
          <span class="tag" style="background:{wcolor}">{wname}</span>
          <span class="tag act">认知动作：{it['action']}</span>
        </div>
        <div class="hook">💡 {it['hook'] or '（见卡片内一句话钩子）'}</div>
        <div class="stats">
          <b>{it['kb']:.0f} KB</b> 单文件 ·
          公式 <b>{it['maths']}</b> 处 ·
          交互组件 <b>1</b> 个 ·
          知识图谱 <b>{it['maps']}</b> 张 ·
          GeoGebra 指令 <b>{it['ggb']}</b> 块
        </div>
      </div>""")

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>概念卡画廊 · math-concept-coach</title>
<style>{CSS}</style>
</head>
<body>
  <div class="wrap">
    <h1>概念卡画廊</h1>
    <p class="sub">下面是本技能的<b>真实产物</b>——不是截图，是可以直接点开、拖动、打印的离线 HTML。</p>

    <div class="howto">
      <b>怎么看</b>：点标题打开卡片 → 找到里面的图形 →
      <b>先预测再拖动</b>（猜一下拖到某个值会发生什么，再拖，看猜得对不对）。<br>
      <b>怎么造</b>：对 AI 说「怎么理解一致连续？」即可生成同款卡片；
      或手写 Markdown 后跑
      <code>python scripts/md2card.py "概念卡/XX-概念卡.md"</code>。<br>
      <b>重建本页</b>：增删卡片后跑 <code>python scripts/make_gallery.py</code>。
    </div>

    <div class="grid">
{chr(10).join(cards)}
    </div>

    <footer>
      共 {len(items)} 张卡片 · 全部单文件离线（0 外部依赖）· 由 math-concept-coach 生成
    </footer>
  </div>
</body>
</html>
"""
    out = EXAMPLES / "index.html"
    out.write_text(doc, encoding="utf-8")
    print(f"[OK] 画廊已生成：{out}")
    print(f"     卡片 {len(items)} 张 | 大小 {len(doc.encode('utf-8')) / 1024:.1f} KB")
    if missing:
        print(f"     [!] 缺少 HTML，已跳过：{', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
