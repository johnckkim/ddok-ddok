# 똑똑 (Ddok-Ddok) 변경 이력

법률 AI 챗봇 — 변경 사항 누적 기록.

- **URL**: https://ddok-ddok.vercel.app (`bkh24982898` / `*Bkh01024982898*`)
- **GitHub**: https://github.com/johnckkim/ddok-ddok
- **작업 폴더**: `C:\Users\kibie\dev\ddok-ddok` (Drive 손상 회피용)

표기: ✨ 신규기능 · 🔧 개선 · 🐛 버그수정 · 🔒 보안 · 📝 인프라·문서

---

## 2026-05-07 — v2.3 초기 배포부터 신뢰도 평가까지

### 1. 첫 배포 + 인프라 (`8820f9d` ~ `dbf98cf`)
- 📝 `8820f9d` deploy 폴더 → GitHub `johnckkim/ddok-ddok` (public) → Vercel `ddok-ddok.vercel.app` 첫 배포 (15 files)
- 🔒 `97d29f1` HTTP Basic Auth via Edge Middleware (`SITE_USER`, `SITE_PASS`)
- 📝 `dbf98cf` `.gitignore`에 `.vercel/` 추가

### 2. 프록시 아키텍처 + Drive 손상 1차 (`2ad2b04` ~ `7038ef8`)
- 🐛 `2ad2b04` `@media print` wrapper 누락 복구 → 흰 화면 fix
- 🐛 `5324962` 헤더 action 버튼 (theme/export/settings) 복구
- 🔧 `871ee1e` 프론트엔드 → `/api/*` proxy로 전체 라우팅 (클라이언트 API 키 노출 0)
- 🔧 `7038ef8` 깊이 분석 토글: 이모지 제거 + 텍스트 가운데

### 3. Deepthink 토글 — 다단계 listener 디버깅 (`4447b42` ~ `274648e`)
- 🐛 `4447b42` 빈 대화 history 숨김 + on/off 대비
- 🔧 `74f64c5` deepthink CSS 재적용
- 🐛 `863019e` `@media print` wrapper 3차 복구
- 🔧 `51cec8c`, `221295c` `.on` class 동기화 시도
- 🔧 `8c615b2` rAF → setTimeout
- 🔧 `1d8af9a` document-level delegation
- 🐛 `c90b4b7` 파일 끝 truncate 복구 (`</script></body></html>` 누락)
- 🐛 `274648e` **inline onclick으로 우회 — 근본 원인이 무엇이든 사이드스텝**

### 4. 공공데이터 API 통합 7개 (`41e0bc1` ~ `6e90550`)
- ✨ `41e0bc1` `/api/assembly`, `/api/constitutional`, `/api/court`, `/api/crime-stats`, `/api/datagovkr`, `/api/interpretation`, `/api/moleg`
- 🐛 `f41fe07` interpretation: 미인증 target 안내 메시지 (이후 `c3ec191`에서 모두 해금)
- 🐛 **`7412e82` law.go.kr DRF가 `Referer: https://www.law.go.kr/` 헤더 요구하도록 변경됨 — 모든 lawsearch 호출에 추가**
- 🐛 `6e90550` cdc/crime/moj — 추측 path 대신 Swagger UI 검증 실제 path로 교체

### 5. 입력·UI 안정화 + Drive 4차 손상 (`a5d3a00` ~ `8f6f5e9`)
- 🐛 `a5d3a00` btn-send + textarea inline 핸들러 (listener attach 이슈 우회)
- 🐛 `ca5e354` `@media print` 4번째 복구
- 🔧 `182f7a2` 사용자 버블 우측 정렬, deepthink 이모지·툴팁 제거
- 🔧 `4d29499` 환영 메시지 인라인 HTML (JS 의존 제거)
- 🔧 `bc94e25` 환영 메시지 + 똑똑 로고 클릭 = 새 대화 + in-place streaming
- 🔧 `919ce87` renderMessages 환영 텍스트 동기화
- 🔧 `8de41c1` 27px greeting (1.5x) + 80ms throttle
- 🔧 `0621897` greeting 간격 8px + 큰 헤딩 56px (2x)
- 🔧 `8f6f5e9` **DeepSeek 스타일 입력박스** (textarea 위 + 깊이 분석/전송 하단)

