# 动效契约

沿用 Hermes Mono Clean 的克制节奏：hover 120ms、普通淡入 180ms、面板 220ms、行状态 100ms，统一使用 `cubic-bezier(.22, 1, .36, 1)`。动效只表达状态变化，不负责制造层级。

`prefers-reduced-motion: reduce` 时移除渐变过渡、图谱漂浮和装饰性缩放，保留点击反馈和状态可见性。
