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

## 3. 품목 판정 순서 (고객이 이름을 넣으면, 2026-11-23 기준)
1. 그 지역 조례 등재(L0) → 그 품목의 모든 규격. 장바구니 `담기` = 조례 품목명.
2. 애매한 이름(예: '침대') → 확인 질문 카드. 쇼핑몰 API 분류명(키 있을 때) → "○○ 맞으신가요?"(무엇인지 확인).
3. 그 지역 조례의 같은 물건(다른 이름·끝말: 양문형냉장고 → 냉장고 규격). 앞말이 규격에 있으면 그 줄만. 간접 답은 `_fit_rows`로
   다른 물건·말하지 않은 종류·봉투/무게 단가 줄을 뺀다. 앞말이 2층·돌·흙·옥·안마·업소 등 다른 종류인데 그 줄이 없으면 3을 건너뛴다.
4. **조례에 없는 품목**: 고객이 쓴 제품명 그대로 계산(다른 항목 이름으로 안내하지 않음, "‘○○’ 항목으로 배출/내놓으시면" 없음).
   과천 확정표·조례의 크기 구분 × (그 지역 k ÷ 과천 k)를 그 지역이 두 번 이상 쓰는 금액 단계에 맞춤(큰 규격은 한 단계 위)
   → 같은 배출 항목 규칙(EQUIV)·유사품목 → 전국 통계 × k → AI가 고른 비슷한 품목의 규격·금액. 금액은 1,000원 단위, `담기` = '기타'.
   확정표(L1) 품목도 앱 카탈로그(=조례)에 없으므로 '기타'.
5. 근거가 없으면(최빈 금액뿐, 맞는 규격 없음, 규격 원문 유실) '확인 후 안내' + 접수번호 + **이름·휴대폰(동의 필수, 90일 후 파기)**.
   계산해서 보여 준 답도 운영자 검토 대기열에 올라간다.

## 4. 환경변수 (Vercel)
| 이름 | 상태 | 용도 |
|---|---|---|
| ADMIN_PASSWORD, SECRET_KEY, CRON_SECRET | 설정됨 | 운영자 로그인·서명·배치 |
| BLOB_READ_WRITE_TOKEN | 설정됨 | DB 스냅숏 |
| AI_GATEWAY_API_KEY | 설정됨 | AI Gateway (무료 등급: Claude 불가, gemini-2.5-flash 7~11초) |
| ANTHROPIC_API_KEY | 설정됨(2026-11-22, Production) | Claude Haiku 5.5 직접 호출(effort low, 1~3초). `temperature` 금지(400). 실패 시 AI Gateway로 넘어가고 `/api/cron/ai` 의 `anthropic` 칸에 이유 표시 |
| NAVER_CLIENT_ID / NAVER_CLIENT_SECRET | **없음** | 쇼핑 검색. 신규 앱 등록 화면에 '검색' API가 없어 발급 못 함 |
| COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY | **없음** | 파트너스 계정이 Open API 미승인(빈 화면) |

## 5. 점검용 주소 (CRON_SECRET 필요)
- AI 점검: `/api/cron/ai?key=…&q=베드 범퍼&m=seoul-eunpyeong` (모델·고른 품목·시도 기록·견적 결과)
  - 모델별 비교: `&models=google/gemini-2.5-flash,openai/gpt-5-mini`
- 수집표 반영: `/api/cron/import?key=…&mode=collected&dry=0&force=1&only=강원_삼척시,전남_곡성군` (only = data/collected 파일 이름, force 를 그 파일에만)
  - 배포 직후(이전 인스턴스가 남은 동안) 돌리면 일부 인스턴스 DB가 늦게 맞춰진다 → 배포가 자리 잡은 뒤 실행하고, 끝나면 그 지역 견적을 두세 번 확인
  - 2026-11-23: 삼척·양양·영덕·익산·완도·평창·고창·울진 8곳을 조례 별표(삼척은 시 신청사이트)로 교체(규격 복원). 평창은 2026-10-08 개정 조례라 공공데이터보다 금액이 높다
