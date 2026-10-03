# 123ui5.0 — Hermes Mono × Indigo/Violet

`123ui5.0` 是 123mshub 的可复用 UI 令牌和组件行为契约。它把 Hermes Agent 的 Mono Clean（grayscale-minimal and focused）作为结构与状态基线，用 `#6366F1`（Indigo）和 `#7C3AED`（Violet）作为品牌强调种子。

## 直接调用

Python/Qt 文件：

```python
from mshub.ui5 import UI5_VERSION, theme_tokens, action_gradient

tokens = theme_tokens("dark")
gradient = action_gradient("light")
```

Web/Vite 文件：

```js
import { UI5_VERSION, themeTokens, actionGradient } from './ui5/tokens.js'

const tokens = themeTokens('dark')
const gradient = actionGradient('light')
```

需要在其他项目复用时，复制 `tokens.json`、`tokens.css`、`theme.py` 或 `theme.mjs` 即可；这些导出文件不依赖 123mshub 的业务 API。

## 核心令牌

| 语义 | 亮色 | 暗色 | 作用 |
| --- | --- | --- | --- |
| `action` | `#6366F1` | `#6366F1` | 主要动作、链接和图谱主色 |
| `accent` | `#7C3AED` | `#A78BFA` | 次级强调、标签和焦点补色 |
| `selection` | `#E9E7FF` | `#312E81` | 列表整行选中填充 |
| `action_gradient` | `#6366F1 → #7C3AED` | `#6366F1 → #7C3AED` | Agent/品牌主入口短渐变 |
| `bg` | `#FFFFFF` | `#0E0E0E` | 页面画布 |
| `surface` | `#FFFFFF` | `#141414` | 卡片、面板和输入表面 |

## 行为契约

- 容器焦点和编辑控件用边框；列表行选中用填充；两者不叠加；
- 任务面板默认收起，首个任务进入时展开为四行高度；任务标题、活动图标和箭头不自带第二层背景；
- 亮暗模式共享字号、间距和 120/180/220/100ms 的 Hermes 过渡时长；
- `prefers-reduced-motion` 时关闭非必要动画；
- `error`、`ok`、`warning` 是独立语义颜色，不从品牌渐变强行推导。

## 文件

- `tokens.json`：三层令牌源；
- `tokens.css`：亮暗模式 CSS 自定义属性；
- `theme.py`：无第三方依赖的 Python 读取与派生辅助；
- `theme.mjs`：无框架依赖的 JavaScript 读取与派生辅助；
- `components.md`：组件和状态使用规则；
- `motion.md`：动效与无障碍规则；
- `CONSUMPTION.md`：从其他文件直接调用的迁移说明。
