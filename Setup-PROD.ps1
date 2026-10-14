param(
 [string]$PortalIP,
 [string]$AdminEmail,
 [Security.SecureString]$AdminPassword
)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (Test-Path -LiteralPath '.env') { throw 'Existing .env found. Setup never resets existing data/configuration. Use Start-HTTPS.ps1 for normal starts.' }
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers first.' }
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required.' }
if (-not $PortalIP) { $PortalIP=Read-Host 'Enter the fixed PROD IPv4 address (ipconfig)' }
$parsed=$null
if (-not [Net.IPAddress]::TryParse($PortalIP,[ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or [Net.IPAddress]::IsLoopback($parsed) -or $parsed.ToString() -eq '0.0.0.0') { throw 'Use the PROD computer LAN IPv4 address.' }
$PortalIP=$parsed.ToString()
if (-not $AdminEmail) { $AdminEmail=Read-Host 'Enter the PROD administrator email' }
$AdminEmail=$AdminEmail.Trim().ToLowerInvariant()
try { $address=[Net.Mail.MailAddress]::new($AdminEmail) } catch { throw 'Invalid administrator email.' }
if ($address.Address -ne $AdminEmail) { throw 'Enter only the email address.' }
if (-not $AdminPassword) { $AdminPassword=Read-Host 'Set the PROD administrator password (minimum 12 characters)' -AsSecureString }
$plain=[Net.NetworkCredential]::new('',$AdminPassword).Password
if ($plain.Length -lt 12 -or $plain.Length -gt 200 -or $plain.Contains("`n") -or $plain.Contains("`r")) { throw 'Password must contain 12 to 200 characters, without newlines.' }
# Avoid adopting existing volumes, even on a machine with another deployment.
$existing=@(& docker volume ls --format '{{.Name}}')
if ($LASTEXITCODE -ne 0) { throw 'Unable to list Docker volumes.' }
foreach ($volume in @('momcc-prod_mysql_data','momcc-prod_attachments_data')) {
 if ($existing -contains $volume) { throw "Existing PROD volume found: $volume. Stop and check it; setup will not reuse or delete it." }
}
function New-RandomPassword {
 $bytes=New-Object byte[] 24
 $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
 try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
 return ([BitConverter]::ToString($bytes)).Replace('-','').ToLowerInvariant()
}
function DotEnv([string]$Value) { return "'"+$Value.Replace("'","\'")+"'" }
$lines=@(
 '# PROD v0.1 - local secrets. Do not commit or share this file.',
 ('MYSQL_ROOT_PASSWORD='+ (New-RandomPassword)),
 ('MYSQL_PASSWORD='+ (New-RandomPassword)),
 ('ADMIN_EMAIL='+ (DotEnv $AdminEmail)),
 ('ADMIN_PASSWORD='+ (DotEnv $plain)),
 'COOKIE_SECURE=true',
 ('SSL_BIND_IP='+$PortalIP),
 ('PORTAL_URL=https://'+$PortalIP),
 'ARCHIVE_HOST_PATH=./MOMCC_Archive',
 'ARCHIVE_ENABLED=true','ARCHIVE_PURGE_ENABLED=false',
 'WAHA_ENABLED=false','WAHA_URL=','WAHA_API_KEY=','WAHA_SESSION=default','WAHA_GROUP_CHAT_ID='
)
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot '.env'),$lines,[Text.UTF8Encoding]::new($false))
$plain=$null
foreach ($folder in @('logs','MOMCC_Archive')) { New-Item -ItemType Directory -Path $folder -Force | Out-Null }
foreach ($volume in @('momcc-prod_mysql_data','momcc-prod_attachments_data')) {
 & docker volume create $volume | Out-Null
 if ($LASTEXITCODE -ne 0) { throw 'Volume creation failed. Preserve .env and inspect Docker; do not delete existing volumes.' }
}
& (Join-Path $PSScriptRoot 'scripts/Initialize-Archive.ps1')
$compose=@('-f','compose.yaml','-f','compose.override.yaml')
& docker compose @compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed.' }
& docker compose @compose build web scheduler
if ($LASTEXITCODE -ne 0) { throw 'Build failed. Fix Docker/network access, then run Resume-PROD.ps1.' }
& (Join-Path $PSScriptRoot 'Generate-Cert.ps1') -PortalIP $PortalIP
& (Join-Path $PSScriptRoot 'Start-HTTPS.ps1')
Write-Output 'PROD v0.1 initialized with a fresh database. No UAT records or users were imported.'
Write-Output 'Import ssl\certs\root-ca.cer on each client, then open the HTTPS address shown above.'