- 답변 일관성: 품목 토큰은 service.py 에서 정렬 튜플로 고정(E.tokens 덮어쓰기). 집합 순서가 인스턴스마다 달라 같은 질문에 금액이 다르던 문제. 엔진에서 set 을 순회해 첫 값을 고르는 코드를 새로 쓰지 말 것
- 공공데이터 반영: `/api/cron/import?key=…&targets=서울 전체, 경기 전체&dry=0`

## 6. 다음 할 일 (우선순위)
1. ~~PC에 있는 API 키 파일 찾기~~ — 2026-11-22 완료(ANTHROPIC_API_KEY 등록·Claude 호출 확인). NAVER 키는 PC에 없음.
   - ANTHROPIC_API_KEY 가 들어가면 `ai._anthropic()` 이 먼저 쓰인다(모델 기본 `claude-haiku-5-5`, `ANTHROPIC_MODEL`로 변경).
2. (선택) AI Gateway 유료 크레딧 $5~10 충전 → 코드 수정 없이 Claude Haiku 로 자동 전환.
3. **수집표 품질 점검** — 은평구처럼 옛 표·비교표가 섞인 곳이 없는지 49곳 `data/collected/*.csv` 점검
   (수수료 500원 미만·같은 품목 중복·규격에 '<신 설>' 같은 표식 등). 고치면 `mode=collected&force=1` 로 반영.
4. 휴대폰 실기기로 키보드가 입력창을 가리지 않는지 확인(지금은 Playwright 시뮬레이션으로만 확인).
5. (선택) 문자 자동 발송 — 솔라피/NHN 등 계정이 생기면 운영자 '확정' 시 연락처로 자동 문자.
6. 베드 범퍼처럼 자주 묻는 미등재 품목은 `catalog.EQUIV` 에 규칙 추가(운영 화면 '표현 사전'으로도 가능).
7. **시연용 앱에 장바구니 이식** — 결과 아래 버튼은 '장바구니에 담기' 하나(2026-11-22, 커밋 7791b64. Vercel 무료 일일 배포 한도 100회에 걸려 운영 반영은 다음 날 재배포 필요). 규격이 여러 개인 품목은 줄을 눌러 하나 고른 뒤 담는다.
   - 코드: `web/app.js` 의 `/* 장바구니 */` 구역(`addToCart`·`cartHTML`·`renderCart`·`openCart`·`cartRows`·`cartText`), `groups`·`pickBox`, 머리 `#cartBtn`, `style.css` 끝 `/* 장바구니 */`.
   - 내려받기: `POST /api/quote/export` 에 행마다 `수량` 을 넣으면 수량·금액 칸과 합계 줄이 붙는다(없으면 예전 4칸 그대로).
   - 장바구니는 메모리에만 있고(새로고침하면 비움), 지역을 바꾸면 비운다(수수료가 지역마다 다름).
   - 지역은 기억하지 않는다: 예전 `localStorage['bw.muni']` 는 첫 로드 때 지운다.
   - **앱 장바구니 연동 자리**(`web/app.js` `bridge()`): 답변 줄마다 붙은 장바구니 아이콘이나 '장바구니에 담기'를 누를 때마다
     같은 내용을 ① `window` 이벤트 `bw:add-to-cart`(detail) ② `window.UdongCart.add(item)`(앱이 넣어 두면 호출)
     ③ `ReactNativeWebView.postMessage(JSON)` ④ iframe이면 `parent.postMessage(item)` 로 보낸다.
     item = `{type:'bw:add-to-cart', municipality, municipalityName, item(조례 한국어 이름), spec, fee(숫자|null), feeText, note, qty:1}`.
     앱에 심을 때는 ②나 ③을 받아 실제 장바구니(스티커 결제)에 넣으면 된다.
   - **조례에 없는 품목 = 기타 + 금액**(2026-11-23 결정): 다른 항목 이름으로 안내하지 않고 고객이 쓴 제품명 그대로 계산 금액을 안내한다
     (과천 확정표 크기 구분 × 지역 금액 수준 → 전국 통계 × 지역 수준 → AI가 고른 비슷한 품목의 규격·금액 순, 근거 없으면 확인 후 안내).
     금액은 1,000원 단위. API 행의 `담기` 칸이 '기타'면 장바구니 품목은 '기타', 아니면 조례 품목명.
     앱 카탈로그의 기타는 `category '기타' / item_name '금액'` 세 줄(1,000·5,000·10,000원, 과천 데모 id gc142~gc144)뿐이라
     연동 item에 `etcLines:[{category,item_name:'금액',item_specification,price,count}]`(예: 7,000원 → 5,000×1 + 1,000×2)를 실어 보낸다.
     앱 `UserCartController.add()`는 같은 discharge_item_id 줄을 바꿔치기하므로, 기타 금액 줄은 **수량을 더해서** 넣어야 한다.
     제품명(`productName`)은 앱 장바구니엔 안 보이므로 주문 메모·조례 보완 자료로 따로 저장할 것.
     앱 데모 AI 화면(`demo_ai_fee_screen.dart`)은 아직 `담기`를 모른다 — 기타 행이면 위 금액 줄로 담도록 바꿀 것.

