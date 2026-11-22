# 대형폐기물 수수료 안내 웹앱 — 이어서 작업하기 (2026-11-22 기준)

클라우드 세션에서 하던 작업을 로컬 새 창에서 이어 가기 위한 인수인계서.
비밀값(관리자 비밀번호·배치 키·API 키)은 이 파일에 적지 않는다 → Vercel 환경변수와 이전 대화 참고.

## 1. 지금 상태 한눈에
- 운영 주소: https://bulky-waste-fee.vercel.app (고객) · /admin (운영자, 아이디 `admin`)
- 코드: GitHub `johnckkim/ddok-ddok`, 브랜치 **`claude/bulky-waste-fee-webapp-nadjzo`**, 폴더 `bulky-waste/`
- 배포: Vercel 팀 `team_czQz5L9DUralWVsQruIpJd8K`, 프로젝트 `bulky-waste-fee` (`prj_GmUp37OlLOSCROmgmyHwIZ4WXMWh`), 리전 icn1
  - 지금까지는 Vercel MCP `create_deployment`(gitSource: org johnckkim / repo ddok-ddok / ref 위 브랜치 / sha) + target production 으로 배포했다.
  - 로컬에선 `cd bulky-waste && vercel --prod` 로도 가능(프로젝트 연결 필요).
- 지자체 131곳 운영 중(공공데이터 82곳 + 공식 홈페이지·조례 별표 수집 49곳 + 과천 확정표).
- 테스트: `python3 -m pytest -q tests/test_app.py` (45개 통과), `python3 tests/regression.py` (41/48, 54/54 PASS), `python3 tests/test_mobile.py` (Playwright).

## 2. 구조
- `app.py` → `server/main.py`(FastAPI 라우트·미들웨어) · `server/service.py`(품목 판정·확인 질문·접수) · `server/catalog.py`(분류·동의어·EQUIV 같은 배출 항목)
- `server/ai.py` — 조례에서 못 찾은 이름을 AI가 **그 지자체 조례 품목명 중에서만** 고르게 함(금액은 조례 금액). 30일 캐시.
- `server/shopping.py` — 네이버/쿠팡 공식 API(키 없으면 꺼짐). `server/store.py` — SQLite + Vercel Blob 스냅숏 동기화.
- `server/admin.py` + `web/admin.*` — 운영자 화면(검토 대기열·확정표·조례·표현 사전·전국 통계·이력·설정).
- `web/index.html·app.js·style.css` — 고객 채팅 화면(첫 질문은 항상 지역, visualViewport로 키보드 대응).
- `engine/engine.py` — 스킬 엔진(손대지 않음, `client_rows` 만 추가). `data/` — 조례·확정표·전국 통계·수집표.
- `tools/` — 수집 도구(배포 제외): `law.py`(국가법령정보센터 현행 자치법규 별표 판독, **[연혁] 파일은 건너뜀**), `hwp.py`, `tbl.py`, `save.py`.
- 고객 응답 금지어(정규식) `L[0-4]|L\?|신뢰도|보정|중앙값|통계|추정|유사|근거|k=` → 0건 유지(테스트가 검사).

## 3. 품목 판정 순서 (고객이 이름을 넣으면)
1. 조례 등재(L0) / 확정표(L1) → 바로 금액
2. 애매한 이름(예: '침대') → 확인 질문 카드
3. 조례에 없으면 `catalog.EQUIV` 같은 배출 항목(예: 베드 범퍼 → 놀이매트·쿠션·방석·이불) → 금액 + "‘○○’ 항목으로 배출"
4. 쇼핑몰 API 분류명(키 있을 때) → "○○ 맞으신가요?"
5. AI가 조례 품목명 중 선택 → "‘○○’ 항목으로 내놓으시면 됩니다. 이대로 안내해 드릴까요?"
6. 그래도 없으면 '확인 후 안내' + 접수번호 + **이름·휴대폰(동의 필수, 90일 후 파기)** → 운영자 검토 대기열에 연락처·문자 문구 복사

