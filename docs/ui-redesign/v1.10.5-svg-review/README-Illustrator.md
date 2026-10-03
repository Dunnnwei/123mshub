# 123 MSHub v1.10.5 UI SVG 参考稿

这组文件选用 **记忆仓库** 页面作为当前 UI 的综合参考稿。页面同时包含左侧导航、品牌区、页头动作按钮、统计标签、搜索与筛选、记忆列表、选中行，以及展开的后台任务列表；亮色和暗色文件保持相同的 `1440 × 900` 画布与相同内容。

## 文件

- `123mshub-v1.10.5-记忆仓库-亮色.svg`
- `123mshub-v1.10.5-记忆仓库-暗色.svg`

两个 SVG 都由当前 v1.10.5 原生 Qt 页面实际渲染后导出，再把纯色画布、品牌标志、导航图标和主要操作图标替换为源 SVG 矢量组。文字、卡片、边框、选中行、标签和间距保留为 SVG 对象，便于在 Illustrator 中直接调整。

## Illustrator 使用建议

1. 直接打开对应的 SVG；如果 Illustrator 提示导入选项，保持默认的 SVG 导入方式并保留文本对象。
2. 建议先复制一份，再调整画布背景、侧栏底色、页板底色、列表行高、文字层级和选中行透明度。
3. 需要定位对象时，可以在图层/对象面板中搜索这些 `id` 或 `data-role`：`canvas-background`、`brand-logo`、`layer-navigation`、`header-new`、`header-edit`、`header-agent`、`memory-search`、`task-chevron`、`task-clear`。
4. 文字使用当前机器解析到的 `Microsoft YaHei UI`，并带有 `Segoe UI`、`Microsoft YaHei` 回退；如果你在 Illustrator 中替换字体，请记录字体名和字号。

## 内容边界

SVG 内的条目和后台任务是为了呈现完整布局的审阅样例，不会写入用户仓库、配置目录或产品数据。当前导出的窗口来自 v1.10.5 源码，不代表已经把 Illustrator 中的修改回写到产品；你把修改后的 SVG 交回后，我会以其颜色、层级、间距和状态表达为参考更新 Qt 代码。

生成脚本在 `source/export_ui.py` 和 `source/prepare_editable.py`，输出目录中的 `native-light.png`、`native-dark.png` 与 `*.rendered.png` 仅用于核对 SVG 视觉是否与原生 Qt 截图一致。
