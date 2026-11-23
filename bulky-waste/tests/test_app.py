"""HANDOFF 10절 완료 기준 테스트.  실행: python3 -m pytest -q tests/
- 회귀(4-3): tests/regression.py 를 그대로 부른다
- 고객 응답 금지어 정규식 0건: 모든 고객 엔드포인트(화면·정적파일·API·확인 흐름·접수번호·내려받기)
- 기대 입력/결과, 확인 흐름(예/아니요/후보/3번 제한), 쇼핑몰 키 없음, 운영자 흐름
"""
import json, os, re, sys, tempfile

import pytest

TMP = tempfile.mkdtemp()
os.environ['DB_PATH'] = os.path.join(TMP, 'test.db')
os.environ['ADMIN_PASSWORD'] = 'test-pass'
os.environ['RATE_LIMIT_SCALE'] = '1000'
os.environ.pop('BLOB_READ_WRITE_TOKEN', None)
for k in ('NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET', 'COUPANG_ACCESS_KEY', 'COUPANG_SECRET_KEY'):
    os.environ.pop(k, None)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fastapi.testclient import TestClient  # noqa: E402

import app as A  # noqa: E402
from server import shopping  # noqa: E402

FORBIDDEN = re.compile(r'L[0-4]|L\?|신뢰도|보정|중앙값|통계|추정|유사|근거|k=')
EXTRA_FORBIDDEN = re.compile(r'약 ?[\d,]+원|[\d,]+원 ?정도|~[\d,]+원|쇼핑|검색해|최저가|판매가|%')
client = TestClient(A.app)
SEEN = []   # 이 파일에서 받은 모든 고객 응답 본문 → 마지막에 한꺼번에 금지어 검사


def cust(method, url, **kw):
    r = getattr(client, method)(url, **kw)
    body = r.content.decode('utf-8', errors='replace')
    SEEN.append((url, body))
    return r


def quote(*names):
    r = cust('post', '/api/quote', json={'municipality': 'gwacheon', 'items': [{'name': n} for n in names]})
    assert r.status_code == 200, r.text
    return r.json()


def rows_of(j, item=None):
    return [(r['품목'], r['규격'], r['수수료'], r['안내']) for r in j['rows'] if item is None or r['품목'] == item]


def assert_clean(text, where):
    m = FORBIDDEN.search(text)
    assert not m, f'금지어 {m.group(0)!r} in {where}: …{text[max(0, m.start() - 60): m.end() + 60]}…'
    if where.startswith('/api/') or where == '/':      # 화면에 보이는 글(코드 속 % 연산자·CSS 단위는 제외)
        m = EXTRA_FORBIDDEN.search(text)
        assert not m, f'금지 표현 {m.group(0)!r} in {where}'


def admin():
    c = TestClient(A.app)
    r = c.post('/api/admin/login', json={'id': 'admin', 'pw': 'test-pass'})
    assert r.status_code == 200, r.text
    return c


# ------------------------------------------------------------------ 1. 회귀
def test_regression():
    import subprocess
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'tests', 'regression.py')], capture_output=True, text=True)
    print(p.stdout)
    assert p.returncode == 0, p.stdout + p.stderr


# ------------------------------------------------------------------ 3. 기대 결과
def test_dishwasher():
    j = quote('식기세척기')
    assert j['message'] == '문의하신 품목의 수수료입니다.'
    assert rows_of(j) == [('식기세척기', '모든규격', '4,000원', '')]


def test_cat_tower():
    assert rows_of(quote('캣타워')) == [('캣타워', '높이 1m 미만', '3,000원', ''), ('캣타워', '높이 1m 이상', '5,000원', '')]


def test_electric_kickboard():
    assert rows_of(quote('전동킥보드')) == [('전동킥보드', '모든규격', '7,000원', '배터리 분리 후 배출')]


def test_sofa_current_ordinance():
    rs = rows_of(quote('소파'))
    assert rs == [('소파', '1인용', '3,000원', '현행 조례 품목'), ('소파', '2인용', '5,000원', '현행 조례 품목'),
                  ('소파', '3인용', '7,000원', '현행 조례 품목')]


def test_umbrella():
    assert rows_of(quote('우산')) == [('우산', '모든규격', '1,000원', '종량제봉투에 들어가면 봉투로 배출')]


def test_bodyfriend():
    rs = rows_of(quote('바디프렌드'))
    assert len(rs) == 1 and rs[0][0] == '안마의자(바디프렌드)' and rs[0][2] == '7,000원'


@pytest.mark.parametrize('name', ['다이슨', '코웨이 그거', '거실 큰 기계'])
def test_ambiguous_cards(name):
    j = quote(name)
    assert j['rows'] == [] and j['pending'] == []
    assert len(j['needs_confirm']) == 1
    card = j['needs_confirm'][0]
    assert card['kind'] in ('yesno', 'choice') and card['card_id']


def test_whiteboard_three_tiers():
    assert rows_of(quote('화이트보드')) == [('화이트보드', '가로 90cm 미만', '2,000원', ''),
                                          ('화이트보드', '가로 90cm 이상~180cm 미만', '5,000원', ''),
                                          ('화이트보드', '가로 180cm 이상', '7,000원', '')]


def test_handoff_example_table():
    j = quote('식기세척기', '캣타워', '전동킥보드', '화이트보드')
    assert [(r['품목'], r['규격'], r['수수료']) for r in j['rows']] == [
        ('식기세척기', '모든규격', '4,000원'), ('캣타워', '높이 1m 미만', '3,000원'), ('캣타워', '높이 1m 이상', '5,000원'),
        ('전동킥보드', '모든규격', '7,000원'), ('화이트보드', '가로 90cm 미만', '2,000원'),
        ('화이트보드', '가로 90cm 이상~180cm 미만', '5,000원'), ('화이트보드', '가로 180cm 이상', '7,000원')]


def test_specs_follow_notation_rules():
    """우리가 정한 금액(확정표·엔진 구간)은 '미만/이상'만 쓴다. 조례 원문 표기(이하·초과)는 '현행 조례 품목'에서만."""
    names = [l.split(',')[0] for l in open(os.path.join(ROOT, 'data', 'test_gwacheon54.csv'), encoding='utf-8-sig').read().split('\n')[1:] if l]
    j = quote(*names[:30])
    j2 = quote(*names[30:])
    for r in j['rows'] + j2['rows']:
        if r['안내'] != '현행 조례 품목':
            assert not re.search(r'이하|초과', re.sub(r'\(.*?\)', '', r['규격'])), r   # 괄호 속 추가요금 메모는 확정표 원문
        assert re.fullmatch(r'[\d,]+원|무상수거|종량제봉투 배출|대상 아님\(건설폐기물\)', r['수수료']), r