## 4. 환경변수 (Vercel)
| 이름 | 상태 | 용도 |
|---|---|---|
| ADMIN_PASSWORD, SECRET_KEY, CRON_SECRET | 설정됨 | 운영자 로그인·서명·배치 |
| BLOB_READ_WRITE_TOKEN | 설정됨 | DB 스냅숏 |
| AI_GATEWAY_API_KEY | 설정됨 | AI Gateway (무료 등급: Claude 불가, gemini-2.5-flash 7~11초) |
| ANTHROPIC_API_KEY | **없음** | 넣으면 Claude Haiku 직접 호출(1~2초, 더 정확). 코드 준비 완료 |
| NAVER_CLIENT_ID / NAVER_CLIENT_SECRET | **없음** | 쇼핑 검색. 신규 앱 등록 화면에 '검색' API가 없어 발급 못 함 |
| COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY | **없음** | 파트너스 계정이 Open API 미승인(빈 화면) |

## 5. 점검용 주소 (CRON_SECRET 필요)
- AI 점검: `/api/cron/ai?key=…&q=베드 범퍼&m=seoul-eunpyeong` (모델·고른 품목·시도 기록·견적 결과)
  - 모델별 비교: `&models=google/gemini-2.5-flash,openai/gpt-5-mini`
- 수집표 반영: `/api/cron/import?key=…&mode=collected&dry=0&force=1`
- 공공데이터 반영: `/api/cron/import?key=…&targets=서울 전체, 경기 전체&dry=0`

## 6. 다음 할 일 (우선순위)
1. **PC에 있는 API 키 파일 찾기** — `sk-ant`(Anthropic), `NAVER_CLIENT`, `.env` 검색 → Vercel 환경변수 등록 → 재배포 → `/api/cron/ai` 로 확인.
   - ANTHROPIC_API_KEY 가 들어가면 `ai._anthropic()` 이 먼저 쓰인다(모델 기본 `claude-haiku-5-5`, `ANTHROPIC_MODEL`로 변경).
2. (선택) AI Gateway 유료 크레딧 $5~10 충전 → 코드 수정 없이 Claude Haiku 로 자동 전환.
3. **수집표 품질 점검** — 은평구처럼 옛 표·비교표가 섞인 곳이 없는지 49곳 `data/collected/*.csv` 점검
   (수수료 500원 미만·같은 품목 중복·규격에 '<신 설>' 같은 표식 등). 고치면 `mode=collected&force=1` 로 반영.
4. 휴대폰 실기기로 키보드가 입력창을 가리지 않는지 확인(지금은 Playwright 시뮬레이션으로만 확인).
5. (선택) 문자 자동 발송 — 솔라피/NHN 등 계정이 생기면 운영자 '확정' 시 연락처로 자동 문자.
6. 베드 범퍼처럼 자주 묻는 미등재 품목은 `catalog.EQUIV` 에 규칙 추가(운영 화면 '표현 사전'으로도 가능).

## 7. 로컬에서 시작
```bash
git clone https://github.com/johnckkim/ddok-ddok.git && cd ddok-ddok
git checkout claude/bulky-waste-fee-webapp-nadjzo
cd bulky-waste
pip install -r requirements.txt pytest httpx playwright pdfplumber olefile
ADMIN_PASSWORD=x RATE_LIMIT_SCALE=1000 python3 -m uvicorn app:app --port 8765   # http://localhost:8765
python3 -m pytest -q tests/test_app.py
```
로컬 DB는 과천만 들어 있다. 운영과 같은 131곳이 필요하면 공공데이터(data.go.kr 15114146)와 `data/collected` 를 가져온다:
`server/importer.run(natdata.cached_rows(), importer.parse_targets(open('data/targets_calendar.txt').read()), 'local', force=True, dry=False)`
그리고 `importer.import_collected('data/collected', 'local', force=True, dry=False)`.

## 8. 사용자 선호
두괄식·한국어. 스스로 기준 세우고 엄격히 검증, 중간 확인 질문 없이 끝까지. 고객 화면엔 근거 없이 품목·규격·수수료·안내만.
