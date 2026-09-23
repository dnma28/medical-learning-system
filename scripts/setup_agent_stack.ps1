param(
    [switch]$SkipSpecKitInit,
    [switch]$SkipSuperpowers
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

if (-not $SkipSuperpowers) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $ToolsRoot = Join-Path $RepoRoot ".agent-tools"
        $SuperpowersDir = Join-Path $ToolsRoot "superpowers"
        New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null

        if (Test-Path (Join-Path $SuperpowersDir ".git")) {
            Write-Host "Refreshing Superpowers checkout to v6.4.1..." -ForegroundColor Cyan
            git -C $SuperpowersDir fetch --tags --force
            git -C $SuperpowersDir checkout --force v6.4.1
        }
        else {
            if (Test-Path $SuperpowersDir) { Remove-Item -Recurse -Force $SuperpowersDir }
            Write-Host "Cloning Superpowers v6.4.1..." -ForegroundColor Cyan
            git clone --depth 1 --branch v6.4.1 https://github.com/obra/superpowers.git $SuperpowersDir
        }

        Write-Host "Installing Superpowers into OpenHarness..." -ForegroundColor Cyan
        uvx --python 3.11 --from "openharness-ai==0.1.9" oh plugin install $SuperpowersDir
        if ($LASTEXITCODE -eq 0) {
            uvx --python 3.11 --from "openharness-ai==0.1.9" oh plugin enable superpowers
        }
        else {
            Write-Host "Superpowers checkout is present, but OpenHarness plugin installation failed. See docs/AGENT_STACK.md." -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "git was not found; Superpowers installation was skipped." -ForegroundColor Yellow
    }
}

# Ensure future shells can resolve uv-managed tool executables.
uv tool update-shell | Out-Null

Write-Host ""
Write-Host "Installed:" -ForegroundColor Green
Write-Host "  Spec Kit:     v1.0.10"
Write-Host "  OpenHarness:  v0.1.9"
if (-not $SkipSuperpowers) { Write-Host "  Superpowers:  v6.4.1 (OpenHarness plugin when installation succeeds)" }
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Open a new PowerShell window so uv's tool PATH is active."
Write-Host "  2. Run: specify integration status"
Write-Host "  3. Run: oh setup"
Write-Host "  4. Configure the provider you want OpenHarness to use (Codex Subscription is supported)."
Write-Host "  5. Run: oh --dry-run"
Write-Host "  6. For native Codex, open /plugins and install Superpowers from the official marketplace if you also want it there."
Write-Host ""
Write-Host "Spec Kit's Codex skills are generated under .agents/skills and are also discoverable by OpenHarness."