def test_mokgum_without_confirmed_goes_to_review():
    a = admin()
    items = a.get('/api/admin/confirmed?muni=gwacheon').json()['items']
    mk = [x for x in items if x['item'] == '목검']
    assert mk
    assert a.delete(f"/api/admin/confirmed/{mk[0]['id']}").status_code == 200
    try:
        j = quote('목검')
        assert j['rows'] == [] and j['pending'] == ['목검']
        assert j['pending_message'] == '확인 후 안내드리겠습니다.'
        assert j['ticket']
        rv = a.get('/api/admin/review?muni=gwacheon').json()['items']
        hit = [r for r in rv if r['query'] == '목검']
        assert hit and hit[0]['detail']['등급'].startswith('L4') and isinstance(hit[0]['proposal'][0]['fee'], int)
        # 고객 접수번호 화면: 아직 대기
        t = cust('get', f"/api/ticket/{j['ticket']}").json()
        assert t['pending'] == ['목검'] and t['rows'] == []
        # 운영자 금액 수정 후 확정 → 확정표 L1 → 같은 품목은 바로 안내, 접수번호에도 결과
        r = a.post(f"/api/admin/review/{hit[0]['id']}", json={'action': 'edit', 'item': '목검', 'rows': [{'spec': '모든규격', 'fee': 2000}]})
        assert r.status_code == 200, r.text
        assert rows_of(quote('목검')) == [('목검', '모든규격', '2,000원', '')]
        t = cust('get', f"/api/ticket/{j['ticket']}").json()
        assert t['rows'][0]['수수료'] == '2,000원' and t['pending'] == []
        hist = a.get('/api/admin/history').json()['items']
        assert any(h['action'] == '금액 수정 후 확정' for h in hist)
    finally:
        pass


def test_policy_show_displays_but_queues():
    a = admin()
    assert a.post('/api/admin/settings', json={'muni': 'gwacheon', 'policy': 'show'}).status_code == 200
    try:
        j = quote('요술램프')                           # 근거 없음 → 정책상 바로 보여주기
        assert j['rows'] and j['pending'] == []
        rv = a.get('/api/admin/review?muni=gwacheon').json()['items']
        assert any(r['query'] == '요술램프' for r in rv)
    finally:
        a.post('/api/admin/settings', json={'muni': 'gwacheon', 'policy': 'hold'})
    j = quote('요술램프2')
    assert j['rows'] == [] and j['pending'] == ['요술램프2']


# ------------------------------------------------------------------ 4. 확인 흐름
def test_confirm_flow_fallback_choice_then_rows():
    j = quote('다이슨')
    card = j['needs_confirm'][0]
    assert card['kind'] == 'choice' and card['step'] == 1 and card['max_steps'] == 3
    assert 3 <= len(card['options']) <= 4
    r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'choice', 'choice': 1}).json()
    assert r['status'] == 'ok' and r['rows']
    assert '다이슨' in r['rows'][0]['품목']


def test_confirm_flow_max_three_questions():
    card = quote('거실 큰 기계')['needs_confirm'][0]
    asked = 1
    r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'other', 'text': ''}).json()
    while r['status'] == 'card':
        asked += 1
        card = r['card']
        assert card['step'] == asked
        if card['kind'] == 'detail':
            r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'detail', 'dims': {'width': '80', 'height': '120'}, 'text': '검은색'}).json()
        else:
            r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'other', 'text': ''}).json()
    assert asked <= 3
    assert r['status'] == 'ok' and r['pending'] and r['ticket']


def test_confirm_other_text_resolves():
    card = quote('코웨이 그거')['needs_confirm'][0]
    r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'other', 'text': '식기세척기'}).json()
    assert rows_of(r) == [('식기세척기', '모든규격', '4,000원', '')]


def test_tampered_card_rejected():
    card = quote('다이슨')['needs_confirm'][0]
    bad = card['card_id'][:-2] + ('00' if not card['card_id'].endswith('00') else '11')
    r = cust('post', f'/api/confirm/{bad}', json={'answer': 'yes'}).json()
    assert r['status'] == 'error'


class FakeProvider(shopping.ShoppingProvider):
    name = 'fake'

    def available(self):
        return True

    def search(self, query):
        P = shopping.Product
        return [P(title='다이슨 V15 무선청소기', image='https://example.com/a.jpg', link='https://example.com/a', path=['가전디지털', '청소기', '무선청소기'], leaf='무선청소기'),
                P(title='다이슨 V12 무선청소기', image='https://example.com/b.jpg', link='https://example.com/b', path=['가전디지털', '청소기', '무선청소기'], leaf='무선청소기'),
                P(title='다이슨 쿨 선풍기', image='https://example.com/c.jpg', link='https://example.com/c', path=['가전디지털', '계절가전', '선풍기'], leaf='선풍기'),
                P(title='다이슨 퓨어 공기청정기', image='https://example.com/d.jpg', link='https://example.com/d', path=['가전디지털', '공기청정기'], leaf='공기청정기'),
                P(title='다이슨 슈퍼소닉', image='https://example.com/e.jpg', link='https://example.com/e', path=['가전디지털', '이미용가전', '헤어드라이기'], leaf='헤어드라이기')]


@pytest.fixture
def fake_shop():
    shopping._TEST_PROVIDER.append(FakeProvider())
    yield
    shopping._TEST_PROVIDER.clear()


def test_shopping_yes(fake_shop):
    card = quote('다이슨 무선')['needs_confirm'][0]
    assert card['kind'] == 'yesno' and card['item_label'] == '무선 청소기(스틱형)'
    assert card['product']['image'].startswith('https://') and card['product']['title']
    assert '원' not in json.dumps(card['product'], ensure_ascii=False)
    r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'yes'}).json()
    assert r['status'] == 'ok' and r['rows'][0]['품목'] == '무선 청소기(스틱형, 다이슨 무선)' and r['rows'][0]['수수료'] == '3,000원'


def test_shopping_no_gives_distinct_fee_candidates(fake_shop):
    card = quote('다이슨 제품')['needs_confirm'][0]
    assert card['kind'] == 'yesno'
    r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'no'}).json()
    assert r['status'] == 'card'
    c2 = r['card']
    assert c2['kind'] == 'choice' and c2['step'] == 2 and c2['other'] is True
    assert 3 <= len(c2['options']) <= 4, c2['options']
    labels = [o['label'] for o in c2['options']]
    assert not any('무선 청소기(스틱형)' == x for x in labels)
    # 후보마다 금액이 서로 다르다(같은 금액은 하나로 합침)
    fees = []
    for i, _ in enumerate(c2['options']):
        rr = client.post(f"/api/confirm/{c2['card_id']}", json={'answer': 'choice', 'choice': i}).json()
        fees.append(json.dumps([(x['규격'], x['수수료']) for x in rr['rows']] or rr['pending'], ensure_ascii=False))
    assert len(set(fees)) == len(fees), fees


