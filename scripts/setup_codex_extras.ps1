param(
    [switch]$SkipMattPocockSkills,
    [switch]$SkipCaveman,
    [switch]$SkipGraphify,
    [switch]$SkipGitNexus
)

$ErrorActionPreference = "Stop"

$SkillsCliVersion = "1.7.0"
$GraphifyVersion = "0.9.67"
$GitNexusVersion = "1.6.12"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required for this Codex tooling setup."
    }
}

if (-not $SkipMattPocockSkills -or -not $SkipCaveman -or -not $SkipGraphify) {
    Assert-Command "npx"
}

if (-not $SkipGraphify) {
    Assert-Command "uv"
}

if (-not $SkipGitNexus) {
    Assert-Command "codex"
}

Write-Host "Installing optional Codex tooling..." -ForegroundColor Cyan
Write-Host "These tools are agent-side only; they are not added to the medical runtime." -ForegroundColor DarkGray

if (-not $SkipMattPocockSkills) {
    Write-Host ""
    Write-Host "Installing Matt Pocock skills for Codex..." -ForegroundColor Cyan
    & npx -y "skills@$SkillsCliVersion" add mattpocock/skills --skill '*' --agent codex --global --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Matt Pocock skills installation failed."
    }

    Write-Host "Installed Matt Pocock skill bundle, including grill-me and to-prd." -ForegroundColor Green
}

if (-not $SkipCaveman) {
    Write-Host ""
    Write-Host "Installing Caveman skills for Codex..." -ForegroundColor Cyan
    & npx -y "skills@$SkillsCliVersion" add JuliusBrussee/caveman --skill '*' --agent codex --global --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Caveman skills installation failed."
    }

    Write-Host "Installed Caveman skills. Keep them explicit-only for this repository." -ForegroundColor Green
}

if (-not $SkipGraphify) {
    Write-Host ""
    Write-Host "Installing Graphify CLI $GraphifyVersion..." -ForegroundColor Cyan
    & uv tool install --python 3.11 "graphifyy==$GraphifyVersion" --force
    if ($LASTEXITCODE -ne 0) {
        throw "Graphify CLI installation failed."
    }

    Write-Host "Installing the Graphify agent skill for Codex..." -ForegroundColor Cyan
    & npx -y "skills@$SkillsCliVersion" add Graphify-Labs/graphify --skill graphify --agent codex --global --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Graphify skill installation failed."
    }

    Write-Host "Installed Graphify CLI + Codex skill." -ForegroundColor Green
}

if (-not $SkipGitNexus) {
    Write-Host ""
    Write-Host "Adding GitNexus Codex plugin marketplace..." -ForegroundColor Cyan
    & codex plugin marketplace add abhigyanpatwari/GitNexus
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Marketplace add returned non-zero. It may already be registered; existing configuration was left untouched." -ForegroundColor Yellow
    }

    Write-Host "Installing GitNexus plugin..." -ForegroundColor Cyan
    & codex plugin add gitnexus@gitnexus-marketplace
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GitNexus plugin add returned non-zero. Open /plugins in Codex and verify whether GitNexus is already installed." -ForegroundColor Yellow
    }
    else {
        Write-Host "Installed GitNexus plugin $GitNexusVersion." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Codex extras configured:" -ForegroundColor Green
if (-not $SkipMattPocockSkills) {
    Write-Host "  Matt Pocock skills via skills@$SkillsCliVersion"
    Write-Host "    Includes: grill-me, to-prd, setup-matt-pocock-skills, and the rest of the bundle"
}
if (-not $SkipCaveman) { Write-Host "  Caveman skills from JuliusBrussee/caveman" }
if (-not $SkipGraphify) { Write-Host "  Graphify: graphifyy==$GraphifyVersion + global Codex skill" }
if (-not $SkipGitNexus) { Write-Host "  GitNexus: Codex plugin marketplace, expected release $GitNexusVersion" }

Write-Host ""
Write-Host "Next checks:" -ForegroundColor Cyan
Write-Host '  1. Restart Codex so newly installed global skills/plugins are discovered.'
Write-Host '  2. Run $setup-matt-pocock-skills once; use GitHub as this repository''s issue tracker.'
Write-Host '  3. Verify explicit skills with $grill-me, $to-prd, $caveman, and $graphify.'
Write-Host '  4. Open /plugins and verify GitNexus is enabled.'
Write-Host '  5. Open /hooks and explicitly approve GitNexus hooks before relying on them.'
Write-Host ""
Write-Host "Do not auto-run Graphify and GitNexus together on every task." -ForegroundColor Yellow
Write-Host "Use GitNexus for code dependency/impact analysis; use Graphify for broader mixed code/docs graph exploration."
