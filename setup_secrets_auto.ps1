# ============================================
# GitHub Secrets 자동 등록 스크립트 (1-Click)
# ============================================

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  GitHub Secrets 자동 등록 시작" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

$REPO = "byu0224-0001/report_daily_briefing"

# 1. GitHub CLI 설치 확인
Write-Host "[1/5] GitHub CLI 확인 중..." -ForegroundColor Yellow
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "   [!] GitHub CLI가 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "   자동 설치를 시작합니다..." -ForegroundColor Green
    Write-Host ""
    
    try {
        winget install --id GitHub.cli --silent --accept-package-agreements --accept-source-agreements
        Write-Host "   [OK] GitHub CLI 설치 완료" -ForegroundColor Green
        Write-Host ""
        Write-Host "   PowerShell을 재시작한 후 다시 실행해주세요." -ForegroundColor Yellow
        Write-Host "   (PATH 환경변수 갱신을 위해 필요합니다)" -ForegroundColor Yellow
        Write-Host ""
        pause
        exit 0
    } catch {
        Write-Host "   [ERROR] 자동 설치 실패" -ForegroundColor Red
        Write-Host ""
        Write-Host "   수동 설치 방법:" -ForegroundColor Green
        Write-Host "   1. https://cli.github.com/ 접속" -ForegroundColor White
        Write-Host "   2. Windows 용 설치 파일 다운로드 및 설치" -ForegroundColor White
        Write-Host "   3. PowerShell 재시작 후 다시 실행" -ForegroundColor White
        Write-Host ""
        pause
        exit 1
    }
} else {
    Write-Host "   [OK] GitHub CLI 설치됨" -ForegroundColor Green
}

# 2. GitHub 인증 확인
Write-Host ""
Write-Host "[2/5] GitHub 인증 확인 중..." -ForegroundColor Yellow
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "   [!] GitHub 인증이 필요합니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "   자동 로그인을 시작합니다..." -ForegroundColor Green
    Write-Host "   (브라우저가 열립니다. GitHub 계정으로 로그인해주세요)" -ForegroundColor Yellow
    Write-Host ""
    
    gh auth login
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "   [ERROR] 인증 실패" -ForegroundColor Red
        Write-Host ""
        pause
        exit 1
    }
    Write-Host ""
    Write-Host "   [OK] GitHub 인증 완료" -ForegroundColor Green
} else {
    Write-Host "   [OK] GitHub 인증됨" -ForegroundColor Green
}

# 3. .env 파일 읽기
Write-Host ""
Write-Host "[3/5] 환경 변수 읽기 중..." -ForegroundColor Yellow
$envPath = ".env"
if (!(Test-Path $envPath)) {
    Write-Host "   [ERROR] .env 파일을 찾을 수 없습니다: $envPath" -ForegroundColor Red
    Write-Host ""
    pause
    exit 1
}

# .env 파일 파싱
$secrets = @{
    "OPENAI_API_KEY" = ""
    "OPENAI_MODEL_NAME" = ""
    "NOTION_API_KEY" = ""
    "NOTION_DATABASE_ID" = ""
}

Get-Content $envPath | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        if ($secrets.ContainsKey($key)) {
            $secrets[$key] = $value
        }
    }
}

# 4. 값 검증
Write-Host ""
Write-Host "[4/5] 값 검증 중..." -ForegroundColor Yellow
$allValid = $true
foreach ($key in $secrets.Keys) {
    $value = $secrets[$key]
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '^(x+|secret_x+|sk-x+)$') {
        Write-Host "   [!] $key : 값이 없거나 예시 값입니다" -ForegroundColor Red
        $allValid = $false
    } else {
        $preview = if ($value.Length -gt 30) { $value.Substring(0, 30) + "..." } else { $value }
        Write-Host "   [OK] $key : $preview" -ForegroundColor Green
    }
}

if (-not $allValid) {
    Write-Host ""
    Write-Host "   [ERROR] 일부 환경 변수가 설정되지 않았습니다." -ForegroundColor Red
    Write-Host "   .env 파일을 확인해주세요." -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}

# 5. Secrets 등록
Write-Host ""
Write-Host "[5/5] GitHub Secrets 등록 중..." -ForegroundColor Yellow
Write-Host ""
Write-Host "   레포지토리: $REPO" -ForegroundColor Cyan
Write-Host "   등록할 Secrets: 4개" -ForegroundColor Cyan
Write-Host ""

$success = 0
$failed = 0

foreach ($key in $secrets.Keys) {
    Write-Host "   [$key] 등록 중..." -ForegroundColor White
    
    try {
        $value = $secrets[$key]
        # PowerShell에서 gh secret set 실행
        $value | gh secret set $key --repo $REPO 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "   [OK] $key 등록 완료" -ForegroundColor Green
            $success++
        } else {
            Write-Host "   [ERROR] $key 등록 실패" -ForegroundColor Red
            $failed++
        }
    } catch {
        Write-Host "   [ERROR] $key 등록 실패: $_" -ForegroundColor Red
        $failed++
    }
    Write-Host ""
}

# 6. 결과 요약
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  등록 완료!" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "   성공: $success / 4" -ForegroundColor Green
if ($failed -gt 0) {
    Write-Host "   실패: $failed / 4" -ForegroundColor Red
}
Write-Host ""

if ($success -eq 4) {
    Write-Host "[SUCCESS] 모든 Secrets가 성공적으로 등록되었습니다!" -ForegroundColor Green
    Write-Host ""
    Write-Host "다음 단계:" -ForegroundColor Yellow
    Write-Host "   1. GitHub Actions 확인:" -ForegroundColor White
    Write-Host "      https://github.com/$REPO/actions" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   2. Secrets 확인:" -ForegroundColor White
    Write-Host "      https://github.com/$REPO/settings/secrets/actions" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   3. 수동 실행 테스트:" -ForegroundColor White
    Write-Host "      Actions -> Daily AI Briefing -> Run workflow" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "[WARNING] 일부 Secrets 등록에 실패했습니다." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "수동으로 등록해주세요:" -ForegroundColor Yellow
    Write-Host "   https://github.com/$REPO/settings/secrets/actions" -ForegroundColor Cyan
    Write-Host ""
}

pause


