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
    b = await request.json()
    muni = str(b.get('municipality') or 'gwacheon')
    items = b.get('items') or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, '품목 이름을 입력해 주세요')
    await run_in_threadpool(_muni_ok, muni)
    return await run_in_threadpool(S.quote, muni, items)


@app.post('/api/confirm/{card_id}')
async def confirm(card_id: str, request: Request):
    rate_limit(request, 'confirm')
    b = await request.json()
    return await run_in_threadpool(S.confirm, card_id, b.get('answer'), b.get('choice'), b.get('size'), b.get('text'),
                                   b.get('photo'), b.get('dims') if isinstance(b.get('dims'), dict) else None)


@app.get('/api/ticket/{tid}')
def ticket(tid: str, request: Request):
    rate_limit(request, 'ticket')
    t = S.ticket(tid)
    if not t:
        raise HTTPException(404, '접수번호를 찾을 수 없습니다')
    return t


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
    b = await request.json()
    rows = b.get('rows') or []
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
    return S.quote(m, [{'name': n} for n in names])


@app.get('/api/cron/import')
def cron_import(request: Request, key: str = '', targets: str = '', dry: str = '1', mode: str = '', force: str = '0'):
    """운영 배치용(비밀키 필요): 공공데이터 지자체 수수료표 가져오기. mode=columns 면 원본 칸 구성만."""
    secret = os.environ.get('CRON_SECRET')
    if not secret or not (key == secret or request.headers.get('authorization') == f'Bearer {secret}'):
        raise HTTPException(401, 'unauthorized')
    from . import importer, natdata
    if mode == 'collected':
        return importer.import_collected(os.path.join(ROOT, 'data', 'collected'), '배치', force=force == '1', dry=dry == '1')
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


@app.get('/')
def home():
    return _page('index.html')


@app.get('/admin')
def admin_page():
    return _page('admin.html')


_STATIC = {'app.js', 'admin.js', 'style.css', 'admin.css', 'udong.png', 'udong-512.png', 'manifest.webmanifest'}


@app.get('/static/{name}')
def static(name: str):
    if name not in _STATIC:
        raise HTTPException(404)
    return _page(name, 'public, max-age=300')
