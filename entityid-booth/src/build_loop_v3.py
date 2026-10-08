#!/usr/bin/env python3
"""Entity.ID booth loop v3 (real entity ids): a live registry. 40 s, every motion periodic, so t=T == t=0."""

import math
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FPS = 30
T = 40.0
NFRAMES = int(FPS * T)
FONT_PATH = "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
TAU = 2 * math.pi
OUT = "/workspace/entityid-booth-loop-v3.mp4"


# ---------------------------------------------------------------- easing
def clamp(v, a, b):
    return a if v < a else b if v > b else v


def smoother(u):
    u = clamp(u, 0.0, 1.0)
    return u * u * u * (u * (u * 6 - 15) + 10)


def ease_out_back(u, k=2.2):
    u = clamp(u, 0.0, 1.0)
    return 1 + (k + 1) * (u - 1) ** 3 + k * (u - 1) ** 2


def wrap(t):
    return t % T


def per(t, n, ph=0.0):
    """Periodic sine with n whole cycles per loop."""
    return math.sin(TAU * n * t / T + ph)


# ---------------------------------------------------------------- world
HUBS = {
    "AI": dict(pos=(-1600.0, -150.0), label="AI Agents"),
    "DAO": dict(pos=(-950.0, 230.0), label="DAOs"),
    "DE": dict(pos=(-450.0, -480.0), label="Delaware · DE"),
    "CO": dict(pos=(450.0, -480.0), label="Companies"),
    "WY": dict(pos=(950.0, 230.0), label="Wyoming · WY"),
    "NGO": dict(pos=(1600.0, -150.0), label="NGOs"),
    "US": dict(pos=(0.0, 380.0), label="United States · US"),
}
HUB_ORDER = ["AI", "DAO", "DE", "CO", "WY", "NGO", "US"]
HUB_LINKS = [("AI", "DAO"), ("AI", "DE"), ("DAO", "DE"), ("DAO", "US"), ("DE", "CO"), ("DE", "US"),
             ("CO", "US"), ("CO", "WY"), ("CO", "NGO"), ("WY", "NGO"), ("WY", "US")]

# entity pills: (hub, text, local dot pos, side, birth or None = persistent, font px)
PILLS = [
    # Real entity ids from the production registry. Persistent pills are on screen at t=0.
    ("AI", "hummingbot.ai.entity.id", (0, -270), "n", None, 50),
    ("AI", "speak5.ai.entity.id", (280, 195), "s", None, 50),
    ("AI", "chaingpt.ai.entity.id", (-330, 240), "s", None, 50),
    ("DAO", "valleydao.ch.entity.id", (200, -240), "n", None, 50),
    ("DE", "andeavor.us-de.entity.id", (-150, -270), "n", 6.8, 50),
    ("DE", "predex.us-de.entity.id", (-200, 230), "s", 7.9, 50),
    ("CO", "dashtag.gb.entity.id", (150, -270), "n", 7.3, 50),
    ("CO", "emeris.ky.entity.id", (220, 230), "s", 8.6, 50),
    ("WY", "workverse.us-wy.entity.id", (-250, -230), "n", 12.9, 50),
    ("WY", "titlechain.us-wy.entity.id", (300, 60), "e", 14.1, 50),
    ("NGO", "impactlife.us-ia.entity.id", (-60, -230), "n", 13.4, 50),
    ("NGO", "sayara.ch.entity.id", (250, 180), "s", 14.8, 50),
    ("US", "suma.us.entity.id", (-320, -170), "n", 19.1, 50),
    ("US", "meriwest.us.entity.id", (320, -170), "n", 19.9, 50),
]

# transient unlabeled registrations (hub, birth)
REG_TIMES = {
    "AI": [38.6, 39.3, 0.6, 1.5, 2.6, 3.4],
    "DAO": [0.3, 1.9, 3.8, 29.6],
    "DE": [6.6, 7.2, 8.4, 9.3, 23.5, 31.0],
    "CO": [6.9, 8.1, 9.6, 10.1, 25.7, 32.2],
    "WY": [12.6, 13.6, 14.5, 15.6, 27.0],
    "NGO": [12.8, 14.1, 15.2, 16.0, 24.6],
    "US": [19.0, 19.5, 20.2, 20.8, 28.3],
}

# camera keys: t, x, y, scale
CAM_KEYS = [
    (0.0, -1290, -20, 0.86),
    (4.3, -1230, 10, 0.90),
    (5.6, -680, -230, 0.62),
    (7.0, -40, -460, 0.86),
    (10.4, 40, -440, 0.90),
    (11.7, 680, -230, 0.62),
    (13.0, 1230, 30, 0.86),
    (16.4, 1290, 60, 0.90),
    (17.7, 660, 220, 0.66),
    (19.0, 20, 390, 0.95),
    (20.6, -20, 400, 0.88),
    (22.6, 0, 240, 0.51),
    (27.8, 25, 232, 0.52),
    (32.6, -10, 226, 0.525),
    (36.8, -120, 220, 0.53),
    (38.5, -760, 120, 0.64),
]

