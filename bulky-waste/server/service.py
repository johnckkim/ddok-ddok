"""엔진을 감싸는 서비스 계층.
- 금액은 전부 engine.price()/client_rows()가 정한다. 여기서는 (1) 지자체별 입력 준비 (2) 고객용 표기 정리
  (3) 확인 질문 흐름 (4) 검토 대기열·접수번호를 다룬다.
- 고객에게 나가는 dict에는 등급·경로·통계 같은 근거를 절대 넣지 않는다(공개 함수 quote/confirm/ticket 반환값).
"""
import json, os, re, secrets, tempfile, threading, time

from engine import engine as E
from . import ai, catalog as C
from . import shopping, store
from .tokens import sign, unsign

BASE_SYN = list(E.SYN)
_ORIG_HEAD = E.local_head


def _local_head(q, local):
    """엔진 끝말 찾기에 '다른 물건' 막기(전기장판→장판, 고양이화장실→이동식 화장실, 키보드→보드)."""
    k = E.norm(q)
    for head, pres in C.HEAD_BLOCK.items():
        if k.endswith(head) and k != head and any(k[:-len(head)].endswith(p) for p in pres):
            return []
    for head, pres in C.HEAD_ONLY.items():
        if k.endswith(head) and k != head and not any(k[:-len(head)].endswith(p) for p in pres):
            return []
    return _ORIG_HEAD(q, local)


def _local_analog(q, local):
    """엔진 유사품목 찾기와 같되, 키워드가 맨 앞에 있고 나머지가 따로 아는 품목이면 쓰지 않는다
    ('드럼세탁기'는 '드럼'(악기)이 아니라 세탁기)."""
    k = E.norm(q); hits = []; first = None
    tried = []
    for qk, lk in E.ANALOG:
        nk = E.norm(qk)
        if first and len(nk) < len(E.norm(first)):
            break
        if nk in k:
            tail = k[k.rfind(nk) + len(nk):]
            if tail and tail not in ('기', '기계', '세트', '어', '용'):      # 키워드가 끝(합성어의 머리)에 있어야 한다: 드럼통≠드럼
                continue
            if any(nk in t and nk != t for t in tried):                        # 더 긴 키워드가 맞았는데 행이 없으면 짧은 것으로 내려가지 않음
                continue
            tried.append(nk)
            key = E.norm(lk)
            ok_row = lambda row: not C.CATCH_ALL.search(row['name'])
            hit = [row for row in local if key in row['tok'] and ok_row(row)]
            if not hit and len(key) >= 2:                                     # 끝말 일치만(컴퓨터 ≠ 컴퓨터책상, 다리미 ≠ 다리미판)
                hit = [row for row in local if ok_row(row) and any(t.endswith(key) for t in row['tok'])]
            if hit:
                first = first or qk
                hits += [h for h in hit if h not in hits]
    return (first and hits and first), hits


E.local_head = _local_head
E.local_analog = _local_analog
# 엔진 유사품목 사전 보강(엔진 파일은 건드리지 않고 여기서 더한다)
# 검수에서 엉뚱하다고 본 유사품목 짝은 뺀다(EQUIV 순서 규칙으로 옮겼거나 확인 후 안내가 낫다)
for _p in [('커튼', '이불'), ('벤치', '운동기구'), ('개집', '고무통'), ('캣휠', '고무통'), ('게시판', '입간판'), ('드럼', '피아노'), ('화환', '액자'), ('목발', '스키'),
           ('골프채', '스키'), ('발마사지기', '운동기구'), ('안전문', '상'), ('나무판자', '상'), ('야전침대', '상'), ('솜', '단열재'),
           ('맥주', '전기밥솥'), ('에어매트', '고무통'), ('현악기', '기타'), ('쓰레기통', '플라스틱류'), ('복합기', '프린터'),
           ('화이트보드', '간판'), ('칠판', '간판'), ('캣타워', '신발장'), ('사물함', '신발장'), ('쿠션', '인형류'),
           ('제습기', '가습기'), ('후드', '다리미'), ('환풍기', '다리미')]:
    while _p in E.ANALOG:
        E.ANALOG.remove(_p)
for _p in [('화분', '항아리'), ('맥주제조기', '전기밥솥'), ('화분', '고무통'), ('킥보드', '자전거'), ('씽씽카', '자전거'), ('전기장판', '전기매트'), ('전기장판', '온수매트'), ('전기장판', '옥매트'), ('전기요', '전기매트'),
           ('러닝머신', '운동기구'), ('런닝머신', '운동기구'), ('워킹머신', '운동기구')]:
    if _p not in E.ANALOG:
        E.ANALOG.append(_p)
E.ANALOG.sort(key=lambda x: -len(x[0]))
_EXCL = re.compile(r'\([^()]*(별도|제외|미포함|불포함)[^()]*\)')


def _tok(name):
    """품목 토큰. '소파(쿠션 별도)'처럼 빠지는 물건은 검색어로 쓰지 않는다."""
    return E.tokens(re.sub(r'[+ㆍ&]', ',', _EXCL.sub(' ', str(name or ''))))   # '운동기구(런닝머신+싸이클)' → 런닝머신·싸이클
BASE_AMBIG = tuple(E.AMBIG)
BASE_VAGUE = set(E.VAGUE)
BRAND_SYN = {'스탠바이미', '바디프렌드', '워시타워', '에어드레서', '룸바'}   # SYN 중 상품명·브랜드 → 일반 명칭인 것
MAX_ASKS = 3
NAME_MAX = 40
_BUILD = threading.RLock()
_CACHE = {}

CARD_TTL = 6 * 3600
PENDING_MSG = '확인 후 안내드리겠습니다.'


# ================================================================ 지자체 문맥(조례·확정표·전국 통계·k)
class Ctx:
    pass


def _raw_norm(s):
    """SYN을 적용하지 않은 정규화(사전 등록용)."""
    s = str(s or '').lower()
    s = re.sub(r'\(.*?\)|\[.*?\]', '', s)
    return re.sub(r'[\s·,./\-_~:;"\'※]', '', s)


def _apply_dictionary():
    """운영자가 승인한 표현 사전을 엔진 전역 사전에 얹는다(엔진 로직은 그대로, 사전 항목만 추가)."""
    syn, amb, vag, hints = [], [], set(), []
    for r in store.q('SELECT kind, expr, target FROM synonym ORDER BY id'):
        e = _raw_norm(r['expr'])
        if not e:
            continue
        if r['kind'] == 'SYN' and r['target']:
            syn.append((e, _raw_norm(r['target'])))
        elif r['kind'] == 'AMBIG':
            amb.append(e)
        elif r['kind'] == 'VAGUE':
            vag.add(e)
        elif r['kind'] == 'HINT' and r['target']:
            hints.append((e, [t.strip() for t in re.split(r'[,\s]+', r['target']) if t.strip()]))
    E.SYN[:] = BASE_SYN + [(a, b) for a, b in C.APP_SYN] + syn
    E.AMBIG = BASE_AMBIG + tuple(amb)
    E.VAGUE = BASE_VAGUE | vag
    return {a for a, _ in syn}, hints