def test_shopping_size_question(fake_shop):
    class P2(FakeProvider):
        def search(self, q):
            P = shopping.Product
            return [P(title='원목 캣타워 대형', image='https://example.com/x.jpg', link='https://example.com/x', path=['반려동물', '고양이', '캣타워'], leaf='캣타워')] * 3 + \
                   [P(title='스크래쳐', image='https://example.com/y.jpg', link='https://example.com/y', path=['반려동물', '고양이', '스크래쳐'], leaf='스크래쳐')]
    shopping._TEST_PROVIDER[:] = [P2()]
    from server import service as S
    c = S.ctx('gwacheon')
    out = S.start_confirm(c, '이케아 고양이')
    card = out['card']
    assert card['kind'] == 'yesno' and card['size_options'] == ['높이 1m 미만', '높이 1m 이상']
    r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'yes', 'size': '높이 1m 이상'}).json()
    assert [(x['규격'], x['수수료']) for x in r['rows']] == [('높이 1m 이상', '5,000원')]


def test_same_fee_candidates_answer_directly():
    j = quote('청소기')        # 진공·무선·로봇 청소기 모두 3,000원 → 묻지 않는다
    assert j['needs_confirm'] == [] and rows_of(j)[0][2] == '3,000원'


# ------------------------------------------------------------------ 5. 쇼핑몰 키 없음
def test_no_shopping_keys_fallback():
    assert shopping.providers() == []
    card = quote('샤오미')['needs_confirm'][0]
    assert card['kind'] == 'choice' and card['question'].startswith('품목 이름을 조금 더 알려 주세요')


# ------------------------------------------------------------------ 운영자
def test_admin_requires_login():
    for path in ('/api/admin/review', '/api/admin/confirmed', '/api/admin/ordinance', '/api/admin/history', '/api/admin/try?q=소파'):
        assert TestClient(A.app).get(path).status_code == 401


def test_admin_bad_password():
    r = TestClient(A.app).post('/api/admin/login', json={'id': 'admin', 'pw': 'nope'})
    assert r.status_code == 401


def test_admin_try_has_internal_fields():
    a = admin()
    r = a.get('/api/admin/try?q=식기세척기&muni=gwacheon').json()
    assert r['result']['등급'].startswith('L1')


def test_confirmed_excel_roundtrip():
    a = admin()
    r = a.get('/api/admin/confirmed/export.xlsx?muni=gwacheon')
    assert r.status_code == 200
    from openpyxl import load_workbook
    import io
    ws = load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[3]] == ['분류', '품목', '규격', '수수료(원)']
    assert ws['D4'].number_format == '#,##0'
    n = sum(1 for row in ws.iter_rows(min_row=4) if row[1].value)
    rep = a.post('/api/admin/confirmed/import', data={'muni': 'gwacheon', 'mode': 'replace', 'dry': '1'},
                 files={'file': ('x.xlsx', r.content)}).json()
    assert rep['rows'] == n and rep['add'] == 0 and rep['change'] == 0 and rep['remove'] == 0 and not rep['errors']


def test_confirmed_rejects_ihang_spec():
    a = admin()
    r = a.post('/api/admin/confirmed?muni=gwacheon', json={'item': '시험품목', 'spec': '높이 1m 이하', 'fee': 3000})
    assert r.status_code == 400


def test_ordinance_preview_counts():
    a = admin()
    data = open(os.path.join(ROOT, 'data', 'gwacheon_ordinance.csv'), 'rb').read()
    rep = a.post('/api/admin/ordinance', data={'muni': 'gwacheon', 'dry': '1'}, files={'file': ('o.csv', data)}).json()
    assert rep['rows'] == 159 and rep['fee_cells'] == 159 and rep['match'] and rep['k'] == 1.25
    assert not rep['added'] and not rep['removed'] and not rep['changed']


def test_new_municipality_upload():
    a = admin()
    csvtext = '품목,규격,수수료\n소파,1인용,4000\n소파,2인용,6000\n냉장고,모든규격,8000\n의자,모든규격,2000\n책상,모든규격,5000\n세탁기,모든규격,5000\n'
    rep = a.post('/api/admin/ordinance', data={'muni': 'testcity', 'name': '시험시', 'dry': '0'},
                 files={'file': ('t.csv', csvtext.encode())}).json()
    assert rep['applied'] and rep['new_municipality']
    j = cust('post', '/api/quote', json={'municipality': 'testcity', 'items': [{'name': '식기세척기'}, {'name': '소파'}, {'name': '목검'}]}).json()
    assert j['municipality'] == '시험시'
    # 그 지자체 금액 체계: 식기세척기 → 그 조례의 세탁기 금액, 소파 → 그 조례 현행 금액
    got = [(r['품목'], r['수수료']) for r in j['rows']]
    assert got[:3] == [('식기세척기', '5,000원'), ('소파', '4,000원'), ('소파', '6,000원')]
    # 조례에 없는 '목검'은 과천 확정표 기준으로 이 지역 금액 단계에 맞춰 계산해 안내(2026-11-23 결정)
    assert [n for n, _ in got[3:]] == ['목검'] and j['pending'] == []


def test_synonym_dictionary_applies():
    a = admin()
    assert a.post('/api/admin/synonyms', json={'kind': 'SYN', 'expr': '스윙의자', 'target': '안마의자'}).status_code == 200
    j = quote('스윙의자')
    assert rows_of(j)[0][2] == '7,000원'
    assert a.post('/api/admin/synonyms', json={'kind': 'AMBIG', 'expr': '무인양품'}).status_code == 200
    assert quote('무인양품 선반')['needs_confirm']


def test_expression_log_from_confirm():
    a = admin()
    card = quote('코웨이')['needs_confirm'][0]
    cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'choice', 'choice': 0})
    log = a.get('/api/admin/synonyms?muni=gwacheon').json()['log']
    assert any(x['expr'] == '코웨이' for x in log)


def test_national_upload_tsv():
    a = admin()
    tsv = open(os.path.join(ROOT, 'data', 'nat_snap.tsv'), 'rb').read()
    r = a.post('/api/admin/national/upload', files={'file': ('n.tsv', tsv)}).json()
    assert r['ok'] and r['items'] == 248


def test_cron_requires_secret():
    assert client.get('/api/cron/national').status_code == 401


