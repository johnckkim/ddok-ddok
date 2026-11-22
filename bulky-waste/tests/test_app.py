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
    assert [(r['품목'], r['수수료']) for r in j['rows']] == [('식기세척기', '5,000원'), ('소파', '4,000원'), ('소파', '6,000원')]
    assert j['pending'] == ['목검']           # 그 지자체엔 확정표가 없음 → 근거 없는 금액은 검토 대기


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
    for u in ('/', '/static/app.js', '/static/style.css', '/api/municipalities', '/api/health'):
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
    for q in ('베드 범퍼', '베드범퍼', '범퍼침대', '침대 범퍼', '아기 범퍼'):
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


def test_ai_picks_ordinance_item_then_yes():
    """조례에서 못 찾은 이름 → AI가 조례 품목명 중 고름 → '○○ 맞으신가요?' → 예 → 조례 금액. 목록에 없는 이름은 버린다."""
    from server import ai
    seen = {}

    def fake(prompt):
        seen['p'] = prompt
        return '{"items": ["없는품목", "캣타워"], "what": "고양이 놀이 가구"}'
    ai._TEST[:] = [fake]
    try:
        j = quote('냥이궁전 대형')
        card = j['needs_confirm'][0]
        assert j['pending'] == [] and card['kind'] == 'yesno' and card['item_label'] == '캣타워' and card['as_item']
        assert '캣타워' in seen['p'] and '냥이궁전 대형' in seen['p']
        r = cust('post', f"/api/confirm/{card['card_id']}", json={'answer': 'yes', 'size': '높이 1m 이상'}).json()
        assert r['status'] == 'ok' and r['rows'][0]['수수료'] == '5,000원'
        assert r['rows'][0]['품목'] == '냥이궁전 대형' and r['rows'][0]['안내'] == '‘캣타워’ 항목으로 배출'
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
                assert set(r) <= {'품목', '규격', '수수료', '안내', '분류'}, (url, r)
