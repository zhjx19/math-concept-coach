#!/usr/bin/env python3
"""极简 LaTeX → MathML 转换器（纯标准库，零依赖，离线可用）。

用途
----
未安装 pandoc 时，把概念卡里的 `$...$` / `$$...$$` 渲染成浏览器原生 MathML，
让降级卡片**同样拥有排版好的数学公式**，而不是一堆 LaTeX 源码。

为什么是 MathML
--------------
- 零依赖、零额外体积：MathML 是 HTML 的一部分，浏览器直接渲染，不需要
  MathJax / KaTeX，也不需要联网。
- 与 pandoc 主路径一致：`pandoc --mathml` 输出的也是 MathML，
  因此「有 pandoc」与「没 pandoc」两条路产出同构的结果。
- 现代浏览器（Chrome 109+ / Firefox / Safari）均已支持 MathML Core。

覆盖范围
--------
刻意限定在大学数学常用语法：上/下标、分式、根式、希腊字母、
求和积分极限、关系与二元运算符、常用函数名、绝对值等定界符。
**解析不了的结构不做猜测**——原样回落到 LaTeX 源码并以等宽字体显示。
宁可朴素，不可出错：公式错误比公式难看严重得多。

自测：python scripts/texmath.py
"""

import re

# ---------------- 符号表 ----------------
_SYMBOLS = {
    # 希腊字母
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "ϕ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # 关系符
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "approx": "≈", "equiv": "≡",
    "sim": "∼", "simeq": "≃", "propto": "∝", "ll": "≪", "gg": "≫",
    "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "in": "∈", "notin": "∉", "ni": "∋", "cup": "∪", "cap": "∩",
    "emptyset": "∅", "mid": "∣", "nmid": "∤", "parallel": "∥",
    "perp": "⊥", "angle": "∠", "prec": "≺", "succ": "≻",
    # 箭头
    "to": "→", "rightarrow": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "leftrightarrow": "↔",
    "Leftrightarrow": "⇔", "mapsto": "↦", "implies": "⇒",
    "upuparrows": "⇈", "longrightarrow": "⟶", "longmapsto": "⟼",
    # 二元运算符
    "times": "×", "div": "÷", "pm": "±", "mp": "∓",
    "cdot": "⋅", "ast": "∗", "star": "⋆", "circ": "∘",
    "bullet": "∙", "oplus": "⊕", "otimes": "⊗", "ominus": "⊖",
    "wedge": "∧", "vee": "∨", "setminus": "∖", "neg": "¬",
    # 杂项符号
    "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ",
    "forall": "∀", "exists": "∃", "nexists": "∄", "prime": "′",
    "dots": "…", "ldots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    "angle": "∠", "triangle": "△", "square": "□", "star": "⋆",
    "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ",
    # 定界符
    "lvert": "|", "rvert": "|", "lVert": "‖", "rVert": "‖", "vert": "|",
    "langle": "⟨", "rangle": "⟩",
    "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
    # 间距
    "quad": " ", "qquad": "  ", ",": " ",
    ";": " ", "!": "",
}

# 间距命令：值为 mspace 宽度，None 表示忽略（负间距）
_SPACING = {
    ",": "0.17em", ":": "0.2em", ";": "0.28em", "!": None,
    " ": "0.25em", "quad": "1em", "qquad": "2em",
}

# 大运算符：上下限（用 msub/msup 表达，display 模式下浏览器自动渲染为上下）
_BIG_OPS = {
    "sum": "∑", "int": "∫", "prod": "∏", "coprod": "∐",
    "bigcup": "⋃", "bigcap": "⋂", "oint": "∮", "iint": "∬",
    "bigoplus": "⊕", "bigotimes": "⊗",
}

# 函数名：用正体 mi 呈现
_FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc",
    "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh",
    "log", "ln", "lg", "exp", "max", "min", "sup", "inf",
    "lim", "limsup", "liminf", "det", "dim", "ker", "rank", "gcd", "arg",
}

# \left / \right 后面的定界符别名
_DELIM_ALIAS = {
    "lbrace": "{", "rbrace": "}", "lbrack": "[", "rbrack": "]",
    "langle": "⟨", "rangle": "⟩", "vert": "|", "lvert": "|", "rvert": "|",
    "lVert": "‖", "rVert": "‖", "backslash": "\\",
}

_OPERATOR_CHARS = set("+-*/=<>()[]|∈∉⊂⊆∪∩∖⋅×÷±∓≤≥≠≈≡∼→←⇒⇔↦∀∃∑∫∏∂∇∞")


class TexError(Exception):
    """解析不了的结构：调用方应回落到 LaTeX 源码。"""


