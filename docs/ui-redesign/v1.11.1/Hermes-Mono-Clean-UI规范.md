# 123mshub v1.11.1 / 123ui5.0 UI 规范

## 目的与边界

v1.11.1 保留 Hermes Agent 的 Mono Clean（grayscale-minimal and focused）作为结构、密度、状态和动效基线，只替换品牌强调层。业务功能、页面路由、服务调用、仓库读写协议、编辑窗口、任务操作、快捷键、窗口尺寸和本地图谱资源方式均保持不变。

源码核对路径：

- Hermes：`C:\Users\Administrator\AppData\Local\hermes\hermes-agent\apps\shared\src\theme-presets.ts`；
- Hermes 桌面派生：`apps/desktop/src/themes/context.tsx` 的 `synthLightColors()`、`getBaseColors()` 和 `applyTheme()`；
- 123mshub：`src/mshub/native/theme.py`、`src/mshub/native/design_tokens.json`、`src/mshub/ui5/tokens.json`、`web/src/styles.css`、`web/native-graph/style.css` 和 `web/native-graph/graph.js`。

## 主题种子与派生

| 角色 | 亮色 | 暗色 | 说明 |
| --- | --- | --- | --- |
| Indigo seed | `#6366F1` | `#6366F1` | 主动作、图谱用户类和品牌渐变起点 |
| Violet seed | `#7C3AED` | `#7C3AED` | 次级强调、图谱参考类和品牌渐变终点 |
| `action` | `#6366F1` | `#6366F1` | 普通主要按钮使用单色 |
| `accent` | `#7C3AED` | `#A78BFA` | 焦点、链接和补色强调 |
| `selection` | `#E9E7FF` | `#312E81` | 列表整行选中填充 |
| `action_gradient` | `#6366F1 → #7C3AED` | `#6366F1 → #7C3AED` | 仅 Agent/品牌入口短渐变 |
| 页面底色 | `#FFFFFF` | `#0E0E0E` | 延续 Hermes Mono 表面层级 |
| 卡片表面 | `#FFFFFF` | `#141414` | 延续 Hermes Mono 平面结构 |

Hermes 的实现是一个 seed 驱动多枚 semantic token；错误、成功、警告、正文和表面不直接使用主题色。本版通过 `123ui5.0` 固定派生值，避免业务文件散落硬编码。

## 状态和组件

1. **表面**：卡片、列表、弹出层、任务面板继续使用实色和单像素结构线；不恢复玻璃模糊、阴影或大圆角。
2. **按钮**：普通 `primary` 使用 Indigo 单色；Agent/品牌入口使用 Indigo → Violet 短渐变；hover/pressed 使用 `action_hover`/`action_pressed`。
3. **选择与焦点**：记忆、技能、安全列表整行使用 `selection` 填充；设置、编辑窗口和输入控件使用 `accent` 边框焦点；列表容器和后台任务箭头不叠加焦点边框。
4. **任务面板**：默认收起；首个任务出现时自动展开到四行高度；标题、动态图标、箭头背景透明；已有任务操作和重试逻辑不变。
5. **搜索**：记忆/技能搜索框的放大镜是透明独立前缀控件，按实际编辑框重算垂直中心，误差门槛为 1px。
6. **图谱**：节点使用四级 Indigo/Violet 明度阶梯，边和画布使用低对比度 Mono 结构色；保留 Sigma、ForceAtlas2、QWebChannel 和闲置呼吸动画。
7. **动效**：hover 120ms、fade 180ms、panel 220ms、row 100ms，统一 `cubic-bezier(.22, 1, .36, 1)`；尊重 `prefers-reduced-motion`。

## 令牌调用

Python/Qt：

```python
from mshub.ui5 import theme_tokens, action_gradient

palette = theme_tokens("dark")
agent_background = action_gradient("light")
```

Web/Vite：

```js
import { themeTokens, actionGradient } from './ui5/tokens.js'
```

规范源和导出文件位于 [design-system/123ui5.0](../../../design-system/123ui5.0/MASTER.md)，原生包中的 `design_tokens.json` 是同源兼容镜像。

## 验收边界

- 自动化测试验证令牌一致、主题切换、焦点/选择规则、图谱构建和本地资源；
- 最终 EXE smoke 验证真实 `D:\MSH` 的图谱节点、边、动效和零 TCP 监听；
- 离屏截图用于比较亮暗状态，不代替真实桌面 DPI 和用户验收；未执行项明确标记 `[待核]`。
