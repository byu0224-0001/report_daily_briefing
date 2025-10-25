# ============================================
# GitHub Secrets 자동 설정 스크립트
# ============================================

Write-Host "🔐 GitHub Secrets 자동 설정 시작..." -ForegroundColor Cyan
Write-Host ""

# 1. GitHub CLI 설치 확인
Write-Host "1️⃣ GitHub CLI 설치 확인 중..." -ForegroundColor Yellow
if (!(Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "❌ GitHub CLI가 설치되어 있지 않습니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "설치 방법:" -ForegroundColor Green
    Write-Host "  winget install --id GitHub.cli" -ForegroundColor White
    Write-Host ""
    Write-Host "또는 수동 다운로드:" -ForegroundColor Green
    Write-Host "  https://cli.github.com/" -ForegroundColor White
    Write-Host ""
    exit 1
}
Write-Host "✅ GitHub CLI 설치됨" -ForegroundColor Green

# 2. GitHub 인증 확인
Write-Host ""
Write-Host "2️⃣ GitHub 인증 확인 중..." -ForegroundColor Yellow
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ GitHub 인증이 필요합니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "인증 방법:" -ForegroundColor Green
    Write-Host "  gh auth login" -ForegroundColor White
    Write-Host ""
    exit 1
}
Write-Host "✅ GitHub 인증됨" -ForegroundColor Green

# 3. .env 파일 읽기
Write-Host ""
Write-Host "3️⃣ .env 파일 읽기 중..." -ForegroundColor Yellow
$envPath = ".env"
if (!(Test-Path $envPath)) {
    Write-Host "❌ .env 파일을 찾을 수 없습니다: $envPath" -ForegroundColor Red
    exit 1
}

# .env 파일 파싱
$envVars = @{}
Get-Content $envPath | ForEach-Object {
    if ($_ -match '^([^#][^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        $envVars[$key] = $value
    }
}

Write-Host "✅ .env 파일 읽기 완료" -ForegroundColor Green

# 4. 필수 변수 확인
Write-Host ""
Write-Host "4️⃣ 환경 변수 확인 중..." -ForegroundColor Yellow
$requiredVars = @("OPENAI_API_KEY", "OPENAI_MODEL_NAME", "NOTION_API_KEY", "NOTION_DATABASE_ID")
$missingVars = @()

foreach ($var in $requiredVars) {
    if (!$envVars.ContainsKey($var) -or $envVars[$var] -match '^(x+|secret_x+|sk-x+)$') {
        $missingVars += $var
        Write-Host "⚠️  $var : 값이 없거나 예시 값입니다" -ForegroundColor Yellow
    } else {
        $preview = $envVars[$var].Substring(0, [Math]::Min(20, $envVars[$var].Length)) + "..."
        Write-Host "✅ $var : $preview" -ForegroundColor Green
    }
}

if ($missingVars.Count -gt 0) {
    Write-Host ""
    Write-Host "❌ 다음 변수들을 .env 파일에 설정해주세요:" -ForegroundColor Red
    foreach ($var in $missingVars) {
        Write-Host "  - $var" -ForegroundColor Yellow
    }
    Write-Host ""
    exit 1
}

# 5. Secrets 설정 확인
Write-Host ""
Write-Host "5️⃣ GitHub Secrets 설정을 시작합니다..." -ForegroundColor Yellow
Write-Host ""
Write-Host "⚠️  주의: 다음 Secrets가 레포지토리에 등록됩니다:" -ForegroundColor Yellow
foreach ($var in $requiredVars) {
    Write-Host "  - $var" -ForegroundColor White
}
Write-Host ""
$confirm = Read-Host "계속하시겠습니까? (Y/N)"
if ($confirm -ne 'Y' -and $confirm -ne 'y') {
    Write-Host "❌ 취소되었습니다." -ForegroundColor Red
    exit 0
}

# 6. Secrets 등록
Write-Host ""
Write-Host "6️⃣ Secrets 등록 중..." -ForegroundColor Yellow
$repo = "byu0224-0001/report_daily_briefing"

foreach ($var in $requiredVars) {
    Write-Host "  설정 중: $var..." -ForegroundColor Cyan
    $value = $envVars[$var]
    
    # PowerShell에서 gh secret set 실행
    $value | gh secret set $var --repo $repo
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ $var 설정 완료" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $var 설정 실패" -ForegroundColor Red
    }
}

# 7. 완료
Write-Host ""
Write-Host "🎉 모든 Secrets 설정이 완료되었습니다!" -ForegroundColor Green
Write-Host ""
Write-Host "다음 단계:" -ForegroundColor Cyan
Write-Host "  1. GitHub Actions 확인: https://github.com/$repo/actions" -ForegroundColor White
Write-Host "  2. 수동 실행 테스트: Actions → Daily AI Briefing → Run workflow" -ForegroundColor White
Write-Host ""