### 6-9. 데이터 남은 일 (2026-11-23 4차 점검 반영)
- 4차 반영(조례 원문 확인):
  - 진도군 [별표 1-2] 폐전기·폐전자제품 면제 8줄
  - 전주시 [별표 2] 라. 전자제품 27품목 무상(판매점 역회수·무상 방문수거)
  - 남원시 제17조제1항제1호다목: 「전자제품등자원순환법 시행령」 제14조 대상 전기·전자제품은 수수료 없음. 품목명은 전주 목록 + '기타 전기·전자제품'
  - 의왕시 [별표 3]: 돌침대·매트리스·침대틀·책상·욕조·운동기구 16줄의 규격 복원
  - 남동구: 공공데이터(2026-07-31)에 전기·전자제품이 하나도 없어, 현행 조례 [별표 1](2026-09-21)의 가전 등 36줄을 보충. source 가 web 으로 바뀌어 공공데이터 배치가 덮어쓰지 않으니, 남동 공공데이터가 갱신되면 csv 를 다시 만들 것
- 확인만 함(바꿀 것 없음):
  - 장수·진주: DB가 조례 별표와 같다. 진주의 154행은 병합 셀 중복
  - 시흥·미추홀·울산 중구: 현행 조례 별표에 가전 줄이 없다. 시흥 [별표 2]는 전자제품을 재활용가능자원으로만 적었고, 무상이라는 문구는 없다
- 엔진 규칙(4차):
  - 무상 줄에 '기타 폐전기·폐전자제품'·'기타 전기·전자제품' 같은 묶음이 있으면, 조례·확정표에 없는 가전(classify '가전·전자')도 무상으로 답한다(_elec_free)
    - 적용 안 함: '소형' 묶음(오산 '기타(소형 가전제품)'), 매트·장판·담요·보일러, TV장 같은 가구
  - 악기 '기타'를 조례의 '기타'(그 밖의 물건) 묶음 줄·무상 줄로 답하지 않는다(_drop_catchall·_method_hit). 묶음 줄만 있으면 '통기타'로 다시 계산
  - '보일러기' = 보일러(APP_SYN)
- 화면(4차):
  - 번역 결과를 localStorage 'bw.tr1' 에 저장해 다시 열 때 번역 요청을 줄인다(지역은 저장하지 않음). 서버 번역 규칙(tr4)을 바꾸면 이 키도 올릴 것
  - 없는 지역 이름을 치면 글자 1~2개 차이 나는 지역을 '혹시 이 지역인가요?' 단추로 보여 준다

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
