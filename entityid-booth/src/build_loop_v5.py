#!/usr/bin/env python3
"""Entity.ID booth loop v5: decluttered opening, real on-chain agent data, compliance-by-modularity,
ownership chain up to the ultimate beneficial owner and down to subsidiaries.

54 s, 1920x1080, 30 fps. Every motion is a function of wrap(t), so frame N == frame 0.
Data: v4-data.json + v5-real-data.json (prod + mainnet, read-only). People appear as initials only.
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
T = 54.0
NFRAMES = int(round(FPS * T))
FONT_PATH = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
TAU = 2 * math.pi
OUT = "/workspace/entityid-booth-loop-v5.mp4"
MASTER = "/workspace/booth-src/v5-master-lossless.mkv"
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
BOX_OUT = (156, 186, 248, 170)
CARD_FILL = (22, 54, 142, 150)
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
RESET0, RESET1 = 50.0, 51.4          # scene elements fade away under the CTA
CAP_A = (53.55, 53.95, 7.0, 7.7)     # opening caption (wraps through t=0)
STATS_IN0, STATS_COUNT1, STATS_OUT0, STATS_OUT1 = 43.8, 45.6, 46.2, 46.55
TITLE_IN0, TITLE_IN1, TITLE_OUT0, TITLE_OUT1 = 46.55, 46.95, 48.3, 48.65
CTA_IN0, CTA_IN1, CTA_OUT0, CTA_OUT1 = 48.7, 49.1, 53.55, 53.95

HOME2 = (810.0, 1400.0)
HOME3 = (810.0, 3000.0)
HOME3B = (1440.0, 3000.0)
HOME3C = (810.0, 4300.0)
HOME4 = (810.0, 5700.0)
SPINE_Y0, SPINE_Y1 = -1150.0, 6750.0

# camera keys: (t, x, y, scale). Smootherstep between keys, zero velocity at keys, plus a periodic drift.
CAM_KEYS = [
    (0.0, 0, -20, 1.0),
    (7.4, 0, 30, 0.975),
    (9.2, HOME2[0], HOME2[1], 1.0),
    (19.0, HOME2[0] + 18, HOME2[1] + 12, 0.975),
    (20.8, HOME3[0], HOME3[1], 1.0),
    (25.0, HOME3[0] + 16, HOME3[1] + 10, 0.985),
    (26.2, HOME3B[0], HOME3B[1], 0.99),
    (28.6, HOME3B[0] + 16, HOME3B[1] + 8, 0.98),
    (30.0, HOME3C[0], HOME3C[1], 1.0),
    (34.6, HOME3C[0] + 16, HOME3C[1] + 10, 0.975),
    (36.4, HOME4[0], HOME4[1], 1.0),
    (42.4, HOME4[0] + 16, HOME4[1] + 10, 0.975),
    (44.6, -150, 2900, 0.17),
    (48.5, -190, 2650, 0.18),
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


def render_box(text, size=34, focus=False, out=None):
    """Thin-outlined rectangular ID box (slide 4 style). One outline, no chips."""
    S = size * 2
    f = load_font(S, 540 if not focus else 600)
    tw = f.getlength(text)
    cap_top = f.getbbox("H")[1]
    cap_h = f.getbbox("H")[3] - cap_top
    pad_x, pad_y = int(S * 0.5), int(S * 0.42)
    w = int(math.ceil(tw)) + 2 * pad_x
    h = int(cap_h + 2 * pad_y + S * 0.2)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    out = out or ((196, 218, 255, 240) if focus else BOX_OUT)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=BOX_FILL, outline=out, width=4 if focus else 3)
    y = (h - cap_h) / 2 - cap_top - S * 0.02
    d.text((pad_x, y), text, font=f, fill=TXT)
    return im


def render_card(w, h):
    """Borderless soft panel (no outline, no accent bar)."""
    im = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], radius=22, fill=CARD_FILL)
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


def render_layer(w, h, fill, outline, label=None, label_col=TXT):
    """Isometric plane (slide 4 'compliance-by-modularity' stack)."""
    ss = 2
    W2, H2 = w * 2 * ss, h * 2 * ss
    im = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(0, H2 / 2), (W2 / 2, 0), (W2, H2 / 2), (W2 / 2, H2)]
    if fill:
        d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=outline, width=3 * ss)
    im = im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    return im


def render_tile(text, w=210, h=74):
    """Side module tile (KYC/AML, State Reg, Tax ID): a skewed plate with its name."""
    ss = 2
    W2, H2 = w * 2 * ss, h * 2 * ss
    sk = 26 * 2 * ss
    im = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(sk, 0), (W2 - 1, 0), (W2 - 1 - sk, H2 - 1), (0, H2 - 1)]
    d.polygon(pts, fill=(52, 104, 222, 240))
    d.line(pts + [pts[0]], fill=(186, 210, 255, 255), width=3 * ss)
    im = im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    t = render_rich([seg(text, 28, 640, TXT)], shadow=False)
    im.alpha_composite(t, ((im.size[0] - t.size[0]) // 2, (im.size[1] - t.size[1]) // 2))
    return im


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
                 font_px=None, home=None, keep=False, move=None):
        self.img = img
        self.x, self.y = x, y
        self.t_in, self.dur, self.slide = t_in, dur, slide
        self.parent, self.name, self.dyn = parent, name, dyn
        self.font_px = font_px
        self.keep = keep
        self.move = move
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
        mx, my = self.move(t) if self.move else (0.0, 0.0)
        if self.t_in is None or t < self.t_in:
            return (self.slide[0] + mx, self.slide[1] + my)
        k = 1 - smoother((t - self.t_in) / (self.dur * 1.5))
        return (self.slide[0] * k + mx, self.slide[1] * k + my)

    def world_rect(self, t, img=None):
        img = img or self.image(t)
        w, h = img.size[0] / 2, img.size[1] / 2
        ox, oy = self.offset(t)
        return (self.x + ox, self.y + oy, w, h)


class Ln:
    def __init__(self, pts, t_in, dur=0.5, val=0.8, width=2.4, pulse=False, ptsfn=None, alphafn=None):
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


# ---------------------------------------------------------------- opening: one ID at a time along the spine
OPEN_IDS = [("speak5.ai.entity.id", "AI agent"), ("northstar-growth.public.entity.id", "Agency"),
            ("workverse.us-wy.entity.id", "Corporation"), ("compass-residency.public.entity.id", "Cooperative"),
            ("predex.us-de.entity.id", "Statutory trust"), ("suma.us.entity.id", "Credit union")]
OPEN_GAP = 60.0


def open_drift(t):
    return (0.0, -15.0 * min(t, 8.0))


def build_opening():
    for k, (eid, typ) in enumerate(OPEN_IDS):
        side = 1 if k % 2 == 0 else -1
        yc = -262 + 124 * k
        t0 = 0.25 + 0.95 * k
        idimg = render_rich([seg(eid, 50, 600, TXT)])
        tyimg = render_rich([seg(typ.upper(), 28, 660, TEAL, track=2.6)])
        w = idimg.size[0] / 2
        x = OPEN_GAP if side > 0 else -OPEN_GAP - w
        ide = El(idimg, x, yc - idimg.size[1] / 4, t0, dur=0.7, slide=(-side * 40, 0), name=f"open:{eid}",
                 font_px=50, move=open_drift)
        tw = tyimg.size[0] / 2
        tx = x + 2 if side > 0 else -OPEN_GAP - tw - 2
        El(tyimg, tx, yc - 58 - tyimg.size[1] / 4, t0 + 0.25, dur=0.5, slide=(0, -12), name=f"open:type:{typ}",
           font_px=28, move=open_drift)

        def pts(t, yc=yc, side=side):
            dy = open_drift(t)[1]
            return [(0, yc + dy), (side * (OPEN_GAP - 14), yc + dy)]
        Ln(None, t0, dur=0.35, val=0.85, ptsfn=pts)


# ---------------------------------------------------------------- scenes
def build_scenes():
    # ---------- scene 2: AI agent speak5.ai.entity.id ----------
    # identity = on-chain agent registration + anchor to a subject of rights. Real registration data:
    # services [{custom: https://speak5.io}], active true, x402support false, supportedTrusts [], registrations [];
    # Reputation Registry getClients(50800) = [] on mainnet -> no reviews yet.
    h = HOME2
    fb = render_box("speak5.ai.entity.id", 44, focus=True)
    put(fb, h, 230, 96, 8.4, dur=1.0, slide=(0, -340), name="s2:focus", font_px=44)
    fy = 96 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], 9.1, dur=0.4)
    line(h, [(272, 96 + fb.size[1] / 2), (272, 205)], 9.25, dur=0.3)
    card = put(render_card(520, 226), h, 230, 205, 9.4, dur=0.45, slide=(0, 18), name="s2:card")
    rows = [
        [seg("Speak5 Agent", 42, 700, TXT)],
        [seg("AI agent", 30, 520, BODY, gap=16), seg("✓ Approved", 28, 640, GREEN, chip=True)],
        [seg("Formed ", 30, 450, DIM), seg("2026-09-15", 30, 560, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (258, 326, 386))):
        put_c(text(r), h, 262, cy, 9.6 + 0.2 * k, slide=(-24, 0), parent=card, name=f"s2:row{k}", font_px=r[0]["s"])
    line(h, [(750, 318), (820, 318)], 10.2, dur=0.3)
    line(h, [(820, 200), (820, 440)], 10.35, dur=0.6, pulse=True)
    for name, cy, t0 in (("Know-Your-Agent", 200, 10.5), ("Attribution", 440, 11.9)):
        line(h, [(820, cy), (854, cy)], t0 - 0.1, dur=0.25)
        put_c(text([seg(name, 32, 660, HDR)]), h, 866, cy, t0, slide=(-20, 0), name=f"s2:h:{name}", font_px=32)
    # Know-Your-Agent: anchor + custodian
    line(h, [(886, 226), (886, 340)], 10.7, dur=0.4)
    line(h, [(886, 270), (912, 270)], 10.8, dur=0.2)
    put_c(text([seg("Anchored to subject of rights", 30, 520, BODY, gap=12), seg("→", 32, 600, TEAL)]),
          h, 924, 270, 10.85, slide=(-18, 0), name="s2:anchor", font_px=30)
    put_c(render_box("speak5.public.entity.id", 34), h, 1400, 270, 11.15, slide=(-40, 0), name="s2:venture",
          font_px=34)
    line(h, [(886, 340), (912, 340)], 11.3, dur=0.2)
    put_c(text([seg("Custodian · ", 30, 450, DIM), seg("K.S.", 30, 700, TXT, gap=14),
                seg("KYC verified ✓", 30, 600, GREEN)]), h, 924, 340, 11.35, slide=(-18, 0),
          name="s2:custodian", font_px=30)
    # Attribution: the agent's on-chain registration (real values)
    att = [
        [seg("On-chain agent · ", 30, 450, DIM), seg("#50800 · Ethereum", 30, 600, BODY)],
        [seg("Endpoint · ", 30, 450, DIM), seg("speak5.io", 30, 600, BODY)],
        [seg("Status · ", 30, 450, DIM), seg("Active ✓", 30, 600, GREEN)],
        [seg("Payments · ", 30, 450, DIM), seg("x402 ✗", 30, 600, AMBER)],
        [seg("Trust models · ", 30, 450, DIM), seg("none declared", 30, 560, BODY)],
        [seg("Reputation · ", 30, 450, DIM), seg("no reviews yet", 30, 560, BODY)],
    ]
    line(h, [(886, 470), (886, 760)], 12.1, dur=0.6)
    for k, r in enumerate(att):
        put_c(text(r), h, 912, 496 + 52 * k, 12.2 + 0.22 * k, slide=(-18, 0), name=f"s2:att{k}", font_px=30)

    # ---------- scene 3: company northstar-growth.public.entity.id ----------
    h = HOME3
    fb = render_box("northstar-growth.public.entity.id", 44, focus=True)
    put(fb, h, 230, 88, 20.0, dur=1.0, slide=(0, -340), name="s3:focus", font_px=44)
    fy = 88 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], 20.7, dur=0.4)
    line(h, [(272, 88 + fb.size[1] / 2), (272, 196)], 20.85, dur=0.3)
    card = put(render_card(560, 280), h, 230, 196, 21.0, dur=0.45, slide=(0, 18), name="s3:card")
    rows = [
        [seg("Northstar Growth Agency", 38, 700, TXT)],
        [seg("Agency", 30, 520, BODY, gap=16), seg("Pending approval", 28, 640, AMBER, chip=True)],
        [seg("Formed ", 30, 450, DIM), seg("2026-06-23", 30, 560, BODY)],
        [seg("Partner signatures · ", 30, 450, DIM), seg("2", 30, 600, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (250, 316, 376, 432))):
        put_c(text(r), h, 262, cy, 21.2 + 0.18 * k, slide=(-24, 0), parent=card, name=f"s3:row{k}", font_px=r[0]["s"])
    line(h, [(790, 330), (836, 330)], 21.9, dur=0.3)
    line(h, [(836, 214), (836, 560)], 22.0, dur=0.6, pulse=True)
    for name, cy, t0 in (("Who is who", 214, 22.2), ("Who owns what", 560, 23.0)):
        line(h, [(836, cy), (866, cy)], t0 - 0.1, dur=0.25)
        put_c(text([seg(name, 32, 660, HDR)]), h, 878, cy, t0, slide=(-20, 0), name=f"s3:h:{name}", font_px=32)
    line(h, [(898, 240), (898, 418)], 22.35, dur=0.4)
    for k, (ini, cy) in enumerate((("A.T.", 304), ("B.R.", 418))):
        line(h, [(898, cy), (916, cy)], 22.45 + 0.2 * k, dur=0.2)
        put_c(render_avatar(ini, 44), h, 920, cy, 22.5 + 0.2 * k, dur=0.4, name=f"s3:av:{ini}", font_px=31)
        put_c(text([seg("Manager · Signer", 30, 560, BODY)]), h, 1028, cy, 22.6 + 0.2 * k, slide=(-18, 0),
              name=f"s3:roles:{ini}", font_px=30)
    line(h, [(898, 586), (898, 760), (916, 760)], 23.1, dur=0.3)
    dn0 = 23.2

    def donut_fn(t, t0=dn0):
        return render_donut(smoother((t - t0) / 1.4) if t >= t0 else 0.0)
    put(donut_fn(dn0 + 2), h, 922, 760 - 142, dn0, dur=0.35, dyn=donut_fn, name="s3:donut")
    for k, (ini, pct, col, cy) in enumerate((("A.T.", 60, (122, 170, 255, 255), 712), ("B.R.", 40, TEAL, 800))):
        sw = text([seg("■", 30, 700, col, gap=10), seg(ini, 30, 640, TXT)])
        put_c(sw, h, 1232, cy, 23.4 + 0.2 * k, slide=(-16, 0), name=f"s3:leg:{ini}", font_px=30)
        cf = count_text(dn0, 1.4, pct, "{}%", 34, 700, col, sync=True)
        put_c(cf(99), h, 1352, cy, 23.4 + 0.2 * k, slide=(-16, 0), dyn=cf, name=f"s3:legpct:{ini}", font_px=34)
    # people -> their other entities (after the pan to HOME3B)
    put_c(text([seg("Who else they own", 32, 660, HDR)]), h, 1520, 200, 25.6, slide=(-20, 0),
          name="s3:h:else", font_px=32)
    others = [("A.T.", 304, "compass-residency.public.entity.id", 286, 100, 25.9),
              ("A.T.", 304, "field-notes-by-ace.public.entity.id", 376, 20, 26.15),
              ("B.R.", 418, "lighthouse-sf.public.entity.id", 478, 100, 26.4)]
    for ini, py, eid, by, pct, t0 in others:
        line(h, [(1272, py), (1330, py), (1400, by), (1520, by)], t0, dur=0.45)
        b = render_box(eid, 34)
        put_c(b, h, 1520, by, t0 + 0.25, slide=(-36, 0), name=f"s3:other:{eid}", font_px=34)
        cf = count_text(t0 + 0.4, 0.9, pct, "{}%", 32, 700, TEAL)
        put_c(cf(99), h, 1520 + b.size[0] / 2 + 18, by, t0 + 0.4, slide=(-12, 0), dyn=cf,
              name=f"s3:otherpct:{eid}", font_px=32)
    # trunk continues down to "How they're managed" (HOME3C)
    dyc = HOME3C[1] - HOME3[1]
    line(h, [(836, 560), (836, dyc + 110)], 28.5, dur=1.4)

    # ---------- scene 3C: how they're managed = compliance-by-modularity (no vendor / spec names) ----------
    h = HOME3C
    line(h, [(836, 110), (866, 110)], 29.7, dur=0.2)
    put_c(text([seg("How they're managed", 32, 660, HDR)]), h, 878, 110, 29.8, slide=(-20, 0),
          name="s3c:h:managed", font_px=32)
    cx, lw, lh = 1120, 420, 150
    upper = [("Governance", 316), ("Dispute", 376), ("Compliance", 436), ("Members", 496)]
    order = [("Treasury", 716, None, (186, 210, 255, 210)), ("Entity.ID", 806, None, (186, 210, 255, 170)),
             ("Entity", 590, (10, 26, 84, 250), (120, 150, 230, 255))]
    fills = {"Members": (38, 82, 196, 238), "Compliance": (48, 98, 214, 238), "Dispute": (58, 114, 228, 238),
             "Governance": (70, 130, 238, 238)}
    t_layer = {"Entity.ID": 30.2, "Treasury": 30.4, "Entity": 30.6, "Members": 30.85, "Compliance": 31.05,
               "Dispute": 31.25, "Governance": 31.45}
    # bottom planes first so upper planes stack over them
    stack = [order[1], order[0], order[2]] + [(nm, cy, fills[nm], (186, 210, 255, 255)) for nm, cy in reversed(upper)]
    for nm, cy, fill, out in stack:
        t0 = t_layer[nm]
        put(render_layer(lw, lh, fill, out), h, cx - lw / 2, cy - lh / 2, t0, dur=0.4, slide=(0, -36),
            name=f"s3c:layer:{nm}")
        line(h, [(cx + lw / 2 - 6, cy), (cx + lw / 2 + 34, cy)], t0 + 0.2, dur=0.2)
        col = TXT if nm not in ("Treasury", "Entity.ID") else BODY
        put_c(text([seg(nm, 30, 680, col)]), h, cx + lw / 2 + 44, cy, t0 + 0.25, slide=(-16, 0),
              name=f"s3c:lbl:{nm}", font_px=30)
    # jurisdictional conformity: side modules plugging into the entity
    put_c(text([seg("Jurisdictional conformity", 30, 640, HDR)]), h, 300, 330, 32.0, slide=(-16, 0),
          name="s3c:jc", font_px=30)
    tiles = [("KYC/AML", 430), ("State Reg", 560), ("Tax ID", 690)]
    for k, (nm, cy) in enumerate(tiles):
        tl = render_tile(nm)
        t0 = 32.2 + 0.25 * k
        put_c(tl, h, 330, cy, t0, dur=0.4, slide=(-30, 0), name=f"s3c:tile:{nm}", font_px=28)
        x1 = 330 + tl.size[0] / 2
        line(h, [(x1 + 6, cy), (cx - lw / 2 - 40, cy), (cx - lw / 2 + 4, 590)], t0 + 0.25, dur=0.5,
             pulse=True)
    put_c(text([seg("Compliance-by-modularity", 44, 640, TXT)]), h, 690, 950, 32.9, slide=(0, 14),
          name="s3c:caption", font_px=44)

    # ---------- scene 4: ownership chain up to the ultimate beneficial owner, subsidiaries below ----------
    # prod GLEIF links (partners[]): warren-equities -> global-montello-group-corp -> global-operating-llc
    # -> global-partners-lp (ultimate parent, no parents of its own). Children: 4 direct subsidiaries. No % in data.
    h = HOME4
    X = 600
    fb = render_box("warren-equities-inc.us-de.entity.id", 44, focus=True)
    fcy = 500
    put_c(fb, h, X - 40, fcy, 35.9, dur=1.0, slide=(0, -340), name="s4:focus", font_px=44)
    line(h, [(150, fcy + 40), (200, fcy), (X - 40, fcy)], 36.6, dur=0.5)
    put_c(text([seg("Corporation · Delaware · formed ", 30, 450, DIM), seg("1956", 30, 600, BODY)]),
          h, X - 40 + fb.size[0] / 2 + 28, fcy, 36.9, slide=(-16, 0), name="s4:facts", font_px=30)
    LX = X - 20
    fh = fb.size[1] / 4
    ups = [("global-montello-group-corp.us-de.entity.id", 380, 37.4),
           ("global-operating-llc.us-de.entity.id", 268, 38.2),
           ("global-partners-lp.us-de.entity.id", 150, 39.0)]
    prev_y = fcy - fh
    for k, (eid, cy, t0) in enumerate(ups):
        top = k == len(ups) - 1
        line(h, [(LX, prev_y), (LX, cy), (X, cy)], t0 - 0.35, dur=0.4, pulse=True)
        b = render_box(eid, 34, out=(120, 236, 222, 255) if top else None)
        put_c(b, h, X, cy, t0, slide=(0, 30), name=f"s4:up{k}", font_px=34)
        prev_y = cy
        if top:
            put_c(text([seg("Ultimate beneficial owner", 32, 700, TEAL)]), h, X + b.size[0] / 2 + 26, cy,
                  t0 + 0.35, slide=(-18, 0), name="s4:ubo", font_px=32)
    put_c(text([seg("Owned by", 30, 640, HDR)]), h, 300, 268, 37.6, slide=(-14, 0), name="s4:cap:up", font_px=30)
    downs = ["drake-petroleum-company-inc.us-de.entity.id", "maryland-oil-company-inc.us-de.entity.id",
             "warex-terminals-corporation.us-de.entity.id", "puritan-oil-company-inc.us-nj.entity.id"]
    y0, step = 630, 92
    line(h, [(LX, fcy + fh), (LX, y0 + step * 3)], 39.6, dur=0.7)
    for k, eid in enumerate(downs):
        cy = y0 + step * k
        t0 = 39.8 + 0.2 * k
        line(h, [(LX, cy), (X, cy)], t0, dur=0.2)
        put_c(render_box(eid, 34), h, X, cy, t0 + 0.08, slide=(-36, 0), name=f"s4:down{k}", font_px=34)
    put_c(text([seg("Subsidiaries", 30, 640, HDR)]), h, 300, 768, 39.7, slide=(-14, 0), name="s4:cap:down",
          font_px=30)


# ghost registrations (only visible in the wide shot): outline boxes branching off the spine
GHOSTS = []


def build_ghosts():
    rng = np.random.default_rng(11)
    y = 760.0
    while y < 6400:
        side = -1
        w = float(rng.uniform(260, 620))
        x1 = -float(rng.uniform(160, 420))
        x0 = x1 - w
        t0 = float(rng.uniform(42.6, 47.6))
        GHOSTS.append((x0, y, x1, y + 58, t0, side))
        if rng.uniform() < 0.55:
            w2 = float(rng.uniform(240, 560))
            xx1 = x0 - float(rng.uniform(140, 300))
            GHOSTS.append((xx1 - w2, y + float(rng.uniform(-20, 20)), xx1, y + 58, t0 + 0.3, side))
        y += float(rng.uniform(95, 150))
    # right side beyond the scene content
    y = -500.0
    while y < 6400:
        w = float(rng.uniform(240, 560))
        x0 = float(rng.uniform(2900, 3300))
        GHOSTS.append((x0, y, x0 + w, y + 58, float(rng.uniform(42.6, 47.6)), 1))
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
    out = []
    for e in ELS:
        a = e.life(t)
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
    y_top = to_screen((0, SPINE_Y0), cam)[1]
    y_bot = to_screen((0, SPINE_Y1), cam)[1]
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
        span = SPINE_Y1 - SPINE_Y0
        for k in range(14):
            u = (k / 14 + 3 * t / T) % 1.0
            wy = SPINE_Y0 + span * u
            px, py = to_screen((0, wy), cam)
            if -60 < py < H + 60:
                glows.append((30 * max(s, 0.35), px, py, 0.55 * math.sin(math.pi * u) ** 0.3))

    # --- scene connectors (drawn in progressively)
    for ln in LNS:
        p, a = ln.state(t)
        if p <= 0 or a <= 0.01:
            continue
        sp = [to_screen(q, cam) for q in (ln.ptsfn(t) if ln.ptsfn else ln.pts)]
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
        elif ln.ptsfn:
            glows.append((16 * max(s, 0.4), sp[0][0], sp[0][1], 0.75 * a))
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
    build_opening()
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
        os.makedirs("/workspace/booth-preview/v5", exist_ok=True)
        ts = [float(x) for x in sys.argv[2:]] or [3, 6.5, 17, 24.5, 28, 33.5, 41.5, 45, 47.5, 51]
        for tt in ts:
            render_frame(int(round(tt * FPS))).save(f"/workspace/booth-preview/v5/t{tt:05.2f}.png")
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
