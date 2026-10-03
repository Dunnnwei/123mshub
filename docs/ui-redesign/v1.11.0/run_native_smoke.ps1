param(
    [string]$Version = "1.11.0",
    [string]$OutputName = "native-smoke.log"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)))
$stamp = Get-Date -Format "yyyyMMddHHmmssfff"
$smokeRoot = Join-Path $projectRoot (".tmp-v1110-final-smoke-" + $stamp)
$config = Join-Path $smokeRoot "config"
$temp = Join-Path $smokeRoot "temp"
$repo = "D:\MSH"
$exe = Join-Path $projectRoot ("release\native-v{0}\123mshub\123mshub.exe" -f $Version)
if (-not (Test-Path -LiteralPath $repo -PathType Container)) { throw "真实仓库不存在：$repo" }
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "发布 EXE 不存在：$exe" }
New-Item -ItemType Directory -Path $config, $temp -Force | Out-Null
$oldTemp, $oldTmp, $oldQt, $oldGpu, $oldFlags = $env:TEMP, $env:TMP, $env:QT_QPA_PLATFORM, $env:QTWEBENGINE_DISABLE_GPU, $env:QTWEBENGINE_CHROMIUM_FLAGS
try {
    $env:TEMP = $temp
    $env:TMP = $temp
    $env:QT_QPA_PLATFORM = "windows"
    $env:QTWEBENGINE_DISABLE_GPU = "1"
    $env:QTWEBENGINE_CHROMIUM_FLAGS = $null
    $process = Start-Process -FilePath $exe -ArgumentList @(
        "--smoke-float-stable", "--repo", $repo, "--config-dir", $config
    ) -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 900
    $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -eq $process.Id })
    $listenerCount = $listeners.Count
    if (-not $process.WaitForExit(30000)) {
        Stop-Process -Id $process.Id -Force
        throw "最终 EXE 烟测超时（30 秒）"
    }
    $log = Join-Path $temp "123mshub-native-smoke.log"
    $destination = Join-Path $projectRoot ("docs\ui-redesign\v1.11.0\{0}" -f $OutputName)
    if (Test-Path -LiteralPath $log) {
        Copy-Item -LiteralPath $log -Destination $destination -Force
        $logText = [string](Get-Content -LiteralPath $log -Raw -Encoding UTF8)
    } else {
        $logText = "[missing smoke log]"
    }
    [pscustomobject]@{
        ExitCode = $process.ExitCode
        ListenerCount = $listenerCount
        Log = $destination
        LogText = $logText
    } | ConvertTo-Json -Depth 4
    if ([int]$process.ExitCode -ne 0) { throw ("final EXE smoke exit code: {0}" -f [int]$process.ExitCode) }
    if ($listenerCount -ne 0) { throw "最终 EXE 烟测出现 TCP 监听：$listenerCount" }
} finally {
    $env:TEMP, $env:TMP, $env:QT_QPA_PLATFORM, $env:QTWEBENGINE_DISABLE_GPU, $env:QTWEBENGINE_CHROMIUM_FLAGS = $oldTemp, $oldTmp, $oldQt, $oldGpu, $oldFlags
    if (Test-Path -LiteralPath $smokeRoot) {
        $resolved = (Resolve-Path -LiteralPath $smokeRoot).Path
        $rootResolved = (Resolve-Path -LiteralPath $projectRoot).Path
        if ($resolved.StartsWith($rootResolved + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}






