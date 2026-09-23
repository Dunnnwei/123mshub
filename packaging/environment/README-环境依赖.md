# 123 MSHub v1.3.3 Windows 环境依赖包

这个 ZIP 是独立的 Windows x64 环境包，和 `123mshub.exe` 分开发布。它不会替换主程序，也不会创建开机启动、服务或计划任务。

## 包含内容

- `Install-123MSHubEnvironment.ps1`：先自检，再列出已存在环境和将补充的安装文件；确认后才安装；
- `一键安装环境依赖.cmd`：双击启动上面的 PowerShell 安装器；
- `environment-manifest.json`：安装器版本、官方来源、文件 SHA-256、签名主体和静默安装参数；
- `SHA256SUMS.txt`：包内文件校验；
- `payload/`：官方签名安装文件。

## 环境边界

主程序 EXE 已自带 Python、FastAPI、前端静态资源和 Sigma 图谱资源，不需要另外安装 Python、Node.js、npm 或 pip。

本环境包处理两个必需的系统级组件，并把一个可选工具一并列入检查：

1. **Microsoft Edge WebView2 Runtime**：原生桌面窗口使用，包内是 Microsoft 官方 Evergreen x64 离线安装器。没有它时，主程序仍可尝试使用默认浏览器打开本地页面，但无法保证桌面嵌入窗口体验。
2. **.NET Framework 4.8 Runtime**：pywebview 的 Windows 渲染桥接使用。Windows 10/11 通常已经具备，安装器会先读取 Release 注册表值，缺少时才补充安装。
3. **Git for Windows**：Git 拉取、项目更新和 Git bundle 自愈使用。默认 archive 下载模式不强制依赖 Git；安装器仍会把它列为可补充项，可用 `-SkipGit` 跳过。

安装器只接受清单中列出的文件，安装前会校验 SHA-256 和 Authenticode 签名。系统安装可能触发一次 UAC，这是安装 WebView2、.NET 或 Git 的系统权限要求，主程序本身不需要管理员权限。

## 使用方式

1. 解压环境包到本地目录；
2. 双击 `一键安装环境依赖.cmd`；
3. 查看自检表和补充计划，输入 `Y` 确认；
4. 安装结束后再次查看自检结果；
5. 再运行 `123mshub.exe`。

只查看已有环境而不安装：

```powershell
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-123MSHubEnvironment.ps1 -ReportOnly
```

## 来源与复核

- WebView2 Evergreen Standalone x64：Microsoft 官方 `go.microsoft.com/fwlink/?linkid=2124701`；
- .NET Framework 4.8 Offline Runtime：Microsoft 官方 `go.microsoft.com/fwlink/?linkid=2088631`；
- Git for Windows：Git for Windows 官方 GitHub Release；具体版本 URL、SHA-256 和签名主体以 `environment-manifest.json` 为准；
- 若企业环境禁止联网，使用本包内的 payload 即可安装；若组策略禁止安装系统组件，请由管理员预先部署对应 Runtime。
