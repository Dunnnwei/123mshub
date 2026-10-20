param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
# v1.9.0：取消 v1.7.4 的程序包/环境包拆分——只发布单一完整包
# （release\123mshub-native-vX-win64.zip，含 PySide6，解压即用）。
# ocr 审查修复：版本号以 src\mshub\__init__.py 的 __version__ 为单一事实来源
# （窗口标题/测试断言都用它）；pyproject.toml 与 web\package.json 仍需发版时手工同步。
$Version = (Select-String -Path (Join-Path $projectRoot "src\mshub\__init__.py") -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "无法从 src\mshub\__init__.py 解析 __version__。" }
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:QT_QPA_PLATFORM = "offscreen"
$env:PYTHONUTF8 = "1"

if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到 .venv\Scripts\python.exe，请先创建开发环境。"
}

New-Item -ItemType Directory -Path (Join-Path $projectRoot 'build') -Force | Out-Null
& $python -m pytest --tb=short --junitxml=build/release-tests.xml
if ($LASTEXITCODE -ne 0) { throw "测试失败，停止打包。" }

$release = Join-Path $projectRoot "release\native-v$Version"
$work = Join-Path $projectRoot "build\native-pyinstaller"
if (Test-Path -LiteralPath $release) {
    $resolvedReleaseToClean = (Resolve-Path -LiteralPath $release).Path
    $releaseParent = (Resolve-Path -LiteralPath (Split-Path -Parent $release)).Path
    if (-not $resolvedReleaseToClean.StartsWith($releaseParent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "发布目录越界：$resolvedReleaseToClean"
    }
    Remove-Item -LiteralPath $resolvedReleaseToClean -Recurse -Force
}
New-Item -ItemType Directory -Path $release -Force | Out-Null
$releaseRoot = Join-Path $release "123mshub"
& $python -m PyInstaller --noconfirm --clean --distpath $release --workpath $work packaging/native/123mshub_native.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败。" }

$root = $releaseRoot
& (Join-Path $projectRoot "scripts\native\prune-webengine.ps1") -BundleRoot $root
$internal = Join-Path $root "_internal"
foreach ($required in @(
    (Join-Path $root "123mshub.exe"),
    (Join-Path $internal "mshub\native\graph\index.html"),
    (Join-Path $internal "mshub\native\graph\haui.css"),
    (Join-Path $internal "mshub\native\graph\haui-tokens.js"),
    (Join-Path $internal "mshub\native\haui\themes.json"),
    (Join-Path $internal "mshub\native\haui\native.qss"),
    (Join-Path $internal "mshub\native\haui\fonts\SpaceGrotesk-Latin.ttf"),
    (Join-Path $internal "mshub\native\haui\licenses\Tabler-MIT.txt"),
    (Join-Path $internal "mshub\ui5\tokens.json"),
    (Join-Path $internal "PySide6\QtWebEngineProcess.exe"),
    (Join-Path $internal "PySide6\resources\icudtl.dat"),
    (Join-Path $internal "PySide6\resources\qtwebengine_resources.pak"),
    (Join-Path $internal "PySide6\resources\v8_context_snapshot.bin"),
    (Join-Path $internal "PySide6\translations\qtwebengine_locales\zh-CN.pak"),
    (Join-Path $internal "PySide6\translations\qtwebengine_locales\en-US.pak"),
    (Join-Path $internal "mshub\native\icons\NEWmshublogo.ico"),
    (Join-Path $internal "mshub\native\icons\new123uilogo.ico"),
    (Join-Path $internal "mshub\native\icons\MATERIAL-SYMBOLS-LICENSE.txt")
)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "缺少 onedir 资源：$required" }
}