# ------------------------------------------------------------------ 2. 금지어(마지막에 모든 고객 응답 일괄 검사)
def test_customer_pages_and_static_clean():
    for u in ('/static/udong.png', '/static/udong-512.png'):
        assert client.get(u).status_code == 200 and client.get(u).headers['content-type'] == 'image/png'
    for u in ('/', '/static/app.js', '/static/i18n.js', '/static/style.css', '/api/municipalities', '/api/health'):
        r = cust('get', u)
        assert r.status_code == 200, u
    big = quote('매트리스 토퍼', '유아용 쿠션', '공기청정기 필터', '덤벨', '절구', '파라솔', '냉장고', 'TV', '에어컨', '책장', '의자', '스키',
                '헤어드라이어', '전기자전거', '나무판자', '2층 침대', '크리스마스트리', '킥보드', '침대', '매트')
    assert big['rows']
    ex = cust('post', '/api/quote/export', json={'format': 'csv', 'rows': big['rows']})
    assert ex.status_code == 200 and ex.content.decode('utf-8-sig').startswith('품목,규격,수수료,배출 안내')
    x = client.post('/api/quote/export', json={'format': 'xlsx', 'rows': big['rows']})
    assert x.status_code == 200
    from openpyxl import load_workbook
    import io
    ws = load_workbook(io.BytesIO(x.content)).active
    assert [c.value for c in ws[1]] == ['품목', '규격', '수수료', '배출 안내']
    SEEN.append(('/api/quote/export(xlsx)', '\n'.join('\t'.join(str(v or '') for v in row) for row in ws.iter_rows(values_only=True))))


def _fake_public_rows():
    rows = []
    def add(ctpv, sgg, inst, items, date='2026-06-30'):
        for nm, sp, fee, free in items:
            rows.append({'CTPV_NM': ctpv, 'SGG_NM': sgg, 'INSTT_NM': inst, 'LAR_WAS_NM': nm, 'LAR_WAS_SPCFCT': sp,
                         'FEE': str(fee), 'PAID_FREE_YN': '무료' if free else '유료', 'CRTR_YMD': date})
    base = [('장롱', '가로 120cm 이상', 15000, 0), ('장롱', '가로 120cm 미만', 10000, 0), ('소파', '1인용', 4000, 0), ('소파', '2인용 이상', 6000, 0),
            ('냉장고', '모든규격', 5000, 0), ('세탁기', '모든규격', 5000, 0), ('의자', '모든규격', 2000, 0), ('선풍기', '모든규격', 0, 1)]
    add('서울특별시', '강남구', '서울특별시 강남구', base)
    add('경기도', '수원시 장안구', '경기도 수원시', base, '2026-03-01')
    add('경기도', '과천시', '경기도 과천시', base)
    add('부산광역시', '사하구', '부산광역시 사하구', base)
    add('부산광역시', '없음', '부산광역시 중구', base)
    add('전라남도', '여수시', '전라남도 여수시', base[:3])          # 5행 미만 → 건너뜀
    return rows


def test_importer_targets_and_codes():
    from server import importer
    assert importer.parse_targets('서울 전체, 경기도 전체\n부산 사하구, 경북 경산시') == [('서울', None), ('경기', None), ('부산', '사하구'), ('경북', '경산시')]
    assert importer.roman('수원시') == 'suwonsi' and importer.muni_code('gyeonggi', '수원시') == 'gyeonggi-suwon'


def test_importer_run():
    from server import importer
    a = admin()
    rep = importer.run(_fake_public_rows(), importer.parse_targets('서울 전체, 경기 전체, 부산 사하구, 전남 여수시, 경북 경산시'), '시험')
    names = {i['name']: i for i in rep['imported']}
    assert set(names) == {'서울특별시 강남구', '경기도 수원시', '부산광역시 사하구'}
    assert any(s['name'] == '경기도 과천시' for s in rep['skipped'])        # 직접 올린 과천 조례는 유지
    assert any('여수시' in s['name'] for s in rep['skipped'])
    assert rep['missing'] == ['경북 경산시'] and rep['spec_column'] == 'LAR_WAS_SPCFCT' and rep['date_column'] == 'CRTR_YMD' and names['경기도 수원시']['date'] == '2026-03-01'
    code = names['서울특별시 강남구']['code']
    j = cust('post', '/api/quote', json={'municipality': code, 'items': [{'name': '소파'}, {'name': '선풍기'}, {'name': '장롱'}]}).json()
    assert j['municipality'] == '서울특별시 강남구'
    got = [(r['품목'], r['규격'], r['수수료']) for r in j['rows']]
    assert ('소파', '1인용', '4,000원') in got and ('선풍기', '모든규격', '무상수거') in got and ('장롱', '가로 120cm 미만', '10,000원') in got
    ms = cust('get', '/api/municipalities').json()['items']
    assert any(m['name'] == '경기도 과천시' and m['code'] == 'gwacheon' for m in ms)
    assert rows_of(quote('식기세척기'))[0][2] == '4,000원'                    # 과천 확정표 그대로


def test_import_collected_rules(tmp_path):
    from server import importer
    good = '품목,규격,수수료\n' + '\n'.join(f'품목{i},모든규격,{2000 + i * 100}' for i in range(25)) + '\n폐가전,모든규격,0\n'
    (tmp_path / '서울_시험구.csv').write_text(good, encoding='utf-8')
    (tmp_path / '서울_시험구.json').write_text('{"name":"서울특별시 시험구","source_url":"https://www.test.go.kr/x"}', encoding='utf-8')
    (tmp_path / '서울_블로그구.csv').write_text(good, encoding='utf-8')
    (tmp_path / '서울_블로그구.json').write_text('{"source_url":"https://blog.naver.com/x"}', encoding='utf-8')
    (tmp_path / '서울_작은구.csv').write_text('품목,규격,수수료\n소파,1인용,3000\n', encoding='utf-8')
    (tmp_path / '서울_작은구.json').write_text('{"source_url":"https://www.small.go.kr/x"}', encoding='utf-8')
    r = importer.import_collected(str(tmp_path), '시험')
    assert [i['name'] for i in r['imported']] == ['서울특별시 시험구'] and r['imported'][0]['free'] == 1
    assert {x['file'] for x in r['rejected']} == {'서울_블로그구.csv', '서울_작은구.csv'}
    j = cust('post', '/api/quote', json={'municipality': r['imported'][0]['code'], 'items': [{'name': '폐가전'}]}).json()
    assert j['rows'][0]['수수료'] == '무상수거'


def test_bed_bumper_expressions():
    for q in ('베드 범퍼', '베드범퍼', '침대 범퍼', '아기 범퍼'):
        j = quote(q)
        # 확정표 '유아용 쿠션(범퍼형·침대 범퍼)'은 1m 이상 한 줄뿐이지만 같은 품목의 1m 미만 줄도 함께 보여 준다
        assert j['pending'] == [] and [(r['규격'], r['수수료']) for r in j['rows']] == [('가로 1m 미만', '2,000원'), ('가로 1m 이상', '3,000원')], (q, j)
    assert rows_of(quote('소파베드'))[0][2] == '10,000원'          # 베드→침대 바꿔도 기존 확정표 그대로


