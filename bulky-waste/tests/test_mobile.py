"""채팅형 고객 화면을 실제 브라우저로: 360px 가로 스크롤 없음 + 지자체→품목→확인 질문 흐름.
실행: BASE_URL=http://localhost:8765 python3 tests/test_mobile.py [스크린샷 폴더]"""
import os, re, sys
BASE = os.environ.get('BASE_URL', 'http://localhost:8765')
OUT = sys.argv[1] if len(sys.argv) > 1 else None
FORBIDDEN = re.compile(r'L[0-4]|L\?|신뢰도|보정|중앙값|통계|추정|유사|근거|k=')


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright 없음 — 건너뜀'); return 0
    ok = True
    with sync_playwright() as p:
        exe = os.environ.get('CHROMIUM_PATH') or ('/opt/pw-browsers/chromium' if os.path.isfile('/opt/pw-browsers/chromium') else None)
        b = p.chromium.launch(**({'executable_path': exe} if exe else {}))
        for name, vw, vh in (('mobile360', 360, 780), ('desktop', 1280, 900)):
            ctx = b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=2 if OUT else 1)
            pg = ctx.new_page()
            pg.goto(BASE + '/')
            pg.wait_for_selector('.msg.bot')
            assert pg.query_selector('#add') is None, '추가 버튼이 남아 있음'
            assert '품목을 입력하면 AI가 수수료를 알려드립니다' in pg.inner_text('body')
            if OUT: pg.screenshot(path=os.path.join(OUT, f'{name}_1_start.png'))
            pg.fill('#input', '과천'); pg.wait_for_selector('#suggest button')
            if OUT: pg.screenshot(path=os.path.join(OUT, f'{name}_2_suggest.png'))
            pg.press('#input', 'Enter')
            pg.wait_for_selector('.msg.bot .chips')
            pg.fill('#input', '식기세척기, 캣타워, 전동킥보드, 화이트보드, 소파, 우산, 냉장고, 목검')
            pg.press('#input', 'Enter')
            pg.wait_for_selector('.msg.result table.fees')
            sw = pg.evaluate('document.documentElement.scrollWidth'); cw = pg.evaluate('document.documentElement.clientWidth')
            tw = pg.evaluate("document.querySelector('.msg.result table.fees').scrollWidth")
            bw = pg.evaluate("document.querySelector('.msg.result .bubble').clientWidth")
            print(f'[{name}] 문서 폭 {sw}/{cw}, 표 폭 {tw}/{bw}')
            if sw > cw or tw > bw: ok = False; print('  ✗ 가로 스크롤')
            if OUT: pg.screenshot(path=os.path.join(OUT, f'{name}_3_result.png'), full_page=True)
            pg.fill('#input', '다이슨'); pg.press('#input', 'Enter')
            pg.wait_for_selector('.msg.card .opt')
            pg.click('.msg.card .opt >> nth=0')
            for _ in range(60):
                if len(pg.query_selector_all('.msg.result')) >= 2: break
                pg.wait_for_timeout(250)
            last = pg.eval_on_selector_all('.msg.result', 'els => els[els.length-1].innerText')
            print(f'[{name}] 확인 질문 결과: {last[:60]!r}')
            if '원' not in last: ok = False
            m = FORBIDDEN.search(pg.inner_text('body'))
            if m: ok = False; print('  ✗ 화면 금지어', m.group(0))
            if OUT: pg.screenshot(path=os.path.join(OUT, f'{name}_4_card.png'), full_page=True)
            ctx.close()
        b.close()
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