if (-not $SkipSmoke) {
    # Use the real Windows platform and the hidden smoke route: it creates a
    # QWebEngineView, loads file:// + qrc WebChannel, then exits by timer.
    $env:QT_QPA_PLATFORM = "windows"
    $env:QTWEBENGINE_DISABLE_GPU = "1"
    $smokeConfig = Join-Path $projectRoot ".tmp-native-smoke-config"
    $smokeRepo = Join-Path $projectRoot ".tmp-native-smoke-repo"
    New-Item -ItemType Directory -Path $smokeConfig, $smokeRepo -Force | Out-Null
    $process = Start-Process -FilePath (Join-Path $root "123mshub.exe") -ArgumentList "--smoke-graph", "--repo", $smokeRepo, "--config-dir", $smokeConfig -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 700
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $process.Id })
    if ($listeners.Count -gt 0) {
        Stop-Process -Id $process.Id -Force
        throw "原生 smoke 创建了 TCP 监听，违反零监听红线。"
    }
    if (-not $process.WaitForExit(30000)) {
        Stop-Process -Id $process.Id -Force
        throw "原生 onedir 图谱冒烟超时。"
    }
    if ($process.ExitCode -ne 0) { throw "原生 onedir 图谱冒烟失败，代码 $($process.ExitCode)。" }
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root "123mshub.exe")
Set-Content -LiteralPath (Join-Path $release "SHA256SUMS.txt") -Value "$($hash.Hash.ToLowerInvariant())  123mshub\123mshub.exe" -Encoding ascii

$readme = Join-Path $release "README-完整包.txt"
Set-Content -LiteralPath $readme -Encoding UTF8 -Value @(
    "123 MSHub 完整包 v$Version（含 HAUI 界面与图形运行环境）",
    "",
    "完整解压后运行 123mshub\123mshub.exe；无需 Python、Node.js 或另下环境包。",
    "升级：设置选项 → 检查更新，或下载完整包解压到新目录后选择原仓库。",
    "配置保存在 %APPDATA%\mshub，仓库数据位于你指定的目录。升级保留配置及数据。",
    "外观：设置选项中可独立选择主题、HAUI 调色板和强调色，点击保存设置生效。",
    "字体与主题的来源及许可证见 _internal\mshub\native\haui。",
    "本版使用标准 onedir，无 UPX、无混淆、无需管理员权限；未进行代码签名。",
    "下载后可用 SHA256SUMS.txt 核对完整包；本机扫描结果见发布验收报告。",
    "",
    "下载页：https://github.com/Dunnnwei/123mshub/releases"
)
Copy-Item -LiteralPath $readme -Destination (Join-Path $root 'README-完整包.txt')
& $python (Join-Path $projectRoot 'scripts/native/verify-release.py') --manifest-only
if ($LASTEXITCODE -ne 0) { throw '发布文件清单生成失败。' }

# ---- v1.9.0：取消环境包分离——单一完整包 ----------------------------------
# 用户反馈：v1.7.4 的「程序包 + 环境包」拆分造成使用不便（首装要下两个包、
# 覆盖更新还要小心保留 _internal\PySide6）。本版起只发布一个完整包 zip
# （约 170MB），解压即用；程序内「设置 → 检查更新」可 GitHub 直升。
# 老版分离包资产保留在历史 Release 中不动。
$zip = Join-Path $projectRoot "release\123mshub-native-v$Version-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
# Compress-Archive 偶发被瞬时文件锁（杀毒/冒烟孤儿进程扫描 EXE/DLL）打断：
# 同一压缩最多重试 3 次，锁通常几秒内自行释放（v1.8.1 实测）。
$compressed = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    try {
        Compress-Archive -Path $releaseRoot -DestinationPath $zip
        $compressed = $true
        break
    } catch {
        Write-Host "Compress-Archive 第 $attempt 次失败（$($_.Exception.Message)），2 秒后重试…"
        Start-Sleep -Seconds 2
    }
}
if (-not $compressed) { throw "完整包压缩连续 3 次失败。" }
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $release "SHA256SUMS.txt") -Encoding ascii -Value @(
    "$($hash.Hash.ToLowerInvariant())  123mshub\123mshub.exe",
    "$zipHash  123mshub-native-v$Version-win64.zip"
)

& $python (Join-Path $projectRoot 'scripts/native/verify-release.py')
if ($LASTEXITCODE -ne 0) { throw '最终发布包校验失败。' }

Write-Host "原生 onedir 已生成：$root"
Write-Host "EXE SHA-256：$($hash.Hash)"
Write-Host "完整包 zip SHA-256：$zipHash"
Write-Host "目录体积（MB）：$([math]::Round(((Get-ChildItem $root -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 2))"
Write-Host "完整包：$zip（MB：$([math]::Round(((Get-Item -LiteralPath $zip).Length / 1MB), 2))）"