# ---------------- 词法 ----------------
def _tokenize(s):
    toks, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = re.match(r"\\[a-zA-Z]+", s[i:])
            if m:
                toks.append(("cmd", m.group(0)[1:]))
                i += len(m.group(0))
                continue
            if i + 1 < len(s):                      # \. 转义，或 \, \; \! 等间距命令
                nxt = s[i + 1]
                toks.append(("cmd", nxt) if nxt in _SPACING else ("chr", nxt))
                i += 2
                continue
            i += 1
            continue
        if c in "{}^_}&":
            toks.append(("tok", c))
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        toks.append(("chr", c))
        i += 1
    return toks


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _chr_node(ch):
    if ch.isdigit() or (ch in "." and False):
        return f"<mn>{_esc(ch)}</mn>"
    if ch in _OPERATOR_CHARS:
        return f"<mo>{_esc(ch)}</mo>"
    return f"<mi>{_esc(ch)}</mi>"


# ---------------- 语法 ----------------
def _parse(toks, i=0, end=None):
    """解析一组 token，直到遇到 end（'}'）或结束。返回 (节点串, 新位置)。"""
    nodes = []
    while i < len(toks):
        t, v = toks[i]
        if t == "tok" and v == "}":
            if end == "}":
                return nodes, i + 1
            i += 1                                   # 多余的 } 直接丢弃
            continue
        node, i = _parse_one(toks, i)
        if node:
            nodes.append(node)
    if end == "}":
        raise TexError("缺少右花括号 }")
    return nodes, i


def _parse_one(toks, i):
    """解析一个元素，并吃掉紧跟其后的 ^ / _。"""
    t, v = toks[i]
    if t == "cmd":
        return _parse_cmd(toks, i)
    if t == "tok":
        if v == "{":
            nodes, i2 = _parse(toks, i + 1, end="}")
            inner = "".join(nodes)
            return (f"<mrow>{inner}</mrow>" if len(nodes) != 1 else inner or ""), i2
        if v in ("^", "_"):                          # 孤立的 ^/_：跳过
            unit, i2 = _next_unit(toks, i + 1)
            return unit, i2
        return "", i + 1
    if v.isdigit():                                  # 连续数字合并成一个 <mn>
        j, buf = i, []
        while j < len(toks) and toks[j][0] == "chr" and toks[j][1].isdigit():
            buf.append(toks[j][1])
            j += 1
        node = f"<mn>{_esc(''.join(buf))}</mn>"
        return _apply_scripts(node, toks, j)
    node = _chr_node(v)
    return _apply_scripts(node, toks, i + 1)


def _next_unit(toks, i):
    """取一个「单元」：{group} / 单条命令 / 单字符。"""
    if i >= len(toks):
        raise TexError("表达式意外结束")
    t, v = toks[i]
    if t == "tok" and v == "{":
        nodes, i2 = _parse(toks, i + 1, end="}")
        inner = "".join(nodes)
        return (f"<mrow>{inner}</mrow>" if len(nodes) != 1 else inner or "<mi></mi>"), i2
    if t == "cmd":
        return _parse_cmd(toks, i)
    return _chr_node(v), i + 1


def _apply_scripts(node, toks, i):
    """处理连续的 ^ 与 _（支持 x^2、x_i^2、x^{a+b}）。"""
    sub = sup = None
    while i < len(toks) and toks[i][0] == "tok" and toks[i][1] in ("^", "_"):
        kind = toks[i][1]
        unit, i = _next_unit(toks, i + 1)
        if kind == "_":
            sub = unit
        else:
            sup = unit
    if sub is not None and sup is not None:
        return f"<msubsup>{node}{sub}{sup}</msubsup>", i
    if sub is not None:
        return f"<msub>{node}{sub}</msub>", i
    if sup is not None:
        return f"<msup>{node}{sup}</msup>", i
    return node, i


