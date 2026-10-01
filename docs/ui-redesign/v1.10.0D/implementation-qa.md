# 123 MSHub v1.10.0D UI 重构与交付验收

本目录保存 v1.10.0D 的原生界面走查证据。设计基准来自
`D:\DiskWork\PJ\123mshub\stitchuirb` 中的 Stitch 页面、`DESIGN.md` 和打包代码，
功能基准来自 v1.10.0C 的原生壳与既有测试契约。

## 排版验收

共享主题把 Stitch 的文字层级固定成可复用 token，并由 PySide6/QSS 与图谱 Web UI
共同使用：

| 层级 | 尺寸 | 用途 |
| --- | ---: | --- |
| display | 20px | 页面主标题、图谱页标题 |
| section | 14px | 品牌或区块标题 |
| brand | 14px | `123 MSHub` 品牌字 |
| body / row | 12px | 导航、正文、按钮、条目主行 |
| meta | 11px | 描述、来源、时间、辅助说明 |
| micro | 10px | Stitch eyebrow、版本胶囊、细标签 |

西文优先沿用 Stitch 的 Plus Jakarta Sans 逻辑，中文使用已安装的 Dream Han Sans CN，
等宽数字与代码使用 Cascadia Mono；所有页面的标题、正文、元数据和标签均从
`src/mshub/native/theme.py` 的 `TYPOGRAPHY` 读取，避免单页自行放大或缩小字体。

## 页面证据

截图均由 `QT_QPA_PLATFORM=offscreen` 的原生走查脚本生成，窗口尺寸 1440×900，
亮色先于暗色应用，覆盖完整的五个导航页面和两套主题：

| 页面 | 亮色 | 暗色 |
| --- | --- | --- |
| 记忆仓库 | [01-memory-light.png](01-memory-light.png) | [05-memory-dark.png](05-memory-dark.png) |
| 技能仓库 | [02-skills-light.png](02-skills-light.png) | [06-skills-dark.png](06-skills-dark.png) |
| 安全中心 | [03-security-light.png](03-security-light.png) | [08-security-dark.png](08-security-dark.png) |
| 设置选项·维护与导入 | [04-settings-maintenance-light.png](04-settings-maintenance-light.png) | [09-settings-maintenance-dark.png](09-settings-maintenance-dark.png) |
| 记忆图示 | [07-graph-page-light.png](07-graph-page-light.png) | [10-graph-page-dark.png](10-graph-page-dark.png) |

图谱页在 offscreen Qt 环境会显示原生占位提示，因此截图只验证统一页头和主题；
实际 WebEngine、WebChannel、节点数、画布和动效由发布包的 Windows smoke 继续验收。

## 自动化验证

- `269 passed, 3 warnings`：第一次全量回归，确认字体/主题改造没有破坏原有功能。
- `270 passed, 2 warnings`：发布前全量回归，包含 v1.9.0 统计按钮兼容契约。
- 原生专项：`9 passed`（主题、窗口、v1.10.0D 功能与品牌版本）。
- Web：`npm run check` 通过，`npm test -- --runInBand` 为 `7 passed`。
- Vite：`node web/node_modules/vite/bin/vite.js build --config web/native-graph/vite.config.mjs` 通过。
- `git diff --check` 通过。

## 发布包验收

构建命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\native\build-native.ps1
```

输出目录与完整包：

- `D:\DiskWork\PJ\123mshub\release\native-v1.10.0D\123mshub\123mshub.exe`
- `D:\DiskWork\PJ\123mshub\release\123mshub-native-v1.10.0D-win64.zip`
- `D:\DiskWork\PJ\123mshub\release\native-v1.10.0D\README-完整包.txt`
- `D:\DiskWork\PJ\123mshub\release\native-v1.10.0D\SHA256SUMS.txt`

构建结果：onedir 目录约 359.93 MB，完整包约 151.63 MB；SHA-256 已写入
`SHA256SUMS.txt`，并在构建后重新读取 EXE 与 ZIP 校验。

最终校验值：EXE `d2beab7f41a9649e03f933838f56aad26688caef90ab257c10c817a069ca5afe`；
ZIP `a78c7de210a00efcef8d02112dab221f687f30d6d48acc98d3a1a081cf394d7a`。

## 真实 Windows 图谱 smoke

使用发布目录的 EXE 和真实 `D:\MSH` 仓库执行：

```powershell
123mshub.exe --smoke-float-stable --repo D:\MSH --config-dir <temporary-config>
```

结果为退出码 `0`、标准输出 `DRIFT_ALIVE`；日志记录 `graph-ready=True nodes=58 edges=42`、
`payloadNodes=58`、`rafActive=true`、`interactionDepth=0`、`floatTime` 从 `4450` 推进到
`11633`，稳定帧 hash 为 `a2acd9cd6d8674abab23a74c8401242a` 与
`80b0c68028931fa639fe4a4df4cbac71`，并记录 `float-alive=True`。

这证明交付包能在真实 Windows 图形平台加载本地图谱资源、拿到真实节点并保持漂移动效；
它不代替真实账户、远程 provider、GitHub 更新线路或用户偏好环境的验收。
