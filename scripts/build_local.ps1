# Local build of net67 via PyInstaller.
#
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 files as ANSI
# unless they carry a UTF-8 BOM, which mangles Cyrillic text and breaks
# parsing. Python helper lives in a separate file for the same reason.
#
# The app only starts from <root>\_internal\net67.exe - this is enforced
# by resolve_application_root() in config/runtime_layout.py. Running the
# folder produced by PyInstaller directly will not work.
#
# Usage (from the project root):
#   py -3.14 -m pip install -r requirements-build.txt
#   powershell -ExecutionPolicy Bypass -File scripts\build_local.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = "py"
$PyVer = "-3.14"

Write-Host "[1/6] Checking generated files" -ForegroundColor Cyan

$buildInfo = Join-Path $Root "src\config\build_info.py"
if (-not (Test-Path $buildInfo)) {
    $lines = @('APP_VERSION = "0.2.67"', 'CHANNEL = "stable"')
    Set-Content -Path $buildInfo -Value $lines -Encoding UTF8
    Write-Host "      created build_info.py" -ForegroundColor Yellow
}

$secrets = Join-Path $Root "src\config\_build_secrets.py"
if (-not (Test-Path $secrets)) {
    $lines = @(
        'UPDATE_SERVERS = []',
        'GITHUB_UPDATE_TOKEN = ""',
        'TG_UPDATE_BOT_TOKEN = ""',
        'PREMIUM_API_BASE_URL = ""',
        'PROXY_PRESETS = []',
        'MTPROXY_LINK = ""'
    )
    Set-Content -Path $secrets -Value $lines -Encoding UTF8
    Write-Host "      created _build_secrets.py" -ForegroundColor Yellow
}

Write-Host "[2/6] Collecting dynamically loaded modules" -ForegroundColor Cyan

$env:PYTHONPATH = (Join-Path $Root "src")
$modules = & $Py $PyVer (Join-Path $Root "scripts\collect_lazy_modules.py")
if ($LASTEXITCODE -ne 0) { throw "Failed to collect module list" }
Write-Host "      modules: $($modules.Count)"

Write-Host "[3/6] Running PyInstaller" -ForegroundColor Cyan

$BuildRoot = Join-Path $Root "build-local"
$DistRoot = Join-Path $BuildRoot "dist"
$Artifact = Join-Path $Root "artifact"

# Release the DPI engine before touching the artifact.
#
# WinDivert is a kernel driver. Once loaded, Windows holds an open handle
# on the .sys file, so Remove-Item skips it and the next Copy-Item dies
# with "the file is used by another process" on exe\Monkey64.sys. The
# driver survives closing the GUI - it has to be stopped explicitly.
# Same sequence as exe\stop.bat from the engine bundle.
function Stop-Net67Engine {
    # A VPN tunnel service keeps exe\amneziawg.exe and exe\wintun.dll
    # open, so it has to go before the WinDivert driver. Prefixes match
    # SERVICE_NAME_PREFIXES in src\vpn\tunnel.py.
    $tunnelPrefixes = @("AmneziaWGTunnel$", "AmneziaWG$", "WireGuardTunnel$")
    Get-Service -ErrorAction SilentlyContinue | ForEach-Object {
        $serviceName = $_.Name
        foreach ($prefix in $tunnelPrefixes) {
            if ($serviceName.StartsWith($prefix)) {
                Write-Host ("      stopping tunnel service " + $serviceName)
                & sc.exe stop $serviceName   | Out-Null
                & sc.exe delete $serviceName | Out-Null
                break
            }
        }
    }

    foreach ($name in @("net67", "winws", "winws2", "amneziawg", "awg")) {
        Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host ("      stopping process " + $_.ProcessName)
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
    }

    # Names the app itself looks for, see _WINDIVERT_DRIVER_SERVICE_NAMES.
    foreach ($service in @("Monkey", "Monkey64", "WinDivert", "WinDivert14", "WinDivert64")) {
        $query = & sc.exe query $service 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host ("      stopping driver service " + $service)
            & sc.exe stop $service   | Out-Null
            & sc.exe delete $service | Out-Null
        }
    }

    # Service deletion is asynchronous: the SCM keeps the handle until the
    # last reference goes away, and only then does the file unlock.
    Start-Sleep -Seconds 2
}