def test_bed_bumper_equivalent_item():
    """조례에 '침대범퍼'가 없는 지자체: 같은 스티커로 내놓는 조례 항목(놀이매트 → 쿠션 → 방석 → 이불)으로 안내한다."""
    from server import service as S
    from engine import engine as E

    class C:
        pass
    c = C()
    row = lambda n, s, f: {'name': n, 'spec': s, 'fee': f, 'tok': E.tokens(n), 'disp_item': '', 'disp_spec': ''}
    c.local = [row('자동차범퍼', '모든규격', 9000), row('이불', '솜이불', 2000), row('유아용 놀이매트', '1㎡당', 1000),
               row('전기매트', '1인용', 3000)]
    for q in ('베드 범퍼', '베드범퍼', '침대 범퍼', '범퍼침대', '침대 가드'):
        rows, used = S._equiv_rows(c, q, q)
        rows = [{k: v for k, v in o.items() if k != 'src'} for o in rows]
        assert used == '유아용 놀이매트' and rows == [{'item': q, 'spec': '1㎡당', 'fee': 1000, 'note': '‘유아용 놀이매트’ 항목으로 배출'}]
    c.local = c.local[:2]
    assert S._equiv_rows(c, '베드 범퍼', '베드 범퍼')[1] == '이불'
    c.local = [row('자동차범퍼', '모든규격', 9000)]
    assert S._equiv_rows(c, '베드 범퍼', '베드 범퍼') is None
    assert S._equiv_rows(c, '소파', '소파') is None


def test_pending_contact_name_phone():
    """확인 후 안내 → 이름·휴대폰(동의 필수) → 운영 화면 검토 대기열에 연락처, 고객 응답에는 가린 번호만."""
    j = quote('요술램프 대형')
    assert j['pending'] and j['ticket']
    url = f"/api/ticket/{j['ticket']}/contact"
    assert cust('post', url, json={'name': '홍길동', 'phone': '010-1234-5678', 'agree': False}).status_code == 400
    assert cust('post', url, json={'name': '홍길동', 'phone': '02-123-4567', 'agree': True}).status_code == 400
    assert cust('post', url, json={'name': '', 'phone': '01012345678', 'agree': True}).status_code == 400
    assert cust('post', '/api/ticket/zzzzzzzz/contact', json={'name': '홍길동', 'phone': '01012345678', 'agree': True}).status_code == 400
    r = cust('post', url, json={'name': '홍길동', 'phone': '01012345678', 'agree': True})
    assert r.status_code == 200 and '010-****-5678' in r.json()['message'] and '1234' not in r.text
    rv = [x for x in admin().get('/api/admin/review?muni=gwacheon').json()['items'] if x['query'] == '요술램프 대형']
    assert rv and rv[0]['contact'][0]['name'] == '홍길동' and rv[0]['contact'][0]['phone'] == '010-1234-5678'
    assert rv[0]['contact'][0]['ticket'] == j['ticket']


def test_shopping_rescues_pending_item(fake_shop):
    """조례·확정표에 없는 이름이라도 쇼핑몰 분류명이 조례 품목이면 '○○ 맞으신가요?'로 바로 묻는다."""
    class P3(FakeProvider):
        def search(self, q):
            P = shopping.Product
            return [P(title='냥이 원목 하우스 3단', image='https://example.com/z.jpg', link='https://example.com/z', path=['반려동물', '고양이', '캣타워'], leaf='캣타워')] * 3
    shopping._TEST_PROVIDER[:] = [P3()]
    j = quote('냥냥하우스 3단')
    assert j['pending'] == [] and j['needs_confirm'][0]['kind'] == 'yesno' and j['needs_confirm'][0]['item_label'] == '캣타워'
    shopping._TEST_PROVIDER[:] = []
    assert quote('냥냥하우스 3단')['pending'] == ['냥냥하우스 3단']


def test_ai_estimate_keeps_product_name_and_cart_etc():
    """조례에 없는 이름 → AI가 비슷한 조례 품목을 고르면 그 규격·금액으로, 제품명 그대로 안내하고 장바구니는 '기타'.
    '○○ 항목으로 내놓으시면' 같은 대체 질문은 하지 않는다(2026-11-23 결정). 목록에 없는 이름은 버린다."""
    from server import ai
    seen = {}

    def fake(prompt):
        seen['p'] = prompt
        return '{"items": ["없는품목", "캣타워"], "what": "고양이 놀이 가구"}'
    ai._TEST[:] = [fake]
    try:
        j = quote('냥이궁전 대형')
        assert j['pending'] == [] and not j['needs_confirm']
        assert '캣타워' in seen['p'] and '냥이궁전 대형' in seen['p']
        assert [(r['품목'], r['규격'], r['수수료'], r['안내'], r['담기']) for r in j['rows']] ==             [('냥이궁전 대형', '높이 1m 미만', '3,000원', '', '기타'), ('냥이궁전 대형', '높이 1m 이상', '5,000원', '', '기타')]
        ai._TEST[:] = [lambda p: '{"items": [], "what": ""}']
        assert quote('알수없는물건 특대')['pending'] == ['알수없는물건 특대']
    finally:
        ai._TEST.clear()


def test_zz_all_customer_responses_forbidden_words():
    assert len(SEEN) > 40
    for url, body in SEEN:
        if body.startswith('PK'):          # 엑셀(zip) 본문은 아래에서 풀어서 검사
            continue
        assert_clean(body, url)
    # 고객 응답 JSON 키에도 근거 필드가 없어야 한다
    for url, body in SEEN:
        if url.startswith('/api/') and body.startswith('{'):
            j = json.loads(body)
            for r in j.get('rows', []):
                assert set(r) <= {'품목', '규격', '수수료', '안내', '분류', '담기'}, (url, r)


def test_modifier_names_show_all_sizes():
    """앞말이 붙은 이름(양문형냉장고·3인용소파)은 최저가 한 줄이 아니라 그 품목 규격을 보여 준다(2026-11-23 전수 검수)."""
    fees = lambda q: [r[2] for r in rows_of(quote(q))]
    assert fees('3인용소파') == ['7,000원']                     # 앞말이 규격에 있으면 그 줄만
    assert len(fees('양문형냉장고')) >= 3 and '4,000원' in fees('양문형냉장고')
    assert fees('흙침대') == ['20,000원', '30,000원']            # 흙·옥·황토침대 → 돌침대
    j = quote('드럼세탁기')
    assert j['rows'] and all('피아노' not in r[0] + r[1] for r in rows_of(j))


