#!/usr/bin/env python3
"""대형폐기물 조례 미등록 품목 수수료 산정 엔진 (stdlib only)
입력: 지자체 조례 가격표 CSV(품목,규격,수수료) + 전국 표준데이터 요약 TSV + 질의 CSV(품목[,규격][,관찰금액])
출력: 4칸(분류,품목,규격,수수료) + 근거(등급·경로·유사품목·전국통계·신뢰도)
"""
import csv, re, math, sys, argparse, statistics as st

SYN = [  # 표기 변형 → 대표형 (정규화 후 적용)
 ('씽크','싱크'),('장농','장롱'),('쇼파','소파'),('카페트','양탄자'),('카펫트','양탄자'),('카펫','양탄자'),('러그','양탄자'),
 ('렌지','레인지'),('텔레비젼','티비'),('텔레비전','티비'),('tv','티비'),('캐비넷','캐비닛'),('케비넷','캐비닛'),
 ('트램폴린','트램펄린'),('에어콘','에어컨'),('페이트','페인트'),('빳레트','파레트'),('파렛트','파레트'),('팔레트','파레트'),
 ('스텝퍼','스테퍼'),('올겐','오르간'),('올갠','오르간'),('메트리스','매트리스'),('책꽃이','책꽂이'),('밥통','밥솥'),
 ('화일','파일'),('칼라','컬러'),('베게','베개'),('후라이','프라이'),('전자레인지','전자레인지'),('스치로폼','스티로폼'),
 # 품목이 하나로 정해지는 상품명·브랜드 라인 → 일반 명칭
 ('스탠바이미','이동식티비'),('바디프렌드','안마의자'),('워시타워','세탁기'),('에어드레서','의류관리기'),('룸바','로봇청소기'),
]
# 여러 품목에 걸치는 브랜드·막연한 표현 → 금액을 내지 않고 쇼핑몰 확인(4-2절)부터
AMBIG=('다이슨','코웨이','비스포크','오브제','삼성','엘지','lg','이케아','한샘','시몬스','일룸','쿠쿠','위닉스','필립스','샤오미',
       '그거','저거','이거','큰거','작은거','큰기계','작은기계','큰물건','작은물건','뭔지','모르')
VAGUE={'기계','물건','가전','가구','세트','제품','가전제품','전자제품','기구'}   # 이 말만 단독으로 오면 확인
def norm(s):
    s = str(s or '').lower()
    s = re.sub(r'\(.*?\)|\[.*?\]', '', s)
    s = re.sub(r'[\s·,./\-_~:;"\'※]', '', s)
    for a, b in SYN: s = s.replace(a, b)
    return s

STOP={'모든규격','일반','이상','미만','이하','초과','기준','등','형','모든','규격','방문','짝은','개'}
def tokens(name):
    """조례 품명 '책장,진열장,장식장,수납장 tv 다이', '침대(침대틀)' → 각 품목 토큰(괄호 안 하위품목 포함)"""
    name=str(name)
    inner=' '.join(re.findall(r'\((.*?)\)', name))
    base = re.sub(r'\(.*?\)', ' ', name)
    out=set()
    for chunk in (base, inner):
        for p in re.split(r'[,·/]|\s+', chunk)+re.split(r'[,·/]', chunk):   # 낱말 + 띄어쓴 묶음('매트리스 토퍼'→'매트리스토퍼')
            t=norm(p)
            if len(t)>=2 and t not in STOP and not re.search(r'\d',t):
                out.add(t)
                if t.endswith('류') and len(t)>=3: out.add(t[:-1])   # 장난감류→장난감, 가방류→가방
    if norm(base): out.add(norm(base))   # 1글자 품목('상')도 전체명으로는 남긴다
    bt=norm(base)
    for i in re.split(r'[,·/]|\s+', inner):                          # '의자(안마)'→'안마의자', '침대(돌)'→'돌침대'
        i=norm(i)
        if i and bt and not re.search(r'\d',i) and i not in STOP and not i.endswith(bt): out.add(i+bt)
    return out

