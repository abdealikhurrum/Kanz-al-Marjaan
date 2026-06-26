"""Read orange target dots on joined_sheet.png -> propose anchor edits.

Same empirical calibration as read_marks.py, adapted to joined_sheet geometry
(CW300/CH300/COLS3, left gutter 150, baseline=cy0+CH-110) and tatweel-elicited
positional forms.  The mark attaches to the letter's positional glyph (uniFExx),
whose pos base @t/@b anchor is the edit target.
"""
import os, re, sys
import numpy as np
import uharfbuzz as hb, freetype
from PIL import Image
from fontTools.ttLib import TTFont

TTF = os.environ.get("READ_MARKS_TTF", "fonts/ttf/KanzAlMarjaan-Regular.ttf")
SHEET = sys.argv[1] if len(sys.argv) > 1 else "out/joined_sheet.png"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
CW, CH, HEADER, COLS, GUT, PPEM = 300, 300, 56, 3, 150, 200
TOP, BOT, TAT = 0x064E, 0x0650, 0x0640
SHAPES = [("beh",0x0628,True),("hah",0x062D,True),("seen",0x0633,True),("sad",0x0635,True),
("tah",0x0637,True),("ain",0x0639,True),("feh",0x0641,True),("kaf",0x0643,True),
("lam",0x0644,True),("meem",0x0645,True),("heh",0x0647,True),("noon",0x0646,True),
("dal",0x062F,False),("reh",0x0631,False),("waw",0x0648,False),("alef",0x0627,False)]

def affix(joins, col):
    # returns (prefix, suffix, formname) around the letter; None if blank cell
    if joins:
        return [([],[TAT],"init"),([TAT],[TAT],"medi"),([TAT],[],"fina")][col]
    return [([],[],"isol"),None,([TAT],[],"fina")][col]

data = open(TTF,"rb").read(); hbf = hb.Font(hb.Face(data)); face = freetype.Face(TTF)
UPM = face.units_per_EM; face.set_pixel_sizes(0,PPEM); sc = PPEM/UPM
order = TTFont(TTF).getGlyphOrder(); fea = open(FEA).read()

def posbase(g):
    return re.search(r"pos base %s\s*<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*"
                     r"<anchor (-?\d+) (-?\d+)> mark \@b" % re.escape(g), fea)
def anchors(g): return tuple(map(int, posbase(g).groups()))

def shaped(cps):
    buf = hb.Buffer(); buf.add_codepoints(cps); buf.guess_segment_properties(); hb.shape(hbf,buf)
    gl=[]; names=[]; mnx=1e9; mxx=-1e9; penx=0
    for info,pos in zip(buf.glyph_infos,buf.glyph_positions):
        names.append(order[info.codepoint])
        face.load_glyph(info.codepoint,freetype.FT_LOAD_RENDER); g=face.glyph; bm=g.bitmap
        rx=(penx+pos.x_offset)*sc+g.bitmap_left; ry=-(pos.y_offset)*sc-g.bitmap_top
        if bm.width and bm.rows:
            gl.append((rx,ry,np.frombuffer(bytes(bm.buffer),np.uint8).reshape(bm.rows,bm.width)))
            mnx=min(mnx,rx); mxx=max(mxx,rx+bm.width)
        penx+=pos.x_advance
    return gl,(mnx,mxx),names

def cell_mask(cps, ox, oy):
    img=np.zeros((CH,CW),np.uint8)
    for rx,ry,ink in shaped(cps)[0]:
        px=int(ox+rx); py=int(oy+ry); h,w=ink.shape
        for yy in range(h):
            Y=py+yy
            if 0<=Y<CH:
                row=ink[yy]
                for xx in range(w):
                    X=px+xx
                    if 0<=X<CW and row[xx]>40: img[Y,X]=255
    return img

a=np.asarray(Image.open(SHEET).convert("RGB")).astype(int)
R,G,B=a[:,:,0],a[:,:,1],a[:,:,2]
mark_px=((R>180)&(G<190)&(B<120)&(R-B>70))   # orange/red/yellow target ink
from collections import defaultdict
cells=defaultdict(list)
ys,xs=np.where(mark_px)
for x,y in zip(xs,ys):
    if y<HEADER or x<GUT: continue
    cells[((y-HEADER)//CH, (x-GUT)//CW)].append((x,y))

print(f"{'glyph':10} {'shape/form':16} side cur_anchor      new_anchor      d(px)")
edits={}
for (i,j) in sorted(cells):
    if i>=len(SHAPES): continue
    name,cp,joins=SHAPES[i]; af=affix(joins,j)
    if af is None: continue
    pre,suf,form=af
    base=pre+[cp]+suf
    g=next((n for n in shaped(base)[2] if n not in ("uni0640",) and posbase(n)), None)
    if not g: print(f"{name} {form}: no mark-bearing glyph"); continue
    cx0,cy0=GUT+j*CW, HEADER+i*CH; oy=cy0+CH-110
    _,(mnx,mxx),_=shaped(pre+[cp,TOP,BOT]+suf); ox=cx0+CW/2-(mnx+mxx)/2
    pts=np.array(cells[(i,j)]); tx,ty,bx,by=anchors(g)
    for side in ("top","bot"):
        sel=pts[pts[:,1]<oy] if side=="top" else pts[pts[:,1]>=oy]
        if len(sel)<8: continue
        rx,ry=sel[:,0].mean(), sel[:,1].mean()
        mk=TOP if side=="top" else BOT
        diff=(cell_mask(pre+[cp,mk]+suf,ox-cx0,oy-cy0)>0)&(cell_mask(base,ox-cx0,oy-cy0)==0)
        dys,dxs=np.where(diff)
        if len(dxs)==0: print(f"{g} {side}: no mark ink"); continue
        mlx,mly=dxs.mean()+cx0, dys.mean()+cy0
        cur=(tx,ty) if side=="top" else (bx,by)
        new=(round(cur[0]+(rx-mlx)/sc), round(cur[1]-(ry-mly)/sc))
        edits[f"{g}:{side}"]=new
        print(f"{g:10} {name+'/'+form:16} {side} {str(cur):15} {str(new):15} ({round(rx-mlx)},{round(ry-mly)})")
print("\nEDITS =", edits)
