$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
node scripts/build.mjs
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host 'Deploying the frontend. Your recordings stay on your PC.' -ForegroundColor Green
if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    Write-Host 'Vercel CLI is required. Install it with: npm install -g vercel'
    exit 1
}
vercel --prod
