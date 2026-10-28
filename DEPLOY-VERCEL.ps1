$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$bundledNode = Join-Path $PSScriptRoot '.tools/node-v22.23.4-win-x64/node.exe'
if ($nodeCommand) { $nodeExe = $nodeCommand.Source }
elseif (Test-Path -LiteralPath $bundledNode) { $nodeExe = $bundledNode }
else { throw 'Node.js 22+ is required. Install Node or restore the local portable Node tools.' }
$env:PATH = (Split-Path -Parent $nodeExe) + ';' + $env:PATH
& $nodeExe scripts/build.mjs
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Host 'Deploying the frontend. Your recordings stay on your PC.' -ForegroundColor Green
$localVercel = Join-Path $PSScriptRoot '.tools/vercel-cli/node_modules/vercel/dist/index.js'
$globalVercel = Get-Command vercel.cmd -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $localVercel) { & $nodeExe $localVercel deploy --prod }
elseif ($globalVercel) { & $globalVercel.Source --prod }
else {
    throw 'Vercel CLI is required. Install it locally with npm install --prefix .tools/vercel-cli vercel, then sign in with that CLI.'
}
if ($LASTEXITCODE -ne 0) { throw 'Vercel deployment failed. Inspect its build logs before retrying.' }
