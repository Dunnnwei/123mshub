# 123 MSHub Native v1.7.0 — MASTER

状态：用户已确认 frontend-design 预览方向；本文件是此次原生 UI 实现的唯一全局设计依据。
目标版本：1.7.0。保留 native/v1.6.1 发布包供回退。

## 研究与规则优先级

1. 用户确认的 `uinew/mshub-ui-redesign.html` 视觉方向优先，页面/操作文案来源于 v1.6.1 原生源码。
2. Ui/UX Pro Max 已执行 `knowledge management desktop productivity --design-system` 和一次聚焦重试 `developer tools dashboard --design-system`，均含营销落地页 Pattern；不将这些不适合桌面的 Pattern、自动颜色/字体或滚动入场模板作为规则保存。以下为经过产品和平台校准的设计系统。
3. 已验证数据库结果：`keyboard focus visible --domain ux` → Focus States / Focus Not Obscured；`dark text contrast --domain ux` → Contrast Readability / Color Contrast。采用 4.5:1 正常文字对比度、可见焦点、焦点不被固定区域遮挡。
4. 已读 quick-reference 的 Accessibility、Interaction、Performance 和 pro-rules。采用 4/8 间距、语义原生控件、透明度克制、状态与文字冗余、可中断动效、长文本截断后可访问全文。移动端 375px/iOS 安全区规则不冒充 Windows 原生要求。
5. 实际技术栈为 PySide6 Widgets + 一个本地 QtWebEngine/QWebChannel 图谱岛；skill 没有 PySide6 专用栈，不能伪称 WPF/WinUI 建议就是 Qt 文档。保留无 TCP、服务层/存储兼容、异步任务、非模态编辑窗口。

## 用户、任务与内容

产品类型：本地 Agent 的共享记忆与技能资产管理工具。主要用户是使用多个 Agent 的个人开发者、创作者与知识维护者；安全审核和首次配置是辅助任务。

主要路径：搜索记忆 → 查看/编辑 → 保存；投递箱 → 原文审核 → 收编；查找技能 → 查看来源与说明 → 检查/更新/复制提示词；选择检查路线 → 审阅完整报告；仓库配置 → 导入扫描 → 确认导入。

内容特点：中英文长标题、kebab-case 标识、Markdown、标签和双链、真实来源、状态、日期、Windows 路径。标题和用途得到最大宽度；类型、来源和风险是辅助判断；数量和状态必须来自真实数据。

保持五个页面 key：memory / graph / skills / security / settings。保留全部编辑、投递、日报、索引、添加、信息编辑、检查报告、导入与关于入口。设计规范页只属于评审文档。

## 视觉方向

共享大脑的安静操作台。保持预览里的细边界、低饱和背景、蓝色焦点、清晰列表与表格、紧凑侧栏、可折叠任务区。采用一个标题和一个主要操作；避免高饱和整屏、粗重网格、重复大卡片、纯装饰英语眉题和文本发光。

原生 UI 使用实体表面和细边框表达层次，不强行用 QSS 模仿 CSS backdrop-filter。图谱浮层可使用本地 Chromium 的轻微玻璃模糊。

## 颜色 tokens

权威机器值放在 `src/mshub/native/design_tokens.json`，原生 QSS 读取；图谱通过 WebChannel 同步同套值。

| 语义 | Light | Dark |
| --- | --- | --- |
| bg | #F2F4F8 | #0B0E14 |
| sidebar | #F7F8FA | #0F1219 |
| surface | #FFFFFF | #141926 |
| raised | #FFFFFF | #1B2232 |
| inset | #F3F5F8 | #1B2232 |
| ink | #171B23 | #E9ECF4 |
| muted | #4E5766 | #A7B0C2 |
| faint（仍可阅读的辅助文字） | #606A7A | #9AA6BC |
| line（非交互分割线） | #E2E6EE | #303A4D |
| strong（控件边界） | #828DA0 | #73839E |
| action / on_action | #0156FC / #FFFFFF | #0156FC / #FFFFFF |
| accent（链接/焦点） | #0148D2 | #8DB5FF |
| selection | #E7F0FF | #172E57 |
| error / error_soft | #AF2424 / #FBEAEA | #FFAAA3 / #3D242A |
| ok / ok_soft | #116B3A / #E5F4EB | #58DFAC / #17392F |
| warning / warning_soft | #88420A / #FBF0DD | #F5C46A / #40341F |
| user | #7144B8 | #B8A0FC |
| project | #0148D2 | #8DB5FF |
| reference | #006F72 | #6ED7D0 |
| feedback | #97500A | #F5BD74 |

普通文字与对应表面目标 ≥4.5:1；可操作边界/焦点 ≥3:1。禁用状态仍用原生 disabled 语义，不能只变灰。safe/unchecked/warning/error 等原始状态保留，并用文字和颜色共同表达；人工信任不能伪装成自动安全结论。

