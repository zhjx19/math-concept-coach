#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_skill.py —— 双层体检。

  第一层（技能说明书）：lint_skill.py --self
      验 SKILL.md / README.md / references 有没有把「默认读者与难度上限」这条约定
      真正写进**可执行的位置**（frontmatter、正文节、纪律红线、过程手册）。
      用意：约定写在文档里但 agent 读不到，等于没写。

  第二层（概念卡）：lint_skill.py <目录或文件...>
      用「新红线第 10 条」点名的工具清单扫概念卡，**读上下文分级**，
      区分「深度越界 / 边界越界 / 合规的免责说明」——裸 grep 会高估。

用法：
    python lint_skill.py --self
    python lint_skill.py 概念卡/
    python lint_skill.py 概念卡/某张卡.md
"""

import argparse
import pathlib
import re
import sys

# ─────────────────────────────────────────────────────────────
# 红线第 10 条点名的禁用工具（词汇表来自 SKILL.md 原文清单）
#   tier 2 = 深度越界：可能承担推理机制
#   tier 1 = 边界越界：工具性提及，但未标层次
# ─────────────────────────────────────────────────────────────
#            名字              tier 匹配模式                        alias（红线里应有）      topic_keys（本卡主题判定）
BANNED = [
    ("测度论",          2, r"测度论|Lebesgue|勒贝格",              ["测度论"],
     ("测度论", "Lebesgue", "σ-代数", "sigma 代数", "可数可加")),
    ("a.e./几乎处处",   2, r"几乎处处|a\.e\.",                  ["a.e.", "几乎处处"],
     ("a.e.", "几乎处处")),
    ("零测集/可测函数",  2, r"零测集|可测集|可测函数|σ-代数|σ代数", ["零测集", "可测函数"],
     ("零测集", "可测函数", "可测集", "测度论", "Lebesgue", "σ-代数", "sigma")),
    ("Gram 矩阵",      1, r"Gram|格拉姆",                        ["Gram"], ("Gram", "格拉姆")),
    ("Cholesky 分解",   1, r"Cholesky|乔列斯基|舒尔分解",         ["Cholesky"],
     ("Cholesky", "乔列斯基", "舒尔")),
    ("抽象代数工具",     1, r"商环|理想\s*[（(]|张量积|Tensor\s*积|正规矩阵|正规算子|西空间|酉空间|Jordan\s*标准形",
     ["抽象代数"], ("商环", "张量", "正规", "西空间", "酉空间", "Jordan")),
    ("泛函分析",        1, r"泛函|Banach|Hilbert|巴拿赫|希尔伯特",  ["泛函"],
     ("泛函", "Banach", "Hilbert", "巴拿赫")),
    ("几何级数判收敛",   1, r"几何级数.{0,6}收敛|比值判别|根值判别", ["几何级数"],
     ("几何级数", "比值判别", "根值判别")),
    ("自造抽象框架",     2, r"累加器|标准化器|首达时间",            ["累加器"],
     ("累加器", "标准化器", "首达时间")),
    # ── 数学分析域：这些相对「极限与连续」都属于更后面 ──
    #    （原清单是从概率卡的真实问题反推的，只覆盖概率域 —— 这是它的缺口）
    ("泰勒展开/渐近记号", 1, r"泰勒展开|泰勒公式|\bO\(x\^|\bo\(x\^|\bO\(\(|小o|渐近记号",
     ["泰勒"], ("泰勒",)),
    ("洛必达法则",       1, r"洛必达",                          ["洛必达"],
     ("洛必达",)),
    ("等价无穷小/洛必达的算法性使用", 1, r"等价无穷小替换|用洛必达算|洛必达法则计算",
     ["等价无穷小"], ("等价无穷小",)),
    ("中值定理",         1, r"罗尔定理|拉格朗日中值|柯西中值|泰勒中值",
     ["中值定理"], ("中值定理", "罗尔定理")),
    ("导数作为前提",      1, r"可导性|导数存在|\b可导\b",     ["可导"],
     ("可导",)),
]

# 合规信号：出现即说明作者已意识到层次，只做提示不做推理工具
# 注意：markdown 粗体会**打断短语**（「都是**测度论语言**」）——
# SHELVE 的每条模式都要能容忍中间夹 ** ，否则合规行会被误判成越界。
SHELVE = re.compile(
    # 「这是更后面的东西」的各种说法
    r"更后面的|后面(会|再|才)|先记住|你现在?不用|你现在?不需要|不要求|超纲|暂不|暂不引入|"
    # 「你现在不需要它」的显式豁免（本卡实际在用的措辞）
    r"本卡不用它|不用它你也|本卡不依赖|不需要测度论|不需要它|不是本课|"
    # 「点名严格名字但声明是测度论语言」
    r"那?是\*{0,2}测度论语言|是\*{0,2}测度论的语言|严格的名字是|"
    # 「读不下去就跳」的预告
    r"读不下去就跳到|跳过|你可以直接看|层次声明|"
    r"本课不|课程不|只需记住|只需要记住|先有个印象|了解一下|不用现在|不展开|略过|留个名字|"
    # 教材差异
    r"教材.*不讲|教材.*默认|若你教材|如果你教材|有的教材|部分教材|多数本科教材|"
    r"本卡按|不必现在|不作为|仅作|只作(提示|标注)|按你教材"
)


def strip_chain_refs(line, card_names):
    """把「链上另一张卡的卡名」从行里抹掉。

    一张卡提到同链另一张卡的名字（例如「概率的测度论定义」这个名字本身含
    「测度论」）是**导航**，不是引入超纲工具。抹掉卡名后再判，才不会误报。
    """
    for nm in card_names:
        if nm and nm in line:
            line = line.replace(nm, "")
    return line

# 承重句：a.e. 若出现在「定理/结论/一句话钩子/核心」位置，就是承担推理机制
LOADBEARING = re.compile(
    r"^\s*[-*>|]?\s*(\*\*)?(一句话钩子|定理|结论|核心|⭐|##)|"
    r"本卡(的)?(核心|主干|组织|分水岭|分界线|一句话)|"
    r"(就是|正是|正是其本质|本质上就是).{0,12}(Gram|a\.e|几乎处处)"
)


def load(p):
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def head_line(md, i):
    for j in range(i, -1, -1):
        s = md[j]
        if s.startswith("#"):
            return re.sub(r"^#+\s*", "", s)[:34]
    return "(文首)"


def redline_nums(skill):
    """取『纪律红线』那一节的编号：从含该词的标题起，读到下一个同级或更高级标题为止。"""
    lines = skill.split("\n")
    start = None
    lvl = 0
    for i, l in enumerate(lines):
        if "纪律红线" in l and l.lstrip().startswith("#"):
            start = i
            lvl = len(l) - len(l.lstrip("#"))
            break
    if start is None:
        return []
    body = []
    for l in lines[start + 1:]:
        if l.lstrip().startswith("#"):
            if len(l) - len(l.lstrip("#")) <= lvl:
                break
        body.append(l)
    return [int(x) for x in re.findall(r"^(\d+)\. \*\*", "\n".join(body), flags=re.M)]


def is_note_line(lines, i):
    """末尾「⚠ 核对提示」节内的行 —— 术语应当出现，不算越界。"""
    for j in range(i, -1, -1):
        s = lines[j]
        if s.startswith("## "):
            return "核对提示" in s
        if s.startswith("# "):
            return False
    return False


def card_level_declaration(lines):
    """读〔层次声明〕：本卡声明为「更后面的工具」的词，全卡视为已标注。

    为什么要有这个：一个工具在一张卡里可能出现几十次（全卡都在指回它），
    但**只需要在首次相遇处标一次**。逐处贴标签既啰嗦又容易漏。

    认三种声明行（语义不同，机械效果相同 —— 都是「全卡豁免」）：
      · 〔层次声明〕      —— 该工具是「更后面的工具」，本卡只讲它的边界
      · 〔层次声明 · 本卡主题〕 —— 该工具就是本卡要讲的东西
      · 〔前置已学〕     —— 该工具属于**已完成的前置卡**，直接用不必解释
    第三种最容易漏：一张以「导数」为前置的卡，卡里满是「可导」二字，
    而「可导」在禁用清单里（它对*更早*的卡才是越界）。
    """
    decl = set()
    for l in lines:
        if any(k in l for k in ("层次声明", "前置已学")):
            for _n, _t, _p, _a, tkeys in BANNED:
                for k in tkeys:
                    if k in l:
                        decl.add(k)
    return decl


def card_subject(lines):
    """从标题行与所属行抽「本卡主题」关键词表。"""
    head = "\n".join(lines[:12])
    subs = set()
    for s in lines[:10]:
        if s.startswith("# ") or "所属" in s:
            for _n, _t, _p, _a, keys in BANNED:
                for k in keys:
                    if k in s:
                        subs.add(k)
    return subs


def lint_cards(paths, outpath=None):
    files = []
    for p in paths:
        p = pathlib.Path(p)
        files += sorted(p.glob("*.md")) if p.is_dir() else [p]

    # 链上所有卡名（用于「链上指向」豁免）
    card_names = {f.stem.replace("-概念卡", "") for f in files}

    rows = []
    total_lb = 0
    for f in files:
        md_all = load(f)
        if md_all is None:
            continue
        md = md_all.split("\n")
        subj = card_subject(md)
        declared = card_level_declaration(md)   # 〔层次声明〕点名的工具
        name = f.stem.replace("-概念卡", "")

        # 该文件是不是概念卡（概念卡必有 F1..F6）
        if not any(l.startswith("## F") for l in md):
            rows.append((name, "skip", [], "非概念卡（清单/目录），跳过"))
            continue

        lb = {}          # 工具 -> 承重行号
        shelf = {}       # 工具 -> 已合规提及行号
        for bname, tier, pat, _al, tkeys in BANNED:
            if any(k in declared for k in tkeys):
                shelf.setdefault(bname, []).append(-1)   # 卡级已声明：全卡豁免
                continue
            for i, l in enumerate(md):
                if not re.search(pat, l):
                    continue
                if any(k in subj for k in tkeys):
                    continue                      # 本卡主题，豁免
                if "〔教材口径〕" in l or is_note_line(md, i):
                    shelf.setdefault(bname, []).append(i)   # 教材口径节，豁免
                    continue
                if SHELVE.search(l):
                    shelf.setdefault(bname, []).append(i)
                    continue
                if not re.search(pat, strip_chain_refs(l, card_names)):
                    shelf.setdefault(bname, []).append(i)   # 只命中链上卡名 → 导航，豁免
                    continue
                lb.setdefault(bname, []).append(i)

        deep = [(k, v) for k, v in lb.items()
                if dict((x[0], x[1]) for x in BANNED)[k] == 2]
        edge = [(k, v) for k, v in lb.items()
                if dict((x[0], x[1]) for x in BANNED)[k] == 1]
        n_lb = sum(len(v) for v in lb.values())
        total_lb += n_lb
        tag = "deep" if deep else ("edge" if edge else "clean")
        detail = []
        for k, v in sorted(deep + edge, key=lambda r: -len(r[1])):
            detail.append("%s %d 行(首处 L%d · %s)" % (k, len(v), v[0] + 1,
                                                     head_line(md, v[0])))
        if shelf:
            detail.append("已合规提及 %d 项（教材口径节/带免责措辞）" % len(shelf))
        rows.append((name, tag, n_lb, detail))

    deep_n = sum(1 for r in rows if r[1] == "deep")
    edge_n = sum(1 for r in rows if r[1] == "edge")
    cln = sum(1 for r in rows if r[1] == "clean")
    skip = sum(1 for r in rows if r[1] == "skip")

    L = []
    L.append("=" * 74)
    L.append("概念卡难度体检（已排除：本卡主题 / 〔教材口径〕标注行 / ⚠核对提示节 / 非概念卡）")
    L.append("=" * 74)
    L.append("样本 %d 个文件：概念卡 %d、非概念卡 %d" % (len(files), len(files) - skip, skip))
    L.append("")
    for name, tag, n_lb, detail in rows:
        if tag == "skip":
            L.append("  –  %-28s %s" % (name[:28], detail[0]))
            continue
        mark = {"deep": "★ 深度越界", "edge": "⚠ 边界越界", "clean": "○ 清白"}[tag]
        L.append("  %s %-28s 承重 %d 行" % (mark, name[:28], n_lb))
        for d in detail:
            L.append("        %s" % d)
    L.append("")
    L.append("─" * 74)
    L.append("承重行合计 %d ｜ ★深度 %d 张 ｜ ⚠边界 %d 张 ｜ ○清白 %d 张 ｜ 跳过 %d"
             % (total_lb, deep_n, edge_n, cln, skip))
    if deep_n:
        L.append("★ 需重做骨架：" + "、".join(r[0] for r in rows if r[1] == "deep"))
    if edge_n:
        L.append("⚠ 需标层次　：" + "、".join(r[0] for r in rows if r[1] == "edge"))
    txt = "\n".join(L)

    if outpath:
        pathlib.Path(outpath).write_text(txt, encoding="utf-8", newline="\n")
    print("（完整报告见 %s）" % outpath if outpath else txt)
    return 1 if (deep_n or edge_n) else 0


def lint_self(root):
    """验「约定有没有写在 agent 真正读得到的位置」。

    要点：frontmatter 是 agent 判断「怎么用」的唯一依据，约定只写在正文里
    等于没写；纪律红线编号必须连续，否则「第 N 条」会指错。
    """
    s = pathlib.Path(root)
    print("=" * 72)
    print("技能说明书体检：%s" % s)
    print("=" * 72)

    skill = load(s / "SKILL.md") or ""
    play = load(s / "references" / "process-playbook.md") or ""
    readme = load(s / "README.md") or ""
    ok = True

    print("\n[1] 默认基线是否写在可执行位置")
    for tag, c in [
        ("frontmatter description 有默认读者", "默认读者是刚学完高中数学" in skill.split("---")[1]),
        ("正文有「默认读者与难度上限」节", "## 默认读者与难度上限" in skill),
        ("节内三条铁律齐全", all(k in skill for k in ("先搭梯子，再讲概念", "不超纲", "分档给"))),
        ("节内指向过程手册第五节", "process-playbook.md` 第五节" in skill),
        ("纪律红线含难度纪律", "难度不超纲，且先搭梯子" in skill),
        ("README 写死默认读者", "刚学完高中数学、正在上第一门大学数学课" in readme),
    ]:
        print("  %s %s" % ("OK  " if c else "FAIL", tag))
        ok &= c

    print("\n[2] 过程手册的搭梯子程序")
    for tag, c in [
        ("第五节：难度分档与搭梯子", "## 五、难度分档与搭梯子" in play),
        ("三问判档表", "5.1 判档" in play),
        ("每档 F3 给什么", "5.2 每档的 F3" in play),
        ("搭梯子三步", "5.3 搭梯子三步" in play),
        ("语言三档示范", "5.4 语言示范" in play),
        ("何时读表已收录第五节", "**五**（先判档，再搭梯子）" in play),
    ]:
        print("  %s %s" % ("OK  " if c else "FAIL", tag))
        ok &= c

    print("\n[3] 纪律红线编号连续性")
    nums = redline_nums(skill)
    cont = bool(nums) and nums == list(range(1, len(nums) + 1))
    print("  %s 编号 %s（连续=%s，%d 条）"
          % ("OK  " if cont else "FAIL", nums, cont, len(nums)))
    ok &= cont

    print("\n[4] 禁用工具清单与脚本同步（防漂移）")
    doc = skill + "\n" + play
    missing = []
    for name, _tier, _pat, alias, _tk in BANNED:
        if not any(a in doc for a in alias):
            missing.append("%s（应含 %s）" % (name, "/".join(alias)))
    print("  清单共 %d 项；SKILL.md+手册中未点名的：%d" % (len(BANNED), len(missing)))
    for m in missing:
        print("     · %s" % m)
    if missing:
        print("     ↑ 这些是脚本能扫、但红线没写的。补进红线，或从清单删掉。")
        ok = False

    print("\n[5] 仓库内换行符统一为 LF（.gitattributes 声明 `* text=auto eol=lf`）")
    # 为什么值得单列一条检查：脚本在 Windows 上 write_text 漏 `newline="\n"` 时会悄悄写出 CRLF，
    # 导致「同一份 md 在不同平台产出不同字节」，且每次重渲都让工作区出现「只有换行不同」的伪改动。
    # 2026-10-09 实测：md2card / make_gallery / knowledge_map 三处都踩过，已修，并在此设防。
    BIN = {".gif", ".png", ".jpg", ".jpeg", ".ico", ".pdf", ".zip"}
    crlf = []
    for p in sorted(pathlib.Path(root).rglob("*")):
        if not p.is_file() or ".git" in p.parts or p.suffix.lower() in BIN:
            continue
        try:
            if b"\r\n" in p.read_bytes():
                crlf.append(p.relative_to(root).as_posix())
        except Exception:
            continue
    print("  含 CRLF 的文件：%d" % len(crlf))
    for c in crlf[:20]:
        print("     · %s" % c)
    if crlf:
        print("     ↑ 脚本写文件时补 `newline=\"\\n\"`，再用生成器重跑一次产物。")
        ok = False

    print("\n结论：%s" % ("全部通过" if ok else "有 FAIL，需修"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--self", action="store_true")
    ap.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent))
    ap.add_argument("-o", "--out", default=None, help="报告写到 UTF-8 文件（避免控制台转码）")
    a = ap.parse_args()
    if a.self:
        sys.exit(lint_self(a.root))
    if not a.paths:
        ap.error("给目录/文件，或用 --self")
    sys.exit(lint_cards(a.paths, a.out))


if __name__ == "__main__":
    main()