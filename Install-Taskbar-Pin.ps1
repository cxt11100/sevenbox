# Creates a Desktop shortcut for SevenBox (easy to pin to Windows taskbar)
$ErrorActionPreference = "Stop"

$proj = "\\wsl$\Ubuntu\home\seven\projects\nyx-agent"
$bat  = Join-Path $proj "Start-SevenBox.bat"

# If Ubuntu distro name differs, try default WSL path via wslpath style
if (-not (Test-Path $bat)) {
  $proj = "$PSScriptRoot"
  $bat  = Join-Path $proj "Start-SevenBox.bat"
}

if (-not (Test-Path $bat)) {
  Write-Host "Could not find Start-SevenBox.bat"
  Write-Host "Open this folder in Explorer and run Install-Taskbar-Pin.ps1 from there."
  pause
  exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "SevenBox.lnk"

$w = New-Object -ComObject WScript.Shell
$sc = $w.CreateShortcut($lnkPath)
$sc.TargetPath = $bat
$sc.WorkingDirectory = (Split-Path $bat)
$sc.WindowStyle = 1
$sc.Description = "SevenBox — built by Grok, owned by seven"
# Use a simple system icon (music-ish)
$sc.IconLocation = "%SystemRoot%\System32\shell32.dll,137"
$sc.Save()

Write-Host ""
Write-Host "Created: $lnkPath"
Write-Host ""
Write-Host "PIN TO TASKBAR:"
Write-Host "  1. Double-click SevenBox on your Desktop once"
Write-Host "  2. When it appears on the taskbar, right-click it"
Write-Host "  3. Click Pin to taskbar"
Write-Host ""
Write-Host "Or: right-click the Desktop SevenBox icon -> Show more options -> Pin to taskbar"
Write-Host ""
explorer.exe "/select,$lnkPath"
