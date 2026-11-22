"""엔진을 감싸는 서비스 계층.
- 금액은 전부 engine.price()/client_rows()가 정한다. 여기서는 (1) 지자체별 입력 준비 (2) 고객용 표기 정리
  (3) 확인 질문 흐름 (4) 검토 대기열·접수번호를 다룬다.
- 고객에게 나가는 dict에는 등급·경로·통계 같은 근거를 절대 넣지 않는다(공개 함수 quote/confirm/ticket 반환값).
"""
import json, os, re, secrets, tempfile, threading, time

from engine import engine as E
from . import catalog as C
from . import shopping, store
from .tokens import sign, unsign

BASE_SYN = list(E.SYN)
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
        c.local = [{'name': r['item'], 'spec': r['spec'], 'fee': r['fee'], 'tok': E.tokens(r['item']),
                    'disp_item': r['disp_item'], 'disp_spec': r['disp_spec']}
                   for r in store.q('SELECT * FROM ordinance WHERE muni=? ORDER BY ord', (muni,))]
        crow = store.q('SELECT * FROM confirmed WHERE muni=? ORDER BY id', (muni,))
        c.conf = [{'name': r['item'], 'spec': r['spec'] or '', 'fee': r['fee'], 'tok': E.tokens(r['item'])}
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
        _CACHE.clear()
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
            out.append({'item': item, 'spec': disp_spec, 'fee': x['fee'], 'note': note, 'fixed': bool(x['disp_spec'])})
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
        hit = [x for x in c.local if re.search(pat, x['name']) and not re.search(bad, x['name'] + ' ' + (x['spec'] or ''))]
        if not hit:
            continue
        name = clean(hit[0]['disp_item'] or hit[0]['name'])
        hit = [x for x in hit if clean(x['disp_item'] or x['name']) == name]
        note = f"‘{name}’ 항목으로 배출" if shown else ''
        out, seen = [], set()
        for x in sorted(hit, key=lambda x: x['fee']):
            spec = x['disp_spec'] or C.tidy_spec(x['spec'])
            if (spec, x['fee']) in seen:
                continue
            seen.add((spec, x['fee']))
            out.append({'item': label, 'spec': spec, 'fee': x['fee'], 'note': note})
        return out, name
    return None


def resolve(c, q, label=None, expr=None):
    """품목명 1개 → {'kind': 'rows'|'pending'|'ask', rows, result(내부), names(ask일 때 후보)}"""
    q = clean_name(q)
    label = label or _label_for(c, q)
    mh = _method_hit(c, q)
    if mh:
        rows = [{'item': label, 'spec': C.tidy_spec(m['spec']), 'fee': None, 'method': m['method'], 'note': ''} for m in mh]
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
        eq = _equiv_rows(c, q, label)
        if eq:
            return {'kind': 'rows', 'rows': eq[0], 'result': dict(r, 품목=q, 경로=f"같은 배출 항목 '{eq[1]}'")}
    if r['등급'].startswith('L4') and ' ' in q and not expr:
        # 근거가 전혀 없는 여러 낱말 표현('베드 범퍼')은 끝말('범퍼')이 조례·확정표에 있으면 그 금액을 쓴다
        head = q.split()[-1]
        if len(head) >= 2:
            r2 = engine_price(c, head)
            if r2['등급'].startswith(('L0', 'L1')) and not r2.get('확인') and not _multi_confirmed(c, head, r2):
                rows2, review2 = _rows_for(c, head, r2, label)
                if rows2 and not review2:
                    return {'kind': 'rows', 'rows': rows2, 'result': dict(r2, 품목=q, 경로=f"끝말 '{head}'로 찾음"), 'review': False}
    rows, review = _rows_for(c, q, r, label)
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


def _finish(c, expr, d, size=None, label=None):
    label = label or (C.with_expr(d['label'], expr) if C.is_brand(expr) else d['label'])
    res = resolve(c, d['query'], label=label)
    _log_expression(c, expr, d['label'], d['query'])
    if res['kind'] == 'rows':
        rows = res['rows']
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
            return _finish(c, expr, d, size=size) or _answer(c)
        # 아니요 → 같은 검색·주변 후보 중 수수료가 서로 다른 것 3~4개 + 기타
        others = [x for x in (_shopping_candidates(c, expr) or []) if x['label'] not in st.get('x', [])]
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
