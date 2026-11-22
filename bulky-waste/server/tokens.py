"""서명 토큰: 확인 카드 상태·운영자 세션을 서버 저장 없이 주고받는다(여러 인스턴스에서도 동작).
본문은 zlib 압축 후 base32 소문자(패딩 없음)로 싣는다 → 고객 응답 금지어 정규식(대문자 L·숫자, '=')에 걸리지 않는다."""
import base64, hashlib, hmac, json, os, secrets, time, zlib


def _secret():
    s = os.environ.get('SECRET_KEY')
    if s:
        return s.encode()
    seed = os.environ.get('ADMIN_PASSWORD') or os.environ.get('ADMIN_USERS')
    if seed:  # 인스턴스가 달라도 같은 키가 나오도록 운영자 비밀번호에서 유도
        return hashlib.sha256(b'bulky-waste-fee:' + seed.encode()).digest()
    return _DEV


_DEV = secrets.token_bytes(32)


def sign(data, ttl=None):
    body = dict(data)
    if ttl:
        body['_x'] = int(time.time() + ttl)
    raw = zlib.compress(json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode(), 9)
    b = base64.b32encode(raw).decode().rstrip('=').lower()
    mac = hmac.new(_secret(), b.encode(), hashlib.sha256).hexdigest()[:32]
    return f'{b}.{mac}'


def unsign(token):
    try:
        b, mac = str(token).rsplit('.', 1)
        good = hmac.new(_secret(), b.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(mac, good):
            return None
        pad = '=' * (-len(b) % 8)
        body = json.loads(zlib.decompress(base64.b32decode(b.upper() + pad)).decode())
        if body.get('_x') and body['_x'] < time.time():
            return None
        return body
    except Exception:
        return None


def text_tag(text):
    """서버가 고객 응답에 실어 보낸 글에 붙이는 16자 서명(번역 캐시는 이 서명이 맞는 글만 받는다)."""
    return hmac.new(_secret(), ('tr:' + str(text)).encode(), hashlib.sha256).hexdigest()[:16]


def text_tag_ok(text, tag):
    return bool(tag) and hmac.compare_digest(text_tag(text), str(tag))
