#!/bin/bash
# ddok-ddok 자동 배포 스크립트 (Mac/Linux/WSL)
set -e
echo "=== 똑똑 Vercel 배포 ==="

# 도구 점검
for cmd in git gh npm; do
  command -v $cmd >/dev/null || { echo "[오류] $cmd 미설치"; exit 1; }
done
command -v vercel >/dev/null || { echo "Vercel CLI 설치..."; npm i -g vercel; }

# git init + commit
[ -d .git ] || { git init -q; git branch -M main; }
git add -A
git diff --cached --quiet || git commit -m "deploy $(date +%Y%m%d-%H%M)" -q && echo "✓ git commit"

# GitHub 인증
gh auth status >/dev/null 2>&1 || { echo "▶ GitHub 인증 필요"; gh auth login --web; }

# Repo 생성 + push
REPO="ddok-ddok"
if ! gh repo view "$REPO" >/dev/null 2>&1; then
  echo "▶ Repo 생성: $REPO"
  gh repo create "$REPO" --public --source=. --push
else
  USER=$(gh api user --jq .login)
  git remote -v | grep -q origin || git remote add origin "https://github.com/$USER/$REPO.git"
  git push -u origin main
fi

# Vercel 인증
[ -d "$HOME/.vercel" ] || { echo "▶ Vercel 인증 필요"; vercel login; }

# 환경변수
echo ""
echo "=== 환경변수 등록 ==="
read -p "ANTHROPIC_API_KEY: " ANT
read -p "DEEPSEEK_API_KEY: " DS
read -p "GROK_API_KEY: " GK
read -p "LAW_GO_KR_OC (default: kibie): " OC
OC=${OC:-kibie}

set_env() {
  vercel env ls production 2>&1 | grep -q "^$1 " && echo "✓ $1 이미 등록" || (echo "$2" | vercel env add "$1" production)
}
[ -n "$ANT" ] && set_env "ANTHROPIC_API_KEY" "$ANT"
[ -n "$DS" ] && set_env "DEEPSEEK_API_KEY" "$DS"
[ -n "$GK" ] && set_env "GROK_API_KEY" "$GK"
[ -n "$OC" ] && set_env "LAW_GO_KR_OC" "$OC"

# 배포
echo ""
echo "=== Vercel --prod 배포 ==="
vercel --prod --yes
echo "✅ 완료"
