# Removes the net67 encrypted DNS service (dnscrypt-proxy) on uninstall.
#
# ASCII only: Windows PowerShell 5.1 reads .ps1 as ANSI without a BOM.
#
# Order matters. Adapters that point at the local engine (127.0.0.1, ::1)
# are switched back to automatic DNS first, and only then the service is
# removed. The other way round leaves those adapters with a DNS address
# nobody answers on: the computer loses the internet right after the
# uninstall, with nothing left on disk to fix it.
#
# Adapters are touched only while the service exists: 127.0.0.1 may belong
# to another local DNS program the user runs on purpose.
#
# The service name must match SERVICE_NAME in src\dns\local_proxy.py.

param([string]$ServiceName = "net67DnsCrypt")

$ErrorActionPreference = "Continue"

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($null -eq $service) {
    Write-Host "encrypted DNS service not found, nothing to remove"
    exit 0
}

$local = @("127.0.0.1", "::1")
$indexes = @(
    Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
        Where-Object { @($_.ServerAddresses | Where-Object { $local -contains $_ }).Count -gt 0 } |
        Select-Object -ExpandProperty InterfaceIndex -Unique
)
foreach ($index in $indexes) {
    Set-DnsClientServerAddress -InterfaceIndex $index -ResetServerAddresses -ErrorAction SilentlyContinue
    Write-Host "adapter $index switched back to automatic DNS"
}
Clear-DnsClientCache -ErrorAction SilentlyContinue

& "$env:SystemRoot\System32\sc.exe" stop $ServiceName | Out-Null
Start-Sleep -Seconds 2
& "$env:SystemRoot\System32\sc.exe" delete $ServiceName | Out-Null
Write-Host "encrypted DNS service removed"
exit 0
