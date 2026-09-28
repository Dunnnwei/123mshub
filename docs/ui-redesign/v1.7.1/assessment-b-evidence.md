# Assessment B：Impeccable detector 证据

本报告只记录 v1.7.0 当前 `web/native-graph` markup 的检测证据与 native 宿主边界，不修改源码、版本号或发布物，也未读取 Assessment A。

## 检测运行记录

- 命令：`C:\Users\Administrator\.codex\skills\impeccable\scripts\impeccable.cmd detect --json web/native-graph`
- 工作目录：`D:\DiskWork\PJ\123mshub`
- detector exit code：`0`
- 输入范围：`web/native-graph`；本次只传 markup 目录，未单独传 `style.css`。
- 原始输出：[`v1.7.0-before-detect.json`](/D:/DiskWork/PJ/123mshub/docs/ui-redesign/v1.7.1/v1.7.0-before-detect.json)
- 原始 JSON SHA-256：`0568E47F18A3158E859C52A6C17BEFF39EF496BE18EA6978C48B1D7DF42B7709`

### 计数

| 项目 | 数量 |
|---|---:|
| 总 findings | 4 |
| 不重复 rule / antipattern | 2 |
| `advisory` | 3 |
| `warning` | 1 |
| `slop` 类别 | 4 |
| detector 报告的文件位置 | 4 次，均为 `web/native-graph/index.html`，`line: 0` |

### 规则与位置

1. `gpt-thin-border-wide-shadow` / Hairline border with wide shadow：3 次，均为 `advisory`。
   - detector snippet：`1px border + 72px shadow blur`
   - detector snippet：`1px border + 34px shadow blur`
   - detector snippet：`1px border + 30px shadow blur`
   - detector location：`D:\DiskWork\PJ\123mshub\web\native-graph\index.html`, `line: 0`（检测器未提供精确 CSS 行号）。
   - 对应的可定位实现位于 [`style.css`](/D:/DiskWork/PJ/123mshub/web/native-graph/style.css)：`.graph-settings` 使用 `border:1px solid` 与 `box-shadow:0 24px 72px`（第 41 行）；`.tooltip` 使用 `border:1px solid` 与 `box-shadow:0 14px 34px`（第 32 行）；`.node-browser` 使用 `border:1px solid` 与 `box-shadow:0 12px 30px`（第 43 行）。这些是 detector 对 markup 入口关联样式的概括位置，不能把 `line: 0` 当作源码行号。
2. `kicker-above-heading` / Kicker / eyebrow label above heading：1 次，`warning`。
   - detector snippet：`kicker "OBSIDIAN GRAPH VIEW" above h1 "记忆图示"`
   - detector location：`D:\DiskWork\PJ\123mshub\web\native-graph\index.html`, `line: 0`。
   - 可定位 markup：[`index.html`](/D:/DiskWork/PJ/123mshub/web/native-graph/index.html) 第 14 行 `.eyebrow`，第 15 行 `h1`。

## 模板化信号与真假阳性判断

`kicker-above-heading` 是一个真实命中的模板化信号：页面在主标题上方放置了独立、全大写、字距拉开的 `OBSIDIAN GRAPH VIEW`。这符合 detector 对“tiny tracked uppercase label directly above heading”的定义。它不是无关文本误报；是否删除属于设计决策，本报告不改动它。

三条 `gpt-thin-border-wide-shadow` 是结构上真实存在的组合，但更接近“有条件的真阳性”而非自动证明的视觉缺陷。图谱设置、tooltip 与键盘节点浏览器都使用 1px 边框，同时使用不同强度的阴影；这是玻璃面板与浮层的有意层级表达，且在浅/深主题中共享 token。detector 的 `advisory` 级别正确表示它是模板化风险提示，不能仅凭静态规则断言必须删除边框或阴影。它也没有捕捉到这些层叠上下文、透明度、backdrop blur、z-index 或实际背景对感知层级的影响。

## native Qt / 布局 / a11y 证据边界

- native graph 宿主是 [`graph_view.py`](/D:/DiskWork/PJ/123mshub/src/mshub/native/views/graph_view.py)：运行环境使用 `QWebEngineView` 加载本地 `file://` graph island；offscreen 测试环境明确退化为 QLabel，因为 QtWebEngine 无法在 offscreen 平台创建 Chromium surface。因而静态 detector 不能代表 QWebEngine 实机合成结果。
- Qt 外壳的尺寸约束、侧栏和页面布局由 [`main_window.py`](/D:/DiskWork/PJ/123mshub/src/mshub/native/main_window.py) 控制：窗口最小尺寸为 960×640，侧栏在窄窗口固定为 176 logical px、宽窗口为 236 logical px；图谱页面本身以 stacked page 嵌入，不能从 detector JSON 推断 DPI、窗口缩放、字体回退、QWebEngine viewport 或滚动/裁切表现。
- markup 已提供原生可访问性线索：图谱 surface 有 `aria-label`，加载消息有 `role=status` 与 `aria-live=polite`，搜索、清除、缩放和节点打开按钮有 `aria-label`，并提供节点下拉选择作为 canvas 的键盘等价入口；CSS 有 `:focus-visible` 与 `prefers-reduced-motion`。这些只能由源码核对确认，detector 本次没有输出 a11y 规则结果。
- 仍存在无法由本次 detector 证明的 native 限制：Sigma canvas 的节点拖拽/悬停关系、屏幕阅读器对图形语义的可读性、Qt 与 Chromium 间焦点转移、125%/150% DPI 下的真实截切、GPU 大图帧率，以及真实读屏器/键盘巡检。已有 QA 文档把这些列为真实环境待核项目。

## 浏览器与 overlay 评估状态

本 Assessment B **跳过 live browser 和 overlay pass**。原因是任务指定的证据动作是对 `web/native-graph` markup 运行一次 Impeccable JSON detector，并补充 current v1.7.0 native 源码/已有截图的限制；detector 本身不启动浏览器，也不产生 overlay 坐标。已有 v1.7.0 截图是离线/真实 Windows smoke 的静态证据，能够说明已有采样范围，但不能替代本次未执行的交互式浏览器检查。没有把浏览器未运行或 overlay 未生成伪装成已验证结果。

## 证据结论范围

本报告支持的结论只有：detector 成功运行，返回 4 条（2 个规则）的模板化信号，并能在当前 markup/CSS 中找到对应实现；Qt/native、DPI、canvas、读屏器和真实用户仓库行为需要独立的实机或专项检查。所有 finding 保持为 detector 原始结果，未因本报告而修改。
