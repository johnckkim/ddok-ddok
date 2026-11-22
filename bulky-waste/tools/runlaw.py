import json, sys
from law import collect
from save import save
T=[('서울','강북구','서울'),('서울','광진구','서울'),('서울','금천구','서울'),('서울','도봉구','서울'),('서울','마포구','서울'),('서울','서대문구','서울'),
   ('서울','성동구','서울'),('서울','송파구','서울'),('서울','은평구','서울'),('경기','성남시','경기'),('경기','의정부시','경기'),('경기','부천시','경기'),('경기','의왕시','경기'),
   ('대구','군위군',''),('경북','김천시',''),('경북','문경시',''),('경북','영양군',''),('경남','밀양시',''),('경남','통영시',''),('전남','함평군',''),('전남','곡성군',''),
   ('전남','나주시',''),('전북','순창군',''),('전북','부안군',''),('전북','정읍시',''),('전북','김제시',''),('충남','논산시',''),('충남','서천군',''),('충남','태안군',''),
   ('강원','횡성군',''),('강원','고성군','강원')]
FULL={'서울':'서울특별시','경기':'경기도','대구':'대구광역시','경북':'경상북도','경남':'경상남도','전남':'전남광주통합특별시','전북':'전북특별자치도','충남':'충청남도','강원':'강원특별자치도'}
only=set(sys.argv[1:])
res={}
for sd,mn,flt in T:
    if only and mn not in only: continue
    try:
        r,log=collect(mn, flt)
    except Exception as e:
        print(json.dumps({'muni':mn,'error':str(e)[:200]},ensure_ascii=False)); continue
    print(json.dumps(log,ensure_ascii=False), flush=True)
    if r:
        rows,byl,url,seq,title=r
        t=' '.join(title.split())
        date=''
        import re
        m=re.search(r'(\d{4})\. (\d{1,2})\. (\d{1,2})\.', t)
        if m: date=f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d} 공포'
        save(f'{sd}_{mn}', f'{FULL[sd]} {mn}', f'https://www.law.go.kr/LSW/ordinInfoP.do?ordinSeq={seq}', rows,
             f'국가법령정보센터 현행 자치법규 「{t[:60]}」 {byl}', date=date, stype='조례 별표')
