# Continue an interrupted installation without replacing credentials or volumes.
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.env')) { throw 'Run Setup-PROD.ps1 first.' }
$existing=@(& docker volume ls --format '{{.Name}}')
if ($LASTEXITCODE -ne 0) { throw 'Unable to list Docker volumes.' }
foreach ($volume in @('momcc-prod_mysql_data','momcc-prod_attachments_data')) {
 if ($existing -notcontains $volume) { & docker volume create $volume|Out-Null;if($LASTEXITCODE -ne 0){throw 'Volume creation failed'} }
}
foreach ($folder in @('logs','MOMCC_Archive')) { New-Item -ItemType Directory -Path $folder -Force|Out-Null }
& (Join-Path $PSScriptRoot 'scripts/Initialize-Archive.ps1')
$ipLine=Get-Content -LiteralPath '.env' | Where-Object {$_ -match '^SSL_BIND_IP='} | Select-Object -First 1
if (-not $ipLine) { throw 'SSL_BIND_IP missing from .env.' }
$ip=($ipLine -split '=',2)[1].Trim()
& docker compose -f compose.yaml -f compose.override.yaml build web scheduler
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
if (-not (Test-Path 'ssl/certs/server.crt') -or -not (Test-Path 'ssl/certs/server.key')) { & (Join-Path $PSScriptRoot 'Generate-Cert.ps1') -PortalIP $ip }
& (Join-Path $PSScriptRoot 'Start-HTTPS.ps1')