def ctx(muni):
    """지자체 문맥. 데이터 버전이 바뀌면 다시 만든다."""
    ver = store.get_setting('data_version', '0')
    key = (muni, ver)
    c = _CACHE.get(key)
    if c:
        return c
    with _BUILD:
        c = _CACHE.get(key)
        if c:
            return c
        m = store.q('SELECT * FROM municipality WHERE code=?', (muni,), one=True)
        if not m:
            raise KeyError(muni)
        brand_extra, hints = _apply_dictionary()
        c = Ctx()
        c.muni, c.name = muni, m['name']
        c.local = [{'name': r['item'], 'spec': r['spec'], 'fee': r['fee'], 'tok': _tok(r['item']),
                    'disp_item': r['disp_item'], 'disp_spec': r['disp_spec']}
                   for r in store.q('SELECT * FROM ordinance WHERE muni=? ORDER BY ord', (muni,))]
        crow = store.q('SELECT * FROM confirmed WHERE muni=? ORDER BY id', (muni,))
        c.conf = [{'name': r['item'], 'spec': r['spec'] or '', 'fee': r['fee'], 'tok': _tok(r['item'])}
                  for r in crow if r['fee'] and r['fee'] > 0 and not r['method']]
        c.methods = [{'name': r['item'], 'spec': r['spec'] or '모든규격', 'method': r['method'], 'tok': E.tokens(r['item'])}
                     for r in crow if r['method']]
        c.cats = {E.norm(r['item']): r['category'] for r in crow if r['category']}
        with tempfile.NamedTemporaryFile('w', suffix='.tsv', delete=False, encoding='utf-8') as f:
            f.write(store.get_setting('nat_tsv', ''))
            tp = f.name
        try:
            c.nat = E.load_nat(tp)
        finally:
            os.unlink(tp)
        c.grid = sorted({r['fee'] for r in c.local}) or [1000]
        c.k, c.kn, c.mad = E.calibrate(c.local, c.nat) if c.local else (1.0, 0, None)
        c.policy = store.get_setting(f'policy:{muni}', 'hold')
        c.brand = BRAND_SYN | brand_extra
        c.hints = hints
        c.spec_disp = {}
        for r in c.local:
            if r['disp_spec']:
                c.spec_disp.setdefault((r['name'], r['spec']), r['disp_spec'])
        for k in [k for k in _CACHE if k[1] != ver]:
            _CACHE.pop(k, None)
        while len(_CACHE) >= 12:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = c
        return c


def municipalities():
    return [{'code': r['code'], 'name': r['name']} for r in store.q('SELECT code, name FROM municipality ORDER BY created_at')]


# ================================================================ 엔진 호출
def engine_price(c, q, spec=None):
    with _BUILD:   # 엔진 전역 사전(SYN 등)이 바뀌는 중에 읽지 않도록
        return E.price(q, spec, c.local, c.nat, c.k, c.grid, None, c.conf)


