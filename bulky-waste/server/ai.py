"""조례 품목 고르기 AI (Vercel AI Gateway).
- 조례·확정표·같은 배출 항목으로도 못 찾은 이름만 묻는다.
- AI는 그 지자체 조례에 '실제로 있는 품목명' 중에서만 고른다. 금액은 AI가 정하지 않는다(엔진이 조례 금액을 쓴다).
- 고객에게는 '○○ 맞으신가요?'로 한 번 더 확인받는다.
- 인증: AI_GATEWAY_API_KEY(어디서나) 또는 Vercel 배포의 OIDC 토큰(환경변수 VERCEL_OIDC_TOKEN 또는 요청 헤더 x-vercel-oidc-token).
- 같은 지자체·같은 이름은 30일 캐시(인스턴스 로컬 SQLite).
"""
import json, os, re, time, urllib.error, urllib.request

from . import store

BASE = 'https://ai-gateway.vercel.sh/v1'
TIMEOUT = float(os.environ.get('AI_TIMEOUT', '11'))
TTL = 30 * 86400
PREFER = [m.strip() for m in os.environ.get('AI_MODEL', '').split(',') if m.strip()] + [
    'anthropic/claude-haiku-5.5', 'anthropic/claude-haiku-4.5', 'anthropic/claude-sonnet-5.5',   # 유료 크레딧이 있을 때
    'google/gemini-2.5-flash', 'openai/gpt-5-mini']                                             # 무료 등급에서 확인된 모델
# google/gemini-2.5-flash-lite 는 무료지만 '베드 범퍼'에 '침대'를 고르는 등 판단이 약해 쓰지 않는다.

_HDR = {'token': '', 'at': 0.0}      # 마지막 요청 헤더의 OIDC 토큰
_MODEL = {'id': None, 'at': 0.0, 'list': None}
_TEST = []                            # 테스트에서 가짜 응답 함수를 끼워 넣는 자리
LAST = {'error': '', 'model': '', 'tries': []}


def remember_header_token(tok):
    if tok:
        _HDR.update(token=tok, at=time.time())


def _token():
    return os.environ.get('AI_GATEWAY_API_KEY') or os.environ.get('VERCEL_OIDC_TOKEN') or _HDR['token']


def available():
    return bool(_TEST) or bool(_token() or os.environ.get('ANTHROPIC_API_KEY')) and os.environ.get('AI_DISABLED') != '1'


