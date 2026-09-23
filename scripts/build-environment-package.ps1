param(
    [switch]$SkipDownload
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$sourceRoot = Join-Path $projectRoot 'packaging\environment'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $projectRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$version = (& $python -c "import tomllib, pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()
$workRoot = Join-Path $projectRoot "build\environment-v$version"
$stageRoot = Join-Path $workRoot 'stage'
$payloadRoot = Join-Path $stageRoot 'payload'
$releaseRoot = Join-Path $projectRoot "release\v$version"
$zipName = "123mshub-environment-v$version-win-x64.zip"
$zipPath = Join-Path (Join-Path $projectRoot 'release') $zipName
$payloadCacheRoot = Join-Path $projectRoot 'build\environment-payload-cache'

function Remove-WorkspaceTree([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $workspace = [IO.Path]::GetFullPath($projectRoot).TrimEnd('\') + '\'
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($workspace, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝清理工作区之外的路径：$resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

function Download-AndVerify([string]$Uri, [string]$Path, [string]$SignerContains) {
    Invoke-WebRequest -Uri $Uri -OutFile $Path -UseBasicParsing
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike "*$SignerContains*") {
        throw "下载文件签名校验失败：$Path（$($signature.Status)，$($signature.SignerCertificate.Subject)）"
    }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-RelativeFilePath([string]$BasePath, [string]$FilePath) {
    # Windows PowerShell 5.1 does not expose [IO.Path]::GetRelativePath.
    $base = [IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $file = [IO.Path]::GetFullPath($FilePath)
    if (-not $file.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "文件不在环境包目录内：$file"
    }
    return $file.Substring($base.Length).Replace('\', '/')
}

if ($SkipDownload) {
    $existingPayload = Join-Path $workRoot 'stage\payload'
    if (Test-Path -LiteralPath $existingPayload) {
        Remove-WorkspaceTree $payloadCacheRoot
        New-Item -ItemType Directory -Force -Path $payloadCacheRoot | Out-Null
        Copy-Item -Path (Join-Path $existingPayload '*') -Destination $payloadCacheRoot -Force
    }
    if (-not (Test-Path -LiteralPath $payloadCacheRoot)) {
        throw '-SkipDownload 需要 build 环境目录中已经存在三个 payload 安装器。'
    }
}
Remove-WorkspaceTree $workRoot
New-Item -ItemType Directory -Force -Path $payloadRoot | Out-Null

$webViewFile = Join-Path $payloadRoot 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
$dotnetFile = Join-Path $payloadRoot 'NDP48-x86-x64-AllOS-ENU.exe'
$gitFile = $null
$webViewHash = $null
$dotnetHash = $null
$gitHash = $null
$gitRelease = $null

if (-not $SkipDownload) {
    Write-Host '下载并验证 Microsoft WebView2 Evergreen Standalone x64...'
    $webViewHash = Download-AndVerify `
        'https://go.microsoft.com/fwlink/?linkid=2124701' `
        $webViewFile `
        'Microsoft Corporation'

    Write-Host '.NET Framework 4.8 离线运行时...'
    $dotnetHash = Download-AndVerify `
        'https://go.microsoft.com/fwlink/?linkid=2088631' `
        $dotnetFile `
        'Microsoft Corporation'

    $headers = @{ 'User-Agent' = '123mshub-environment-builder' }
    $gitRelease = Invoke-RestMethod -Headers $headers -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest'
    $gitAsset = $gitRelease.assets |
        Where-Object { $_.name -match '^Git-\d+(\.\d+)+-64-bit\.exe$' } |
        Select-Object -First 1
    if (-not $gitAsset) { throw 'Git for Windows 官方 Release 中找不到 64-bit 安装器。' }
    $gitFile = Join-Path $payloadRoot $gitAsset.name
    Write-Host ("下载并验证 {0}..." -f $gitAsset.name)
    $gitHash = Download-AndVerify $gitAsset.browser_download_url $gitFile 'Johannes Schindelin'
}
else {
    Copy-Item -Path (Join-Path $payloadCacheRoot '*') -Destination $payloadRoot -Force
    $gitFile = Get-ChildItem -LiteralPath $payloadRoot -Filter 'Git-*-64-bit.exe' -File | Select-Object -First 1 -ExpandProperty FullName
    $dotnetFile = Get-ChildItem -LiteralPath $payloadRoot -Filter 'NDP48-*.exe' -File | Select-Object -First 1 -ExpandProperty FullName
    if (-not (Test-Path -LiteralPath $webViewFile) -or -not (Test-Path -LiteralPath $dotnetFile) -or -not $gitFile) {
        throw '-SkipDownload 需要 build 环境目录中已经存在三个 payload 安装器。'
    }
    $webViewHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $webViewFile).Hash.ToLowerInvariant()
    $dotnetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dotnetFile).Hash.ToLowerInvariant()
    $gitHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $gitFile).Hash.ToLowerInvariant()
}

if (-not $gitRelease) {
    $gitName = Split-Path -Leaf $gitFile
    $gitVersion = [regex]::Match($gitName, '^Git-(.+)-64-bit\.exe$').Groups[1].Value
    $gitUrl = 'https://github.com/git-for-windows/git/releases/latest'
}
else {
    $gitName = $gitAsset.name
    $gitVersion = $gitRelease.tag_name
    $gitUrl = $gitAsset.browser_download_url
}

$manifest = [ordered]@{
    schema_version = 1
    product = '123mshub'
    product_version = $version
    platform = 'win-x64'
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    components = @(
        [ordered]@{
            id = 'webview2'
            label = 'Microsoft Edge WebView2 Runtime'
            description = '原生桌面窗口运行时'
            required = $true
            file = 'payload/MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
            source = 'https://go.microsoft.com/fwlink/?linkid=2124701'
            sha256 = $webViewHash
            signer_contains = 'Microsoft Corporation'
            install_arguments = '/silent /install'
        },
        [ordered]@{
            id = 'dotnet48'
            label = '.NET Framework 4.8 Runtime'
            description = 'pywebview Windows 渲染桥接所需的系统运行时'
            required = $true
            file = 'payload/NDP48-x86-x64-AllOS-ENU.exe'
            source = 'https://go.microsoft.com/fwlink/?linkid=2088631'
            sha256 = $dotnetHash
            signer_contains = 'Microsoft Corporation'
            install_arguments = '/q /norestart'
        },
        [ordered]@{
            id = 'git'
            label = "Git for Windows $gitVersion"
            description = 'Git 拉取、项目更新和 Git bundle 自愈（可选）'
            required = $false
            file = "payload/$gitName"
            source = $gitUrl
            sha256 = $gitHash
            signer_contains = 'Johannes Schindelin'
            install_arguments = '/VERYSILENT /NORESTART'
        }
    )
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stageRoot 'environment-manifest.json') -Encoding UTF8
Copy-Item -LiteralPath (Join-Path $sourceRoot 'Install-123MSHubEnvironment.ps1') -Destination $stageRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot '一键安装环境依赖.cmd') -Destination $stageRoot -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot 'README-环境依赖.md') -Destination $stageRoot -Force

$sumLines = Get-ChildItem -LiteralPath $stageRoot -File -Recurse |
    Where-Object { $_.Name -ne 'SHA256SUMS.txt' } |
    ForEach-Object {
        $relative = Get-RelativeFilePath $stageRoot $_.FullName
        "$((Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant())  $relative"
    }
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllLines((Join-Path $stageRoot 'SHA256SUMS.txt'), [string[]]$sumLines, $utf8NoBom)

if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path (Join-Path $stageRoot '*') -DestinationPath $zipPath -Force
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$zipPath.sha256" -Value "$zipHash  $zipName" -Encoding ascii

if (Test-Path -LiteralPath (Join-Path $releaseRoot 'SHA256SUMS.txt')) {
    $releaseSumsPath = Join-Path $releaseRoot 'SHA256SUMS.txt'
    $existing = @(Get-Content -LiteralPath $releaseSumsPath | Where-Object { $_ -notlike "*$zipName" })
    Set-Content -LiteralPath $releaseSumsPath -Value @($existing + "$zipHash  $zipName") -Encoding ascii
}

Write-Host ''
Write-Host "环境依赖包已生成：$zipPath"
Write-Host "SHA-256：$zipHash"
Write-Host "安装前自检入口：Install-123MSHubEnvironment.ps1 -ReportOnly"