Write-Host "      releasing DPI engine (driver keeps .sys files locked)"
Stop-Net67Engine

# Windows unlocks files lazily after a service is deleted, so a single
# attempt is not enough - retry for a few seconds before giving up.
for ($attempt = 1; $attempt -le 5; $attempt++) {
    Remove-Item -Recurse -Force $Artifact -ErrorAction SilentlyContinue
    if (-not (Test-Path $Artifact)) { break }
    Start-Sleep -Seconds 1
}

if (Test-Path $Artifact) {
    $locked = @(Get-ChildItem -Path $Artifact -Recurse -File -ErrorAction SilentlyContinue)
    if ($locked.Count -gt 0) {
        Write-Host ""
        Write-Host "Could not clear the artifact folder. Files still in use:" -ForegroundColor Yellow
        $locked | Select-Object -First 5 | ForEach-Object { Write-Host ("  " + $_.FullName) }
        Write-Host ""
        Write-Host "Something still holds them. From an elevated prompt:" -ForegroundColor Yellow
        Write-Host "  taskkill /F /IM net67.exe /IM winws.exe /IM winws2.exe /IM amneziawg.exe"
        Write-Host "  sc stop Monkey"
        Write-Host "  sc delete Monkey"
        Write-Host "  Get-Service AmneziaWG* | ForEach-Object { sc.exe delete `$_.Name }"
        Write-Host ""
        Write-Host "Are you running this as Administrator? Deleting a service needs it." -ForegroundColor Yellow
        throw "Artifact folder is locked"
    }
}

$piArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name", "net67",
    "--windowed",
    "--uac-admin",
    "--onedir",
    "--contents-directory", ".",
    "--paths", "src",
    "--workpath", (Join-Path $BuildRoot "work"),
    "--distpath", $DistRoot
)

$icon = Join-Path $Root "ico\net67.ico"
if (-not (Test-Path $icon)) { $icon = Join-Path $Root "src\ico\net67.ico" }
if (Test-Path $icon) { $piArgs += @("--icon", $icon) }

# Data that lives INSIDE a package and is read relative to __file__ must be
# bundled by PyInstaller, not copied to the install root. blockcheck reads
# Path(__file__).parent / "data", so a root-level copy would never be found.
$packageData = @(
    @("src\blockcheck\data", "blockcheck\data"),
    @("src\config\config.json", "config")
)
foreach ($item in $packageData) {
    $source = Join-Path $Root $item[0]
    if (Test-Path $source) { $piArgs += ("--add-data=" + $source + ";" + $item[1]) }
}

foreach ($m in $modules) {
    $name = "$m".Trim()
    if ($name) { $piArgs += "--hidden-import=$name" }
}

$piArgs += "src\main.py"

& $Py $PyVer @piArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with code $LASTEXITCODE" }

Write-Host "[4/6] Building _internal layout" -ForegroundColor Cyan

$Runtime = Join-Path $Artifact "_internal"
New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
Copy-Item -Path (Join-Path $DistRoot "net67\*") -Destination $Runtime -Recurse -Force

$builtExe = Join-Path $Runtime "net67.exe"
if (-not (Test-Path $builtExe)) { throw "Missing $builtExe" }

Write-Host "[5/6] Copying resources next to _internal" -ForegroundColor Cyan

