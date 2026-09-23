param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $BundleRoot).Path
$internal = Join-Path $root "_internal"
$qtRoot = Join-Path $internal "PySide6"
if (-not (Test-Path -LiteralPath $internal -PathType Container)) {
    throw "不是 PyInstaller onedir 目录，缺少 _internal：$root"
}
if (-not (Test-Path -LiteralPath $qtRoot -PathType Container)) {
    throw "不是 PySide6 onedir 目录，缺少 PySide6：$root"
}

function Remove-IfPresent([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $resolved = (Resolve-Path -LiteralPath $Path).Path
        if (-not $resolved.StartsWith($qtRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "裁剪路径越界：$resolved"
        }
        Remove-Item -LiteralPath $resolved -Force
    }
}

# QtWebEngine ships debug/devtools packs beside the release packs. The native
# shell never opens Chromium DevTools, so carrying them would add ~88 MB while
# providing no runtime capability.
$resources = Join-Path $qtRoot "resources"
Get-ChildItem -LiteralPath $resources -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "*.debug.pak" -or $_.Name -like "*.debug.bin" -or $_.Name -like "qtwebengine_devtools_resources.pak" } |
    ForEach-Object { Remove-IfPresent $_.FullName }

# v1.4.0 ships a Chinese UI and an English fallback. Chromium locale packs are
# independent of Qt's .qm translations; retain only the two supported locales.
$locales = Join-Path $qtRoot "translations\qtwebengine_locales"
if (Test-Path -LiteralPath $locales -PathType Container) {
    Get-ChildItem -LiteralPath $locales -File |
        Where-Object { $_.Name -notin @("zh-CN.pak", "en-US.pak") } |
        ForEach-Object { Remove-IfPresent $_.FullName }
}

# Keep the two UI locales plus the WebEngine/QML fallback catalogues. The
# stock wheel also carries translations for every Qt language and module.
$keepQm = @(
    "qt_en.qm", "qt_zh_CN.qm", "qt_help_en.qm", "qt_help_zh_CN.qm",
    "qtbase_en.qm", "qtbase_zh_CN.qm",
    "qtdeclarative_en.qm", "qtdeclarative_zh_CN.qm",
    "qtlocation_en.qm", "qtlocation_zh_CN.qm",
    "qtwebengine_en.qm", "qtwebengine_zh_CN.qm"
)
$translationRoot = Join-Path $qtRoot "translations"
Get-ChildItem -LiteralPath $translationRoot -File -Filter "*.qm" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notin $keepQm } |
    ForEach-Object { Remove-IfPresent $_.FullName }

# QML tooling is for development/debugging and is not used by QWebEngineView.
# Keep platform, image, network, position, TLS and style plugins intact.
$qmlTooling = Join-Path $qtRoot "plugins\qmltooling"
if (Test-Path -LiteralPath $qmlTooling -PathType Container) {
    # Only remove files; do not recursively traverse or delete a computed
    # directory. All resolved files are verified against the bundle root.
    Get-ChildItem -LiteralPath $qmlTooling -File | ForEach-Object { Remove-IfPresent $_.FullName }
}

Write-Host ("WebEngine runtime prune complete: {0:N2} MB" -f ((Get-ChildItem $root -Recurse -File | Measure-Object Length -Sum).Sum / 1MB))
