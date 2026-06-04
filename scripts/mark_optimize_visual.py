"""Before/after visual: place the real fatha (top) / kasra (bottom) at the
current anchor vs an ink-hugging anchor (base ink + GAP) for sample bases."""
import re
import freetype, numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
FEA = "sources/KanzAlMarjaan-Regular.ufo/features.fea"
GAP = 110
SAMPLES = [("uni0628","top"),("uni0633","top"),("uni067E","top"),("uniFE92","top"),
           ("uni0627","top"),("uni0644","top"),("uniFEDE","top"),("uni0637","top"),
           ("uni0648","bot"),("uni0631","bot"),("uni064A","bot"),("uni0646","bot")]

fea = open(FEA).read()
rx = re.compile(r"pos base (\S+)\s*<anchor (-?\d+) (-?\d+)> mark \@t\.uni064B\s*"
                r"<anchor (-?\d+) (-?\d+)> mark \@b\.uni064D_1;", re.S)
ANC = {m.group(1): tuple(map(int, m.group(2,3,4,5))) for m in rx.finditer(fea)}

tt = TTFont(TTF); upm = tt["head"].unitsPerEm
order = tt.getGlyphOrder(); n2g = {n:i for i,n in enumerate(order)}
cmap = tt.getBestCmap()
FATHA = n2g[cmap[0x064E]]; KASRA = n2g[cmap[0x0650]]
MARK_ANCHOR = (114, 0)   # both fatha & kasra markClass anchor x; y≈ink edge

PPEM = 200; face = freetype.Face(TTF); face.set_pixel_sizes(0, PPEM); sc = PPEM/upm

def render(gid):
    face.load_glyph(gid, freetype.FT_LOAD_RENDER); g = face.glyph; bm = g.bitmap
    if not (bm.width and bm.rows): return None
    a = np.frombuffer(bytes(bm.buffer),"uint8").reshape(bm.rows,bm.width)
    return a, g.bitmap_left, g.bitmap_top

def ink_band(gid, x0u, x1u, top):
    r = render(gid)
    if not r: return None
    a,bl,bt = r; m = a>40
    c0 = max(0,int(round(x0u*sc-bl))); c1 = min(a.shape[1],int(round(x1u*sc-bl)))
    if c1<=c0: return None
    rows = np.where(m[:,c0:c1].any(axis=1))[0]
    if not len(rows): return None
    return (bt-(rows.min() if top else rows.max()))/sc

CW,CH = 360,420; cols=4; rows=(len(SAMPLES)+cols-1)//cols
sheet = Image.new("RGB",(cols*CW, rows*CH),"white"); draw=ImageDraw.Draw(sheet)
try: lab=ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf",17)
except: lab=ImageFont.load_default()

def paste(gid, ox, oy_base, dx_u, dy_u, color):
    r = render(gid)
    if not r: return
    a,bl,bt = r; ink=Image.fromarray(a)
    x = int(ox + dx_u*sc + bl); y = int(oy_base - dy_u*sc - bt)
    sheet.paste(color,(x,y),ink)

for i,(gn,kind) in enumerate(SAMPLES):
    if gn not in ANC: continue
    TX,TY,BX,BY = ANC[gn]
    cx=(i%cols)*CW; cy=(i//cols)*CH; ox=cx+150; base=cy+260
    draw.rectangle([cx+4,cy+4,cx+CW-4,cy+CH-4],outline=(230,230,230))
    draw.line([cx,base,cx+CW,base],fill=(170,170,220))
    if kind=="top":
        top=ink_band(n2g[gn],TX-114,TX+423,True);
        optTY=round(top+GAP) if top is not None else TY
        # current (grey base + red fatha)
        paste(n2g[gn],ox,base,0,0,(30,30,30))
        paste(FATHA,ox,base,TX-MARK_ANCHOR[0],TY-MARK_ANCHOR[1],(210,40,40))
        # proposed fatha (green) on same base
        paste(FATHA,ox,base,TX-MARK_ANCHOR[0],optTY-MARK_ANCHOR[1],(30,150,30))
        draw.text((cx+10,cy+8),f"{gn}  TY {TY}->{optTY}",fill="black",font=lab)
        draw.text((cx+10,cy+28),"red=current green=proposed",fill=(120,120,120),font=lab)
    else:
        bot=ink_band(n2g[gn],BX-114,BX+423,False)
        optBY=round(bot-GAP) if bot is not None else BY
        paste(n2g[gn],ox,base,0,0,(30,30,30))
        paste(KASRA,ox,base,BX-MARK_ANCHOR[0],BY-MARK_ANCHOR[1],(210,40,40))
        paste(KASRA,ox,base,BX-MARK_ANCHOR[0],optBY-MARK_ANCHOR[1],(30,150,30))
        draw.text((cx+10,cy+8),f"{gn}  BY {BY}->{optBY}",fill="black",font=lab)
        draw.text((cx+10,cy+28),"red=current green=proposed",fill=(120,120,120),font=lab)

sheet.save("out/11_mark_optimize.png"); print("wrote out/11_mark_optimize.png")
