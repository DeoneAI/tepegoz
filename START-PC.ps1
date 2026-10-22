$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Sensorlink Week 01 - PC collector' -ForegroundColor Green
$siteOrigin = Read-Host 'Frontend origin (e.g. https://your-site.vercel.app), or Enter for local preview'
$origins = @('http://localhost:8787', 'http://127.0.0.1:8787')
if ($siteOrigin) {
    $siteUri = [Uri]$siteOrigin
    if ($siteUri.Scheme -ne 'https' -or $siteUri.AbsolutePath -ne '/') { throw 'Enter only an HTTPS origin.' }
    $origins += $siteUri.GetLeftPart([System.UriPartial]::Authority)
}
$env:ALLOWED_ORIGINS = $origins -join ','
node pc/server.mjs
