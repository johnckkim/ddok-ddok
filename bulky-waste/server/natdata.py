"""전국 통계 갱신: 공공데이터포털 「전국대형폐기물수거수수료정보표준데이터」(publicDataPk=15114146).
다운로드 버튼이 JS라서 HANDOFF 4-2의 두 단계 호출을 그대로 한다 → build_nat.summarize()로 요약 TSV."""
import json, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

from engine.build_nat import summarize
from . import store

PK = '15114146'
BASE = 'https://www.data.go.kr/download'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; bulky-fee-app)', 'Referer': f'https://www.data.go.kr/data/{PK}/standard.do'}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_rows(per_page=10000):
    meta = _get(f'{BASE}/columList.json?' + urllib.parse.urlencode({'pk': PK, 'ext': 'CSV'}))
    tv = meta.get('tableVO') or {}
    cols = tv.get('colNmList') or meta.get('colNmList') or []
    if isinstance(cols, str):
        cols = [c for c in cols.split(',') if c]
    table = tv.get('svcTableNm') or meta.get('svcTableNm')
    total = int(meta.get('totalCount') or tv.get('totalCount') or 0)
    if not cols or not table or not total:
        raise RuntimeError('목록 정보(colNmList·svcTableNm·totalCount)를 받지 못했습니다')
    rows, page = [], 1
    while len(rows) < total and page <= 20:
        params = [('publicDataPk', PK)] + [('colNmList', c) for c in cols] + [
            ('totalCount', total), ('svcTableNm', table), ('perPage', per_page), ('page', page)]
        data = _get(f'{BASE}/standard.json?' + urllib.parse.urlencode(params), timeout=40)
        part = data.get('rows') if isinstance(data, dict) else data
        if part is None and isinstance(data, dict):
            part = data.get('data') or []
        if not part:
            break
        rows += part
        page += 1
    return rows, total


_ROWS = {'at': 0, 'rows': None}


def cached_rows(max_age=3600):
    """같은 인스턴스에서 1시간 안에 다시 쓰면 원본을 다시 받지 않는다."""
    if _ROWS['rows'] is None or time.time() - _ROWS['at'] > max_age:
        rows, _ = fetch_rows()
        _ROWS.update(at=time.time(), rows=rows)
    return _ROWS['rows']


def apply_rows(rows, user, source):
    lines = summarize(rows)
    if len(lines) < 50:
        raise RuntimeError(f'요약 품목이 {len(lines)}개뿐입니다(50개 미만). 원본을 확인해 주세요.')
    return apply_tsv('\n'.join(lines) + '\n', user, source, n_rows=len(rows))


def apply_tsv(tsv, user, source, n_rows=None):
    good = [l for l in tsv.splitlines() if len(l.split('\t')) >= 5 and l.split('\t')[1].isdigit()]
    if len(good) < 50:
        raise RuntimeError(f'유효한 품목 줄이 {len(good)}개뿐입니다(50개 미만).')
    before = {'items': len([l for l in (store.get_setting('nat_tsv') or '').splitlines() if l.strip()]),
              'updated': store.get_setting('nat_updated')}
    today = datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')
    store.set_setting('nat_tsv', '\n'.join(good) + '\n')
    store.set_setting('nat_updated', today)
    store.set_setting('nat_source', source + (f' · 원본 {n_rows:,}행' if n_rows else '') + f' · {len(good)}품목')
    store.bump_version()
    store.log(user, '전국 통계 갱신', source, before, {'items': len(good), 'updated': today})
    return {'items': len(good), 'updated': today}


def refresh(user):
    rows, total = fetch_rows()
    if not rows:
        raise RuntimeError('원본 행을 받지 못했습니다')
    return dict(apply_rows(rows, user, '공공데이터포털 15114146'), total=total)