def test_wrong_head_word_blocked():
    """끝말만 같은 다른 물건으로 매기지 않는다."""
    from server import service as S
    c = S.ctx('gwacheon')
    bad = {'전기장판': '상위어 장판', '고양이화장실': '상위어', '화이트보드': '상위어', '킥보드': '상위어', '키보드': '상위어'}
    for q, wrong in bad.items():
        res = S.resolve(c, q)
        assert wrong not in str(res['result'].get('경로')), (q, res['result'])


def test_unclear_specs_go_to_review():
    """같은 품목·같은 규격 글자에 금액이 둘이면 고를 수 없으니 확인 후 안내."""
    from server import service as S
    rows = [{'item': '냉장고', 'spec': '모든규격', 'fee': 5000}, {'item': '냉장고', 'spec': '모든규격', 'fee': 7000}]
    assert S._unclear(rows)
    assert not S._unclear([{'item': '냉장고', 'spec': '300L 미만', 'fee': 5000}, {'item': '냉장고', 'spec': '300L 이상', 'fee': 7000}])


def test_translate_endpoint_and_cache():
    """다국어: 서버가 서명한 글(응답의 tk)만 캐시하고, 서명 없는 글은 번역만 하고 캐시하지 않는다.
    숫자가 바뀐 번역은 버리고, 개수 불일치·잘못된 언어면 원문/400."""
    from server import ai
    from server.tokens import text_tag
    calls = []

    def fake(prompt):
        calls.append(prompt)
        import json as _j
        arr = _j.loads(prompt[prompt.rindex('['):])
        return _j.dumps(['EN:' + x for x in arr], ensure_ascii=False)
    ai._TEST[:] = [fake]
    try:
        tk = {'소파': text_tag('소파'), '1인용': text_tag('1인용')}
        r = client.post('/api/translate', json={'lang': 'en', 'texts': ['소파', '1인용', '3,000', ''], 'tk': tk})
        assert r.status_code == 200 and r.json()['texts'] == ['EN:소파', 'EN:1인용', '3,000', '']
        n = len(calls)
        assert client.post('/api/translate', json={'lang': 'en', 'texts': ['소파'], 'tk': tk}).json()['texts'] == ['EN:소파']
        assert len(calls) == n                                   # 서명 있는 글은 캐시
        client.post('/api/translate', json={'lang': 'en', 'texts': ['냉장고 아무말']})
        client.post('/api/translate', json={'lang': 'en', 'texts': ['냉장고 아무말']})
        assert len(calls) == n + 2                               # 서명 없는 글은 캐시하지 않는다
        ai._TEST[:] = [lambda p: '["2m 이상"]']
        assert client.post('/api/translate', json={'lang': 'ru', 'texts': ['1m 이상'], 'tk': {'1m 이상': text_tag('1m 이상')}}).json()['texts'] == ['1m 이상']
        ai._TEST[:] = [lambda p: '["하나뿐"]']
        assert client.post('/api/translate', json={'lang': 'vi', 'texts': ['냉장고', '책상']}).json()['texts'] == ['냉장고', '책상']
        assert client.post('/api/translate', json={'lang': 'xx', 'texts': ['소파']}).status_code == 400
        assert client.post('/api/translate', json=[1]).status_code == 400
        q = client.post('/api/quote', json={'municipality': 'gwacheon', 'items': [{'name': '소파'}]}).json()
        assert q['tk'].get('1인용') == text_tag('1인용')       # 답 속 글에는 서명이 붙어 온다
    finally:
        ai._TEST[:] = []


def test_ai_pick_accepts_name_inside_comma_list():
    """'벽시계, 가방, …, 항아리' 한 줄 조례 항목: AI가 '항아리'만 답해도 받아들인다(서천 화분)."""
    from server import ai
    ai._TEST[:] = [lambda p: '{"items": ["항아리"], "what": "도자기 화분"}']
    try:
        got = ai.pick_items('test-comma', '시험군', '화분 대형', ['벽시계, 가방, 거울, 항아리', '자전거'])
        assert got == ['항아리'], got
    finally:
        ai._TEST[:] = []


def test_powered_item_uses_manual_top_tier():
    """전동킥보드: 조례에 수동형도 없으면 수동형이 매겨지는 항목의 최고 구간 + 배터리 안내."""
    from server import service as S
    c = S.ctx('gwacheon')
    res = S.resolve(c, '전동킥보드')
    assert res['kind'] == 'rows' and len(res['rows']) == 1 and '배터리' in (res['rows'][0].get('note') or ''), res


def test_child_items_hide_adult_rows():
    """'아기 전동자동차'에 '성인용' 줄이 나오면 안 된다(반대도 같다)."""
    from server import service as S
    rows = [{'item': 'x', 'spec': '어린이용', 'fee': 2000}, {'item': 'x', 'spec': '성인용', 'fee': 3000}]
    assert [o['spec'] for o in S._age_fit('아기 전동자동차', rows)] == ['어린이용']
    assert [o['spec'] for o in S._age_fit('성인 자전거', rows)] == ['성인용']
    assert S._age_fit('자전거', rows) == rows
    assert S._age_fit('아기 의자', [{'item': 'x', 'spec': '성인용', 'fee': 3000}])[0]['spec'] == '성인용'   # 남는 줄이 없으면 그대로


def test_examples_only_answerable_items():
    """지역을 고른 뒤 보이는 예시 단추는 그 지역에서 금액이 바로 나오는 품목만."""
    from server import service as S
    j = client.get('/api/examples?m=gwacheon').json()
    assert 1 <= len(j['items']) <= 6
    c = S.ctx('gwacheon')
    for q in j['items']:
        r = S.resolve(c, q)
        assert r['kind'] == 'rows' and any(o.get('fee') for o in r['rows']), (q, r)


def test_ai_pick_rejects_material_groups():
    """AI가 '나무류'(합판·팔레트·판넬·20ℓ 묶음)를 골라도 물건 크기가 아니므로 건너뛴다(서천 캣타워)."""
    from server import service as S
    rows = [{'item': 'x', 'spec': s, 'fee': f} for s, f in
            [('20ℓ 1묶음', 2000), ('합판류(소)', 2000), ('지게차 팔레트', 4000), ('공사용 판넬', 5000)]]
    assert S._not_one_object(rows, '나무류')
    assert not S._not_one_object([{'item': 'x', 'spec': '1인용', 'fee': 3000}, {'item': 'x', 'spec': '2인용', 'fee': 5000}], '소파')
    assert not S._not_one_object([{'item': 'x', 'spec': '높이 1m 미만', 'fee': 2000}, {'item': 'x', 'spec': '높이 1m 이상', 'fee': 3000}], '신발장')
    from server import catalog as C
    assert C.CATCH_ALL.search('나무류') and C.CATCH_ALL.search('기타100') and not C.CATCH_ALL.search('기타(악기)')


