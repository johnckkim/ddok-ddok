import re, sys, json, os, io, zipfile, urllib.parse, urllib.request, html
from playwright.sync_api import sync_playwright
from hwp import tables as hwp_tables
DL=__import__('os').environ.get('DL_DIR','/tmp/bulky-dl')
os.makedirs(DL, exist_ok=True)
UA={'User-Agent':'Mozilla/5.0 Chrome/120','Referer':'https://www.law.go.kr/'}
def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
def hwpx_tables(data):
    z=zipfile.ZipFile(io.BytesIO(data)); out=[]
    for n in sorted(x for x in z.namelist() if re.match(r'Contents/section\d+\.xml',x)):
        x=z.read(n).decode('utf-8','replace')
        for tb in re.findall(r'<hp:tbl\b.*?</hp:tbl>', x, re.S):
            cells={}
            for tc in re.findall(r'<hp:tc\b.*?</hp:tc>', tb, re.S):
                a=re.search(r'colAddr="(\d+)"\s+rowAddr="(\d+)"', tc); s=re.search(r'colSpan="(\d+)"\s+rowSpan="(\d+)"', tc)
                if not a: continue
                txt=' '.join(html.unescape(t) for t in re.findall(r'<hp:t>(.*?)</hp:t>', tc, re.S))
                cells[(int(a.group(2)),int(a.group(1)))]=(txt,int(s.group(1)) if s else 1,int(s.group(2)) if s else 1)
            if not cells: continue
            R=max(r for r,c in cells)+1; C=max(c for r,c in cells)+1; g=[['']*C for _ in range(R)]
            for (r,c),(v,cs,rs) in cells.items():
                for dr in range(rs):
                    for dc in range(cs):
                        if r+dr<R and c+dc<C: g[r+dr][c+dc]=v.strip()
            out.append(g)
    return out
def pdf_tables(data):
    import pdfplumber; out=[]
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for p in pdf.pages:
            for t in p.extract_tables():
                out.append([[ (c or '').strip() for c in r] for r in t])
    return out
def file_tables(data):
    if data[:8]==b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        p=f'{DL}/tmp.hwp'; open(p,'wb').write(data); return hwp_tables(p)
    if data[:2]==b'PK': return hwpx_tables(data)
    if data[:4]==b'%PDF': return pdf_tables(data)
    return []
ITEM=re.compile(r'품\s*목|품\s*명|품\s*별|제\s*품\s*명|폐기물\s*명|명\s*칭|물\s*품')
FEE=re.compile(r'수\s*수\s*료|금\s*액|요\s*금|단\s*가')
SPEC=re.compile(r'규\s*격|기\s*준|크\s*기|용\s*량')
def fee_rows(g):
    """표 → [(품목,규격,금액)]. 머리행에서 열 위치를 찾고, 좌우로 반복된 표(두 묶음)도 처리."""
    for hi in range(min(3,len(g))):
        h=g[hi]
        fees=[i for i,c in enumerate(h) if FEE.search(c)]
        items=[i for i,c in enumerate(h) if ITEM.search(c)]
        if not fees or not items: continue
        rows=[]
        for fi in fees:
            ii=max([i for i in items if i<fi] or [None]) if any(i<fi for i in items) else None
            if ii is None: continue
            sp=[i for i,c in enumerate(h) if SPEC.search(c) and ii<i<fi]
            si=sp[0] if sp else None
            for r in g[hi+1:]:
                if fi>=len(r): continue
                it=r[ii]; f=r[fi]; s=r[si] if si is not None else ''
                if not re.search(r'\d', f or ''): continue
                it=' '.join((it or '').split())
                if re.fullmatch(r'(\S )+\S', it): it=it.replace(' ','')
                fs=re.findall(r'\d[\d,]*', f.replace('\n',' '))
                ss=[x.strip() for x in (s or '').split('\n') if x.strip()]
                if len(fs)>1 and len(ss)==len(fs):
                    rows+= [(it,a,b2) for a,b2 in zip(ss,fs)]
                elif len(fs)>1 and not ss:
                    continue
                else:
                    rows.append((it,' '.join(ss),fs[0] if fs else f))
        if rows: return rows
    return []
def search(pg, muni, sido):
    q=urllib.parse.quote(f'{muni} 폐기물')
    pg.goto(f'https://www.law.go.kr/LSW/ordinSc.do?menuId=3&subMenuId=27&tabMenuId=139&query={q}', wait_until='networkidle', timeout=60000)
    rows=pg.eval_on_selector_all('tr', "els=>els.map(e=>[e.innerText, (e.querySelector('a[onclick*=ordinInfPop]')||{}).getAttribute ? e.querySelector('a[onclick*=ordinInfPop]').getAttribute('onclick') : ''])")
    out=[]
    for txt,oc in rows:
        m=re.search(r"ordinInfPop\('(\d+)'", oc or '')
        if not m: continue
        t=' '.join(txt.split())
        if muni not in t or (sido and sido not in t): continue
        title=re.search(r'(\S*'+re.escape(muni[:2])+r'\S*[^\t]*?(?:조례|규칙))', t)
        out.append((m.group(1), t))
    return out
def ordin_files(pg, seq):
    pg.goto(f'https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq={seq}', wait_until='domcontentloaded', timeout=60000); pg.wait_for_timeout(2500)
    try: pg.click('text=별표/서식', timeout=5000); pg.wait_for_timeout(2500)
    except Exception: pass
    h=pg.content()
    title=re.search(r'<title>(.*?)</title>', h, re.S)
    fl=[]
    for m in re.finditer(r'flDownload\.do\?gubun=ELIS&(?:amp;)?flSeq=(\d+)&(?:amp;)?flNm=([^"\'&\s<]+)', h):
        k=(m.group(1), urllib.parse.unquote_plus(html.unescape(m.group(2))))
        if k not in fl: fl.append(k)
    return fl
def collect(muni, sido=''):
    log={'muni':muni,'tried':[]}
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path='/opt/pw-browsers/chromium', args=['--no-sandbox'])
        pg=b.new_page(locale='ko-KR')
        cands=search(pg, muni, sido)
        def score(t):
            s=0
            if '음식물' in t or '영농' in t or '처리시설' in t or '기금' in t or '건설' in t or '재활용' in t and '관리' not in t: s-=10
            if '폐기물' in t and ('관리' in t or '수수료' in t or '배출' in t): s+=5
            if '규칙' in t: s-=1
            return s
        cands=sorted(cands, key=lambda c:-score(c[1]))
        for seq,t in cands[:3]:
            if score(t)<0: continue
            files=ordin_files(pg, seq)
            log['tried'].append({'seq':seq,'title':t[:80],'files':len(files)})
            best=None
            for fseq,fnm in files:
                if '연혁' in fnm: continue   # [연혁] 파일은 옛 표 — 현행 별표만 읽는다
                url=f'https://www.law.go.kr/LSW/flDownload.do?gubun=ELIS&flSeq={fseq}&flNm={urllib.parse.quote(fnm)}'
                try: data=fetch(url)
                except Exception as e: continue
                try: tbs=file_tables(data)
                except Exception as e: continue
                rows=[]
                for g in tbs: rows+=fee_rows(g)
                if len(rows)>=20 and (best is None or len(rows)>len(best[0])):
                    best=(rows, fnm, url, seq, t)
            if best:
                b.close(); log['found']={'rows':len(best[0]),'byl':best[1],'seq':best[3]}
                return best, log
        b.close()
    return None, log
if __name__=='__main__':
    r,log=collect(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else '')
    print(json.dumps(log, ensure_ascii=False))
    if r: print(r[0][:8])