# ---------- 가격 격자: 조례에 실제 쓰인 금액만 허용 ----------
def snap(x, grid):
    """로그 거리 최솟값 격자점. 동률이면 큰 값(수거비 보전)"""
    return min(grid, key=lambda g: (abs(math.log(g) - math.log(x)), -g))
def snap_floor(x, grid):
    """통계 추정은 지역 격자에서 x 이하 최댓값(주민 부담 보수적). x가 최솟값보다 작으면 최솟값"""
    lo=[g for g in grid if g<=x*1.05]
    return max(lo) if lo else min(grid)
def next_step(p, grid, ratio=1.6):
    """상위 구간 금액: p×1.6 이상인 최소 격자점"""
    up = [g for g in grid if g >= p * ratio]
    return min(up) if up else max(grid)

# ---------- 유사품목 사전 (질의 키워드 → 조례 품목 키워드, 근거) ----------
ANALOG = [
 # 가전
 ('식기세척기','세탁기'),('의류건조기','세탁기'),('건조기','세탁기'),('의류관리기','세탁기'),('스타일러','세탁기'),
 ('제습기','가습기'),('인덕션','가스오븐레인지'),('전기레인지','가스오븐레인지'),('가스레인지','가스오븐레인지'),('바비큐그릴','가스오븐레인지'),
 ('냉동고','냉장고'),('와인셀러','냉장고'),('쇼케이스','냉장고'),('자판기','냉장고'),('자동판매기','냉장고'),
 ('냉온수기','정수기'),('연수기','정수기'),('로봇청소기','진공청소기'),
 ('에어프라이','전자레인지'),('젖병소독기','전자레인지'),('음식물처리기','전기밥솥'),('맥주','전기밥솥'),
 ('믹서','커피머신'),('토스터','커피머신'),('전기포트','커피머신'),('원액기','커피머신'),('녹즙기','커피머신'),
 ('노트북','컴퓨터'),('태블릿','컴퓨터'),('스캐너','프린터'),('복합기','프린터'),('앰프','스피커'),
 ('노래방','전축'),('홈시어터','전축'),('후드','다리미'),('환풍기','다리미'),('체중계','다리미'),('프로젝터','비디오'),
 ('반신욕기','욕조'),('온수매트','전기장판'),('전기매트','전기장판'),('전기담요','전기장판'),('히터','난로'),
 # 가구·유아
 ('아기침대','침대틀'),('2층침대','침대틀'),('벙커침대','침대틀'),('빈백','소파'),('리클라이너','소파'),('소파베드','소파'),('스툴','소파'),
 ('하이체어','보행기'),('바운서','보행기'),('쏘서','보행기'),('점퍼루','보행기'),('웨건','유모차'),('손수레','유모차'),('카트','유모차'),
 ('유아매트','옥매트'),('폴더매트','옥매트'),('놀이매트','옥매트'),
 ('기저귀갈이대','상'),('안전문','상'),('평상','식탁'),('야전침대','상'),('접이식테이블','상'),('나무판자','상'),
 ('선반','수납장'),('카메라보관함','신발장'),('제습함','신발장'),('캣타워','신발장'),('사물함','신발장'),('공간박스','책꽂이'),('컬러박스','책꽂이'),
 ('안내데스크','책상'),('카운터','책상'),
 # 운동·악기·기타
 ('트램펄린','운동기구'),('거꾸리','운동기구'),('벤치','운동기구'),('윗몸일으키기','운동기구'),('샌드백','운동기구'),('턱걸이','운동기구'),('발마사지기','운동기구'),
 ('스노보드','스키'),('스케이트','스키'),('인라인','스키'),('골프채','스키'),('목발','스키'),
 ('드럼','피아노'),('현악기','기타'),
 ('화이트보드','간판'),('게시판','입간판'),('칠판','간판'),('태양광','간판'),('프로젝터스크린','블라인드'),
 ('천막','텐트'),('어닝','텐트'),('에어매트','고무통'),('기름탱크','물탱크'),('드럼통','고무통'),('쓰레기통','플라스틱류'),
 ('아크릴','플라스틱류'),('포맥스','플라스틱류'),('도배지','장판류'),('벽지','장판류'),('인조잔디','장판류'),('카시미론','단열재'),('솜','단열재'),
 ('쿠션','인형류'),('바디필로우','이불'),('커튼','이불'),('화환','액자'),('캐리어','가방류'),('개집','고무통'),('캣휠','고무통'),
]
ANALOG += [('토퍼','매트리스'),('라텍스','매트리스'),('온수매트','옥매트'),('온수기','정수기')]
ANALOG.sort(key=lambda x: -len(x[0]))          # '프로젝터스크린'이 '프로젝터'보다 먼저
SMALL=('우산','토너','카트리지','헬멧','라켓','방석','도마','양산')   # 1개당 최저가(격자 최솟값) 허용 소형품
PARTS=('필터','부속','부품','커버','거치대','받침')               # 본체가 아닌 부속 → 품목 최저가
# 규격 구간을 나눌 때 쓰는 기준 (품목 키워드 → (차원, 경계, 단위))
TIER = [
 (('크리스마스트리','미끄럼틀','캣타워','보관함','제습함','기저귀갈이대'),'높이',1.0,'m'),
 (('화이트보드','칠판','스크린'),'가로',2.0,'m'),
 (('판자','합판','아크릴','포맥스'),'길이',1.2,'m'),
 (('온수기','물탱크','냉동고','와인셀러'),'용량',50,'L'),
 (('파라솔',),'지름',2.0,'m'),
 (('덤벨','바벨','장난감','절구'),'무게',10,'kg'),
 (('쓰레기통',),'용량',20,'L'),
 (('음식물처리기',),'높이',0.7,'m'),
 (('킥보드',),'높이',1.0,'m'),
]

