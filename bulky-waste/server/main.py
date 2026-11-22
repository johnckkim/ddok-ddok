"""FastAPI 앱: 고객 화면(공개) + 운영자 화면(로그인).
고객 API 응답에는 근거 필드가 없다 — service.quote/confirm/ticket 이 만든 dict만 그대로 내보낸다."""
import csv, io, os, re, threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response

from . import admin, ai, service as S, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, 'web')

app = FastAPI(title='대형폐기물 수수료 안내', docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(admin.router)

_init_lock = threading.Lock()
_ready = [False]


def ensure_ready():
    if _ready[0]:
        return
    with _init_lock:
        if not _ready[0]:
            store.init()
            _ready[0] = True


from .ratelimit import rate_limit  # noqa: E402
from .tokens import text_tag, text_tag_ok  # noqa: E402


async def _body(request):
    """JSON 객체 본문만 받는다(배열·깨진 글이면 400)."""
    try:
        b = await request.json()
    except Exception:
        raise HTTPException(400, '요청 형식을 확인해 주세요')
    if not isinstance(b, dict):
        raise HTTPException(400, '요청 형식을 확인해 주세요')
    return b


_CATS = {'가구류', '가전·전자', '생활용품', '유아용품', '반려동물', '운동·레저', '악기·취미', '사무·기타', '목재', '기타'}


def _tag_texts(j):
    """고객 응답 속 번역할 만한 글마다 서명을 붙인다(tk). 번역 캐시는 이 서명이 맞는 글만 받는다."""
    if not isinstance(j, dict):
        return j
    out = set()
    add = lambda s: out.add(s) if isinstance(s, str) and s.strip() and len(s) <= 300 else None
    for r in j.get('rows') or []:
        for k in ('품목', '규격', '안내', '수수료'):
            add(r.get(k))
    for x in (j.get('pending') or []) + (j.get('closed') or []):
        add(x)
    cards = list(j.get('needs_confirm') or []) + ([j['card']] if isinstance(j.get('card'), dict) else [])
    for c in cards:
        add(c.get('item_label')); add(c.get('question'))
        for s in c.get('size_options') or []:
            add(s)
        for o in c.get('options') or []:
            add(o.get('label')); add(o.get('desc'))
        if isinstance(c.get('product'), dict):
            add(c['product'].get('title'))
    add(j.get('message')); add(j.get('municipality'))
    j['tk'] = {s: text_tag(s) for s in out}
    return j


SEC_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'X-Frame-Options': 'DENY',
    'Permissions-Policy': 'camera=(self), microphone=(), geolocation=()',
    'Content-Security-Policy': "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
}


@app.middleware('http')
async def lifecycle(request: Request, call_next):
    if request.url.path.startswith('/static/'):          # 정적 파일은 DB 준비·동기화가 필요 없다
        resp = await call_next(request)
        for k, v in SEC_HEADERS.items():
            resp.headers.setdefault(k, v)
        return resp
    await run_in_threadpool(ensure_ready)
    ai.remember_header_token(request.headers.get('x-vercel-oidc-token'))
    path = request.url.path
    if path.startswith('/api/'):
        force = path.startswith('/api/admin/') and request.method != 'GET'
        await run_in_threadpool(store.SYNC.pull, force)
    before = store.writes()
    resp = await call_next(request)
    if store.writes() != before:
        await run_in_threadpool(store.SYNC.push)
    for k, v in SEC_HEADERS.items():
        resp.headers.setdefault(k, v)
    if path.startswith('/api/'):
        resp.headers.setdefault('Cache-Control', 'no-store')
    return resp


@app.exception_handler(HTTPException)
async def http_err(request: Request, exc: HTTPException):
    return JSONResponse({'status': 'error', 'message': exc.detail}, status_code=exc.status_code, headers=SEC_HEADERS)


# ---------------------------------------------------------------- 고객 API
@app.get('/api/municipalities')
def municipalities():
    return {'items': S.municipalities()}


