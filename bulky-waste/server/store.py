"""저장소: SQLite 한 파일. Vercel처럼 디스크가 휘발되는 곳에서는 BLOB_READ_WRITE_TOKEN 이 있으면
DB 파일 전체를 Vercel Blob(private)에 버전 경로로 올려 두고, 인스턴스가 뜰 때·주기적으로 최신본을 받아 온다.
(버전마다 새 경로를 쓰므로 CDN 캐시 때문에 옛 파일을 읽는 일이 없다. 최근 10개 버전은 백업으로 남긴다.)"""
import csv, io, json, os, secrets, sqlite3, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
ON_VERCEL = bool(os.environ.get('VERCEL'))
DB_PATH = os.environ.get('DB_PATH') or ('/tmp/bulky.db' if ON_VERCEL else os.path.join(ROOT, 'var', 'app.db'))
BLOB_PREFIX = os.environ.get('BLOB_PREFIX', 'state/')
SYNC_EVERY = float(os.environ.get('SYNC_EVERY', '8'))

LOCK = threading.RLock()
_local = threading.local()

SCHEMA = '''
CREATE TABLE IF NOT EXISTS municipality(code TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL);
CREATE TABLE IF NOT EXISTS ordinance(id INTEGER PRIMARY KEY, muni TEXT, item TEXT, spec TEXT, fee INTEGER,
    disp_item TEXT, disp_spec TEXT, ord INTEGER);
CREATE TABLE IF NOT EXISTS confirmed(id INTEGER PRIMARY KEY, muni TEXT, item TEXT, spec TEXT, fee INTEGER, method TEXT,
    category TEXT, updated_at REAL, updated_by TEXT);
CREATE TABLE IF NOT EXISTS review(id INTEGER PRIMARY KEY, muni TEXT, query TEXT, qnorm TEXT, label TEXT, status TEXT,
    detail TEXT, proposal TEXT, asks INTEGER DEFAULT 1, contact TEXT, attachment TEXT, dims TEXT, memo TEXT,
    created_at REAL, updated_at REAL, resolved_by TEXT, resolved_at REAL, result TEXT);
CREATE TABLE IF NOT EXISTS ticket(id TEXT PRIMARY KEY, muni TEXT, items TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, at REAL, user TEXT, action TEXT, target TEXT, before TEXT, after TEXT);
CREATE TABLE IF NOT EXISTS expression(id INTEGER PRIMARY KEY, muni TEXT, expr TEXT, enorm TEXT, general TEXT, query TEXT,
    count INTEGER DEFAULT 1, status TEXT DEFAULT 'new', created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS synonym(id INTEGER PRIMARY KEY, kind TEXT, expr TEXT, target TEXT, by TEXT, at REAL);
CREATE TABLE IF NOT EXISTS setting(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS shopcache(key TEXT PRIMARY KEY, value TEXT, at REAL);
CREATE INDEX IF NOT EXISTS ix_conf ON confirmed(muni);
CREATE INDEX IF NOT EXISTS ix_ord ON ordinance(muni);
CREATE INDEX IF NOT EXISTS ix_rev ON review(muni, status);
'''


