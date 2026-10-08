#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_examples_sync.py —— 样例卡与主目录的同步门禁（**开发时用**）

为什么需要它
------------
`examples/` 里的样例卡是从主目录**拷贝**来的（为了给用户看「真实产物长什么样」）。
一旦主卡更新、而样例没跟着同步，两份 md 就**静默分叉** ——
题面还在、数字还在，只是**旧了**；没有任何现有脚本会发现这件事。
本脚本把「分叉」变成可执行断言。

用法
    python3 scripts/check_examples_sync.py <主目录>            # 只检查，报告分叉
    python3 scripts/check_examples_sync.py <主目录> --fix      # 用主卡覆盖样例并重生成 HTML，再复扫

为什么主目录要当参数传
--------------------
本脚本是**开发流程专用**：分发出去的技能里只有 `examples/`，没有「主目录」。
主目录是作者自己的卡片集合（各人路径不同），所以**不写死**，由调用方传入 ——
这也满足发版验证门「脚本内不得含任何本机私有路径」。

豁免规则
--------
`examples/` 里**没有同名主卡**的样例（如独立写的 `一致连续`、`大数定律`）判为
「仅存在于 examples」，**不报分叉** —— 它们是独立样例，本来就不与主目录同步。

判据（两层，任一不过即算分叉）
    md   逐字节相同
    html 逐字节相同（md2card 是确定性生成，同一 md 必出同一 html；
                     故 html 不同 ⟹ 要么 md 分了叉，要么 html 是旧的没重生成）

退出码
    0 = 当前状态全部同步（--fix 修完后再复扫，故修好即 0）
    1 = 仍有分叉
"""

import argparse
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _configure_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def first_diff(a, b):
    """返回 (行号, a 那一行, b 那一行)；完全相同返回 None。"""
    if a == b:
        return None
    la, lb = a.split("\n"), b.split("\n")
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else "<缺失>"
        y = lb[i] if i < len(lb) else "<缺失>"
        if x != y:
            return i + 1, x, y
    return 1, "<长度不同>", "<长度不同>"


def scan(ex, master):
    """扫一遍样例目录，返回 (synced, split, only_ex)。split 项为 (label, why)。"""
    synced, split, only_ex = [], [], []
    for s in sorted(ex.glob("*-概念卡.md")):
        m = master / s.name
        label = s.stem.replace("-概念卡", "")
        if not m.exists():
            only_ex.append(label)
            continue
        md_same = s.read_bytes() == m.read_bytes()
        hs, hm = ex / (s.stem + ".html"), master / (s.stem + ".html")
        html_same = (not hs.exists() and not hm.exists()) or \
                    (hs.exists() and hm.exists() and hs.read_bytes() == hm.read_bytes())
        if md_same and html_same:
            synced.append(label)
        else:
            why = []
            if not md_same:
                why.append(("md", first_diff(s.read_text(encoding="utf-8"),
                                             m.read_text(encoding="utf-8"))))
            if not html_same:
                why.append(("html", None))
            split.append((label, why))
    return synced, split, only_ex


def report(ex, master, synced, split, only_ex):
    o = ["=" * 78,
         "样例同步门禁：%s  ↔  %s" % (ex, master),
         "=" * 78,
         "样例卡 %d 张 ｜ 有同名主卡 %d ｜ 仅存在于 examples %d"
         % (len(synced) + len(split) + len(only_ex),
            len(synced) + len(split), len(only_ex)),
         ""]
    o.append("── 已同步（md 与 html 均逐字节相同）：%d ──" % len(synced))
    o.append("  " + ("、".join(synced) if synced else "（无）"))
    o.append("")
    o.append("── 分叉：%d ──" % len(split))
    if not split:
        o.append("  ✓ 无")
    for label, why in split:
        o.append("  ✗ %s   （%s 不同）" % (label, "、".join(k for k, _ in why)))
        for k, d in why:
            if d:
                ln, xs, xm = d
                o.append("      %s 第 %d 行：" % (k, ln))
                o.append("        样例 : %s" % xs[:96])
                o.append("        主卡 : %s" % xm[:96])
            elif k == "html":
                o.append("      html 不同 —— 多半是 md 分叉的连带，或 html 没重生成")
    o.append("")
    o.append("── 仅存在于 examples（豁免，无同名主卡）：%d ──" % len(only_ex))
    o.append("  " + ("、".join(only_ex) if only_ex else "（无）"))
    if only_ex:
        o.append("  说明：这些是独立写的样例，本来就不与主目录同步，不算分叉。")
    o.append("")
    return o


def main():
    ap = argparse.ArgumentParser(description="样例卡与主目录的同步门禁")
    ap.add_argument("master", help="主卡片目录（作者的卡片集合）")
    ap.add_argument("--examples", default=str(HERE.parent / "examples"),
                    help="样例目录（默认：技能自带的 examples/）")
    ap.add_argument("--fix", action="store_true",
                    help="用主卡覆盖样例并重生成 HTML，然后复扫")
    ap.add_argument("-o", "--out", default=None,
                    help="报告写到 UTF-8 文件（避免控制台转码）")
    a = ap.parse_args()
    _configure_console()

    master = pathlib.Path(a.master)
    ex = pathlib.Path(a.examples)
    if not master.is_dir():
        raise SystemExit("[x] 主目录不存在：%s" % master)
    if not ex.is_dir():
        raise SystemExit("[x] 样例目录不存在：%s" % ex)
    if not any(ex.glob("*-概念卡.md")):
        raise SystemExit("[x] 样例目录里没有 *-概念卡.md：%s" % ex)

    synced, split, only_ex = scan(ex, master)
    o = report(ex, master, synced, split, only_ex)

    if a.fix and split:
        o.append("── --fix：用主卡覆盖样例并重生成 HTML ──")
        failed = 0
        for label, _ in split:
            src = master / ("%s-概念卡.md" % label)
            dst = ex / ("%s-概念卡.md" % label)
            try:
                dst.write_bytes(src.read_bytes())
                r = subprocess.run([sys.executable, str(HERE / "md2card.py"), str(dst)],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=300)
            except subprocess.TimeoutExpired:
                r = None
            ok = r is not None and r.returncode == 0 and (ex / ("%s-概念卡.html" % label)).exists()
            o.append("  %s %s" % ("✓" if ok else "✗", label))
            if not ok:
                failed += 1
                err = (getattr(r, "stderr", "") or "(超时)")[:200]
                o.append("       md2card 失败：%s" % err)
        # 复扫：按**修复后**的真实状态报结论与退出码
        synced, split, only_ex = scan(ex, master)
        o.append("")
        o.append("── --fix 后复扫 ──")
        o.append("  已同步 %d ｜ 分叉 %d ｜ 豁免 %d%s"
                 % (len(synced), len(split), len(only_ex),
                    "" if not split else "  （仍有：%s）" % "、".join(l for l, _ in split)))
        if failed:
            o.append("  ⚠ 有 %d 张 md2card 未成功，其 html 可能仍旧。" % failed)
        o.append("")

    o.append("结论：%s（已同步 %d ｜ 分叉 %d ｜ 豁免 %d）"
             % ("全部同步" if not split else "存在分叉，需修", len(synced), len(split), len(only_ex)))

    text = "\n".join(o)
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0 if not split else 1


if __name__ == "__main__":
    sys.exit(main())
