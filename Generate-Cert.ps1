param([string]$PortalIP)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $PortalIP) { $PortalIP = Read-Host 'Enter the fixed Portal IPv4 address (from ipconfig)' }
$parsedIP = $null
if (-not [System.Net.IPAddress]::TryParse($PortalIP, [ref]$parsedIP) -or $parsedIP.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'Enter a valid IPv4 address.' }
$PortalIP = $parsedIP.ToString()
New-Item -ItemType Directory -Force -Path .\ssl\certs | Out-Null
$sslFolder = (Resolve-Path .\ssl).Path
# Uses cryptography already installed in the existing web image.
docker compose run --rm --no-deps --user root --volume "${sslFolder}:/ssl" web python /ssl/generate-cert.py --ip $PortalIP
if ($LASTEXITCODE -ne 0) { throw 'Certificate generation failed. HTTPS has not been started.' }
Set-Content -Path .\ssl\portal-ip.txt -Value $PortalIP -Encoding ASCII
Write-Host "Certificate ready for https://$PortalIP . Run Start-HTTPS.ps1 next."
