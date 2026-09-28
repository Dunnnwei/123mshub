# 123 MSHub Native v1.7.1 — Bolder Delta

状态：v1.7.0 评估已完成；本文件是在 `design-system/123mshub-native-v1.7.0/MASTER.md` 之上的定向调整，不替换产品功能、路由、存储协议或原生技术栈。

## 评估基线

- 产品类型：本地 Agent 共享记忆与技能资产管理工具。
- 工作模式：Operate / data-heavy desktop product。
- 目标用户：多 Agent 开发者、创作者、知识维护者；安全审核和首次配置是辅助任务。
- 评估证据：[critique-summary.md](../../docs/ui-redesign/v1.7.1/critique-summary.md)、[Assessment A](../../docs/ui-redesign/v1.7.1/assessment-a-design.md)、[Assessment B](../../docs/ui-redesign/v1.7.1/assessment-b-evidence.md)。
- 既有系统：皇家蓝、低饱和 light/dark、Dream Han Sans CN、Cascadia Mono、4/8 间距、原生 Qt 控件、单一本地图谱 Web 岛。

## Bolder 目标

让页面更有把握，而不是更吵。每页只制造一个视觉峰值，使用 v1.7.0 已拥有的颜色、字体和圆角语言，强化已有产品语义，不引入新的视觉世界。

1. **Typography contrast**：页面标题 30px/760，section 18px/700，正文 14px/500，辅助 13px/450，列表标题 14px/650，元信息 12px/550；数值摘要 15px/700。标题、主数值和风险状态先被看到。
2. **Rhythm**：页头 20px 内部节奏，摘要与工具栏 12–16px，主要内容面获得连续的 16–20px 呼吸，收尾动作与内容面保持 12px 距离；紧凑窗口自动降为 12px/16px。
3. **Hierarchy**：primary 动作使用现有 `action` 蓝色；secondary 使用实体 surface；危险动作使用既有 error token；统计是摘要，不伪装成 7 个同权 CTA。
4. **Product language**：Native 页面可保留少量品牌眉题，但图谱不再借用 `OBSIDIAN GRAPH VIEW`；使用“共享记忆关系图 / 关系探索”表达产品任务。内部状态用中文短语和颜色共同表达。
5. **Float discipline**：图谱浮层继续使用细边界，但阴影从扩散装饰改为更克制的层级提示；不把 detector 的 advisory 当作机械删除边框的命令。

## 组件规则

- `QLabel#title`：30px/760；唯一页面主标题。
- `QLabel#sectionTitle`：18px/700；详情、设置分组、结果摘要。
- `QLabel#eyebrow`：12px/800；仅用于必要的产品上下文，不能写成通用模板眉题。
- `QLabel#muted`：13px/450；只承担解释，不与标题竞争。
- `QLabel#helper` / `#faint`：12px/450；用于低频补充信息，仍必须达到设计系统对比度。
- `QPushButton#primary`：36px 最小高度、700 字重；每页默认一个主要行动。
- `QPushButton#stat`：40px 高度、13px/650、轻量实体表面；当前筛选项才使用 accent 边界。
- Native memory row：标题 14px/650，说明 12px/450，元信息 12px/550；不再让 11px 元信息承载主要判断。
- Graph h1：32px/760；stats strong：30px/700；settings h2：20px/700；panel shadows 控制在 18–36px blur。

## 页面节奏

- 记忆：页头 → 统计摘要 → 搜索/筛选 → 记忆内容面 → 整理收尾。主按钮是“新建记忆”或根据仓库状态切换的当前任务，低频整理保留但弱化。
- 技能：页头 → 来源/状态筛选 → 资产表 → 检查/报告 → 详情。检查是主行动，信任/更新/软删除进入危险操作组。
- 安全：路线选择 → 解释当前路线 → 结果摘要 → 报告/恢复动作。`未检查 / 已通过 / 需复核 / 存在风险` 与颜色同时出现。
- 设置：页头 → 分组 tab → 可滚动表单 → 草稿/已保存状态 → 固定保存。字段不改变业务文案和协议。
- 图谱：共享记忆关系图 → 关系/查找工具 → Canvas → 节点打开/复位；高级 Force 参数继续可用但不承担首要注意力。

## 可访问性与证据边界

- 保留 native StrongFocus、2px focus 边界、label/buddy、AccessibleTextRole、aria-label、`role=status`/`aria-live=polite`、reduced-motion 和节点下拉等价入口。
- 不把颜色作为唯一状态表达；风险、检查、完成和失败必须有文字。
- 保留 Route A 离线 / Route B AI 的显式选择，不做隐含网络默认。
- v1.7.1 必须重新做 full pytest、web check/test/build、graph bundle build、PyInstaller、SHA256、Windows real smoke；截图要注明隔离样本或真实仓库，不把单一 smoke 当作完整用户验收。
