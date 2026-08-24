# Removes the net67 block from the system hosts file.
#
# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI without a BOM.
#
# The uninstaller calls this while the application files are still on
# disk. Everything outside the managed markers is left untouched - users
# keep their own hosts entries.
#
# Markers must match _MANAGED_HOSTS_BEGIN / _MANAGED_HOSTS_END in
# src\hosts\hosts.py. Legacy markers are recognised too: a block written
# before the rename would otherwise stay in hosts forever with nothing
# left on disk able to find it.

$ErrorActionPreference = "Stop"

$Markers = @{
    Begin = @(
        "# >>> net67:hosts managed begin >>>",
        "# >>> zapretgui:hosts managed begin >>>"
    )
    End = @(
        "# <<< net67:hosts managed end <<<",
        "# <<< zapretgui:hosts managed end <<<"
    )
}

$HostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"

if (-not (Test-Path -LiteralPath $HostsPath)) {
    Write-Host "hosts file not found, nothing to clean"
    exit 0
}

try {
    $lines = @(Get-Content -LiteralPath $HostsPath -ErrorAction Stop)
} catch {
    Write-Host ("Could not read hosts: " + $_.Exception.Message)
    exit 1
}

$kept = New-Object System.Collections.Generic.List[string]
$inside = $false
$removed = 0

foreach ($line in $lines) {
    $trimmed = $line.Trim()

    if (-not $inside -and $Markers.Begin -contains $trimmed) {
        $inside = $true
        $removed++
        continue
    }

    if ($inside) {
        $removed++
        if ($Markers.End -contains $trimmed) { $inside = $false }
        continue
    }

    $kept.Add($line)
}

if ($removed -eq 0) {
    Write-Host "No net67 block in hosts, nothing to clean"
    exit 0
}

# An unterminated block means the file was edited by hand mid-block. Do
# not guess where it ended - a truncated hosts file is worse than a
# leftover comment.
if ($inside) {
    Write-Host "The net67 block has no end marker - hosts left untouched"
    exit 1
}

while ($kept.Count -gt 0 -and [string]::IsNullOrWhiteSpace($kept[$kept.Count - 1])) {
    $kept.RemoveAt($kept.Count - 1)
}

try {
    Set-Content -LiteralPath $HostsPath -Value $kept -Encoding ASCII -ErrorAction Stop
    Write-Host ("Removed " + $removed + " lines from hosts")
} catch {
    Write-Host ("Could not write hosts: " + $_.Exception.Message)
    exit 1
}

exit 0
