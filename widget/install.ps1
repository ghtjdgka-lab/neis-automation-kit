# 바로가기 위젯 — 클로드 없이 설치 (바로가기위젯_설치.cmd 가 키트를 받아 풀고 이 파일을 부른다)
# 1) 키트 setup.ps1 (파이썬·패키지·크롬 제어 도구)  2) 설정 창(지역·인증서)을 띄운다 — 저장하면 위젯이 뜬다
$ErrorActionPreference = "Continue"
$kit = Split-Path $PSScriptRoot -Parent
Set-Location $kit

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  나이스·에듀파인 바로가기 위젯 설치" -ForegroundColor Cyan
Write-Host "  (5~15분 걸릴 수 있어요. 이 창을 닫지 마세요)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $kit "setup.ps1") -Widget
$setupCode = $LASTEXITCODE
$pyw = Join-Path $kit ".venv\Scripts\pythonw.exe"
$py  = Join-Path $kit ".venv\Scripts\python.exe"
$ok = ($setupCode -eq 0) -and (Test-Path $py)
if ($ok) {
    # 설정 창이 쓰는 것들이 실제로 들어왔나 (pythonw 는 실패해도 아무 말이 없다)
    & $py -c "import keyring, psutil, tkinter, playwright, setup_wizard" 2>$null
    $ok = ($LASTEXITCODE -eq 0)
}
if (-not $ok) {
    Write-Host ""
    Write-Host "  X 설치가 끝나지 않았습니다. 위의 빨간 글씨를 사진으로 찍어 보내 주세요." -ForegroundColor Red
    Write-Host "    (학교망이 막는 경우가 있어요 — 휴대폰 테더링으로 이 파일을 한 번 더 실행해 보세요)"
    Read-Host "닫으려면 Enter"
    exit 1
}

Write-Host ""
Write-Host "  설정 창을 띄웁니다 — 지역을 고르고 인증서 암호를 넣은 뒤 [저장하고 위젯 켜기]를 누르세요." -ForegroundColor Green
Start-Process -FilePath $pyw -ArgumentList ('"' + (Join-Path $PSScriptRoot "바로가기_설정창.pyw") + '"') -WorkingDirectory $PSScriptRoot
Start-Sleep 3
