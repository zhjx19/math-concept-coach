# ============================================================================
# demo.tape —— 终端流水线演示（vhs 录制脚本）
#
# 录的是什么
#   把一张 Markdown 概念卡渲染成「离线单文件可交互 HTML」这条真实命令行。
#   演示 GIF 托管在 gh-pages 分支（主分支保持 SkillHub 干净），README 经 Pages 域名引用；
#   需要时由 scripts/make_demo_gif.py 重新生成。
#
# 怎么录
#   在技能根目录执行：vhs assets/demo.tape
#   产出 assets/demo-cli.gif
#
# 诚实声明
#   作者机器没有 vhs（无 winget/scoop/choco/go，GitHub 亦不可达），因此
#   assets/demo-cli.gif 未随包提供——本文件是可复现的录制配方，不是摆拍脚本：
#   下面四条命令均在 Windows + Git Bash + Python 3.13 上实跑通过，输出见注释。
#
# 依赖
#   vhs    https://github.com/charmbracelet/vhs
#   python 3.x（脚本自带 MathML 转换，不需要 Pillow / Node）
#   pandoc 由 scripts/md2card.py 自动探测，找不到会明确报错
# ============================================================================

Output assets/demo-cli.gif

Set Shell "bash"
Set FontSize 15
Set Width 1100
Set Height 620
Set Padding 20
Set Margin 0
Set Theme "Catppuccin Mocha"
Set BorderRadius 8
Set TypingSpeed 40ms
Set CursorBlink false

Sleep 500ms

# ① 一条命令：Markdown 概念卡 → 离线单文件 HTML
#    实测输出：
#      [OK] 概念卡已生成：out\card.html
#           交互组件 1 个 | 知识图谱 1 张 | GeoGebra 指令块 1 个 | 折叠面板 6 个
#           公式(MathML) 133 处 | 表格 5 个 | 单文件离线可交互
Type "python scripts/md2card.py examples/数列极限-概念卡.md -o out/card.html"
Enter
Sleep 3500ms

# ② 看看产物多大（实测 94K）
Type "ls -lh out/card.html"
Enter
Sleep 1800ms

# ③ 卡里到底塞了什么（实测 1 个自绘交互组件）
Type "grep -c 'data-wb=' out/card.html"
Enter
Sleep 1500ms

# ④ 收尾
Type "rm -rf out"
Enter
Sleep 900ms