def clean_name(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s[:NAME_MAX]


def _method_hit(c, q):
    k = E.norm(q)
    return [m for m in c.methods if k in m['tok']]


def _multi_confirmed(c, q, r):
    """확정표 일치(L1)인데 서로 다른 품목 여러 개에 걸리면(예: '침대' → 2층 침대, 침대 범퍼) 무엇인지 물어야 한다."""
    if not r['등급'].startswith('L1 확정'):
        return None
    k = E.norm(q)
    hit = [x for x in c.conf if k in x['tok']]
    names = list(dict.fromkeys(re.sub(r'\(.*?\)', '', x['name']).strip() for x in hit))
    if len(names) > 1 and k not in {E.norm(n) for n in names}:
        return names
    return None


def _is_ambiguous(c, q):
    k = E.norm(q)
    if k in C.AMBIG_NOUNS:
        return True
    return any(e == k for e, _ in c.hints)


# ================================================================ 고객용 행 만들기
_LADDER = re.compile(r'^(.*?)([\d][\d,\.]*)\s*([^\d\s~]*)\s*(이상|미만)$')


def _ladder(specs):
    """'70cm 미만, 70cm 이상, 110cm 이상' → '70cm 미만, 70cm 이상~110cm 미만, 110cm 이상' (3단 이상 범위 표기)"""
    if len(specs) < 3:
        return specs
    ps = [_LADDER.match(s) for s in specs]
    if not all(ps):
        return specs
    pre = {m.group(1).strip() for m in ps}
    unit = {m.group(3) for m in ps}
    if len(pre) != 1 or len(unit) != 1:
        return specs
    vals = [(float(m.group(2).replace(',', '')), m.group(4), m.group(2)) for m in ps]
    if [v[1] for v in vals].count('미만') != 1 or vals[0][1] != '미만':
        return specs
    ups = [v for v in vals[1:]]
    if [v[0] for v in ups] != sorted(v[0] for v in ups) or ups[0][0] != vals[0][0]:
        return specs
    p, u = pre.pop(), unit.pop()
    p = (p + ' ') if p else ''
    out = [specs[0]]
    for i, v in enumerate(ups):
        if i + 1 < len(ups):
            out.append(f'{p}{v[2]}{u} 이상~{ups[i + 1][2]}{u} 미만')
        else:
            out.append(f'{p}{v[2]}{u} 이상')
    return out


def _fee_text(fee):
    return f'{fee:,}원'


def _rows_for(c, q, r, label):
    """엔진 결과 1건 → 고객 행 [{item, spec, fee, method, note}], review(bool)."""
    rows, review, _ = E.client_rows([r], c.local)
    out = []
    note = rows[0][3] if rows else ''
    if r['등급'].startswith('L0') and not r.get('확정') and r['규격'] in ('', '모든규격'):
        ex = E.local_exact(q, c.local)
        k = E.norm(q)
        same = [x for x in ex if E.norm(x['name']) == k]
        ex = same or ex
        clean = lambda n: re.sub(r'\s*\(\d+\)\s*', ' ', n).strip()      # 원문 일련번호 '쇼파(1)' 제거
        names = list(dict.fromkeys(clean(x['name']) for x in ex))
        seen = set()
        for x in sorted(ex, key=lambda x: x['fee']):
            disp_spec = x['disp_spec'] or C.tidy_spec(x['spec'])
            item = label if len(names) == 1 else (x['disp_item'] or re.sub(r'\s+', ' ', clean(x['name'])))
            if (item, disp_spec, x['fee']) in seen:
                continue
            seen.add((item, disp_spec, x['fee']))
            out.append({'item': item, 'spec': disp_spec, 'fee': x['fee'], 'note': note, 'fixed': bool(x['disp_spec']), 'src': x['name']})
    else:
        disp = {}
        for x in E.local_exact(q, c.local):
            if x['disp_spec']:
                disp.setdefault(x['spec'], x['disp_spec'])
        for _, sp, fe, nt in rows:
            spec = disp.get(sp) or C.tidy_spec(sp)
            out.append({'item': label, 'spec': spec, 'fee': int(fe.replace(',', '')), 'note': nt, 'fixed': sp in disp})
    # 같은 품목 3단 이상은 범위 표기(조례 원문 표시규격이 따로 있으면 그것이 우선)
    for item in dict.fromkeys(o['item'] for o in out):
        grp = [o for o in out if o['item'] == item]
        if len(grp) >= 3 and not any(g['fixed'] for g in grp):
            for g, sp in zip(grp, _ladder([g['spec'] for g in grp])):
                g['spec'] = sp
    for o in out:
        o.pop('fixed', None)
    return out, bool(review)


def _base(name):
    return re.sub(r'\s+', ' ', re.sub(r'\(.*?\)', '', name or '')).strip()


def _with_siblings(c, q, rows, label):
    """확정표에서 괄호 속 이름(예: '유아용 쿠션(범퍼형·침대 범퍼)')으로 한 규격 줄만 걸리면
    같은 본 품목('유아용 쿠션')의 다른 규격 줄도 함께 보여 준다(크기는 고객이 고른다)."""
    k = E.norm(q)
    hit = [x for x in c.conf if k in x['tok']]
    bases = {_base(x['name']) for x in hit}
    if len(bases) != 1:
        return rows
    base = bases.pop()
    sib = [x for x in c.conf if _base(x['name']) == base]
    if len(sib) <= len(rows) or not base:
        return rows
    note = rows[0].get('note', '') if rows else ''
    out, seen = [], set()
    for x in sorted(sib, key=lambda x: x['fee']):
        spec = C.tidy_spec(x['spec'] or '모든규격')
        if (spec, x['fee']) in seen:
            continue
        seen.add((spec, x['fee']))
        out.append({'item': label, 'spec': spec, 'fee': x['fee'], 'note': note})
    return out


_ADDON = re.compile(r'추가|초과\s*시|마다|\d\s*(kg|㎏|cm|㎝|m|㎡|ℓ|L|톤)\s*당')


def _order(x):
    """금액순이되, '10kg 초과 시 10kg당 추가' 같은 추가·단위 요금 줄은 뒤로."""
    return (1 if _ADDON.search(str(x.get('spec') or '')) else 0, x['fee'] or 0)


def _group_rows(src, label):
    """조례 행 묶음 → 고객 행(금액순, 품목명이 여럿이면 줄마다 조례 품목명, 3단 이상은 범위 표기)."""
    clean = lambda n: re.sub(r'\s+', ' ', re.sub(r'\s*\(\d+\)\s*', ' ', n or '')).strip()
    names = list(dict.fromkeys(clean(x['disp_item'] or x['name']) for x in src))
    out, seen = [], set()
    for x in sorted(src, key=_order):
        sp = x['disp_spec'] or C.tidy_spec(x['spec'])
        it = label if len(names) == 1 else clean(x['disp_item'] or x['name'])
        if (it, sp, x['fee']) in seen:
            continue
        seen.add((it, sp, x['fee']))
        out.append({'item': it, 'spec': sp, 'fee': x['fee'], 'note': '', 'fixed': bool(x['disp_spec']), 'src': x['name']})
    for item in dict.fromkeys(o['item'] for o in out):
        grp = [o for o in out if o['item'] == item]
        if len(grp) >= 3 and not any(g['fixed'] for g in grp):
            for g, sp in zip(grp, _ladder([g['spec'] for g in grp])):
                g['spec'] = sp
    for o in out:
        o.pop('fixed', None)
    return out


def _l2_rows(c, q, label, spec_only=False):
    """'양문형냉장고'·'3인용소파'처럼 앞말이 붙은 이름: 끝말 품목(없으면 유사품목)의 조례 행을 모두 펼친다.
    앞말이 규격 원문에 들어 있으면(침대 │ 2층 침대) 그 줄만 보여 준다."""
    hd = E.local_head(q, c.local)
    src = hd or E.local_analog(q, c.local)[1]
    if not src:
        return None
    k = E.norm(q)
    head = max((t for x in src for t in x['tok'] if k.endswith(t)), key=len, default='')
    pre = k[:len(k) - len(head)] if head else ''
    raw = lambda s: re.sub(r'\s', '', str(s or '').lower())
    hit = [x for x in src if pre and head and (pre + head) in raw(x['spec'])]                 # 침대 │ 돌침대 1인용
    hit = hit or [x for x in src if len(pre) >= 2 and pre in raw(x['spec'])]               # 냉장고 │ 양문형(600L 이상)
    if spec_only and not hit:
        return None
    out = _group_rows(hit or src, label)
    if not hd:      # 다른 품목(유사품목)으로 안내하면 어느 항목인지 밝힌다
        names = {o['item'] for o in out}
        if names == {label}:
            nm = re.sub(r'\s*\(\d+\)\s*', ' ', src[0]['disp_item'] or src[0]['name']).strip()
            comps = [p.strip() for p in re.split(r'[,ㆍ·/+]', nm) if p.strip()]
            if len(comps) >= 3:      # '벽시계, 가방, …, 항아리' 한 줄 항목: 실제로 맞은 낱개 이름만
                tgt = next((E.norm(lk) for qk, lk in E.ANALOG if E.norm(qk) in k), '')
                nm = next((p for p in comps if tgt and E.norm(p) == tgt), None) or                     next((p for p in comps if head and E.norm(p).endswith(head)), None) or nm
            for o in out:
                o['note'] = f'‘{nm}’ 항목으로 배출'
    return out


def _unclear(rows):
    """같은 품목·같은 규격 글자에 금액이 둘 이상이면(규격 원문 유실) 고객이 고를 수 없다."""
    seen = {}
    for o in rows:
        if o.get('fee') is None:
            continue
        key = (o['item'], o['spec'])
        if key in seen and seen[key] != o['fee']:
            return True
        seen[key] = o['fee']
    return False


def _category(c, label, q):
    return c.cats.get(E.norm(q)) or c.cats.get(E.norm(label)) or C.classify(label) or C.classify(q)


def _label_for(c, q):
    """브랜드·상품명(SYN)이 일반 명칭으로 바뀌었으면 '안마의자(바디프렌드)'처럼."""
    raw = _raw_norm(q)
    for a, b in E.SYN:
        if a in c.brand and a in raw:
            general = C.GENERAL_LABEL.get(b, b)
            return C.with_expr(general, q)
    return q


def _equiv_rows(c, q, label):
    """조례에 따로 없는 품목을 그 지자체 조례에서 같은 스티커로 내놓는 항목으로 안내한다(C.EQUIV).
    돌려주는 값: (고객 행, 쓴 조례 품명) 또는 None."""
    k = E.norm(q)
    k = C.EQUIV_ALIAS.get(k, k)
    rules = C.EQUIV.get(k)
    if not rules:
        return None
    clean = lambda n: re.sub(r'\s*\(\d+\)\s*', ' ', n or '').strip()
    for pat, bad, shown in rules:
        hit = [x for x in c.local if re.search(pat, x['name']) and not (bad and re.search(bad, x['name'] + ' ' + (x['spec'] or '')))]
        if not hit:
            continue
        if '전동' in E.norm(q):      # 전동형을 물으면 전동 줄(용산 '유아용 자동차(전동차)', 노원 '전동형')이 있으면 그것만
            pw = [x for x in hit if '전동' in (x['name'] + ' ' + (x['spec'] or ''))]
            hit = pw or hit
        name = clean(hit[0]['disp_item'] or hit[0]['name'])
        hit = [x for x in hit if clean(x['disp_item'] or x['name']) == name]
        note = f"‘{name}’ 항목으로 배출" if shown else ''
        out, seen = [], set()
        for x in sorted(hit, key=_order):
            spec = x['disp_spec'] or C.tidy_spec(x['spec'])
            if (spec, x['fee']) in seen:
                continue
            seen.add((spec, x['fee']))
            out.append({'item': label, 'spec': spec, 'fee': x['fee'], 'note': note, 'src': x['name']})
        out = [o for o in out if not (C.ROW_BAG.search(str(o['spec'])) or C.ROW_RATE.search(str(o['spec'])))] or out   # 추가·단가·봉투 줄만 빼고
        if _unclear(out) or (len(out) > 1 and _not_one_object(out, name)) or all(_RATE.search(str(o['spec'])) for o in out):
            continue          # 규격 원문 유실·무게 단가·다른 물건 묶음이면 다음 대체 항목으로
        return out, name
    return None


def _age_fit(q, rows):
    """'아기 전동자동차'에 '성인용' 줄을, '성인용 자전거'에 '어린이용' 줄을 보이지 않는다(남는 줄이 없으면 그대로)."""
    kid, adult = C.CHILD_WORDS.search(q or ''), C.ADULT_WORDS.search(q or '')
    if not rows or bool(kid) == bool(adult):
        return rows
    bad = C.ADULT_WORDS if kid else C.CHILD_WORDS
    keep = [o for o in rows if not bad.search(str(o.get('spec') or ''))]
    return keep or rows


def _row_words(text):
    s = re.sub(r'\s', '', str(text or '').lower())
    found = []
    for w in C.ROW_WORDS:
        if w in s:
            found.append(w)
            s = s.replace(w, '|')
    return found


_INDIRECT = ('상위어', '유사품목', '같은 배출', '다른 이름', '끝말', '전동형', '규격 일치')


def _fit_rows(q, rows):
    # 간접 답에서 '물어본 물건의 크기'가 아닌 줄을 뺀다: 다른 물건(캠핑의자→안마의자), 말하지 않은 종류(퀸침대→2층·돌·유아용),
    # 봉투·마대 부피, 무게·면적 단가. 남는 줄이 없으면 빈 목록(→ 확인 후 안내).
    qn = re.sub(r'\s', '', q or '') + '|' + E.norm(q or '')          # '흙침대'는 정규화하면 '돌침대'
    qf = {C.ROW_WORD[w] for w in _row_words(qn)}
    grown = re.search(r'퀸|킹|더블|싱글|\d\s*인|성인|어른|일반', q or '')      # 어른 크기를 말했으면 유아·아기 줄은 다른 종류
    kid = ('유아', '아기', '어린이', '아동')
    out = []
    for o in rows:
        sp = str(o.get('spec') or '')
        if o.get('method'):
            out.append(o)
            continue
        if C.ROW_BAG.search(sp) or C.ROW_WEIGHT.search(sp):
            continue                                     # 봉투·마대·무게 단가(면적·길이 단가는 그 물건의 크기라 남긴다)
        m = re.search(r'‘(.+?)’', str(o.get('note') or ''))
        tf = {C.ROW_WORD[w] for w in _row_words(m.group(1))} if m else set()
        tf |= {C.ROW_WORD[w] for w in _row_words(re.sub(r'\(.*?\)', '', str(o.get('src') or '')))}
        sw = _row_words(sp)
        sf = {C.ROW_WORD[w] for w in sw}
        if sf and not (sf & (qf | tf)):
            continue                                     # 규격에 다른 무리 물건 이름
        src = re.sub(r'\s', '', str(o.get('src') or ''))
        if len(re.split(r'[,ㆍ·/+]', src)) >= 3:
            src = ''                                     # '벽시계, 가방, …, 휠체어' 한 줄 묶음 이름은 종류 판단에 쓰지 않는다
        here = sp.replace(' ', '') + '|' + src
        if any(t in here and t not in qn and (t not in kid or grown) for t in C.TYPE_WORDS):
            continue                                     # 고객이 말하지 않은 다른 종류(규격 글이나 조례 품목 이름에)
        out.append(o)
    base = [o for o in out if not C.ROW_ADDON.search(str(o.get('spec') or ''))]
    return base if base and len(base) < len(out) else out      # '추가 시' 줄은 기본 줄이 있으면 뺀다


def resolve(c, q, label=None, expr=None):
    """품목명 1개 → {'kind': 'rows'|'pending'|'ask', rows, result(내부), names(ask일 때 후보)}"""
    res = _resolve(c, q, label, expr)
    if res.get('rows'):
        res['rows'] = _age_fit(expr or q, res['rows'])
        path = str(res.get('result', {}).get('경로') or '')
        if res['kind'] == 'rows' and any(k in path for k in _INDIRECT):
            kept = _fit_rows(expr or q, res['rows'])
            if not kept:
                return {'kind': 'pending', 'rows': res['rows'], 'result': dict(res['result'], 경로=path + ' (맞는 규격 없음)'), 'review': True}
            res['rows'] = kept
    return res


REF_MUNI = 'gwacheon'      # 확정표가 갖춰진 기준 지자체(조례에 없는 품목의 크기 구분·금액 비율 기준)


def _ref_scaled(c, q, label):
    """조례에 없는 품목: 과천 확정표·조례에 그 품목이 있으면 과천의 크기 구분을 그대로 쓰고,
    금액은 이 지역 금액 수준(k)으로 환산해 이 지역 금액 단계에 맞춘다. (캣타워면 캣타워로)"""
    if c.muni == REF_MUNI:
        return None
    try:
        g = ctx(REF_MUNI)
    except KeyError:
        return None
    rg = _resolve(g, q, label)
    grade = str(rg.get('result', {}).get('등급') or '')
    if rg['kind'] != 'rows' or not grade.startswith(('L0', 'L1')) or not rg['rows'] or any(not o.get('fee') for o in rg['rows']):
        return None
    ratio = (c.k or 1.0) / (g.k or 1.0)
    fees = [r['fee'] for r in c.local]
    grid = sorted({f for f in fees if fees.count(f) >= 2}) or c.grid      # 그 지역에서 두 번 이상 쓰는 금액 단계
    out = []
    for o in rg['rows']:
        fee = E.snap(o['fee'] * ratio, grid)
        out.append({'item': label, 'spec': o['spec'], 'fee': fee, 'note': ''})
    return out


def _resolve(c, q, label=None, expr=None):
    q = clean_name(q)
    label = label or _label_for(c, q)
    mh = _method_hit(c, q)
    if mh:
        rows = [{'item': label, 'spec': C.tidy_spec(m['spec']), 'fee': None, 'method': m['method'], 'note': ''} for m in mh]
        # 무상수거 같은 배출 방법 줄이 있어도 조례·확정표의 유료 규격은 함께 보여 준다(큰 TV 등)
        r0 = engine_price(c, q)
        if r0['등급'].startswith(('L0', 'L1')) and not r0.get('확인'):
            paid, rv = _rows_for(c, q, r0, label)
            if paid and not rv:
                rows += [o for o in paid if o['fee']]
        return {'kind': 'rows', 'rows': rows, 'result': {'등급': '배출 방법', '품목': q}}
    if _is_ambiguous(c, q):
        return {'kind': 'ask', 'rows': [], 'result': {'등급': 'L? 품목 확인 필요(표현 사전)', '품목': q}}
    r = engine_price(c, q)
    if r.get('확인'):
        return {'kind': 'ask', 'rows': [], 'result': r}
    multi = _multi_confirmed(c, q, r)
    if multi:
        return {'kind': 'ask', 'rows': [], 'result': r, 'names': multi}
    if not r['등급'].startswith(('L0', 'L1')):
        # 같은 물건의 다른 이름(아기 범퍼 → 침대범퍼)이 이 지자체 조례·확정표에 있으면 그것이 우선
        alias = C.EQUIV_ALIAS.get(E.norm(q))
        if alias and alias != E.norm(q):
            ra = engine_price(c, alias)
            if ra['등급'].startswith(('L0', 'L1')) and not ra.get('확인') and not _multi_confirmed(c, alias, ra):
                rows_a, review_a = _rows_for(c, alias, ra, label)
                if ra['등급'].startswith('L1'):
                    rows_a = _with_siblings(c, alias, rows_a, label)
                if rows_a and not review_a:
                    return {'kind': 'rows', 'rows': rows_a, 'result': dict(ra, 품목=q, 경로=f"다른 이름 '{alias}'로 찾음"), 'review': False}
        if not str(r.get('경로') or '').startswith('상위어'):
            ref = _ref_scaled(c, q, label)
            if ref and not _unclear(ref):
                return {'kind': 'rows', 'rows': ref, 'result': dict(r, 품목=q, 경로=f'과천 기준 지역 환산(k {c.k:.2f})'), 'review': True}
        eq = _equiv_rows(c, q, label)
        if eq:
            return {'kind': 'rows', 'rows': eq[0], 'result': dict(r, 품목=q, 경로=f"같은 배출 항목 '{eq[1]}'")}
    if r['등급'].startswith('L4') and ' ' in q and not expr:
        # 근거가 전혀 없는 여러 낱말 표현('베드 범퍼')은 끝말('범퍼')이 조례·확정표에 있으면 그 금액을 쓴다
        head = q.split()[-1]
        hk = E.norm(head)
        ok_l1 = lambda: any(E.norm(_base(x['name'])) == hk for x in c.conf if hk in x['tok'])   # 수식어 붙은 확정표 품목(강아지 계단)은 대체하지 않음
        if len(head) >= 2 and hk not in C.AMBIG_NOUNS:      # '원목 테이블'처럼 끝말이 애매하면 대체하지 않음
            r2 = engine_price(c, head)
            if r2['등급'].startswith(('L0', 'L1')) and not r2.get('확인') and not _multi_confirmed(c, head, r2) \
                    and (r2['등급'].startswith('L0') or ok_l1()):
                rows2, review2 = _rows_for(c, head, r2, label)
                if r2['등급'].startswith('L1'):
                    rows2 = _with_siblings(c, head, rows2, label)
                if rows2 and not review2:
                    return {'kind': 'rows', 'rows': rows2, 'result': dict(r2, 품목=q, 경로=f"끝말 '{head}'로 찾음"), 'review': False}
    if '전동' in E.norm(q) and r['등급'].startswith('L2* 전동형') and not expr:
        # 전동킥보드처럼 조례에 수동형도 없으면, 수동형(킥보드)이 매겨지는 항목의 규격을 보여 주고 배터리 안내를 붙인다
        base = re.sub(r'전동\s*', '', q).strip()
        if len(base) >= 2:
            rb = resolve(c, base, label=label, expr=q)
            if rb['kind'] == 'rows' and rb['rows'] and all(o.get('fee') for o in rb['rows']):
                top = max(enumerate(rb['rows']), key=lambda t: (t[1]['fee'], t[0]))[1]   # 전동형은 수동형 최고 구간(같은 금액이면 뒤쪽=큰 규격)
                rows_b = [dict(top, note=' · '.join(x for x in (top.get('note'), '배터리 분리 후 배출') if x))]
                return {'kind': 'rows', 'rows': rows_b, 'result': dict(rb['result'], 품목=q, 경로=f"전동형 → 수동형 '{base}' 기준"), 'review': False}
    if r['등급'].startswith('L2* 유사품목'):
        # 통계와 차이가 커도 앞말이 규격 원문에 그대로 있으면(침대 │ 1인용 돌침대 세트) 그 줄이 답이다
        l2s = _l2_rows(c, q, label, spec_only=True)
        if l2s and not _unclear(l2s):
            return {'kind': 'rows', 'rows': l2s, 'result': dict(r, 경로=str(r.get('경로')) + ' (규격 일치)'), 'review': False}
    if r['등급'].startswith('L2 유사품목'):
        # 상위어·유사품목은 최저가 한 줄 대신 그 품목의 규격을 모두 보여 준다(앞말이 규격에 있으면 그 줄만)
        l2 = _l2_rows(c, q, label)
        if l2 and _unclear(l2):
            return {'kind': 'pending', 'rows': l2, 'result': dict(r, 경로=str(r.get('경로')) + ' (규격 원문 유실)'), 'review': True}
        if l2:
            return {'kind': 'rows', 'rows': l2, 'result': r, 'review': False}
    rows, review = _rows_for(c, q, r, label)
    if r['등급'].startswith('L1'):
        rows = _with_siblings(c, q, rows, label)
    if _unclear(rows):          # '모든규격 3,000 / 모든규격 5,000' → 확인 후 안내
        review = True
        if c.policy == 'show':
            return {'kind': 'pending', 'rows': rows, 'result': dict(r, 경로=str(r.get('경로')) + ' (규격 원문 유실)'), 'review': True}
    if review and r['등급'].startswith('L3') and rows and all(o.get('fee') for o in rows) and not _unclear(rows):
        return {'kind': 'rows', 'rows': rows, 'result': r, 'review': True}      # 조례에 없는 품목: 전국 통계 × 지역 수준으로 계산해 안내
    if review and c.policy != 'show':
        return {'kind': 'pending', 'rows': rows, 'result': r, 'review': True}
    return {'kind': 'rows', 'rows': rows, 'result': r, 'review': review}


def public_rows(c, rows, q=None):
    out = []
    for o in rows:
        out.append({'품목': o['item'], '규격': o['spec'],
                    '수수료': o.get('method') or _fee_text(o['fee']),
                    '안내': o.get('note') or '',
                    '분류': _category(c, o['item'], q or o['item'])})
    return out


def _signature(res):
    if res['kind'] == 'pending':
        return ('pending', res['result'].get('품목'))
    if res['kind'] != 'rows':
        return ('ask', res['result'].get('품목'))
    return tuple((o['spec'], o['fee'], o.get('method')) for o in res['rows'])


# ================================================================ 검토 대기열·접수번호
def _internal(r):
    keep = ('품목', '규격', '수수료', '등급', '신뢰도', '경로', '유사', '유사구간', '통계추정', '전국', '구간', '조치', '확정')
    return {k: r.get(k) for k in keep if k in r}


def enqueue_review(c, q, label, res, extra=None):
    now = time.time()
    qn = E.norm(q)
    ex = store.q("SELECT id, asks FROM review WHERE muni=? AND qnorm=? AND status='open'", (c.muni, qn), one=True)
    detail = json.dumps(_internal(res.get('result') or {}), ensure_ascii=False, default=list)
    proposal = json.dumps(res.get('rows') or [], ensure_ascii=False)
    extra = extra or {}
    if ex and not extra:
        store.x('UPDATE review SET asks=asks+1, updated_at=? WHERE id=?', (now, ex['id']))
        return ex['id']
    if ex:
        store.x('UPDATE review SET asks=asks+1, updated_at=?, attachment=COALESCE(?,attachment), dims=COALESCE(?,dims), memo=COALESCE(?,memo) WHERE id=?',
                (now, extra.get('attachment'), extra.get('dims'), extra.get('memo'), ex['id']))
        return ex['id']
    return store.x('INSERT INTO review(muni,query,qnorm,label,status,detail,proposal,asks,attachment,dims,memo,created_at,updated_at) '
                   'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (c.muni, q, qn, label, 'open', detail, proposal, 1, extra.get('attachment'), extra.get('dims'),
                    extra.get('memo'), now, now))