def load_local(path):
    rows=[]
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            try: fee=int(re.sub(r'[^\d]','',r['수수료']))
            except: continue
            if fee<=0: continue
            rows.append({'name':r['품목'].strip(),'spec':(r.get('규격') or '').strip(),'fee':fee,'tok':tokens(r['품목'])})
    return rows

def load_nat(path):
    nat={}
    with open(path, encoding='utf-8') as f:
        for line in f:
            f_=line.rstrip('\n').split('\t')
            if len(f_)<5 or not f_[1].isdigit(): continue
            k,n,med,p25,p75=f_[:5]; mn,mx=(f_[5],f_[6]) if len(f_)>=7 else (p25,p75)   # 스킬 내장 스냅샷은 5칸
            nat[k]=dict(n=int(n),med=float(med),p25=float(p25),p75=float(p75),min=float(mn),max=float(mx))
    return nat

def nat_lookup(q, nat):
    k=norm(q)
    if k in nat: return k,nat[k]
    c=[(v['n'],kk) for kk,v in nat.items() if len(kk)>=2 and (kk in k or k in kk)]
    if not c: return None,None
    n,kk=max(c); return kk,nat[kk]

def calibrate(local, nat):
    """지역 가격 수준 k = exp(median(log(지역/전국))). 조례 품목 중 전국 통계(n>=5)가 있는 것만."""
    r=[]
    for row in local:
        for t in row['tok']:
            if t in nat and nat[t]['n']>=5:
                r.append(math.log(row['fee']/nat[t]['med'])); break
    if len(r)<5: return 1.0,len(r),None
    m=st.median(r); mad=st.median([abs(x-m) for x in r])
    return math.exp(m),len(r),mad

def local_exact(q, local):
    k=norm(q)
    hit=[row for row in local if k in row['tok']]
    return hit

