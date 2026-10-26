# Removes the net67 encrypted DNS service (dnscrypt-proxy) on uninstall
# and before a local build wipes the artifact folder.
#
# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI without a BOM.
#
# Order matters. Adapters that point at the local engine (127.0.0.1, ::1)
# get their DNS back first, and only then the service is removed. The
# other way round leaves those adapters with a DNS address nobody answers
# on: the computer loses the internet right after the uninstall, with
# nothing left on disk to fix it.
#
# "Back" means the DNS the adapter had before net67 set 127.0.0.1 - the
# app writes it to previous_dns.json next to the engine. Resetting to
# automatic DNS is not enough: an adapter with a static address has no
# automatic DNS at all (the owner pointed it out, 26 October 2026).
# Without a record: automatic DNS where DHCP gives it, otherwise the
# default gateway if it really answers DNS queries, otherwise a warning.
#
# Adapters are touched only while the service exists: 127.0.0.1 may belong
# to another local DNS program the user runs on purpose.
#
# The service name must match SERVICE_NAME, the record name PREVIOUS_DNS_NAME
# in src\dns\local_proxy.py.

param([string]$ServiceName = "net67DnsCrypt")

$ErrorActionPreference = "Continue"

$service = Get-CimInstance -ClassName Win32_Service -Filter ("Name='" + $ServiceName + "'") -ErrorAction SilentlyContinue
if ($null -eq $service) {
    Write-Host "encrypted DNS service not found, nothing to remove"
    exit 0
}

# The engine runs from its own folder; the record lies next to it.
$records = @{}
$image = [string]$service.PathName
if ($image -match '^\s*"([^"]+)"') { $exe = $Matches[1] } else { $exe = ($image -split '\s+')[0] }
if ($exe) {
    $recordPath = Join-Path (Split-Path -Parent $exe) "previous_dns.json"
    if (Test-Path -LiteralPath $recordPath) {
        try {
            $saved = Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($item in @($saved.adapters)) {
                if ($item.guid) { $records[([string]$item.guid).ToLowerInvariant()] = $item }
            }
        } catch {
            Write-Host "previous DNS record unreadable: $($_.Exception.Message)"
        }
    }
}

function Test-AnswersDns([string]$server) {
    try {
        $answer = Resolve-DnsName -Name "example.com" -Type A -Server $server -DnsOnly -QuickTimeout -ErrorAction Stop
        return @($answer | Where-Object { $_.IPAddress }).Count -gt 0
    } catch {
        return $false
    }
}

$local = @("127.0.0.1", "::1")
$indexes = @(
    Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
        Where-Object { @($_.ServerAddresses | Where-Object { $local -contains $_ }).Count -gt 0 } |
        Select-Object -ExpandProperty InterfaceIndex -Unique
)
foreach ($index in $indexes) {
    $adapter = Get-NetAdapter -InterfaceIndex $index -ErrorAction SilentlyContinue
    $name = if ($adapter) { $adapter.Name } else { "interface $index" }
    $guid = if ($adapter) { ([string]$adapter.InterfaceGuid).ToLowerInvariant() } else { "" }
    $record = if ($guid -and $records.ContainsKey($guid)) { $records[$guid] } else { $null }

    if ($record) {
        $servers = @(@($record.ipv4) + @($record.ipv6) | Where-Object { $_ })
        if ($servers.Count -gt 0) {
            Set-DnsClientServerAddress -InterfaceIndex $index -ServerAddresses $servers -ErrorAction SilentlyContinue
            Write-Host "adapter $name gets its DNS back: $($servers -join ', ')"
        } else {
            Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -ErrorAction SilentlyContinue
            Write-Host "adapter $name gets its automatic DNS back"
        }
        continue
    }

    $dhcp = Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4 -ErrorAction SilentlyContinue
    if ($dhcp -and $dhcp.Dhcp -eq "Enabled") {
        Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -ErrorAction SilentlyContinue
        Write-Host "adapter $name switched back to automatic DNS"
        continue
    }

    # Static address and no record of the old DNS: try the router.
    $gateway = (Get-NetIPConfiguration -InterfaceIndex $index -ErrorAction SilentlyContinue).IPv4DefaultGateway |
        Select-Object -First 1 -ExpandProperty NextHop
    if ($gateway -and (Test-AnswersDns $gateway)) {
        Set-DnsClientServerAddress -InterfaceIndex $index -ServerAddresses @($gateway) -ErrorAction SilentlyContinue
        Write-Host "adapter $name has a static address, DNS set to its gateway $gateway (it answers DNS)"
        continue
    }
    Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -ErrorAction SilentlyContinue
    Write-Host "adapter $name has a static address and its old DNS is unknown - set its DNS by hand" -ForegroundColor Yellow
}
Clear-DnsClientCache -ErrorAction SilentlyContinue

& "$env:SystemRoot\System32\sc.exe" stop $ServiceName | Out-Null
Start-Sleep -Seconds 2
& "$env:SystemRoot\System32\sc.exe" delete $ServiceName | Out-Null
Write-Host "encrypted DNS service removed"
exit 0
