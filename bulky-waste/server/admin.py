"""운영자 API (/api/admin/*). 모든 경로는 로그인 세션이 있어야 한다. 근거 데이터는 여기서만 나간다."""
import csv, hmac, io, json, os, re, time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse

from engine import engine as E
from . import catalog as C
from . import natdata, service as S, shopping, store
from .ratelimit import rate_limit
from .tokens import sign, unsign

router = APIRouter(prefix='/api/admin')
COOKIE = 'bw_admin'
METHODS = ('무상수거', '종량제봉투 배출', '대상 아님(건설폐기물)')


# ---------------------------------------------------------------- 인증
def users():
    raw = os.environ.get('ADMIN_USERS')
    out = []
    if raw:
        try:
            for u in json.loads(raw):
                if u.get('id') and (u.get('pw') or u.get('password')):
                    out.append({'id': str(u['id']), 'pw': str(u.get('pw') or u.get('password')), 'name': str(u.get('name') or u['id'])})
        except Exception:
            pass
    if os.environ.get('ADMIN_PASSWORD'):
        out.append({'id': os.environ.get('ADMIN_ID', 'admin'), 'pw': os.environ['ADMIN_PASSWORD'], 'name': os.environ.get('ADMIN_NAME', '운영자')})
    return out


def me(request: Request):
    s = unsign(request.cookies.get(COOKIE, ''))
    if not s or not s.get('u'):
        raise HTTPException(401, '로그인이 필요합니다')
    return s


@router.post('/login')
async def login(request: Request, response: Response):
    rate_limit(request, 'login')
    body = await request.json()
    uid, pw = str(body.get('id') or ''), str(body.get('pw') or '')
    for u in users():
        if hmac.compare_digest(u['id'], uid) and hmac.compare_digest(u['pw'], pw):
            tok = sign({'u': u['id'], 'n': u['name']}, ttl=12 * 3600)
            secure = request.url.scheme == 'https' or request.headers.get('x-forwarded-proto') == 'https'
            response.set_cookie(COOKIE, tok, httponly=True, samesite='strict', secure=secure, max_age=12 * 3600, path='/')
            store.log(u['name'], '로그인', u['id'])
            return {'ok': True, 'name': u['name']}
    if not users():
        raise HTTPException(503, '운영자 계정이 설정되지 않았습니다(ADMIN_PASSWORD 또는 ADMIN_USERS 환경변수)')
    raise HTTPException(401, '아이디 또는 비밀번호가 맞지 않습니다')


@router.post('/logout')
def logout(response: Response):
    response.delete_cookie(COOKIE, path='/')
    return {'ok': True}


@router.get('/me')
def whoami(u=Depends(me)):
    return {'id': u['u'], 'name': u['n']}


def _muni(m):
    if not store.q('SELECT 1 FROM municipality WHERE code=?', (m,), one=True):
        raise HTTPException(404, '지자체를 찾을 수 없습니다')
    return m