# ---------------------------------------------------------------- Blob 동기화
class BlobSync:
    def __init__(self):
        self.enabled = bool(os.environ.get('BLOB_READ_WRITE_TOKEN'))
        self.current = None      # 지금 로컬 DB가 어떤 blob 버전에서 왔는지
        self.checked = 0.0
        self.error = None

    def _blob(self):
        from vercel.blob import sync as b
        return b

    def latest(self):
        b = self._blob()
        items = [x for x in b.query_blobs(prefix=BLOB_PREFIX) if x.pathname.endswith('.sqlite')]
        items.sort(key=lambda x: x.pathname)
        return items

    def pull(self, force=False):
        """원격 최신본이 로컬과 다르면 받아서 교체. 반환: 교체했는지."""
        if not self.enabled:
            return False
        now = time.time()
        if not force and now - self.checked < SYNC_EVERY:
            return False
        self.checked = now
        try:
            items = self.latest()
            if not items:
                return False
            top = items[-1]
            if top.pathname == self.current:
                return False
            data = self._blob().get_blob(top.pathname, access='private').body
            with LOCK:
                close_conn()
                tmp = DB_PATH + '.dl'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, DB_PATH)
                self.current = top.pathname
                _GEN[0] += 1
                ensure_schema()
            self.error = None
            return True
        except Exception as e:  # 원격이 잠시 안 돼도 서비스는 로컬 DB로 계속
            self.error = f'{type(e).__name__}: {e}'
            print('[blob pull]', self.error, flush=True)
            return False

    def push(self):
        if not self.enabled:
            return
        try:
            with LOCK:
                src = conn()
                mem = sqlite3.connect(':memory:')
                src.backup(mem)
                data = mem.serialize()
                mem.close()
            name = f'{BLOB_PREFIX}db-{int(time.time() * 1000):015d}-{secrets.token_hex(3)}.sqlite'
            self._blob().put_blob(name, bytes(data), access='private', content_type='application/octet-stream')
            self.current = name
            self.checked = time.time()
            items = self.latest()
            old = [x.pathname for x in items[:-10]]
            if old:
                self._blob().delete_blob(old)
            self.error = None
        except Exception as e:
            self.error = f'{type(e).__name__}: {e}'
            print('[blob push]', self.error, flush=True)


SYNC = BlobSync()


# ---------------------------------------------------------------- 연결
def close_conn():
    c = getattr(_local, 'c', None)
    if c is not None:
        try:
            c.close()
        except Exception:
            pass
    _local.c = None
    _local.gen = None


_GEN = [0]


def conn():
    """스레드별 연결. DB 파일이 교체되면(_GEN 증가) 새로 연다."""
    c = getattr(_local, 'c', None)
    if c is None or getattr(_local, 'gen', None) != _GEN[0]:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
        c.row_factory = sqlite3.Row
        _local.c = c
        _local.gen = _GEN[0]
    return c


def q(sql, args=(), one=False):
    with LOCK:
        cur = conn().execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    with LOCK:
        c = conn()
        cur = c.execute(sql, args)
        c.commit()
        mark_dirty()
        return cur.lastrowid


def xmany(sql, seq):
    with LOCK:
        c = conn()
        c.executemany(sql, seq)
        c.commit()
        mark_dirty()


_WRITES = [0]


def mark_dirty():
    _WRITES[0] += 1


def writes():
    return _WRITES[0]


def get_setting(key, default=None):
    r = q('SELECT value FROM setting WHERE key=?', (key,), one=True)
    return r['value'] if r else default


