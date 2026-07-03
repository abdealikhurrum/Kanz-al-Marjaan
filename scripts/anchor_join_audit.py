#!/usr/bin/env python3
"""Audit curs ENTRY anchors against each glyph's right-hand connection socket.

The RTL curs feature derives a glyph's advance from its entry-anchor x, so a
right-joining glyph's entry anchor must sit on the baseline connection seam
(the near-vertical stroke that rises from y~0 to the connection height ~170)
at the right edge of the glyph. When the anchor drifts off that socket -- a y
far below the stroke, or an x well past it -- the preceding letter lands short
and the join opens a gap. This was the root cause of every 2.5 join fix
(uniFC88, the bari-yeh finals, glyph2227/2228, glyph1946).

Components are flattened. Glyphs whose right connection is a high curve
(jeem family) have no baseline socket and are not judged here.

  python scripts/anchor_join_audit.py
"""
import re, argparse
from defcon import Font
SRC="sources/KanzAlMarjaan-Regular.ufo"

def flat(font,name,seen=None):
    if seen is None: seen=set()
    if name in seen or name not in font: return []
    seen.add(name); g=font[name]
    out=[[(p.x,p.y,bool(p.segmentType)) for p in c] for c in g]
    for comp in g.components:
        dx,dy=comp.transformation[4],comp.transformation[5]
        out+=[[(x+dx,y+dy,o) for x,y,o in c] for c in flat(font,comp.baseGlyph,set(seen))]
    return out

def right_socket(cs,width):
    best=None
    for c in cs:
        on=[(x,y) for x,y,o in c if o]; n=len(on)
        for i in range(n):
            x0,y0=on[i]; x1,y1=on[(i+1)%n]
            if abs(x1-x0)<=18 and abs(y1-y0)>=90:
                ylo,yhi=sorted((y0,y1))
                if -40<=ylo<=45 and 120<=yhi<=210 and width-140<=(x0+x1)/2<=width+90:
                    x=(x0+x1)/2
                    if best is None or x>best[0]: best=(x,ylo,yhi)
    return best

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--src",default=SRC)
    ap.add_argument("--ytol",type=float,default=45)
    ap.add_argument("--xtol",type=float,default=40)
    a=ap.parse_args()
    font=Font(a.src)
    fea=open(f"{a.src}/features.fea").read()
    pat=re.compile(r"pos cursive (\S+) <anchor ([^>]+)> <anchor ([^>]+)>;")
    hits=[]
    for m in pat.finditer(fea):
        name,ent,_=m.groups()
        if ent.strip()=="NULL" or name not in font: continue
        try: ax=float(ent.split()[0]); ay=float(ent.split()[1])
        except: continue
        w=font[name].width
        if w<=0: continue
        s=right_socket(flat(font,name),w)
        if not s: continue
        sx,ylo,yhi=s
        if ay<ylo-a.ytol or ax>sx+a.xtol:
            hits.append((name,round(ax),round(ay),round(sx),round((ylo+yhi)/2)))
    for name,ax,ay,sx,my in sorted(hits):
        print(f"{name:26} entry=({ax},{ay})  socket_x={sx}  suggest=<{sx} {my}>")
    # --- exit-anchor overhang check (spread class: tatweel etc.) ---
    exits=[]
    for m in pat.finditer(fea):
        name,ent,exi=m.groups()
        if exi.strip()=="NULL" or name not in font: continue
        try: ex=float(exi.split()[0])
        except: continue
        cs=flat(font,name)
        minx=min((x for c in cs for x,y,o in c), default=0)
        # left-connecting glyph whose ink overhangs the origin, with exit anchor on the overhang
        if -110<=minx< -20 and ex < -20:
            exits.append((name,round(ex),round(minx),font[name].width))
    for name,ex,minx,w in sorted(exits):
        print(f"[exit] {name:24} exit_x={ex}  ink_minx={minx}  width={w}  (curs may spread overlap -> gap; want exit_x~0)")
    if exits: print(f"{len(exits)} exit-overhang spread risk(s)")
    print(f"{len(hits)} join defect(s)")
    return 1 if hits else 0

if __name__=="__main__":
    raise SystemExit(main())
