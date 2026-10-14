param(
    [string]$ArchivePath=(Join-Path (Split-Path -Parent $PSScriptRoot) 'MOMCC_Archive'),
    [switch]$ConfigurePortal
)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Path $ArchivePath -Force | Out-Null
$marker=Join-Path $ArchivePath '.momcc-archive-target'
if (-not (Test-Path -LiteralPath $marker)) {
    [IO.File]::WriteAllText($marker,[guid]::NewGuid().ToString(),[Text.UTF8Encoding]::new($false))
}
[guid]::Parse([IO.File]::ReadAllText($marker).Trim()) | Out-Null
if ($ConfigurePortal) {
    $envFile=Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { throw 'Existing Portal .env file not found.' }
    $normalized=(Resolve-Path -LiteralPath $ArchivePath).Path.Replace('\','/').Replace('$','$$')
    $values=@{ARCHIVE_HOST_PATH=('"'+$normalized+'"');ARCHIVE_ENABLED='true';ARCHIVE_PURGE_ENABLED='false'}
    $lines=[Collections.Generic.List[string]]::new()
    foreach ($line in [IO.File]::ReadAllLines($envFile)) {
        $replaced=$false
        foreach ($key in @($values.Keys)) {
            if ($line -match ('^\s*'+$key+'\s*=')) {
                $lines.Add($key+'='+$values[$key]);$replaced=$true
            }
        }
        if (-not $replaced) { $lines.Add($line) }
    }
    foreach ($key in $values.Keys) {
        if (-not ($lines | Where-Object { $_ -match ('^'+$key+'=') })) { $lines.Add($key+'='+$values[$key]) }
    }
    $temporary=$envFile+'.archive.tmp'
    [IO.File]::WriteAllLines($temporary,$lines,[Text.UTF8Encoding]::new($false))
    [IO.File]::Replace($temporary,$envFile,$envFile+'.before-archive')
    Write-Output 'Portal .env configured for daily archive copies at 03:00 SGT. Online cleanup is disabled.'
}
Write-Output "Archive target initialized: $ArchivePath"
Write-Output 'Keep the marker when moving the complete archive to external storage. Online cleanup stays disabled by default.'