SCALE_CLOSE = 0.88
TITLE_IN0, TITLE_IN1, TITLE_OUT0, TITLE_OUT1 = 28.6, 29.3, 32.4, 32.9
CTA_IN0, CTA_IN1, CTA_OUT0, CTA_OUT1 = 32.9, 33.4, 37.4, 37.9
STATS_IN0, STATS_COUNT1, STATS_OUT0, STATS_OUT1 = 22.9, 24.7, 26.0, 26.4
PILLARS_IN0, PILLARS_OUT0, PILLARS_OUT1 = 26.4, 28.2, 28.6
QR_URL = "https://app.entity.id"
LINK_ON0, LINK_DIM0, LINK_DIM1 = 20.6, 37.4, 39.4


# ---------------------------------------------------------------- camera (periodic Hermite spline)
def _cam_channel(idx, t):
    keys = CAM_KEYS
    n = len(keys)
    tt = [k[0] for k in keys]
    if idx == 3:
        vals = [math.log(k[3]) for k in keys]
    else:
        vals = [float(k[idx]) for k in keys]
    t = wrap(t)
    # find segment
    i = n - 1
    for j in range(n):
        t0 = tt[j]
        t1 = tt[j + 1] if j + 1 < n else T
        if t0 <= t < t1:
            i = j
            break
    j = (i + 1) % n
    t0 = tt[i]
    t1 = tt[j] if j != 0 else T

    def tangent(k):
        kp = (k - 1) % n
        kn = (k + 1) % n
        tp = tt[kp] if kp < k else tt[kp] - T
        tn = tt[kn] if kn > k else tt[kn] + T
        return (vals[kn] - vals[kp]) / (tn - tp) * 0.85

    h = t1 - t0
    u = (t - t0) / h
    m0 = tangent(i) * h
    m1 = tangent(j) * h
    p0, p1 = vals[i], vals[j]
    u2, u3 = u * u, u * u * u
    v = (2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * p1 + (u3 - u2) * m1
    return math.exp(v) if idx == 3 else v


def camera(t):
    x = _cam_channel(1, t) + 28 * per(t, 3, 0.4)
    y = _cam_channel(2, t) + 20 * per(t, 4, 1.3)
    s = _cam_channel(3, t) * (1 + 0.012 * per(t, 5, 0.2))
    rot = 0.034 * per(t, 1, 0.3) + 0.012 * per(t, 3, 2.0)
    return x, y, s, rot


def to_screen(p, cam):
    cx, cy, s, rot = cam
    dx, dy = p[0] - cx, p[1] - cy
    c, sn = math.cos(rot), math.sin(rot)
    return (W / 2 + (dx * c - dy * sn) * s, H / 2 + (dx * sn + dy * c) * s)


# ---------------------------------------------------------------- nodes
rng = np.random.default_rng(7)


def hub_pos(h, t):
    x, y = HUBS[h]["pos"]
    i = HUB_ORDER.index(h)
    return (x + 10 * per(t, 2, i), y + 8 * per(t, 3, i * 1.7))


class Sat:
    """An orbiting unlabeled node."""

    def __init__(self, hub, r, a0, k, birth=None):
        self.hub, self.r, self.a0, self.k, self.birth = hub, r, a0, k, birth
        self.death = None
        self.hue = float(rng.uniform(0, 0.45))
        self.ph = float(rng.uniform(0, TAU))
        self.pulse_period = float(rng.choice([1.6, 2.0, 2.5, 4.0]))
        self.pulse_ph = float(rng.uniform(0, 1))

    def pos(self, t):
        hx, hy = hub_pos(self.hub, t)
        a = self.a0 + self.k * TAU * t / T
        r = self.r * (1 + 0.04 * per(t, 2, self.ph))
        return (hx + r * math.cos(a), hy + 0.8 * r * math.sin(a))


class PillNode:
    def __init__(self, hub, text, local, side, birth, size):
        self.hub, self.text, self.local, self.side, self.birth, self.size = hub, text, local, side, birth, size
        self.death = None
        self.ph = float(rng.uniform(0, TAU))
        self.hue = 0.1
        self.pulse_period = 2.5
        self.pulse_ph = float(rng.uniform(0, 1))

    def pos(self, t):
        hx, hy = hub_pos(self.hub, t)
        return (hx + self.local[0] + 16 * per(t, 2, self.ph), hy + self.local[1] + 12 * per(t, 3, self.ph + 1))


SATS = []
for h in HUB_ORDER:
    n_persist = 6 if h in ("AI", "US") else 5
    for i in range(n_persist):
        SATS.append(Sat(h, float(rng.uniform(150, 330)), float(rng.uniform(0, TAU)), int(rng.choice([-1, 1]))))
    for b in REG_TIMES[h]:
        SATS.append(Sat(h, float(rng.uniform(160, 330)), float(rng.uniform(0, TAU)), int(rng.choice([-1, 1])), birth=b))
PILL_NODES = [PillNode(*p) for p in PILLS]


def offscreen(node, t, margin):
    if isinstance(node, PillNode):
        margin = 1000
    x, y = to_screen(node.pos(t), camera(t))
    return x < -margin or x > W + margin or y < -margin or y > H + margin


def assign_deaths():
    """A transient node leaves by being absorbed into its hub. Prefer moments when it is off camera,
    or when the camera is wide (entity pills hidden); never while the camera is close on it."""
    problems = []
    step = 2.0 / FPS
    for node in SATS + PILL_NODES:
        if node.birth is None:
            continue
        b = node.birth
        lo, hi = b + 6.0, b + T - 1.5
        need = 1.0
        found = None
        d = lo
        while d + need <= hi:
            ok = True
            tau = d
            while tau <= d + need:
                tw = wrap(tau)
                wide = camera(tw)[2] < 0.56
                if not (wide or offscreen(node, tw, 160)):
                    ok = False
                    break
                tau += step
            if ok:
                found = d
                break
            d += step
        if found is None:
            problems.append((node.hub, b, getattr(node, "text", "sat")))
            node.death = hi
        else:
            node.death = found + need
    return problems


ABSORB = 1.0


def node_pos(node, t):
    """Position including the absorb-into-hub motion at end of life."""
    p = node.pos(t)
    if node.birth is None:
        return p
    age = wrap(t - node.birth)
    life = node.death - node.birth
    k = (age - (life - ABSORB)) / ABSORB
    if k <= 0:
        return p
    k = smoother(k)
    h = hub_pos(node.hub, t)
    return (p[0] + (h[0] - p[0]) * k, p[1] + (h[1] - p[1]) * k)


def life_alpha(node, t):
    """Returns (alpha, pop_scale, age) for a node."""
    if node.birth is None:
        return 1.0, 1.0, 99.0
    age = wrap(t - node.birth)
    life = node.death - node.birth
    if age >= life:
        return 0.0, 0.0, age
    pop = ease_out_back(age / 0.55)
    a = smoother(age / 0.25)
    if age > life - 0.45:
        a *= 1 - smoother((age - (life - 0.45)) / 0.45)
    return a, pop, age


# ---------------------------------------------------------------- drawing helpers
BG = None


def make_background():
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xs - W / 2) / W
    ny = (ys - H / 2) / H
    r = np.sqrt(nx * nx + ny * ny)
    bg = np.zeros((H, W, 3), dtype=np.float32)
    bg[..., 0] = 8 + 7 * (1 - r)
    bg[..., 1] = 14 + 12 * (1 - r)
    bg[..., 2] = 26 + 16 * (1 - r)
    vig = np.clip(1.0 - np.maximum(r - 0.25, 0) * 1.15, 0.62, 1.0)
    bg *= vig[..., None]
    return bg