### 6. Claude Opus 4.7 업그레이드 + 답변 품질 (`70d3386` ~ `3d7e5f1`)
- 🔧 `70d3386` 스트리밍 중 plain textContent → 완료 시 markdown
- 🐛 `152c889` `.message` fadeIn 애니메이션 제거 (깜빡임 원인)
- ✨ **`d966f68` Claude Opus 4.6 → 4.7 + max_tokens 4096 → 8192 + 풍부한 system prompt** (출력 구조 명시, GRADE 기준)
- ✨ `618109a` 질문/답변 아래 작은 복사 버튼
- 🐛 **`3d7e5f1` Opus 4.7 deprecated `temperature` 파라미터 제거** + rAF 타이프라이터

### 7. 새 대화·병렬 세션 흐름 (`db537af` ~ `c3c09f5`)
- 🔧 `db537af` 새 대화 시 busy 리셋 + 옛 typewriter 취소
- 🔧 `c9db470` deepthink 텍스트 정중앙 (input out-of-flow + symmetric padding)
- 🔧 `fe6c9ab` deepthink outline 기본 + soft chip-bg ON 상태 (진한 primary 제거)
- 🔧 `29f0d54` favicon (이전 똑 SVG), 빈 대화 필터, 핸들러 중복 제거, Text.appendData
- 🔧 `31105ee` favicon: 똑 → ㄸ
- 🐛 `934a44e` 사이드바에 현재 빈 대화 표시 + orphan 빈 대화 재사용
- 🐛 `25fd356` 타이프라이터 — DOM 재빌드 시 `_typeShown`으로 text node 복원
- 🐛 `1f931ec` favicon URL 인코딩 수정 (`%E3%85%B8` → `%E3%84%B8`, ㅘ → ㄸ)
- 🐛 **`7990a27` 타이프라이터 per-ask closure + 고유 `streamBodyId`** — 두 세션 동시 진행 시 격리
- 🔧 `58ac7bf` favicon SVG path로 ㄸ 직접 그림 (폰트 의존성 제거)
- 🐛 `c3c09f5` 병렬 스트림 — `state.busy` 단일 → `window._busyConvs` Set + askId 취소 제거

### 8. 모든 DRF target 해금 + 결합형 신뢰도 (`c3ec191` ~ `33aaad3`)
- ✨ **`c3ec191` 모든 DRF target 해금** (Referer 헤더로 OC=kibie가 expc·ntsCgmExpc·molitCgmExpc·moelCgmExpc·licbyl·admrul 모두 사용 가능 발견) + 부처별 자동 라우팅
- 🐛 `f40daf3` 타이프라이터 — 돌아왔을 때 현재 target까지 즉시 점프 (재생 X)
- ✨ **`33aaad3` 결합형 신뢰도 (Option C)**: Claude self + 검증 동의 + 교차 동의 + 인용 매칭률 4가지 결합 GRADE 자동 산정