def local_head(q, local):
    """한국어 합성명사는 끝말이 상위어: '캠핑의자'→'의자'. 가장 긴 접미 일치."""
    k=norm(q); best=None
    for row in local:
        for t in row['tok']:
            if len(t)>=2 and k.endswith(t) and k!=t and (best is None or len(t)>len(best[0])):
                best=(t,row)
    if not best: return []
    return [row for row in local if best[0] in row['tok']]

def local_analog(q, local):
    k=norm(q); hits=[]; first=None
    for qk,lk in ANALOG:
        if first and len(norm(qk))<len(norm(first)): break     # 가장 긴 키워드 묶음만
        if norm(qk) in k:
            key=norm(lk)
            hit=[row for row in local if key in row['tok']]                     # 토큰 완전일치 우선
            if not hit and len(key)>=2:
                hit=[row for row in local if any(key in t for t in row['tok'])]  # 2글자 이상만 부분일치
            if hit:
                first=first or qk; hits+=[h for h in hit if h not in hits]
    return (first and hits and first), hits

def rep_fee(rows):
    """유사품목이 규격별로 여러 줄이면 최하위 구간(가정 배출 기본형) 금액"""
    return min(r['fee'] for r in rows)

def price(q, spec, local, nat, k, grid, observed=None, confirmed=None):
    out={'품목':q,'규격':spec or '모든규격'}
    if (any(w in norm(q) for w in AMBIG) or norm(q) in VAGUE) and not observed:                 # 무엇인지부터 확인
        out.update(등급='L? 품목 확인 필요',수수료=0,경로='브랜드·막연한 표현',신뢰도=0,조치='쇼핑몰 확인 후 예/아니오 질문(4-2절)',확인=True)
        return out
    fees=[r['fee'] for r in local]
    cgrid=sorted({f for f in fees if fees.count(f)>=2}) or grid       # 조례에 2회 이상 쓰인 금액
    item_floor=min(f for f in cgrid if f>=2000) if any(f>=2000 for f in cgrid) else min(cgrid)
    mode=max(set(fees),key=lambda f:(fees.count(f),-f))                 # 조례 최빈 금액
    cx=local_exact(q, confirmed or [])                                  # 이미 확정한 금액(제출표·사용자 결정)
    ex=local_exact(q, local)
    if cx and not ex and not observed:                                  # 조례에 없는 품목 → 확정 금액이 최우선
        out.update(등급='L1 확정 금액',수수료=rep_fee(cx),경로='확정 금액',신뢰도=1.0,조치='확정 금액 사용',
                   확정=sorted({(r['spec'] or '모든규격',r['fee']) for r in cx},key=lambda x:x[1]))
        return out
    if ex:
        out.update(등급='L0 조례 등재',수수료=rep_fee(ex),경로='조례 직접',유사=';'.join(f"{r['name']} {r['spec']} {r['fee']}" for r in ex[:4]),신뢰도=1.0,조치='미등록 목록 제외(품명 보완만 검토)')
        add=[r for r in cx if norm(r['name'])==norm(q) and '(' not in r['name']]   # 조례 품목에 확정표가 새 규격을 더한 경우(유아매트 1인용)
        if add:
            out['확정']=sorted({(r['spec'] or '모든규격',r['fee']) for r in ex+add},key=lambda x:x[1])
            out['수수료']=out['확정'][0][1]; out['조치']='조례 + 확정 규격'
        return out
    hd=local_head(q, local)
    lk,an=local_analog(q, local)
    pa=None; src=None
    tiers=[]
    if hd: pa=rep_fee(hd); src='상위어 '+hd[0]['name']; tiers=sorted({r['fee'] for r in hd})
    elif an: pa=rep_fee(an); src='유사품목 '+'/'.join(sorted({r['name'] for r in an})); tiers=sorted({r['fee'] for r in an})
    out['유사구간']=tiers
    nk,ns=nat_lookup(q, nat)
    ps=snap_floor(ns['med']*k, cgrid) if ns and ns['n']>=3 else None
    if observed:
        p=snap(observed,grid); lvl='L1 업체 안내가'; conf=0.95; path='수거업체 실제 안내 금액'
    elif pa and ps:
        agree=abs(math.log(pa/ps))<=math.log(2)
        p=pa; lvl='L2 유사품목' if agree else 'L2* 유사품목(통계와 2배 이상 차이)'; conf=0.85 if agree else 0.6; path=src
    elif pa:
        p=pa; lvl='L2 유사품목'; conf=0.75; path=src
    elif ps:
        p=ps; lvl='L3 전국 통계×지역 보정'; conf=min(0.7,0.4+0.03*ns['n']); path=f"전국 {nk} 중앙값 {int(ns['med'])}×k"
    else:
        p=mode; lvl='L4 기본 추정'; conf=0.3; path=f'근거 없음: 조례 최빈 금액 {mode}'
    kq=norm(q); powered=False
    if '전동' in kq and not observed:                                   # 전동형은 배터리·모터로 무겁다 → 수동형 최고 구간 이상, 단일 금액
        base=kq.replace('전동','')
        b=[r for r in (confirmed or [])+local if base in r['tok']]
        if b:
            powered=True; top=max(r['fee'] for r in b)
            if top>p: p=top; lvl='L2 전동형'; conf=max(conf,0.8); path=f'수동형 {b[0]["name"]} 최고 구간 {top} 이상'
        else:                                                           # 수동형도 없으면 한 단계 위 단일 금액, 사람 확인
            powered=True; p=next_step(p,cgrid); lvl='L2* 전동형(수동형 없음)'; conf=0.5; path+=' → 전동형 한 단계 상향'
    if any(w in kq for w in PARTS) and not observed:
        p=item_floor; lvl='L2 부속품'; conf=max(conf,0.7); path='부속·소모품 → 품목 최저가'
    if any(w in kq for w in SMALL) and not observed:
        p=min(cgrid); lvl='L3 소형품'; conf=max(conf,0.6); path='봉투 배출 가능 소형품 → 격자 최솟값(봉투 배출 우선 안내)'
    elif p<item_floor and not observed and not re.search(r'kg|㎏',(spec or '')):
        p=item_floor; path+=' (품목 최저가로 올림)'
    out.update(수수료=p,등급=lvl,경로=path,신뢰도=round(conf,2),
               전국=(f"{nk} n={ns['n']} 중앙{int(ns['med'])} IQR {int(ns['p25'])}~{int(ns['p75'])}" if ns else '-'),
               통계추정=ps or '-',유사=src or '-')
    # 구간 분할 판단: 전국 IQR 폭이 2배 이상이거나 품목 유형이 크기 의존형
    split=None
    if powered or any(w in kq for w in PARTS+SMALL):  # 전동형·부속·소형품은 구간을 나누지 않는다
        out['조치']='단일 금액'; return out
    if ns and ns['n']>=5 and ns['p75']>=2*ns['p25']: split='전국 금액 분산 큼(p75/p25≥2)'
    for keys,dim,b,u in TIER:
        if any(kw in kq for kw in keys):
            up=[t for t in tiers if t>p]                 # 유사품목에 상위 구간이 있으면 그 금액, 없으면 1.6배 격자
            split=(split+'; ' if split else '')+f"{dim} {b}{u} 기준"; out['구간']=(dim,b,u,p,min(up) if up else next_step(p,grid))
            break
    out['조치']=('구간 분할 권장: '+split) if split else '단일 금액'
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--local',required=True); ap.add_argument('--nat',required=True)
    ap.add_argument('--query',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--confirmed',help='이미 확정한 금액 CSV(품목,규격,수수료). 예: 직전 제출표')
    ap.add_argument('--client',help='고객 제출용 CSV(품목,규격,수수료(원),배출 안내). 근거 열 없음')
    a=ap.parse_args()
    local=load_local(a.local); nat=load_nat(a.nat); conf_rows=load_local(a.confirmed) if a.confirmed else []
    grid=sorted({r['fee'] for r in local})
    k,n,mad=calibrate(local,nat)
    print(f'조례 {len(local)}행, 가격격자 {grid}, k={k:.3f} (보정쌍 {n}, MAD {mad})',file=sys.stderr)
    res=[]
    with open(a.query,encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            obs=int(r['관찰금액']) if r.get('관찰금액') else None
            res.append(price(r['품목'],r.get('규격'),local,nat,k,grid,obs,conf_rows))
    cols=['품목','규격','수수료','등급','신뢰도','경로','유사','유사구간','통계추정','전국','구간','조치']
    with open(a.out,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore'); w.writeheader(); w.writerows(res)
    if a.client: write_client(res,a.client)

def fmt_bound(b,u):
    """1.0m→1m, 1.2m→120cm, 0.7m→70cm, 50L→50L"""
    if u=='m' and b!=int(b): return f'{round(b*100)}cm'
    return f'{int(b) if b==int(b) else b}{u}'
def client_rows(res, local=None):
    """고객용 행 생성(파일·stderr 없이 반환). rows=[[품목,규격,수수료,안내]], review=검토 필요 품목, ask=품목 확인 필요.
    local(조례 행)을 주면 조례 등재(L0) 품목은 대표 1줄 대신 조례의 규격별 현행 금액을 모두 펼친다."""
    rows=[]; review=[]; ask=[]
    for r in res:
        q=r['품목']; kq=norm(q); note=''
        if r.get('확인'): ask.append(q); continue          # 품목이 불분명 → 고객 파일에 넣지 않고 확인 질문부터
        if r['등급'].startswith('L0'): note='현행 조례 품목'
        elif any(w in kq for w in SMALL): note='종량제봉투에 들어가면 봉투로 배출'
        if any(w in kq for w in ('전동','전기자전거','배터리')): note=(note+', ' if note else '')+'배터리 분리 후 배출'
        if r['등급'].startswith(('L2*','L3 전국','L4')) or r.get('구간'):   # 사람이 금액을 확정해야 하는 것
            review.append(q)
        t=r.get('구간')
        if r.get('확정'):
            rows+= [[q,sp,f'{fe:,}',note] for sp,fe in r['확정']]
        elif local is not None and r['등급'].startswith('L0') and r['규격'] in ('','모든규격'):
            ex=sorted({(x['spec'] or '모든규격',x['fee']) for x in local_exact(q,local)},key=lambda x:x[1])
            rows+= [[q,sp,f'{fe:,}',note] for sp,fe in ex] or [[q,'모든규격',f"{r['수수료']:,}",note]]
        elif t and r['규격'] in ('','모든규격'):
            dim,b,u,lo,hi=t; bb=fmt_bound(b,u)
            rows.append([q,f'{dim} {bb} 미만',f'{lo:,}',note]); rows.append([q,f'{dim} {bb} 이상',f'{hi:,}',note])
        else:
            rows.append([q,r['규격'] or '모든규격',f"{r['수수료']:,}",note])
    return rows, list(dict.fromkeys(review)), list(dict.fromkeys(ask))
def write_client(res,path):
    """고객용: 결과값만. 등급·신뢰도·근거·통계 열은 절대 넣지 않는다. 검토 대상은 화면(stderr)에만 알린다."""
    rows,review,ask=client_rows(res)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f); w.writerow(['품목','규격','수수료(원)','배출 안내']); w.writerows(rows)
    if review: print('보내기 전 검토: '+', '.join(review),file=sys.stderr)
    if ask: print('품목 확인 필요(4-2절 쇼핑몰 확인 → 예/아니오): '+', '.join(ask),file=sys.stderr)
if __name__=='__main__': main()
