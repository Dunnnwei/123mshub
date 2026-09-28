# 123 MSHub v1.7.1 — Impeccable 综合评估

日期：2026-09-25
基线：native/v1.7.0
方法：dual-agent（Assessment A 设计评审 + Assessment B detector/证据评审）

## 两份独立评估

- [Assessment A：独立设计评审](assessment-a-design.md)
- [Assessment B：detector 与浏览证据](assessment-b-evidence.md)
- [v1.7.0 detector 原始 JSON](v1.7.0-before-detect.json)

两份评估在汇总前相互隔离。Assessment A 没有读取 detector 输出；Assessment B 没有读取 A 的判断，也没有修改产品源码或版本文件。

## 设计完成度与模板化程度

v1.7.0 的主观设计完成度为 **74/100**。颜色 token、light/dark、原生焦点、异步详情、批量操作和真实业务字段已经形成可靠基线；主要扣分来自跨页面语气未完全收束、动作同权、状态解释和帮助发现不足。

视觉模板化残留约 **38%**。这个数值是设计判断，不是代码覆盖率：产品语义已经进入记忆分类、技能安全、路线 A/B 和图谱关系，但 236px 侧栏、英文眉题、统计 chip、搜索/筛选/描边按钮阵列和统一的“标题 + 描述 + 动作”骨架仍可直接迁移到一般 CRUD 或后台 Dashboard。

## 汇总健康分

Assessment A 按 Impeccable 的 Nielsen 十项启发式完成全量评分：**27/40**，属于“中等偏上，基础可靠但需要继续削弱认知负荷”的区间。

| 启发式 | 分数 | 汇总判断 |
|---|---:|---|
| 系统状态可见性 | 3/4 | 异步、后台任务、状态栏存在，但成功/失败总结权重偏低 |
| 系统与现实世界匹配 | 3/4 | 业务概念真实，英文/内部术语解释不足 |
| 用户控制与自由 | 3/4 | 编辑保护、软删除和复位好，恢复/重试路径不完整 |
| 一致性与标准 | 3/4 | Native token 已统一，弹窗和 Web 岛语气仍有断层 |
| 错误预防 | 3/4 | 路线选择、冲突检查和危险确认可靠，风险动作同权 |
| 识别而非回忆 | 3/4 | 列表和 tooltip 有帮助，快捷键和状态词典不可发现 |
| 灵活性与效率 | 3/4 | 快捷键、批量和筛选已存在，缺少快捷键入口/快速打开 |
| 审美与极简 | 2/4 | 蓝色和细边界稳定，但控件阵列稀释了主路径 |
| 错误诊断与恢复 | 2/4 | 有状态提示，缺少就地原因、重试和恢复闭环 |
| 帮助与文档 | 2/4 | placeholder/tooltip 基础可用，没有任务型解释和词典 |

## detector 证据

Assessment B 对 `web/native-graph` markup 执行了真实 `impeccable.cmd detect --json`：

- exit code：0
- findings：4
- 不重复规则：2
- advisory：3
- warning：1
- 位置：均回指 `web/native-graph/index.html` 的 line 0；具体 CSS 实现在 [style.css](../../web/native-graph/style.css)

规则为：

1. `gpt-thin-border-wide-shadow`：3 次，属于有条件的模板化提示。图谱的设置面板、tooltip 和节点浏览器确实同时使用细边框与扩散阴影，但这些浮层有明确层级用途；v1.7.1 会收紧阴影而不是机械删除边界。
2. `kicker-above-heading`：1 次，命中 `OBSIDIAN GRAPH VIEW` 全大写眉题。这个 finding 是真实模板化信号，v1.7.1 将改成产品自己的中文上下文，避免从另一个产品借来命名语气。

detector 不覆盖 PySide6 原生布局、Qt 与 Chromium 焦点切换、真实 DPI、Canvas 关系可读性、用户 GPU 帧率、真实 Provider 和读屏器；这些仍按证据边界单独验证。

## 优先问题

### P1 — 动作同权，主路径不突出

记忆页有 7 个统计、3 个页头动作、搜索筛选和 4 个底部整理动作；技能详情又把检查、AI、信任、更新、删除、编辑放在同一层。用户不能快速判断当前推荐动作。

v1.7.1 处理：加重一个明确 primary，降低低频维护动作的视觉重量；统计 chip 改成更清晰的摘要节奏；保留功能和文案，不隐藏真实操作。

### P1 — 字体对比和版式节奏偏保守

页面标题与正文说明之间的差异不够，行内元信息偏小，空列表下方的大面积表面让界面像没有填满的模板。

v1.7.1 处理：使用系统已经拥有的 type scale 放大标题、数值、section 和主要列表标题；辅助信息收紧为明确的 secondary 层；页头、摘要、工具栏、内容面和收尾动作建立更清楚的垂直节奏。

### P1 — 安全流程缺少风险阶梯

路线 A/B、检查、报告、信任、更新和软删除没有明显推荐顺序；`unchecked` 等内部词需要用户自行翻译。

v1.7.1 处理：保留显式路线 A/B 和全部业务动作，强化检查/报告为主路径，并用状态文字和状态色共同表达风险；不把联网 AI 变成默认路线。

### P2 — Native 与图谱 Web 岛的语气断层

图谱使用 `OBSIDIAN GRAPH VIEW`、Filters、Display、Forces 和独立浮层语法，虽然 token 相同，但不像同一个产品。

v1.7.1 处理：改用“共享记忆关系图”语气，中文化设置分组，沿用 Native 页面标题与状态节奏；保留本地 WebChannel 和 Canvas 能力。

### P2 — 设置页分组与版本证据需要收口

仓库、网络、语言、主题和 AI 配置聚集在少量 tab 中；上一版紧凑截图曾出现旧版本标签，影响发布可信度。

v1.7.1 处理：加强 tab 标题和表单节奏，补充草稿/保存状态层级，并重新核对版本标签和截图。

## Persona 红旗

- **Alex（Power User）**：快捷键存在但不可发现；批量栏出现后动作过多；后台任务没有明显重试/原因入口。
- **Jordan（First-Timer）**：英文眉题、`kebab-case`、`unchecked`、`archive/git` 和路线 A/B 缺少就地解释；多个按钮看起来像同级起点。
- **Sam（Accessibility-Dependent User）**：原生 label、focus-visible 和节点下拉是优势；Canvas 关系本身仍没有完整读屏等价，状态不能只靠颜色或短暂 status bar。

## 后续建议

1. 先完成 v1.7.1 Bolder：字体对比、动作权重、版式节奏和风险摘要。
2. 用一次真实安全任务复核“路线选择 → 检查 → 报告 → 信任/删除”的决策阶梯。
3. 对图谱 Web 岛做一次独立的 Native/Chromium 焦点和读屏巡检。
4. 在 125%/150% DPI、960×640、1280×820、1920×1080 和真实大图仓库上重新采集视觉证据。
5. 下一轮再补快捷键面板、状态/风险词典和可关闭的新手下一步卡片。

Questions skipped: 用户已明确指定全量 Impeccable Bolder、字体对比/版式节奏/视觉层级优化和 v1.7.1 迭代范围，因此没有再次请求方向确认。
