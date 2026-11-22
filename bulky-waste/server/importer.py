"""지자체 수수료표 일괄 가져오기: 공공데이터포털 「전국대형폐기물수거수수료정보표준데이터」(15114146)의
지자체별 행(품목·규격·수수료)을 그 지자체의 조례 가격표로 넣는다. 각 지자체가 등록한 기준일자를 함께 남긴다.
- 대상: 시도 전체(예: 서울·경기) 또는 '시도 시군구' 목록
- 이미 운영자가 직접 올린 조례(source='manual')는 덮어쓰지 않는다(force 일 때만)
- 무료 품목은 확정표에 배출 방법 '무상수거'로 넣는다
"""
import json, re, time
from collections import defaultdict

from . import store

SIDO = {  # 표기 변형 → (짧은 이름, 정식 이름, 로마자)
    '서울': ('서울', '서울특별시', 'seoul'), '부산': ('부산', '부산광역시', 'busan'), '대구': ('대구', '대구광역시', 'daegu'),
    '인천': ('인천', '인천광역시', 'incheon'), '광주광역': ('광주', '광주광역시', 'gwangju'), '대전': ('대전', '대전광역시', 'daejeon'),
    '울산': ('울산', '울산광역시', 'ulsan'), '세종': ('세종', '세종특별자치시', 'sejong'), '경기': ('경기', '경기도', 'gyeonggi'),
    '강원': ('강원', '강원특별자치도', 'gangwon'), '충청북': ('충북', '충청북도', 'chungbuk'), '충북': ('충북', '충청북도', 'chungbuk'),
    '충청남': ('충남', '충청남도', 'chungnam'), '충남': ('충남', '충청남도', 'chungnam'), '전라북': ('전북', '전북특별자치도', 'jeonbuk'),
    '전북': ('전북', '전북특별자치도', 'jeonbuk'), '전라남': ('전남', '전라남도', 'jeonnam'), '전남': ('전남', '전라남도', 'jeonnam'),
    '경상북': ('경북', '경상북도', 'gyeongbuk'), '경북': ('경북', '경상북도', 'gyeongbuk'), '경상남': ('경남', '경상남도', 'gyeongnam'),
    '경남': ('경남', '경상남도', 'gyeongnam'), '제주': ('제주', '제주특별자치도', 'jeju'),
}


def sido_of(s):
    s = str(s or '').strip()
    if s.startswith('전남광주'):
        return SIDO['전남']
    if s.startswith('광주') and ('광역' in s or s == '광주'):
        return SIDO['광주광역']
    for k in sorted(SIDO, key=len, reverse=True):
        if s.startswith(k):
            return SIDO[k]
    return None


