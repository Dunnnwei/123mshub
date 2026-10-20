param([string]$Version = '1.12.0')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$release = Join-Path $projectRoot "release/native-v$Version"
$bundle = Join-Path $release '123mshub'
$zip = Join-Path $projectRoot "release/123mshub-native-v$Version-win64.zip"
$exe = Join-Path $bundle '123mshub.exe'
$scanner = Join-Path $env:ProgramData 'Microsoft/Windows Defender/Platform/CurrentVersion/MpCmdRun.exe'
if (-not (Test-Path -LiteralPath $scanner)) {
    $scanner = Join-Path $env:ProgramFiles 'Windows Defender/MpCmdRun.exe'
}
if (-not (Test-Path -LiteralPath $scanner)) { throw 'Windows Defender scanner is unavailable.' }
$before = Get-MpComputerStatus
if (-not $before.AMServiceEnabled -or -not $before.AntivirusEnabled -or -not $before.RealTimeProtectionEnabled) {
    throw 'Windows Defender protection is not active; no clean-scan claim can be made.'
}
$results = @()
foreach ($target in @($bundle, $zip)) {
    $kind = if ($target -eq $bundle) { 'bundle' } else { 'zip' }
    $stdout = Join-Path $release "defender-$kind.txt"
    $stderr = Join-Path $release "defender-$kind-stderr.txt"
    $started = [DateTimeOffset]::UtcNow
    $process = Start-Process -FilePath $scanner -ArgumentList @('-Scan', '-ScanType', '3', '-File', ('"' + $target + '"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    while (-not $process.WaitForExit(5000)) {
        if (([DateTimeOffset]::UtcNow - $started).TotalMinutes -gt 15) {
            throw "Defender scan did not complete within 15 minutes: $kind"
        }
    }
    $results += [ordered]@{target=$target; exit_code=$process.ExitCode; started_utc=$started.ToString('o'); finished_utc=[DateTimeOffset]::UtcNow.ToString('o'); stdout_file=[IO.Path]::GetFileName($stdout); stderr_file=[IO.Path]::GetFileName($stderr)}
    if ($process.ExitCode -ne 0) { throw "Defender reported a detection or scan error ($($process.ExitCode)): $kind" }
}
$after = Get-MpComputerStatus
$signature = Get-AuthenticodeSignature -LiteralPath $exe
$details = (Get-Item -LiteralPath $exe).VersionInfo
$report = [ordered]@{
    product='123mshub'; version=$Version; scanner=$scanner
    antivirus_enabled=$after.AntivirusEnabled; realtime_enabled=$after.RealTimeProtectionEnabled
    engine_version=$after.AMEngineVersion; signature_version=$after.AntivirusSignatureVersion
    signature_updated=$after.AntivirusSignatureLastUpdated.ToString('o')
    signature_version_before=$before.AntivirusSignatureVersion
    scans=$results; authenticode=$signature.Status.ToString()
    exe_file_version=$details.FileVersion; exe_product_version=$details.ProductVersion
    exe_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    zip_sha256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    limitations='Current-host Microsoft Defender custom scans only; unsigned application. Other AV, SmartScreen reputation, and other computers are not covered.'
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $release 'defender-scan.json') -Encoding UTF8
$report | ConvertTo-Json -Depth 8
