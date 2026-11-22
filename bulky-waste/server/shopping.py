"""쇼핑몰 상품 검색 Provider (HANDOFF 5-1).
- 크롤링하지 않는다. 공식 API만: 네이버 검색 API(쇼핑), 쿠팡 파트너스 Open API.
- 키는 환경변수. 둘 다 없거나 실패하면 None → 호출 측이 '자주 쓰는 후보'로 대체한다.
- 질의어 기준 24시간 캐시(인스턴스 로컬 SQLite, 원격 동기화 대상 아님).
- 가격·판매처는 받더라도 버린다(고객에게 보이지 않게 아예 저장하지 않음).
"""
import hashlib, hmac, html, json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone

from . import store

TTL = 24 * 3600
TIMEOUT = float(os.environ.get('SHOP_TIMEOUT', '4'))


class Product(dict):
    """{title, image, link, path:[카테고리...], leaf}"""


def _clean(t):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', str(t or '')))).strip()


class ShoppingProvider:
    name = 'base'

    def available(self):
        return False

    def search(self, query):
        raise NotImplementedError


class NaverShopping(ShoppingProvider):
    """GET https://openapi.naver.com/v1/search/shop.json  헤더 X-Naver-Client-Id / X-Naver-Client-Secret
    응답 items[]: title, link, image, lprice, brand, maker, category1~4"""
    name = 'naver'

    def available(self):
        return bool(os.environ.get('NAVER_CLIENT_ID') and os.environ.get('NAVER_CLIENT_SECRET'))

    def search(self, query):
        url = 'https://openapi.naver.com/v1/search/shop.json?' + urllib.parse.urlencode(
            {'query': query, 'display': 20, 'sort': 'sim'})
        req = urllib.request.Request(url, headers={
            'X-Naver-Client-Id': os.environ['NAVER_CLIENT_ID'],
            'X-Naver-Client-Secret': os.environ['NAVER_CLIENT_SECRET']})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode('utf-8'))
        out = []
        for it in data.get('items', []):
            path = [_clean(it.get(f'category{i}')) for i in range(1, 5)]
            path = [p for p in path if p]
            out.append(Product(title=_clean(it.get('title')), image=it.get('image') or '', link=it.get('link') or '',
                               path=path, leaf=path[-1] if path else ''))
        return out


class CoupangPartners(ShoppingProvider):
    """쿠팡 파트너스 Open API 상품 검색(파트너 승인·호출 한도 있음).
    GET /v2/providers/affiliate_open_api/apis/openapi/products/search?keyword=..&limit=..
    Authorization: CEA algorithm=HmacSHA256, access-key=.., signed-date=yyMMddTHHmmssZ, signature=hex(HMAC(secret, date+method+path+query))
    응답 data.productData[]: productName, productImage, productUrl, categoryName"""
    name = 'coupang'
    HOST = 'https://api-gateway.coupang.com'
    PATH = '/v2/providers/affiliate_open_api/apis/openapi/products/search'

    def available(self):
        return bool(os.environ.get('COUPANG_ACCESS_KEY') and os.environ.get('COUPANG_SECRET_KEY'))

    def search(self, query):
        qs = urllib.parse.urlencode({'keyword': query, 'limit': 10})
        dt = datetime.now(timezone.utc).strftime('%y%m%dT%H%M%SZ')
        msg = dt + 'GET' + self.PATH + qs
        sig = hmac.new(os.environ['COUPANG_SECRET_KEY'].encode(), msg.encode(), hashlib.sha256).hexdigest()
        auth = f"CEA algorithm=HmacSHA256, access-key={os.environ['COUPANG_ACCESS_KEY']}, signed-date={dt}, signature={sig}"
        req = urllib.request.Request(f'{self.HOST}{self.PATH}?{qs}', headers={'Authorization': auth})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode('utf-8'))
        out = []
        for it in (data.get('data') or {}).get('productData', []) or []:
            leaf = _clean(it.get('categoryName'))
            out.append(Product(title=_clean(it.get('productName')), image=it.get('productImage') or '',
                               link=it.get('productUrl') or '', path=[leaf] if leaf else [], leaf=leaf))
        return out


PROVIDERS = [NaverShopping(), CoupangPartners()]
_TEST_PROVIDER = []   # 테스트에서 가짜 Provider를 끼워 넣는 자리


def providers():
    return _TEST_PROVIDER or [p for p in PROVIDERS if p.available()]


def _cache_get(key):
    try:
        r = store.q('SELECT value, at FROM shopcache WHERE key=?', (key,), one=True)
        if r and time.time() - r['at'] < TTL:
            return [Product(x) for x in json.loads(r['value'])]
    except Exception:
        pass
    return None


def _cache_put(key, items):
    try:
        with store.LOCK:
            c = store.conn()
            c.execute('INSERT INTO shopcache(key,value,at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, at=excluded.at',
                      (key, json.dumps(items, ensure_ascii=False), time.time()))
            c.commit()           # 캐시는 원격 동기화 대상이 아니므로 mark_dirty 하지 않는다
    except Exception:
        pass


def search(query):
    """[Product] 또는 None(쓸 수 있는 Provider 없음/모두 실패)."""
    ps = providers()
    if not ps:
        return None
    key = 'q:' + re.sub(r'\s+', ' ', query.strip().lower())
    cached = _cache_get(key)
    if cached is not None:
        return cached
    for p in ps:
        try:
            items = p.search(query)
            if items:
                _cache_put(key, items)
                return items
        except Exception:
            continue
    return None


def status():
    return [{'name': p.name, 'available': p.available()} for p in PROVIDERS]