def test_indirect_rows_only_sizes_of_asked_item():
    """간접 답: 다른 물건(안마의자)·말하지 않은 종류(2층·돌·유아용)·봉투·무게 단가 줄은 뺀다. 면적 단가는 남긴다."""
    from server import service as S
    rows = [{'item': '캠핑의자', 'spec': s, 'fee': f, 'note': ''} for s, f in
            [('일반의자(1인용)', 2000), ('회전의자(1인용)', 4000), ('안마의자', 15000), ('20kg당', 1000)]]
    assert [o['spec'] for o in S._fit_rows('캠핑의자', rows)] == ['일반의자(1인용)', '회전의자(1인용)']
    beds = [{'item': '퀸침대', 'spec': s, 'fee': f, 'note': ''} for s, f in
            [('유아용 침대', 3000), ('2인용(틀)', 7000), ('어린이 2층 침대', 20000), ('2인용 돌침대 세트', 30000)]]
    assert [o['spec'] for o in S._fit_rows('퀸침대', beds)] == ['2인용(틀)']
    kick = [{'item': '킥보드', 'spec': s, 'fee': f, 'note': ''} for s, f in [('어린이용', 2000), ('성인용', 3000)]]
    assert len(S._fit_rows('킥보드', kick)) == 2                        # 어른 크기를 말하지 않았으면 어린이용도 크기
    mat = [{'item': '놀이매트', 'spec': '3.3㎡(1평)당', 'fee': 2000, 'note': ''}]
    assert S._fit_rows('놀이매트', mat) == mat                         # 면적 단가는 그 물건의 크기


def test_missing_item_uses_reference_sizes_scaled():
    """조례에 없는 품목은 과천 확정표의 크기 구분으로, 금액은 그 지역 수준으로 환산(캣타워면 캣타워로)."""
    from server import service as S
    g = S.ctx('gwacheon')
    rows = S._ref_scaled(g, '캣타워', '캣타워')
    assert rows is None                                   # 과천 자신은 환산하지 않는다


def test_etc_fee_rounds_to_app_amount_units():
    """조례에 없는 품목은 앱 '기타 > 금액'(1,000/5,000/10,000원)으로 담기므로 1,000원 단위."""
    from server import service as S
    assert [S._etc_fee(f) for f in (400, 1500, 2400, 2500, 6000, None)] == [1000, 2000, 2000, 3000, 6000, None]
    res = {'kind': 'rows', 'result': {'등급': 'L3 전국 통계×지역 보정', '경로': '전국 캣타워 중앙값 3000×k'},
           'rows': [{'item': '캣타워', 'spec': '높이 1m 미만', 'fee': 2500, 'note': '‘신발장’ 항목으로 배출'}]}
    S._mark_cart(res)
    o = res['rows'][0]
    assert o['cart'] == '기타' and o['fee'] == 3000 and o['note'] == ''


def test_ref_scaling_to_other_region():
    """과천 확정표 크기 구분 × (그 지역 k ÷ 과천 k), 그 지역이 두 번 이상 쓰는 금액 단계, 큰 규격은 한 단계 위."""
    from server import service as S

    class R:
        pass
    c = R()
    c.muni, c.k, c.grid = 'test-region', 1.0, [2000, 3000, 4000]
    c.local = [{'fee': f} for f in (2000, 2000, 3000, 3000, 4000, 4000)]
    g = S.ctx('gwacheon')
    base = [(o['spec'], o['fee']) for o in S.resolve(g, '캣타워')['rows']]
    rows = S._ref_scaled(c, '캣타워', '캣타워')
    assert [o['spec'] for o in rows] == [s for s, _ in base]
    fees = [o['fee'] for o in rows]
    assert all(f in (2000, 3000, 4000) for f in fees) and fees == sorted(fees) and len(set(fees)) == len(fees)


def test_filtered_rows_never_come_back_as_estimate():
    """간접 답에서 맞는 규격이 하나도 안 남으면(퀸침대→접이식·2층만) 계산값으로 되살리지 않는다."""
    from server import service as S
    res = {'kind': 'pending', 'rows': [{'item': '퀸침대', 'spec': '2층 침대', 'fee': 19000}],
           'result': {'등급': 'L2 유사품목', '경로': '상위어 접이식 침대 (맞는 규격 없음)'}}
    assert S._engine_estimate(S.ctx('gwacheon'), '퀸침대', res) is None


def test_modifier_type_only_when_region_prices_it():
    """'접이식'처럼 꾸미는 말은 그 지역 조례가 따로 값을 매길 때만 따진다(없으면 빨래건조대 줄로 답한다)."""
    from server import service as S

    class R:
        pass
    c = R()
    c.local = [{'name': '빨래건조대', 'spec': '모든규격', 'disp_item': '', 'disp_spec': ''}]
    c.conf = []
    assert not S._region_has(c, '접이식')
    c.local.append({'name': '의자', 'spec': '접이식', 'disp_item': '', 'disp_spec': ''})
    assert S._region_has(c, '접이식')


def test_tokens_order_is_fixed():
    """토큰 순서가 프로세스(해시 시드)마다 달라 지역 금액 수준 k가 바뀌던 문제: 정렬된 튜플이어야 한다."""
    import subprocess, sys, os
    code = ("from server import service as S; from engine import engine as E;"
            "print(E.tokens('책장,진열장,장식장,수납장 tv 다이'))")
    outs = {subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, encoding='utf-8',
                           env=dict(os.environ, PYTHONHASHSEED=str(s), PYTHONIOENCODING='utf-8'),
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout for s in (1, 2, 3)}
    assert len(outs) == 1 and outs.pop().startswith('(')


def test_kid_item_drops_adult_sizes():
    """아이 물건은 유아용 줄이 있으면 그 줄만, 없으면 2인용·더블 같은 어른 크기 줄을 뺀다."""
    from server import service as S
    rows = [{'spec': '유아용 침대', 'fee': 3000, 'src': '침대'}, {'spec': '1인용(틀)', 'fee': 5000, 'src': '침대'},
            {'spec': '2인용(틀)', 'fee': 7000, 'src': '침대'}]
    assert [o['spec'] for o in S._age_fit('아기침대', rows)] == ['유아용 침대']
    sofa = [{'spec': '1인용', 'fee': 3000}, {'spec': '2인용', 'fee': 5000}, {'spec': '4인용 이상', 'fee': 9000}]
    assert [o['spec'] for o in S._age_fit('어린이 소파', sofa)] == ['1인용']
    assert len(S._age_fit('소파', sofa)) == 3