# ApplicationPaths looks for resources in the install root, so they go
# beside _internal, not inside it.
#
# Careful: src\presets, src\profile and src\lists are Python PACKAGES, not
# resource folders. Copying them wholesale is what produced an artifact
# with presets\commands.py in it and no strategies at all - the app then
# reported "presets not found" for artifact\presets\winws2_builtin.
#
# The real resource layout comes from core\paths.py (EnginePaths) and
# profile\strategy_catalog.py:
#   presets\winws1          user presets, engine winws1  (starts empty)
#   presets\winws1_builtin  shipped presets, engine winws1
#   presets\winws2          user presets, engine winws2  (starts empty)
#   presets\winws2_builtin  shipped presets, engine winws2
#   profile\strategy_catalogs\winws1|winws2
#
# exe, bin, lua, json, lists and windivert.filter hold the DPI engine
# itself (winws.exe, winws2.exe, WinDivert) plus the hostlists, fake
# payloads and lua scripts every preset references, e.g.
#   --lua-init=@lua/zapret-lib.lua
#   --hostlist=lists/discord.txt
#   --dpi-desync-fake-tls=bin/tls_clienthello_www_google_com.bin
# Without them the UI starts but "Enable" has nothing to launch.
$pairs = @(
    @("exe",                            "exe"),
    @("ico",                            "ico"),
    @("src\exe",                        "exe"),
    @("src\ico",                        "ico"),
    @("src\presets\builtin\winws1",     "presets\winws1_builtin"),
    @("src\presets\builtin\winws2",     "presets\winws2_builtin"),
    @("src\profile\strategy_catalogs",  "profile\strategy_catalogs"),
    @("src\profile\templates",          "profile\templates"),
    @("lists",                          "lists"),
    @("lua",                            "lua"),
    @("json",                           "json"),
    @("themes",                         "themes"),
    @("windivert.filter",               "windivert.filter"),
    @("bin",                            "bin")
)

foreach ($pair in $pairs) {
    $source = Join-Path $Root $pair[0]
    if (-not (Test-Path $source)) { continue }
    $target = Join-Path $Artifact $pair[1]
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $entries = @(Get-ChildItem -Path $source -Force)
    if ($entries.Count -gt 0) {
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    }
    Write-Host ("      " + $pair[0] + " -> " + $pair[1])
}

# Directories the app writes into. It creates them itself on first run,
# but an empty tree makes the artifact self-describing.
$emptyDirs = @(
    "presets\winws1",
    "presets\winws2",
    "lists\base",
    "lists\user",
    "logs",
    "settings",
    "themes",
    "tmp"
)
foreach ($dir in $emptyDirs) {
    New-Item -ItemType Directory -Path (Join-Path $Artifact $dir) -Force | Out-Null
}

$w1 = @(Get-ChildItem -Path (Join-Path $Artifact "presets\winws1_builtin") -Filter *.txt -ErrorAction SilentlyContinue)
$w2 = @(Get-ChildItem -Path (Join-Path $Artifact "presets\winws2_builtin") -Filter *.txt -ErrorAction SilentlyContinue)
Write-Host ("      builtin presets: winws1=" + $w1.Count + " winws2=" + $w2.Count)
if ($w1.Count -eq 0 -or $w2.Count -eq 0) {
    throw "No builtin presets were copied - check src\presets\builtin"
}

# Fail here rather than let the user find out from a red banner that
# "Enable" does nothing. These files are the engine, not decoration.
$required = @(
    "exe\winws.exe",
    "exe\winws2.exe",
    "exe\WinDivert.dll",
    "lua\zapret-lib.lua",
    "lists\base\discord.txt",
    "bin\tls_clienthello_www_google_com.bin"
)
$missing = @()
foreach ($item in $required) {
    if (-not (Test-Path (Join-Path $Artifact $item))) { $missing += $item }
}
if ($missing.Count -gt 0) {
    throw ("DPI engine files are missing from the artifact: " + ($missing -join ", "))
}
Write-Host "      engine: winws.exe, winws2.exe, WinDivert, lua, lists, bin - ok"

Write-Host "[6/6] Done" -ForegroundColor Green
Write-Host ""
Write-Host "Built: $Runtime\net67.exe"
Write-Host "Run that exact file - it must stay inside _internal." -ForegroundColor Yellow
Write-Host "Administrator rights are required (WinDivert is a driver)." -ForegroundColor Yellow

if (-not (Test-Path (Join-Path $Artifact "exe\amneziawg.exe"))) {
    Write-Host ""
    Write-Host "Warning: exe\amneziawg.exe is missing - VPN tunnel will not start." -ForegroundColor Yellow
}
