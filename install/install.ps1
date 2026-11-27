# 콘봇 윈도우 설치: 받기 → 내 컴퓨터에 풀기 → 바탕화면 아이콘 → 열기. 회원이 따로 깔 것은 없음.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$url  = "https://github.com/genedonsa/yujabs-planner/releases/latest/download/CornBot-windows.zip"
$dest = Join-Path $env:LOCALAPPDATA "CornBot"
$zip  = Join-Path $env:TEMP "CornBot-windows.zip"
Write-Host "콘봇 받는 중..."
Invoke-WebRequest -Uri $url -OutFile $zip
Get-Process CornBot -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $dest -Force
Get-ChildItem $dest -Recurse | Unblock-File
Remove-Item $zip
$exe = Join-Path $dest "CornBot.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "콘봇.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk); $s.TargetPath = $exe; $s.WorkingDirectory = $dest; $s.Save()
Write-Host "설치 완료: $exe (바탕화면에 '콘봇' 아이콘을 만들었어요)"
Start-Process $exe
