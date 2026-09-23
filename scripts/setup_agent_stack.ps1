param(
    [switch]$SkipSpecKitInit
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install uv first, then rerun this script."
}

Write-Host "Installing pinned agent tooling..." -ForegroundColor Cyan

# Spec Kit v1.0.10 requires Python 3.11+.
uv tool install --python 3.11 specify-cli --from "git+https://github.com/github/spec-kit.git@v1.0.10" --force

# Keep OpenHarness isolated from the application's runtime dependencies.
uv tool install --python 3.11 openharness-ai==0.1.9 --force

if (-not $SkipSpecKitInit) {
    if (Test-Path ".specify") {
        Write-Host ".specify already exists; skipping destructive re-initialization." -ForegroundColor Yellow
        Write-Host "Inspect it with: specify integration status"
    }
    else {
        Write-Host "Initializing Spec Kit for the existing repository with Codex integration..." -ForegroundColor Cyan
        # Use uvx for this first invocation so setup does not depend on PATH refresh.
        uvx --python 3.11 --from "git+https://github.com/github/spec-kit.git@v1.0.10" specify init --here --force --integration codex
    }
}

# Ensure future shells can resolve uv-managed tool executables.
uv tool update-shell | Out-Null

Write-Host ""
Write-Host "Installed:" -ForegroundColor Green
Write-Host "  Spec Kit:     v1.0.10"
Write-Host "  OpenHarness:  v0.1.9"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open a new PowerShell window so uv's tool PATH is active."
Write-Host "  2. Run: specify integration status"
Write-Host "  3. Run: oh setup"
Write-Host "  4. Configure the provider you want OpenHarness to use (Codex Subscription is supported)."
Write-Host "  5. Run: oh --dry-run"
Write-Host ""
Write-Host "Spec Kit's Codex skills are generated under .agents/skills and are also discoverable by OpenHarness."