def make_ticket(c, items):
    tid = ''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz23456789') for _ in range(8))
    store.x('INSERT INTO ticket(id,muni,items,created_at) VALUES(?,?,?,?)',
            (tid, c.muni, json.dumps(items, ensure_ascii=False), time.time()))
    return tid


def ticket(tid):
    t = store.q('SELECT * FROM ticket WHERE id=?', (str(tid or '').lower(),), one=True)
    if not t:
        return None
    c = ctx(t['muni'])
    rows, waiting, closed = [], [], []
    for it in json.loads(t['items']):
        rv = store.q('SELECT status, result FROM review WHERE id=?', (it['rid'],), one=True)
        if rv and rv['status'] == 'confirmed' and rv['result']:
            rows += json.loads(rv['result'])
        elif rv and rv['status'] == 'rejected':
            closed.append(it['name'])
        else:
            waiting.append(it['name'])
    msg = []
    if waiting:
        msg.append(PENDING_MSG)
    if closed:
        msg.append('안내가 어려운 품목입니다. 지자체 담당 부서로 문의해 주세요.')
    return {'status': 'ok', 'municipality': c.name, 'rows': rows, 'pending': waiting, 'closed': closed,
            'message': ' '.join(msg), 'ticket': t['id']}


CONTACT_KEEP_DAYS = 90


