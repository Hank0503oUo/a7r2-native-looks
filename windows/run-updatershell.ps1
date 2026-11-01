# Run a Sony-PMCA-RE updater-shell script against the camera and keep the full log.
# The camera must be in MTP USB mode with a charged battery; updater mode refuses to start on low battery.
# Windows needs administrator rights for the updater-mode USB device, so this re-launches itself elevated.
#
#   powershell -ExecutionPolicy Bypass -File run-updatershell.ps1 -Commands cmds_write.txt -Log pmca_write.log
#
# Relative paths are resolved against -Dir (default: the current folder).
param(
    [Parameter(Mandatory = $true)][string]$Commands,
    [Parameter(Mandatory = $true)][string]$Log,
    [string]$Pmca = 'pmca-console.exe',   # Sony-PMCA-RE v0.18 Windows build
    [string]$Dir = (Get-Location).Path
)
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    # an elevated process starts in System32, so hand it the folder explicitly
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
                 '-Commands', "`"$Commands`"", '-Log', "`"$Log`"", '-Pmca', "`"$Pmca`"", '-Dir', "`"$Dir`"")
    Start-Process powershell -Verb RunAs -Wait -ArgumentList $argList
    Get-Content (Join-Path $Dir "$Log.status")
    exit
}
Set-Location $Dir
"start $(Get-Date -Format s)" | Out-File -Encoding utf8 "$Log.status"
cmd /c "`"$Pmca`" updatershell < `"$Commands`" > `"$Log`" 2>&1"
"exit=$LASTEXITCODE end $(Get-Date -Format s)" | Out-File -Append -Encoding utf8 "$Log.status"
