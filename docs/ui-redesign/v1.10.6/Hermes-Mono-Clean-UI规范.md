# 123mshub v1.10.6 UI 适配规范

## 目的与边界

v1.10.6 将 123mshub 的现有原生 Qt 窗口和本地图谱 WebEngine 岛适配到本机 Hermes Agent 的 **Mono — Clean grayscale — minimal and focused** 主题。功能、路由、服务调用、仓库读写协议、编辑窗口、任务操作、快捷键和现有页面布局保持不变；本版本只改变视觉令牌、状态表达和与主题直接相关的动效。

主题来源已在 Hermes Agent 源码中核对：

- 源码根目录：`C:\Users\Administrator\AppData\Local\hermes\hermes-agent`
- 共享色板：`apps/shared/src/theme-presets.ts` 的 `THEME_PRESET_PALETTES.mono`
- CLI 交互色板：`hermes_cli/skin_engine.py` 的 `mono` skin
- 桌面主题推导：`apps/desktop/src/themes/context.tsx` 的 `synthLightColors()`、`getBaseColors()` 和 `applyTheme()`
- 主题参数：`apps/desktop/src/themes/presets.ts`、`web/src/themes/presets.ts` 的 `monoTheme`

本规范先于 v1.10.6 产品文件修改建立，所有实现和验收都以它为依据。

## Hermes Mono 的可复现色板

### 暗色模式（Hermes 原值）

| 角色 | 色值 | 123mshub 令牌 |
| --- | --- | --- |
| 最底层画布 | `#0E0E0E` | `bg` |
| 侧栏 | `#0A0A0A` | `sidebar` |
| 卡片 | `#141414` | `surface` |
| 次级底 | `#1E1E1E` | `inset` |
| 浮层 | `#181818` | `raised` |
| 次级层 | `#262626` | `glass` |
| 主文字 | `#EAEAEA` | `ink` |
| 次级文字 | `#C8C8C8` | `muted` |
| 弱文字 | `#808080` | `faint` |
| 结构线 | `#2A2A2A` | `line` |
| 强结构线 / hover | `#363636` | `strong` |
| 主动作 / ring | `#9A9A9A` | `action` / `accent` |
| 动作文字 | `#0E0E0E` | `on_action` |
| 选择背景 | `#505050` | `selection` |
| 错误语义 | `#A84040` | `error` |
| 错误弱底 | `#2A1A1A` | `error_soft` |
| 成功语义 | `#B5B5B5` | `ok` |
| 警告语义 | `#AAAAAA` | `warning` |

Hermes CLI 的 `selection_bg` 是 `#505050`，完成菜单当前项是 `#464646`；原生列表统一采用 `selection` 令牌的实色灰阶，避免在两种主题下因透明度叠加而出现不可读的浅选中态。

### 明亮模式（沿用 Hermes 桌面 `synthLightColors(mono)` 推导）

Mono 主题在共享表中提供暗色基准，Hermes 桌面用 `synthLightColors()` 生成明亮模式。本项目按该函数的 sRGB `mix()` 逐项落地，避免自行发明一套浅色灰阶：

| 角色 | 推导值 | 123mshub 令牌 |
| --- | --- | --- |
| 最底层画布 | `#FFFFFF` | `bg` |
| 侧栏 | `#F5F5F5` | `sidebar` |
| 卡片 | `#FFFFFF` | `surface` |
| 次级底 | `#F9F9F9` | `inset` |
| 浮层 | `#FFFFFF` | `raised` |
| 次级层 | `#F5F5F5` | `glass` |
| 主文字 | `#161616` | `ink` |
| 次级文字 | `#737377` | `muted` |
| 弱文字 | `#808080` | `faint` |
| 结构线 | `#E1E1E3` | `line` |
| 强结构线 / hover | `#C8C8C8` | `strong` |
| 主动作 / ring | `#9A9A9A` | `action` / `accent` |
| 动作文字 | `#161616` | `on_action` |
| 选择背景 | `#D8D8D8` | `selection` |
| 错误语义 | `#B94A3A` | `error` |
| 错误弱底 | `#F5E6E3` | `error_soft` |
| 成功语义 | `#555555` | `ok` |
| 警告语义 | `#666666` | `warning` |

`#D8D8D8` 是列表选择专用的可见灰阶；输入框、编辑窗口和设置选项仍使用 `#9A9A9A` 的边框高亮，保持 Hermes 的“结构边框表达焦点、填充表达行选择”分工。

