"""요청 속도 제한(인스턴스별 메모리). 서버리스에서는 인스턴스마다 따로 센다."""
import collections, os, time

from fastapi import HTTPException

_HITS = collections.defaultdict(collections.deque)
LIMITS = {'quote': (40, 60), 'confirm': (40, 60), 'login': (10, 600), 'ticket': (60, 60)}


def client_ip(request):
    fwd = request.headers.get('x-forwarded-for', '')
    return (fwd.split(',')[0].strip() if fwd else '') or (request.client.host if request.client else '?')


def rate_limit(request, bucket):
    n, win = LIMITS[bucket]
    n = int(n * float(os.environ.get('RATE_LIMIT_SCALE', '1')))
    key = (bucket, client_ip(request))
    now = time.time()
    dq = _HITS[key]
    while dq and now - dq[0] > win:
        dq.popleft()
    if len(dq) >= n:
        raise HTTPException(429, '요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.')
    dq.append(now)
    if len(_HITS) > 20000:
        _HITS.clear()


