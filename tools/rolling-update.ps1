# Rolling update for lab 6 (O6.4), PowerShell variant of rolling-update.sh: rebuild, then replace
# instances ONE BY ONE; the next one is replaced only when the new one answers GET /ready on its
# published port. Run from the project root:
#
#   .\tools\rolling-update.ps1                         # app-a, then app-b
#   .\tools\rolling-update.ps1 app-a app-b worker gateway-a gateway-b
#   $env:APP_TAG = "v2"; .\tools\rolling-update.ps1    # roll out the image tagged v2
#
# Meanwhile run the load in another terminal and count failed requests (the guide: <= 0.5 %).
# Services without /ready (publisher, worker, router) are replaced without waiting.
$ErrorActionPreference = "Stop"
$services = if ($args.Count -gt 0) { $args } else { @("app-a", "app-b") }
function Invoke-Docker {
  & docker @args
  if ($LASTEXITCODE -ne 0) { throw "docker failed (exit $LASTEXITCODE): $args" }
}

function Get-ReadyPort([string]$svc) {
  $binding = @(Invoke-Docker compose port $svc 8000)[0]
  if ($binding -notmatch ':(\d+)$') { throw "No published readiness port for $svc" }
  return [int]$Matches[1]
}

function Wait-Ready([string]$svc, [int]$port) {
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing "http://localhost:$port/ready" -TimeoutSec 2
      if ($r.StatusCode -eq 200) { Write-Host "  $svc is ready"; return }
    } catch { }
    Start-Sleep -Seconds 1
  }
  throw "$svc is NOT ready after 60 s - stopping here; the other instances still serve"
}

Write-Host "building: $services"
Invoke-Docker compose build @services
foreach ($svc in $services) {
  Write-Host "replacing $svc"
  Invoke-Docker compose up -d --no-deps --force-recreate $svc
  if ($svc -match '^(app-|gateway-)') {
    Wait-Ready $svc (Get-ReadyPort $svc)
    Invoke-Docker compose exec -T nginx nginx -t
    Invoke-Docker compose exec -T nginx nginx -s reload
    Start-Sleep -Seconds 3
  }
}
Write-Host "done: $services replaced"