## 视觉和交互规则

1. **灰阶优先。** 删除原有蓝紫渐变、彩色分类点和彩色星点。错误/成功/警告只保留低饱和语义灰或 Hermes Mono 已定义的暗红；不改变语义和可读性。
2. **几何采用 Mono 的零圆角倾向。** Hermes Web `monoTheme` 的 `layout.radius` 为 `0`。123mshub 保留原有页面尺寸、分栏、列表行高、任务面板高度和弹窗尺寸，但卡片、按钮、标签、输入框、表格和浮层统一使用 0px 圆角；原生滚动条把手保留 2px 作为可操作性例外。
3. **去掉装饰性的分层底色。** 后台任务标题、左侧动态图标、右侧箭头都为透明背景；任务面板本身也不添加新的色块。页面边界通过单像素结构线和空间关系表达。
4. **统一选择语言。** 记忆、技能和安全列表行使用整行灰色选择背景；列表控件自身不绘制 focus 边框。设置选项、编辑窗口、输入框和组合框仍使用 2px `accent` 边框焦点。后台任务箭头获得焦点时不显示边框。
5. **搜索图标光学居中。** 搜索框左侧图标采用独立透明子控件，位置按实际编辑框高度重算，中心与输入行垂直中心对齐；图标不会影响 clear action 或点击区域。
6. **任务状态。** 后台任务默认收起；第一条任务从空列表出现时自动展开到现有的四行任务高度，用户主动收起后不因刷新再次打开。任务行高度、操作、重试、详情和清除功能保持现有实现。
7. **动效克制。** 采用 Hermes 的状态动效节奏：hover/颜色 100–120ms，普通淡入 180ms，面板 220ms；只过渡具体属性，不使用 `transition: all`。按钮按下只提供轻微 `translateY(1px)`，不引入高频弹跳。尊重 `prefers-reduced-motion`；图谱保留现有闲置微动，但节点、边、标签全部改用灰阶令牌。
8. **字体和排版。** 123mshub 保留 Qt 系统字体和中文回退，字号与当前版页面排版不变；Hermes Mono 的 IBM Plex Sans / IBM Plex Mono 作为优先字体名加入回退栈，在未安装时由 Segoe UI / Microsoft YaHei 接管。列表文字继续使用现有 row/meta 令牌，技能和安全列表不再单独放大。
9. **图谱同步。** `web/native-graph` 只从 Qt bridge 接收主题令牌，画布、工具栏、设置面板、tooltip、图例、节点、边和选中/悬停状态均使用同一灰阶变量。保留 Sigma、ForceAtlas2、QWebChannel、离线 `file://`/`qrc://` 资源和闲置呼吸逻辑。

## 实现映射与验收证据

| 目标 | 实现位置 | 验收方式 |
| --- | --- | --- |
| 两套 Mono 令牌 | `src/mshub/native/design_tokens.json`、`theme.py` fallback | JSON/Fallback 完整性测试；亮暗截图 |
| Qt 组件几何、状态、动效 | `src/mshub/native/theme.py` | light/dark stylesheet token smoke；无渐变/任务透明/焦点规则检查 |
| 列表选中统一 | `src/mshub/native/list_table.py`、memory QSS | delegate 亮暗行选择截图和测试 |
| 搜索图标居中 | `src/mshub/native/ui_icons.py` | Windows 实际字体/尺寸隐藏渲染，图标中心误差 ≤1px |
| 图谱色板同步 | `web/native-graph/style.css`、`graph.js`、`index.html` | bridge palette smoke；节点数、边数、`rafActive`、`floatTime`、帧哈希 |
| 版本与交付 | `pyproject.toml`、`src/mshub/__init__.py`、`web/package.json`、`RELEASE_NOTES.md`、`release/native-v1.10.6/` | PyInstaller EXE smoke、onedir 完整包、ZIP、SHA256、验收记录 |

## 明确不改变的内容

仓库路径与配置协议、记忆/技能/安全数据服务、批量操作、编辑和导入逻辑、AI 任务、后台任务生命周期、图谱数据桥接协议、页面路由、窗口分栏和现有快捷键均不在本版本重构范围内。若视觉适配发现业务行为问题，单独记录，不借主题迭代顺手改变业务逻辑。
