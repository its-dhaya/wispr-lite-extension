<#
.SYNOPSIS
    Registers the Wispr Lite native messaging host with Chrome.

.DESCRIPTION
    Run this once after you load the unpacked extension in Chrome
    (chrome://extensions -> Developer mode -> Load unpacked).
    Copy the Extension ID shown there and pass it in below.

.EXAMPLE
    .\install.ps1 -ExtensionId "abcdefghijklmnopabcdefghijklmnop"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$ExtensionId
)

$ErrorActionPreference = "Stop"

$nativeHostDir = $PSScriptRoot
$pythonAppDir  = Join-Path (Split-Path $nativeHostDir -Parent) "python-app"
$hostScript    = Join-Path $pythonAppDir "wispr_lite_host.py"

if (-not (Test-Path $hostScript)) {
    throw "Could not find wispr_lite_host.py at $hostScript"
}

# Find pythonw.exe (no console window) so no black terminal flashes up
$pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonw) {
    Write-Warning "pythonw.exe not found on PATH, falling back to python.exe (a console window may appear)."
    $pythonw = (Get-Command python.exe).Source
}

# Wrapper .bat, since Chrome's native messaging "path" must point at an executable
$batPath = Join-Path $nativeHostDir "run_host.bat"
@"
@echo off
"$pythonw" "$hostScript"
"@ | Set-Content -Path $batPath -Encoding ASCII

# Write the manifest with real paths filled in
$manifestPath = Join-Path $nativeHostDir "com.wispr_lite.host.json"
$manifest = @{
    name             = "com.wispr_lite.host"
    description      = "Wispr Lite native messaging host"
    path             = $batPath
    type             = "stdio"
    allowed_origins  = @("chrome-extension://$ExtensionId/")
}
$manifest | ConvertTo-Json | Set-Content -Path $manifestPath -Encoding UTF8

# Register with Chrome (current user, no admin required)
$regPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.wispr_lite.host"
New-Item -Path $regPath -Force | Out-Null
Set-ItemProperty -Path $regPath -Name "(default)" -Value $manifestPath

Write-Host "Wispr Lite native host registered."
Write-Host "Manifest: $manifestPath"
Write-Host "Launcher: $batPath"
Write-Host ""
Write-Host "Next: pip install -r ..\python-app\requirements.txt, then toggle the extension on."
