param(
    [switch]$SkipPromptfoo
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is required. Install Python 3.10+ first."
    }
    Write-Host "Creating .venv..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "Installing project evaluation extra (Ragas 0.4.3)..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e ".[eval]"

if (-not $SkipPromptfoo) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        $PromptfooRoot = Join-Path $RepoRoot ".agent-tools\promptfoo"
        New-Item -ItemType Directory -Force -Path $PromptfooRoot | Out-Null
        Write-Host "Installing Promptfoo 0.123.1 locally..." -ForegroundColor Cyan
        npm install --prefix $PromptfooRoot "promptfoo@0.123.1"
        $PromptfooCmd = Join-Path $PromptfooRoot "node_modules\.bin\promptfoo.cmd"
        if (Test-Path $PromptfooCmd) {
            & $PromptfooCmd --version
        }
    }
    else {
        Write-Host "npm was not found; Promptfoo was skipped. Install Node.js and rerun this script." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Quality tooling ready." -ForegroundColor Green
Write-Host "Ragas is available inside .venv through the [eval] extra."
Write-Host "Promptfoo is local-only under .agent-tools/promptfoo when npm is available."
Write-Host "Neither tool may promote claims into the Canonical Medical KG; they only evaluate system behavior."
