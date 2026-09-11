#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 assets/demo.gif —— 概念卡的浏览器真实渲染回放。

为什么不用 vhs / 终端录屏：
    本技能的产物是 HTML 概念卡，不是终端程序。真实回放应当发生在浏览器里。
    （assets/demo.tape 另录终端流水线那一段，两者互补。）

这份脚本就是 demo.gif 的可复现录制脚本（数据脚本），内容全部是真实渲染：
    * 打开 examples/数列极限-概念卡.html（Chromium 实际渲染，非截图拼接）
    * 点「展开全部」——走卡片自身的 .facet-toggle 点击处理器
    * 拖动 ε 滑块——走卡片自身的 input 事件处理器，N 线随之移动
    * 滚动到各章节取帧
Pillow 只负责把真实帧按统一调色板合成 GIF，并烧一个章节字幕条。

依赖：playwright（含 chromium）+ Pillow
    pip install playwright pillow
    playwright install chromium        # 若本机无缓存浏览器

用法：
    python scripts/make_demo_gif.py
    python scripts/make_demo_gif.py examples/矩阵的秩-概念卡.html -o assets/demo.gif
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent

VIEW_W, VIEW_H = 1180, 760          # 浏览器视口
OUT_W, OUT_H = 900, 580             # GIF 尺寸（与视口等比，约 1.55）
GIF_COLORS = 128                    # 统一调色板颜色数

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