def _muni_ok(m):
    if not any(x['code'] == m for x in S.municipalities()):
        raise HTTPException(404, '지자체를 찾을 수 없습니다')


@app.post('/api/quote')
async def quote(request: Request):
    rate_limit(request, 'quote')
    b = await _body(request)
    muni = str(b.get('municipality') or 'gwacheon')
    items = b.get('items') or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, '품목 이름을 입력해 주세요')
    await run_in_threadpool(_muni_ok, muni)
    return _tag_texts(await run_in_threadpool(S.quote, muni, items))


_EXAMPLES = ['소파', '냉장고', '식기세척기', '캣타워', '전동킥보드', '매트리스', '책상', '세탁기', '장롱', '의자', '자전거', '에어컨',
             '식탁', '서랍장', 'TV', '책장', '유모차', '침대']
_EX_CACHE = {}


@app.get('/api/examples')
def examples(request: Request, m: str = ''):
    """그 지역에서 실제로 금액이 바로 나오는 품목만 예시 단추로(답 못 하는 예시 금지)."""
    rate_limit(request, 'quote')
    _muni_ok(m)
    key = (m, store.get_setting('data_version', '0'))
    if key not in _EX_CACHE:
        c = S.ctx(m)
        ok = []
        for q in _EXAMPLES:
            try:
                r = S.resolve(c, q)
            except Exception:
                continue
            if r['kind'] == 'rows' and r['rows'] and not r.get('review') and any(o.get('fee') for o in r['rows']):
                ok.append(q)
            if len(ok) >= 6:
                break
        _EX_CACHE[key] = ok
    return {'items': _EX_CACHE[key]}


@app.post('/api/translate')
async def translate(request: Request):
    """화면 글 번역(우리동네플러스 지원 언어). {lang, texts[]} → {texts[]}. 실패한 칸은 원문 그대로."""
    rate_limit(request, 'translate')
    b = await _body(request)
    lang = str(b.get('lang') or '')
    texts = b.get('texts') or []
    tags = b.get('tk') if isinstance(b.get('tk'), dict) else {}
    if lang not in ai.LANGS or not isinstance(texts, list):
        raise HTTPException(400, 'lang, texts 를 확인해 주세요')
    texts = [str(t)[:300] for t in texts[:60] if isinstance(t, (str, int, float))]
    names = {m['name'] for m in S.municipalities()}
    trusted = {t for t in texts if lang != 'ko' and (t in names or t in _CATS or text_tag_ok(t, tags.get(t)))}
    return {'texts': await run_in_threadpool(ai.translate, texts, lang, trusted)}


@app.post('/api/confirm/{card_id}')
async def confirm(card_id: str, request: Request):
    rate_limit(request, 'confirm')
    b = await _body(request)
    return _tag_texts(await run_in_threadpool(S.confirm, card_id, b.get('answer'), b.get('choice'), b.get('size'), b.get('text'),
                                              b.get('photo'), b.get('dims') if isinstance(b.get('dims'), dict) else None))


@app.get('/api/ticket/{tid}')
def ticket(tid: str, request: Request):
    rate_limit(request, 'ticket')
    t = S.ticket(tid)
    if not t:
        raise HTTPException(404, '접수번호를 찾을 수 없습니다')
    return _tag_texts(t)


@app.post('/api/ticket/{tid}/contact')
async def ticket_contact(tid: str, request: Request):
    rate_limit(request, 'contact')
    b = await request.json()
    r = await run_in_threadpool(S.save_contact, tid, b.get('name'), b.get('phone'), b.get('agree'))
    if r['status'] != 'ok':
        raise HTTPException(400, r['message'])
    return r