def _purge_contacts():
    """연락처는 받은 날부터 90일 뒤 지운다(동의 문구와 같은 기간)."""
    cut = time.time() - CONTACT_KEEP_DAYS * 86400
    old = store.q('SELECT id FROM ticket WHERE contact_at IS NOT NULL AND contact_at < ?', (cut,))
    if not old:
        return
    store.x('UPDATE ticket SET contact_name=NULL, contact_phone=NULL, contact_at=NULL WHERE contact_at < ?', (cut,))
    for r in store.q("SELECT id, contact FROM review WHERE contact IS NOT NULL AND contact != ''"):
        keep = [k for k in json.loads(r['contact']) if k.get('at', 0) >= cut]
        store.x('UPDATE review SET contact=? WHERE id=?', (json.dumps(keep, ensure_ascii=False) if keep else None, r['id']))


def save_contact(tid, name, phone, agree):
    """'확인 후 안내' 품목에 고객 이름·휴대폰 번호를 붙인다 → 운영 화면 검토 대기열에 보이고, 담당자가 문자로 알려 준다."""
    t = store.q('SELECT * FROM ticket WHERE id=?', (str(tid or '').lower(),), one=True)
    if not t:
        return {'status': 'error', 'message': '접수번호를 찾을 수 없습니다. 품목을 다시 입력해 주세요.'}
    name = re.sub(r'\s+', ' ', str(name or '')).strip()
    digits = re.sub(r'\D', '', str(phone or ''))
    if agree is not True:
        return {'status': 'error', 'message': '개인정보 수집·이용에 동의해 주세요.'}
    if not (1 <= len(name) <= 20) or re.search(r'[<>]', name):
        return {'status': 'error', 'message': '이름을 확인해 주세요.'}
    if not re.fullmatch(r'01[016789]\d{7,8}', digits):
        return {'status': 'error', 'message': '휴대폰 번호를 확인해 주세요. (예: 010-1234-5678)'}
    shown = f'{digits[:3]}-{digits[3:-4]}-{digits[-4:]}'
    now = time.time()
    _purge_contacts()
    store.x('UPDATE ticket SET contact_name=?, contact_phone=?, contact_at=? WHERE id=?', (name, shown, now, t['id']))
    for it in json.loads(t['items']):
        rv = store.q('SELECT contact FROM review WHERE id=?', (it['rid'],), one=True)
        if not rv:
            continue
        lst = [k for k in (json.loads(rv['contact']) if rv['contact'] else []) if k.get('phone') != shown]
        lst.append({'name': name, 'phone': shown, 'ticket': t['id'], 'item': it['name'], 'at': now})
        store.x('UPDATE review SET contact=?, updated_at=? WHERE id=?', (json.dumps(lst, ensure_ascii=False), now, it['rid']))
    return {'status': 'ok', 'message': f'접수되었습니다. 확인되는 대로 {shown[:4]}****-{shown[-4:]} 번호로 문자 드리겠습니다.'}


