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

특정 키워드가 들어간 나라장터 신규 입찰공고를 자동으로 찾아 **Slack `#나라장터` 채널**로 알리고 **Notion '나라장터' DB**에 정리합니다.

```
Cron / 외부 스케줄러
  └─ /api/watch-g2b
       ├─ 최근 N시간(기본 48h) 게시 공고 조회 (data.go.kr 입찰공고정보서비스, bidNtceNm)
       ├─ 물품/용역/공사/외자 × 키워드(AND 지원) 매칭
       ├─ Notion DB에 공고번호 존재 여부로 중복 판별 → 신규만 선별
       └─ Notion 기록 + Slack 알림
```

### 키워드 문법
- 단일: `키오스크` → 공고명에 키오스크 포함
- AND: `키오스크+유지보수` → 공고명에 키오스크 **그리고** 유지보수 모두 포함

기본 키워드: `베리어프리, 대형폐기물, 키오스크, 무인배출신고시스템` + 각각의 `+유지보수` 조합.

### 설정 (Vercel 환경변수)

| 변수 | 필수 | 설명 |
|------|------|------|
| `DATA_GO_KR_KEY` | ✅ | 공공데이터포털 일반 인증키(Decoding). **"나라장터 입찰공고정보서비스" 활용신청** 필요 |
| `SLACK_WEBHOOK_URL` | ✅ | `#나라장터` 채널용 Slack Incoming Webhook URL |
| `WATCH_KEYWORDS` | | 쉼표구분 키워드(미설정 시 기본값 사용) |
| `WATCH_CATEGORIES` | | `thng,servc,cnstwk,frgcpt` 중 선택 (기본 전체) |
| `WATCH_LOOKBACK_HOURS` | | 조회 시간창. 기본 `48` |
| `CRON_SECRET` | | 설정 시 요청 `Authorization` 헤더 검증 |
| `NOTION_TOKEN` | | Notion 내부 통합 시크릿. 설정 시 정리 + **중복판별** |
| `NOTION_DATABASE_ID` | | '나라장터' 데이터베이스 ID |
| `NOTION_TITLE_PROP` | | title 속성명(기본 `공고명`) |
| `NOTION_BIDNO_PROP` | | 공고번호 속성명(기본 `공고번호`, 중복판별 키) |

### Notion '나라장터' DB 만들기
1. Notion에서 새 **데이터베이스** 생성, 이름 `나라장터`
2. 속성 구성:
   - `공고명` (제목/Title)
   - `공고번호` (텍스트) — 중복판별 키
   - `카테고리` (선택/Select)
   - `기관` (텍스트), `게시일` (텍스트), `마감일` (텍스트)
   - `키워드` (다중 선택/Multi-select)
   - `링크` (URL)
3. https://www.notion.so/my-integrations → **내부 통합** 생성 → 시크릿을 `NOTION_TOKEN` 으로 등록
4. DB 우측 `…` → **연결 추가**로 그 통합을 DB에 연결(권한 부여)
5. DB URL의 32자리 해시를 `NOTION_DATABASE_ID` 로 등록

> Notion 미설정이어도 동작합니다(이 경우 Slack만, 중복판별은 시간창 방식으로 fallback → 하루 1회 실행 권장).

### 준비 절차
1. **공공데이터포털**: 인증키를 `DATA_GO_KR_KEY` 로 등록
2. **Slack**: `#나라장터` 채널 생성 → Incoming Webhook 발급 → `SLACK_WEBHOOK_URL`
3. **Notion**: 위 DB 생성 후 `NOTION_TOKEN`/`NOTION_DATABASE_ID` 등록
4. 재배포

### 동작 확인 (수동 테스트)
```bash
# Slack/Notion 미반영, 매칭 결과만 확인
curl "https://<배포URL>/api/watch-g2b?dry=1"
# 키워드 임시 지정
curl "https://<배포URL>/api/watch-g2b?dry=1&keywords=키오스크+유지보수,대형폐기물"
```

### 하루 여러 번 실행하기
Vercel **Hobby 플랜 Cron은 일 1회**까지만 지원합니다(현재 `vercel.json`은 매일 09:00 KST 1회). 하루 여러 번 원하면:
- **Vercel Pro**: `vercel.json`의 `crons.schedule`을 `0 */3 * * *`(3시간마다) 등으로 변경, 또는
- **외부 스케줄러**(cron-job.org 등): 원하는 주기로 `https://<배포URL>/api/watch-g2b` 호출 (헤더 `Authorization: Bearer <CRON_SECRET>` 추가).

여러 번 실행해도 **Notion 중복판별** 덕분에 같은 공고는 한 번만 알림됩니다.

## 디스클레이머

본 도구의 답변은 AI 기반 참고자료이며 법적 효력이 없습니다. 구체적 사안에 대해서는 반드시 변호사와 상담하시기 바랍니다.