def _parse_cmd(toks, i):
    name = toks[i][1]
    i += 1

    # 间距
    if name in _SPACING:
        w = _SPACING[name]
        return (f'<mspace width="{w}"/>' if w else ""), i

    # 分式
    if name in ("frac", "dfrac", "tfrac", "cfrac"):
        a, i = _next_unit(toks, i)
        b, i = _next_unit(toks, i)
        return _apply_scripts(f"<mfrac>{a}{b}</mfrac>", toks, i)

    # 根式：\sqrt{x} 与 \sqrt[n]{x}
    if name == "sqrt":
        if i < len(toks) and toks[i][0] == "chr" and toks[i][1] == "[":
            buf, j = [], i + 1
            while j < len(toks) and not (toks[j][0] == "chr" and toks[j][1] == "]"):
                buf.append(toks[j])
                j += 1
            idx = "".join(_parse(buf)[0]) or "<mn>2</mn>"
            body, j2 = _next_unit(toks, j + 1)
            return f"<mroot>{body}{idx}</mroot>", j2
        body, i = _next_unit(toks, i)
        return f"<msqrt>{body}</msqrt>", i

    # 纯文本
    if name == "text":
        if i < len(toks) and toks[i][0] == "tok" and toks[i][1] == "{":
            depth, j, buf = 1, i + 1, []
            while j < len(toks) and depth:
                if toks[j] == ("tok", "{"):
                    depth += 1
                elif toks[j] == ("tok", "}"):
                    depth -= 1
                    if depth == 0:
                        break
                buf.append(toks[j][1] if toks[j][0] == "chr" else " ")
                j += 1
            return f"<mtext>{_esc(''.join(buf))}</mtext>", j + 1
        unit, i = _next_unit(toks, i)
        return f"<mtext>{_esc(unit)}</mtext>", i

    # \left / \right：丢弃修饰符，保留其后的定界符
    if name in ("left", "right", "big", "Big", "bigg", "Bigg"):
        if i < len(toks):
            t, v = toks[i]
            if t == "cmd":
                ch = _DELIM_ALIAS.get(v, _SYMBOLS.get(v, "."))
                return f"<mo>{_esc(ch)}</mo>", i + 1
            return f"<mo>{_esc(v)}</mo>", i + 1
        return "", i

    # 大运算符
    if name in _BIG_OPS:
        return _apply_scripts(f"<mo>{_BIG_OPS[name]}</mo>", toks, i)

    # 函数名
    if name in _FUNCS:
        return _apply_scripts(f"<mi>{name}</mi>", toks, i)

    # 符号表
    if name in _SYMBOLS:
        ch = _SYMBOLS[name]
        kind = "mo" if (ch in _OPERATOR_CHARS or ch in "≤≥≠≈≡∼∝≪≫⊂⊆⊃⊇∈∉∋∪∩∅∣∥⊥∠≺≻→←⇒⇐↔⇔↦∀∃∞∂∇±∓×÷⋅⋆∘∙⊕⊗") else "mi"
        return f"<{kind}>{_esc(ch)}</{kind}>", i

    # 数字型命令等，无法识别 → 抛出，由调用方回落为源码
    raise TexError(f"不支持的命令 \\{name}")


def _render_tokens(toks):
    nodes, _ = _parse(toks)
    if not nodes:
        return ""
    return "".join(nodes)


# ---------------- 对外接口 ----------------
def tex_to_mathml(tex, display=False):
    """把一段 LaTeX 数学代码转为 MathML 字符串。

    解析不了时抛出 TexError，调用方应回落到 LaTeX 源码显示。
    """
    body = tex.strip()
    if not body:
        raise TexError("空公式")
    # 明显超出能力范围的结构，直接回落，不做半吊子猜测
    if re.search(r"\\begin\{|\\matrix|\\pmatrix|\\cases|\\binom", body):
        raise TexError("矩阵/方程组等结构不在支持范围内")
    inner = _render_tokens(_tokenize(body))
    if not inner:
        raise TexError("解析结果为空")
    attr = ' display="block"' if display else ' display="inline"'
    return f"<math{attr}><mrow>{inner}</mrow></math>"


# ---------------- 自测 ----------------
if __name__ == "__main__":
    cases = [
        (r"\varepsilon", False),
        (r"\forall \varepsilon > 0,\ \exists N", False),
        (r"\lvert a_n - a \rvert < \varepsilon", False),
        (r"\lim_{n \to \infty} a_n = a", True),
        (r"\sum_{i=1}^{n} i = \frac{n(n+1)}{2}", True),
        (r"f'(x) = \lim_{h \to 0} \frac{f(x+h)-f(x)}{h}", True),
        (r"\sqrt{x^2 + y^2}", False),
        (r"\sqrt[3]{x}", False),
        (r"\int_0^1 x^2 \, dx = \frac{1}{3}", True),
        (r"\sin^2 x + \cos^2 x = 1", False),
        (r"A \subseteq B,\ x \notin A", False),
        (r"\det(A) \neq 0 \Rightarrow A^{-1}\ \text{存在}", False),
        (r"x_{i}^{2}", False),
    ]
    ok = bad = 0
    for tex, disp in cases:
        try:
            out = tex_to_mathml(tex, disp)
            ok += 1
            print(f"  ✓ {tex}")
            print(f"     {out[:110]}{'…' if len(out) > 110 else ''}")
        except TexError as e:
            bad += 1
            print(f"  ↘ {tex}   → 回落源码（{e}）")
    print(f"\n自测：转换成功 {ok} / 回落 {bad}")