def _shop_rescue(c, name):
    """'확인 후 안내'로 갈 품목을 쇼핑몰(공식 API)에서 찾아 본다. 상품 분류명이 이 지자체 조례·확정표로 바로 안내되면
    '○○ 맞으신가요?' 카드를 돌려준다. 쇼핑몰 키가 없거나 안내할 수 있는 분류가 없으면 None."""
    if not shopping.providers():
        return None
    shop = _shopping_candidates(c, name)
    if not shop:
        return None
    ok = [(d, r) for d, r in _evaluate(c, shop, name) if r['kind'] == 'rows' and not r.get('review')]
    if not ok:
        return None
    top, res = ok[0]
    st = {'m': c.muni, 'e': name, 's': 1, 'p': 'yesno', 'c': [_cand_tuple(top)], 'x': [top['label']]}
    card = {'kind': 'yesno', 'question': f"문의하신 품목이 {top['label']}{josa(top['label'])} 맞으신가요?", 'item_label': top['label'],
            'product': {'title': top.get('title', ''), 'image': top.get('img', ''), 'link': top.get('link', '')},
            'size_options': _size_options(res['rows'])}
    return _card_public(st, card)


# ---- AI가 고른 항목이 '한 물건의 크기'인지 검사(2026-11-23 검수: 11,971개 후보 중 973개가 다른 물건·봉투·단가 묶음) ----
_BUNDLE = re.compile(r'묶음|마대|포대|봉투|봉지|자루|다발')
_NOTE = re.compile(r'문의|※|준용|경우\s*:')
_RATE = re.compile(r'(kg|㎏|킬로그램|킬로|ℓ|리터|L|㎥|톤|ton)\s*\)?\s*(당|마다)|톤\s*차량|㎥')
_ADD2 = re.compile(r'추가|초과\s*시|마다|가산|(?:㎡|m²|㎥|평|kg|킬로그램|m|미터|cm|단|ℓ|L|리터)\s*\)?\s*당')
_SIZED = re.compile(r'\d|이상|이하|미만|초과|[소중대]\s*형|특대|싱글|더블|퀸|킹|인용|모든\s*규격|일반|기본|전체|가정|업소|영업|사무|유아|아동|어린이|성인|어른|'
                    r'목재|철재|철제|스텐|플라스틱|대리석|원목|유리|스탠드|벽걸이|전기|가스|석유|수동|전동|접이|좌식|입식|서랍|편수|양수|'
                    r'그랜드|업라이트|어프라이트|디지털|겨울|여름|하절기|동절기|반신|전신|연탄|기름|홑|솜|거울|상판|틀|받침|세트|셋트|프레임|포함|것$|용$|형$|^\s*[소중대]\s*$')
_PAREN = re.compile(r'\([^()]*\)')


def _not_one_object(rows, name):
    """규격 줄이 그 물건의 크기가 아니라 다른 물건·봉투 묶음·무게 단가·안내문이면 True."""
    specs = [str(o.get('spec') or '').strip() for o in rows]
    if not specs:
        return True
    if all(_RATE.search(s) for s in specs):
        return True
    if any(_BUNDLE.search(s) or _NOTE.search(s) for s in specs):
        return True
    add = [s for s in specs if _ADD2.search(s)]
    if add and len(add) < len(specs):
        return True
    heads = [h[-2:] for h in re.findall(r'[가-힣]{2,}', _PAREN.sub(' ', name or ''))]
    bare = {re.sub(r'\s', '', _PAREN.sub('', s)) for s in specs if re.search(r'[가-힣]{2,}', _PAREN.sub('', s))
            and not _SIZED.search(s) and not any(h in s for h in heads)}
    return len(bare) >= 2


def _own_rows(c, x, label):
    """조례 항목 x '자기' 줄만(resolve 는 괄호를 떼고 다른 항목까지 묶어 올 수 있다). 한 줄 여러 품목 이름의 낱개면 그 줄."""
    clean = lambda n: re.sub(r'\s+', ' ', re.sub(r'\s*\(\d+\)\s*', ' ', n or '')).strip()
    own = [r for r in c.local if clean(r['disp_item'] or r['name']) == x or clean(r['name']) == x]
    if not own:
        own = [r for r in c.local if x in [p.strip() for p in re.split(r'[,ㆍ·/+]', _PAREN.sub('', r['name']))]]
    if not own:
        conf = [r for r in c.conf if r['name'] == x]
        if conf:
            return [{'item': label, 'spec': C.tidy_spec(r['spec'] or '모든규격'), 'fee': r['fee'], 'note': ''} for r in sorted(conf, key=lambda r: r['fee'])]
        return None
    rows = _group_rows(own, label)
    for o in rows:
        o['item'] = label
    return rows


