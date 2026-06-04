"""Render multi-paragraph RTL Arabic specimens (vocalized + unvocalized)."""
import uharfbuzz as hb, freetype
from PIL import Image, ImageDraw

TTF = "fonts/ttf/KanzAlMarjaan-Regular.ttf"
data = open(TTF, "rb").read()
hbfont = hb.Font(hb.Face(data))
face = freetype.Face(TTF)
UPM = face.units_per_EM

VOCAL = [
    "بِسْمِ اللَّهِ الرَّحْمٰنِ الرَّحِيمِ. الْحَمْدُ لِلَّهِ رَبِّ الْعالَمِينَ. "
    "الرَّحْمٰنِ الرَّحِيمِ. مالِكِ يَوْمِ الدِّينِ.",
    "إِيّاكَ نَعْبُدُ وَإِيّاكَ نَسْتَعِينُ. اهْدِنَا الصِّراطَ الْمُسْتَقِيمَ. "
    "صِراطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ غَيْرِ الْمَغْضُوبِ عَلَيْهِمْ.",
]
PLAIN = [
    "يولد جميع الناس أحرارا متساوين في الكرامة والحقوق، وقد وهبوا عقلا وضميرا "
    "وعليهم أن يعامل بعضهم بعضا بروح الإخاء.",
    "اللغة العربية من أكثر اللغات انتشارا في العالم، ويتحدث بها مئات الملايين "
    "من الناس في مختلف أنحاء الأرض ومنها تفرعت خطوط وفنون كثيرة.",
]


def word_w(w, sc):
    buf = hb.Buffer(); buf.add_str(w); buf.guess_segment_properties(); hb.shape(hbfont, buf)
    return sum(p.x_advance for p in buf.glyph_positions) * sc


def draw_word(img, w, x_left, baseline, sc):
    buf = hb.Buffer(); buf.add_str(w); buf.guess_segment_properties(); hb.shape(hbfont, buf)
    penx = x_left
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER)
        g = face.glyph; bm = g.bitmap
        if bm.width and bm.rows:
            ink = Image.frombytes("L", (bm.width, bm.rows), bytes(bm.buffer))
            img.paste((20, 20, 20),
                      (int(penx + pos.x_offset * sc + g.bitmap_left),
                       int(baseline - pos.y_offset * sc - g.bitmap_top)), ink)
        penx += pos.x_advance * sc


def render(paragraphs, out, ppem, line_factor, title):
    sc = ppem / UPM
    face.set_pixel_sizes(0, ppem)
    W = 1100; margin = 60; right = W - margin; maxw = W - 2 * margin
    lh = int(ppem * line_factor)
    sp = word_w(" ", sc) or ppem * 0.25
    # layout into lines
    lines = []
    for para in paragraphs:
        cur = []; used = 0
        for word in para.split():
            ww = word_w(word, sc)
            if cur and used + sp + ww > maxw:
                lines.append(cur); cur = []; used = 0
            cur.append((word, ww)); used += (sp + ww if cur[:-1] else ww)
        if cur:
            lines.append(cur)
        lines.append(None)  # paragraph break
    H = int(80 + lh * (len(lines) + 1))
    img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    d.text((margin, 18), title, fill=(150, 150, 150))
    y = 70 + int(ppem * 0.9)
    for ln in lines:
        if ln is None:
            y += int(lh * 0.5); continue
        xr = right
        for word, ww in ln:
            draw_word(img, word, xr - ww, y, sc)
            xr -= ww + sp
        y += lh
    img.save(out); print("wrote", out, img.size)


render(VOCAL, "out/specimen_vocalized.png", 64, 2.0, "Kanz Al Marjaan — vocalized")
render(PLAIN, "out/specimen_plain.png", 64, 1.5, "Kanz Al Marjaan — unvocalized")