def test_spec_column_hit():
    """'매트리스'가 조례 '침대' 줄의 규격 칸에만 있으면 그 줄로 답한다(세트 줄은 뺀다)."""
    from server import service as S

    class R:
        pass
    c = R()
    mk = lambda n, s, f: {'name': n, 'spec': s, 'fee': f, 'tok': S._tok(n), 'disp_item': '', 'disp_spec': ''}
    c.local = [mk('침대', '1인용 (매트리스)', 5000), mk('침대', '2인용 (매트리스)', 8000), mk('침대', '1인용 세트(매트리스 1개+틀)', 10000),
               mk('침대', '1인용(틀)', 5000), mk('소파', '1인용', 3000)]
    for q in ('침대 매트리스', '매트리스'):
        r = S._spec_hit(c, q, q)
        assert r and [o['fee'] for o in r['rows']] == [5000, 8000], q
    assert S._spec_hit(c, '냉장고', '냉장고') is None


def test_kid_indirect_keeps_baby_row_not_bunk():
    """'유아침대': 조례의 '아기/접이식 침대' 줄은 남기고 '어린이 2층 침대'는 뺀다. 성인용만 있으면 답하지 않는다."""
    from server import service as S
    rows = [{'item': '침대', 'spec': '유아용 침대', 'fee': 3000, 'src': '침대'},
            {'item': '침대', 'spec': '어린이 2층 침대', 'fee': 20000, 'src': '침대'},
            {'item': '침대', 'spec': '모든규격', 'fee': 5000, 'src': '아기/접이식 침대'}]
    kept = S._age_fit('유아침대', S._fit_rows('유아침대', rows), strict=True)
    assert sorted(o['fee'] for o in kept) == [3000, 5000]
    assert S._age_fit('아기욕조', [{'spec': '성인용', 'fee': 5000}], strict=True) == []


def test_size_and_kind_fit():
    """싱글침대엔 2인용 줄을, 의자엔 안마의자 줄을 보이지 않는다. 업소용 같은 그 품목의 규격은 남긴다."""
    from server import service as S
    bed = [{'spec': '1인용(틀)', 'fee': 5000}, {'spec': '2인용(틀)', 'fee': 7000}, {'spec': '1인용 세트', 'fee': 10000}]
    assert [o['fee'] for o in S._size_fit('싱글침대', bed)] == [5000, 10000]
    assert len(S._size_fit('침대', bed)) == 3
    chair = [{'spec': '일반의자', 'fee': 2000}, {'spec': '안마의자', 'fee': 15000}]
    assert [o['fee'] for o in S._kind_fit('의자', chair)] == [2000]
    fr = [{'spec': '300ℓ 미만', 'fee': 4000}, {'spec': '업소용', 'fee': 20000}]
    assert len(S._kind_fit('냉장고', fr)) == 2


def test_elec_free_catchall_and_guitar():
    """조례 무상 줄에 '기타 폐전기·폐전자제품'이 있으면 가전은 무상. 악기 '기타'는 조례의 '기타'(그 밖의 물건) 줄로 답하지 않는다."""
    from server import service as S

    class R:
        pass
    c = R()
    c.methods = [{'name': '기타 폐전기·폐전자제품 등 유사품목', 'spec': '모든규격', 'method': '무상수거', 'tok': ()}]
    assert S._elec_free(c, '전자레인지')['method'] == '무상수거'
    assert S._elec_free(c, '장롱') is None and S._elec_free(c, 'TV장') is None
    c.methods = [{'name': '기타(소형 가전제품)', 'spec': '모든규격', 'method': '무상수거', 'tok': ()}]
    assert S._elec_free(c, '김치냉장고') is None
    c.methods = [{'name': '냉장고', 'spec': '모든규격', 'method': '무상수거', 'tok': ()}]
    assert S._elec_free(c, '전자레인지') is None
    res = {'kind': 'rows', 'result': {'등급': 'L0'}, 'rows': [{'item': '기타', 'spec': '기타(악기)', 'fee': 2000, 'src': '기타(악기)'},
                                                             {'item': '기타', 'spec': '샌드백', 'fee': 2000, 'src': '기타'}]}
    out = S._drop_catchall(None, '기타', '기타', res)
    assert [o['spec'] for o in out['rows']] == ['기타(악기)']


def test_sized_bed_adds_matching_frame():
    """'싱글침대'가 매트리스 줄로만 나오면 조례의 1,400mm 미만·1인용 침대틀 줄을 함께, 퀸이면 미만 틀은 뺀다."""
    from server import service as S

    class R:
        pass
    c = R()
    mk = lambda n, s, f: {'name': n, 'spec': s, 'fee': f, 'tok': S._tok(n), 'disp_item': '', 'disp_spec': ''}
    c.local = [mk('침대틀', '1인용', 10000), mk('침대틀', '2인용', 15000), mk('침대 매트리스', '1인용', 5000)]
    rows = [{'item': '싱글침대', 'spec': '1인용', 'fee': 5000, 'src': '침대 매트리스'}]
    out = S._bed_frame(c, '싱글침대', rows)
    assert [(o['spec'], o['fee']) for o in out] == [('침대틀 1인용', 10000), ('1인용', 5000)]
    q = [{'item': '퀸침대', 'spec': '1400mm 미만', 'fee': 5000, 'src': '침대(침대틀)'},
         {'item': '퀸침대', 'spec': '1400mm 이상', 'fee': 8000, 'src': '침대(침대틀)'}]
    assert [o['fee'] for o in S._bed_frame(c, '퀸침대', q)] == [8000]


def test_sized_bed_with_separate_frame_and_mattress_items():
    """조례에 '침대틀'·'매트리스'가 따로 품목이어도 '싱글침대'는 1,400mm 미만 틀 + 싱글 매트리스, '퀸침대'는 이상 틀 + 퀸 매트리스."""
    from server import service as S

    class R:
        pass
    c = R()
    mk = lambda n, s, f: {'name': n, 'spec': s, 'fee': f, 'tok': S._tok(n), 'disp_item': '', 'disp_spec': ''}
    c.local = [mk('침대틀', '1,400mm미만', 5000), mk('침대틀', '1,400mm이상', 8000), mk('매트리스', '1,000mm이상~1,400mm미만(싱글, 슈퍼싱글)', 5000),
               mk('매트리스', '1,400mm이상~1,700mm미만(더블, 퀸)', 8000), mk('돌침대', '모든규격', 20000)]
    r = S._sized_bed(c, '싱글침대', '싱글침대')
    assert [o['fee'] for o in r['rows']] == [5000, 5000] and [o['src'] for o in r['rows']] == ['침대틀', '매트리스']
    assert [o['fee'] for o in S._sized_bed(c, '퀸침대', '퀸침대')['rows']] == [8000, 8000]
    assert S._sized_bed(c, '2층침대', '2층침대') is None and S._sized_bed(c, '침대', '침대') is None
