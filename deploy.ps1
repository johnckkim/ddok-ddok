# ddok-ddok 자동 배포 스크립트 (Windows PowerShell)
# 실행: cd "C:\Users\kibie\내 드라이브\Law\deploy"; ./deploy.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== 똑똑 Vercel 배포 ===" -ForegroundColor Cyan

# 1. 필수 도구 점검
$tools = @{
  git = "https://git-scm.com/downloads"
  gh = "https://cli.github.com/"
  npm = "https://nodejs.org/"
}
foreach ($k in $tools.Keys) {
  if (-not (Get-Command $k -ErrorAction SilentlyContinue)) {
    Write-Host "[오류] $k 미설치 → $($tools[$k]) 에서 설치 후 다시 실행" -ForegroundColor Red
    exit 1
  }
}
if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
  Write-Host "Vercel CLI 설치 중..."
  npm i -g vercel
}

# 2. git init + commit
if (-not (Test-Path .git)) {
  git init | Out-Null
  git branch -M main
}
git add -A | Out-Null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
  git commit -m "deploy $(Get-Date -Format 'yyyyMMdd-HHmm')" | Out-Null
  Write-Host "✓ git commit"
}

# 3. GitHub 인증
$ghStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "▶ GitHub 인증이 필요합니다. 브라우저가 열립니다." -ForegroundColor Yellow
  gh auth login --web
}

# 4. Repo 생성 + push (이미 있으면 push만)
$repoName = "ddok-ddok"
$existing = gh repo view $repoName 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "▶ GitHub repo 생성: $repoName"
  gh repo create $repoName --public --source=. --push
} else {
  Write-Host "✓ repo 이미 존재"
  $remoteSet = git remote -v 2>&1 | Select-String "origin"
  if (-not $remoteSet) {
    $user = gh api user --jq .login
    git remote add origin "https://github.com/$user/$repoName.git"
  }
  git push -u origin main
}

# 5. Vercel 인증
$vTokenPath = "$env:USERPROFILE\.vercel"
if (-not (Test-Path $vTokenPath)) {
  Write-Host "▶ Vercel 인증이 필요합니다. 브라우저가 열립니다." -ForegroundColor Yellow
  vercel login
}

# 6. 환경변수 입력 (이미 등록돼 있으면 건너뜀)
function Set-VercelEnv {
  param([string]$Name, [string]$Value)
  $list = vercel env ls production 2>&1
  if ($list -match $Name) {
    Write-Host "✓ $Name 이미 등록"
    return
  }
  Write-Host "▶ $Name 등록"
  $Value | vercel env add $Name production
}

Write-Host ""
Write-Host "=== 환경변수 등록 ===" -ForegroundColor Cyan
Write-Host "각 키를 입력하세요 (이미 있으면 Enter)"
$ant = Read-Host "ANTHROPIC_API_KEY (sk-ant-api03-...)"
$ds = Read-Host "DEEPSEEK_API_KEY (sk-...)"
$gk = Read-Host "GROK_API_KEY (xai-...)"
$oc = Read-Host "LAW_GO_KR_OC (이메일 ID, default: kibie)"
if ([string]::IsNullOrWhiteSpace($oc)) { $oc = "kibie" }

if ($ant) { Set-VercelEnv "ANTHROPIC_API_KEY" $ant }
if ($ds) { Set-VercelEnv "DEEPSEEK_API_KEY" $ds }
if ($gk) { Set-VercelEnv "GROK_API_KEY" $gk }
if ($oc) { Set-VercelEnv "LAW_GO_KR_OC" $oc }

# 7. 배포
Write-Host ""
Write-Host "=== Vercel --prod 배포 시작 ===" -ForegroundColor Cyan
vercel --prod --yes
Write-Host ""
Write-Host "✅ 배포 완료. 위 URL이 외부 접속 주소입니다." -ForegroundColor Green
