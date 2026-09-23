param(
    [switch]$ReportOnly,
    [switch]$SkipGit,
    [switch]$NoPrompt
)

$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $packageRoot 'environment-manifest.json'
$webViewGuid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'

function Read-Manifest {
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw "找不到环境清单：$manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.platform -ne 'win-x64') {
        throw "当前环境包只支持 win-x64，清单平台为：$($manifest.platform)"
    }
    return $manifest
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-WebView2State {
    $registryPaths = @(
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$webViewGuid",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$webViewGuid",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$webViewGuid",
        "HKCU:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$webViewGuid"
    )
    foreach ($path in $registryPaths) {
        try {
            $item = Get-ItemProperty -LiteralPath $path -ErrorAction Stop
            if ($item.pv -or $item.version) {
                $version = if ($item.pv) { $item.pv } else { $item.version }
                return [pscustomobject]@{ Installed = $true; Version = [string]$version; Source = $path }
            }
        }
        catch {
            # Registry view may not exist on this machine.
        }
    }
    $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ }
    foreach ($root in $roots) {
        $applicationRoot = Join-Path $root 'Microsoft\EdgeWebView\Application'
        if (Test-Path -LiteralPath $applicationRoot) {
            $versionDir = Get-ChildItem -LiteralPath $applicationRoot -Directory -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending | Select-Object -First 1
            if ($versionDir) {
                return [pscustomobject]@{ Installed = $true; Version = $versionDir.Name; Source = $versionDir.FullName }
            }
        }
    }
    return [pscustomobject]@{ Installed = $false; Version = ''; Source = '' }
}

function Get-GitState {
    $command = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        return [pscustomobject]@{ Installed = $false; Version = ''; Source = '' }
    }
    $version = ''
    try { $version = (& $command.Source --version 2>$null).Trim() } catch { }
    return [pscustomobject]@{ Installed = $true; Version = $version; Source = $command.Source }
}

function Get-DotNetState {
    $registryPaths = @(
        'HKLM:\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\NET Framework Setup\NDP\v4\Full'
    )
    foreach ($path in $registryPaths) {
        try {
            $release = [int](Get-ItemProperty -LiteralPath $path -Name Release -ErrorAction Stop).Release
            if ($release -ge 528040) {
                return [pscustomobject]@{ Installed = $true; Version = "4.8 (Release $release)"; Source = $path }
            }
        }
        catch {
            # Registry view may not exist on this machine.
        }
    }
    return [pscustomobject]@{ Installed = $false; Version = ''; Source = '' }
}

function Get-BrowserState {
    $path = 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice'
    try {
        $choice = (Get-ItemProperty -LiteralPath $path -Name ProgId -ErrorAction Stop).ProgId
        return [string]$choice
    }
    catch {
        return '未读取到默认浏览器'
    }
}

function Test-LocalPortAvailable([int]$Port) {
    $listener = $null
    try {
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($listener) { $listener.Stop() }
    }
}

function Get-Preflight($Manifest) {
    $webview = Get-WebView2State
    $dotnet = Get-DotNetState
    $git = Get-GitState
    $rows = @(
        [pscustomobject]@{ 项目 = '系统架构'; 当前状态 = if ([Environment]::Is64BitOperatingSystem) { 'Windows x64' } else { '非 x64' }; 说明 = '当前包目标为 win-x64' },
        [pscustomobject]@{ 项目 = 'WebView2 Runtime'; 当前状态 = if ($webview.Installed) { "已存在 $($webview.Version)" } else { '缺少' }; 说明 = '原生桌面窗口需要' },
        [pscustomobject]@{ 项目 = '.NET Framework 4.8'; 当前状态 = if ($dotnet.Installed) { "已存在 $($dotnet.Version)" } else { '缺少' }; 说明 = 'Windows 渲染桥接需要' },
        [pscustomobject]@{ 项目 = 'Git for Windows'; 当前状态 = if ($git.Installed) { "已存在 $($git.Version)" } else { '缺少' }; 说明 = 'Git 拉取/项目更新可选' },
        [pscustomobject]@{ 项目 = '默认浏览器'; 当前状态 = Get-BrowserState; 说明 = 'WebView2 缺失时的回退路径' },
        [pscustomobject]@{ 项目 = '本地端口 8766'; 当前状态 = if (Test-LocalPortAvailable 8766) { '可用' } else { '已占用' }; 说明 = '程序启动时使用' }
    )
    Write-Host ''
    Write-Host '=== 123 MSHub 环境自检 ===' -ForegroundColor Cyan
    $rows | Format-Table -AutoSize | Out-Host
    $plan = @()
    $webviewComponent = $Manifest.components | Where-Object id -eq 'webview2' | Select-Object -First 1
    $dotnetComponent = $Manifest.components | Where-Object id -eq 'dotnet48' | Select-Object -First 1
    $gitComponent = $Manifest.components | Where-Object id -eq 'git' | Select-Object -First 1
    if (-not $webview.Installed) { $plan += $webviewComponent }
    if (-not $dotnet.Installed) { $plan += $dotnetComponent }
    if (-not $SkipGit -and -not $git.Installed) { $plan += $gitComponent }
    Write-Host '=== 将补充的环境包 ===' -ForegroundColor Cyan
    if ($plan.Count -eq 0) {
        Write-Host '当前环境已满足环境包检查项，不需要补充安装。' -ForegroundColor Green
    }
    else {
        foreach ($component in $plan) {
            Write-Host ("- {0}：{1}" -f $component.label, $component.description)
            Write-Host ("  文件：{0}" -f $component.file)
        }
    }
    return [pscustomobject]@{ WebView2 = $webview; DotNet = $dotnet; Git = $git; Plan = @($plan) }
}

