# Start the Tepegoz collector. It prints one sign-in link: open it in your browser.
# Phone over Wi-Fi: the dashboard starts a secure link for you (needs cloudflared once:
#   winget install --id Cloudflare.cloudflared). Phone over USB: install Android Platform-Tools.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
node --env-file-if-exists=.env pc/server.mjs @args