## 字体、字号与密度

- 正文：本地 `Dream Han Sans CN`，缺失回退 `Segoe UI` / Microsoft YaHei。标题仍同一家族。按既有 W1/W15/W20/W27 本地注册机制加载，不从公网下载字体。
- Qt 正文 14px/400，辅助 12px/400，导航 14px/600，页面标题 24px/700，数值 24px/650，品牌 20px/700。
- 等宽 `Cascadia Mono` 只用于正文编辑器、路径、版本和代码。列表标题不全部强制等宽。
- 页面边距正常 28px，紧凑 16px；间距 scale = 4 / 8 / 12 / 16 / 24 / 32。
- 控件最小高度 36px（桌面鼠标），图标按钮至少 32px，复选框点击区域至少 24px；列表 64px 两行，技能/安全表格 52px，任务行 36px。
- 圆角：按钮/输入 8px，导航 9px，内容框 12px，浮层 14px。边框 1px，焦点 2px，边界尺寸稳定。

## 布局和响应式

- 标准 1440×900 / 1280×820：236px 侧栏；独立标题/动作行、搜索/筛选行、可滚动内容、底部必要反馈。
- 紧凑 960×640 / 1024×768：侧栏 176px，主边距 16px，页头动作换行，统计和批量按钮自动换行；按钮文字不缩到不可读。设置表单可纵向滚动，保存按钮固定在滚动区外。
- 大屏 1920×1080：主要列表获得更多宽度，名称/说明同比扩展，元信息列宽受控；不放大字体填空。
- 125% / 150% DPI 使用 Qt logical pixels，字体与矢量图标随 DPI 缩放。以有效逻辑分辨率判断布局，目标支持至少 960×640。
- 记忆行：复选框 + 左侧标题/描述 + 右侧类型/来源/日期，长字符串 ellipsis + tooltip + accessibleName 保留全文；无最小宽度挤爆布局。
- 技能表：名称不少于 190px，说明 stretch；紧凑时标签与更新时间收起到详情，来源、安全、打开详情始终可见。隐藏列不删除数据。
- 安全表：名称/来源/状态/最近检查/摘要按任务权重分配；完整报告有明确按钮和 Enter，双击仍保留。
- 无任务时任务区显示一句空态；有任务时可折叠展开，不给空白表格预留半屏。任务名称、阶段和进度可读。

## 组件状态与交互

所有按钮/输入有 default / hover / pressed / focus / disabled；选择状态有文本和高亮边界；错误有就近说明；长任务即时给状态并放入后台任务区；成功明确提示完成。

- 列表点击用于选择；Enter / 双击 / 编辑选中打开详情。Space 选中条目做批量处理。快捷键 Ctrl+F 聚焦当前页搜索，Ctrl+1…5 导航，编辑窗口 Ctrl+S 保存。
- 编辑窗口先显示框架和“正在加载…”再异步填入；不要打开旧内容或在读取中允许保存。保留未保存确认及独立可调整窗口。
- 批量操作只在勾选后显示，并显示真实已选数；危险操作保留确认；本地技能的更新禁用并解释原因。
- 安全路线 A / B 显式选择，网络 AI 不做隐含默认；检查报告保留完整 findings 和原始状态。
- 表单标签与输入控件关联，密码允许粘贴；保存前是草稿；错误不清空已输入值。
- 图谱保留搜索、类型、孤儿、标签边、尺寸、阈值和力参数；给键盘可达的节点列表作为 canvas 等价入口，点击/Enter 打开条目；缩放/复位有按钮替代鼠标操作。

## 动效

hover 120ms / 状态淡入 180ms / 浮层 220ms，按任务语义选择。Qt 控件优先使用即时原生状态，无导航加载动画阻塞输入。图谱保留现有可关闭呼吸、交互暂停恢复、大图保护及 reduced-motion；禁止增加装饰性持续动效。减少动态效果时取消 CSS transitions。

## 实施范围与验收

1. 先读取本 MASTER，再实现 tokens、公共控件和壳层；之后记忆、技能、安全、设置、子窗口与图谱同步。
2. 保留业务服务函数、目录与存储协议、五个路由 key、中文文案与翻译切换；不迁移技术栈、不增加 TCP 服务。
3. 验证新/编辑/软删除、异步任务、主题、语言、筛选、批量显隐、详情键盘、设置草稿、图谱资源/WebChannel。测试以行为为目标。
4. 输出对比度报告；用隔离示例数据捕获原生截图（标注隔离样本）；覆盖明暗主题、960×640 / 1280×820 / 1920×1080 与代表性 DPI。截图不代表用户真实数据端到端验收。
5. 完整已有 pytest + graph JS tests + native graph build 通过后打包 native-v1.7.0，做冻结 smoke，重新生成 SHA256；保留供应商/真实仓库/读屏器验收边界。