def set_setting(key, value):
    x('INSERT INTO setting(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))


def bump_version():
    set_setting('data_version', f'{time.time():.6f}-{secrets.token_hex(2)}')


def log(user, action, target, before=None, after=None):
    x('INSERT INTO history(at,user,action,target,before,after) VALUES(?,?,?,?,?,?)',
      (time.time(), user, action, target,
       json.dumps(before, ensure_ascii=False) if before is not None else None,
       json.dumps(after, ensure_ascii=False) if after is not None else None))


# ---------------------------------------------------------------- 초기 데이터
def read_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def parse_fee(v):
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return int(s) if s else None


def ordinance_rows_from_csv(text):
    """조례 CSV 텍스트 → (행 목록, 버린 행 목록). 4·5번째 칸(표시품목·표시규격)은 있으면 쓴다."""
    rd = csv.DictReader(io.StringIO(text.lstrip('﻿')))
    need = {'품목', '규격', '수수료'}
    if not need <= set(rd.fieldnames or []):
        raise ValueError('머리행에 품목,규격,수수료 칸이 있어야 합니다')
    rows, dropped = [], []
    for i, r in enumerate(rd, start=2):
        fee = parse_fee(r.get('수수료'))
        item = (r.get('품목') or '').strip()
        if not item or not fee or fee <= 0:
            dropped.append({'line': i, 'row': {k: r.get(k) for k in ('품목', '규격', '수수료')}})
            continue
        rows.append({'item': item, 'spec': (r.get('규격') or '').strip(), 'fee': fee,
                     'disp_item': (r.get('표시품목') or '').strip(), 'disp_spec': (r.get('표시규격') or '').strip()})
    return rows, dropped


def save_ordinance(muni, rows):
    with LOCK:
        c = conn()
        c.execute('DELETE FROM ordinance WHERE muni=?', (muni,))
        c.executemany('INSERT INTO ordinance(muni,item,spec,fee,disp_item,disp_spec,ord) VALUES(?,?,?,?,?,?,?)',
                      [(muni, r['item'], r['spec'], r['fee'], r.get('disp_item') or '', r.get('disp_spec') or '', i)
                       for i, r in enumerate(rows)])
        c.commit()
        mark_dirty()


def ensure_schema():
    with LOCK:
        c = conn()
        c.executescript(SCHEMA)
        c.commit()


def seed():
    """빈 DB면 과천시 자료와 전국 스냅샷으로 채운다."""
    ensure_schema()
    if q('SELECT 1 FROM municipality LIMIT 1', one=True):
        return False
    now = time.time()
    x('INSERT INTO municipality(code,name,created_at) VALUES(?,?,?)', ('gwacheon', '경기도 과천시', now))
    disp = {}
    p = os.path.join(DATA, 'gwacheon_display.csv')
    if os.path.exists(p):
        for r in read_csv(p):
            disp[(r['품목'].strip(), r['규격'].strip())] = (r['표시품목'].strip(), r['표시규격'].strip())
    rows, _ = ordinance_rows_from_csv(open(os.path.join(DATA, 'gwacheon_ordinance.csv'), encoding='utf-8-sig').read())
    for r in rows:
        di, ds = disp.get((r['item'], r['spec']), ('', ''))
        r['disp_item'], r['disp_spec'] = di, ds
    save_ordinance('gwacheon', rows)
    from .catalog import classify
    conf = read_csv(os.path.join(DATA, 'gwacheon_confirmed.csv'))
    xmany('INSERT INTO confirmed(muni,item,spec,fee,method,category,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)',
          [('gwacheon', r['품목'].strip(), r['규격'].strip(), parse_fee(r['수수료']), None, classify(r['품목']), now, '초기 자료')
           for r in conf])
    mp = os.path.join(DATA, 'gwacheon_methods.csv')
    if os.path.exists(mp):
        xmany('INSERT INTO confirmed(muni,item,spec,fee,method,category,updated_at,updated_by) VALUES(?,?,?,?,?,?,?,?)',
              [('gwacheon', r['품목'].strip(), r['규격'].strip() or '모든규격', None, r['배출방법'].strip(), classify(r['품목']), now,
                '초기 자료') for r in read_csv(mp)])
    set_setting('nat_tsv', open(os.path.join(DATA, 'nat_snap.tsv'), encoding='utf-8').read())
    set_setting('nat_updated', '2026-11-13')
    set_setting('nat_source', '내장 스냅샷(143개 기관, 248품목)')
    set_setting('policy:gwacheon', 'hold')
    set_setting('source:gwacheon', 'manual')
    bump_version()
    log('시스템', '초기 자료 적재', '과천시', None, {'조례': len(rows), '확정표': len(conf)})
    return True


def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    SYNC.pull(force=True)
    seeded = seed()
    for sql in ('ALTER TABLE ticket ADD COLUMN contact_name TEXT', 'ALTER TABLE ticket ADD COLUMN contact_phone TEXT',
                'ALTER TABLE ticket ADD COLUMN contact_at REAL'):
        try:
            x(sql)          # 예전 DB에 연락처 칸 추가(이미 있으면 그대로)
        except Exception:
            pass
    if q("SELECT 1 FROM municipality WHERE code='gwacheon' AND name='과천시'", one=True):   # 이름 체계 통일(시도 붙임)
        x("UPDATE municipality SET name='경기도 과천시' WHERE code='gwacheon'")
        set_setting('source:gwacheon', 'manual')
        bump_version()
    if seeded and SYNC.enabled and SYNC.current is None:
        SYNC.push()
