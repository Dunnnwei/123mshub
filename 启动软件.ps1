$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mshubExe = Join-Path $projectRoot ".venv\Scripts\mshub.exe"

Set-Location -LiteralPath $projectRoot

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "正在创建 Python 虚拟环境..."
    python -m venv .venv
}

Write-Host "正在确认 Python 依赖..."
& $venvPython -m pip install -e ".[gui,keyring]"

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "src\mshub\web\index.html"))) {
    Write-Host "正在构建前端..."
    Push-Location (Join-Path $projectRoot "web")
    try {
        npm install
        npm run build
    }
    finally {
        Pop-Location
    }
}

Write-Host "正在启动 mshub..."
& $mshubExe serve --gui

