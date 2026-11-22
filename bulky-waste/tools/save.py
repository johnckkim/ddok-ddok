import csv, json, os, re
OUT=__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'..','data','collected')
def fee(v):
    s=re.sub(r'[^\d]','',str(v)); return int(s) if s else None
def save(key, name, url, rows, note='', date='', stype='홈페이지'):
    seen=set(); clean=[]
    for it,sp,fe in rows:
        it=re.sub(r'\s+',' ',str(it)).strip(); sp=re.sub(r'\s+',' ',str(sp or '')).strip()
        if re.fullmatch(r'(\S )+\S', sp): sp=sp.replace(' ','')
        if sp in ('','-'): sp='모든규격'
        f=fee(fe)
        if not it or f is None: continue
        k=(it,sp,f)
        if k in seen: continue
        seen.add(k); clean.append(k)
    with open(f'{OUT}/{key}.csv','w',encoding='utf-8',newline='') as fh:
        w=csv.writer(fh); w.writerow(['품목','규격','수수료']); w.writerows(clean)
    json.dump({'name':name,'source_url':url,'source_type':stype,'basis_date':date or '2026-11-22 (페이지 조회일)','rows':len(clean),'note':note},
              open(f'{OUT}/{key}.json','w',encoding='utf-8'),ensure_ascii=False)
    print(key, len(clean))
