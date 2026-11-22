"""조례 품목 고르기 AI (Vercel AI Gateway).
- 조례·확정표·같은 배출 항목으로도 못 찾은 이름만 묻는다.
- AI는 그 지자체 조례에 '실제로 있는 품목명' 중에서만 고른다. 금액은 AI가 정하지 않는다(엔진이 조례 금액을 쓴다).
- 고객에게는 '○○ 맞으신가요?'로 한 번 더 확인받는다.
- 인증: AI_GATEWAY_API_KEY(어디서나) 또는 Vercel 배포의 OIDC 토큰(환경변수 VERCEL_OIDC_TOKEN 또는 요청 헤더 x-vercel-oidc-token).
- 같은 지자체·같은 이름은 30일 캐시(인스턴스 로컬 SQLite).
"""
import json, os, re, time, urllib.request

from . import store

BASE = 'https://ai-gateway.vercel.sh/v1'
TIMEOUT = float(os.environ.get('AI_TIMEOUT', '8'))
TTL = 30 * 86400
PREFER = [m.strip() for m in os.environ.get('AI_MODEL', '').split(',') if m.strip()] + [
    'anthropic/claude-haiku-5.5', 'anthropic/claude-haiku-5', 'anthropic/claude-sonnet-5.5', 'anthropic/claude-sonnet-5',
    'anthropic/claude-haiku-4.5', 'anthropic/claude-sonnet-4.5', 'openai/gpt-5-mini', 'google/gemini-2.5-flash']

_HDR = {'token': '', 'at': 0.0}      # 마지막 요청 헤더의 OIDC 토큰
_MODEL = {'id': None, 'at': 0.0}
_TEST = []                            # 테스트에서 가짜 응답 함수를 끼워 넣는 자리
LAST = {'error': '', 'model': ''}


def remember_header_token(tok):
    if tok:
        _HDR.update(token=tok, at=time.time())


def _token():
    return os.environ.get('AI_GATEWAY_API_KEY') or os.environ.get('VERCEL_OIDC_TOKEN') or _HDR['token']


def available():
    return bool(_TEST) or bool(_token()) and os.environ.get('AI_DISABLED') != '1'


def _req(path, body=None, timeout=TIMEOUT):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method='POST' if body is not None else 'GET', headers={
        'Authorization': f'Bearer {_token()}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def model():
    if _MODEL['id'] and time.time() - _MODEL['at'] < 86400:
        return _MODEL['id']
    pick = PREFER[0]
    try:
        ids = {m.get('id') for m in _req('/models', timeout=5).get('data', [])}
        pick = next((m for m in PREFER if m in ids), None) or next(
            (i for i in sorted(ids) if i.startswith('anthropic/claude-haiku')), PREFER[0])
    except Exception as e:  # 목록을 못 받으면 첫 후보로 시도
        LAST['error'] = f'models: {e}'
    _MODEL.update(id=pick, at=time.time())
    return pick


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
            m = model()
            LAST['model'] = m
            out = _req('/chat/completions', {'model': m, 'max_tokens': 200, 'temperature': 0,
                                             'messages': [{'role': 'user', 'content': prompt}]})
            text = out['choices'][0]['message']['content'] or ''
        js = json.loads(re.search(r'\{.*\}', text, re.S).group(0))
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
