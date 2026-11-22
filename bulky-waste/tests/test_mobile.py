"""모바일 폭(360px)에서 표가 가로 스크롤 없이 읽히는지 + 화면 흐름이 실제 브라우저에서 동작하는지.
실행: 서버를 띄운 뒤  BASE_URL=http://localhost:8765 python3 tests/test_mobile.py [스크린샷 폴더]
(Playwright 가 없으면 건너뜀)"""
import os, re, sys

BASE = os.environ.get('BASE_URL', 'http://localhost:8765')
OUT = sys.argv[1] if len(sys.argv) > 1 else None
FORBIDDEN = re.compile(r'L[0-4]|L\?|신뢰도|보정|중앙값|통계|추정|유사|근거|k=')


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('playwright 없음 — 건너뜀')
        return 0
    ok = True
    with sync_playwright() as p:
        exe = os.environ.get('CHROMIUM_PATH') or ('/opt/pw-browsers/chromium' if os.path.exists('/opt/pw-browsers/chromium') and os.path.isfile('/opt/pw-browsers/chromium') else None)
        b = p.chromium.launch(**({'executable_path': exe} if exe else {}))
        for name, vw, vh in (('mobile360', 360, 780), ('desktop', 1280, 900)):
            pg = b.new_page(viewport={'width': vw, 'height': vh}, device_scale_factor=2 if OUT else 1)
            pg.goto(BASE + '/')
            pg.wait_for_selector('#where:not([hidden])')
            if OUT:
                pg.screenshot(path=os.path.join(OUT, f'{name}_where.png'))
            pg.fill('#place', '과천')
            pg.click('#placeList button >> nth=0')
            pg.wait_for_selector('#ask:not([hidden])')
            for n in ('식기세척기', '캣타워', '전동킥보드', '화이트보드', '소파', '우산', '냉장고', '매트리스', '에어컨', '책장', '목검(나무)'):
                pg.fill('#item', n)
                pg.click('#add')
            pg.click('#go')
            pg.wait_for_selector('#result:not([hidden]) table.fees')
            sw = pg.evaluate('document.documentElement.scrollWidth')
            cw = pg.evaluate('document.documentElement.clientWidth')
            tw = pg.evaluate("document.querySelector('table.fees').scrollWidth")
            pw = pg.evaluate("document.querySelector('#rows').clientWidth")
            print(f'[{name}] 문서 폭 {sw}/{cw}, 표 폭 {tw}/{pw}')
            if sw > cw or tw > pw:
                ok = False
                print('  ✗ 가로 스크롤 발생')
            text = pg.inner_text('body')
            m = FORBIDDEN.search(text)
            if m:
                ok = False
                print('  ✗ 화면 금지어', m.group(0))
            if OUT:
                os.makedirs(OUT, exist_ok=True)
                pg.screenshot(path=os.path.join(OUT, f'{name}_table.png'), full_page=True)
            # 확인 카드 흐름
            pg.goto(BASE + '/')
            pg.wait_for_selector('#ask:not([hidden])')          # 고른 지자체는 기억된다
            pg.fill('#item', '다이슨')
            pg.click('#go')
            pg.wait_for_selector('.card .opt')
            if OUT:
                pg.screenshot(path=os.path.join(OUT, f'{name}_card.png'), full_page=True)
            pg.click('.card .opt >> nth=0')
            pg.wait_for_selector('#result:not([hidden]) .lines li')
            line = pg.inner_text('#rows')
            print(f'[{name}] 카드 선택 결과: {line!r}')
            if '원' not in line:
                ok = False
            if OUT:
                pg.screenshot(path=os.path.join(OUT, f'{name}_card_done.png'), full_page=True)
            pg.close()
        b.close()
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
