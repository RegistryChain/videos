#!/usr/bin/env python3
"""Entity.ID booth loop v4: real Entity.IDs on a slide-4 style spine, each opening into its real data.

50 s, 1920x1080, 30 fps. Every motion is a function of wrap(t), so frame N == frame 0.
Data: /workspace/booth-src/v4-data.json (prod, read-only). People appear as initials only.
"""

import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30
T = 50.0
NFRAMES = int(round(FPS * T))
FONT_PATH = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
TAU = 2 * math.pi
OUT = "/workspace/entityid-booth-loop-v4.mp4"
MASTER = "/workspace/booth-src/v4-master-lossless.mkv"
QR_URL = "https://app.entity.id"

# palette (slide 4: deep navy / royal blue, light spine, thin outlined boxes)
TXT = (242, 246, 255, 255)
HDR = (150, 192, 255, 255)
BODY = (214, 226, 252, 255)
DIM = (170, 190, 238, 255)
TEAL = (112, 232, 216, 255)
GREEN = (118, 228, 164, 255)
AMBER = (255, 202, 106, 255)
BOX_FILL = (13, 36, 104, 238)
BOX_OUT = (156, 186, 248, 210)
CARD_FILL = (18, 46, 128, 226)
CARD_OUT = (156, 186, 248, 150)
LINE_RGB = np.array([168, 198, 255], np.float32)


# ---------------------------------------------------------------- easing
def clamp(v, a, b):
    return a if v < a else b if v > b else v


def smoother(u):
    u = clamp(u, 0.0, 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


def ease_out_back(u, k=1.7):
    u = clamp(u, 0.0, 1.0)
    return 1 + (k + 1) * (u - 1) ** 3 + k * (u - 1) ** 2


def wrap(t):
    return t % T


def per(t, n, ph=0.0):
    return math.sin(TAU * n * t / T + ph)


def window(t, a0, a1, b0, b1):
    """0 before a0, ramps to 1 by a1, holds, ramps to 0 from b0 to b1."""
    if t < a0 or t >= b1:
        return 0.0
    if t < a1:
        return smoother((t - a0) / (a1 - a0))
    if t < b0:
        return 1.0
    return 1.0 - smoother((t - b0) / (b1 - b0))


# ---------------------------------------------------------------- timeline
RESET0, RESET1 = 46.6, 48.0          # scene elements fade away under the CTA
CAP_A = (49.55, 49.95, 5.2, 5.9)     # opening caption (wraps through t=0)
STATS_IN0, STATS_COUNT1, STATS_OUT0, STATS_OUT1 = 40.8, 42.6, 43.3, 43.7
TITLE_IN0, TITLE_IN1, TITLE_OUT0, TITLE_OUT1 = 43.7, 44.1, 44.85, 45.2
CTA_IN0, CTA_IN1, CTA_OUT0, CTA_OUT1 = 45.15, 45.55, 49.6, 49.98

HOME2 = (810.0, 1540.0)
HOME3 = (810.0, 3100.0)
HOME3B = (1440.0, 3100.0)
HOME4 = (810.0, 4560.0)

# camera keys: (t, x, y, scale). Smootherstep between keys, zero velocity at keys, plus a periodic drift.
CAM_KEYS = [
    (0.0, 0, 0, 1.0),
    (5.8, 0, 60, 0.975),
    (8.0, HOME2[0], HOME2[1], 1.0),
    (16.8, HOME2[0] + 18, HOME2[1] + 14, 0.975),
    (19.0, HOME3[0], HOME3[1], 1.0),
    (23.4, HOME3[0] + 16, HOME3[1] + 10, 0.985),
    (25.0, HOME3B[0], HOME3B[1], 0.99),
    (30.6, HOME3B[0] + 18, HOME3B[1] + 12, 0.97),
    (32.8, HOME4[0], HOME4[1], 1.0),
    (39.0, HOME4[0] + 18, HOME4[1] + 12, 0.975),
    (41.6, -120, 2480, 0.235),
    (45.6, -160, 2260, 0.25),
]


def camera(t):
    t = wrap(t)
    keys = CAM_KEYS
    n = len(keys)
    for i in range(n):
        t0 = keys[i][0]
        t1 = keys[i + 1][0] if i + 1 < n else T
        if t0 <= t < t1:
            break
    a = keys[i]
    b = keys[(i + 1) % n]
    t1 = b[0] if i + 1 < n else T
    u = smoother((t - a[0]) / (t1 - a[0]))
    ls = math.log(a[3]) + (math.log(b[3]) - math.log(a[3])) * u
    s = math.exp(ls)
    # interpolate the focus so the zoom feels anchored: blend in screen space weighted by scale
    wa, wb = a[3] * (1 - u), b[3] * u
    x = (a[1] * wa + b[1] * wb) / (wa + wb)
    y = (a[2] * wa + b[2] * wb) / (wa + wb)
    x += 9 * per(t, 3, 0.4) + 5 * per(t, 7, 1.1)
    y += 7 * per(t, 4, 1.3) + 4 * per(t, 9, 0.2)
    s *= 1 + 0.006 * per(t, 5, 0.2)
    return x, y, s


def to_screen(p, cam):
    cx, cy, s = cam
    return (W / 2 + (p[0] - cx) * s, H / 2 + (p[1] - cy) * s)


# ---------------------------------------------------------------- text / sprite masters (2x)
_FONTS = {}


def load_font(size, weight):
    key = (size, weight)
    f = _FONTS.get(key)
    if f is None:
        f = ImageFont.truetype(FONT_PATH, size)
        f.set_variation_by_axes([32 if size >= 32 else max(14, size), weight])
        _FONTS[key] = f
    return f


def seg(t, s=30, w=500, c=BODY, chip=False, gap=0, track=0.0):
    return dict(t=t, s=s, w=w, c=c, chip=chip, gap=gap, track=track)


def render_rich(segs, shadow=True):
    """One line of mixed text and outlined chips, rendered at 2x. Returns RGBA master."""
    items = []
    asc_max = desc_max = 0
    for sg in segs:
        f = load_font(sg["s"] * 2, sg["w"])
        asc, desc = f.getmetrics()
        tr = sg["track"] * 2
        tw = sum(f.getlength(ch) for ch in sg["t"]) + tr * max(0, len(sg["t"]) - 1)
        if sg["chip"]:
            px, py = sg["s"] * 0.55 * 2, sg["s"] * 0.30 * 2
            cw = tw + 2 * px
            asc_c, desc_c = asc + py, desc + py
        else:
            px = py = 0
            cw = tw
            asc_c, desc_c = asc, desc
        asc_max, desc_max = max(asc_max, asc_c), max(desc_max, desc_c)
        items.append((sg, f, tw, cw, px, py, asc, desc))
    total = int(math.ceil(sum(it[3] + it[0]["gap"] * 2 for it in items))) + 12
    hgt = int(math.ceil(asc_max + desc_max)) + 12
    im = Image.new("RGBA", (total, hgt), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    base = 6 + asc_max
    x = 6.0
    for sg, f, tw, cw, px, py, asc, desc in items:
        if sg["chip"]:
            col = sg["c"]
            cap_top = f.getbbox("H")[1]
            cap_h = f.getbbox("H")[3] - cap_top
            ytop = base - asc + cap_top - py * 0.95
            ybot = base - asc + cap_top + cap_h + py * 1.05
            d.rounded_rectangle([x, ytop, x + cw, ybot], radius=(ybot - ytop) / 2,
                                fill=(col[0] // 7, col[1] // 7 + 14, col[2] // 6 + 30, 230),
                                outline=col[:3] + (235,), width=4)
            tx = x + px
        else:
            tx = x
        passes = ((3, (0, 0, 20, 120)), (0, sg["c"])) if (shadow and not sg["chip"]) else ((0, sg["c"]),)
        for off, col in passes:
            xx = tx
            for ch in sg["t"]:
                d.text((xx, base - asc + off), ch, font=f, fill=col)
                xx += f.getlength(ch) + sg["track"] * 2
        x += cw + sg["gap"] * 2
    return im


def render_box(text, size=34, chip=None, chip_col=DIM, focus=False):
    """Thin-outlined rectangular ID box (slide 4 style), optional jurisdiction chip inside."""
    S = size * 2
    f = load_font(S, 540 if not focus else 600)
    tw = f.getlength(text)
    cap_top = f.getbbox("H")[1]
    cap_h = f.getbbox("H")[3] - cap_top
    pad_x, pad_y = int(S * 0.5), int(S * 0.42)
    chip_img = None
    if chip:
        chip_img = render_rich([seg(chip, 28, 600, chip_col, chip=True)], shadow=False)
    cw = chip_img.size[0] + int(S * 0.35) if chip_img else 0
    w = int(math.ceil(tw)) + 2 * pad_x + cw
    h = int(cap_h + 2 * pad_y + S * 0.2)
    if chip_img:
        h = max(h, chip_img.size[1] + 20)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    out = (190, 214, 255, 245) if focus else BOX_OUT
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=BOX_FILL, outline=out, width=5 if focus else 3)
    y = (h - cap_h) / 2 - cap_top - S * 0.02
    d.text((pad_x, y), text, font=f, fill=TXT)
    if chip_img:
        im.alpha_composite(chip_img, (int(pad_x + tw + S * 0.35), int((h - chip_img.size[1]) / 2)))
    return im


def render_card(w, h):
    im = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], radius=20, fill=CARD_FILL, outline=CARD_OUT, width=3)
    # thin accent bar on the left edge, like a record card
    d.rounded_rectangle([0, 0, 10, h * 2 - 1], radius=5, fill=(150, 192, 255, 200))
    return im