### 9. 후속 fix
- 📝 `c67874a` CHANGELOG.md 추가 (Drive + dev 양쪽)
- 🐛 `6551155` 새 대화 시 깊이 분석 토글 OFF 자동 리셋
- ✨ **`da23ef4` 답변 중단 기능** — `AbortController` per-conv + 진행 중에는 send 버튼이 빨간 ■ stop 버튼으로 변신, 클릭 시 즉시 중단 + "사용자가 중단함" 마킹
- ✨ **`ef0456c` 모바일 반응형 완성** — 햄버거 메뉴(☰) + 사이드바 슬라이드인 오버레이 + 백드롭 + iOS zoom 방지(font-size 16px) + 환영 메시지·답변 카드·input padding 축소
- 🐛 `8dbff3b` `sidebar-backdrop` 기본 `display:none` 미디어 쿼리 밖으로 — PC grid 레이아웃 붕괴 fix
- 🐛 **`805c5a7` 옛 btn-theme/settings/cancel/save handler 삭제** — element 미존재 상태에서 `null.addEventListener` 에러 던지며 그 이후 JS(window.copyMessage, newChat, toggleSidebar 등) 등록 일부 누락 가능성 차단
- 🐛 **모바일 메인창 백지 fix** — 모바일에서 `.sidebar`가 `position:fixed`로 빠지면 `.chat-area`가 grid 자동 배치 규칙에 따라 0px 컬럼(1열)에 들어가 메인 콘텐츠가 사라지던 버그. `.app { grid-template-columns: 1fr }` + `.chat-area { grid-column: 1/2; grid-row: 2/3 }`로 명시 고정 (2026-05-07)
- 🐛 **모바일 입력창 잘림 fix** — `.app { height: 100vh }`가 모바일 주소창 영역까지 포함해 화면 밖으로 밀렸음. `100dvh`로 보정 + `.input-area`에 `env(safe-area-inset-bottom)` 패딩 추가 (2026-05-07)
- ✨ **파일 첨부 기능** (2026-05-07)
  - input-actions 좌측에 ＋ 버튼 추가 (deepthink 토글 옆)
  - 드래그 앤 드롭 지원 — 화면 어디든 파일 끌면 풀스크린 dashed overlay 표시 + 놓으면 첨부
  - 클립보드 붙여넣기 (Ctrl+V) 로 이미지 첨부 가능
  - 지원 형식: 이미지(jpg/png/gif/webp ≤5MB) · PDF(≤10MB) · 텍스트(txt/md/csv/json/code 등 ≤1MB)
  - 미지원: hwp/docx/xlsx — 안내 alert + PDF 변환 권고
  - textarea 위에 첨부 칩 표시 (아이콘 + 파일명 + 크기 + × 삭제)
  - Claude API multipart content 변환 — 이미지·PDF는 base64 block, 텍스트는 question에 인라인
  - localStorage quota 보호 — 저장 시 base64 data 필드 strip (id/name/size/kind/mediaType만 유지)
  - 사용자 메시지 카드에 첨부 미리보기 칩 표시 (history 재방문 시도 그대로)
- 🎨 textarea placeholder 문구 제거 (`법률 질문을 입력하세요. 예) ...` → 빈 값) (2026-05-07)
- ✨ **모바일 첨부 분기 — 카메라/갤러리/파일** (2026-05-07)
  - 모바일(≤768px)에서 ＋ 버튼 누르면 하단 액션 시트 슬라이드업
  - 📷 카메라 (`capture="environment"` 후면 카메라 직접) · 🖼 갤러리 (`accept="image/*"`) · 📄 파일 (전체)
  - 백드롭 클릭 또는 취소 버튼으로 닫힘, safe-area-inset-bottom 보정
  - PC는 분기 없이 기존대로 바로 전체 파일 다이얼로그

---

## 환경변수 (Vercel — production + development)

| 키 | 용도 | 비밀 정도 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude Opus 4.7 | 🔒 매우 비밀 |
| `DEEPSEEK_API_KEY` | DeepSeek 분류·검증·reasoner | 🔒 |
| `GROK_API_KEY` | Grok 교차검증 | 🔒 |
| `DATA_GO_KR_KEY` | 헌재·법무부·범죄통계 | 🔒 |
| `ASSEMBLY_API_KEY` | 열린국회정보 | 🔒 |
| `LAW_GO_KR_OC` = `kibie` | 사용자 ID (DRF) | 🟢 공개 가능 |
| `SITE_USER`, `SITE_PASS` | Basic Auth | 🔒 |

## API 엔드포인트 (16개)

