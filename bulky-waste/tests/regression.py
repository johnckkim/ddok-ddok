#!/usr/bin/env python3
"""회귀 기준 (HANDOFF 4-3)
1) test_gwacheon54.csv 를 nat_snap.tsv 로, 확정표 없이 → 정확 일치 41건 이상, 1.67배 이내 48건 이상
2) 확정표(--confirmed)를 넣으면 54건 모두 정답 금액이 고객 행(구간 포함)에 들어 있어야 한다
3) 엔진 CLI(--client) 출력이 분리 전 원본 엔진과 바이트 단위로 같아야 한다(원본이 있을 때)
사용: python3 tests/regression.py   (종료코드 0 = 통과)
"""
import csv, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import engine as E  # noqa: E402

D = lambda *p: os.path.join(ROOT, 'data', *p)


def load_cases():
    with open(D('test_gwacheon54.csv'), encoding='utf-8-sig') as f:
        return [(r['품목'], int(r['확정'])) for r in csv.DictReader(f)]


def run(confirmed):
    local = E.load_local(D('gwacheon_ordinance.csv'))
    nat = E.load_nat(D('nat_snap.tsv'))
    conf = E.load_local(D('gwacheon_confirmed.csv')) if confirmed else []
    grid = sorted({r['fee'] for r in local})
    k, _, _ = E.calibrate(local, nat)
    return local, [(q, ans, E.price(q, None, local, nat, k, grid, None, conf)) for q, ans in load_cases()]


def main():
    ok = True
    _, res = run(False)
    exact = sum(1 for _, a, r in res if r['수수료'] == a)
    within = sum(1 for _, a, r in res if r['수수료'] and max(r['수수료'], a) / min(r['수수료'], a) <= 1.67)
    print(f'[1] 확정표 없이: 정확 일치 {exact}/54 (기준 41), 1.67배 이내 {within}/54 (기준 48)')
    if exact < 41 or within < 48:
        ok = False
        for q, a, r in res:
            if r['수수료'] != a: print('   불일치', q, a, r['수수료'], r['등급'])

    local, res = run(True)
    miss = []
    for q, a, r in res:
        rows, _, _ = E.client_rows([r], local)
        fees = {int(x[2].replace(',', '')) for x in rows}
        if a not in fees: miss.append((q, a, sorted(fees)))
    print(f'[2] 확정표 사용: 정답 금액이 고객 행에 포함 {54 - len(miss)}/54 (기준 54)')
    for m in miss: print('   누락', m)
    ok &= not miss

    orig = os.environ.get('ORIGINAL_ENGINE')
    if orig and os.path.exists(orig):
        with tempfile.TemporaryDirectory() as t:
            q = os.path.join(t, 'q.csv')
            with open(q, 'w', encoding='utf-8') as f:
                f.write('품목\n' + '\n'.join(c for c, _ in load_cases()) + '\n식기세척기\n소파\n다이슨\n목검\n')
            outs = []
            for eng in (orig, os.path.join(ROOT, 'engine', 'engine.py')):
                c = os.path.join(t, 'c.csv')
                p = subprocess.run([sys.executable, eng, '--local', D('gwacheon_ordinance.csv'), '--nat', D('nat_snap.tsv'),
                                    '--query', q, '--out', os.path.join(t, 'o.csv'), '--client', c,
                                    '--confirmed', D('gwacheon_confirmed.csv')], capture_output=True, text=True)
                outs.append((open(c, 'rb').read(), open(os.path.join(t, 'o.csv'), 'rb').read(), p.stderr))
            same = outs[0] == outs[1]
            print(f'[3] CLI 출력 원본 엔진과 동일: {same}')
            ok &= same
    print('PASS' if ok else 'FAIL')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
