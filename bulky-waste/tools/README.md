# 수수료표 수집 도구 (운영자용, 배포 제외)
공공데이터포털에 없는 지자체의 대형폐기물 수수료표를 공식 출처에서 모아 `data/collected/<시도>_<시군구>.csv/.json` 으로 저장한다.
반영은 배포 후 `/api/cron/import?key=CRON_SECRET&mode=collected&dry=0` (공공 도메인 출처·유료 20행 이상만 반영).

- `law.py` — 국가법령정보센터 **현행 자치법규** 검색 → 폐기물 조례 → 별표 파일(HWP/HWPX/PDF) 내려받아 수수료 표 판독. `python3 law.py 정읍시`
- `runlaw.py` — 여러 지자체 일괄 실행
- `hwp.py` — HWP5 표 판독(셀 행·열 위치 그대로)
- `tbl.py` — HTML 표 추출, `save.py` — CSV·출처 JSON 저장
필요: `pip install playwright pdfplumber olefile` + Chromium. 네트워크에서 law.go.kr·각 지자체 도메인 허용.
