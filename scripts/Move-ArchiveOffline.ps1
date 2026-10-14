param(
    [Parameter(Mandatory=$true)][string]$Destination,
    [string]$StagingPath=(Join-Path (Split-Path -Parent $PSScriptRoot) 'MOMCC_Archive')
)
$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
$StagingPath=(Resolve-Path -LiteralPath $StagingPath).Path
# Require an existing connected destination. Never create a missing drive root.
$Destination=(Resolve-Path -LiteralPath $Destination).Path
$source=[IO.Path]::GetFullPath($StagingPath).TrimEnd('\','/')
$dest=[IO.Path]::GetFullPath($Destination).TrimEnd('\','/')
if ($source.Equals($dest,[StringComparison]::OrdinalIgnoreCase) -or $dest.StartsWith($source+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or $source.StartsWith($dest+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Destination and staging must be separate folders.' }
if ([IO.Path]::GetPathRoot($source).Equals([IO.Path]::GetPathRoot($dest),[StringComparison]::OrdinalIgnoreCase)) { throw 'Use an external drive on a different drive letter from staging.' }
$marker='.momcc-archive-target'
$target=[IO.File]::ReadAllText((Join-Path $source $marker)).Trim()
[guid]::Parse($target)|Out-Null
$destMarker=Join-Path $dest $marker
if (Test-Path -LiteralPath $destMarker) {
 if ([IO.File]::ReadAllText($destMarker).Trim() -ne $target) { throw 'Destination belongs to another archive target.' }
} else { [IO.File]::WriteAllText($destMarker,$target,[Text.UTF8Encoding]::new($false)) }
$records=@()
# Only immutable per-record folders are transferred. New staged records can be
# generated meanwhile; the receipt covers this exact snapshot only.
foreach ($kind in @('FAULT','CR','SR')) {
 $kindPath=Join-Path $source $kind
 if (-not (Test-Path -LiteralPath $kindPath)) { continue }
 foreach ($record in Get-ChildItem -LiteralPath $kindPath -Directory) {
  $manifest=Join-Path $record.FullName 'manifest.json'
  if (-not (Test-Path -LiteralPath $manifest)) { continue }
  $folder=$kind+'/'+$record.Name
  $output=Join-Path $dest $folder
  if (Test-Path -LiteralPath $output) {
   if (-not (Test-Path -LiteralPath (Join-Path $output 'manifest.json')) -or (Get-FileHash -LiteralPath (Join-Path $output 'manifest.json') -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash) { throw "Existing destination differs: $folder" }
  } else {
   $parent=Join-Path $dest $kind
   New-Item -ItemType Directory -Path $parent -Force|Out-Null
   $partial=Join-Path $parent ('.partial-'+[guid]::NewGuid().ToString('N'))
   Copy-Item -LiteralPath $record.FullName -Destination $partial -Recurse
   Move-Item -LiteralPath $partial -Destination $output
  }
  $records+=@{folder=$folder;manifest_sha256=(Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash.ToLowerInvariant()}
 }
}
& (Join-Path $PSScriptRoot 'Test-Archive.ps1') -ArchivePath $dest
if ($records.Count -eq 0) { Write-Output 'No staged records to move.';exit 0 }
# Rebuild the external offline catalogue from every archived summary, preserving
# existing records from earlier transfers. The Portal helper supplies the same
# self-contained renderer without requiring an external drive Docker mount.
$receiptName='.export-'+[guid]::NewGuid().ToString('N')+'.json'
$receipt=Join-Path $source $receiptName
$payload=@{target=$target;location=$dest;records=@($records)}|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($receipt,$payload,[Text.UTF8Encoding]::new($false))
$previousEncoding=$OutputEncoding
$OutputEncoding=[Text.UTF8Encoding]::new($false)
Push-Location $project
try {
 $compose=@('compose','-f','compose.yaml','-f','compose.override.yaml','-f','compose.ssl.yaml')
 # Render using destination summaries, including previous batches, by passing
 # their data through stdin; only the local staging is mounted in Docker.
 $rows=@()
 foreach ($summary in Get-ChildItem -LiteralPath $dest -Filter summary.json -File -Recurse) {
  $row=Get-Content -LiteralPath $summary.FullName -Raw|ConvertFrom-Json
  $relative=$summary.Directory.FullName.Substring($dest.Length+1).Replace('\','/')+'/index.html'
  $row|Add-Member -NotePropertyName path -NotePropertyValue $relative -Force
  $rows+= $row
 }
 $rowJson=ConvertTo-Json -InputObject @($rows) -Depth 10 -Compress
 $renderer="import app.main; from app.archive import page; import sys,json,base64; print(base64.b64encode(page(json.load(sys.stdin),True)).decode())"
 $encoded=$rowJson | & docker @compose exec -T web python -c $renderer
 if ($LASTEXITCODE -ne 0) { throw 'Offline index generation failed; source copies retained.' }
 [IO.File]::WriteAllBytes((Join-Path $dest 'index.html'),[Convert]::FromBase64String(($encoded -join '').Trim()))
 # The root CSV and HTML are conveniences; per-record manifests cover all
 # content and attachments. CSV is also available from the offline HTML.
 foreach ($row in $rows) { foreach ($property in $row.PSObject.Properties) { if ($property.Value -is [string] -and $property.Value.TrimStart() -match '^[=+@-]') { $property.Value="'"+$property.Value } } }
 $rows|Select-Object kind,number,subject,owner,status,created,completed,description,scope,approval_records,attachments,attachment_paths,path|Export-Csv -LiteralPath (Join-Path $dest 'archive.csv') -NoTypeInformation -Encoding UTF8
 & (Join-Path $PSScriptRoot 'Test-Archive.ps1') -ArchivePath $dest
 $finalize="import app.main; from app.archive import finish_export,root; import json; print(finish_export(app.main.engine,json.loads((root()[0]/'$receiptName').read_text())))"
 & docker @compose exec -T web python -c $finalize
 if ($LASTEXITCODE -ne 0) { throw 'Finalization incomplete. Keep both copies and retry; inspect Portal logs.' }
 Write-Output "Offline transfer complete: $dest. You may safely eject the external drive."
} finally {
 $OutputEncoding=$previousEncoding
 Pop-Location
 Remove-Item -LiteralPath $receipt -ErrorAction SilentlyContinue
}