| 엔드포인트 | 용도 | 상태 |
|---|---|---|
| `/api/chat` | Claude Opus 4.7 SSE | ✅ |
| `/api/classify` | DeepSeek 질문 분류 | ✅ |
| `/api/verify` | DeepSeek 답변 검증 | ✅ |
| `/api/cross` | Grok 교차검증 | ✅ |
| `/api/reasoner` | DeepSeek 깊이 분석 | ✅ |
| `/api/lawsearch` | 법령·판례 (모든 DRF target) | ✅ |
| `/api/interpretation` | 법령해석례 + 부처별 해석례 | ✅ |
| `/api/constitutional`, `/api/cdc` | 헌재 판례정보 (data.go.kr 15141085) | ✅ |
| `/api/crime-stats`, `/api/crime` | 범죄통계 (data.go.kr 15140047) | ✅ |
| `/api/moj` | 법무부 인기검색어 (data.go.kr 15126815) | ⚠️ 백엔드 일시 오류 |
| `/api/assembly` | 22대 국회 의안 (open.assembly.go.kr) | ✅ |
| `/api/datagovkr` | 범용 data.go.kr proxy | ✅ |
| `/api/court` | 대법원 사법정보공유포털 | 🚫 변호사 자격 인증 필요 |
| `/api/moleg` | 법제처 입법예고 | 🚫 공식 OpenAPI 미공개 |

## DRF target 인증 결과 (OC=kibie + Referer 헤더)

| target | 분야 | 작동 |
|---|---|---|
| `law` | 법령 | ✅ |
| `prec` | 판례 | ✅ |
| `detc` | 헌재 결정문 | ✅ |
| `expc` | 법령해석례 (통합) | ✅ |
| `ntsCgmExpc` | 국세청 해석례 | ✅ |
| `molitCgmExpc` | 국토교통부 해석례 | ✅ |
| `moelCgmExpc` | 고용노동부 해석례 | ✅ |
| `licbyl` | 행정해석 (별표·서식) | ✅ |
| `admrul` | 행정규칙 | ✅ |
| `ordin` | 자치법규 | ✅ |
| `trty` | 조약 | ✅ |

## 신뢰도 산정 공식 (Option C)

```
기본 점수 = Claude self-grade (A=3, B=2, C=1)
+ DeepSeek 검증 동의: +0.3, 반대: -0.5, 중립: 0
+ Grok 교차 동의: +0.3, 반대: -0.5, 중립: 0
+ 인용 사건번호 매칭률 ≥80%: +0.5
                     ≥50%: ±0
                     <50%: -0.5

최종: ≥3.0 → A, ≥2.0 → B, 그 외 → C
```

배지 hover 툴팁에 4가지 산정 근거 표시.

## 주요 발견 (Lessons Learned)

1. **Drive 폴더에서 작업 금지** — Google Drive sync가 작업 중인 파일을 무작위로 truncate·revert. 본 세션 중 4번 발생. 해결: 작업 폴더를 Drive 밖(`C:\Users\kibie\dev\ddok-ddok`)으로 이전.
2. **www.law.go.kr DRF Referer 필수** (2026-05~) — `Referer: https://www.law.go.kr/` 없으면 "필수 입력값" 에러. 처음엔 OC 권한 부족으로 오인.
3. **OC=kibie 인증 범위는 모든 target** — Referer 헤더 추가 시 expc·ntsCgmExpc 등도 작동. 별도 등록 불필요.
4. **Opus 4.7 deprecated parameters** — `temperature` 보내면 400 에러. 향후 다른 deprecated 가능성 모니터링 필요.
5. **JS event listener attach 이슈** — DOM 재빌드 환경에서 addEventListener가 누락되는 알 수 없는 케이스 발견. 해결: inline onclick/onkeydown으로 우회.
6. **타이프라이터 격리** — 두 세션 동시 streaming 시 window 전역 state는 충돌. closure-scoped 상태 + 고유 stream body ID 필요.

---

> 앞으로의 변경사항도 이 파일에 누적 기록됩니다.
> 작성 위치: `C:\Users\kibie\내 드라이브\Law\deploy\CHANGELOG.md` (편의용) + `C:\Users\kibie\dev\ddok-ddok\CHANGELOG.md` (git 영구 기록).
