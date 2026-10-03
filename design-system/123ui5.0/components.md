# 组件契约

## 颜色使用

普通文字、结构边框和表面只调用 semantic token；品牌色只出现在主要动作、链接、选中指示、图谱类别和品牌版本标识。大面积背景不使用 Indigo/Violet 渐变。

## 状态

| 状态 | 表达 | 令牌 |
| --- | --- | --- |
| hover | 提升表面或加深边框 | `raised`、`action_hover` |
| pressed | 轻微压低和加深 | `action_pressed` |
| focus | 2px 主题色边框 | `accent` |
| selected row | 整行填充 | `selection` |
| disabled | 降低对比度，不使用透明模糊 | `faint`、`strong` |
| danger | 独立红色语义 | `error`、`error_soft` |

## 组件映射

- `primary`：单色 Indigo，适用于一般提交和保存；
- `agent`：Indigo → Violet 短渐变，只用于 Agent 连接/品牌入口；
- `ghost`：透明底和结构边框，hover 时使用 `selection`；
- `memoryRow` / `skillRow` / `securityRow`：选中使用 `selection` 填充，列表容器保持无焦点边框；
- `jobPanel`：实色面板，标题和箭头背景透明；
- `graph`：节点使用四级品牌明度，边使用低对比度 `graph_line`。
