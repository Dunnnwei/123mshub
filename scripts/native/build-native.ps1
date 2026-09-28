param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
# v1.7.4：发布拆分为「程序包」（release\native-vX，不含 PySide6）与
# 「环境包」（release\123mshub-environment-vX-win-x64.zip，仅 _internal\PySide6）。
# 有环境的老用户以后只需下载程序包。
# ocr 审查修复：版本号以 src\mshub\__init__.py 的 __version__ 为单一事实来源
# （窗口标题/测试断言都用它）；pyproject.toml 与 web\package.json 仍需发版时手工同步。
$Version = (Select-String -Path (Join-Path $projectRoot "src\mshub\__init__.py") -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { throw "无法从 src\mshub\__init__.py 解析 __version__。" }
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:QT_QPA_PLATFORM = "offscreen"

if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到 .venv\Scripts\python.exe，请先创建开发环境。"
}

& $python -m pytest
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
    (Join-Path $internal "PySide6\QtWebEngineProcess.exe"),
    (Join-Path $internal "PySide6\resources\icudtl.dat"),
    (Join-Path $internal "PySide6\resources\qtwebengine_resources.pak"),
    (Join-Path $internal "PySide6\resources\v8_context_snapshot.bin"),
    (Join-Path $internal "PySide6\translations\qtwebengine_locales\zh-CN.pak"),
    (Join-Path $internal "PySide6\translations\qtwebengine_locales\en-US.pak"),
    (Join-Path $internal "mshub\native\icons\123mshublogo.ico"),
    (Join-Path $internal "mshub\native\icons\123mshublogohei.ico")
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
    if (-not $process.WaitForExit(15000)) {
        Stop-Process -Id $process.Id -Force
        throw "原生 onedir 图谱冒烟超时。"
    }
    if ($process.ExitCode -ne 0) { throw "原生 onedir 图谱冒烟失败，代码 $($process.ExitCode)。" }
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root "123mshub.exe")
Set-Content -LiteralPath (Join-Path $release "SHA256SUMS.txt") -Value "$($hash.Hash.ToLowerInvariant())  123mshub\123mshub.exe" -Encoding ascii

# ---- v1.7.4 环境包/程序包拆分 -------------------------------------------
# 环境包 = _internal\PySide6（约 300MB，Qt/WebEngine 运行库，版本间通常不变）；
# 程序包 = 拆分后的 native-vX 目录（约 50MB）。以上冒烟在完整包上跑过；
# 拆分后立即验证"缺环境"路径（应弹下载提示并退出码 2），再打环境包 zip。
$pyside = Join-Path $internal "PySide6"
if (-not (Test-Path -LiteralPath $pyside)) { throw "缺少 _internal\PySide6，无法拆分环境包。" }
$envStage = Join-Path $projectRoot "build\native-environment"
if (Test-Path -LiteralPath $envStage) { Remove-Item -LiteralPath $envStage -Recurse -Force }
New-Item -ItemType Directory -Path $envStage -Force | Out-Null
Move-Item -LiteralPath $pyside -Destination $envStage

$env:MSHUB_ENV_CHECK_SILENT = "1"
# ocr 审查修复：记住外层是否原本设置过该变量，finally 恢复原值而不是无条件清除
$prevSilent = $null
if (Test-Path Env:\MSHUB_ENV_CHECK_SILENT) { $prevSilent = $env:MSHUB_ENV_CHECK_SILENT }
try {
    $probe = Start-Process -FilePath (Join-Path $root "123mshub.exe") -ArgumentList "--smoke-graph" -WindowStyle Hidden -PassThru
    if (-not $probe.WaitForExit(20000)) {
        Stop-Process -Id $probe.Id -Force
        throw "缺环境探测超时。"
    }
    if ($probe.ExitCode -ne 2) { throw "程序包缺环境时应退出码 2（弹下载提示），实际 $($probe.ExitCode)。" }
} finally {
    if ($null -eq $prevSilent) {
        Remove-Item Env:\MSHUB_ENV_CHECK_SILENT -ErrorAction SilentlyContinue
    } else {
        $env:MSHUB_ENV_CHECK_SILENT = $prevSilent
    }
}

$pysideVersion = (& $python -c "import PySide6; print(PySide6.__version__)" 2>$null)
if (-not $pysideVersion) { $pysideVersion = "unknown" }
$envReadme = Join-Path $envStage "README-环境包.txt"
Set-Content -LiteralPath $envReadme -Encoding UTF8 -Value @(
    "123 MSHub 环境包 v$Version（PySide6/Qt $pysideVersion）",
    "",
    "本包只包含图形运行环境（PySide6 文件夹），不含程序本体。",
    "首次使用：先解压「程序包」得到 123mshub 文件夹，再把本包中的 PySide6",
    "文件夹解压到 123mshub\_internal\ 里（与 python3xx.dll 同级），然后运行",
    "123mshub.exe。缺环境时程序会弹窗给出同样的下载指引。",
    "",
    "更新程序：下载新版程序包，直接解压覆盖旧目录（保留 _internal\PySide6）。",
    "除非发布页注明环境包升级，无需重新下载本包。",
    "",
    "下载页：https://github.com/Dunnnwei/123mshub/releases"
)
$envZip = Join-Path $projectRoot "release\123mshub-environment-v$Version-win-x64.zip"
if (Test-Path -LiteralPath $envZip) { Remove-Item -LiteralPath $envZip -Force }
Compress-Archive -Path (Join-Path $envStage "*") -DestinationPath $envZip
$envHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $envZip).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$envZip.sha256" -Value "$envHash  123mshub-environment-v$Version-win-x64.zip" -Encoding ascii

$programReadme = Join-Path $release "README-程序包.txt"
Set-Content -LiteralPath $programReadme -Encoding UTF8 -Value @(
    "123 MSHub 程序包 v$Version",
    "",
    "本包不含图形运行环境（PySide6/Qt，约 300MB）。首次使用需同时下载",
    "「环境包」123mshub-environment-v$Version-win-x64.zip，并把其中的 PySide6",
    "文件夹解压到本目录 123mshub\_internal\ 内；之后更新程序只需覆盖本包。",
    "环境缺失时启动会弹窗给出环境包下载地址；环境也可自行安装（需保持",
    "与本程序匹配的 PySide6 版本）。",
    "",
    "下载页：https://github.com/Dunnnwei/123mshub/releases"
)

Write-Host "原生 onedir 已生成：$root"
Write-Host "EXE SHA-256：$($hash.Hash)"
Write-Host "程序包体积（MB）：$([math]::Round(((Get-ChildItem $root -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 2))"
Write-Host "环境包：$envZip（MB：$([math]::Round(((Get-Item -LiteralPath $envZip).Length / 1MB), 2))）"
