# 똑똑 — 한국 법률 분석 채팅 (Vercel 배포)

Vercel Edge Functions로 API 키 보호 + 스트리밍 응답.

## 디렉토리 구조

```
deploy/
├── index.html          # 프론트엔드 (키 노출 0)
├── api/
│   ├── chat.js         # Anthropic Claude streaming proxy
│   ├── classify.js     # DeepSeek 질문 분류
│   ├── verify.js       # DeepSeek 검증 (백그라운드)
│   ├── cross.js        # Grok 교차 검증 (백그라운드)
│   ├── reasoner.js     # DeepSeek-reasoner 딥씽크
│   └── lawsearch.js    # law.go.kr DRF proxy (CORS 우회)
├── vercel.json         # Edge runtime + 보안 헤더
├── package.json
└── .env.example        # 환경변수 가이드
```

## 배포 절차 (사용자 직접 실행)

### 1단계: GitHub 리포 생성

```bash
cd "C:\Users\kibie\내 드라이브\Law\deploy"
git init
git add .
git commit -m "똑똑 v2.2 — Vercel Edge Functions 배포"
git branch -M main
git remote add origin git@github.com:<USERNAME>/ddok-ddok.git
git push -u origin main
```

GitHub에 신규 리포 `ddok-ddok` 생성 후 push.

### 2단계: Vercel 배포 (옵션 A — 웹)

1. https://vercel.com/new 접속
2. **Import Git Repository** → 방금 push한 `ddok-ddok` 선택
3. **Framework Preset**: Other (자동 감지)
4. **Environment Variables** (중요):
   - `ANTHROPIC_API_KEY` → Claude 키
   - `DEEPSEEK_API_KEY` → DeepSeek 키
   - `GROK_API_KEY` → Grok 키
   - `LAW_GO_KR_OC` → law.go.kr OC (이메일 ID)
5. **Deploy** 클릭 → 약 30초 후 URL 발급

### 2단계: Vercel 배포 (옵션 B — CLI)

```bash
npm i -g vercel
cd deploy/
vercel login          # 처음 한 번만
vercel --prod
# 프로젝트 이름·환경변수 입력 후 자동 배포
```

배포 완료 후 외부 URL: `https://ddok-ddok-<hash>.vercel.app` 형식.

### 3단계: 환경변수 등록 (CLI 사용 시)

```bash
vercel env add ANTHROPIC_API_KEY production
# 값 입력 (한 번만)
vercel env add DEEPSEEK_API_KEY production
vercel env add GROK_API_KEY production
vercel env add LAW_GO_KR_OC production
vercel --prod          # 환경변수 적용 후 재배포
```

## 동작 흐름

```
사용자 → ddok-ddok.vercel.app
        └─ index.html (키 0건)
            ├─ POST /api/classify  (DeepSeek 분류)
            ├─ POST /api/lawsearch (law.go.kr 검색)
            ├─ POST /api/chat      (Claude streaming SSE)
            ├─ POST /api/verify    (백그라운드 검증)
            ├─ POST /api/cross     (백그라운드 교차)
            └─ POST /api/reasoner  (딥씽크 ON 시)
                ↓
        Vercel Edge Functions
            └─ process.env.* (키 보관)
                ↓
        외부 API (Anthropic / DeepSeek / xAI / law.go.kr)
```

## 주요 §-rule

- §LAW-NO-MOCK-IN-PRODUCTION
- §LAW-MULTI-PASS-RAG
- §LAW-DISSENT-SECTION-MANDATORY
- §TABLE-CELL-SINGLE-LINE-PRIORITY
- §TITLE-SINGLE-LINE
- §LAW-DISCLAIMER

## 나라장터 입찰공고 키워드 알림 (`/api/watch-g2b`)

특정 키워드가 들어간 나라장터 신규 입찰공고를 매일 자동으로 찾아 Slack으로 알려줍니다.

```
Vercel Cron (매일 00:00 UTC = 09:00 KST)
  └─ /api/watch-g2b
       ├─ 최근 24h 게시 공고 조회 (data.go.kr 입찰공고정보서비스, bidNtceNm 키워드)
       ├─ 물품/용역/공사/외자 4개 카테고리 × 키워드별 조회 → 공고번호로 중복 제거
       └─ 매칭분을 Slack Incoming Webhook 으로 전송
```

### 설정 (Vercel 환경변수)

| 변수 | 필수 | 설명 |
|------|------|------|
| `DATA_GO_KR_KEY` | ✅ | 공공데이터포털 일반 인증키(Decoding). **"조달청\_나라장터 입찰공고정보서비스" 활용신청** 필요 |
| `SLACK_WEBHOOK_URL` | ✅ | Slack Incoming Webhook URL |
| `WATCH_KEYWORDS` | ✅ | 쉼표로 구분한 키워드. 예: `인공지능,데이터 구축,LLM` |
| `WATCH_CATEGORIES` | | `thng,servc,cnstwk,frgcpt` 중 선택 (기본 전체) |
| `WATCH_LOOKBACK_HOURS` | | 조회 시간창. 기본 `24` |
| `CRON_SECRET` | | 설정 시 Cron 요청 `Authorization` 헤더 검증 |

### 준비 절차

1. **공공데이터포털**: `data.go.kr` 로그인 → "조달청_나라장터 입찰공고정보서비스" 활용신청 → 인증키를 `DATA_GO_KR_KEY` 로 등록
2. **Slack**: 워크스페이스 앱 설정 → Incoming Webhooks 활성화 → 채널 지정 → 발급된 URL을 `SLACK_WEBHOOK_URL` 로 등록
3. **키워드**: `WATCH_KEYWORDS` 에 모니터링할 키워드 입력
4. 재배포 → Cron이 매일 자동 실행

### 동작 확인 (수동 테스트)

```bash
# Slack 전송 없이 매칭 결과만 확인
curl "https://<배포URL>/api/watch-g2b?dry=1"

# 키워드 임시 지정 테스트
curl "https://<배포URL>/api/watch-g2b?dry=1&keywords=인공지능,데이터"
```

> ⚠️ Vercel **Hobby 플랜은 Cron 일 1회**까지만 지원합니다. 더 자주(예: 1시간마다) 돌리려면 Pro 플랜 또는 외부 스케줄러(cron-job.org 등)에서 `CRON_SECRET` 헤더와 함께 호출하세요.

## 디스클레이머

본 도구의 답변은 AI 기반 참고자료이며 법적 효력이 없습니다. 구체적 사안에 대해서는 반드시 변호사와 상담하시기 바랍니다.