@app.post('/api/quote/export')
async def quote_export(request: Request):
    """화면에 받은 고객용 칸(품목·규격·수수료·배출 안내, 장바구니면 수량·금액)만 CSV/엑셀로 담는다(다른 칸은 버림)."""
    rate_limit(request, 'quote')
    b = await _body(request)
    rows = b.get('rows') or []
    if not isinstance(rows, list):
        raise HTTPException(400, '요청 형식을 확인해 주세요')
    fmt = b.get('format', 'csv')
    cart = any('수량' in r for r in rows[:300] if isinstance(r, dict))

    def won(fee):
        return int(fee.replace(',', '').replace('원', '')) if re.fullmatch(r'[\d,]+원', fee) else None

    head = ['품목', '규격', '수수료', '배출 안내'] + (['수량', '금액'] if cart else [])
    clean, total = [], 0
    for r in rows[:300]:
        if not isinstance(r, dict):
            continue
        row = [str(r.get(k) or '')[:80] for k in ('품목', '규격', '수수료', '안내')]
        if cart:
            try:
                qty = max(1, min(99, int(r.get('수량') or 1)))
            except (TypeError, ValueError):
                qty = 1
            fee = won(row[2])
            amt = fee * qty if fee is not None else None
            total += amt or 0
            row += [qty, amt]
        clean.append(row)
    if fmt == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        wb = Workbook()
        ws = wb.active
        ws.title = '장바구니' if cart else '수수료'
        ws.append(head)
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in clean:
            num = won(r[2])
            ws.append([r[0], r[1], num if num is not None else r[2], r[3]] + (r[4:] if cart else []))
            cells = [ws.cell(row=ws.max_row, column=3)] + ([ws.cell(row=ws.max_row, column=6)] if cart else [])
            for cell in cells:
                if isinstance(cell.value, int):
                    cell.number_format = '#,##0"원"'
                cell.alignment = Alignment(horizontal='right')
        if cart:
            ws.append(['합계', '', '', '', '', total])
            last = ws.max_row
            ws.cell(row=last, column=1).font = Font(bold=True)
            c = ws.cell(row=last, column=6)
            c.font = Font(bold=True)
            c.number_format = '#,##0"원"'
        for col, w in zip('ABCDEF', (28, 30, 14, 30, 8, 14)):
            ws.column_dimensions[col].width = w
        bio = io.BytesIO()
        wb.save(bio)
        return admin.xlsx_response(bio.getvalue(), '대형폐기물_수수료.xlsx')
    bio = io.StringIO()
    w = csv.writer(bio)
    w.writerow(head)
    w.writerows([[('' if v is None else v) for v in r] for r in clean])
    if cart:
        w.writerow(['합계', '', '', '', '', total])
    return Response('﻿' + bio.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': "attachment; filename*=UTF-8''%EB%8C%80%ED%98%95%ED%8F%90%EA%B8%B0%EB%AC%BC_%EC%88%98%EC%88%98%EB%A3%8C.csv"})


@app.get('/api/health')
def health():
    return {'ok': True, 'sync': store.SYNC.enabled, 'sync_ok': store.SYNC.error is None,
            'restored': store.SYNC.current is not None}


@app.get('/api/quote')
def quote_get(request: Request, q: str = '', m: str = 'gwacheon'):
    """공유 링크용: /api/quote?q=식기세척기,캣타워 (POST /api/quote 와 같은 응답)"""
    rate_limit(request, 'quote')
    names = [x.strip() for x in re.split(r'[,\n]', q) if x.strip()]
    if not names:
        raise HTTPException(400, '품목 이름을 입력해 주세요')
    _muni_ok(m)
    return _tag_texts(S.quote(m, [{'name': n} for n in names]))


@app.get('/api/cron/import')
def cron_import(request: Request, key: str = '', targets: str = '', dry: str = '1', mode: str = '', force: str = '0', only: str = ''):
    """운영 배치용(비밀키 필요): 공공데이터 지자체 수수료표 가져오기. mode=columns 면 원본 칸 구성만."""
    secret = os.environ.get('CRON_SECRET')
    if not secret or not (key == secret or request.headers.get('authorization') == f'Bearer {secret}'):
        raise HTTPException(401, 'unauthorized')
    from . import importer, natdata
    if mode == 'collected':
        return importer.import_collected(os.path.join(ROOT, 'data', 'collected'), '배치', force=force == '1', dry=dry == '1',
                                         only={x.strip() for x in only.split(',') if x.strip()} or None)
    rows = natdata.cached_rows()
    if mode == 'columns':
        return importer.columns_preview(rows)
    if mode == 'national':
        return natdata.apply_rows(rows, '배치', '공공데이터포털 15114146')
    return importer.run(rows, importer.parse_targets(targets), '배치', force=force == '1', dry=dry == '1')


def _cron_ok(request, key):
    secret = os.environ.get('CRON_SECRET')
    return bool(secret) and (key == secret or request.headers.get('authorization') == f'Bearer {secret}')


@app.get('/api/cron/ai')
def cron_ai(request: Request, key: str = '', q: str = '베드 범퍼', m: str = 'seoul-eunpyeong', models: str = ''):
    """AI 연결 점검(운영자용): 모델·고른 품목·오류."""
    if not _cron_ok(request, key):
        raise HTTPException(403, '권한이 없습니다')
    c = S.ctx(m)
    names = [x['disp_item'] or x['name'] for x in c.local]
    if models:   # 모델별 시험: 각 모델이 고른 품목·걸린 시간
        out = {}
        for mm in [x.strip() for x in models.split(',') if x.strip()][:6]:
            t0 = __import__('time').time()
            try:
                out[mm] = [ai._chat(ai.PROMPT.format(item=q, muni=c.name, names='\n'.join(dict.fromkeys(names))), only=[mm], budget=25)[:300],
                           round(__import__('time').time() - t0, 1)]
            except Exception as e:
                out[mm] = [str(e)[:300], round(__import__('time').time() - t0, 1)]
        return out
    picks = ai.pick_items(c.muni, c.name, q, names) if names else []
    return {'available': ai.available(), 'model': ai.LAST.get('model') or ai._MODEL.get('id'), 'picks': picks,
            'skipped': sorted(ai._MODEL.get('bad') or []), 'tries': ai.LAST.get('tries'), 'candidates': (ai._MODEL.get('list') or [])[:30],
            'error': ai.LAST.get('error'), 'anthropic_key': bool(os.environ.get('ANTHROPIC_API_KEY')),
            'anthropic': ai.LAST.get('anthropic'), 'quote': S.quote(m, [{'name': q}])}


@app.get('/api/cron/national')
def cron_national(request: Request):
    secret = os.environ.get('CRON_SECRET')
    if not secret or request.headers.get('authorization') != f'Bearer {secret}':
        raise HTTPException(401, 'unauthorized')
    from . import natdata
    try:
        return dict(natdata.refresh('정기 갱신'), ok=True)
    except Exception as e:
        store.log('정기 갱신', '전국 통계 갱신 실패', str(e)[:300])
        raise HTTPException(502, str(e)[:300])


# ---------------------------------------------------------------- 화면
def _page(name, cache='no-cache'):
    return FileResponse(os.path.join(WEB, name), headers={'Cache-Control': cache})


@app.api_route('/', methods=['GET', 'HEAD'])
def home():
    return _page('index.html')


@app.get('/admin')
def admin_page():
    return _page('admin.html')


_STATIC = {'app.js', 'i18n.js', 'admin.js', 'style.css', 'admin.css', 'udong.png', 'udong-512.png'}


@app.api_route('/static/{name}', methods=['GET', 'HEAD'])
def static(name: str, request: Request):
    if name not in _STATIC or not os.path.exists(os.path.join(WEB, name)):
        raise HTTPException(404)
    # ?v= 가 붙은 파일은 내용이 바뀌면 v 가 바뀌므로 오래 캐시
    return _page(name, 'public, max-age=31536000, immutable' if request.query_params.get('v') else 'public, max-age=300')