GLOW = {}


def node_rgb(hue):
    teal = np.array([64, 224, 214], dtype=np.float32)
    blue = np.array([96, 186, 255], dtype=np.float32)
    return teal * (1 - hue) + blue * hue


def glow_sprite(radius, hue):
    key = (int(round(radius)), int(round(hue * 10)))
    hit = GLOW.get(key)
    if hit is not None:
        return hit
    R = max(3, key[0])
    y, x = np.mgrid[-R:R + 1, -R:R + 1].astype(np.float32)
    d2 = (x * x + y * y) / float(R * R)
    d = np.sqrt(d2)
    halo = np.exp(-d2 * 2.55) * np.clip(1.0 - d, 0, 1)
    core = np.exp(-d2 * 36.0)
    mid = np.exp(-d2 * 8.0)
    col = node_rgb(key[1] / 10.0) / 255.0
    rgb = col[None, None, :] * (halo * 0.72 + mid * 0.22)[..., None]
    rgb = rgb + np.array([0.90, 0.99, 0.98], np.float32)[None, None, :] * core[..., None] * 0.95
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


def load_font(size, weight):
    f = ImageFont.truetype(FONT_PATH, size)
    f.set_variation_by_axes([32 if size >= 32 else max(14, size), weight])
    return f


def render_pill(text, size, hub=False):
    """Master pill at 2x. Returns RGBA image."""
    S = size * 2
    font = load_font(S, 640 if hub else 560)
    tw = font.getlength(text)
    cap_top = font.getbbox("H")[1]
    cap_h = font.getbbox("H")[3] - cap_top
    pad_x, pad_y = int(S * 0.48), int(S * 0.36)
    w = int(math.ceil(tw)) + 2 * pad_x
    h = int(cap_h + 2 * pad_y + S * 0.18)
    ss = 2
    pill = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(pill)
    fill = (9, 26, 42, 248) if hub else (5, 12, 24, 246)
    outline = (120, 236, 228, 230) if hub else (110, 226, 220, 130)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=h * ss // 2, fill=fill,
                        outline=outline, width=(5 if hub else 3) * ss)
    pill = pill.resize((w, h), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(pill)
    y = (h - cap_h) / 2 - cap_top - S * 0.04
    d.text((pad_x, y), text, font=font, fill=(246, 252, 253, 255))
    return pill


PILL_IMG = {}
HUB_IMG = {}


def paste_scaled(base, img, cx, cy, f, alpha):
    """Paste master (2x) image scaled by f/2 centred at (cx, cy)."""
    if alpha <= 0.01 or f <= 0.02:
        return
    w = max(2, int(round(img.size[0] * f / 2)))
    h = max(2, int(round(img.size[1] * f / 2)))
    x = cx - w / 2
    y = cy - h / 2
    if x > W or y > H or x + w < 0 or y + h < 0:
        return
    im = img.resize((w, h), Image.Resampling.LANCZOS)
    if alpha < 0.999:
        a = np.array(im, dtype=np.float32)
        a[..., 3] *= alpha
        im = Image.fromarray(a.astype(np.uint8), "RGBA")
    base.alpha_composite(im, (int(round(x)), int(round(y))))


def hub_focus(h, t, cam):
    """1 when the hub is near frame centre, 0 when it is only peeking in from an edge."""
    hp = to_screen(hub_pos(h, t), cam)
    d = math.hypot(hp[0] - W / 2, hp[1] - H / 2)
    return 1.0 - smoother((d - 455) / 110)


# id pills show only during their own camera stop (their pills are already faded at these bounds)
STOP_WINDOWS = {"AI": (38.6, 5.3), "DAO": (38.6, 5.3), "DE": (6.0, 11.4), "CO": (6.0, 11.4),
                "WY": (12.2, 17.4), "NGO": (12.2, 17.4), "US": (18.6, 21.6)}


def stop_gate(h, t):
    a, b = STOP_WINDOWS[h]
    u = wrap(t - a)
    span = wrap(b - a)
    if u > span:
        return 0.0
    return smoother(u / 0.3) * smoother((span - u) / 0.3)


def edge_fade(l, tp, r, bt):
    """Pills fade before they would touch the frame edge, so an id is never shown cut off."""
    over = max(0.0, 14 - l, r - (W - 14), 14 - tp, bt - (H - 14))
    return 1.0 - smoother(over / 50)


def pill_center(dot, side, w, h, gap):
    x, y = dot
    if side == "n":
        return x, y - gap - h / 2
    if side == "s":
        return x, y + gap + h / 2
    if side == "e":
        return x + gap + w / 2, y
    return x - gap - w / 2, y


def render_text(text, size, weight, fill, tracking=0):
    font = load_font(size, weight)
    widths = [font.getlength(ch) for ch in text]
    total = int(math.ceil(sum(widths) + tracking * (len(text) - 1))) + 8
    bb = font.getbbox("Ag")
    height = (bb[3] - bb[1]) + 16
    im = Image.new("RGBA", (total, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    base_y = 6 - bb[1]
    for pass_, col in ((1, (0, 0, 0, 150)), (0, fill)):
        x = 4
        for ch, wch in zip(text, widths):
            d.text((x, base_y + 2 * pass_), ch, font=font, fill=col)
            x += wch + tracking
    return im


TITLE = None
SUB = None


def title_alpha(t):
    if t < TITLE_IN0 or t >= TITLE_OUT1:
        return 0.0
    if t < TITLE_IN1:
        return smoother((t - TITLE_IN0) / (TITLE_IN1 - TITLE_IN0))
    if t < TITLE_OUT0:
        return 1.0
    return 1.0 - smoother((t - TITLE_OUT0) / (TITLE_OUT1 - TITLE_OUT0))


def link_state(t, k):
    """(draw progress, brightness) of hub link k."""
    t0 = LINK_ON0 + 0.15 * k
    if t < t0 or t >= LINK_DIM1:
        return 0.0, 0.0
    p = smoother((t - t0) / 1.3)
    if t < LINK_DIM0:
        return p, 1.0
    return 1.0, 1.0 - smoother((t - LINK_DIM0) / (LINK_DIM1 - LINK_DIM0))


# ---------------------------------------------------------------- frame
def render_frame(i):
    t = i / FPS
    cam = camera(t)
    s = cam[2]
    zoom = s / SCALE_CLOSE
    canvas = BG.copy()
    mask = Image.new("L", (W * 2, H * 2), 0)
    md = ImageDraw.Draw(mask)
    sprites = []  # (radius, hue, x, y, gain)

    hubs_scr = {h: to_screen(hub_pos(h, t), cam) for h in HUB_ORDER}
    line_w = (1.0 + 1.5 * zoom) * 2

    def line(p, q, val, width=None):
        if val <= 0.01:
            return
        md.line([(p[0] * 2, p[1] * 2), (q[0] * 2, q[1] * 2)], fill=int(clamp(val, 0, 1) * 255),
                width=max(2, int(round(width or line_w))))

    def pulses(p, q, period, ph, gain, rad, count=1):
        for c in range(count):
            u = ((t / period) + ph + c / count) % 1.0
            # fade at ends so pulses don't pop
            env = math.sin(math.pi * u)
            x = p[0] + (q[0] - p[0]) * u
            y = p[1] + (q[1] - p[1]) * u
            sprites.append((rad, 0.1, x, y, gain * env))

    # hub links: faint baseline always, bright draw-on 21-27.6
    for k, (a, b) in enumerate(HUB_LINKS):
        pa, pb = hubs_scr[a], hubs_scr[b]
        line(pa, pb, 0.16, line_w * 0.9)
        p, br = link_state(t, k)
        if br > 0 and p > 0:
            q = (pa[0] + (pb[0] - pa[0]) * p, pa[1] + (pb[1] - pa[1]) * p)
            line(pa, q, 0.95 * br, line_w * 1.5)
            if p < 1:
                sprites.append((26 * max(zoom, 0.6), 0.1, q[0], q[1], 1.1 * br))
            pulses(pa, pb, 2.0, 0.13 * k, 0.9 * br * smoother((p - 0.98) / 0.02 if p < 1 else 1), 16 * max(zoom, 0.6), 2)
        # a slow pulse always travels the faint link
        pulses(pa, pb, 5.0, 0.21 * k, 0.45, 12 * max(zoom, 0.6))

    # satellites
    sat_scr = []
    for n in SATS:
        a, pop, age = life_alpha(n, t)
        if a <= 0.004:
            sat_scr.append(None)
            continue
        sp = to_screen(node_pos(n, t), cam)
        hp = hubs_scr[n.hub]
        sat_scr.append((sp, a))
        if n.birth is not None:
            lf = n.death - n.birth
            if lf - 0.25 < age < lf + 0.0:
                sprites.append((70 * max(zoom, 0.55), 0.05, hp[0], hp[1], 0.7 * (1 - (lf - age) / 0.25)))
        grow = smoother(age / 0.45) if n.birth is not None else 1.0
        q = (hp[0] + (sp[0] - hp[0]) * grow, hp[1] + (sp[1] - hp[1]) * grow)
        line(hp, q, 0.5 * a)
        if grow >= 1:
            pulses(sp, hp, n.pulse_period, n.pulse_ph, 0.75 * a, 9 + 6 * zoom)
        breathe = 1 + 0.12 * per(t, 6, n.ph)
        r = (24 + 6 * (n.hue)) * max(zoom, 0.55) * breathe * pop
        sprites.append((r, n.hue, sp[0], sp[1], 0.85 * a))
        if n.birth is not None and age < 1.3:
            # ripple ring
            ru = age / 1.3
            rr = (20 + 150 * smoother(ru)) * max(zoom, 0.55)
            val = (1 - ru) ** 1.5 * 0.9
            md.ellipse([(sp[0] - rr) * 2, (sp[1] - rr) * 2, (sp[0] + rr) * 2, (sp[1] + rr) * 2],
                       outline=int(val * 255), width=max(2, int(line_w * 1.2)))
            if age < 0.35:
                sprites.append((60 * max(zoom, 0.55), 0.05, sp[0], sp[1], 0.9 * (1 - age / 0.35)))

    # pill dots
    pill_draw = []
    for n in PILL_NODES:
        a, pop, age = life_alpha(n, t)
        if a <= 0.004:
            continue
        sp = to_screen(node_pos(n, t), cam)
        hp = hubs_scr[n.hub]
        grow = smoother(age / 0.45) if n.birth is not None else 1.0
        q = (hp[0] + (sp[0] - hp[0]) * grow, hp[1] + (sp[1] - hp[1]) * grow)
        line(hp, q, 0.62 * a)
        if n.birth is not None and age > (n.death - n.birth) - ABSORB:
            a *= 1 - smoother((age - ((n.death - n.birth) - ABSORB)) / 0.5)
        if grow >= 1:
            pulses(sp, hp, n.pulse_period, n.pulse_ph, 0.85 * a, 10 + 6 * zoom, 2)
        breathe = 1 + 0.10 * per(t, 5, n.ph)
        sprites.append((34 * max(zoom, 0.55) * breathe * pop, 0.05, sp[0], sp[1], a))
        if n.birth is not None and age < 1.4:
            ru = age / 1.4
            for off in (0.0, 0.18):
                uu = ru - off
                if uu <= 0:
                    continue
                rr = (24 + 210 * smoother(uu)) * max(zoom, 0.55)
                val = (1 - uu) ** 1.5
                md.ellipse([(sp[0] - rr) * 2, (sp[1] - rr) * 2, (sp[0] + rr) * 2, (sp[1] + rr) * 2],
                           outline=int(val * 255), width=max(2, int(line_w * 1.3)))
            if age < 0.4:
                sprites.append((90 * max(zoom, 0.55), 0.05, sp[0], sp[1], 1.0 * (1 - age / 0.4)))
        pill_draw.append((n, sp, a, pop))

    # hubs
    for k, h in enumerate(HUB_ORDER):
        hp = hubs_scr[h]
        breathe = 1 + 0.08 * per(t, 4, k)
        sprites.append((150 * max(zoom, 0.5) * breathe, 0.15, hp[0], hp[1], 0.55))
        sprites.append((60 * max(zoom, 0.5) * breathe, 0.0, hp[0], hp[1], 1.0))
        # slow halo ring that breathes outward
        hu = (t / 4.0 + k * 0.25) % 1.0
        rr = (70 + 120 * hu) * max(zoom, 0.5)
        md.ellipse([(hp[0] - rr) * 2, (hp[1] - rr) * 2, (hp[0] + rr) * 2, (hp[1] + rr) * 2],
                   outline=int(255 * 0.35 * math.sin(math.pi * hu)), width=max(2, int(line_w)))

    small = mask.resize((W, H), Image.Resampling.BOX)
    m = np.asarray(small, dtype=np.float32) / 255.0
    canvas += m[..., None] * np.array([120, 214, 214], np.float32) * 0.62
    for r, hue, x, y, g in sprites:
        if -200 < x < W + 200 and -200 < y < H + 200:
            blit_add(canvas, glow_sprite(r, hue), x, y, g)

    ta = title_alpha(t)
    oa = max(ta, stats_alpha(t), pillars_alpha(t))
    ca = cta_alpha(t)
    if oa > 0.001 or ca > 0.001:
        ys = np.arange(H, dtype=np.float32)
        band = np.exp(-((ys - 865) ** 2) / (170 ** 2)) * 0.66 * oa
        band2 = np.clip((ys - 380) / 220, 0, 1) * 0.72 * ca
        canvas *= (1.0 - np.maximum(band, band2))[:, None, None]

    np.clip(canvas, 0, 255, out=canvas)
    im = Image.fromarray(canvas.astype(np.uint8), "RGB").convert("RGBA")

    # entity pills (fade out as the camera pulls wide)
    ent_vis = smoother((zoom - 0.84) / 0.12)
    for n, sp, a, pop in pill_draw:
        img = PILL_IMG[n.text]
        f = min(1.0, 0.75 + 0.25 * zoom) * pop
        w, h = img.size[0] * f / 2, img.size[1] * f / 2
        c = pill_center(sp, n.side, w, h, 30 * max(zoom, 0.6))
        ef = edge_fade(c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)
        paste_scaled(im, img, c[0], c[1], f, a * ent_vis * hub_focus(n.hub, t, cam) * ef * stop_gate(n.hub, t))

    # hub labels always visible; shrink a little when wide, dim slightly under the title
    hf = clamp(0.56 + 0.44 * (zoom - 0.5) / 0.5, 0.56, 1.0)
    ov = max(title_alpha(t), stats_alpha(t), pillars_alpha(t), cta_alpha(t))
    for h in HUB_ORDER:
        img = HUB_IMG[h]
        hp = hubs_scr[h]
        gap = 30 * max(zoom, 0.5) + 50 * max(zoom, 0.5)
        hh = img.size[1] * hf / 2
        cy = hp[1] + gap + hh / 2
        low = smoother((cy - 380) / 80)
        paste_scaled(im, img, hp[0], cy, hf, (1.0 - 0.2 * ov) * (1.0 - cta_alpha(t) * low))

    if ta > 0.001:
        rise = 14 * (1 - smoother((t - TITLE_IN0) / 0.9))
        im.alpha_composite(_fade(TITLE, ta), (int((W - TITLE.size[0]) / 2), int(790 + rise)))
        im.alpha_composite(_fade(SUB, ta), (int((W - SUB.size[0]) / 2), int(790 + rise + TITLE.size[1] + 8)))
    draw_stats(im, t)
    draw_pillars(im, t)
    if ca > 0.001:
        rise = 16 * (1 - smoother((t - CTA_IN0) / 0.8))
        pop = 0.92 + 0.08 * ease_out_back((t - CTA_IN0) / 0.6, 1.6)
        w, h = int(CTA.size[0] * pop), int(CTA.size[1] * pop)
        img = CTA.resize((w, h), Image.Resampling.LANCZOS) if pop != 1 else CTA
        im.alpha_composite(_fade(img, ca), (int((W - w) / 2), int(CTA_Y - h / 2 + rise)))
        # QR: fixed integer position, never scaled, no glow; only its opacity follows the CTA
        im.alpha_composite(_fade(QR_IMG, ca), (QR_X, QR_Y))
    return im.convert("RGB")


def cta_alpha(t):
    if t < CTA_IN0 or t >= CTA_OUT1:
        return 0.0
    if t < CTA_IN1:
        return smoother((t - CTA_IN0) / (CTA_IN1 - CTA_IN0))
    if t < CTA_OUT0:
        return 1.0
    return 1.0 - smoother((t - CTA_OUT0) / (CTA_OUT1 - CTA_OUT0))


def render_cta():
    """'Get your ID' in white, a cyan arrow, and the URL in a bright pill for maximum contrast."""
    f1 = load_font(92, 640)
    fu = load_font(92, 700)
    a = "Get your ID"
    arrow = "→"
    url = "app.entity.id"
    wa = f1.getlength(a)
    warr = f1.getlength(arrow)
    wu = fu.getlength(url)
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
    d.text((4, base + 3), a, font=f1, fill=(0, 0, 0, 160))
    d.text((4, base), a, font=f1, fill=(246, 252, 253, 255))
    xa = 4 + wa + gap
    d.text((xa, base), arrow, font=f1, fill=(110, 230, 222, 255))
    xp = int(xa + warr + gap)
    ss = 2
    pill = Image.new("RGBA", (pill_w * ss, pill_h * ss), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle([0, 0, pill_w * ss - 1, pill_h * ss - 1], radius=pill_h * ss // 2,
                         fill=(120, 236, 228, 255))
    pill = pill.resize((pill_w, pill_h), Image.Resampling.LANCZOS)
    im.alpha_composite(pill, (xp, (hgt - pill_h) // 2))
    d.text((xp + pad_x, base), url, font=fu, fill=(4, 16, 30, 255))
    return im


CTA = None
CTA_Y = 560
QR_IMG = None
QR_X = QR_Y = 0


def render_qr():
    import qrcode
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=4, box_size=1)
    q.add_data(QR_URL)
    q.make(fit=True)
    m = q.get_matrix()  # includes the 4-module quiet zone
    n = len(m)
    mod = 340 // n
    size = n * mod
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(mod * 1.6), fill=(246, 250, 252, 255))
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                d.rectangle([x * mod, y * mod, (x + 1) * mod - 1, (y + 1) * mod - 1], fill=(4, 14, 28, 255))
    return img, q.version, n, mod


STATS = [(2935661, "registered entities"), (311, "active jurisdictions"), (226467, "verifiable entities")]
STAT_CAPS = []
NUM_FONT = None


def stats_alpha(t):
    if t < STATS_IN0 or t >= STATS_OUT1:
        return 0.0
    a = smoother((t - STATS_IN0) / 0.45)
    if t > STATS_OUT0:
        a *= 1 - smoother((t - STATS_OUT0) / (STATS_OUT1 - STATS_OUT0))
    return a


def pillars_alpha(t):
    if t < PILLARS_IN0 or t >= PILLARS_OUT1:
        return 0.0
    a = smoother((t - PILLARS_IN0) / 0.3)
    if t > PILLARS_OUT0:
        a *= 1 - smoother((t - PILLARS_OUT0) / (PILLARS_OUT1 - PILLARS_OUT0))
    return a


def draw_stats(im, t):
    a = stats_alpha(t)
    if a <= 0.001:
        return
    u = smoother((t - STATS_IN0 - 0.1) / (STATS_COUNT1 - STATS_IN0 - 0.1))
    col_w = 600
    x0 = (W - col_w * 3) / 2
    for k, (val, cap) in enumerate(STATS):
        uk = smoother(clamp((u - 0.06 * k) / (1 - 0.12), 0, 1))
        v = int(round(val * (1 - (1 - uk) ** 3)))
        if uk >= 1:
            v = val
        s = f"{v:,}"
        img = Image.new("RGBA", (col_w, 130), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        tw = d.textlength(s, font=NUM_FONT, features=["tnum"])
        d.text(((col_w - tw) / 2, 4), s, font=NUM_FONT, fill=(246, 252, 253, 255), features=["tnum"])
        cx = x0 + col_w * k
        rise = 18 * (1 - smoother((t - STATS_IN0 - 0.12 * k) / 0.6))
        im.alpha_composite(_fade(img, a), (int(cx), int(762 + rise)))
        capi = STAT_CAPS[k]
        im.alpha_composite(_fade(capi, a), (int(cx + (col_w - capi.size[0]) / 2), int(890 + rise)))


PILLAR_IMGS = []
DOT_IMG = None


def draw_pillars(im, t):
    a = pillars_alpha(t)
    if a <= 0.001:
        return
    gap = 34
    widths = [p.size[0] for p in PILLAR_IMGS]
    total = sum(widths) + 2 * (DOT_IMG.size[0] + 2 * gap)
    x = (W - total) / 2
    y_mid = 865
    for k, img in enumerate(PILLAR_IMGS):
        age = t - PILLARS_IN0 - 0.35 * k
        if age > 0:
            pop = ease_out_back(age / 0.5, 1.8)
            f = 0.6 + 0.4 * pop
            w, h = int(img.size[0] * f), int(img.size[1] * f)
            sc = img.resize((max(2, w), max(2, h)), Image.Resampling.LANCZOS)
            al = a * smoother(age / 0.25)
            cxk = x + img.size[0] / 2
            im.alpha_composite(_fade(sc, al), (int(cxk - w / 2), int(y_mid - h / 2)))
            if age < 0.6:
                pass
        x += img.size[0]
        if k < 2:
            age_d = t - PILLARS_IN0 - 0.35 * k - 0.2
            if age_d > 0:
                im.alpha_composite(_fade(DOT_IMG, a * smoother(age_d / 0.3)),
                                   (int(x + gap), int(y_mid - DOT_IMG.size[1] / 2)))
            x += DOT_IMG.size[0] + 2 * gap


def _fade(img, a):
    if a >= 0.999:
        return img
    arr = np.array(img, dtype=np.float32)
    arr[..., 3] *= a
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def init():
    global BG, TITLE, SUB
    BG = make_background()
    for n in PILL_NODES:
        PILL_IMG[n.text] = render_pill(n.text, n.size)
    for h in HUB_ORDER:
        HUB_IMG[h] = render_pill(HUBS[h]["label"], 60, hub=True)
    global NUM_FONT, DOT_IMG
    TITLE = render_text("Every entity. One verifiable identity.", 92, 640, (244, 249, 252, 255), 0.3)
    SUB = render_text("Entity.ID", 60, 680, (120, 232, 224, 255), 1.0)
    global CTA, QR_IMG, QR_X, QR_Y
    CTA = render_cta()
    QR_IMG, ver, n, mod = render_qr()
    QR_X = (W - QR_IMG.size[0]) // 2
    QR_Y = CTA_Y + CTA.size[1] // 2 + 28
    if os.environ.get("QR_INFO"):
        print(f"QR version {ver}, {n} modules incl. quiet zone, {mod}px/module, {QR_IMG.size[0]}px, at ({QR_X},{QR_Y})")
    NUM_FONT = load_font(104, 680)
    STAT_CAPS.clear()
    for _, cap in STATS:
        STAT_CAPS.append(render_text(cap, 40, 520, (126, 220, 214, 255), 1.0))
    PILLAR_IMGS.clear()
    for w in ("Unified", "Verifiable", "Interoperable"):
        PILLAR_IMGS.append(render_text(w, 100, 640, (244, 249, 252, 255), 0.3))
    DOT_IMG = render_text("·", 100, 640, (110, 226, 220, 255))


def frame_bytes(i):
    return render_frame(i).tobytes()


PROBLEMS = assign_deaths()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    init()
    print("death-window problems:", PROBLEMS)
    for n in SATS + PILL_NODES:
        if n.birth is not None:
            print(f"  {n.hub} {getattr(n, 'text', 'sat'):10s} born {n.birth:5.1f} gone {wrap(n.death):5.1f}")
    if mode == "preview":
        os.makedirs("/workspace/booth-preview/v2", exist_ok=True)
        os.environ["QR_INFO"] = "1"
        init()
        ts = [float(x) for x in sys.argv[2:]] or [0, 2.5, 5.6, 8.5, 14.5, 19.8, 21.8, 24.0, 25.5, 28.0, 31.5, 35.5, 38.5, 39.97]
        for tt in ts:
            render_frame(int(round(tt * FPS))).save(f"/workspace/booth-preview/v2/t{tt:05.2f}.png")
        a = np.asarray(render_frame(0)).astype(int)
        b = np.asarray(render_frame(NFRAMES)).astype(int)  # t = 30
        print("raw t=0 vs t=T max diff", int(np.abs(a - b).max()))
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-b:v", "10M", "-maxrate", "12M", "-bufsize", "20M", "-preset", "medium", "-g", "60",
           "-movflags", "+faststart", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(7, initializer=init) as pool:
        for k, buf in enumerate(pool.imap(frame_bytes, range(NFRAMES), chunksize=4)):
            proc.stdin.write(buf)
            if k % 90 == 0:
                print(f"frame {k}/{NFRAMES}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print("encode done", OUT)


if __name__ == "__main__":
    main()
