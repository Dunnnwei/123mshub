# Obsidian 图谱视觉基准截图（内部开发参考）

为「记忆图示」重构（sigma.js/WebGL 版）准备的像素级校准基准。**仅作内部视觉校准
参考，不随发布物分发**；截图版权归原作者所有，来源见下表。

校准时只看**图谱画布区域**，忽略截图中的窗口边框、标签栏、文件侧栏等界面外壳。

| 文件 | 内容 | 校准什么 | 来源 |
|---|---|---|---|
| `obsidian-graph-default.png` | 全景默认态：深色背景、灰白节点、无标签、群落自然聚拢 | 布局观感、节点/边的基础色与透明度 | Ryan Himmelwright 博客（Obsidian v0.12.19） |
| `obsidian-graph-hover.png` | 悬停态：选中节点紫色高亮、一度邻居提亮并显示标签、其余节点与边淡出 | 悬停高亮/淡出强度、邻居标签浮现 | MakeUseOf |
| `obsidian-graph-zoom.png` | 带标签视图：节点旁浅灰文字标签、带深色 halo 描边 | 标签字号、颜色、描边与浮现行为 | Linux Handbook |
| `obsidian-graph-settings.png` | local graph + 官方设置面板：Filters（Tags/Links/Existing links only/Orphans）、Display（Text fade threshold/Node size/Link opacity）、Forces（Center/Repel/Link force/Link distance） | 设置浮层的分组与控件清单 | Obsidian Forum |

## 从截图确认的关键观感参数（近似值）

- 画布背景：约 `#1E1E1E` 深灰黑（融入暗色主题，无渐变无网格）；
- 默认节点：灰白 `#A6A6A6` 左右，大小随度数；
- 悬停/选中高亮：主题 accent 色（紫），仅高亮节点 + 一度邻居，其余淡出；
- 标签：浅灰、带深色 halo，未放大/未高亮时不显示或极淡；
- 边：细、半透明灰、直线无箭头。
