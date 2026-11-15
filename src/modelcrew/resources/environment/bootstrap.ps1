param(
    [string]$Workspace = (Join-Path $env:LOCALAPPDATA 'NexusMORE\workspace'),
    [string]$DistributionDirectory = $PSScriptRoot,
    [string]$ArchiveDirectory = '',
    [string]$Wheelhouse = '',
    [switch]$Offline,
    [switch]$SkipServices
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'This release requires Windows x86_64.'
}
$Workspace = [IO.Path]::GetFullPath($Workspace)
$DistributionDirectory = [IO.Path]::GetFullPath($DistributionDirectory)
if ($Workspace -eq [IO.Path]::GetPathRoot($Workspace)) { throw 'Choose a dedicated workspace, not a drive root.' }
$walk = $Workspace
while ($walk) {
    if (Test-Path -LiteralPath $walk) {
        $item = Get-Item -LiteralPath $walk -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Workspace may not traverse a junction or symbolic link.' }
    }
    $parent = [IO.Directory]::GetParent($walk)
    $walk = if ($null -eq $parent) { $null } else { $parent.FullName }
}
function Get-LockedHash([string]$FilePath) {
    $stream = [IO.File]::OpenRead($FilePath)
    $digest = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($digest.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $digest.Dispose() }
}
$lockPath = Join-Path $DistributionDirectory 'distribution-lock.json'
$catalogPath = Join-Path $DistributionDirectory 'native-tools.json'
$releaseLock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ((Get-LockedHash $catalogPath) -ne $releaseLock.native_catalog_sha256) { throw 'Native catalog identity changed.' }
$catalog = Get-Content -LiteralPath $catalogPath -Raw -Encoding UTF8 | ConvertFrom-Json
$wheelPath = Join-Path $DistributionDirectory $releaseLock.wheel.filename
if ([IO.Path]::GetFileName($releaseLock.wheel.filename) -ne $releaseLock.wheel.filename) { throw 'Invalid wheel file name.' }
if ((Get-LockedHash $wheelPath) -ne $releaseLock.wheel.sha256) { throw 'Wheel identity changed.' }
$localRoot = Join-Path $Workspace 'configs\local'
$downloads = Join-Path $localRoot 'downloads'
foreach ($candidate in @($localRoot,$downloads,(Join-Path $localRoot 'runtime\python313'))) {
    $part = $candidate
    while ($part -and $part -ne $Workspace) {
        if (Test-Path -LiteralPath $part) {
            if ((Get-Item -LiteralPath $part -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Local setup paths may not traverse links.' }
        }
        $part = [IO.Path]::GetDirectoryName($part)
    }
}
[IO.Directory]::CreateDirectory($downloads) | Out-Null
function Get-LockedDownload($Entry) {
    $target = Join-Path $downloads $Entry.filename
    if (-not (Test-Path -LiteralPath $target)) {
        if ($ArchiveDirectory) {
            Copy-Item -LiteralPath (Join-Path $ArchiveDirectory $Entry.filename) -Destination $target
        } elseif ($Offline) {
            throw ('Required archive unavailable offline: ' + $Entry.filename)
        } else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $Entry.url -OutFile $target -UseBasicParsing
        }
    }
    if ((Get-Item -LiteralPath $target).Length -ne $Entry.bytes -or (Get-LockedHash $target) -ne $Entry.sha256) {
        throw ('Download size/SHA256 mismatch: ' + $Entry.filename)
    }
    return $target
}
function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Preparation command failed, exit ' + $LASTEXITCODE + '. Keep the workspace and inspect logs before retrying.') }
}
$pythonArchive = Get-LockedDownload $catalog.downloads.'python-embedded'
$pipArchive = Get-LockedDownload $catalog.downloads.pip
$pythonRoot = Join-Path $localRoot 'runtime\python313'
$pythonExe = Join-Path $pythonRoot 'python.exe'
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (Test-Path -LiteralPath $pythonRoot) { throw 'Partial Python runtime exists; recover the original archive before proceeding.' }
    [IO.Compression.ZipFile]::ExtractToDirectory($pythonArchive,$pythonRoot)
    $site = Join-Path $pythonRoot 'Lib\site-packages'
    New-Item -ItemType Directory -Path $site -Force | Out-Null
    [IO.Compression.ZipFile]::ExtractToDirectory($pipArchive,$site)
    $pth = Join-Path $pythonRoot 'python313._pth'
    [IO.File]::WriteAllText($pth,"python313.zip`n.`nLib/site-packages`nimport site`n",[Text.UTF8Encoding]::new($false))
}
# Verify core runtime bytes before executing an existing private Python as well.
$runtimeZip = [IO.Compression.ZipFile]::OpenRead($pythonArchive)
try {
    foreach ($entry in $runtimeZip.Entries) {
        if (-not $entry.Name -or $entry.FullName -eq 'python313._pth') { continue }
        $installed = Join-Path $pythonRoot $entry.FullName
        $digest = [Security.Cryptography.SHA256]::Create()
        $stream = $entry.Open()
        try { $expected = [BitConverter]::ToString($digest.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $stream.Dispose(); $digest.Dispose() }
        if (-not (Test-Path -LiteralPath $installed) -or (Get-LockedHash $installed) -ne $expected) { throw 'Private Python runtime changed; refusing execution.' }
    }
} finally { $runtimeZip.Dispose() }
$env:PIP_CACHE_DIR = Join-Path $localRoot 'pip-cache'
Invoke-Checked $pythonExe @('-I','-c','import sys,struct; assert sys.version_info[:3]==(3,13,5) and struct.calcsize(chr(80))==8; assert sys.flags.isolated==1')
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:MODELCREW_WORKSPACE = $Workspace
# Replace only the application wheel, even for repeated private dev-version builds.
Invoke-Checked $pythonExe @('-I','-m','pip','install','--no-deps','--force-reinstall','--no-compile','--no-warn-script-location',$wheelPath)
$package = $wheelPath + '[workflow,documents,figures,evidence,retrieval,paper]'
if ($Offline) {
    if (-not $Wheelhouse) { throw 'Offline preparation needs an explicit wheelhouse.' }
    Invoke-Checked $pythonExe @('-I','-m','pip','install','--no-index','--find-links',$Wheelhouse,'--no-compile','--no-warn-script-location',$package)
} else {
    Invoke-Checked $pythonExe @('-I','-m','pip','install','torch==2.6.0+cpu','--index-url','https://download.pytorch.org/whl/cpu','--no-compile','--no-warn-script-location')
    Invoke-Checked $pythonExe @('-I','-m','pip','install','--no-compile','--no-warn-script-location',$package)
}
Invoke-Checked $pythonExe @('-I','-m','pip','check')
Invoke-Checked $pythonExe @('-I','-m','modelcrew','init')
if (-not $SkipServices) {
    $setupArguments = @('-I','-m','modelcrew','environment','setup')
    if ($Offline) { $setupArguments += '--offline' }
    if ($ArchiveDirectory) { $setupArguments += @('--archives',$ArchiveDirectory) }
    Invoke-Checked $pythonExe $setupArguments
}
# A local launcher preserves the selected workspace across new shells.
$launcherPath = Join-Path $Workspace 'modelcrew.ps1'
$launcher = @'
$ErrorActionPreference = 'Stop'
$env:MODELCREW_WORKSPACE = $PSScriptRoot
& (Join-Path $PSScriptRoot 'configs\local\runtime\python313\python.exe') -I -m modelcrew @args
exit $LASTEXITCODE
'@
if (-not (Test-Path -LiteralPath $launcherPath)) { [IO.File]::WriteAllText($launcherPath,$launcher,[Text.UTF8Encoding]::new($false)) }
Write-Output ('Prepared private Python/runtime at: ' + $pythonRoot)
Write-Output ('Workspace launcher: ' + $launcherPath)
Write-Output 'No system Python, registry, PATH, model key or Harness installation was changed.'
Write-Output 'Docker Desktop/WSL2 remain host prerequisites. Real Word rendering needs a licensed local Microsoft Word installation.'
