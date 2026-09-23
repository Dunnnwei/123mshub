param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:QT_QPA_PLATFORM = "offscreen"

if (-not (Test-Path -LiteralPath $python)) {
    throw "找不到 .venv\Scripts\python.exe，请先创建开发环境。"
}

& $python -m pytest
if ($LASTEXITCODE -ne 0) { throw "测试失败，停止打包。" }

$release = Join-Path $projectRoot "release\native-v1.4.1"
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
    (Join-Path $internal "PySide6\translations\qtwebengine_locales\en-US.pak")
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
Write-Host "原生 onedir 已生成：$root"
Write-Host "EXE SHA-256：$($hash.Hash)"
Write-Host "目录体积（MB）：$([math]::Round(((Get-ChildItem $root -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 2))"
