# 상벌점 위젯(하이에듀) — 클로드 없이 설치 (하이에듀위젯_설치.cmd 가 키트를 받아 풀고 이 파일을 부른다)
# 1) 키트 setup.ps1 (파이썬·패키지·크롬 제어 도구)  2) 바탕화면·시작프로그램에 «상벌점 위젯»  3) 위젯을 띄운다 — 처음이면 설정 창이 뜬다
$ErrorActionPreference = "Continue"
$kit = Split-Path $PSScriptRoot -Parent
Set-Location $kit

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  상벌점 위젯(하이에듀) 설치" -ForegroundColor Cyan
Write-Host "  (5~15분 걸릴 수 있어요. 이 창을 닫지 마세요)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $kit "setup.ps1") -Widget
$setupCode = $LASTEXITCODE
$pyw = Join-Path $kit ".venv\Scripts\pythonw.exe"
$py  = Join-Path $kit ".venv\Scripts\python.exe"
$ok = ($setupCode -eq 0) -and (Test-Path $py)
if ($ok) {
    # 위젯·설정 창이 쓰는 것들이 실제로 들어왔나 (pythonw 는 실패해도 아무 말이 없다)
    & $py -c "import keyring, tkinter, playwright, PIL, setup_wizard" 2>$null
    $ok = ($LASTEXITCODE -eq 0)
}
if (-not $ok) {
    Write-Host ""
    Write-Host "  X 설치가 끝나지 않았습니다. 위의 빨간 글씨를 사진으로 찍어 보내 주세요." -ForegroundColor Red
    Write-Host "    (학교망이 막는 경우가 있어요 — 휴대폰 테더링으로 이 파일을 한 번 더 실행해 보세요)"
    Read-Host "닫으려면 Enter"
    exit 1
}

$widget = Join-Path $PSScriptRoot "하이에듀_위젯.pyw"
$sh = New-Object -ComObject WScript.Shell
# 학교 PC는 바탕화면이 OneDrive 로 옮겨져 있는 일이 많다 — GetFolderPath 가 옮겨진 곳을 준다
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Startup'))) {
    $lnk = $sh.CreateShortcut((Join-Path $folder "상벌점 위젯.lnk"))
    $lnk.TargetPath = $pyw
    $lnk.Arguments = '"' + $widget + '"'
    $lnk.WorkingDirectory = $PSScriptRoot
    $lnk.IconLocation = $pyw
    $lnk.Save()
}

Write-Host ""
Write-Host "  바탕화면·시작프로그램에 «상벌점 위젯»을 만들었습니다 (컴퓨터를 켜면 저절로 뜹니다)." -ForegroundColor Green
Write-Host "  위젯을 띄웁니다 — 처음이면 설정 창이 뜹니다. 하이에듀 아이디·비밀번호, 인증서·인증서 암호, 학년·반을 넣고" -ForegroundColor Green
Write-Host "  [저장하고 로그인 확인]을 누르세요. 암호는 윈도우 «자격 증명 관리자»에만 저장됩니다." -ForegroundColor Green
Start-Process -FilePath $pyw -ArgumentList ('"' + $widget + '"') -WorkingDirectory $PSScriptRoot
Start-Sleep 3