def render_avatar(initials, r=44):
    R = r * 2
    ss = 2
    im = Image.new("RGBA", (2 * R * ss, 2 * R * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([0, 0, 2 * R * ss - 1, 2 * R * ss - 1], fill=(26, 66, 168, 250), outline=(186, 210, 255, 255), width=4 * ss)
    im = im.resize((2 * R, 2 * R), Image.Resampling.LANCZOS)
    f = load_font(int(r * 0.72) * 2, 700)
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), initials, font=f)
    d.text((R - (bb[0] + bb[2]) / 2, R - (bb[1] + bb[3]) / 2), initials, font=f, fill=TXT)
    return im


def render_layer(w, h, fill, outline):
    """Isometric plane (slide 4 'compliance-by-modularity' stack)."""
    ss = 2
    W2, H2 = w * 2 * ss, h * 2 * ss
    im = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(0, H2 / 2), (W2 / 2, 0), (W2, H2 / 2), (W2 / 2, H2)]
    d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=outline, width=3 * ss)
    return im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)


_DONUT = {}


def render_donut(p, r_out=140, r_in=90):
    """A.T. 60% / B.R. 40% ring, drawn in to progress p. 2x master."""
    key = int(round(p * 200))
    hit = _DONUT.get(key)
    if hit is not None:
        return hit
    ss = 2
    R = r_out * 2 * ss
    im = Image.new("RGBA", (2 * R + 8, 2 * R + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = R + 4
    box = [c - R, c - R, c + R, c + R]
    thick = (r_out - r_in) * 2 * ss
    d.ellipse(box, outline=(40, 80, 170, 200), width=thick)
    pk = key / 200.0
    a_end = -90 + 360 * 0.60 * pk
    if pk > 0:
        d.arc(box, -90, a_end, fill=(122, 170, 255, 255), width=thick)
    b_frac = clamp((pk - 0.0) * 1.0, 0, 1)
    if pk > 0:
        d.arc(box, -90 + 216 + 2, -90 + 216 + 2 + (144 - 4) * b_frac, fill=TEAL, width=thick)
        # separators
    im = im.resize((im.size[0] // ss, im.size[1] // ss), Image.Resampling.LANCZOS)
    _DONUT[key] = im
    return im


# ---------------------------------------------------------------- scene graph
ELS = []    # sprite elements
LNS = []    # connector polylines
ARCS = []   # ring arcs on the line layer


class El:
    def __init__(self, img, x, y, t_in, dur=0.45, slide=(0.0, 0.0), parent=None, name=None, dyn=None,
                 font_px=None, home=None, keep=False):
        self.img = img
        self.x, self.y = x, y
        self.t_in, self.dur, self.slide = t_in, dur, slide
        self.parent, self.name, self.dyn = parent, name, dyn
        self.font_px = font_px
        self.keep = keep
        if img is not None:
            self.w, self.h = img.size[0] / 2, img.size[1] / 2
        ELS.append(self)

    def image(self, t):
        return self.dyn(t) if self.dyn else self.img

    def life(self, t):
        if self.t_in is None:
            return 1.0
        if t < self.t_in:
            return 0.0
        a = smoother((t - self.t_in) / self.dur)
        if not self.keep and t > RESET0:
            a *= 1 - smoother((t - RESET0) / (RESET1 - RESET0))
        return a

    def offset(self, t):
        if self.t_in is None or t < self.t_in:
            return self.slide
        k = 1 - smoother((t - self.t_in) / (self.dur * 1.5))
        return (self.slide[0] * k, self.slide[1] * k)

    def world_rect(self, t, img=None):
        img = img or self.image(t)
        w, h = img.size[0] / 2, img.size[1] / 2
        ox, oy = self.offset(t)
        return (self.x + ox, self.y + oy, w, h)


class Ln:
    def __init__(self, pts, t_in, dur=0.5, val=0.8, width=2.4, pulse=True, ptsfn=None, alphafn=None):
        self.pts, self.t_in, self.dur, self.val, self.width = pts, t_in, dur, val, width
        self.pulse, self.ptsfn, self.alphafn = pulse, ptsfn, alphafn
        self.ph = (len(LNS) * 0.37) % 1.0
        LNS.append(self)

    def state(self, t):
        if self.t_in is None:
            p, a = 1.0, 1.0
        elif t < self.t_in:
            return 0.0, 0.0
        else:
            p = smoother((t - self.t_in) / self.dur)
            a = 1.0
            if t > RESET0:
                a *= 1 - smoother((t - RESET0) / (RESET1 - RESET0))
        if self.alphafn:
            a *= self.alphafn(t)
        return p, a


class Arc:
    def __init__(self, c, r, t_in, dur):
        self.c, self.r, self.t_in, self.dur = c, r, t_in, dur
        ARCS.append(self)


def L(home, sx, sy):
    """Scene-local screen coords (as seen from that scene's home camera at scale 1) -> world."""
    return (home[0] - W / 2 + sx, home[1] - H / 2 + sy)


def put(img, home, sx, sy, t_in, **kw):
    x, y = L(home, sx, sy)
    return El(img, x, y, t_in, **kw)


def put_c(img, home, sx, cy, t_in, **kw):
    """Place with left edge sx and vertical centre cy."""
    return put(img, home, sx, cy - img.size[1] / 4, t_in, **kw)


def line(home, pts, t_in, **kw):
    return Ln([L(home, *p) for p in pts], t_in, **kw)


def text(segs):
    return render_rich(segs)


def count_text(t0, dur, target, fmt, size=30, weight=640, col=TEAL, prefix=None, sync=False):
    cache = {}

    def fn(t):
        u = smoother((t - t0) / dur) if t >= t0 else 0.0
        v = int(round(target * (u if sync else 1 - (1 - u) ** 3)))
        if u >= 1:
            v = target
        img = cache.get(v)
        if img is None:
            segs = []
            if prefix:
                segs += prefix
            segs.append(seg(fmt.format(v), size, weight, col))
            img = render_rich(segs)
            cache[v] = img
        return img
    return fn


# ---------------------------------------------------------------- opening: the spine conveyor
BELT_L = 1000.0
BELT_C = -70.0
BELT_V = BELT_L / T            # one belt length per loop -> periodic
BELT_X = 118.0
LEFT_COL = [("hdr", "AI Agents"), ("id", "speak5.ai.entity.id", "AI"), ("id", "hummingbot.ai.entity.id", "AI"),
            ("hdr", "Ventures"), ("id", "speak5.public.entity.id", "Public"), ("id", "lighthouse-sf.public.entity.id", "Public"),
            ("hdr", "Cooperatives"), ("id", "compass-residency.public.entity.id", "Public"), ("id", "suma.us.entity.id", "USA")]
RIGHT_COL = [("hdr", "Companies & Trusts"), ("id", "northstar-growth.public.entity.id", "Public"),
             ("id", "emeris.ky.entity.id", "Cayman"), ("id", "predex.us-de.entity.id", "Delaware"),
             ("id", "wyoming-bank-trust.us-wy.entity.id", "Wyoming"),
             ("hdr", "Corporations"), ("id", "the-lauridsen-group-inc.us-ia.entity.id", "Iowa"),
             ("id", "workverse.us-wy.entity.id", "Wyoming")]
BELT = []   # (El, side, y0, kind)


def build_belt():
    """Compact groups with a 40 px gap; the leftover belt length is one gap hidden at the wrap point."""
    for side, col, direction, y_start in ((-1, LEFT_COL, -1, -420.0), (1, RIGHT_COL, 1, -440.0)):
        y = y_start
        first = True
        for c in col:
            if c[0] == "hdr":
                if not first:
                    y += 40
                img = text([seg(c[1].upper(), 28, 660, HDR, track=2.2)])
                y_c, y = y + 26, y + 60
            else:
                img = render_box(c[1], 34, chip=c[2])
                y_c, y = y + 38, y + 80
            first = False
            e = El(img, 0, 0, None, name=("belt:" + c[1]), font_px=28 if c[0] == "hdr" else 34)
            BELT.append((e, side, y_c, direction, c[0]))
        assert y <= BELT_C + BELT_L / 2 - 60, (side, y)


def belt_y(y0, direction, t):
    v = y0 + direction * BELT_V * t
    return BELT_C + (v - BELT_C + BELT_L / 2) % BELT_L - BELT_L / 2


def belt_alpha(y):
    return smoother((BELT_L / 2 - abs(y - BELT_C)) / 90.0)


def belt_place(t):
    """Set positions of belt items for time t; return connector polylines."""
    conns = []
    for e, side, y0, direction, kind in BELT:
        yc = belt_y(y0, direction, t)
        w = e.w
        e.x = BELT_X if side > 0 else -BELT_X - w
        e.y = yc - e.h / 2
        e._belt_a = belt_alpha(yc)
        if kind == "id":
            inner = BELT_X if side > 0 else -BELT_X
            mid = inner - side * 44
            conns.append(([(inner, yc), (mid, yc), (side * 8, yc + 34 * direction * -1)], e))
    return conns


# ---------------------------------------------------------------- scenes
def build_scenes():
    # ---------- scene 2: AI agent speak5.ai.entity.id ----------
    h = HOME2
    fb = render_box("speak5.ai.entity.id", 44, chip="AI agent", chip_col=TEAL, focus=True)
    focus = put(fb, h, 230, 96, 7.2, dur=1.0, slide=(0, -340), name="s2:focus", font_px=44)
    fy = 96 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], 7.9, dur=0.4)
    line(h, [(272, 96 + fb.size[1] / 2), (272, 205)], 8.05, dur=0.3)
    card = put(render_card(560, 300), h, 230, 205, 8.2, dur=0.45, slide=(0, 18), name="s2:card")
    rows = [
        [seg("Speak5 Agent", 42, 700, TXT)],
        [seg("AI agent", 30, 520, BODY, gap=16), seg("✓ Approved", 28, 640, GREEN, chip=True)],
        [seg("Formed ", 30, 450, DIM), seg("2026-09-15", 30, 560, BODY)],
        [seg("Disputes · ", 30, 450, DIM), seg("Kleros v2", 30, 560, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (262, 330, 392, 452))):
        put_c(text(r), h, 262, cy, 8.45 + 0.2 * k, slide=(-24, 0), parent=card, name=f"s2:row{k}",
              font_px=r[0]["s"])
    # tree trunk with bracket ticks (slide style)
    line(h, [(790, 330), (850, 330)], 9.25, dur=0.3)
    line(h, [(850, 200), (850, 660)], 9.4, dur=0.8)
    heads = [("Know-Your-Agent", 200, 9.6), ("Attribution", 450, 10.8), ("Who is who", 660, 12.2)]
    for name, cy, t0 in heads:
        line(h, [(850, cy), (884, cy)], t0 - 0.1, dur=0.25)
        put_c(text([seg(name, 32, 660, HDR)]), h, 896, cy, t0, slide=(-20, 0), name=f"s2:h:{name}", font_px=32)
    line(h, [(916, 226), (916, 360)], 9.8, dur=0.5)
    kya = [
        [seg("Owner KYC verified ", 30, 500, BODY), seg("✓", 30, 700, GREEN)],
        [seg("Owner signature ", 30, 500, BODY), seg("✓", 30, 700, GREEN)],
        [seg("Constitution · ", 30, 450, DIM), seg("Model 1", 30, 560, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(kya, (256, 306, 356))):
        line(h, [(916, cy), (944, cy)], 9.9 + 0.2 * k, dur=0.2)
        put_c(text(r), h, 956, cy, 9.95 + 0.2 * k, slide=(-18, 0), name=f"s2:kya{k}", font_px=30)
    # attribution -> second box
    line(h, [(916, 476), (916, 512), (944, 512)], 11.0, dur=0.3)
    put_c(text([seg("Same owner", 30, 500, BODY, gap=10), seg("→", 32, 600, TEAL)]), h, 956, 512, 11.1,
          slide=(-18, 0), name="s2:sameowner", font_px=30)
    vb = render_box("speak5.public.entity.id", 34, chip="Public")
    put_c(vb, h, 1200, 512, 11.35, slide=(-40, 0), name="s2:venture", font_px=34)
    put_c(text([seg("Venture", 28, 520, DIM, gap=12), seg("✓ Approved", 28, 640, GREEN, chip=True)]),
          h, 1206, 586, 11.6, slide=(0, 10), name="s2:venture-cap", font_px=28)
    # who is who: K.S.
    av = render_avatar("K.S.", 46)
    line(h, [(916, 686), (916, 782), (944, 782)], 12.35, dur=0.3)
    put_c(av, h, 952, 782, 12.45, dur=0.4, name="s2:avatar", font_px=33)
    Arc(L(h, 998, 782), 58, 12.7, 1.0)
    put_c(text([seg("Manager · Signer", 30, 560, BODY)]), h, 1080, 762, 12.6, slide=(-18, 0),
          name="s2:roles", font_px=30)
    cf = count_text(12.8, 1.0, 100, "{}%", 34, 700, TEAL, prefix=[seg("Owns ", 30, 450, DIM)])
    put_c(cf(99), h, 1080, 812, 12.75, slide=(-18, 0), name="s2:owns", dyn=cf, font_px=30)

    # ---------- scene 3: company northstar-growth.public.entity.id ----------
    h = HOME3
    fb = render_box("northstar-growth.public.entity.id", 44, chip="Public", focus=True)
    put(fb, h, 230, 88, 18.2, dur=1.0, slide=(0, -340), name="s3:focus", font_px=44)
    fy = 88 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], 18.9, dur=0.4)
    line(h, [(272, 88 + fb.size[1] / 2), (272, 196)], 19.05, dur=0.3)
    card = put(render_card(560, 330), h, 230, 196, 19.2, dur=0.45, slide=(0, 18), name="s3:card")
    rows = [
        [seg("Northstar Growth Agency", 38, 700, TXT)],
        [seg("Agency", 30, 520, BODY, gap=16), seg("Pending approval", 28, 640, AMBER, chip=True)],
        [seg("Formed ", 30, 450, DIM), seg("2026-06-23", 30, 560, BODY)],
        [seg("Disputes · ", 30, 450, DIM), seg("Kleros v2", 30, 560, BODY)],
        [seg("Partner signatures · ", 30, 450, DIM), seg("2", 30, 600, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (250, 316, 376, 430, 484))):
        put_c(text(r), h, 262, cy, 19.4 + 0.18 * k, slide=(-24, 0), parent=card, name=f"s3:row{k}",
              font_px=r[0]["s"])
    line(h, [(790, 330), (836, 330)], 20.3, dur=0.3)
    line(h, [(836, 214), (836, 560)], 20.4, dur=0.6)
    for name, cy, t0 in (("Who is who", 214, 20.6), ("Who owns what", 560, 21.6)):
        line(h, [(836, cy), (866, cy)], t0 - 0.1, dur=0.25)
        put_c(text([seg(name, 32, 660, HDR)]), h, 878, cy, t0, slide=(-20, 0), name=f"s3:h:{name}", font_px=32)
    line(h, [(898, 240), (898, 418)], 20.75, dur=0.4)
    for k, (ini, cy) in enumerate((("A.T.", 304), ("B.R.", 418))):
        line(h, [(898, cy), (916, cy)], 20.85 + 0.2 * k, dur=0.2)
        put_c(render_avatar(ini, 44), h, 920, cy, 20.9 + 0.2 * k, dur=0.4, name=f"s3:av:{ini}", font_px=31)
        put_c(text([seg("Manager · Signer", 30, 560, BODY)]), h, 1028, cy, 21.0 + 0.2 * k, slide=(-18, 0),
              name=f"s3:roles:{ini}", font_px=30)
    # who owns what: donut + legend count-ups
    line(h, [(898, 586), (898, 760), (916, 760)], 21.7, dur=0.3)
    dn0 = 21.8

    def donut_fn(t, t0=dn0):
        return render_donut(smoother((t - t0) / 1.4) if t >= t0 else 0.0)
    put(donut_fn(dn0 + 2), h, 922, 760 - 142, dn0, dur=0.35, dyn=donut_fn, name="s3:donut")
    for k, (ini, pct, col, cy) in enumerate((("A.T.", 60, (122, 170, 255, 255), 712), ("B.R.", 40, TEAL, 800))):
        sw = text([seg("■", 30, 700, col, gap=10), seg(ini, 30, 640, TXT)])
        put_c(sw, h, 1232, cy, 22.0 + 0.2 * k, slide=(-16, 0), name=f"s3:leg:{ini}", font_px=30)
        cf = count_text(dn0, 1.4, pct, "{}%", 34, 700, col, sync=True)  # in step with the ring
        put_c(cf(99), h, 1352, cy, 22.0 + 0.2 * k, slide=(-16, 0), dyn=cf, name=f"s3:legpct:{ini}", font_px=34)
    # people -> their other entities (seen after the pan to HOME3B)
    put_c(text([seg("Who else they own", 32, 660, HDR)]), h, 1520, 200, 24.3, slide=(-20, 0),
          name="s3:h:else", font_px=32)
    others = [("A.T.", 304, "compass-residency.public.entity.id", 286, 100, 24.6),
              ("A.T.", 304, "field-notes-by-ace.public.entity.id", 376, 20, 24.85),
              ("B.R.", 418, "lighthouse-sf.public.entity.id", 478, 100, 25.1)]
    for ini, py, eid, by, pct, t0 in others:
        line(h, [(1272, py), (1330, py), (1400, by), (1520, by)], t0, dur=0.45)
        b = render_box(eid, 34, chip="Public")
        put_c(b, h, 1520, by, t0 + 0.25, slide=(-36, 0), name=f"s3:other:{eid}", font_px=34)
        cf = count_text(t0 + 0.4, 0.9, pct, "{}%", 32, 700, TEAL)
        put_c(cf(99), h, 1520 + b.size[0] / 2 + 18, by, t0 + 0.4, slide=(-12, 0), dyn=cf,
              name=f"s3:otherpct:{eid}", font_px=32)
    # how they're managed: stacked layers
    put_c(text([seg("How they're managed", 32, 660, HDR)]), h, 1520, 600, 26.0, slide=(-20, 0),
          name="s3:h:managed", font_px=32)
    lw, lh = 330, 124
    cx = 1660
    layers = [("Entity", None, (20, 40, 110, 245), (120, 150, 230, 255)),
              ("Members", "A.T. · B.R.", (38, 82, 196, 238), (176, 204, 255, 255)),
              ("Compliance", "2 partner signatures", (48, 98, 214, 238), (176, 204, 255, 255)),
              ("Dispute", "Kleros v2 arbitration", (58, 114, 228, 238), (180, 208, 255, 255)),
              ("Governance", "Constitution Model 1", (70, 130, 238, 238), (190, 214, 255, 255))]
    base_y, step = 938, 50
    for k, (nm, val, fill, out) in enumerate(layers):
        cy = base_y - step * k
        t0 = 26.2 + 0.25 * k
        put(render_layer(lw, lh, fill, out), h, cx - lw / 2, cy - lh / 2, t0, dur=0.4, slide=(0, -40),
            name=f"s3:layer:{nm}")
        if val:
            line(h, [(cx + lw / 2 - 6, cy), (cx + lw / 2 + 34, cy)], t0 + 0.25, dur=0.25, pulse=False)
            put_c(text([seg(nm, 30, 680, TXT, gap=14), seg(val, 30, 500, DIM)]), h, cx + lw / 2 + 44, cy,
                  t0 + 0.3, slide=(-16, 0), name=f"s3:layerlbl:{nm}", font_px=30)
    # layer motif sits over the stack: we draw layers bottom->top in creation order

    # ---------- scene 4: corporate group the-lauridsen-group-inc.us-ia.entity.id ----------
    h = HOME4
    fb = render_box("the-lauridsen-group-inc.us-ia.entity.id", 40, chip="Iowa", focus=True)
    put(fb, h, 230, 88, 32.0, dur=1.0, slide=(0, -340), name="s4:focus", font_px=40)
    fy = 88 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], 32.7, dur=0.4)
    line(h, [(272, 88 + fb.size[1] / 2), (272, 196)], 32.85, dur=0.3)
    card = put(render_card(540, 236), h, 230, 196, 33.0, dur=0.45, slide=(0, 18), name="s4:card")
    rows = [
        [seg("Profit Corporation", 38, 700, TXT)],
        [seg("Iowa · formed ", 30, 450, DIM), seg("1994", 30, 600, BODY)],
        [seg("LEI ", 30, 450, DIM), seg("549300X1EKGQF6FLG933", 30, 560, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (250, 316, 376))):
        put_c(text(r), h, 262, cy, 33.2 + 0.18 * k, slide=(-24, 0), parent=card, name=f"s4:row{k}",
              font_px=r[0]["s"])
    put_c(text([seg("Parent → subsidiaries,", 32, 640, HDR)]), h, 230, 500, 34.2, slide=(-20, 0),
          name="s4:cap1", font_px=32)
    put_c(text([seg("across jurisdictions", 32, 640, HDR)]), h, 230, 544, 34.3, slide=(-20, 0),
          name="s4:cap2", font_px=32)
    juris = [("6", "Iowa"), ("1", "Nebraska"), ("1", "Denmark")]
    for k, (n, j) in enumerate(juris):
        put_c(text([seg(n, 32, 700, TEAL, gap=12), seg("×", 30, 500, DIM, gap=12), seg(j, 30, 560, BODY)]),
              h, 262, 620 + 54 * k, 35.6 + 0.2 * k, slide=(-18, 0), name=f"s4:jur:{j}", font_px=30)
    subs = [("bhj-as.dk.entity.id", "Denmark", AMBER), ("proliant-dairy-llc.us-ia.entity.id", "Iowa", DIM),
            ("proliant-biologicals-llc.us-ia.entity.id", "Iowa", DIM), ("apc-llc.us-ia.entity.id", "Iowa", DIM),
            ("boyer-valley-company-llc.us-ia.entity.id", "Iowa", DIM),
            ("essentia-by-product-solutions-llc.us-ia.entity.id", "Iowa", DIM),
            ("ampc-llc.us-ia.entity.id", "Iowa", DIM), ("bhj-usa-llc.us-ne.entity.id", "Nebraska", AMBER)]
    line(h, [(770, 314), (830, 314)], 33.75, dur=0.25)
    put_c(text([seg("Who owns what", 32, 660, HDR)]), h, 870, 196, 33.85, slide=(-20, 0),
          name="s4:h:owns", font_px=32)
    y0, step = 272, 94
    line(h, [(830, 196), (830, y0 + step * 7)], 33.9, dur=0.9)
    line(h, [(830, 196), (858, 196)], 33.85, dur=0.2, pulse=False)
    for k, (eid, j, col) in enumerate(subs):
        cy = y0 + step * k
        t0 = 34.1 + 0.2 * k
        line(h, [(830, cy), (870, cy)], t0, dur=0.25)
        put_c(render_box(eid, 34, chip=j, chip_col=col), h, 870, cy, t0 + 0.08, slide=(-40, 0),
              name=f"s4:sub:{eid}", font_px=34)


# ghost registrations (only visible in the wide shot): outline boxes branching off the spine
GHOSTS = []


def build_ghosts():
    rng = np.random.default_rng(11)
    y = 760.0
    while y < 5000:
        side = -1
        w = float(rng.uniform(260, 620))
        x1 = -float(rng.uniform(160, 420))
        x0 = x1 - w
        t0 = float(rng.uniform(39.3, 44.5))
        GHOSTS.append((x0, y, x1, y + 58, t0, side))
        if rng.uniform() < 0.55:
            w2 = float(rng.uniform(240, 560))
            xx1 = x0 - float(rng.uniform(140, 300))
            GHOSTS.append((xx1 - w2, y + float(rng.uniform(-20, 20)), xx1, y + 58, t0 + 0.3, side))
        y += float(rng.uniform(95, 150))
    # right side beyond the scene content
    y = -500.0
    while y < 5000:
        w = float(rng.uniform(240, 560))
        x0 = float(rng.uniform(2900, 3300))
        GHOSTS.append((x0, y, x0 + w, y + 58, float(rng.uniform(39.3, 44.5)), 1))
        y += float(rng.uniform(110, 190))


# ---------------------------------------------------------------- rendering
BG = None
GLOW = {}


def make_background():
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xs - W * 0.45) / W
    ny = (ys - H * 0.45) / H
    r = np.sqrt(nx * nx + ny * ny)
    bg = np.zeros((H, W, 3), dtype=np.float32)
    k = np.clip(1 - r * 1.25, 0, 1)
    bg[..., 0] = 7 + 9 * k
    bg[..., 1] = 22 + 26 * k
    bg[..., 2] = 74 + 62 * k
    return bg


def glow_sprite(radius):
    key = int(round(radius))
    hit = GLOW.get(key)
    if hit is not None:
        return hit
    R = max(3, key)
    y, x = np.mgrid[-R:R + 1, -R:R + 1].astype(np.float32)
    d2 = (x * x + y * y) / float(R * R)
    d = np.sqrt(d2)
    halo = np.exp(-d2 * 3.0) * np.clip(1.0 - d, 0, 1)
    core = np.exp(-d2 * 40.0)
    col = np.array([150, 190, 255], np.float32) / 255.0
    rgb = col[None, None, :] * (halo * 0.8)[..., None]
    rgb = rgb + np.array([0.92, 0.96, 1.0], np.float32)[None, None, :] * core[..., None] * 0.9
    GLOW[key] = rgb.astype(np.float32)
    return GLOW[key]


def blit_add(canvas, sprite, cx, cy, gain):
    if gain <= 0.004:
        return
    h, w = sprite.shape[:2]
    x0 = int(round(cx - w / 2))
    y0 = int(round(cy - h / 2))
    sx0, sy0 = max(0, -x0), max(0, -y0)
    sx1, sy1 = min(w, W - x0), min(h, H - y0)
    if sx0 >= sx1 or sy0 >= sy1:
        return
    canvas[y0 + sy0:y0 + sy1, x0 + sx0:x0 + sx1] += sprite[sy0:sy1, sx0:sx1] * (gain * 255.0)


def _fade(img, a):
    if a >= 0.999:
        return img
    arr = np.array(img, dtype=np.float32)
    arr[..., 3] *= a
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def cap_alpha(t):
    a0, a1, b0, b1 = CAP_A
    if t >= a0:
        return smoother((t - a0) / (a1 - a0))
    if t < b0:
        return 1.0
    return 1.0 - smoother((t - b0) / (b1 - b0))


def bottom_limit(t):
    return H - 168 * cap_alpha(t)


def edge_alpha(l, tp, r, bt, t):
    """Elements fade out before they reach the frame edge, so nothing is ever shown cut off."""
    d = min(l, tp, W - r, bottom_limit(t) - bt)
    return smoother((d - 4) / 26.0)


def placed(t, cam):
    """All world sprites with screen rect and effective alpha. Returns list of (el, img, x, y, w, h, alpha, f)."""
    s = cam[2]
    belt_place(t)
    out = []
    for e in ELS:
        a = e.life(t)
        if hasattr(e, "_belt_a") and e.t_in is None:
            a *= e._belt_a
        if a <= 0.004:
            continue
        img = e.image(t)
        wx, wy, ww, wh = e.world_rect(t, img)
        sx, sy = to_screen((wx, wy), cam)
        sw, sh = ww * s, wh * s
        if sx > W or sy > H or sx + sw < 0 or sy + sh < 0:
            continue
        a *= edge_alpha(sx, sy, sx + sw, sy + sh, t)
        if a <= 0.004:
            continue
        out.append((e, img, sx, sy, sw, sh, a, s))
    return out


TITLE_IMGS = None
CTA = None
CTA_Y = 300
QR_IMG = None
QR_X = QR_Y = 0
QR_CAP = None
CAP_IMG = None
STATS = [(2935661, "registered entities"), (311, "active jurisdictions"), (226467, "verifiable entities")]
STAT_CAPS = []
NUM_FONT = None
WORDMARK = None


def stats_alpha(t):
    return window(t, STATS_IN0, STATS_IN0 + 0.45, STATS_OUT0, STATS_OUT1)


def title_alpha(t):
    return window(t, TITLE_IN0, TITLE_IN1, TITLE_OUT0, TITLE_OUT1)


def cta_alpha(t):
    return window(t, CTA_IN0, CTA_IN1, CTA_OUT0, CTA_OUT1)


def ghost_alpha(s):
    return smoother((0.62 - s) / 0.22)


def render_frame(i, want_rects=False):
    t = wrap(i / FPS)
    cam = camera(t)
    s = cam[2]
    canvas = BG.copy()
    mask = Image.new("L", (W * 2, H * 2), 0)
    md = ImageDraw.Draw(mask)
    glows = []
    lw = max(2, int(round(2.4 * s * 2)))

    # --- spine (soft vertical light)
    sx, _ = to_screen((0, 0), cam)
    y_top = to_screen((0, -1150), cam)[1]
    y_bot = to_screen((0, 5250), cam)[1]
    r0, r1 = int(max(0, y_top)), int(min(H, y_bot))
    if r1 > r0 and -400 < sx < W + 400:
        half = int(min(600, 260 * max(s, 0.25)))
        c0, c1 = max(0, int(sx) - half), min(W, int(sx) + half)
        if c1 > c0:
            xs = np.arange(c0, c1, dtype=np.float32) - sx
            sig_w = 95 * max(s, 0.3)
            sig_m = 24 * max(s, 0.25)
            sig_c = max(1.1, 2.2 * s)
            prof = (0.10 * np.exp(-(xs / sig_w) ** 2) + 0.22 * np.exp(-(xs / sig_m) ** 2)
                    + 0.55 * np.exp(-(xs / sig_c) ** 2))
            ys = np.arange(r0, r1, dtype=np.float32)
            vf = np.clip((ys - y_top) / (200 * s + 1), 0, 1) * np.clip((y_bot - ys) / (200 * s + 1), 0, 1)
            vf *= 0.9 + 0.1 * math.sin(TAU * 2 * t / T)
            canvas[r0:r1, c0:c1] += (vf[:, None, None] * prof[None, :, None]) * np.array([120, 160, 255], np.float32)[None, None, :]
        # spine pulses travelling down (periodic: integer cycles per loop)
        span = 6400.0
        for k in range(16):
            u = (k / 16 + 3 * t / T) % 1.0
            wy = -1150 + span * u
            px, py = to_screen((0, wy), cam)
            if -60 < py < H + 60:
                glows.append((30 * max(s, 0.35), px, py, 0.55 * math.sin(math.pi * u) ** 0.3))

    # --- belt connectors
    conns = belt_place(t)
    for pts, e in conns:
        sp = [to_screen(p, cam) for p in pts]
        bx, by = to_screen((e.x, e.y), cam)
        aa = e._belt_a * edge_alpha(bx, by, bx + e.w * s, by + e.h * s, t)
        if aa > 0.01:
            md.line([(x * 2, y * 2) for x, y in sp], fill=int(200 * aa), width=lw, joint="curve")
            glows.append((16 * max(s, 0.4), sp[-1][0], sp[-1][1], 0.7 * aa))

    # --- scene connectors (drawn in progressively)
    for ln in LNS:
        p, a = ln.state(t)
        if p <= 0 or a <= 0.01:
            continue
        sp = [to_screen(q, cam) for q in ln.pts]
        if max(x for x, _ in sp) < -50 or min(x for x, _ in sp) > W + 50 or max(y for _, y in sp) < -50 or min(y for _, y in sp) > H + 50:
            continue
        segs_len = [math.dist(sp[k], sp[k + 1]) for k in range(len(sp) - 1)]
        total = sum(segs_len) or 1
        want = total * p
        pts = [sp[0]]
        acc = 0
        for k, sl in enumerate(segs_len):
            if acc + sl >= want:
                u = (want - acc) / sl if sl else 0
                pts.append((sp[k][0] + (sp[k + 1][0] - sp[k][0]) * u, sp[k][1] + (sp[k + 1][1] - sp[k][1]) * u))
                break
            pts.append(sp[k + 1])
            acc += sl
        md.line([(x * 2, y * 2) for x, y in pts], fill=int(255 * ln.val * a), width=lw, joint="curve")
        if p < 1:
            glows.append((26 * max(s, 0.4), pts[-1][0], pts[-1][1], 1.0 * a))
        elif ln.pulse:
            u = (t / 2.5 + ln.ph) % 1.0
            want = total * u
            acc = 0
            for k, sl in enumerate(segs_len):
                if acc + sl >= want:
                    uu = (want - acc) / sl if sl else 0
                    glows.append((15 * max(s, 0.4), sp[k][0] + (sp[k + 1][0] - sp[k][0]) * uu,
                                  sp[k][1] + (sp[k + 1][1] - sp[k][1]) * uu, 0.75 * a * math.sin(math.pi * u)))
                    break
                acc += sl

    # --- ownership rings
    for arc in ARCS:
        if t < arc.t_in:
            continue
        p = smoother((t - arc.t_in) / arc.dur)
        a = 1.0 if t < RESET0 else 1 - smoother((t - RESET0) / (RESET1 - RESET0))
        c = to_screen(arc.c, cam)
        r = arc.r * s
        if a > 0.01 and p > 0 and -100 < c[0] < W + 100:
            md.arc([(c[0] - r) * 2, (c[1] - r) * 2, (c[0] + r) * 2, (c[1] + r) * 2], -90, -90 + 360 * p,
                   fill=int(255 * a), width=max(3, int(round(5 * s * 2))))

    # --- ghosts (wide shot only)
    ga = ghost_alpha(s)
    if ga > 0.01:
        for x0, y0, x1, y1, tg, side in GHOSTS:
            if t < tg:
                continue
            a = ga * smoother((t - tg) / 0.5)
            if t > RESET0:
                a *= 1 - smoother((t - RESET0) / (RESET1 - RESET0))
            if a < 0.01:
                continue
            p0 = to_screen((x0, y0), cam)
            p1 = to_screen((x1, y1), cam)
            if p1[0] < 0 or p0[0] > W or p1[1] < 0 or p0[1] > H:
                continue
            md.rectangle([p0[0] * 2, p0[1] * 2, p1[0] * 2, p1[1] * 2], outline=int(150 * a), width=2)
            # faint text bar inside
            md.line([(p0[0] + 4 * s * 2) * 2, (p0[1] + p1[1]), (p0[0] + (p1[0] - p0[0]) * 0.7) * 2, (p0[1] + p1[1])],
                     fill=int(90 * a), width=max(2, int(9 * s * 2)))
            ym = (p0[1] + p1[1]) / 2
            if side < 0:
                q = to_screen((0, (y0 + y1) / 2 + 30), cam)
                md.line([(p1[0] * 2, ym * 2), (q[0] * 2, q[1] * 2)], fill=int(110 * a), width=2)
            if t - tg < 0.6:
                glows.append((40 * max(s, 0.3) * 2, p1[0] if side < 0 else p0[0], ym, 0.9 * (1 - (t - tg) / 0.6)))

    small = mask.resize((W, H), Image.Resampling.BOX)
    m = np.asarray(small, dtype=np.float32) / 255.0
    canvas += m[..., None] * LINE_RGB * 0.78
    for r, x, y, g in glows:
        if -120 < x < W + 120 and -120 < y < H + 120:
            blit_add(canvas, glow_sprite(r), x, y, g)

    # overlay dimming
    st, ti, ca, cp = stats_alpha(t), title_alpha(t), cta_alpha(t), cap_alpha(t)
    ob = max(st, ti)
    if ob > 0.001 or ca > 0.001 or cp > 0.001:
        ys = np.arange(H, dtype=np.float32)
        band = np.clip((ys - 600) / 220, 0, 1) * 0.78 * ob
        band_cap = np.clip((ys - 860) / 90, 0, 1) * 0.70 * cp
        dim = np.maximum(np.maximum(band, band_cap), 0.80 * ca)
        canvas *= (1.0 - dim)[:, None, None]

    np.clip(canvas, 0, 255, out=canvas)
    im = Image.fromarray(canvas.astype(np.uint8), "RGB").convert("RGBA")

    dimf = 1.0 - 0.80 * ca
    rects = []
    for e, img, x, y, w, h, a, f in placed(t, cam):
        wi, hi = max(2, int(round(w))), max(2, int(round(h))) 
        sm = img.resize((wi, hi), Image.Resampling.LANCZOS, reducing_gap=3.0 if f < 0.6 else None)
        # dim under the CTA / stats band like the background
        dd = dimf
        if ob > 0.001:
            cyy = y + h / 2
            dd *= 1 - clamp((cyy - 600) / 220, 0, 1) * 0.78 * ob
        im.alpha_composite(_fade(sm, a * dd), (int(round(x)), int(round(y))))
        if want_rects:
            rects.append((e, x, y, x + wi, y + hi, a * dd, f))

    draw_overlays(im, t, rects if want_rects else None)
    if want_rects:
        return im.convert("RGB"), rects
    return im.convert("RGB")


class _Ov:
    def __init__(self, name, px):
        self.name, self.parent, self.font_px = name, None, px


def _ov_add(rects, name, x, y, img, a, px):
    if rects is not None and a > 0.001:
        rects.append((_Ov(name, px), x, y, x + img.size[0], y + img.size[1], a, 1.0))


def draw_overlays(im, t, rects=None):
    # opening caption
    cp = cap_alpha(t)
    if cp > 0.001:
        x = int((W - CAP_IMG.size[0]) / 2)
        y = int(H - 70 - CAP_IMG.size[1] / 2)
        im.alpha_composite(_fade(CAP_IMG, cp), (x, y))
        _ov_add(rects, "ov:caption", x, y, CAP_IMG, cp, 46)
    # stats
    a = stats_alpha(t)
    if a > 0.001:
        u = smoother((t - STATS_IN0 - 0.1) / (STATS_COUNT1 - STATS_IN0 - 0.1))
        col_w = 600
        x0 = (W - col_w * 3) / 2
        for k, (val, cap) in enumerate(STATS):
            uk = smoother(clamp((u - 0.06 * k) / (1 - 0.12), 0, 1))
            v = int(round(val * (1 - (1 - uk) ** 3)))
            if uk >= 1:
                v = val
            sv = f"{v:,}"
            img = Image.new("RGBA", (col_w, 130), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            tw = d.textlength(sv, font=NUM_FONT, features=["tnum"])
            d.text(((col_w - tw) / 2, 4), sv, font=NUM_FONT, fill=TXT, features=["tnum"])
            cx = x0 + col_w * k
            rise = 18 * (1 - smoother((t - STATS_IN0 - 0.12 * k) / 0.6))
            im.alpha_composite(_fade(img, a), (int(cx), int(762 + rise)))
            capi = STAT_CAPS[k]
            im.alpha_composite(_fade(capi, a), (int(cx + (col_w - capi.size[0]) / 2), int(890 + rise)))
            if rects is not None:
                bb = NUM_FONT.getbbox("2,935,661", features=["tnum"])
                rects.append((_Ov(f"ov:stat{k}", 104), cx + (col_w - tw) / 2, 762 + rise, cx + (col_w + tw) / 2,
                              762 + rise + 130, a, 1.0))
                _ov_add(rects, f"ov:statcap{k}", int(cx + (col_w - capi.size[0]) / 2), int(890 + rise), capi, a, 40)
    # title
    ta = title_alpha(t)
    if ta > 0.001:
        rise = 14 * (1 - smoother((t - TITLE_IN0) / 0.9))
        y = 742 + rise
        for k, img in enumerate(TITLE_IMGS):
            x = int((W - img.size[0]) / 2)
            im.alpha_composite(_fade(img, ta), (x, int(y)))
            _ov_add(rects, f"ov:title{k}", x, int(y), img, ta, 40)
            y += img.size[1] + 4
    # CTA + QR
    ca = cta_alpha(t)
    if ca > 0.001:
        x = int((W - WORDMARK.size[0]) / 2)
        im.alpha_composite(_fade(WORDMARK, ca), (x, 112))
        _ov_add(rects, "ov:wordmark", x, 112, WORDMARK, ca, 72)
        rise = 16 * (1 - smoother((t - CTA_IN0) / 0.8))
        pop = 0.92 + 0.08 * ease_out_back((t - CTA_IN0) / 0.6, 1.6)
        w, h = int(CTA.size[0] * pop), int(CTA.size[1] * pop)
        img = CTA.resize((w, h), Image.Resampling.LANCZOS) if pop != 1 else CTA
        cx, cy = int((W - w) / 2), int(CTA_Y - h / 2 + rise)
        im.alpha_composite(_fade(img, ca), (cx, cy))
        _ov_add(rects, "ov:cta", cx, cy, img, ca, 92)
        im.alpha_composite(_fade(QR_IMG, ca), (QR_X, QR_Y))
        _ov_add(rects, "ov:qr", QR_X, QR_Y, QR_IMG, ca, 999)
        x = int((W - QR_CAP.size[0]) / 2)
        y = QR_Y + QR_IMG.size[1] + 16
        im.alpha_composite(_fade(QR_CAP, ca), (x, y))
        _ov_add(rects, "ov:qrcap", x, y, QR_CAP, ca, 30)


def render_cta():
    f1 = load_font(92, 640)
    fu = load_font(92, 700)
    a, arrow, url = "Get your ID", "→", "app.entity.id"
    wa, warr, wu = f1.getlength(a), f1.getlength(arrow), fu.getlength(url)
    cap_top = f1.getbbox("H")[1]
    cap_h = f1.getbbox("H")[3] - cap_top
    pad_x, pad_y = 44, 30
    pill_w = int(wu + 2 * pad_x)
    pill_h = int(cap_h + 2 * pad_y + 22)
    gap = 34
    total = int(wa + gap + warr + gap + pill_w) + 12
    hgt = pill_h + 12
    im = Image.new("RGBA", (total, hgt), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    base = (hgt - cap_h) / 2 - cap_top - 6
    d.text((4, base + 3), a, font=f1, fill=(0, 0, 20, 160))
    d.text((4, base), a, font=f1, fill=TXT)
    xa = 4 + wa + gap
    d.text((xa, base), arrow, font=f1, fill=TEAL)
    xp = int(xa + warr + gap)
    ss = 2
    pill = Image.new("RGBA", (pill_w * ss, pill_h * ss), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle([0, 0, pill_w * ss - 1, pill_h * ss - 1], radius=pill_h * ss // 2, fill=(120, 236, 228, 255))
    pill = pill.resize((pill_w, pill_h), Image.Resampling.LANCZOS)
    im.alpha_composite(pill, (xp, (hgt - pill_h) // 2))
    d.text((xp + pad_x, base), url, font=fu, fill=(4, 16, 50, 255))
    return im


def render_qr():
    import qrcode
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=4, box_size=1)
    q.add_data(QR_URL)
    q.make(fit=True)
    m = q.get_matrix()
    n = len(m)
    mod = 340 // n
    size = n * mod
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(mod * 1.6), fill=(246, 250, 255, 255))
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                d.rectangle([x * mod, y * mod, (x + 1) * mod - 1, (y + 1) * mod - 1], fill=(6, 18, 60, 255))
    return img, q.version, n, mod


def render_text_1x(segs):
    """Overlay text at 1x (overlays are never scaled)."""
    big = render_rich(segs)
    return big.resize((big.size[0] // 2, big.size[1] // 2), Image.Resampling.LANCZOS)


_INIT = False


def init():
    global BG, TITLE_IMGS, CTA, QR_IMG, QR_X, QR_Y, QR_CAP, CAP_IMG, NUM_FONT, WORDMARK, _INIT
    if _INIT:
        return
    _INIT = True
    BG = make_background()
    build_belt()
    build_scenes()
    build_ghosts()
    CAP_IMG = render_text_1x([seg("Universal Verified Facts", 46, 600, TXT, gap=22), seg("Entity.ID", 46, 720, TEAL)])
    TITLE_IMGS = [render_text_1x([seg("UNIVERSAL VERIFIED FACTS", 40, 640, HDR, track=4)]),
                  render_text_1x([seg("Every entity. One verifiable identity.", 84, 640, TXT, track=0.3)]),
                  render_text_1x([seg("Entity.ID", 62, 720, TEAL, track=1.0)])]
    WORDMARK = render_text_1x([seg("Entity.ID", 72, 720, TXT, track=1.0)])
    CTA = render_cta()
    QR_IMG, ver, n, mod = render_qr()
    QR_X = (W - QR_IMG.size[0]) // 2
    QR_Y = CTA_Y + CTA.size[1] // 2 + 30
    QR_CAP = render_text_1x([seg("Scan to get your ID", 30, 560, DIM)])
    if os.environ.get("QR_INFO"):
        print(f"QR version {ver}, {n} modules, {mod}px/module, {QR_IMG.size[0]}px at ({QR_X},{QR_Y})")
    NUM_FONT = load_font(104, 680)
    STAT_CAPS.clear()
    for _, cap in STATS:
        STAT_CAPS.append(render_text_1x([seg(cap, 40, 520, TEAL, track=1.0)]))


def frame_bytes(i):
    return render_frame(i).tobytes()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    os.environ["QR_INFO"] = "1"
    init()
    if mode == "preview":
        os.makedirs("/workspace/booth-preview/v4", exist_ok=True)
        ts = [float(x) for x in sys.argv[2:]] or [0, 3, 7, 10, 14, 20, 23, 26.5, 29, 35, 38, 41, 43, 44.5, 47, 49.7]
        for tt in ts:
            render_frame(int(round(tt * FPS))).save(f"/workspace/booth-preview/v4/t{tt:05.2f}.png")
        a = np.asarray(render_frame(0)).astype(int)
        b = np.asarray(render_frame(NFRAMES)).astype(int)
        print("raw t=0 vs t=T max diff", int(np.abs(a - b).max()))
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264rgb", "-qp", "0", "-preset", "ultrafast", MASTER]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(7, initializer=init) as pool:
        for k, buf in enumerate(pool.imap(frame_bytes, range(NFRAMES), chunksize=4)):
            proc.stdin.write(buf)
            if k % 150 == 0:
                print(f"frame {k}/{NFRAMES}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print("lossless master done", MASTER)


if __name__ == "__main__":
    main()
