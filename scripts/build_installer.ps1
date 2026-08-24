# Builds the net67 installer from artifact\ using Inno Setup 6.
#
# ASCII only on purpose, same reason as build_local.ps1: Windows
# PowerShell 5.1 reads .ps1 as ANSI without a BOM and mangles Cyrillic.
#
# Usage (from the project root, elevated not required):
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
#
# Run scripts\build_local.ps1 first - this script only packs what is
# already in artifact\, it does not build the application.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Artifact  = Join-Path $Root "artifact"
$Installer = Join-Path $Root "installer"
$Script    = Join-Path $Installer "net67.iss"
$OutputDir = Join-Path $Installer "output"

Write-Host "[1/4] Checking the artifact" -ForegroundColor Cyan

if (-not (Test-Path $Artifact)) {
    throw "artifact\ is missing. Run scripts\build_local.ps1 first."
}

# The same engine files build_local.ps1 guards. An installer without them
# produces an application whose "Enable" button silently does nothing -
# and that is discovered by twenty managers, not by the developer.
$required = @(
    "_internal\net67.exe",
    "exe\winws.exe",
    "exe\winws2.exe",
    "exe\WinDivert.dll",
    "lua\zapret-lib.lua",
    "lists\base\discord.txt",
    "bin\tls_clienthello_www_google_com.bin",
    "ico\net67.ico"
)
$missing = @()
foreach ($item in $required) {
    if (-not (Test-Path (Join-Path $Artifact $item))) { $missing += $item }
}
if ($missing.Count -gt 0) {
    throw ("The artifact is incomplete: " + ($missing -join ", ") + ". Rebuild with scripts\build_local.ps1.")
}

# The installer copies the artifact wholesale but excludes user-data
# folders, so nothing here can reach the manager's machine. Files still
# show up because the application is launched from artifact\_internal and
# writes its settings next to itself - worth saying out loud, not worth
# stopping the build for.
$userDataDirs = @(
    "presets\winws1",
    "presets\winws2",
    "lists\user",
    "settings"
)
$dirty = @()
foreach ($dir in $userDataDirs) {
    $path = Join-Path $Artifact $dir
    if (-not (Test-Path $path)) { continue }
    $files = @(Get-ChildItem -Path $path -Recurse -File -Force -ErrorAction SilentlyContinue)
    if ($files.Count -gt 0) { $dirty += ($dir + " (" + $files.Count + ")") }
}
if ($dirty.Count -gt 0) {
    Write-Host "      user data in the artifact (excluded from the installer):" -ForegroundColor Yellow
    foreach ($item in $dirty) { Write-Host ("        " + $item) }
}

$builtin1 = @(Get-ChildItem -Path (Join-Path $Artifact "presets\winws1_builtin") -Filter *.txt -ErrorAction SilentlyContinue)
$builtin2 = @(Get-ChildItem -Path (Join-Path $Artifact "presets\winws2_builtin") -Filter *.txt -ErrorAction SilentlyContinue)
if ($builtin1.Count -eq 0 -or $builtin2.Count -eq 0) {
    throw "No builtin presets in the artifact - rebuild with scripts\build_local.ps1."
}
Write-Host ("      engine ok, builtin presets: winws1=" + $builtin1.Count + " winws2=" + $builtin2.Count)

Write-Host "[2/4] Reading the version" -ForegroundColor Cyan

$Version = "1.0.0.0"
$buildInfo = Join-Path $Root "src\config\build_info.py"
if (Test-Path $buildInfo) {
    $match = Select-String -Path $buildInfo -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
    if ($match) { $Version = $match.Matches[0].Groups[1].Value }
}
# Inno Setup requires up to four numeric parts in VersionInfoVersion.
if ($Version -notmatch '^\d+(\.\d+){0,3}$') {
    Write-Host ("      version '" + $Version + "' is not numeric, using 1.0.0.0 for VersionInfo") -ForegroundColor Yellow
    $Version = "1.0.0.0"
}
Write-Host ("      version: " + $Version)

Write-Host "[3/4] Locating Inno Setup" -ForegroundColor Cyan

$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$Iscc = $null
foreach ($path in $candidates) {
    if ($path -and (Test-Path $path)) { $Iscc = $path; break }
}
if (-not $Iscc) {
    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) { $Iscc = $command.Source }
}
if (-not $Iscc) {
    Write-Host ""
    Write-Host "Inno Setup 6 was not found." -ForegroundColor Yellow
    Write-Host "Install it from https://jrsoftware.org/isdl.php (or: winget install JRSoftware.InnoSetup)"
    throw "ISCC.exe is missing"
}
Write-Host ("      " + $Iscc)

# Version is printed for the log only, never used to block the build.
#
# ISCC.exe carries no version resource: Get-Item.VersionInfo returns
# 0.0.0.0 even on a fresh 6.7.3. A guard built on that number refused to
# compile with a perfectly good compiler and told the user to upgrade
# something already up to date. The real version lives in the banner the
# compiler prints when started without arguments.
$isccVersion = "unknown"
try {
    $banner = & $Iscc 2>&1 | Select-Object -First 3
    $match = [regex]::Match(($banner -join " "), '\d+\.\d+(\.\d+)*')
    if ($match.Success) { $isccVersion = $match.Value }
} catch {
    $isccVersion = "unknown"
}
Write-Host ("      version " + $isccVersion)

Write-Host "[4/4] Compiling the installer" -ForegroundColor Cyan

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

& $Iscc `
    ("/DAppVersion=" + $Version) `
    ("/DSourceDir=" + $Artifact) `
    ("/O" + $OutputDir) `
    $Script

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "If the error mentions an invalid [Setup] directive, the compiler is" -ForegroundColor Yellow
    Write-Host "older than 6.3: net67.iss uses ArchitecturesAllowed=x64compatible."
    Write-Host "Update with: winget upgrade JRSoftware.InnoSetup"
    throw "ISCC failed with code $LASTEXITCODE"
}

$setup = Join-Path $OutputDir ("net67-setup-" + $Version + ".exe")
Write-Host ""
if (Test-Path $setup) {
    $sizeMb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
    Write-Host ("Built: " + $setup + "  (" + $sizeMb + " MB)") -ForegroundColor Green
} else {
    Write-Host ("Built, see " + $OutputDir) -ForegroundColor Green
}

Write-Host ""
Write-Host "The installer is NOT signed." -ForegroundColor Yellow
Write-Host "SmartScreen will warn on first run: More info -> Run anyway."
Write-Host "Ask IT to whitelist exe\winws.exe, exe\winws2.exe and the WinDivert driver,"
Write-Host "otherwise antivirus quarantines them and Enable does nothing."