def _req(path, body=None, timeout=TIMEOUT):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method='POST' if body is not None else 'GET', headers={
        'Authorization': f'Bearer {_token()}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


CHEAP = ('haiku', 'flash', 'mini')


def candidates():
    """쓸 모델 후보(앞에서부터 시도). 무료 등급에서 막힌 모델은 건너뛴다."""
    if _MODEL.get('list') and time.time() - _MODEL['at'] < 86400:
        return _MODEL['list']
    ids = []
    try:
        data = _req('/models', timeout=5).get('data', [])
        ids = [m.get('id') for m in data if m.get('id') and (m.get('type') in (None, 'language'))]
    except Exception as e:
        LAST['error'] = f'models: {e}'
    pref = [m for m in PREFER if not ids or m in ids]
    cheap = [i for i in ids if i not in pref and any(k in i.lower() for k in CHEAP)
             and not any(k in i.lower() for k in ('embed', 'image', 'tts', 'whisper', 'vision', 'lite', 'nano', 'batch', 'omni', 'fast'))]
    lst = pref + sorted(cheap, key=lambda i: (0 if 'haiku' in i else 1 if 'flash' in i else 2 if 'mini' in i else 3, i))
    _MODEL.update(list=lst, at=time.time())
    return lst


def model():
    return _MODEL.get('id') or (candidates() or PREFER)[0]


def _anthropic(prompt):
    """ANTHROPIC_API_KEY 가 있으면 Claude API를 바로 쓴다(빠르고 판단이 좋다)."""
    m = os.environ.get('ANTHROPIC_MODEL', 'claude-haiku-5-5')
    req = urllib.request.Request('https://api.anthropic.com/v1/messages', method='POST', data=json.dumps({
        'model': m, 'max_tokens': 1024, 'thinking': {'type': 'disabled'}, 'messages': [{'role': 'user', 'content': prompt}]}).encode(),
        headers={'x-api-key': os.environ['ANTHROPIC_API_KEY'], 'anthropic-version': '2023-06-01', 'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        out = json.loads(r.read().decode('utf-8'))
    LAST['model'] = m
    return ''.join(b.get('text', '') for b in out.get('content', []) if b.get('type') == 'text')


def _chat(prompt, only=None, budget=None):
    if os.environ.get('ANTHROPIC_API_KEY') and not only:
        try:
            out = _anthropic(prompt)
            LAST['anthropic'] = 'ok'
            return out
        except Exception as e:      # 실패하면 AI Gateway 로(이유는 점검 화면에 남긴다)
            body = ''
            try:
                body = e.read().decode('utf-8', 'replace')[:200] if hasattr(e, 'read') else ''
            except Exception:
                pass
            LAST['error'] = LAST['anthropic'] = f'anthropic: {type(e).__name__}: {e} {body}'[:300]
    return _gateway(prompt, only, budget)


def _gateway(prompt, only=None, budget=None):
    """되는 모델을 찾을 때까지 차례로 시도(무료 등급 제한·빈 답·시간 초과는 다음으로). 되는 모델은 기억한다.
    전체 대기 시간은 budget초를 넘기지 않는다."""
    order = only or (([_MODEL['id']] if _MODEL.get('id') else []) + [m for m in candidates() if m != _MODEL.get('id')])
    bad = _MODEL.setdefault('bad', set())
    slow = _MODEL.setdefault('slow', {})
    tries = LAST['tries'] = []
    t_end = time.time() + (budget or float(os.environ.get('AI_BUDGET', '14')))
    last = None
    for m in [m for m in order if only or (m not in bad and slow.get(m, 0) < 2)][:12]:
        left = t_end - time.time()
        if left < 2:
            break
        t0 = time.time()
        try:
            out = _req('/chat/completions', {'model': m, 'max_tokens': 1500, 'temperature': 0,
                                             'messages': [{'role': 'user', 'content': prompt}]}, timeout=left if only else min(TIMEOUT, left))
            text = out['choices'][0]['message'].get('content') or ''
            tries.append((m, round(time.time() - t0, 1), 'ok' if text.strip() else 'empty'))
            if not text.strip():
                last = f'{m}: 빈 답'
                bad.add(m)
                continue
            _MODEL['id'] = m
            LAST['model'] = m
            return text
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'replace')[:300]
            tries.append((m, round(time.time() - t0, 1), f'HTTP {e.code} {body[:120]}'))
            last = f'{m}: HTTP {e.code} {body}'
            if e.code in (400, 403, 404) and ('model' in body.lower() or 'provider' in body.lower() or 'tier' in body.lower()):
                bad.add(m)
                if _MODEL.get('id') == m:
                    _MODEL['id'] = None
                continue
            if e.code == 429:
                continue
            raise RuntimeError(last)
        except Exception as e:          # 시간 초과·연결 오류 → 다음 모델(두 번 느리면 빼 둔다)
            tries.append((m, round(time.time() - t0, 1), f'{type(e).__name__}'))
            last = f'{m}: {type(e).__name__}: {e}'
            slow[m] = slow.get(m, 0) + 1
            if _MODEL.get('id') == m:
                _MODEL['id'] = None
            continue
    raise RuntimeError(last or '쓸 수 있는 모델이 없습니다')


def _cache(key, val=None):
    try:
        if val is None:
            r = store.q('SELECT value, at FROM shopcache WHERE key=?', (key,), one=True)
            return json.loads(r['value']) if r and time.time() - r['at'] < TTL else None
        with store.LOCK:
            c = store.conn()
            c.execute('INSERT INTO shopcache(key,value,at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, at=excluded.at',
                      (key, json.dumps(val, ensure_ascii=False), time.time()))
            c.commit()
    except Exception:
        return None


PROMPT = """너는 한국 지자체 대형폐기물 배출 안내 담당자다.
고객이 버리려는 물건: "{item}"
지자체: {muni}
아래는 이 지자체 대형폐기물 수수료 조례에 있는 품목명 목록이다(한 줄에 하나).
---
{names}
---
이 물건을 내놓을 때 스티커를 붙이는 품목을 목록에서 골라라.
- 반드시 목록에 있는 품목명을 글자 그대로 쓴다. 목록에 없는 이름은 쓰지 않는다.
- 가장 알맞은 것부터 최대 3개. 물건의 재질·크기·쓰임이 같은 품목을 고른다.
- 재질이 다른 품목은 고르지 않는다(예: 천·솜·스펀지 물건에 목재·플라스틱 품목 X).
- '기타 ○○' 같은 묶음 품목은 재질이 맞고 다른 알맞은 품목이 없을 때만 쓴다.
- 대형폐기물이 아니거나(종량제 봉투·재활용) 알맞은 품목이 없으면 빈 배열.
JSON 한 줄로만 답한다: {{"items": ["품목명", ...], "what": "이 물건이 무엇인지 10자 안팎"}}"""


def pick_items(muni_key, muni_name, item, names):
    """조례 품목명 목록(names) 중 item 을 배출할 품목 0~3개. 실패·불가면 []."""
    names = [n for n in dict.fromkeys(n.strip() for n in names) if n][:400]
    if not names or not available():
        return []
    key = 'ai:' + muni_key + ':' + re.sub(r'\s+', '', item.lower())
    hit = _cache(key)
    if hit is not None:
        return [n for n in hit if n in names]
    prompt = PROMPT.format(item=item, muni=muni_name, names='\n'.join(names))
    try:
        if _TEST:
            text = _TEST[0](prompt)
        else:
            text = _chat(prompt)
        mt = re.search(r'\{.*\}', text or '', re.S)
        if not mt:
            raise ValueError(f'JSON 없음: {str(text)[:120]!r}')
        js = json.loads(mt.group(0))
        got = [n for n in (js.get('items') or []) if isinstance(n, str) and n in names][:3]
        LAST['error'] = ''
    except Exception as e:
        body = ''
        try:
            body = e.read().decode('utf-8', 'replace')[:400] if hasattr(e, 'read') else ''
        except Exception:
            pass
        LAST['error'] = f'{type(e).__name__}: {e} {body}'[:600]
        return []
    _cache(key, got)
    return got
