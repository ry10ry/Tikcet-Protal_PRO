$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .\ssl\portal-ip.txt)) { throw 'Run Generate-Cert.ps1 first.' }
$env:SSL_BIND_IP = (Get-Content .\ssl\portal-ip.txt -Raw).Trim()
$composeArgs = @()
$baseFile = @('compose.yaml','compose.yml','docker-compose.yaml','docker-compose.yml') | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $baseFile) { throw 'Copy these files into the existing ServiceDesk project directory.' }
$composeArgs += @('-f', $baseFile)
$overrideFile = @('compose.override.yaml','compose.override.yml','docker-compose.override.yaml','docker-compose.override.yml') | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($overrideFile) { $composeArgs += @('-f', $overrideFile) }
$composeArgs += @('-f','compose.ssl.yaml')
docker compose @composeArgs up -d web scheduler proxy
if ($LASTEXITCODE -ne 0) { throw 'HTTPS startup failed. Check the Docker output above.' }
docker compose @composeArgs exec -T proxy nginx -t
if ($LASTEXITCODE -ne 0) { throw 'Nginx HTTPS configuration validation failed.' }
docker compose @composeArgs exec -T proxy nginx -s reload
if ($LASTEXITCODE -ne 0) { throw 'Nginx reload failed.' }
Write-Host "Open https://$env:SSL_BIND_IP . Import ssl\certs\root-ca.cer on each client."
