# 대형폐기물 수수료 안내 웹앱

조례에 **없는** 대형폐기물 품목을 물으면, 그 지자체 조례 금액 체계 안에서 수수료를 정해 **품목·규격·금액만** 보여 준다.
품목이 애매하면 먼저 "이게 맞나요?"를 묻는다. 계산은 검증된 `engine/engine.py`가 전부 한다(웹앱은 감싸기만 함).

- 고객 화면 `/` — 공개, 모바일 우선. 근거(등급·통계 등)는 API 응답에 아예 없다.
- 운영자 화면 `/admin` — 로그인. 검토 대기열, 확정표(엑셀 가져오기/내보내기), 조례 업로드, 표현 사전, 전국 통계 갱신, 이력, 공개 정책.

## 실행
```bash
pip install -r requirements.txt uvicorn
ADMIN_PASSWORD=비밀번호 uvicorn app:app --port 8000
```
처음 실행하면 `var/app.db`(SQLite)에 과천시 조례 159행·확정표 174행·전국 스냅샷이 들어간다.

## 환경변수
| 이름 | 뜻 |
|---|---|
| `ADMIN_PASSWORD` (`ADMIN_ID`, `ADMIN_NAME`) | 운영자 계정 1개. 여러 명은 `ADMIN_USERS='[{"id":"kim","pw":"…","name":"김OO"}]'` |
| `SECRET_KEY` | 세션·확인카드 서명 키(없으면 운영자 비밀번호에서 유도) |
| `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 네이버 검색 API(쇼핑). 없으면 자주 쓰는 후보로 대체 |
| `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` | 쿠팡 파트너스 Open API(승인 필요). 크롤링은 하지 않는다 |
| `BLOB_READ_WRITE_TOKEN` | Vercel Blob(private). 있으면 SQLite 파일을 버전별로 올려 서버리스에서도 데이터 유지 |
| `CRON_SECRET` | 분기별 전국 통계 자동 갱신(`/api/cron/national`) 인증 |
| `DB_PATH` | SQLite 경로 |

## 구성 (HANDOFF 9절 대비 바꾼 점과 이유)
- 백엔드 FastAPI + SQLite — 그대로. 프론트는 빌드 없는 정적 HTML/JS(서버가 직접 제공) — Vite 빌드 단계를 없애 배포·유지가 단순하고, 화면 2개뿐이라 충분하다.
- 확인 카드 상태는 서버 메모리가 아니라 **서명 토큰**에 담는다 — 서버리스 인스턴스가 여러 개여도 흐름이 끊기지 않는다(토큰은 base32 소문자라 금지어 정규식에도 안 걸림).
- Vercel의 디스크는 휘발되므로 `BLOB_READ_WRITE_TOKEN`이 있으면 DB 파일을 Blob에 버전 경로로 저장·복원한다(최근 10개 백업 유지).

## 엔진을 바꾼 곳
`write_client`의 행 생성만 `client_rows(res, local=None)`으로 분리했다(반환형). `local`을 주면 조례 등재 품목을 규격별 현행 금액으로 모두 펼친다. 금액 로직은 그대로이며, CLI 출력은 원본과 바이트 단위로 같다(회귀 테스트 3번).
`build_nat.py`는 같은 로직을 `summarize(rows)` 함수로 감쌌다(CLI 동작 동일).

## 테스트
```bash
python3 tests/regression.py          # 4-3 회귀: 41/54, 48/54, 확정표 사용 54/54
python3 -m pytest -q tests/          # 10절 완료 기준 37개(금지어·기대결과·확인흐름·운영자)
BASE_URL=http://localhost:8000 python3 tests/test_mobile.py   # 360px 가로 스크롤 없음(Playwright)
```

## 데이터 파일
- `data/gwacheon_ordinance.csv` 조례 159행 · `data/gwacheon_confirmed.csv` 확정표 174행 · `data/nat_snap.tsv` 전국 248품목
- `data/gwacheon_display.csv` 조례 원문 규격의 화면 표기(예: `모 든 규 격`→`모든규격`, `300ℓ이상`→`300ℓ 이상~500ℓ 미만`). 금액은 건드리지 않는다.
- `data/gwacheon_methods.csv` 금액 대신 배출 방법으로 답하는 품목(운영자 화면 확정표에서 수정 가능)