function Resolve-PayloadPath($Component) {
    $root = [IO.Path]::GetFullPath($packageRoot).TrimEnd('\') + '\'
    $path = [IO.Path]::GetFullPath((Join-Path $packageRoot $Component.file))
    if (-not $path.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝使用环境包目录外的安装文件：$path"
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "环境包缺少安装文件：$path"
    }
    return $path
}

function Assert-Payload($Component) {
    $path = Resolve-PayloadPath $Component
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($hash -ne ([string]$Component.sha256).ToLowerInvariant()) {
        throw "安装文件 SHA-256 不匹配：$($Component.file)"
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    if ($signature.Status -ne 'Valid') {
        throw "安装文件签名无效：$($Component.file)（$($signature.Status)）"
    }
    if ($Component.signer_contains -and $signature.SignerCertificate.Subject -notlike "*$($Component.signer_contains)*") {
        throw "安装文件签名主体不符合清单：$($Component.file)"
    }
    return $path
}

function Relaunch-Elevated {
    $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
    if ($ReportOnly) { $arguments += '-ReportOnly' }
    if ($SkipGit) { $arguments += '-SkipGit' }
    if ($NoPrompt) { $arguments += '-NoPrompt' }
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $arguments | Out-Null
    exit 0
}

try {
    $manifest = Read-Manifest
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw '当前环境不是 64 位 Windows，不能安装 win-x64 环境包。'
    }
    $preflight = Get-Preflight $manifest
    if ($ReportOnly -or $preflight.Plan.Count -eq 0) {
        if ($preflight.Plan.Count -eq 0) { Write-Host '环境自检完成，无需安装。' -ForegroundColor Green }
        exit 0
    }
    if (-not $NoPrompt) {
        $answer = Read-Host '以上是将补充的环境包，继续安装吗？输入 Y 继续，其他输入退出'
        if ($answer -notmatch '^(Y|y)$') { Write-Host '已取消安装。'; exit 0 }
    }
    if (-not (Test-IsAdministrator)) {
        Write-Host '安装系统环境包需要管理员权限，即将弹出 UAC 确认。' -ForegroundColor Yellow
        Relaunch-Elevated
    }
    foreach ($component in $preflight.Plan) {
        $path = Assert-Payload $component
        Write-Host ("正在安装 {0}..." -f $component.label) -ForegroundColor Cyan
        $process = Start-Process -FilePath $path -ArgumentList $component.install_arguments -Wait -PassThru
        if ($process.ExitCode -notin @(0, 3010)) {
            throw "$($component.label) 安装失败，退出码：$($process.ExitCode)"
        }
    }
    Write-Host ''
    Write-Host '安装完成，重新执行自检：' -ForegroundColor Green
    $after = Get-Preflight $manifest
    if (-not $after.WebView2.Installed) { throw 'WebView2 安装后仍未检测到，请重启 Windows 后重试。' }
    if (-not $after.DotNet.Installed) { throw '.NET Framework 4.8 安装后仍未检测到，请重启 Windows 后重试。' }
    if (-not $SkipGit -and -not $after.Git.Installed) { throw 'Git 安装后仍未检测到，请重启终端后重试。' }
    Write-Host '123 MSHub 环境依赖自检通过。' -ForegroundColor Green
}
catch {
    Write-Host ("环境安装失败：{0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
