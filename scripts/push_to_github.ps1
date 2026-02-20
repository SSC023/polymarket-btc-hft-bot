# Push Polymarket HFT Bot to GitHub
# Run from project root: .\scripts\push_to_github.ps1
# Or: powershell -ExecutionPolicy Bypass -File scripts\push_to_github.ps1

param(
    [string]$RepoName = "polymarket-btc-hft-bot",
    [string]$Description = "24/7 high-frequency trading bot for Polymarket BTC 15-minute markets"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# Check git
try {
    git --version | Out-Null
} catch {
    Write-Host "ERROR: Git is not installed or not in PATH. Install from https://git-scm.com/" -ForegroundColor Red
    exit 1
}

# Init if needed
if (-not (Test-Path ".git")) {
    Write-Host "Initializing git repository..." -ForegroundColor Cyan
    git init
}

# Add and commit
Write-Host "Staging files..." -ForegroundColor Cyan
git add -A
git status

$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit (all changes already committed)." -ForegroundColor Yellow
} else {
    Write-Host "Committing..." -ForegroundColor Cyan
    git commit -m "Initial commit: Polymarket BTC 15m HFT bot"
}

# Try GitHub CLI
$useGh = $false
try {
    $ghVersion = gh --version 2>&1
    if ($LASTEXITCODE -eq 0) { $useGh = $true }
} catch { }

if ($useGh) {
    Write-Host "Using GitHub CLI to create repo and push..." -ForegroundColor Cyan
    gh repo create $RepoName --public --source=. --remote=origin --push --description $Description
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Done! Repo: https://github.com/$env:USERNAME/$RepoName" -ForegroundColor Green
        exit 0
    }
}

# Fallback: manual instructions
Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "MANUAL STEPS - Create repo on GitHub and push:" -ForegroundColor Yellow
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "1. Go to https://github.com/new"
Write-Host "2. Create repository: $RepoName"
Write-Host "3. Do NOT initialize with README (we already have files)"
Write-Host ""
Write-Host "4. Run these commands in this folder:" -ForegroundColor White
Write-Host "   git remote add origin https://github.com/YOUR_USERNAME/$RepoName.git"
Write-Host "   git branch -M main"
Write-Host "   git push -u origin main"
Write-Host ""
