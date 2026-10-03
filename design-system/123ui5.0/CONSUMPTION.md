# 123ui5.0 调用说明

## Python

将 `tokens.json` 与 `theme.py` 放在项目包中：

```python
from theme import theme_tokens, action_gradient

primary = theme_tokens("light")["action"]
agent_background = action_gradient("dark")
```

在 123mshub 内直接使用：

```python
from mshub.ui5 import theme_tokens
```

## Web

直接引入 `tokens.css`，或使用 `theme.mjs` 的 `themeTokens(mode)` 生成 CSS 变量。组件只引用 semantic token，不把 `#6366F1` 或 `#7C3AED` 散落到业务文件。

## 迁移规则

从 Mono 灰阶迁移时，只替换 `action`、`accent`、`selection`、图谱类型和 Agent 入口；保留 `bg`、`surface`、字号、间距、圆角、焦点逻辑和业务状态。这样可以把 123ui5.0 应用到新页面而不改变功能布局。
