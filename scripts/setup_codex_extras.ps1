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

$MattPocockCommit = "c55ee46073ed923f86ce59a5eb3b6d895095d1b7"
$CavemanCommit = "2fd153c67988e980fb0b2455c90832159a6a5a25"
$GraphifyCommit = "8e09034743280ecc5ff2201b27c0ccae31f61966"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ToolsRoot = Join-Path $RepoRoot ".agent-tools\codex-extras"
Set-Location $RepoRoot

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required for this Codex tooling setup."
    }
}

function Sync-PinnedRepo {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Commit
    )

    $Destination = Join-Path $ToolsRoot $Name
    New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null

    if (-not (Test-Path (Join-Path $Destination ".git"))) {
        if (Test-Path $Destination) {
            Remove-Item -Recurse -Force $Destination
        }

        git clone --filter=blob:none --no-checkout $Url $Destination | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to clone $Name."
        }
    }

    git -C $Destination fetch --force origin $Commit | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to fetch pinned commit for $Name."
    }

    git -C $Destination checkout --detach --force $Commit | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to checkout pinned commit for $Name."
    }

    return $Destination
}

if (-not $SkipMattPocockSkills -or -not $SkipCaveman -or -not $SkipGraphify) {
    Assert-Command "npx"
    Assert-Command "git"
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
    $MattPocockDir = Sync-PinnedRepo -Name "mattpocock-skills" -Url "https://github.com/mattpocock/skills.git" -Commit $MattPocockCommit

    & npx -y "skills@$SkillsCliVersion" add $MattPocockDir --skill '*' --agent codex --global --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Matt Pocock skills installation failed."
    }

    Write-Host "Installed Matt Pocock skill bundle at $MattPocockCommit, including grill-me and to-prd." -ForegroundColor Green
}

if (-not $SkipCaveman) {
    Write-Host ""
    Write-Host "Installing Caveman skills for Codex..." -ForegroundColor Cyan
    $CavemanDir = Sync-PinnedRepo -Name "caveman" -Url "https://github.com/JuliusBrussee/caveman.git" -Commit $CavemanCommit

    & npx -y "skills@$SkillsCliVersion" add $CavemanDir --skill '*' --agent codex --global --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Caveman skills installation failed."
    }

    Write-Host "Installed Caveman skills at $CavemanCommit. Keep them explicit-only for this repository." -ForegroundColor Green
}

if (-not $SkipGraphify) {
    Write-Host ""
    Write-Host "Installing Graphify CLI $GraphifyVersion..." -ForegroundColor Cyan
    & uv tool install --python 3.11 "graphifyy==$GraphifyVersion" --force
    if ($LASTEXITCODE -ne 0) {
        throw "Graphify CLI installation failed."
    }

    Write-Host "Installing the Graphify agent skill for Codex..." -ForegroundColor Cyan
    $GraphifyDir = Sync-PinnedRepo -Name "graphify" -Url "https://github.com/Graphify-Labs/graphify.git" -Commit $GraphifyCommit

    & npx -y "skills@$SkillsCliVersion" add $GraphifyDir --skill graphify --agent codex --global --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Graphify skill installation failed."
    }

    Write-Host "Installed Graphify CLI + Codex skill at $GraphifyCommit." -ForegroundColor Green
}

if (-not $SkipGitNexus) {
    Write-Host ""
    Write-Host "Adding GitNexus Codex plugin marketplace pinned to v$GitNexusVersion..." -ForegroundColor Cyan
    & codex plugin marketplace add abhigyanpatwari/GitNexus --ref "v$GitNexusVersion"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Marketplace add returned non-zero. It may already be registered; verify its pinned ref in Codex before continuing." -ForegroundColor Yellow
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
    Write-Host "  Matt Pocock skills: $MattPocockCommit via skills@$SkillsCliVersion"
    Write-Host "    Includes: grill-me, to-prd, setup-matt-pocock-skills, and the rest of the bundle"
}
if (-not $SkipCaveman) { Write-Host "  Caveman: $CavemanCommit" }
if (-not $SkipGraphify) { Write-Host "  Graphify: graphifyy==$GraphifyVersion + skill $GraphifyCommit" }
if (-not $SkipGitNexus) { Write-Host "  GitNexus: Codex plugin marketplace pinned to v$GitNexusVersion" }

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
