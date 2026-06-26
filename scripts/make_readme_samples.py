"""Render non-denominational README sample images into documentation/."""
import os, uharfbuzz as hb, freetype
from PIL import Image, ImageDraw, ImageFont
TTF=os.environ.get("README_TTF","/tmp/_kam_readme.ttf")
data=open(TTF,"rb").read(); HB=hb.Font(hb.Face(data)); FACE=freetype.Face(TTF); UPM=FACE.units_per_EM
INK=(20,20,20); GREY=(140,140,140)
def lab(sz):
    try: return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf",sz)
    except: return ImageFont.load_default()
def draw_line(img, text, ppem, x_right, baseline, color=INK):
    FACE.set_pixel_sizes(0,ppem); sc=ppem/UPM
    buf=hb.Buffer(); buf.add_str(text); buf.guess_segment_properties(); hb.shape(HB,buf)
    lw=sum(p.x_advance for p in buf.glyph_positions)*sc; penx=0; ox=x_right-lw
    for info,pos in zip(buf.glyph_infos,buf.glyph_positions):
        FACE.load_glyph(info.codepoint,freetype.FT_LOAD_RENDER); g=FACE.glyph; bm=g.bitmap
        gx=int(ox+(penx+pos.x_offset)*sc+g.bitmap_left); gy=int(baseline-(pos.y_offset)*sc-g.bitmap_top)
        if bm.width and bm.rows: img.paste(color,(gx,gy),Image.frombytes("L",(bm.width,bm.rows),bytes(bm.buffer)))
        penx+=pos.x_advance
    return lw

# 1) HERO — name + tagline (non-denominational)
W=1600; H=560; img=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(img)
draw_line(img,"كنز المرجان",230,W-120,330)
d.text((W-120-380,380),"An Arabic & Lisan al-Dawat typeface",fill=GREY,font=lab(34),anchor="la")
d.text((124,380),"Kanz al Marjaan",fill=(60,60,60),font=lab(40))
img.save("documentation/sample-hero.png"); print("hero")

# 2) VOCALIZATION showcase — UDHR Article 1 (neutral), full harakat
lines=["يُولَدُ جَمِيعُ النَّاسِ أَحْرَارًا مُتَسَاوِينَ","فِي الكَرَامَةِ وَالحُقُوقِ، وَقَدْ وُهِبُوا","عَقْلًا وَضَمِيرًا وَعَلَيْهِمْ أَنْ يُعَامِلَ","بَعْضُهُمْ بَعْضًا بِرُوحِ الإِخَاءِ."]
W=1600; PPEM=104; LH=int(PPEM*2.0); top=90; H=top+LH*len(lines)+70
img=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(img)
d.text((120,28),"Full vocalisation — harakat, shadda, tanwīn (UDHR, Article 1)",fill=GREY,font=lab(28))
for i,t in enumerate(lines): draw_line(img,t,PPEM,W-120,top+LH*i+PPEM)
img.save("documentation/sample-vocalized.png"); print("vocalized")

# 3) CHARSET — Arabic alphabet + Lisan al-Dawat letters
ar="ا ب ت ث ج ح خ د ذ ر ز س ش ص ض ط ظ ع غ ف ق ك ل م ن ه و ي"
ld=" پ چ ج ڠ ٹ ڈ ڑ ھ ہ ے ۇ"
W=1600; H=560; img=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(img)
d.text((120,34),"Arabic",fill=GREY,font=lab(28)); draw_line(img,ar,86,W-120,210)
d.text((120,300),"Lisan al-Dawat (extended)",fill=GREY,font=lab(28)); draw_line(img,ld,86,W-120,470)
img.save("documentation/sample-charset.png"); print("charset")
print("done")
