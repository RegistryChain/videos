#!/usr/bin/env python3
"""Entity.ID booth loop v7 (production): rock-steady text, person as ultimate beneficial owner, one ID in web2 + web3.

Text steadiness: no camera drift, no scale changes while text is readable, every sprite composited at integer pixels
from a cached 1x raster, camera keys hold exactly still during every read, glows / pulses are masked out of text
regions so held text pixels never change.

80 s, 1920x1080, 30 fps. Every motion is a function of wrap(t), so frame N == frame 0.
Data: prod snapshots (read-only, cached 2026-10-08: v4-raw-*.json) + v5-real-data.json. People appear as initials only.
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
T = 80.0
NFRAMES = int(round(FPS * T))
_FONT_NAME = "Inter-VariableFont_opsz,wght.ttf"
_FONT_CANDIDATES = [
    os.environ.get("ENTITYID_FONT", ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", _FONT_NAME),
    "/usr/share/fonts/truetype/sand-box/google/Inter/" + _FONT_NAME,
    os.path.expanduser("~/Library/Fonts/" + _FONT_NAME),
    "/Library/Fonts/" + _FONT_NAME,
]
FONT_PATH = next((f for f in _FONT_CANDIDATES if f and os.path.exists(f)), None)
if FONT_PATH is None:
    sys.exit("Inter variable font not found: put " + _FONT_NAME + " in src/fonts/ or set ENTITYID_FONT")
TAU = 2 * math.pi
OUT = "/workspace/entityid-booth-loop-v7.mp4"
MASTER = "/workspace/booth-src/v7-master-lossless.mkv"
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
# ---- scene time bases: each scene builds in small steps, then everything holds perfectly still >= HOLD
TRAVEL = 2.2
HOLD = 4.8
SETTLE = 0.7                                       # last element of a build is fully settled this long after t_in
HERO_HOLD = 3.0                                    # wordmark centred; then a crossfade (no scaling) to the spine top
OPEN_ID0, OPEN_GAP_T = 4.2, 0.8
OPEN_END = OPEN_ID0 + OPEN_GAP_T * 5 + SETTLE + HOLD
A = OPEN_END + TRAVEL                              # agent speak5
A_END = A + 4.4 + 0.3 + 0.32 * 5 + SETTLE + HOLD
N = A_END + TRAVEL                                 # northstar: who is who, who owns what
N_END = N + 5.6 + HOLD
U = N_END + TRAVEL                                 # A.T. as ultimate beneficial owner
U_ROW0, U_ROW_GAP = 2.3, 0.6
U_END = U + 4.4 + SETTLE + HOLD
X = U_END + TRAVEL                                 # one ID, web2 and web3
X_END = X + 10.3 + SETTLE + HOLD
SPR_FADE0, SPR_FADE1 = X_END, X_END + 0.6         # all scene text fades before the wide pull-back (no text zooms)
WIDE0 = X_END + TRAVEL
STATS_IN0 = X_END + 0.5
STATS_COUNT1 = STATS_IN0 + 1.2
STATS_OUT0, STATS_OUT1 = STATS_COUNT1 + 2.0, STATS_COUNT1 + 2.35
CTA_IN0 = STATS_OUT1
CTA_IN1 = CTA_IN0 + 0.4
CTA_OUT0, CTA_OUT1 = 79.2, 79.6
HERO_IN0, HERO_IN1 = 79.3, 79.9
RESET0, RESET1 = CTA_IN0 - 0.3, CTA_IN1 + 0.2     # lines and ghosts fade while the CTA comes up
TITLE_IN0 = TITLE_IN1 = TITLE_OUT0 = TITLE_OUT1 = -1.0
CAP_A = None

HOME2 = (810.0, 1300.0)
HOME3 = (810.0, 2600.0)
HOME4 = (810.0, 3900.0)
HOMEX = (1150.0, 5200.0)
SPINE_Y0, SPINE_Y1 = -380.0, 5000.0
WM_ANCHOR = (0.0, -445.0)
WIDE = (-150.0, 2500.0, 0.17)

# camera keys: (t, x, y, scale). Two identical keys around every hold: the camera is exactly still while reading.
CAM_KEYS = [
    (0.0, 0, 0, 1.0),
    (OPEN_END, 0, 0, 1.0),
    (A, HOME2[0], HOME2[1], 1.0),
    (A_END, HOME2[0], HOME2[1], 1.0),
    (N, HOME3[0], HOME3[1], 1.0),
    (N_END, HOME3[0], HOME3[1], 1.0),
    (U, HOME4[0], HOME4[1], 1.0),
    (U_END, HOME4[0], HOME4[1], 1.0),
    (X, HOMEX[0], HOMEX[1], 1.0),
    (X_END, HOMEX[0], HOMEX[1], 1.0),
    (WIDE0, *WIDE),
    (CTA_OUT0, *WIDE),
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
    u = clamp((t - a[0]) / (t1 - a[0]), 0.0, 1.0)
    u = u * u * (3 - 2 * u)
    ls = math.log(a[3]) + (math.log(b[3]) - math.log(a[3])) * u
    s = math.exp(ls)
    # interpolate the focus so the zoom feels anchored: blend in screen space weighted by scale
    wa, wb = a[3] * (1 - u), b[3] * u
    x = (a[1] * wa + b[1] * wb) / (wa + wb)
    y = (a[2] * wa + b[2] * wb) / (wa + wb)
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
                 font_px=None, home=None, keep=False, move=None, scalefn=None, t_out=None):
        self.img = img
        self.x, self.y = x, y
        self.t_in, self.dur, self.slide = t_in, dur, slide
        self.parent, self.name, self.dyn = parent, name, dyn
        self.font_px = font_px
        self.keep = keep
        self.move = move
        self.scalefn, self.t_out = scalefn, t_out
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
        if self.t_out is not None and t > self.t_out:
            a *= 1 - smoother((t - self.t_out) / 0.5)
        if not self.keep and t > SPR_FADE0:
            a *= 1 - smoother((t - SPR_FADE0) / (SPR_FADE1 - SPR_FADE0))
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


# ---------------------------------------------------------------- opening: wordmark first, then one ID at a time
OPEN_IDS = [("speak5.ai.entity.id", "AI agent"), ("northstar-growth.public.entity.id", "Agency"),
            ("compass-residency.public.entity.id", "Cooperative"), ("hummingbot.ai.entity.id", "AI agent"),
            ("wyoming-bank-trust.us-wy.entity.id", "Commercial bank"), ("suma.us.entity.id", "Credit union")]
OPEN_GAP = 60.0


def build_opening():
    wm = render_rich([seg("Entity.ID", 66, 720, TXT, track=1.0)])
    El(wm, WM_ANCHOR[0] - wm.size[0] / 4, WM_ANCHOR[1] - wm.size[1] / 4, HERO_HOLD + 0.3, dur=0.6,
       name="open:wordmark", font_px=66)
    for k, (eid, typ) in enumerate(OPEN_IDS):
        side = 1 if k % 2 == 0 else -1
        yc = -250 + 104 * k
        t0 = OPEN_ID0 + OPEN_GAP_T * k
        idimg = render_rich([seg(eid, 50, 600, TXT)])
        tyimg = render_rich([seg(typ.upper(), 28, 660, TEAL, track=2.6)])
        w = idimg.size[0] / 2
        x = OPEN_GAP if side > 0 else -OPEN_GAP - w
        El(idimg, x, yc - idimg.size[1] / 4, t0, dur=0.5, slide=(-side * 30, 0), name=f"open:{eid}", font_px=50)
        tw = tyimg.size[0] / 2
        tx = x + 2 if side > 0 else -OPEN_GAP - tw - 2
        El(tyimg, tx, yc - 58 - tyimg.size[1] / 4, t0 + 0.15, dur=0.45, name=f"open:type:{eid}", font_px=28)
        Ln([(0, yc), (side * (OPEN_GAP - 14), yc)], t0, dur=0.35, val=0.85)


def hero_alpha(t):
    """Centred wordmark: shown 0..HERO_HOLD, crossfades out (no scaling); fades back in at the loop end."""
    if t >= HERO_IN0:
        return smoother((t - HERO_IN0) / (HERO_IN1 - HERO_IN0))
    if t < HERO_HOLD:
        return 1.0
    return 1 - smoother((t - HERO_HOLD) / 0.6)


def hero_sub_alpha(t):
    return hero_alpha(t)


# ---------------------------------------------------------------- scenes
def build_scenes():
    # ---------- scene 2: AI agent speak5.ai.entity.id (real on-chain registration; see v5-real-data.json) ----------
    h = HOME2
    fb = render_box("speak5.ai.entity.id", 44, focus=True)
    put(fb, h, 230, 96, A - 1.3, dur=1.0, slide=(0, -300), name="s2:focus", font_px=44)
    fy = 96 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], A - 0.5, dur=0.4)
    line(h, [(272, 96 + fb.size[1] / 2), (272, 205)], A - 0.1, dur=0.3)
    card = put(render_card(520, 226), h, 230, 205, A + 0.2, dur=0.5, slide=(0, 18), name="s2:card")
    rows = [
        [seg("Speak5 Agent", 42, 700, TXT)],
        [seg("AI agent", 30, 520, BODY, gap=16), seg("✓ Approved", 28, 640, GREEN, chip=True)],
        [seg("Formed ", 30, 450, DIM), seg("2026-09-15", 30, 560, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (258, 326, 386))):
        put_c(text(r), h, 262, cy, A + 0.4 + 0.25 * k, slide=(-24, 0), parent=card, name=f"s2:row{k}",
              font_px=r[0]["s"])
    k0 = A + 2.0                                  # Know-Your-Agent
    line(h, [(750, 318), (820, 318)], k0 - 0.4, dur=0.3)
    line(h, [(820, 200), (820, 440)], k0 - 0.2, dur=0.6, pulse=True)
    line(h, [(820, 200), (854, 200)], k0 - 0.1, dur=0.25)
    put_c(text([seg("Know-Your-Agent", 32, 660, HDR)]), h, 866, 200, k0, slide=(-20, 0), name="s2:h:kya", font_px=32)
    line(h, [(886, 226), (886, 340)], k0 + 0.2, dur=0.4)
    line(h, [(886, 270), (912, 270)], k0 + 0.3, dur=0.2)
    put_c(text([seg("Anchored to subject of rights", 30, 520, BODY, gap=12), seg("→", 32, 600, TEAL)]),
          h, 924, 270, k0 + 0.35, slide=(-18, 0), name="s2:anchor", font_px=30)
    put_c(render_box("speak5.public.entity.id", 34), h, 1400, 270, k0 + 0.75, slide=(-40, 0), name="s2:venture",
          font_px=34)
    line(h, [(886, 340), (912, 340)], k0 + 0.9, dur=0.2)
    put_c(text([seg("Custodian · ", 30, 450, DIM), seg("K.S.", 30, 700, TXT, gap=14),
                seg("KYC verified ✓", 30, 600, GREEN)]), h, 924, 340, k0 + 1.0, slide=(-18, 0),
          name="s2:custodian", font_px=30)
    a0 = A + 4.4                                  # Attribution: the agent's on-chain registration (real values)
    line(h, [(820, 440), (854, 440)], a0 - 0.1, dur=0.25)
    put_c(text([seg("Attribution", 32, 660, HDR)]), h, 866, 440, a0, slide=(-20, 0), name="s2:h:att", font_px=32)
    att = [
        [seg("On-chain agent · ", 30, 450, DIM), seg("#50800 · Ethereum", 30, 600, BODY)],
        [seg("Endpoint · ", 30, 450, DIM), seg("speak5.io", 30, 600, BODY)],
        [seg("Status · ", 30, 450, DIM), seg("Active ✓", 30, 600, GREEN)],
        [seg("Payments · ", 30, 450, DIM), seg("x402 ✗", 30, 600, AMBER)],
        [seg("Trust models · ", 30, 450, DIM), seg("none declared", 30, 560, BODY)],
        [seg("Reputation · ", 30, 450, DIM), seg("no reviews yet", 30, 560, BODY)],
    ]
    line(h, [(886, 470), (886, 760)], a0 + 0.2, dur=0.8)
    for k, r in enumerate(att):
        put_c(text(r), h, 912, 496 + 52 * k, a0 + 0.3 + 0.32 * k, slide=(-18, 0), name=f"s2:att{k}", font_px=30)

    # ---------- scene 3: people ownership example, northstar-growth.public.entity.id ----------
    h = HOME3
    fb = render_box("northstar-growth.public.entity.id", 44, focus=True)
    put(fb, h, 230, 88, N - 1.3, dur=1.0, slide=(0, -300), name="s3:focus", font_px=44)
    fy = 88 + fb.size[1] / 4
    line(h, [(150, fy + 40), (196, fy), (230, fy)], N - 0.5, dur=0.4)
    line(h, [(272, 88 + fb.size[1] / 2), (272, 196)], N - 0.1, dur=0.3)
    card = put(render_card(560, 280), h, 230, 196, N + 0.2, dur=0.5, slide=(0, 18), name="s3:card")
    rows = [
        [seg("Northstar Growth Agency", 38, 700, TXT)],
        [seg("Agency", 30, 520, BODY, gap=16), seg("Pending approval", 28, 640, AMBER, chip=True)],
        [seg("Formed ", 30, 450, DIM), seg("2026-06-23", 30, 560, BODY)],
        [seg("Partner signatures · ", 30, 450, DIM), seg("2", 30, 600, BODY)],
    ]
    for k, (r, cy) in enumerate(zip(rows, (250, 316, 376, 432))):
        put_c(text(r), h, 262, cy, N + 0.4 + 0.25 * k, slide=(-24, 0), parent=card, name=f"s3:row{k}",
              font_px=r[0]["s"])
    w0 = N + 2.2                                  # who is who
    line(h, [(790, 330), (836, 330)], w0 - 0.4, dur=0.3)
    line(h, [(836, 214), (836, 560)], w0 - 0.2, dur=0.6, pulse=True)
    line(h, [(836, 214), (866, 214)], w0 - 0.1, dur=0.25)
    put_c(text([seg("Who is who", 32, 660, HDR)]), h, 878, 214, w0, slide=(-20, 0), name="s3:h:who", font_px=32)
    line(h, [(898, 240), (898, 418)], w0 + 0.15, dur=0.4)
    for k, (ini, cy) in enumerate((("A.T.", 304), ("B.R.", 418))):
        line(h, [(898, cy), (916, cy)], w0 + 0.25 + 0.4 * k, dur=0.2)
        put_c(render_avatar(ini, 44), h, 920, cy, w0 + 0.3 + 0.4 * k, dur=0.4, name=f"s3:av:{ini}", font_px=31)
        put_c(text([seg("Manager · Signer", 30, 560, BODY)]), h, 1028, cy, w0 + 0.45 + 0.4 * k, slide=(-18, 0),
              name=f"s3:roles:{ini}", font_px=30)
    o0 = N + 4.0                                  # who owns what
    line(h, [(836, 560), (866, 560)], o0 - 0.1, dur=0.25)
    put_c(text([seg("Who owns what", 32, 660, HDR)]), h, 878, 560, o0, slide=(-20, 0), name="s3:h:owns", font_px=32)
    line(h, [(898, 586), (898, 760), (916, 760)], o0 + 0.1, dur=0.3)
    dn0 = o0 + 0.2

    def donut_fn(t, t0=dn0):
        return render_donut(smoother((t - t0) / 1.4) if t >= t0 else 0.0)
    put(donut_fn(dn0 + 2), h, 922, 760 - 142, dn0, dur=0.35, dyn=donut_fn, name="s3:donut")
    for k, (ini, pct, col, cy) in enumerate((("A.T.", 60, (122, 170, 255, 255), 712), ("B.R.", 40, TEAL, 800))):
        sw = text([seg("■", 30, 700, col, gap=10), seg(ini, 30, 640, TXT)])
        put_c(sw, h, 1232, cy, dn0 + 0.2 + 0.2 * k, slide=(-16, 0), name=f"s3:leg:{ini}", font_px=30)
        cf = count_text(dn0, 1.4, pct, "{}%", 34, 700, col, sync=True)
        put_c(cf(99), h, 1352, cy, dn0 + 0.2 + 0.2 * k, slide=(-16, 0), dyn=cf, name=f"s3:legpct:{ini}", font_px=34)

    # ---------- scene 4: the person behind it: A.T. as ultimate beneficial owner (prod member records) ----------
    # Real: one wallet (same person) is a member with roles manager + signer in all three app entities;
    # % = that member's shares / total shares: northstar-growth 60/100, compass-residency 100/100, field-notes-by-ace 20/100.
    h = HOME4
    av = render_avatar("A.T.", 52)
    line(h, [(150, 250), (194, 206), (262, 206)], U - 0.3, dur=0.4)
    put_c(av, h, 266, 206, U + 0.1, dur=0.45, name="s4:avatar", font_px=37)
    put_c(text([seg("Ultimate beneficial owner", 38, 700, TEAL, gap=14), seg("· A.T.", 38, 700, TXT)]), h, 396, 184,
          U + 0.5, slide=(-20, 0), name="s4:ubo", font_px=38)
    put_c(text([seg("Manager · Signer", 30, 560, BODY, gap=14), seg("· same wallet in all three", 30, 450, DIM)]),
          h, 398, 238, U + 0.9, slide=(-20, 0), name="s4:roles", font_px=30)
    line(h, [(318, 262), (318, 800)], U + 1.5, dur=0.8, pulse=True)
    put_c(text([seg("Owns", 32, 660, HDR)]), h, 340, 346, U + 1.6, slide=(-14, 0), name="s4:owns", font_px=32)
    rows = [("northstar-growth.public.entity.id", 60, [seg("Agency · ", 30, 520, BODY), seg("Pending approval", 30, 600, AMBER)]),
            ("compass-residency.public.entity.id", 100, [seg("Cooperative · ", 30, 520, BODY), seg("Approved ✓", 30, 600, GREEN)]),
            ("field-notes-by-ace.public.entity.id", 20, [seg("Venture", 30, 520, BODY)])]
    boxes = [render_box(eid, 34) for eid, _, _ in rows]
    bx = 420
    pct_x = bx + max(b.size[0] for b in boxes) / 2 + 40
    for k, ((eid, pct, typ), b) in enumerate(zip(rows, boxes)):
        cy = 440 + 160 * k
        t0 = U + U_ROW0 + U_ROW_GAP * k
        line(h, [(318, cy), (bx - 8, cy)], t0, dur=0.25)
        put_c(b, h, bx, cy, t0 + 0.1, dur=0.45, slide=(-24, 0), name=f"s4:box{k}", font_px=34)
        put_c(text([seg(f"{pct}%", 44, 700, TEAL)]), h, pct_x, cy, t0 + 0.3, dur=0.45, name=f"s4:pct{k}", font_px=44)
        put_c(text(typ), h, pct_x + 150, cy, t0 + 0.4, dur=0.45, name=f"s4:type{k}", font_px=30)
    put_c(text([seg("% = shares held in each entity's member register", 28, 450, DIM)]), h, 340, 920,
          U + U_ROW0 + U_ROW_GAP * 2 + 0.6, dur=0.5, name="s4:note", font_px=28)

    # ---------- scene 5: one ID, web2 and web3 (illustrative UI mock; card fields from the prod doc) ----------
    # hummingbot.ai.entity.id (prod): name "Hummingbot", category "Agent", registrar "ai",
    # owner 0xd873FaFd02351e6474906CD9233B454117b834DF (registry seeding wallet, not a person).
    h = HOMEX
    ttl = text([seg("One identifier. Web2 and Web3.", 58, 700, TXT)])
    put_c(ttl, h, 960 - ttl.size[0] / 4, 92, X + 0.1, dur=0.5, name="s5:title", font_px=58)
    tag = text([seg("Illustrative UI mock-up", 26, 520, DIM, track=1.0)])
    put_c(tag, h, 960 - tag.size[0] / 4, 148, X + 0.4, dur=0.5, name="s5:tag", font_px=26)
    eid = "hummingbot.ai.entity.id"
    # one rail under both worlds (non-text motion during the hold: a pulse travels along it)
    line(h, [(90, 862), (1830, 862)], X + 0.9, dur=1.4, pulse=True, val=0.6)
    line(h, [(762, 466), (818, 466)], X + 5.0, dur=0.3, pulse=True)
    # (a) web2: browser
    bw = put(render_window(690, 540, "browser"), h, 70, 196, X + 0.9, dur=0.5, name="s5:browser")
    tf = typing(eid, X + 1.4, 0.075, 30)
    put_c(tf(999), h, 132, 300, X + 1.35, dur=0.15, dyn=tf, parent=bw, name="s5:url", font_px=30)
    card = put(render_card(610, 250), h, 110, 384, X + 3.4, dur=0.5, parent=bw, name="s5:card")
    rws = [[seg("Hummingbot", 40, 700, TXT)],
           [seg("Type · ", 30, 450, DIM), seg("AI agent", 30, 600, BODY)],
           [seg("Registrar · ", 30, 450, DIM), seg("ai", 30, 600, BODY)]]
    for k2, (r, cy) in enumerate(zip(rws, (440, 512, 572))):
        put_c(text(r), h, 140, cy, X + 3.6 + 0.2 * k2, dur=0.4, parent=card, name=f"s5:card{k2}", font_px=r[0]["s"])
    c2 = text([seg("Web2 · type it in a browser", 34, 660, HDR)])
    put_c(c2, h, 415 - c2.size[0] / 4, 790, X + 4.3, dur=0.5, name="s5:cap2", font_px=34)
    # (b) web3: generic wallet (no brand marks) + confirmation
    wl = put(render_window(500, 540, "wallet"), h, 820, 196, X + 5.0, dur=0.5, name="s5:wallet")
    put_c(text([seg("Recipient", 28, 560, DIM)]), h, 852, 300, X + 5.3, dur=0.4, parent=wl, name="s5:rlabel", font_px=28)
    tf2 = typing(eid, X + 5.6, 0.075, 30)
    put_c(tf2(999), h, 868, 360, X + 5.55, dur=0.15, dyn=tf2, parent=wl, name="s5:recip", font_px=30)
    put_c(text([seg("Resolves to ", 28, 450, DIM), seg("0xd873…34DF", 30, 600, TXT, gap=10), seg("✓", 30, 700, GREEN)]),
          h, 852, 432, X + 7.6, dur=0.45, parent=wl, name="s5:resolve", font_px=28)
    put_c(text([seg("Amount", 28, 560, DIM)]), h, 852, 520, X + 8.0, dur=0.4, parent=wl, name="s5:alabel", font_px=28)
    put_c(text([seg("0.01 ETH", 30, 600, BODY, gap=12), seg("(example)", 26, 450, DIM)]), h, 868, 580, X + 8.1,
          dur=0.4, parent=wl, name="s5:amount", font_px=26)
    line(h, [(1322, 466), (1376, 466)], X + 8.6, dur=0.3, pulse=True)
    cf = put(render_window(470, 540, "confirm"), h, 1380, 196, X + 8.8, dur=0.5, name="s5:confirm")
    put_c(text([seg("Send to", 28, 560, DIM)]), h, 1410, 300, X + 9.1, dur=0.4, parent=cf, name="s5:sendto", font_px=28)
    put_c(text([seg(eid, 30, 640, TXT)]), h, 1410, 346, X + 9.2, dur=0.4, parent=cf, name="s5:sendid", font_px=30)
    put_c(text([seg("0xd873…34DF", 28, 520, DIM)]), h, 1410, 392, X + 9.3, dur=0.4, parent=cf, name="s5:sendaddr",
          font_px=28)
    put_c(text([seg("0.01 ETH", 30, 600, BODY, gap=12), seg("(example)", 26, 450, DIM)]), h, 1410, 448, X + 9.4,
          dur=0.4, parent=cf, name="s5:sendamt", font_px=26)
    ok = text([seg("Confirmed ✓", 34, 700, GREEN, chip=True)])
    put_c(ok, h, 1615 - ok.size[0] / 4, 580, X + 10.3, dur=0.45, parent=cf, name="s5:confirmed", font_px=34)
    c3 = text([seg("Web3 · send to it from a wallet or contract", 34, 660, HDR)])
    put_c(c3, h, 1335 - c3.size[0] / 4, 790, X + 9.9, dur=0.5, name="s5:cap3", font_px=34)


def typing(full, t0, per_char, size):
    """Address-bar style typing: characters appear one at a time (left-aligned, so typed text never moves)."""
    cache = {}

    def fn(t):
        n = len(full) if t >= t0 + per_char * len(full) else max(0, int((t - t0) / per_char) + 1) if t >= t0 else 0
        caret = n < len(full)
        img = cache.get(n)
        if img is None:
            segs = [seg(full[:n] or " ", size, 560, TXT)]
            if caret:
                segs.append(seg("|", size, 300, TEAL))
            img = render_rich(segs, shadow=False)
            cache[n] = img
        return img
    return fn


def render_window(w, h, kind):
    """Generic UI window mock (no brand marks): title bar with three dots, plus fields for the kind."""
    ss = 2
    im = Image.new("RGBA", (w * 2 * ss, h * 2 * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    S = 2 * ss
    d.rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=18 * S, fill=(12, 32, 92, 246),
                        outline=(156, 186, 248, 200), width=2 * S)
    d.rounded_rectangle([0, 0, w * S - 1, 56 * S], radius=18 * S, fill=(26, 58, 140, 255))
    d.rectangle([0, 38 * S, w * S - 1, 56 * S], fill=(26, 58, 140, 255))
    for k, col in enumerate(((255, 120, 110), (255, 200, 90), (110, 220, 140))):
        cx, cy = (28 + 24 * k) * S, 28 * S
        d.ellipse([cx - 7 * S, cy - 7 * S, cx + 7 * S, cy + 7 * S], fill=col + (230,))
    if kind == "browser":
        d.rounded_rectangle([30 * S, 72 * S, (w - 30) * S, 136 * S], radius=32 * S, fill=(6, 18, 60, 255),
                            outline=(120, 236, 228, 220), width=2 * S)
    elif kind == "wallet":
        d.rounded_rectangle([24 * S, 132 * S, (w - 24) * S, 196 * S], radius=12 * S, fill=(6, 18, 60, 255),
                            outline=(120, 236, 228, 220), width=2 * S)
        d.rounded_rectangle([24 * S, 352 * S, (w - 24) * S, 416 * S], radius=12 * S, fill=(6, 18, 60, 255),
                            outline=(156, 186, 248, 160), width=2 * S)
    im = im.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    label = {"browser": "Browser", "wallet": "Wallet", "confirm": "Confirm"}[kind]
    tl = render_rich([seg(label, 26, 600, BODY)], shadow=False)
    im.alpha_composite(tl, ((im.size[0] - tl.size[0]) // 2, (112 - tl.size[1]) // 2 + 2))
    return im


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
        t0 = float(rng.uniform(X_END + 0.8, X_END + 3.6))
        GHOSTS.append((x0, y, x1, y + 58, t0, side))
        if rng.uniform() < 0.55:
            w2 = float(rng.uniform(240, 560))
            xx1 = x0 - float(rng.uniform(140, 300))
            GHOSTS.append((xx1 - w2, y + float(rng.uniform(-20, 20)), xx1, y + 58, t0 + 0.3, side))
        y += float(rng.uniform(95, 150))
    # right side beyond the scene content
    y = -300.0
    while y < 5000:
        w = float(rng.uniform(240, 560))
        x0 = float(rng.uniform(2900, 3300))
        GHOSTS.append((x0, y, x0 + w, y + 58, float(rng.uniform(X_END + 0.8, X_END + 3.6)), 1))
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
    return 0.0


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
        k = e.scalefn(t) if e.scalefn else 1.0
        if k != 1.0:
            wx, wy, ww, wh = wx + ww * (1 - k) / 2, wy + wh * (1 - k) / 2, ww * k, wh * k
        sx, sy = to_screen((wx, wy), cam)
        sw, sh = ww * s, wh * s
        if sx > W or sy > H or sx + sw < 0 or sy + sh < 0:
            continue
        a *= edge_alpha(sx, sy, sx + sw, sy + sh, t)
        if a <= 0.004:
            continue
        out.append((e, img, sx, sy, sw, sh, a, s * k))
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
            vf *= 1 - 0.88 * hero_alpha(t)
            canvas[r0:r1, c0:c1] += (vf[:, None, None] * prof[None, :, None]) * np.array([120, 160, 255], np.float32)[None, None, :]
        # spine pulses travelling down (periodic: integer cycles per loop)
        span = SPINE_Y1 - SPINE_Y0
        for k in range(14):
            u = (k / 14 + 2 * t / T) % 1.0
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
            u = (t / (T / round(T / 3.0)) + ln.ph) % 1.0
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
    pl = placed(t, cam)
    if glows:
        gl = np.zeros_like(canvas)
        for r, x, y, g in glows:
            if -120 < x < W + 120 and -120 < y < H + 120:
                blit_add(gl, glow_sprite(r), x, y, g)
        canvas += gl * glow_keepout(t, pl)[..., None]

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
    for e, img, x, y, w, h, a, f in pl:
        wi, hi = max(2, int(round(w))), max(2, int(round(h)))
        sm = raster(img, wi, hi, f)
        # dim under the CTA / stats band like the background
        dd = dimf
        if ob > 0.001:
            cyy = y + h / 2
            dd *= 1 - clamp((cyy - 600) / 220, 0, 1) * 0.78 * ob
        im.alpha_composite(_fade(sm, a * dd), (int(round(x)), int(round(y))))
        if want_rects:
            rects.append((e, x, y, x + wi, y + hi, a * dd, f))

    draw_wordmark(im, t, cam, dimf, rects if want_rects else None)
    draw_overlays(im, t, rects if want_rects else None)
    if want_rects:
        return im.convert("RGB"), rects
    return im.convert("RGB")


HERO_IMG = None
HERO_IMG1 = None
HERO_SUB = None
TAGLINE = None
_RASTER = {}


def raster(img, wi, hi, f):
    """Downsampled sprite, cached per (master, size): identical pixels every frame for a held sprite."""
    key = (id(img), wi, hi)
    hit = _RASTER.get(key)
    if hit is None:
        hit = img.resize((wi, hi), Image.Resampling.LANCZOS, reducing_gap=3.0 if f < 0.6 else None)
        if abs(f - 1.0) < 1e-9 or len(_RASTER) < 4000:
            _RASTER[key] = hit
    return hit


def overlay_boxes(t):
    out = []
    if hero_alpha(t) > 0.004:
        out.append((W / 2 - HERO_IMG.size[0] / 4, 470 - HERO_IMG.size[1] / 4, W / 2 + HERO_IMG.size[0] / 4,
                    470 + HERO_IMG.size[1] / 4 + 30 + HERO_SUB.size[1]))
    if stats_alpha(t) > 0.004:
        out.append((60, 740, W - 60, 960))
    if cta_alpha(t) > 0.004:
        out.append((W / 2 - CTA.size[0] / 2 - 20, 90, W / 2 + CTA.size[0] / 2 + 20, QR_Y + QR_IMG.size[1] + 70))
    return out


def glow_keepout(t, pl):
    """1 outside text / box sprites, 0 inside (feathered): moving glows never touch held text pixels."""
    from PIL import ImageFilter
    km = Image.new("L", (W, H), 0)
    kd = ImageDraw.Draw(km)
    pad = 16
    boxes = [(x, y, x + w, y + h) for e, img, x, y, w, h, a, f in pl] + overlay_boxes(t)
    if not boxes:
        return np.ones((H, W), np.float32)
    for x0, y0, x1, y1 in boxes:
        kd.rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], fill=255)
    km = km.filter(ImageFilter.BoxBlur(7))
    return 1.0 - np.asarray(km, dtype=np.float32) / 255.0


def draw_wordmark(im, t, cam, dimf, rects=None):
    """Centred hero wordmark + subtitle (overlay, never scaled or moved)."""
    a = hero_alpha(t)
    if a > 0.004:
        x = int(round(W / 2 - HERO_IMG1.size[0] / 2))
        y = int(round(470 - HERO_IMG1.size[1] / 2))
        im.alpha_composite(_fade(HERO_IMG1, a), (x, y))
        _ov_add(rects, "ov:hero", x, y, HERO_IMG1, a, 132)
    sa = hero_sub_alpha(t)
    if sa > 0.004:
        x = int((W - HERO_SUB.size[0]) / 2)
        y = int(470 + HERO_IMG1.size[1] / 2 + 26)
        im.alpha_composite(_fade(HERO_SUB, sa), (x, y))
        _ov_add(rects, "ov:herosub", x, y, HERO_SUB, sa, 44)


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
        x = int((W - TAGLINE.size[0]) / 2)
        im.alpha_composite(_fade(TAGLINE, ca), (x, 100))
        _ov_add(rects, "ov:tagline", x, 100, TAGLINE, ca, 64)
        rise = int(round(16 * (1 - smoother((t - CTA_IN0) / 0.8))))
        w, h = CTA.size
        img = CTA
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
    global HERO_IMG, HERO_SUB, TAGLINE
    HERO_IMG = render_rich([seg("Entity.ID", 132, 720, TXT, track=1.5)])
    global HERO_IMG1
    HERO_IMG1 = render_text_1x([seg("Entity.ID", 132, 720, TXT, track=1.5)])
    HERO_SUB = render_text_1x([seg("Universal Verified Facts ID", 44, 560, HDR, track=1.0)])
    TAGLINE = render_text_1x([seg("Every entity. One verifiable identity.", 64, 640, TXT, track=0.3)])
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
        os.makedirs("/workspace/booth-preview/v7", exist_ok=True)
        ts = [float(x) for x in sys.argv[2:]] or [1.0, 3.6, 12.0, 25.0, 38.0, 50.0, 57.5, 62.0, 68.0, 72.0, 77.0, 79.6]
        for tt in ts:
            render_frame(int(round(tt * FPS))).save(f"/workspace/booth-preview/v7/t{tt:05.2f}.png")
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