# --------------------------------------------------------------------------
# 浏览器
# --------------------------------------------------------------------------
def find_chromium_executable() -> str | None:
    """回退路径：直接扫本机缓存的 Chromium / headless shell。"""
    roots = [Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []
    roots += [
        Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",
        Path.home() / "AppData" / "Local" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    patterns = (
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell.exe",
        "chromium_headless_shell-*/chrome-headless-shell-*/headless_shell.exe",
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
        "chromium-*/chrome-win64/chrome.exe",
        "chromium-*/chrome-win/chrome.exe",
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
    )
    for root in roots:
        if not str(root) or not root.is_dir():
            continue
        for pat in patterns:
            hits = sorted(root.glob(pat))
            if hits:
                return str(hits[-1])
    return None


def launch(pw):
    kwargs = dict(args=["--hide-scrollbars", "--force-color-profile=srgb"])
    try:
        return pw.chromium.launch(**kwargs)
    except Exception as exc:                        # noqa: BLE001
        exe = find_chromium_executable()
        if not exe:
            raise SystemExit(
                f"[x] 找不到可用的 Chromium：{exc}\n"
                f"    请先执行：playwright install chromium"
            ) from exc
        print(f"[i] 回退到本机缓存浏览器：{exe}")
        return pw.chromium.launch(executable_path=exe, **kwargs)


# --------------------------------------------------------------------------
# 取帧
# --------------------------------------------------------------------------
MEASURE_JS = """() => {
  const sy = window.scrollY;
  const off = el => el ? el.getBoundingClientRect().top + sy : null;
  const facets = [...document.querySelectorAll('details.facet')];
  const svgs = [...document.querySelectorAll('svg')];
  const i = document.querySelector('.wb-widget input[type=range]');
  const r = i ? i.getBoundingClientRect() : null;
  return {
    total: document.documentElement.scrollHeight,
    vh: window.innerHeight,
    f1: off(facets[0]),
    widget: off(document.querySelector('.wb-widget')),
    f6: off(facets[5]),
    kmap: off(svgs.length ? svgs[svgs.length - 1] : null),
    slider: r ? { left: r.left, width: r.width, y: r.top + r.height / 2,
                  min: +i.min, max: +i.max, value: +i.value } : null,
  };
}"""


class Recorder:
    """按顺序收集真实截图帧，每帧自带停留时长与字幕。"""

    def __init__(self, page):
        self.page = page
        self.frames: list[tuple[bytes, int, str]] = []

    def shot(self, label: str, ms: int = 110):
        self.frames.append((self.page.screenshot(type="png"), ms, label))

    def scroll_to(self, y: float):
        self.page.evaluate("y => window.scrollTo(0, y)", float(y))

    def travel(self, y_from: float, y_to: float, steps: int, label: str, ms: int = 82):
        """缓入缓出滚动，每步取一帧。"""
        for k in range(1, steps + 1):
            t = k / steps
            e = 2 * t * t if t < 0.5 else 1 - 2 * (1 - t) ** 2
            self.scroll_to(y_from + (y_to - y_from) * e)
            self.page.wait_for_timeout(16)
            self.shot(label, ms)


def caption(png_bytes: bytes, text: str, font, size: tuple[int, int]) -> "object":
    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(png_bytes)).convert("RGB").resize(size, Image.LANCZOS)
    if text:
        d = ImageDraw.Draw(im, "RGBA")
        pad_x, pad_y = 14, 8
        box = d.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x, y = 18, im.height - th - pad_y * 2 - 16
        d.rounded_rectangle([x, y, x + tw + pad_x * 2, y + th + pad_y * 2],
                            radius=9, fill=(24, 32, 44, 208))
        d.text((x + pad_x, y + pad_y - 2), text, font=font, fill=(255, 255, 255))
    return im


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build(card: Path, out: Path) -> int:
    from playwright.sync_api import sync_playwright
    from PIL import Image, ImageFont

    font = None
    for fp in FONT_CANDIDATES:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 21)
                break
            except Exception:                  # noqa: BLE001
                continue
    if font is None:
        font = ImageFont.load_default()

    with sync_playwright() as pw:
        browser = launch(pw)
        page = browser.new_page(viewport={"width": VIEW_W, "height": VIEW_H},
                                device_scale_factor=1)
        page.goto(card.resolve().as_uri())
        # 组件在 F5 折叠面内，默认不可见 → 先等它挂载
        page.wait_for_selector(".wb-widget", state="attached", timeout=15000)
        page.wait_for_timeout(500)

        # ① 六个面全部展开。注意：卡片默认已展开 F1，此时按钮文案是「收起全部」，
        #    盲点一下会全收起来 —— 所以按真实状态点到位为止（全部走卡片自己的点击处理器）。
        for _ in range(3):
            if all(page.eval_on_selector_all("details.facet", "els => els.map(e => e.open)")):
                break
            page.click(".facet-toggle")
            page.wait_for_timeout(260)
        opened = page.eval_on_selector_all("details.facet", "els => els.map(e => e.open)")
        print(f"[i] 折叠面状态 {opened}")
        page.wait_for_selector(".wb-widget canvas", state="visible", timeout=10000)
        page.wait_for_timeout(600)

        m = page.evaluate(MEASURE_JS)
        total, vh = m["total"], m["vh"]
        print(f"[i] 页面高 {total}px / 视口 {vh}px")
        print(f"[i] 滑块定位 {m['slider']}")

        def top_of(y):
            return max(0.0, min(y - 78, total - vh))

        y_f1, y_wg = top_of(m["f1"]), top_of(m["widget"] - 40)
        y_f6, y_km = top_of(m["f6"]), top_of(m["kmap"] - 40)

        L_TOP = "数列极限 · 六棱镜拆解"
        L_F1 = "F1 正反拆解：正例 / 边界例 / 反例"
        L_WALK = "六棱镜逐面拆解"
        L_WG = "F5 自绘交互组件（零依赖 Canvas）"
        L_DRAG = "F5 拖动 ε：0.1 → 0.05，N 由 10 变 20"
        L_MAP = "F6 知识图谱 + 可复制 GeoGebra 指令"

        rec = Recorder(page)

        # ② 标题 / 钩子
        rec.scroll_to(0)
        page.wait_for_timeout(120)
        rec.shot(L_TOP, 700)

        # ③ F1 正反拆解
        rec.travel(0, y_f1, 5, L_F1, 95)
        rec.shot(L_F1, 560)
        rec.shot(L_F1, 300)

        # ④ 掠过 F2–F4，走到 F5
        rec.travel(y_f1, y_wg, 9, L_WALK)
        rec.shot(L_WG, 420)

        # ⑤ 真实拖动 ε 滑块 0.1 → 0.05 —— N 翻倍，正好回答卡片自己出的预测题
        s = page.evaluate(MEASURE_JS)["slider"]
        if s:
            frac = lambda v: (v - s["min"]) / (s["max"] - s["min"])  # noqa: E731
            cur_x = s["left"] + frac(s["value"]) * s["width"]
            tgt_x = s["left"] + frac(0.05) * s["width"]
            page.mouse.move(cur_x, s["y"])
            page.mouse.down()
            steps = 8
            for k in range(1, steps + 1):
                page.mouse.move(cur_x + (tgt_x - cur_x) * k / steps, s["y"])
                page.wait_for_timeout(26)
                rec.shot(L_DRAG, 110)
            page.mouse.up()
            page.wait_for_timeout(60)
            rec.shot(L_WG, 700)

        # ⑥ 知识图谱
        rec.travel(y_wg, y_f6, 5, L_WALK)
        rec.travel(y_f6, y_km, 4, L_MAP)
        rec.shot(L_MAP, 820)
        rec.shot(L_MAP, 300)

        browser.close()

    raw = rec.frames
    print(f"[i] 原始帧 {len(raw)}")

    # ⑦ 加字幕 + 统一调色板合成 GIF（避免帧间闪烁）
    size = (OUT_W, OUT_H)
    imgs = [caption(png, label, font, size) for png, _, label in raw]
    base = imgs[0].quantize(colors=GIF_COLORS, method=Image.MEDIANCUT)
    qs = [im.quantize(palette=base, dither=Image.FLOYDSTEINBERG) for im in imgs]

    out.parent.mkdir(parents=True, exist_ok=True)
    durations = [ms for _, ms, _ in raw]
    qs[0].save(out, save_all=True, append_images=qs[1:], duration=durations,
               loop=0, optimize=True, disposal=2)
    print(f"[OK] {out}  {out.stat().st_size / 1024:.0f} KB  {OUT_W}x{OUT_H}  "
          f"{len(qs)} 帧  总时长 {sum(durations) / 1000:.1f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成概念卡演示 GIF（浏览器真实渲染）")
    ap.add_argument("card", nargs="?", default="examples/数列极限-概念卡.html",
                    help="输入概念卡 HTML（默认 examples/数列极限-概念卡.html）")
    ap.add_argument("-o", "--output", default="assets/demo.gif", help="输出 GIF 路径")
    args = ap.parse_args()

    card = Path(args.card)
    if not card.is_absolute():
        card = SKILL_DIR / card
    if not card.exists():
        print(f"[x] 找不到概念卡：{card}", file=sys.stderr)
        return 1
    out = Path(args.output)
    return build(card, out if out.is_absolute() else SKILL_DIR / out)


if __name__ == "__main__":
    raise SystemExit(main())
