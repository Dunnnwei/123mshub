param(
    [string]$EvidenceRoot = 'docs/ui-redesign/v1.12.0',
    [string]$BundleRoot = 'release/native-v1.12.0/123mshub'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $projectRoot
$exe = (Resolve-Path -LiteralPath (Join-Path $BundleRoot '123mshub.exe')).Path
$evidence = [IO.Path]::GetFullPath((Join-Path $projectRoot $EvidenceRoot))
$env:QT_QPA_PLATFORM = 'windows'
$env:QT_SCALE_FACTOR = '1'
$env:QT_SCALE_FACTOR_ROUNDING_POLICY = 'PassThrough'
$env:PYTHONUTF8 = '1'
Remove-Item Env:QTWEBENGINE_DISABLE_GPU -ErrorAction SilentlyContinue
Remove-Item Env:QTWEBENGINE_CHROMIUM_FLAGS -ErrorAction SilentlyContinue
$runs = @()

foreach ($scale in @('1.25', '1.5')) {
    $label = if ($scale -eq '1.25') { 'dpi125' } else { 'dpi150' }
    $output = Join-Path $evidence $label
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    $fixture = Join-Path $projectRoot ('.tmp-release-ui-' + [guid]::NewGuid().ToString('N'))
    $repo = Join-Path $fixture 'repo'
    $config = Join-Path $fixture 'config'
    $env:QT_SCREEN_SCALE_FACTORS = $scale
    $arguments = @('--smoke-ui', '--repo', ('"' + $repo + '"'), '--config-dir', ('"' + $config + '"'), '--evidence-dir', ('"' + $output + '"'))
    $started = [DateTimeOffset]::UtcNow
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $output 'stdout.txt') -RedirectStandardError (Join-Path $output 'stderr.txt')
    $owned = [Collections.Generic.HashSet[int]]::new()
    [void]$owned.Add($process.Id)
    $listeners = @()
    $samples = 0
    while (-not $process.HasExited) {
        foreach ($child in (Get-CimInstance Win32_Process | Where-Object { $owned.Contains([int]$_.ParentProcessId) })) {
            [void]$owned.Add([int]$child.ProcessId)
        }
        $listeners += @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $owned.Contains([int]$_.OwningProcess) } | Select-Object LocalAddress, LocalPort, OwningProcess)
        $samples++
        if (([DateTimeOffset]::UtcNow - $started).TotalSeconds -gt 90) {
            foreach ($ownedId in $owned) { Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue }
            throw "UI QA timed out: $label"
        }
        Start-Sleep -Milliseconds 250
        $process.Refresh()
    }
    $process.WaitForExit()
    $reportPath = Join-Path $output 'ui-smoke.json'
    if (-not (Test-Path -LiteralPath $reportPath)) { throw "UI QA report missing: $label" }
    $report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $run = [ordered]@{
        scale = $scale
        started_utc = $started.ToString('o')
        seconds = [math]::Round(([DateTimeOffset]::UtcNow - $started).TotalSeconds, 2)
        exit_code = $process.ExitCode
        process_ids = @($owned)
        listener_samples = $samples
        listeners = $listeners
        frozen = $report.frozen
        passed = $report.passed
        screenshot_count = $report.screenshots.Count
        actual_dpr = @($report.screenshots.dpr | Select-Object -Unique)
    }
    $runs += $run
    $run | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $output 'process-check.json') -Encoding UTF8
    if ($process.ExitCode -ne 0 -or -not $report.passed -or -not $report.frozen -or $listeners.Count -ne 0) { throw "UI QA failed: $label" }
    if (@($report.screenshots | Where-Object { [math]::Abs($_.dpr - [double]::Parse($scale, [Globalization.CultureInfo]::InvariantCulture)) -gt 0.01 }).Count -ne 0) { throw "DPR mismatch: $label" }
    Write-Host "$label passed: $($report.screenshots.Count) screenshots, $samples listener samples."
}
$runs | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'exe-ui-checks.json') -Encoding UTF8
