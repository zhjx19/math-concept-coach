# 图形化组件规范（Widget Spec）

> 概念卡支持三种「特殊代码块」，`scripts/md2card.py` 会把它们渲染成**真实内容**（不是原样显示代码）：
>
> | 代码块语言 | 渲染成 | 用途 |
> |---|---|---|
> | ` ```interactive ` | **可拖动交互图形**（Canvas + 滑块，单文件离线） | F5 图形化演示 |
> | ` ```concept-map ` | **知识图谱**（内联 SVG） | F6 联系其它概念 |
> | ` ```geogebra ` | **GeoGebra 复现指令** + 一键复制按钮 | F5 让学生自己动手 |
>
> 三种块都必须**顶格写**（可带少量缩进），块内不要出现空行。

---

## 一、组件选型：什么概念用哪个组件

| 概念类型 | 用哪个 | 典型概念 |
|---|---|---|
| 函数图像随参数变化、ε–δ、曲线上取点连线 | **`plot`** | 极限、连续、一致连续、导数（割线→切线）、中值定理、单调性、凹凸 |
| 离散数列 + ε–N | **`seq`** | 数列极限、收敛、子列 |
| 曲线下面积 / 分割求和 | **`riemann`** | 定积分、黎曼和、达布和 |
| 2 维线性变换、行列式、秩的几何 | **`matrix2`** | 线性变换、行列式、矩阵的秩、可逆、特征方向 |
| 向量的线性组合与张成 | **`vectors2`** | 线性相关/无关、基、张成空间、维数 |

> 都不合适时（如「数域」「欧氏空间」这类纯结构概念）→ **不画**，改为表格 + 结构说明。**不要硬凑图。**

### 表达式语法（`plot` / `seq` / `riemann` / 叠加层通用）

- 幂用 `^`：`x^2`、`x^(1/3)`
- **乘法必须显式写 `*`**：写 `2*x`，**不能**写 `2x`
- 可用函数：`sin cos tan asin acos atan sinh cosh tanh exp log`（=ln）`sqrt abs floor ceil sign min max pow`
- 可用常量：`pi`、`e`
- 自变量：`plot` 用 `x`；`seq` 用 `n`
- **叠加层 / 标记点里可以调用主函数**：写 `f(x0)`、`f(x0+d)`
- 未声明的标识符会被当作变量（取不到值就画不出来）——**变量名必须来自 `sliders`**

---

## 二、`plot`：函数图像 + 参数滑块

```interactive
{
  "type": "plot",
  "expr": "sin(1/x)",
  "xrange": [0.02, 1],
  "yrange": [-1.35, 1.35],
  "ratio": 0.5,
  "sliders": [
    {"name": "x0", "label": "x₀ 位置", "min": 0.03, "max": 0.9, "step": 0.01, "value": 0.6},
    {"name": "d",  "label": "δ",      "min": 0.005, "max": 0.25, "step": 0.005, "value": 0.06},
    {"name": "eps","label": "ε",      "min": 0.1,  "max": 1.3, "step": 0.05, "value": 0.6}
  ],
  "overlays": [
    {"kind": "hbar",  "y": "f(x0)", "half": "eps", "color": "#f0a53a", "label": "ε 带"},
    {"kind": "vband", "x": "x0",    "half": "d",   "color": "#6aa3d5"}
  ],
  "points": [
    {"x": "x0",   "y": "f(x0)",   "label": "A", "color": "#c2582a"},
    {"x": "x0+d", "y": "f(x0+d)", "label": "B", "color": "#1f8a63"}
  ],
  "segments": [
    {"x1": "x0", "y1": "f(x0)", "x2": "x0+d", "y2": "f(x0+d)", "color": "#c2582a", "dash": [4, 3]}
  ],
  "readout": [
    {"label": "|f(A)−f(B)|", "expr": "abs(f(x0+d)-f(x0))", "digits": 3},
    {"label": "ε", "expr": "eps", "digits": 2}
  ],
  "hint": "把 δ 固定在 0.06，慢慢移动 x₀ 到靠近 0：|f(A)−f(B)| 会冲破 ε。"
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `expr` | ✅ | 主函数表达式 |
| `xrange` / `yrange` | ✅ | 视野范围 `[min, max]`；**务必保证曲线主体在视野内** |
| `ratio` | | 画布高宽比，默认 `0.52` |
| `sliders` | | `{name,label,min,max,step,value}`；**最多 3 个**，多了学生调不过来（`matrix2` / `vectors2` 因结构需要可到 4 个，见 §五、§六） |
| `overlays` | | `hbar`＝水平 ε 带（`y` 中心、`half` 半宽）；`vband`＝垂直 δ 条（`x` 中心、`half` 半宽） |
| `points` | | 曲线上的标记点 |
| `segments` | | 两点连线（割线/切线弦），`dash` 可选 |
| `readout` | | 实时数值显示；`digits` 控制小数位 |
| `hint` | ✅ | **操作引导语**：拖什么、看什么、先预测什么 |

### 现成配方

| 概念 | expr / 滑块 | 叠加层 |
|---|---|---|
| 数列→函数极限（ε–δ） | `expr` 任意；滑块 `x0`、`d`、`eps` | hbar + vband + 点 A、B |
| 导数（割线→切线） | 滑块 `a`、`h`；点 A=`(a,f(a))`、B=`(a+h,f(a+h))`；segment A–B | 另加一条切线用 `segments` 近似 |
| 中值定理 | 滑块 `a`、`b`；`segments` 连 A、B | — |
| 单调性 / 凹凸 | 滑块 `a`；点 `(a, f(a))` | hbar 显示函数值比较 |

---

## 三、`seq`：数列 ε–N

```interactive
{
  "type": "seq",
  "expr": "1/n",
  "nrange": [1, 60],
  "target": 0,
  "sliders": [{"name": "eps", "label": "ε", "min": 0.01, "max": 0.5, "step": 0.01, "value": 0.1}],
  "hint": "拖动 ε，看 N 怎么变：ε 越小，N 越大——这就是「任意小」。"
}
```

| 字段 | 说明 |
|---|---|
| `expr` | 通项表达式，自变量是 **`n`** |
| `nrange` | 画到第几项 `[n1, n2]`，建议 `n2 ≥ 40` |
| `target` | 极限值 a（画水平虚线 + ε 带中心） |
| `sliders` | **必须有一个名为 `eps`** 的滑块 |

自动计算并标注 **N**（此后所有项都落入 ε 带），红点＝带外的项，绿点＝带内的项。

---

## 四、`riemann`：定积分 / 黎曼和

```interactive
{
  "type": "riemann",
  "expr": "x*x",
  "xrange": [0, 1],
  "yrange": [0, 1.2],
  "nslider": {"min": 1, "max": 60, "step": 1, "value": 8, "label": "n（分割份数）"},
  "exact": 0.3333333,
  "hint": "拖 n 从 1 到 60，看 S_n 逼近精确值。"
}
```

`exact` 可选；给了就实时显示误差。

---

## 五、`matrix2`：线性变换 / 行列式 / 秩

```interactive
{
  "type": "matrix2",
  "range": [-3, 3],
  "sliders": [
    {"name": "a", "label": "a", "min": -2, "max": 2, "step": 0.05, "value": 2},
    {"name": "b", "label": "b", "min": -2, "max": 2, "step": 0.05, "value": 0},
    {"name": "c", "label": "c", "min": -2, "max": 2, "step": 0.05, "value": 0},
    {"name": "d", "label": "d", "min": -2, "max": 2, "step": 0.05, "value": 1.5}
  ],
  "hint": "拖到 ad−bc=0（例如让 a=0 且 c=0）：单位正方形被压扁成一条线段，秩从 2 掉到 1。"
}
```

矩阵为 $\begin{pmatrix} a & b \\ c & d \end{pmatrix}$。滑块**必须命名为 `a` `b` `c` `d`**。
自动显示 `det`、`秩`、像的形状（整个平面 / 一条直线 / 一个点）。

---

## 六、`vectors2`：线性相关 / 张成空间

```interactive
{
  "type": "vectors2",
  "range": [-3, 3],
  "sliders": [
    {"name": "u1", "label": "u₁", "min": -3, "max": 3, "step": 0.1, "value": 2},
    {"name": "u2", "label": "u₂", "min": -3, "max": 3, "step": 0.1, "value": 1},
    {"name": "v1", "label": "v₁", "min": -3, "max": 3, "step": 0.1, "value": -1},
    {"name": "v2", "label": "v₂", "min": -3, "max": 3, "step": 0.1, "value": 2}
  ],
  "hint": "拖到 det(u,v)=0（两向量共线），张成空间就从整个平面塌成一条直线。"
}
```

滑块**必须命名为 `u1` `u2` `v1` `v2`**。自动显示 `det(u,v)`、线性相关/无关、张成空间维数。

---

## 七、`concept-map`：知识图谱（F6 专用）

支持两种写法：**简单行格式**（推荐，手写友好）或 JSON。

```concept-map
concept: 一致连续
course: 数学分析 · 函数连续性
down: 函数, 极限, 连续, 区间
up: 闭区间上连续函数性质（Cantor 定理）, 一致收敛, 可积性
lateral: 连续
note: 从「局部」走向「整体」的第一个范例
```

| 键 | 必填 | 说明 |
|---|---|---|
| `concept` | ✅ | 中心概念 |
| `course` | | 所属课程 · 章节（显示在中心节点上方） |
| `down` | ✅ | **下楼（前置）**：它建立在哪些概念之上；多个用 `,` `，` `、` 分隔 |
| `up` | ✅ | **上楼（后续）**：由它能推出什么；多个同上 |
| `lateral` | | **平移（同类 / 对偶）**：如「连续」（与一致连续对偶） |
| `note` | | 一句话定位（图底部） |

- `down` 节点在左、`up` 在右、`lateral` 在下（双向虚线）。
- 每侧建议 **2–4 个**，总数不超过 9 个，否则图会挤。
- 概念名要**短**（4–10 字），过长会自动缩字号。

---

## 八、`geogebra`：让学生自己在 GeoGebra 里复现

```geogebra
f(x) = sin(1/x)
SetColor(f, 0.18, 0.44, 0.70)
d = Slider(0.005, 0.25, 0.005)
x_0 = Slider(0.03, 0.9, 0.01)
A = (x_0, f(x_0))
B = (x_0 + d, f(x_0 + d))
s = Segment(A, B)
SetColor(s, 0.76, 0.35, 0.17)
eps = Slider(0.1, 1.3, 0.05)
g: y = f(x_0) + eps
h: y = f(x_0) - eps
```

**规则**：
1. **每行一条命令**，学生可逐行粘贴到 GeoGebra 输入栏。
2. 颜色用 **RGB 三数**形式 `SetColor(obj, r, g, b)`（取值 0–1）——最稳，不依赖颜色名支持。
3. 用 `Slider(min, max, increment)` 建滑动条。
4. 装饰性命令（`SetColor` / `SetLineStyle`）放在最后，并提示「若报错可整行删掉，不影响图形」。
5. 指令必须和卡片上的 `interactive` 组件**讲同一件事**（学生能对照着做）。
6. 不确定某命令在你版本里是否可用时，**宁可不写**，只给核心的 `f(x)=...`、`Slider(...)`、取点连线。

---

## 九、写组件的纪律（交付前自查）

- [ ] 组件**服务概念**，不是装饰？图能**回指 F3 的严格式子**吗？
- [ ] 有 `hint` **操作引导语**（拖什么、看什么、先预测什么）吗？
- [ ] 滑块 **≤ 3 个**（`matrix2`/`vectors2` 因结构需要可到 4 个）？
- [ ] 视野范围设对了吗？把滑块推到端点时曲线还在画面里吗？
- [ ] 表达式**乘号写全**了吗（`2*x` 不是 `2x`）？变量名都在 `sliders` 里吗？
- [ ] `geogebra` 指令与 `interactive` 组件一致吗？
- [ ] `concept-map` 的 `down`/`up` 是否**指明了方向**（谁推出谁），而不是只列名字？
- [ ] 跑过 `scripts/check_card.py` 和 `node scripts/smoke_test_widgets.mjs` 吗？
