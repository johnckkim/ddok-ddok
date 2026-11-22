#!/usr/bin/env python3
"""전국 표준데이터 JSON(rows) → 품목별 요약 TSV. 지자체 수는 (시도,시군구,기관) 중복 없이 센다.
사용: python3 build_nat.py bw.json nat.tsv [제외할 기관명 일부]"""
import json,sys,statistics as st
sys.path.insert(0,__import__('os').path.dirname(__file__))
try:                       # 웹앱에서 패키지로 import 할 때
    from engine.engine import norm
except ImportError:        # CLI: python3 build_nat.py ... (engine.py 와 같은 폴더)
    from engine import norm
def q(v,p):
    v=sorted(v); i=(len(v)-1)*p; lo=int(i); hi=min(lo+1,len(v)-1); return v[lo]+(v[hi]-v[lo])*(i-lo)
def summarize(rows, excl=None):
    """행 목록 → TSV 줄 목록(품목·기관수·중앙값·p25·p75·최소·최대). 웹앱 갱신 기능도 이 함수를 쓴다."""
    agg={}
    for r in rows:
        if excl and excl in (r.get('INSTT_NM') or ''): continue
        if r.get('PAID_FREE_YN')=='무료': continue
        try: fee=int(str(r['FEE']).replace(',',''))
        except: continue
        if fee<=0 or fee>300000: continue
        k=norm(r['LAR_WAS_NM'])
        if len(k)<1: continue
        a=agg.setdefault(k,{'org':set(),'fee':{}})
        org=(r['CTPV_NM'],r['SGG_NM'],r['INSTT_NM']); a['org'].add(org)
        a['fee'].setdefault(org,[]).append(fee)
    out=[]
    for k,a in sorted(agg.items(),key=lambda x:-len(x[1]['org'])):
        per=[min(v) for v in a['fee'].values()]   # 기관별 최저 구간(기본형) 1개씩 → 기관 가중 동일
        out.append('\t'.join(map(str,[k,len(per),st.median(per),q(per,.25),q(per,.75),min(per),max(per)])))
    return out
if __name__=='__main__':
    rows=json.load(open(sys.argv[1]))['rows']; excl=sys.argv[3] if len(sys.argv)>3 else None
    lines=summarize(rows,excl)
    with open(sys.argv[2],'w') as f:
        for l in lines: f.write(l+'\n')
    print(len(lines))
