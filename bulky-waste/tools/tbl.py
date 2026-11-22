import re, sys, urllib.request, html
from html.parser import HTMLParser
UA={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120 Safari/537.36','Accept-Language':'ko-KR'}
def get(url, data=None, tries=4):
    import time
    for i in range(tries):
        try: return _get(url, data)
        except Exception as e:
            if i==tries-1: raise
            time.sleep(2*(i+1))
def _get(url, data=None):
    req=urllib.request.Request(url, data=data.encode() if data else None, headers=dict(UA, **({'Content-Type':'application/x-www-form-urlencoded'} if data else {})))
    raw=urllib.request.urlopen(req, timeout=30).read()
    m=re.search(rb'charset=["\']?([\w-]+)', raw[:4000])
    enc=m.group(1).decode() if m else 'utf-8'
    try: return raw.decode(enc, errors='replace')
    except LookupError: return raw.decode('utf-8','replace')
class T(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True); s.tables=[]; s.st=[]; s.row=None; s.cell=None; s.links=[]; s.a=None
    def handle_starttag(s,t,a):
        a=dict(a)
        if t=='table': s.st.append([])
        elif t=='tr' and s.st: s.row=[]
        elif t in('td','th') and s.row is not None: s.cell=[]; s.span=int(a.get('rowspan') or 1)
        elif t=='br' and s.cell is not None: s.cell.append(' ')
        elif t=='a': s.a=[a.get('href') or a.get('onclick') or '',[]]
    def handle_endtag(s,t):
        if t in('td','th') and s.cell is not None and s.row is not None:
            s.row.append(re.sub(r'\s+',' ',''.join(s.cell)).strip()); s.cell=None
        elif t=='tr' and s.row is not None and s.st:
            if any(s.row): s.st[-1].append(s.row)
            s.row=None
        elif t=='table' and s.st:
            x=s.st.pop(); 
            if x: s.tables.append(x)
        elif t=='a' and s.a:
            s.links.append((''.join(s.a[1]).strip(), s.a[0])); s.a=None
    def handle_data(s,d):
        if s.cell is not None: s.cell.append(d)
        if s.a is not None: s.a[1].append(d)
def parse(text):
    p=T(); p.feed(text); return p
if __name__=='__main__':
    t=get(sys.argv[1], sys.argv[2] if len(sys.argv)>2 and sys.argv[2] else None)
    p=parse(t)
    for i,tb in enumerate(p.tables):
        print(f'--- table {i} rows {len(tb)}')
        for r in tb[:6]: print(r)
    pg=[l for l in p.links if re.search(r'page|cp=|pageIndex|goPage|fn_|search', l[1], re.I)]
    print('LINKS', pg[:15])
