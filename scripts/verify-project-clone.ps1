param(
    [string]$ExePath = "",
    [string]$Source = "octocat/Hello-World",
    [string]$Proxy = "http://127.0.0.1:7892"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$version = (Select-String -LiteralPath (Join-Path $projectRoot "pyproject.toml") -Pattern '^version = "([^"]+)"$').Matches.Groups[1].Value
if (-not $ExePath) {
    $ExePath = Join-Path $projectRoot "release\v$version\123mshub.exe"
}
$ExePath = [System.IO.Path]::GetFullPath($ExePath)
$gitCommand = Get-Command git -ErrorAction Stop
$testRoot = Join-Path $env:TEMP ("123mshub-project-check-" + [guid]::NewGuid().ToString("N"))
$appData = Join-Path $testRoot "appdata"
$repoRoot = Join-Path $testRoot "repo"
New-Item -ItemType Directory -Path $appData,$repoRoot -Force | Out-Null

$originalAppData = $env:APPDATA
$originalPath = $env:PATH
$env:APPDATA = $appData
$env:PATH = "$(Split-Path -Parent $gitCommand.Source);$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
$process = $null
$startedAt = Get-Date

function ConvertTo-Utf8JsonBytes {
    param([Parameter(Mandatory = $true)]$Value)
    Write-Output -NoEnumerate ([System.Text.Encoding]::UTF8.GetBytes(($Value | ConvertTo-Json -Depth 8)))
}

try {
    $process = Start-Process -FilePath $ExePath -WindowStyle Hidden -PassThru
    $health = $null
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/health" -TimeoutSec 2
            break
        }
        catch { Start-Sleep -Milliseconds 250 }
    }
    if (-not $health) { throw "EXE did not start the local service within 20 seconds." }

    $configBody = @{ repo_root = $repoRoot }
    if ($Proxy) { $configBody.proxy = $Proxy }
    Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/config" -Method Put `
        -ContentType "application/json; charset=utf-8" `
        -Body (ConvertTo-Utf8JsonBytes $configBody) | Out-Null
    $installed = Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/skills" -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body (ConvertTo-Utf8JsonBytes @{
            source = $Source
            item_type = "project"
            mode = "standard"
            fetcher = "archive"
            tags = @("project", "verification")
        })

    if ($installed.item_type -ne "project") { throw "Project item type was not preserved." }
    if ($installed.install_mode -ne "full") { throw "Project was not forced to full mode." }
    if ($installed.fetcher -ne "git") { throw "Project was not forced to Git." }
    if (-not (Test-Path -LiteralPath (Join-Path $installed.absolute_dir ".git"))) {
        throw "Project directory does not contain .git."
    }
    $versionCheck = Invoke-RestMethod -Uri "http://127.0.0.1:8766/api/skills/check-version" -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body (ConvertTo-Utf8JsonBytes @{ name = $installed.name })

    [ordered]@{
        version = $health.version
        python_on_isolated_path = [bool](Get-Command python -ErrorAction SilentlyContinue)
        git_on_isolated_path = [bool](Get-Command git -ErrorAction SilentlyContinue)
        project = $installed.name
        item_type = $installed.item_type
        install_mode = $installed.install_mode
        fetcher = $installed.fetcher
        git_metadata = $true
        remote_version_checked = [bool]$versionCheck.remote_hash
        result = "passed"
    } | ConvertTo-Json -Depth 5
}
finally {
    $env:APPDATA = $originalAppData
    $env:PATH = $originalPath
    Get-Process -Name "123mshub" -ErrorAction SilentlyContinue |
        Where-Object { try { $_.StartTime -ge $startedAt.AddSeconds(-2) } catch { $false } } |
        Stop-Process -Force
    if (Test-Path -LiteralPath $testRoot) {
        $resolved = (Resolve-Path -LiteralPath $testRoot).Path
        $tempPrefix = (Resolve-Path -LiteralPath $env:TEMP).Path.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
        if (-not $resolved.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a non-temporary directory: $resolved"
        }
        Get-ChildItem -LiteralPath $resolved -Recurse -Force -File -ErrorAction SilentlyContinue |
            ForEach-Object { $_.IsReadOnly = $false }
        [System.IO.Directory]::Delete($resolved, $true)
    }
}
