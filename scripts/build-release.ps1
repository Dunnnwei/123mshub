param(
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entry = Join-Path $projectRoot "packaging\123mshub_entry.py"
$webRoot = Join-Path $projectRoot "src\mshub\web"

Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = "1"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "创建发布虚拟环境..."
    python -m venv .venv
}

Write-Host "安装/确认打包依赖..."
& $python -m pip install -e ".[gui,keyring,release]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipFrontendBuild) {
    Write-Host "重新构建前端..."
    Push-Location (Join-Path $projectRoot "web")
    try {
        npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        npm run check
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        Pop-Location
    }
}

$version = (& $python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "pyproject.toml 中的版本号无效：$version"
}

$requiredAssets = @(
    (Join-Path $webRoot "index.html"),
    (Join-Path $webRoot "assets")
)
foreach ($asset in $requiredAssets) {
    if (-not (Test-Path -LiteralPath $asset)) {
        throw "缺少前端构建产物：$asset"
    }
}

$assetFiles = Get-ChildItem -LiteralPath (Join-Path $webRoot "assets") -File
if (-not ($assetFiles | Where-Object Extension -eq ".js") -or -not ($assetFiles | Where-Object Extension -eq ".css")) {
    throw "前端 assets 中必须同时包含 JS 和 CSS。"
}

$releaseDir = Join-Path $projectRoot "release\v$version"
$workDir = Join-Path $projectRoot "build\pyinstaller"
$specDir = Join-Path $workDir "spec"
# 版本信息文件必须放同步盘之外：build\ 在 DiskWork 双向同步区内，曾出现
# 分机侧陈旧副本连内容带 mtime 一起被同步还原、导致 EXE 版本资源写错
# （2026-09-20 实测 10 秒内被还原）。%TEMP% 不进同步，永不受竞态影响。
$versionFile = Join-Path $env:TEMP "mshub-version-info.txt"

New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
New-Item -ItemType Directory -Path $specDir -Force | Out-Null

$parts = $version.Split(".")
$versionTuple = "$($parts[0]), $($parts[1]), $($parts[2]), 0"
$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($versionTuple),
    prodvers=($versionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [
          StringStruct('CompanyName', 'Dunnnwei'),
          StringStruct('FileDescription', '123 MSHub 本地 Agent 共享大脑管理器（Memory & Skill Hub）'),
          StringStruct('FileVersion', '$version'),
          StringStruct('InternalName', '123mshub'),
          StringStruct('LegalCopyright', 'MIT License'),
          StringStruct('OriginalFilename', '123mshub.exe'),
          StringStruct('ProductName', '123 MSHub'),
          StringStruct('ProductVersion', '$version')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"@
# 中文版本信息必须带 BOM，否则 PyInstaller 按 GBK 读会乱码
[System.IO.File]::WriteAllText($versionFile, $versionInfo, [System.Text.UTF8Encoding]::new($true))

$oldExe = Join-Path $releaseDir "123mshub.exe"
if (Test-Path -LiteralPath $oldExe) {
    [System.IO.File]::Delete($oldExe)
}

Write-Host "使用 PyInstaller 生成单文件 EXE..."
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name 123mshub `
    --distpath $releaseDir `
    --workpath $workDir `
    --specpath $specDir `
    --paths (Join-Path $projectRoot "src") `
    --add-data "$webRoot;mshub/web" `
    --add-data "$(Join-Path $projectRoot 'README.md');." `
    --version-file $versionFile `
    --collect-all webview `
    --collect-submodules keyring.backends `
    --hidden-import keyring.backends.Windows `
    $entry
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$exe = Get-Item -LiteralPath $oldExe
$limit = 50MB
if ($exe.Length -ge $limit) {
    throw "EXE 大小为 $([math]::Round($exe.Length / 1MB, 2)) MB，超过 50 MB 限制。"
}

$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $exe.FullName
Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") `
    -Value "$($hash.Hash.ToLowerInvariant())  123mshub.exe" `
    -Encoding ascii

$notes = Join-Path $projectRoot "RELEASE_NOTES.md"
if (Test-Path -LiteralPath $notes) {
    Copy-Item -LiteralPath $notes -Destination (Join-Path $releaseDir "RELEASE_NOTES.md") -Force
}

# 发布物 = zip 解压包：EXE + README（精简版）+ SHA256SUMS
$zipName = "123mshub-v$version-win64.zip"
$zipPath = Join-Path (Split-Path -Parent $releaseDir) $zipName
if (Test-Path -LiteralPath $zipPath) {
    [System.IO.File]::Delete($zipPath)
}
$readmeLite = Join-Path $releaseDir "README.md"
@"
# 123 MSHub（Memory & Skill Hub）v$version

本地 agent 的共享大脑管理器。解压到任意目录，双击 ``123mshub.exe`` 即可运行。

- 首次启动：设定仓库位置（建议放进同步盘）；AI 接口与 GitHub Token 可选；
- 复制「注入提示词」发给你的 agent，它就能读共享记忆、用共享技能库、往 inbox 投递新知识；
- 连通暗号：向 agent 发 ``AI猛如虎``，应只回「Token任你烧！/ 暗号对齐，123mshub已接入。」。

## 校验与安全

SHA256 见同目录 ``SHA256SUMS.txt``（PowerShell：``Get-FileHash .\123mshub.exe``）。
SmartScreen 提示「Windows 已保护你的电脑」为未签名 EXE 的正常现象：
「更多信息 → 仍要运行」。

## 常见问题

- 桌面窗口依赖 Edge WebView2（Win11 自带）；缺失时自动改用默认浏览器打开；
- 默认端口 8766，与旧 123skillrepo（8765）互不干扰，可同时运行；
- 完整说明（含记忆库使用、整理与日报、值守 Agent）见项目主页 README。

记忆体系致谢开源项目 Engramory（github.com/tinqiao-oss/engramory）。
MIT License。
"@ | Out-File -LiteralPath $readmeLite -Encoding utf8

Compress-Archive -LiteralPath @(
    (Join-Path $releaseDir "123mshub.exe"),
    $readmeLite,
    (Join-Path $releaseDir "SHA256SUMS.txt"),
    $notes
) -DestinationPath $zipPath -Force

$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
Add-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") `
    -Value "$zipHash  $zipName" -Encoding ascii

Write-Host ""
Write-Host "发布包已生成：$zipPath"
Write-Host "发布目录：$releaseDir"
Write-Host "版本：v$version"
Write-Host "EXE 大小：$([math]::Round($exe.Length / 1MB, 2)) MB；zip 大小：$([math]::Round((Get-Item $zipPath).Length / 1MB, 2)) MB"
Write-Host "SHA-256（EXE）：$($hash.Hash)"
