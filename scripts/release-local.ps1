<#
.SYNOPSIS
  Builds the tp-mcp-coach wheel + sdist locally and uploads them as assets
  on the matching GitHub Release.

.DESCRIPTION
  - Reads the version from pyproject.toml.
  - Runs `uv build` (or falls back to `python -m build`) into ./dist.
  - Ensures a tag vX.Y.Z exists (creates and pushes it if missing).
  - Ensures a GitHub Release vX.Y.Z exists (creates it if missing) using `gh`.
  - Uploads the freshly built dist/* files to that release, overwriting
    any existing assets with the same name.

.PREREQUISITES
  - GitHub CLI installed and authenticated:    winget install GitHub.cli ; gh auth login
  - Either `uv` (recommended) or Python's `build` package installed.

.EXAMPLE
  pwsh ./scripts/release-local.ps1
  pwsh ./scripts/release-local.ps1 -SkipTagPush   # build & upload without touching git tags
#>

[CmdletBinding()]
param(
    [switch]$SkipTagPush,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# --- Read version from pyproject.toml ---------------------------------------
$pyproject = Get-Content -Raw -Path (Join-Path $repoRoot 'pyproject.toml')
if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not find version in pyproject.toml"
}
$version = $Matches[1]
$tag = "v$version"
Write-Host "Package version: $version  (tag: $tag)" -ForegroundColor Cyan

# --- Sanity check tools ------------------------------------------------------
function Test-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

if (-not (Test-Command 'gh')) {
    throw "GitHub CLI (gh) is required. Install with: winget install GitHub.cli, then 'gh auth login'."
}

# --- Clean dist --------------------------------------------------------------
$distDir = Join-Path $repoRoot 'dist'
if ($Clean -and (Test-Path $distDir)) {
    Write-Host "Cleaning $distDir" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $distDir
}
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

# --- Build -------------------------------------------------------------------
if (Test-Command 'uv') {
    Write-Host "Building with uv..." -ForegroundColor Cyan
    uv build
} else {
    Write-Host "uv not found; building with 'python -m build'..." -ForegroundColor Yellow
    python -m pip install --upgrade build | Out-Null
    python -m build
}

$artifacts = Get-ChildItem -Path $distDir -File | Where-Object {
    $_.Name -like "*$version*" -and ($_.Extension -in '.whl', '.gz')
}
if (-not $artifacts) {
    throw "No build artifacts found in $distDir matching version $version"
}
Write-Host "Built artifacts:" -ForegroundColor Green
$artifacts | ForEach-Object { Write-Host "  $($_.Name)" }

# --- Ensure tag exists locally + remotely -----------------------------------
if (-not $SkipTagPush) {
    $localTag = git tag --list $tag
    if (-not $localTag) {
        Write-Host "Creating local tag $tag" -ForegroundColor Cyan
        git tag $tag
    }
    $remoteTag = git ls-remote --tags origin "refs/tags/$tag"
    if (-not $remoteTag) {
        Write-Host "Pushing tag $tag to origin" -ForegroundColor Cyan
        git push origin $tag
    } else {
        Write-Host "Tag $tag already on origin" -ForegroundColor DarkGray
    }
}

# --- Ensure GitHub Release exists -------------------------------------------
$releaseExists = $true
try {
    gh release view $tag --json tagName 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { $releaseExists = $false }
} catch { $releaseExists = $false }

if (-not $releaseExists) {
    Write-Host "Creating GitHub Release $tag" -ForegroundColor Cyan
    gh release create $tag --title $tag --generate-notes
    if ($LASTEXITCODE -ne 0) { throw "gh release create failed" }
} else {
    Write-Host "GitHub Release $tag already exists; will upload (and overwrite) assets" -ForegroundColor DarkGray
}

# --- Upload assets -----------------------------------------------------------
Write-Host "Uploading assets to release $tag" -ForegroundColor Cyan
$paths = $artifacts | ForEach-Object { $_.FullName }
gh release upload $tag @paths --clobber
if ($LASTEXITCODE -ne 0) { throw "gh release upload failed" }

Write-Host ""
Write-Host "Done. Release URL:" -ForegroundColor Green
gh release view $tag --json url --jq .url