def _ai_rescue(c, name):
    """조례에서 못 찾은 이름 → AI가 이 지자체 조례 품목명 중에서 고른다 → 조례 금액으로 바로 안내되는 첫 품목을
    '○○ 맞으신가요?'로 묻는다. 나머지 후보는 '아니요' 다음 선택지로 쓴다. AI를 쓸 수 없으면 None."""
    if not ai.available():
        return None
    clean = lambda n: re.sub(r'\s*\(\d+\)\s*', ' ', n or '').strip()
    names = [clean(x['disp_item'] or x['name']) for x in c.local] + [x['name'] for x in c.conf]
    names = [n for n in names if not C.CATCH_ALL.search(n)]      # 나무류·플라스틱류 같은 재질 묶음은 물건의 크기 기준이 아님
    picks = ai.pick_items(c.muni, c.name, name, names)
    ok = []
    for p in picks:
        own = _own_rows(c, p, p)
        res = {'kind': 'rows', 'rows': own} if own else resolve(c, p, label=p)
        if res['kind'] != 'rows' or res.get('review') or not res['rows']:
            continue
        if _not_one_object(res['rows'], p) or _unclear(res['rows']):
            continue                     # 나무류(합판·팔레트)·봉투 묶음·단가 줄은 물건의 크기로 안내하지 않는다
        ok.append(({'id': p, 'label': p, 'query': p, 'desc': ''}, res))
    if not ok:
        return None
    top, res = ok[0]
    st = {'m': c.muni, 'e': name, 's': 1, 'p': 'yesno', 'c': [_cand_tuple(top)], 'x': [top['label']],
          'a': [d['label'] for d, _ in ok[1:]], 'v': 1}
    card = {'kind': 'yesno', 'question': f"‘{top['label']}’ 항목으로 내놓으시면 됩니다. 이대로 안내해 드릴까요?",
            'item_label': top['label'], 'as_item': True, 'product': None, 'size_options': _size_options(res['rows'])}
    return _card_public(st, card)


# ================================================================ 확인 질문 흐름 (HANDOFF 5절)
def _cand_tuple(d):
    return [d['label'], d['query'], d.get('desc', ''), d.get('img', ''), d.get('link', ''), d.get('title', '')]


def _from_tuple(t):
    return {'label': t[0], 'query': t[1], 'desc': t[2], 'img': t[3] if len(t) > 3 else '',
            'link': t[4] if len(t) > 4 else '', 'title': t[5] if len(t) > 5 else ''}


def _shopping_candidates(c, expr):
    """쇼핑몰 상위 결과 → 카테고리 말단별 후보(빈도순) + 대표 상품. 사용할 수 없으면 None."""
    items = shopping.search(expr)
    if not items:
        return None
    groups = {}
    for p in items:
        leaf = p.get('leaf') or ''
        if not leaf:
            continue
        cid = C.LEAF.get(E.norm(leaf).replace(' ', ''))
        if cid:
            d = C.cand(cid)
        else:
            d = {'id': leaf, 'label': leaf, 'query': leaf, 'desc': ' > '.join(p.get('path', [])[-2:])}
        g = groups.setdefault(d['label'], {'d': d, 'n': 0, 'p': p})
        g['n'] += 1
    out = []
    for g in sorted(groups.values(), key=lambda g: -g['n']):
        d = dict(g['d'])
        d['img'], d['link'], d['title'] = g['p'].get('image', ''), g['p'].get('link', ''), g['p'].get('title', '')
        out.append(d)
    return out


def _evaluate(c, cands, expr):
    """후보마다 엔진을 미리 돌린다. 근거가 전혀 없는(L4) 쇼핑몰 말단은 버린다."""
    out = []
    for d in cands:
        res = resolve(c, d['query'], label=d['label'])
        if res['kind'] == 'ask':
            continue
        if res['result'].get('등급', '').startswith('L4') and d.get('img'):
            continue
        out.append((d, res))
    return out


def _merge_by_fee(evals, limit=4):
    """금액이 같은 후보는 하나로 합친다 → [(label, desc, [cand...])]"""
    groups = []
    for d, res in evals:
        sig = _signature(res)
        for g in groups:
            if g['sig'] == sig:
                if d['label'] not in g['labels']:
                    g['labels'].append(d['label'])
                    g['cands'].append(d)
                break
        else:
            groups.append({'sig': sig, 'labels': [d['label']], 'cands': [d], 'desc': d.get('desc', '')})
    return groups[:limit]


def _size_options(rows):
    specs = [o['spec'] for o in rows]
    return specs if len(specs) > 1 and len(set(o['item'] for o in rows)) == 1 else None


def _card_public(state, card):
    card['card_id'] = sign(state, ttl=CARD_TTL)
    card['step'] = state['s']
    card['max_steps'] = MAX_ASKS
    card['name'] = state['e']
    return card


def _choice_card(c, state, cands, title):
    evals = _evaluate(c, cands, state['e'])
    groups = _merge_by_fee(evals)
    state = dict(state, p='choice', c=[[_cand_tuple(d) for d in g['cands']] for g in groups])
    options = [{'id': i, 'label': ' · '.join(g['labels']), 'desc': g['desc']} for i, g in enumerate(groups)]
    return _card_public(state, {'kind': 'choice', 'question': title, 'options': options, 'other': True})


def _detail_card(state):
    state = dict(state, p='detail', c=[])
    return _card_public(state, {'kind': 'detail',
                                'question': '사진이나 가로·세로·높이를 알려 주시면 바로 안내해 드리겠습니다.',
                                'fields': ['photo', 'width', 'depth', 'height', 'text']})


def start_confirm(c, expr, names=None):
    """애매한 품목 → 바로 답(후보 금액이 모두 같을 때) 또는 첫 카드."""
    state = {'m': c.muni, 'e': expr, 's': 1}
    shop = _shopping_candidates(c, expr)
    fb = [C.cand(i) for i in C.fallback_candidates(expr, c.hints)]
    if names:
        fb = [{'id': n, 'label': n, 'query': n, 'desc': ''} for n in names] + fb
    cands = list(shop or [])
    seen = {d['label'] for d in cands}
    cands += [d for d in fb if d['label'] not in seen]
    evals = _evaluate(c, cands, expr)
    if not evals:
        return {'kind': 'card', 'card': _detail_card(state)}
    sigs = {_signature(r) for _, r in evals}
    if len(sigs) == 1 and evals[0][1]['kind'] == 'rows' and not names:
        return {'kind': 'rows', 'rows': [dict(o, item=C.with_expr(o['item'], expr) if C.is_brand(expr) else expr)
                                         for o in evals[0][1]['rows']]}
    if shop:
        top, res = next(((d, r) for d, r in evals if d.get('img')), evals[0])
        st = dict(state, p='yesno', c=[_cand_tuple(top)], x=[top['label']])
        card = {'kind': 'yesno', 'question': f"문의하신 품목이 {top['label']}{josa(top['label'])} 맞으신가요?", 'item_label': top['label'],
                'product': {'title': top.get('title', ''), 'image': top.get('img', ''), 'link': top.get('link', '')},
                'size_options': _size_options(res['rows']) if res['kind'] == 'rows' else None}
        return {'kind': 'card', 'card': _card_public(st, card)}
    return {'kind': 'card', 'card': _choice_card(c, state, cands, '품목 이름을 조금 더 알려 주세요. 아래 중 어느 것인가요?')}


def josa(label):
    base = re.sub(r'\s*\([^()]*\)\s*$', '', str(label)).strip()
    ch = ord(base[-1]) if base else 0
    if 0xAC00 <= ch <= 0xD7A3:
        return '이' if (ch - 0xAC00) % 28 else '가'
    return '가'


