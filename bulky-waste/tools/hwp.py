import olefile, zlib, struct, sys
def records(data):
    i=0
    while i+4<=len(data):
        h=struct.unpack_from('<I',data,i); h=h[0]; i+=4
        tag=h&0x3ff; lvl=(h>>10)&0x3ff; size=(h>>20)&0xfff
        if size==0xfff: size=struct.unpack_from('<I',data,i)[0]; i+=4
        yield tag,lvl,data[i:i+size]; i+=size
def text(b):
    out=[]; i=0; n=len(b)//2
    w=struct.unpack('<%dH'%n,b[:n*2])
    while i<n:
        c=w[i]
        if c in (10,): out.append('\n'); i+=1
        elif c==13: i+=1
        elif c<32 and c not in (24,25,26,27,28,29,30,31,0):
            i+=8
        elif c<32: i+=1
        else: out.append(chr(c)); i+=1
    return ''.join(out)
def tables(path):
    o=olefile.OleFileIO(path)
    hdr=o.openstream('FileHeader').read(); comp=struct.unpack_from('<I',hdr,36)[0]&1
    secs=sorted([e for e in o.listdir() if e[0]=='BodyText'], key=lambda e:int(e[1][7:]))
    out=[]
    for s in secs:
        d=o.openstream(s).read()
        if comp: d=zlib.decompress(d,-15)
        cur_tbl=None; cell=None; cell_lvl=None
        for tag,lvl,body in records(d):
            if cell is not None and lvl<cell_lvl:
                cell=None
            if tag==71 and body[:4]==b' lbt':
                cur_tbl={}; out.append(cur_tbl)
            elif tag==72 and cur_tbl is not None and len(body)>=16:
                col,row,cs,rs=struct.unpack_from('<4H',body,8)
                cell=[]; cell_lvl=lvl; cur_tbl[(row,col)]=(cell,cs,rs)
            elif tag==67 and cell is not None and lvl>=cell_lvl:
                cell.append(text(body))
    grids=[]
    for t in out:
        if not t: continue
        R=max(r for r,c in t)+1; C=max(c for r,c in t)+1
        g=[['']*C for _ in range(R)]
        for (r,c),(cell,cs,rs) in t.items():
            v='\n'.join(x.strip() for x in cell if x.strip())
            for dr in range(max(rs,1)):
                for dc in range(max(cs,1)):
                    if r+dr<R and c+dc<C: g[r+dr][c+dc]=v
        grids.append(g)
    return grids
if __name__=='__main__':
    for g in tables(sys.argv[1]):
        print('--- table', len(g), 'x', len(g[0]))
        for r in g[:8]: print(r)
