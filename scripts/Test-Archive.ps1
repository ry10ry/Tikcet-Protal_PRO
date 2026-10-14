param([string]$ArchivePath=(Join-Path (Split-Path -Parent $PSScriptRoot) 'MOMCC_Archive'))
$ErrorActionPreference='Stop'
$ArchivePath=(Resolve-Path -LiteralPath $ArchivePath).Path
[guid]::Parse([IO.File]::ReadAllText((Join-Path $ArchivePath '.momcc-archive-target')).Trim()) | Out-Null
$records=0;$files=0
foreach ($manifest in Get-ChildItem -LiteralPath $ArchivePath -Filter manifest.json -File -Recurse) {
    $folder=[IO.Path]::GetFullPath($manifest.Directory.FullName)+[IO.Path]::DirectorySeparatorChar
    foreach ($item in (Get-Content -LiteralPath $manifest.FullName -Raw | ConvertFrom-Json)) {
        $path=[IO.Path]::GetFullPath((Join-Path $folder $item.path))
        if (-not $path.StartsWith($folder,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe manifest path.' }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing archive file: $path" }
        if ((Get-Item -LiteralPath $path).Length -ne $item.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) {
            throw "Archive integrity verification failed: $path"
        }
        $files++
    }
    $records++
}
Write-Output "Archive verification passed: $records records, $files files."
Write-Output 'This verifies the archive copies; it does not delete online files.'