def _log_expression(c, expr, label, query):
    if not expr or E.norm(expr) == E.norm(label):
        return
    now = time.time()
    en = _raw_norm(expr)
    r = store.q('SELECT id FROM expression WHERE muni=? AND enorm=? AND general=?', (c.muni, en, label), one=True)
    if r:
        store.x('UPDATE expression SET count=count+1, updated_at=? WHERE id=?', (now, r['id']))
    else:
        store.x('INSERT INTO expression(muni,expr,enorm,general,query,count,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (c.muni, expr, en, label, query, 1, 'new', now, now))


def _finish(c, expr, d, size=None, label=None, as_item=False):
    label = label or (expr if as_item else C.with_expr(d['label'], expr) if C.is_brand(expr) else d['label'])
    own = _own_rows(c, d['query'], label) if as_item else None
    res = {'kind': 'rows', 'rows': own, 'result': {}} if own else resolve(c, d['query'], label=label)
    _log_expression(c, expr, d['label'], d['query'])
    if res['kind'] == 'rows':
        rows = res['rows']
        rows = _age_fit(expr, rows)
        if as_item:      # AI가 고른 조례 항목: 고객이 쓴 이름 + '○○ 항목으로 배출'
            rows = [dict(o, note=f"‘{d['label']}’ 항목으로 배출") for o in rows]   # '현행 조례 품목'보다 어느 항목인지가 먼저
        if size:
            pick = [o for o in rows if o['spec'] == size]
            rows = pick or rows
        return _answer(c, rows=rows, q=d['query'])
    if res['kind'] == 'pending':
        return _pending_answer(c, [(d['query'], label, res)])
    return None


def _answer(c, rows=None, pending=None, cards=None, ticket_id=None, q=None):
    out = {'status': 'ok', 'message': '문의하신 품목의 수수료입니다.' if rows else '',
           'rows': public_rows(c, rows or [], q), 'pending': pending or [], 'needs_confirm': cards or []}
    if pending:
        out['pending_message'] = PENDING_MSG
        out['ticket'] = ticket_id
    return out


def _pending_answer(c, items, extra=None):
    tk = []
    for q, label, res in items:
        rid = enqueue_review(c, q, label, res, extra)
        tk.append({'name': label, 'rid': rid})
    tid = make_ticket(c, tk)
    return _answer(c, pending=[t['name'] for t in tk], ticket_id=tid)


def confirm(token, answer, choice=None, size=None, text=None, photo=None, dims=None):
    st = unsign(token)
    if not st:
        return {'status': 'error', 'message': '확인 시간이 지났습니다. 품목을 다시 입력해 주세요.'}
    c = ctx(st['m'])
    expr, step, phase = st['e'], st['s'], st['p']
    cands = st.get('c') or []
    answer = (answer or '').lower()
    if phase == 'yesno':
        d = _from_tuple(cands[0])
        if answer == 'yes':
            return _finish(c, expr, d, size=size, as_item=bool(st.get('v'))) or _answer(c)
        # 아니요 → 같은 검색·주변 후보 중 수수료가 서로 다른 것 3~4개 + 기타
        others = [{'id': n, 'label': n, 'query': n, 'desc': ''} for n in st.get('a', [])]
        others += [x for x in (_shopping_candidates(c, expr) or []) if x['label'] not in st.get('x', [])]
        fb = [C.cand(i) for i in C.fallback_candidates(expr, c.hints)]
        seen = {x['label'] for x in others} | set(st.get('x', []))
        others += [x for x in fb if x['label'] not in seen]
        nst = dict(st, s=step + 1)
        return {'status': 'card', 'card': _choice_card(c, nst, others, '그러면 아래 중 어느 것인가요?')}
    if phase == 'choice':
        if answer == 'choice' and choice is not None:
            try:
                grp = [_from_tuple(t) for t in cands[int(choice)]]
            except (ValueError, IndexError, TypeError):
                return {'status': 'error', 'message': '선택지를 다시 골라 주세요.'}
            if len(grp) == 1:
                return _finish(c, expr, grp[0]) or _answer(c)
            label = ' · '.join(g['label'] for g in grp)
            label = C.with_expr(label, expr) if C.is_brand(expr) else label
            return _finish(c, expr, grp[0], label=label) or _answer(c)
        t = clean_name(text)
        if t:
            res = resolve(c, t)
            if res['kind'] == 'rows':
                _log_expression(c, expr, t, t)
                return _answer(c, rows=res['rows'], q=t)
            if res['kind'] == 'pending':
                return _pending_answer(c, [(t, t, res)])
        if step >= MAX_ASKS:
            return _pending_answer(c, [(expr, expr, {'result': {'품목': expr, '등급': 'L? 확인 질문 종료'}, 'rows': []})],
                                   {'memo': t or None})
        nst = dict(st, s=step + 1, t=t)
        return {'status': 'card', 'card': _detail_card(nst)}
    if phase == 'detail':
        memo = clean_name(text) or st.get('t') or None
        dm = None
        if dims:
            dm = json.dumps({k: v for k, v in dims.items() if v}, ensure_ascii=False) or None
        pic = photo if (photo and isinstance(photo, str) and photo.startswith('data:image/') and len(photo) < 1_600_000) else None
        return _pending_answer(c, [(expr, expr, {'result': {'품목': expr, '등급': 'L? 사진·치수 확인'}, 'rows': []})],
                               {'attachment': pic, 'dims': dm, 'memo': memo})
    return {'status': 'error', 'message': '확인 시간이 지났습니다. 품목을 다시 입력해 주세요.'}


# ================================================================ 견적 (POST /api/quote)
def quote(muni, items):
    c = ctx(muni)
    rows, pend, cards = [], [], []
    seen = set()
    for it in items[:30]:
        name = clean_name(it.get('name') if isinstance(it, dict) else it)
        if not name or E.norm(name) in seen:
            continue
        seen.add(E.norm(name))
        res = resolve(c, name)
        if res['kind'] == 'rows':
            rows += res['rows']
            if res.get('review'):          # 정책 '바로 보여주기'여도 운영자 확정은 받는다
                enqueue_review(c, name, _label_for(c, name), res)
        elif res['kind'] == 'pending':
            card = _shop_rescue(c, name) or _ai_rescue(c, name)
            if card:
                cards.append(card)
            else:
                pend.append((name, _label_for(c, name), res))
        else:
            r = start_confirm(c, name, res.get('names'))
            if r['kind'] == 'rows':
                rows += r['rows']
            else:
                cards.append(r['card'])
    tid = None
    if pend:
        tk = [{'name': label, 'rid': enqueue_review(c, q, label, res)} for q, label, res in pend]
        tid = make_ticket(c, tk)
    out = _answer(c, rows=rows, pending=[p[1] for p in pend], cards=cards, ticket_id=tid)
    out['municipality'] = c.name
    return out


# ================================================================ 운영자용(근거 포함)
def admin_try(muni, q):
    c = ctx(muni)
    r = engine_price(c, q)
    rows, review = _rows_for(c, q, r, _label_for(c, q)) if not r.get('확인') else ([], False)
    return {'result': _internal(r), 'rows': public_rows(c, rows, q), 'review': review,
            'ambiguous': bool(r.get('확인')) or _is_ambiguous(c, q), 'policy': c.policy}


def stats(muni):
    c = ctx(muni)
    fees = [r['fee'] for r in c.local]
    cgrid = sorted({f for f in fees if fees.count(f) >= 2})
    return {'rows': len(c.local), 'grid': c.grid, 'grid2': cgrid, 'k': round(c.k, 3), 'k_pairs': c.kn,
            'mad': round(c.mad, 3) if c.mad is not None else None, 'confirmed': len(c.conf) + len(c.methods),
            'nat_items': len(c.nat)}
