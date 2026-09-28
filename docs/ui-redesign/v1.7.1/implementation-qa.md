# 123 MSHub v1.7.1 — Impeccable Bolder implementation QA

日期：2026-09-25  
基线：`native-v1.7.0`  
目标：在保留现有功能、路由、存储协议和真实文案的前提下，用 Impeccable `critique` 结果驱动一次定向 Bolder 调整，形成可审阅的 v1.7.1 原生发布包。

## 交付物

- [MASTER.md](../../../design-system/123mshub-native-v1.7.1/MASTER.md)：v1.7.1 Bolder 设计规则。
- [critique-summary.md](critique-summary.md)：汇总、完成度、模板化程度、优先问题和后续建议。
- [Assessment A](assessment-a-design.md)：独立设计评估，基于源码和 v1.7.0 隔离截图。
- [Assessment B](assessment-b-evidence.md)：独立 detector 与证据评估。
- [v1.7.0 detector JSON](v1.7.0-before-detect.json) 与 [v1.7.1 detector JSON](v1.7.1-after-detect.json)。
- [Windows real-package smoke log](v1.7.1-native-real-smoke.log)：最终 onedir 包在真实仓库上的运行证据。

## 已实现的 Bolder 调整

- 全局原生主题强化标题、section、列表标题、元信息和统计数值的字重与字号；主标题 30px/760，section 18px/700，列表标题 14px/650，元信息 12px/550。
- 页头、摘要、工具栏、内容面和收尾动作建立 12–20px 的垂直节奏；紧凑窗口保留可滚动表单和固定保存入口。
- 每个主要任务面保留一个明确 primary，低频维护动作退到 secondary/danger 层；业务能力、路由、动作和真实文案没有删除。
- 将 Native 与图谱 Web 岛的产品语气收口为“共享记忆关系图”，移除 `OBSIDIAN GRAPH VIEW` 模板眉题，中文化图谱设置分组。
- 安全页把 `unchecked/safe/warning/error` 转成“未检查/已通过/需复核/存在风险”，风险不依赖颜色单独表达；Route A 离线与 Route B AI 的显式选择保留。
- 图谱 tooltip、设置面板和 node browser 的阴影由 72/34/30px 收紧至 36/24px；仍保留浮层边界和层级分离。
- 版本、README、发布脚本、前端 package metadata、测试期望和 release notes 已统一为 1.7.1。

## 自动化验证

以下命令在 v1.7.1 源码上完成并通过：

| 检查 | 结果 |
|---|---|
| `PYTHONPATH=src .venv\\Scripts\\python.exe -m compileall -q src/mshub` | 通过 |
| `PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest -q tests/native` | 19 passed |
| `PYTHONPATH=src .venv\\Scripts\\python.exe -m pytest -q` | 193 passed，2 warnings（Starlette/httpx、anyio deprecation） |
| `npm run check` | 通过 |
| `node --check native-graph/graph.js` | 通过 |
| `npm test` | 7/7 passed |
| `npm run build` | 通过，生产 UI 已复制到 `src/mshub/web` |
| Native graph Vite build | 通过，bundle hash 已更新 |
| `git diff --check` | 通过；仅保留仓库既有 CRLF 提示 |
| `impeccable.cmd detect --json web/native-graph`（v1.7.0） | 4 findings：3 advisory、1 warning、2 unique rules |
| 同一 detector（v1.7.1） | 2 advisory、1 unique rule；kicker warning 已消失 |

## 发布包与真实冒烟

PyInstaller onedir 构建通过，输出目录为 `release/native-v1.7.1/123mshub/`，目录约 359.84 MB。最终 EXE SHA256 为：

`2842818A48029297EACCC9BF8980E4A10F16D384775AB41A98B2F755F81D21E5`

对应的 [SHA256SUMS.txt](../../../release/native-v1.7.1/SHA256SUMS.txt) 与 EXE 内容一致。发布包包含 design tokens 与更新后的 graph bundle；v1.7.0 和 v1.6.1 发布目录仍保留。

最终包在 `D:\MSH` 真实仓库执行 `--smoke-float-stable`：

- `graph-ready=True nodes=58 edges=42`；Canvas 为 902×416。
- WebChannel payload 为 58 个节点、11529 字符。
- `rafActive=true`、`interactionDepth=0`，`floatTime` 从 4450 推进到 11649。
- 两个稳定帧 hash 不同，`float-alive=True`，进程退出码 0。

完整原始行见 [v1.7.1-native-real-smoke.log](v1.7.1-native-real-smoke.log)。

## 视觉与可访问性证据边界

使用 `QT_QPA_PLATFORM=offscreen` 生成了隔离样本，用于检查设计规则是否落到 light、dark 和紧凑设置布局：

- [light offscreen](v1.7.1-native-offscreen-light.png)
- [dark offscreen](v1.7.1-native-offscreen-dark.png)
- [compact settings offscreen](v1.7.1-native-settings-compact.png)

这些样本确认了中文 eyebrow、30px 页面标题、主次按钮对比、统计摘要节奏、侧栏品牌和 1.7.1 版本标记；它们是离屏渲染证据，不冒充真实 Windows 屏幕验收。本轮环境没有可用的原生窗口控制通道，因此没有把未采集的 125%/150% DPI、GPU 真实帧率、读屏器输出或真实 Provider 返回写成已验收。

源码层保留并复核了 StrongFocus、2px focus 边界、label/buddy、AccessibleTextRole、`aria-label`、`role=status`/`aria-live=polite`、reduced-motion 和图谱节点下拉等价入口；风险状态同时显示文字和颜色。下一轮应在真实 Windows 屏幕上补做 DPI、键盘全路径、读屏器、真实安全 Provider 和大图仓库帧率巡检。

## 结论

实现、自动化验证、发布包构建和真实仓库图谱冒烟均已完成，版本已迭代为 **123mshub v1.7.1**。当前剩余项属于环境相关的人工验收，不是本轮实现阻塞。

Questions skipped: 用户已经明确授权使用 Impeccable critique、并行子代理和 Bolder 定向调整，因此没有再次请求方向确认。
