# CornBot Windows installer (ASCII only: irm|iex may not decode UTF-8)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$url  = "https://github.com/genedonsa/yujabs-planner/releases/latest/download/CornBot-windows.zip"
$dest = Join-Path $env:LOCALAPPDATA "CornBot"
$zip  = Join-Path $env:TEMP "CornBot-windows.zip"
Write-Host "Downloading CornBot..."
Invoke-WebRequest -Uri $url -OutFile $zip
Get-Process CornBot -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $dest -Force
Get-ChildItem $dest -Recurse | Unblock-File
Remove-Item $zip
$exe = Join-Path $dest "CornBot.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "CornBot.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk); $s.TargetPath = $exe; $s.WorkingDirectory = $dest; $s.Save()
Write-Host "Installed: $exe (desktop shortcut: CornBot)"
if (-not $env:CORNBOT_NO_OPEN) { Start-Process $exe }
