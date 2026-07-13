# Quick Cloudflare Tunnel to local skill-map server (port 5000).
# Requires cloudflared: winget install Cloudflare.cloudflared
$port = if ($env:PORT) { $env:PORT } else { "5000" }
$url = "http://localhost:$port"

function Find-Cloudflared {
  $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $candidates = @(
    "$env:ProgramFiles\cloudflared\cloudflared.exe",
    "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
  )
  foreach ($path in $candidates) {
    if (Test-Path $path) { return $path }
  }
  return $null
}

$cloudflared = Find-Cloudflared
if (-not $cloudflared) {
  Write-Error "cloudflared not found. Install with: winget install Cloudflare.cloudflared`nThen open a new terminal and run: npm run tunnel"
  exit 1
}

Write-Host "Starting Cloudflare quick tunnel -> $url"
Write-Host "Using: $cloudflared"
Write-Host "Keep this window open. Run 'npm run serve' in another terminal if not already running."
Write-Host ""

& $cloudflared tunnel --url $url