# ---------------------------------------------------------------- 개요
@router.get('/overview')
def overview(muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    st = S.stats(muni)
    return {'stats': st, 'open_reviews': store.q("SELECT COUNT(*) n FROM review WHERE muni=? AND status='open'", (muni,), one=True)['n'],
            'new_expressions': store.q("SELECT COUNT(*) n FROM expression WHERE muni=? AND status='new'", (muni,), one=True)['n'],
            'policy': store.get_setting(f'policy:{muni}', 'hold'), 'nat_updated': store.get_setting('nat_updated'),
            'nat_source': store.get_setting('nat_source'), 'shopping': shopping.status(),
            'sync': {'enabled': store.SYNC.enabled, 'error': store.SYNC.error}, 'municipalities': S.municipalities()}


@router.get('/try')
def try_item(q: str, muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    return S.admin_try(muni, q)


# ---------------------------------------------------------------- 검토 대기열
@router.get('/review')
def review_list(muni: str = 'gwacheon', status: str = 'open', u=Depends(me)):
    _muni(muni)
    rows = store.q('SELECT id,muni,query,label,status,detail,proposal,asks,dims,memo,created_at,updated_at,resolved_by,resolved_at,result,'
                   '(attachment IS NOT NULL) AS has_photo FROM review WHERE muni=? AND status=? ORDER BY asks DESC, updated_at DESC LIMIT 300',
                   (muni, status))
    for r in rows:
        for k in ('detail', 'proposal', 'result', 'dims'):
            r[k] = json.loads(r[k]) if r.get(k) else None
        r['category'] = C.classify(r['label'] or r['query'])
    return {'items': rows}


@router.get('/review/{rid}/photo')
def review_photo(rid: int, u=Depends(me)):
    r = store.q('SELECT attachment FROM review WHERE id=?', (rid,), one=True)
    if not r or not r['attachment']:
        raise HTTPException(404)
    m = re.match(r'data:(image/[\w+.-]+);base64,(.*)$', r['attachment'], re.S)
    if not m:
        raise HTTPException(404)
    import base64
    return Response(base64.b64decode(m.group(2)), media_type=m.group(1), headers={'Cache-Control': 'private, no-store'})


def _validate_rows(rows):
    out = []
    for r in rows or []:
        spec = re.sub(r'\s+', ' ', str(r.get('spec') or '모든규격')).strip() or '모든규격'
        if re.search(r'이하|초과', spec):
            raise HTTPException(400, f"규격은 '미만/이상'으로 적어 주세요: {spec}")
        fee, method = r.get('fee'), (r.get('method') or '').strip() or None
        if isinstance(fee, str):
            if fee.strip() in METHODS:
                method, fee = fee.strip(), None
            else:
                fee = store.parse_fee(fee)
        if method and method not in METHODS:
            raise HTTPException(400, f'배출 방법은 {", ".join(METHODS)} 중 하나여야 합니다')
        if not method and (not fee or int(fee) <= 0):
            raise HTTPException(400, f'수수료를 확인해 주세요: {spec}')
        out.append({'spec': spec, 'fee': int(fee) if fee else None, 'method': method})
    if not out:
        raise HTTPException(400, '규격·수수료가 한 줄 이상 있어야 합니다')
    if len({r['spec'] for r in out}) != len(out):
        raise HTTPException(400, '같은 규격이 두 번 들어 있습니다')
    fees = [r['fee'] for r in out if r['fee']]
    return out


@router.post('/review/{rid}')
async def review_act(rid: int, request: Request, u=Depends(me)):
    body = await request.json()
    r = store.q('SELECT * FROM review WHERE id=?', (rid,), one=True)
    if not r:
        raise HTTPException(404, '없는 항목입니다')
    if r['status'] != 'open':
        raise HTTPException(409, '이미 처리된 항목입니다')
    action = body.get('action')
    now = time.time()
    if action == 'reject':
        store.x("UPDATE review SET status='rejected', resolved_by=?, resolved_at=?, result=? WHERE muni=? AND qnorm=? AND status='open'",
                (u['n'], now, json.dumps([]), r['muni'], r['qnorm']))
        store.log(u['n'], '검토 반려', r['query'], {'id': rid}, {'memo': body.get('message')})
        return {'ok': True}
    if action not in ('confirm', 'edit'):
        raise HTTPException(400, 'action 은 confirm · edit · reject 중 하나')
    item = re.sub(r'\s+', ' ', str(body.get('item') or r['query'])).strip()
    rows = body.get('rows')
    if not rows:
        prop = json.loads(r['proposal'] or '[]')
        rows = [{'spec': p['spec'], 'fee': p.get('fee'), 'method': p.get('method')} for p in prop]
    rows = _validate_rows(rows)
    category = body.get('category') or C.classify(item)
    before = store.q('SELECT item,spec,fee,method FROM confirmed WHERE muni=? AND item=?', (r['muni'], item))
    store.x('DELETE FROM confirmed WHERE muni=? AND item=?', (r['muni'], item))
    store.xmany('INSERT INTO confirmed(muni,item,spec,fee,method,category,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)',
                [(r['muni'], item, x['spec'], x['fee'], x['method'], category, now, u['n']) for x in rows])
    store.bump_version()
    c = S.ctx(r['muni'])
    res = S.resolve(c, r['query'])
    if res['kind'] == 'rows':
        result = S.public_rows(c, res['rows'], r['query'])
    else:
        label = r['label'] or item
        result = S.public_rows(c, [{'item': label, 'spec': x['spec'], 'fee': x['fee'], 'method': x['method'], 'note': ''} for x in rows])
    store.x("UPDATE review SET status='confirmed', resolved_by=?, resolved_at=?, result=? WHERE muni=? AND qnorm=? AND status='open'",
            (u['n'], now, json.dumps(result, ensure_ascii=False), r['muni'], r['qnorm']))
    store.x("UPDATE review SET status='confirmed', resolved_by=?, resolved_at=?, result=? WHERE id=?",
            (u['n'], now, json.dumps(result, ensure_ascii=False), rid))
    store.log(u['n'], '검토 확정' if action == 'confirm' else '금액 수정 후 확정', f"{r['query']} → {item}", before,
              {'item': item, 'rows': rows})
    return {'ok': True, 'result': result, 'resolved_as': res['kind']}


# ---------------------------------------------------------------- 확정표
@router.get('/confirmed')
def confirmed_list(muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    rows = store.q('SELECT * FROM confirmed WHERE muni=? ORDER BY id', (muni,))
    order = {c: i for i, c in enumerate(C.CATEGORY_ORDER)}
    rows.sort(key=lambda r: (order.get(r['category'] or '기타', 99), r['id']))
    return {'items': rows}


@router.post('/confirmed')
async def confirmed_create(request: Request, muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    b = await request.json()
    item = re.sub(r'\s+', ' ', str(b.get('item') or '')).strip()
    if not item:
        raise HTTPException(400, '품목을 입력해 주세요')
    row = _validate_rows([b])[0]
    if store.q('SELECT 1 FROM confirmed WHERE muni=? AND item=? AND spec=?', (muni, item, row['spec']), one=True):
        raise HTTPException(409, '같은 품목·규격이 이미 있습니다')
    cat = b.get('category') or C.classify(item)
    rid = store.x('INSERT INTO confirmed(muni,item,spec,fee,method,category,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)',
                  (muni, item, row['spec'], row['fee'], row['method'], cat, time.time(), u['n']))
    store.bump_version()
    store.log(u['n'], '확정표 추가', item, None, dict(row, item=item, category=cat))
    return {'ok': True, 'id': rid}


@router.put('/confirmed/{cid}')
async def confirmed_update(cid: int, request: Request, u=Depends(me)):
    b = await request.json()
    old = store.q('SELECT * FROM confirmed WHERE id=?', (cid,), one=True)
    if not old:
        raise HTTPException(404)
    item = re.sub(r'\s+', ' ', str(b.get('item') or old['item'])).strip()
    row = _validate_rows([{'spec': b.get('spec', old['spec']), 'fee': b.get('fee', old['fee']),
                           'method': b.get('method', old['method'])}])[0]
    dup = store.q('SELECT id FROM confirmed WHERE muni=? AND item=? AND spec=? AND id<>?', (old['muni'], item, row['spec'], cid), one=True)
    if dup:
        raise HTTPException(409, '같은 품목·규격이 이미 있습니다')
    cat = b.get('category') or old['category'] or C.classify(item)
    store.x('UPDATE confirmed SET item=?, spec=?, fee=?, method=?, category=?, updated_at=?, updated_by=? WHERE id=?',
            (item, row['spec'], row['fee'], row['method'], cat, time.time(), u['n'], cid))
    store.bump_version()
    store.log(u['n'], '확정표 수정', item, {k: old[k] for k in ('item', 'spec', 'fee', 'method', 'category')},
              dict(row, item=item, category=cat))
    return {'ok': True}


@router.delete('/confirmed/{cid}')
def confirmed_delete(cid: int, u=Depends(me)):
    old = store.q('SELECT * FROM confirmed WHERE id=?', (cid,), one=True)
    if not old:
        raise HTTPException(404)
    store.x('DELETE FROM confirmed WHERE id=?', (cid,))
    store.bump_version()
    store.log(u['n'], '확정표 삭제', old['item'], {k: old[k] for k in ('item', 'spec', 'fee', 'method', 'category')}, None)
    return {'ok': True}


def _xlsx_bytes(title, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    wb = Workbook()
    ws = wb.active
    ws.title = '수수료'
    ws['A1'] = title
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = time.strftime('%Y-%m-%d 기준')
    hdr = ['분류', '품목', '규격', '수수료(원)']
    thin = Side(style='thin', color='BBBBBB')
    for i, h in enumerate(hdr, 1):
        cell = ws.cell(row=3, column=i, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='E8EEF6')
        cell.alignment = Alignment(horizontal='center')
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    for r_i, r in enumerate(rows, 4):
        vals = [r['분류'], r['품목'], r['규격'], r['수수료']]
        for c_i, v in enumerate(vals, 1):
            cell = ws.cell(row=r_i, column=c_i, value=v)
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            if c_i == 4:
                if isinstance(v, int):
                    cell.number_format = '#,##0'
                cell.alignment = Alignment(horizontal='right')
    for col, w in zip('ABCD', (12, 34, 34, 14)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = 'A4'
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def xlsx_response(data, filename):
    from urllib.parse import quote
    return Response(data, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"})


@router.get('/confirmed/export.xlsx')
def confirmed_export(muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    name = store.q('SELECT name FROM municipality WHERE code=?', (muni,), one=True)['name']
    items = confirmed_list(muni, u)['items']
    rows = [{'분류': r['category'] or C.classify(r['item']), '품목': r['item'], '규격': r['spec'] or '모든규격',
             '수수료': r['method'] or r['fee']} for r in items]
    return xlsx_response(_xlsx_bytes(f'{name} 조례미등록품목 수수료책정내역', rows), f'{name}_조례미등록품목_수수료책정내역.xlsx')


def _read_table(data, filename):
    """엑셀(3행 머리행·4행부터) 또는 CSV → [{분류,품목,규격,수수료}]"""
    if filename.lower().endswith(('.xlsx', '.xlsm')):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), data_only=True)
        ws = wb.active
        grid = [[(c if c is not None else '') for c in row] for row in ws.iter_rows(values_only=True)]
    else:
        text = data.decode('utf-8-sig', errors='replace')
        grid = list(csv.reader(io.StringIO(text)))
    hdr_i = None
    for i, row in enumerate(grid[:12]):
        cells = [str(c).strip() for c in row]
        if '품목' in cells and any(x.startswith('수수료') for x in cells):
            hdr_i = i
            break
    if hdr_i is None:
        raise HTTPException(400, "머리행(품목·수수료)을 찾지 못했습니다. 3행 머리행 '분류 | 품목 | 규격 | 수수료(원)' 형식을 써 주세요")
    hdr = [str(c).strip() for c in grid[hdr_i]]
    col = lambda name: next((j for j, h in enumerate(hdr) if h.startswith(name)), None)
    ci, cs, cf, cc = col('품목'), col('규격'), col('수수료'), col('분류')
    out, errors = [], []
    for n, row in enumerate(grid[hdr_i + 1:], hdr_i + 2):
        get = lambda j: (str(row[j]).strip() if j is not None and j < len(row) and row[j] is not None else '')
        item = get(ci)
        if not item:
            continue
        fv = get(cf)
        fee = None if fv in METHODS else store.parse_fee(fv.split('.')[0] if re.fullmatch(r'\d+\.0', fv) else fv)
        if fv not in METHODS and not fee:
            errors.append(f'{n}행 수수료 없음: {item}')
            continue
        out.append({'분류': get(cc), '품목': item, '규격': get(cs) or '모든규격', 'fee': fee, 'method': fv if fv in METHODS else None})
    return out, errors


@router.post('/confirmed/import')
async def confirmed_import(file: UploadFile = File(...), muni: str = Form('gwacheon'), mode: str = Form('merge'),
                           dry: str = Form('1'), u=Depends(me)):
    _muni(muni)
    rows, errors = _read_table(await file.read(), file.filename or '')
    seen, dups = set(), []
    for r in rows:
        key = (r['품목'], r['규격'])
        if key in seen:
            dups.append(f"{r['품목']} / {r['규격']}")
        seen.add(key)
    bad_spec = [f"{r['품목']} / {r['규격']}" for r in rows if re.search(r'이하|초과', r['규격'])]
    cur = {(r['item'], r['spec']): r for r in store.q('SELECT * FROM confirmed WHERE muni=?', (muni,))}
    add = [r for r in rows if (r['품목'], r['규격']) not in cur]
    chg = [r for r in rows if (r['품목'], r['규격']) in cur and (cur[(r['품목'], r['규격'])]['fee'], cur[(r['품목'], r['규격'])]['method']) != (r['fee'], r['method'])]
    rem = [k for k in cur if k not in seen] if mode == 'replace' else []
    report = {'rows': len(rows), 'add': len(add), 'change': len(chg), 'remove': len(rem), 'errors': errors,
              'duplicates': dups, 'bad_spec': bad_spec, 'mode': mode,
              'sample_add': [f"{r['품목']} / {r['규격']} / {r['method'] or format(r['fee'], ',')}" for r in add[:15]],
              'sample_change': [f"{r['품목']} / {r['규격']}: {cur[(r['품목'], r['규격'])]['fee']} → {r['fee'] or r['method']}" for r in chg[:15]]}
    if dry == '1' or errors or dups or bad_spec:
        report['applied'] = False
        return report
    now = time.time()
    if mode == 'replace':
        store.x('DELETE FROM confirmed WHERE muni=?', (muni,))
        targets = rows
    else:
        targets = add + chg
        for r in chg:
            store.x('DELETE FROM confirmed WHERE muni=? AND item=? AND spec=?', (muni, r['품목'], r['규격']))
    store.xmany('INSERT INTO confirmed(muni,item,spec,fee,method,category,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)',
                [(muni, r['품목'], r['규격'], r['fee'], r['method'], r['분류'] or C.classify(r['품목']), now, u['n']) for r in targets])
    store.bump_version()
    store.log(u['n'], f'확정표 가져오기({mode})', file.filename, {'count': len(cur)}, {k: report[k] for k in ('rows', 'add', 'change', 'remove')})
    report['applied'] = True
    return report


# ---------------------------------------------------------------- 조례
@router.get('/ordinance')
def ordinance_get(muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    return {'items': store.q('SELECT item,spec,fee,disp_item,disp_spec FROM ordinance WHERE muni=? ORDER BY ord', (muni,)),
            'stats': S.stats(muni)}


@router.get('/ordinance/export.csv')
def ordinance_export(muni: str = 'gwacheon', u=Depends(me)):
    _muni(muni)
    bio = io.StringIO()
    w = csv.writer(bio)
    w.writerow(['품목', '규격', '수수료', '표시품목', '표시규격'])
    for r in store.q('SELECT item,spec,fee,disp_item,disp_spec FROM ordinance WHERE muni=? ORDER BY ord', (muni,)):
        w.writerow([r['item'], r['spec'], r['fee'], r['disp_item'], r['disp_spec']])
    from urllib.parse import quote
    return Response('﻿' + bio.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(muni + '_조례.csv')}"})


def _ordinance_preview(text, muni):
    rows, dropped = store.ordinance_rows_from_csv(text)
    lines = [l for l in csv.reader(io.StringIO(text.lstrip('﻿')))][1:]
    data_lines = [l for l in lines if any(str(c).strip() for c in l)]
    fee_cells = sum(1 for l in data_lines if len(l) >= 3 and store.parse_fee(l[2]))
    nat = S.ctx(S.municipalities()[0]['code']).nat if S.municipalities() else {}
    local = [{'name': r['item'], 'spec': r['spec'], 'fee': r['fee'], 'tok': E.tokens(r['item'])} for r in rows]
    k, kn, mad = E.calibrate(local, nat) if local else (1.0, 0, None)
    fees = [r['fee'] for r in rows]
    cur = {(r['item'], r['spec']): r['fee'] for r in store.q('SELECT item,spec,fee FROM ordinance WHERE muni=?', (muni,))}
    new = {(r['item'], r['spec']): r['fee'] for r in rows}
    return rows, {
        'data_lines': len(data_lines), 'rows': len(rows), 'fee_cells': fee_cells, 'dropped': dropped,
        'match': len(rows) == fee_cells,
        'grid': sorted(set(fees)), 'grid2': sorted({f for f in fees if fees.count(f) >= 2}),
        'k': round(k, 3), 'k_pairs': kn, 'mad': round(mad, 3) if mad is not None else None,
        'added': [f'{a} / {b} / {new[(a, b)]:,}' for a, b in new if (a, b) not in cur][:50],
        'removed': [f'{a} / {b} / {cur[(a, b)]:,}' for a, b in cur if (a, b) not in new][:50],
        'changed': [f'{a} / {b}: {cur[(a, b)]:,} → {new[(a, b)]:,}' for a, b in new if (a, b) in cur and cur[(a, b)] != new[(a, b)]][:50],
    }


@router.post('/ordinance')
async def ordinance_upload(file: UploadFile = File(...), muni: str = Form(...), name: str = Form(''), dry: str = Form('1'),
                           u=Depends(me)):
    muni = re.sub(r'[^a-z0-9_-]', '', muni.lower())
    if not muni:
        raise HTTPException(400, '지자체 코드는 영문 소문자·숫자로 적어 주세요(예: gwacheon)')
    raw = await file.read()
    if (file.filename or '').lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(raw), data_only=True).active
        bio = io.StringIO()
        csv.writer(bio).writerows([[('' if c is None else c) for c in r] for r in ws.iter_rows(values_only=True)])
        text = bio.getvalue()
    else:
        text = raw.decode('utf-8-sig', errors='replace')
    try:
        rows, report = _ordinance_preview(text, muni)
    except ValueError as e:
        raise HTTPException(400, str(e))
    exists = store.q('SELECT name FROM municipality WHERE code=?', (muni,), one=True)
    report['new_municipality'] = not exists
    if dry == '1':
        report['applied'] = False
        return report
    if not rows:
        raise HTTPException(400, '적용할 행이 없습니다')
    if not exists:
        if not name.strip():
            raise HTTPException(400, '새 지자체 이름을 입력해 주세요')
        store.x('INSERT INTO municipality(code,name,created_at) VALUES(?,?,?)', (muni, name.strip(), time.time()))
        store.set_setting(f'policy:{muni}', 'hold')
    old = store.q('SELECT COUNT(*) n FROM ordinance WHERE muni=?', (muni,), one=True)['n']
    store.save_ordinance(muni, rows)
    store.bump_version()
    store.log(u['n'], '조례 업로드', f'{muni} {file.filename}', {'rows': old}, {'rows': len(rows), 'k': report['k']})
    report['applied'] = True
    return report


# ---------------------------------------------------------------- 표현 사전
@router.get('/synonyms')
def synonyms(muni: str = 'gwacheon', u=Depends(me)):
    logs = store.q("SELECT * FROM expression WHERE muni=? ORDER BY (status='new') DESC, count DESC, updated_at DESC LIMIT 500", (muni,))
    by = {}
    for r in store.q('SELECT enorm, general FROM expression WHERE muni=?', (muni,)):
        by.setdefault(r['enorm'], set()).add(r['general'])
    for r in logs:
        r['single'] = len(by.get(r['enorm'], ())) == 1
        r['generals'] = sorted(by.get(r['enorm'], ()))
    return {'log': logs, 'dictionary': store.q('SELECT * FROM synonym ORDER BY id DESC'),
            'builtin': {'SYN': [f'{a}→{b}' for a, b in S.BASE_SYN], 'AMBIG': list(S.BASE_AMBIG), 'VAGUE': sorted(S.BASE_VAGUE),
                        'AMBIG_NOUNS': {k: v for k, v in C.AMBIG_NOUNS.items()}}}


@router.post('/synonyms')
async def synonym_add(request: Request, u=Depends(me)):
    b = await request.json()
    kind = b.get('kind')
    expr = str(b.get('expr') or '').strip()
    target = str(b.get('target') or '').strip()
    if kind not in ('SYN', 'AMBIG', 'VAGUE', 'HINT') or not S._raw_norm(expr):
        raise HTTPException(400, '종류(SYN·AMBIG·VAGUE·HINT)와 표현을 확인해 주세요')
    if kind in ('SYN', 'HINT') and not target:
        raise HTTPException(400, '대상 품목을 입력해 주세요')
    if kind == 'SYN' and len(S._raw_norm(expr)) < 2:
        raise HTTPException(400, '한 글자 표현은 다른 품목명 안에서도 바뀌므로 SYN으로 넣을 수 없습니다')
    sid = store.x('INSERT INTO synonym(kind,expr,target,by,at) VALUES(?,?,?,?,?)', (kind, expr, target, u['n'], time.time()))
    if b.get('log_id'):
        store.x("UPDATE expression SET status='approved' WHERE id=?", (b['log_id'],))
    store.bump_version()
    store.log(u['n'], f'표현 사전 추가({kind})', expr, None, {'target': target})
    return {'ok': True, 'id': sid}


@router.post('/synonyms/log/{lid}')
async def synonym_log_act(lid: int, request: Request, u=Depends(me)):
    b = await request.json()
    if b.get('action') != 'reject':
        raise HTTPException(400)
    store.x("UPDATE expression SET status='rejected' WHERE id=?", (lid,))
    store.log(u['n'], '표현 기록 보류', str(lid))
    return {'ok': True}


@router.delete('/synonyms/{sid}')
def synonym_delete(sid: int, u=Depends(me)):
    old = store.q('SELECT * FROM synonym WHERE id=?', (sid,), one=True)
    if not old:
        raise HTTPException(404)
    store.x('DELETE FROM synonym WHERE id=?', (sid,))
    store.bump_version()
    store.log(u['n'], f"표현 사전 삭제({old['kind']})", old['expr'], {'target': old['target']}, None)
    return {'ok': True}


# ---------------------------------------------------------------- 전국 통계
@router.get('/national')
def national(u=Depends(me)):
    tsv = store.get_setting('nat_tsv') or ''
    lines = [l.split('\t') for l in tsv.splitlines() if l.strip()]
    return {'updated': store.get_setting('nat_updated'), 'source': store.get_setting('nat_source'), 'items': len(lines),
            'top': [{'품목': l[0], '기관수': int(l[1]), '중앙값': float(l[2]), 'p25': float(l[3]), 'p75': float(l[4])} for l in lines[:400]]}


@router.post('/national/refresh')
def national_refresh(u=Depends(me)):
    try:
        return dict(natdata.refresh(u['n']), ok=True)
    except Exception as e:
        raise HTTPException(502, f'공공데이터포털에서 받지 못했습니다: {e}. 원본 JSON(rows)이나 요약 TSV를 직접 올릴 수 있습니다.')


@router.post('/national/upload')
async def national_upload(file: UploadFile = File(...), u=Depends(me)):
    raw = (await file.read()).decode('utf-8-sig', errors='replace')
    try:
        if raw.lstrip().startswith(('{', '[')):
            data = json.loads(raw)
            rows = data['rows'] if isinstance(data, dict) else data
            return dict(natdata.apply_rows(rows, u['n'], f'파일 업로드({file.filename})'), ok=True)
        return dict(natdata.apply_tsv(raw, u['n'], f'TSV 업로드({file.filename})'), ok=True)
    except Exception as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 이력·설정
@router.get('/history')
def history(limit: int = 300, u=Depends(me)):
    rows = store.q('SELECT * FROM history ORDER BY id DESC LIMIT ?', (min(limit, 2000),))
    for r in rows:
        for k in ('before', 'after'):
            r[k] = json.loads(r[k]) if r.get(k) else None
    return {'items': rows}


@router.post('/settings')
async def settings(request: Request, u=Depends(me)):
    b = await request.json()
    muni = _muni(b.get('muni') or 'gwacheon')
    pol = b.get('policy')
    if pol not in ('hold', 'show'):
        raise HTTPException(400, "policy 는 hold(확정 전 대기) 또는 show(바로 보여주기)")
    old = store.get_setting(f'policy:{muni}', 'hold')
    store.set_setting(f'policy:{muni}', pol)
    store.bump_version()
    store.log(u['n'], '공개 정책 변경', muni, {'policy': old}, {'policy': pol})
    return {'ok': True}