# ---------------------------------------------------------------- 로마자(주소용 코드)
_I = ['g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's', 'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h']
_V = ['a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o', 'wa', 'wae', 'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu', 'eu', 'ui', 'i']
_F = ['', 'k', 'k', 'k', 'n', 'n', 'n', 't', 'l', 'k', 'm', 'l', 'l', 'l', 'p', 'l', 'm', 'p', 'p', 't', 't', 'ng', 't', 't', 'k', 't', 'p', 't']


def roman(text):
    out = []
    for ch in str(text):
        c = ord(ch)
        if 0xAC00 <= c <= 0xD7A3:
            c -= 0xAC00
            out.append(_I[c // 588] + _V[(c % 588) // 28] + _F[c % 28])
        elif ch.isascii() and ch.isalnum():
            out.append(ch.lower())
    return ''.join(out)


def muni_code(sido_roman, sgg):
    base = re.sub(r'(si|gun|gu)$', '', roman(sgg)) or roman(sgg)
    return f'{sido_roman}-{base}'


# ---------------------------------------------------------------- 대상 해석
def parse_targets(text):
    """'서울 전체, 경기 전체, 부산 사하구, 경북 경산시' → [(시도짧은이름, 시군구 or None)]"""
    out = []
    for part in re.split(r'[,\n;]+', str(text or '')):
        p = part.strip()
        if not p:
            continue
        toks = p.split()
        sd = sido_of(toks[0])
        if not sd:
            continue
        rest = ' '.join(toks[1:]).strip()
        out.append((sd[0], None if rest in ('', '전체', '전부', '*') else rest))
    return out


def _sgg_base(s):
    """'수원시 장안구' → '수원시', '창원시 의창구' → '창원시'"""
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    parts = s.split(' ')
    if len(parts) >= 2 and parts[0].endswith('시') and parts[1].endswith('구'):
        return parts[0]
    return parts[0] if parts else ''


def _pick(row, *keys):
    for k in keys:
        if row.get(k) not in (None, ''):
            return str(row[k]).strip()
    return ''


def _spec_key(rows):
    keys = set()
    for r in rows[:200]:
        keys |= set(r)
    for cand in ('LAR_WAS_STNDRD', 'LAR_WAS_STD', 'STNDRD', 'LAR_WAS_SPCFC', 'SPCFC', 'LAR_WAS_SIZE', 'SIZE', 'LAR_WAS_STND'):
        for k in keys:
            if k.upper() == cand or cand in k.upper():
                return k
    return None


def _date_key(rows):
    keys = set()
    for r in rows[:200]:
        keys |= set(r)
    for k in sorted(keys):
        if 'STDR_DE' in k.upper() or k.upper() in ('CRTR_YMD', 'REFERENCE_DATE', 'STD_DT', 'BASE_DE'):
            return k
    return None


def group(rows):
    """행 → {(시도짧은, 시군구): {'inst':{기관: [행]}}}"""
    out = defaultdict(lambda: defaultdict(list))
    for r in rows:
        sd = sido_of(r.get('CTPV_NM'))
        if not sd:
            continue
        raw = str(r.get('SGG_NM') or '').strip()
        if raw in ('', '없음', '-'):
            inst = str(r.get('INSTT_NM') or '').replace(sd[1], '').strip()     # '부산광역시 사하구' → '사하구'
            raw = inst or (sd[1] if sd[0] == '세종' else '')
        sgg = _sgg_base(raw)
        if not sgg:
            continue
        out[(sd[0], sgg)][_pick(r, 'INSTT_NM') or sgg].append(r)
    return out


def build_table(inst_rows, spec_key, date_key):
    """한 기관의 행 → (조례 행 목록, 무상 품목 목록, 기준일자)"""
    seen, rows, free = set(), [], []
    dates = []
    for r in inst_rows:
        item = re.sub(r'\s+', ' ', _pick(r, 'LAR_WAS_NM')).strip()
        if not item:
            continue
        spec = re.sub(r'\s+', ' ', str(r.get(spec_key) or '')).strip() if spec_key else ''
        if date_key and r.get(date_key):
            dates.append(str(r[date_key])[:10])
        if r.get('PAID_FREE_YN') == '무료':
            free.append((item, spec or '모든규격'))
            continue
        fee = store.parse_fee(r.get('FEE'))
        if not fee or fee <= 0 or fee > 300000:
            continue
        key = (item, spec, fee)
        if key in seen:
            continue
        seen.add(key)
        rows.append({'item': item, 'spec': spec or '모든규격', 'fee': fee, 'disp_item': '', 'disp_spec': ''})
    return rows, free, (max(dates) if dates else '')


def run(rows, targets, user, force=False, dry=False):
    spec_key, date_key = _spec_key(rows), _date_key(rows)
    g = group(rows)
    want_all = {sd for sd, sgg in targets if sgg is None}
    want_one = {(sd, _sgg_base(sgg)) for sd, sgg in targets if sgg}
    report = {'spec_column': spec_key, 'date_column': date_key, 'imported': [], 'skipped': [], 'missing': []}
    found = set()
    from .catalog import classify
    now = time.time()
    for (sd, sgg), insts in sorted(g.items()):
        if sd not in want_all and (sd, sgg) not in want_one:
            continue
        found.add((sd, sgg))
        inst, irows = max(insts.items(), key=lambda kv: len(kv[1]))
        table, free, date = build_table(irows, spec_key, date_key)
        if len(table) < 5:
            report['skipped'].append({'name': f'{sd} {sgg}', 'reason': f'유료 품목 {len(table)}행뿐'})
            continue
        sido = sido_of(sd)
        inst_clean = re.sub(r'\s+', ' ', inst).strip()
        name = inst_clean if inst_clean.endswith(sgg) and len(inst_clean) > len(sgg) else f'{sido[1]} {sgg}'
        exist = store.q('SELECT code, name FROM municipality WHERE name=? OR name=?', (name, f'{sido[1]} {sgg}'), one=True)
        code = exist['code'] if exist else muni_code(sido[2], sgg)
        src = store.get_setting(f'source:{code}', 'manual' if exist else '')
        if exist and src == 'manual' and not force:
            report['skipped'].append({'name': name, 'reason': '운영자가 직접 올린 조례 유지', 'code': code})
            continue
        item = {'name': name, 'code': code, 'rows': len(table), 'free': len(free), 'date': date, 'institution': inst}
        report['imported'].append(item)
        if dry:
            continue
        if exist and exist['name'] != name:
            store.x('UPDATE municipality SET name=? WHERE code=?', (name, code))
        if not exist:
            n = 2
            base = code
            while store.q('SELECT 1 FROM municipality WHERE code=?', (code,), one=True):
                code = f'{base}{n}'
                n += 1
            item['code'] = code
            store.x('INSERT INTO municipality(code,name,created_at) VALUES(?,?,?)', (code, name, now))
            store.set_setting(f'policy:{code}', 'hold')
        store.save_ordinance(code, table)
        store.set_setting(f'source:{code}', 'public')
        store.set_setting(f'basis:{code}', json.dumps({'source': '공공데이터포털 15114146', 'date': date, 'institution': inst,
                                                       'imported': time.strftime('%Y-%m-%d')}, ensure_ascii=False))
        store.x("DELETE FROM confirmed WHERE muni=? AND updated_by='공공데이터 무상'", (code,))
        if free:
            store.xmany('INSERT INTO confirmed(muni,item,spec,fee,method,category,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)',
                        [(code, it, sp, None, '무상수거', classify(it), now, '공공데이터 무상') for it, sp in dict.fromkeys(free)])
    for sd, sgg in want_one:
        if (sd, sgg) not in found:
            report['missing'].append(f'{sd} {sgg}')
    for sd in want_all:
        report.setdefault('regions', {})[sd] = sorted(s for (d, s) in found if d == sd)
    if not dry and report['imported']:
        store.bump_version()
        store.log(user, '공공데이터 지자체 가져오기', f"{len(report['imported'])}곳", None,
                  {'imported': [i['name'] for i in report['imported']], 'missing': report['missing']})
    return report


def columns_preview(rows, n=3):
    keys = []
    for r in rows[:50]:
        for k in r:
            if k not in keys:
                keys.append(k)
    return {'columns': keys, 'sample': rows[:n], 'total': len(rows)}
