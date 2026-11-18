"""The 16 scenes. Each scene function takes a context `c` and returns a float
RGB frame. `c.t` is the time since the scene started, `c.D` its length,
`c.gt` the global time and `c.lt(name)` an event's time relative to the scene."""
import re

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

import assets as A
import gfx as G
from config import FPS, H, W

TAU = 2 * np.pi
CX = 540
YELLOW = (255, 214, 64)
WHITE = (255, 255, 255)
CYAN_GLOW = (0.25, 0.55, 1.0)
GOLD_GLOW = (1.0, 0.55, 0.12)


# ======================================================================= events
def _norm(s):
    return re.sub(r"[^a-z0-9.']", "", s.lower().replace("’", "'"))


def word(tl, line, text, nth=0, key="t0"):
    ws = [w for w in tl["lines"][line - 1]["words"] if _norm(w["text"]) == _norm(text)]
    return ws[nth][key]


def events(tl):
    S = {s["index"]: s for s in tl["scenes"]}
    Ln = {l["index"]: l for l in tl["lines"]}
    e = {}
    e["s1_actually"] = word(tl, 1, "actually")
    e["s2_lap0"] = word(tl, 2, "it")
    e["s2_lap1"] = word(tl, 2, "second", key="t1")
    e["s3_beam0"] = S[3]["start"] + 0.30
    e["s3_beam1"] = min(e["s3_beam0"] + 1.3, S[3]["end"] - 0.35)
    e["s4_beam0"] = S[4]["start"] + 0.12
    e["s4_beam1"] = word(tl, 4, "minutes", key="t1") - 0.05
    e["s5_day"] = word(tl, 5, "light")
    e["s5_beeps"] = [S[5]["start"] + 0.45 + k * 0.95 for k in range(5)]
    e["s6_name"] = S[6]["start"] + 0.75
    e["s6_dist"] = word(tl, 6, "four")
    e["s7_ruler"] = word(tl, 7, "hundred") - 0.2
    e["s8_dist"] = word(tl, 8, "two")
    e["s9_lan"] = word(tl, 9, "laniakea")
    e["s9_count"] = word(tl, 9, "hundred")
    e["s10_label"] = word(tl, 10, "giant")
    e["s11_zoom0"] = word(tl, 11, "and") - 0.05
    e["s11_zoom1"] = word(tl, 11, "thousands") + 0.12
    e["s12_line"] = Ln[12]["start"]
    e["s12_num"] = word(tl, 12, "13.8")
    e["s13_reveal"] = word(tl, 13, "93") - 0.04
    e["s14_light"] = word(tl, 14, "light")
    e["s15_q1"] = word(tl, 15, "nobody")
    e["s15_q2"] = word(tl, 15, "infinite")
    e["s16_dot"] = word(tl, 16, "you're")
    e["s16_card"] = word(tl, 16, "follow")
    e["riser0"] = S[12]["start"] - 1.6
    e["riser1"] = S[12]["start"]
    e["silence0"] = S[12]["start"]
    e["silence1"] = Ln[12]["start"]
    e["transitions"] = [(s["index"], s["start"], s["transition"]["kind"], s["transition"]["dur"])
                        for s in tl["scenes"] if s["transition"]]
    return e


# ======================================================================= camera
SPEED = {1: 1.7, 2: 0.25, 3: 0.3, 4: 0.35, 5: -0.3, 6: -1.0, 7: -0.6, 8: -1.0, 9: -0.6,
         10: -0.5, 11: 0.12, 12: 0.4, 13: 0.5, 14: 0.15, 15: -0.12, 16: 0.2}


class Camera:
    def __init__(self, tl, ev):
        n = int(70 * FPS)
        t = (np.arange(n) - 5 * FPS) / FPS  # covers -5 s .. 65 s
        sp = np.zeros(n)
        for s in tl["scenes"]:
            m = (t >= s["start"]) & (t < s["end"])
            sp[m] = SPEED[s["index"]]
        sp[t >= tl["scenes"][-1]["end"]] = SPEED[16]
        m = (t >= tl["scenes"][15]["start"]) & (t < ev["s16_dot"])
        sp[m] = 3.2
        sp[t < 0] = SPEED[1]
        sp = ndimage.gaussian_filter1d(sp, 5)
        self.t = t
        self.z = np.cumsum(sp) / FPS
        self.z -= np.interp(0, t, self.z)

    def camz(self, t):
        return float(np.interp(t, self.t, self.z))

    @staticmethod
    def camx(t):
        return 0.05 * t + 0.03 * np.sin(t * 0.21)

    @staticmethod
    def camy(t):
        return 0.025 * np.sin(t * 0.17) - 0.01 * t


# ======================================================================= helpers
def pop_scale(dt, d=0.24, amt=0.4):
    if dt >= d:
        return 1.0
    p = max(dt, 0) / d
    c1 = 1.70158
    e = 1 + (c1 + 1) * (p - 1) ** 3 + c1 * (p - 1) ** 2
    return (1 - amt) + amt * e


def label(img, text, y, t=None, t_on=None, t_off=None, size=64, color=WHITE, glow=CYAN_GLOW,
          x=CX, weight="x", glow_k=0.7, tracking=0, alpha=1.0, max_w=760, pop=0.4, scale=1.0):
    a, s = alpha, scale
    if t_on is not None:
        dt = t - t_on
        if dt < 0:
            return
        a *= min(1.0, dt / 0.1)
        s *= pop_scale(dt, amt=pop)
    if t_off is not None and t is not None:
        if t > t_off + 0.15:
            return
        if t > t_off:
            a *= 1 - (t - t_off) / 0.15
    im = G.text_rgba(text, size, fill=color, stroke=max(3, size // 13), stroke_fill=(0, 0, 0),
                     max_w=max_w, weight=weight, tracking=tracking)
    w = im.width * s
    x = min(max(x, 60 + w / 2), 925 - w / 2) if w < 865 else 492
    G.glow_text(img, im, x, y, glow, k=glow_k, radius=18, alpha=a, scale=s)


def fixed_text(img, text, ref, y, size, color, glow, k=0.8):
    """Left-anchored text (for counters) so digits don't make it jump around."""
    ref_im = G.text_rgba(ref, size, fill=color, stroke=max(3, size // 13), max_w=760)
    im = G.text_rgba(text, size, fill=color, stroke=max(3, size // 13), max_w=760)
    if im.height != ref_im.height:
        im = im.resize((int(im.width * ref_im.height / im.height), ref_im.height))
    x_left = CX - ref_im.width / 2
    G.glow_text(img, im, x_left + im.width / 2, y, glow, k=k, radius=18)


def base(c, stars=1.0, streak=1.0, neb=0.2, neb_zoom=1.0, **kw):
    img = G.frame()
    A.draw_nebula(img, c.gt, neb, zoom=neb_zoom)
    c.stars.render(img, c.gt, stars, streak, **kw)
    return img


def rgb_layer():
    im = Image.new("RGB", (W, H))
    return im, ImageDraw.Draw(im)


def add_rgb_layer(img, im, k=1.0, glow=0.0, glow_k=1.2):
    a = np.asarray(im, np.float32) / 255.0
    img += k * a
    if glow:
        s = 4
        sm = a.reshape(H // s, s, W // s, s, 3).mean(axis=(1, 3))
        g = ndimage.gaussian_filter(sm, (glow / s, glow / s, 0))
        img += glow_k * G.upsample(g, s)


def beam(img, p0, p1, color=(0.7, 0.9, 1.0), width=5, head=True, k=1.0):
    im, d = rgb_layer()
    col = tuple(int(255 * min(1, v)) for v in color)
    d.line([tuple(p0), tuple(p1)], fill=col, width=width)
    add_rgb_layer(img, im, k * 1.2, glow=10, glow_k=2.0 * k)
    if head:
        G.add_glow(img, p1[0], p1[1], 7, (0.85, 0.95, 1.0), 2.2 * k, halo=0.35 * k, halo_r=20, extent=120)


def dashed(d, p0, p1, fill, width=2, dash=14, gap=10):
    p0, p1 = np.array(p0, float), np.array(p1, float)
    L = np.linalg.norm(p1 - p0)
    if L < 1:
        return
    u = (p1 - p0) / L
    s = 0.0
    while s < L:
        a = p0 + u * s
        b = p0 + u * min(L, s + dash)
        d.line([tuple(a), tuple(b)], fill=fill, width=width)
        s += dash + gap


def star_point(img, x, y, color, k=1.0, r=4, halo=0.4, spikes=0.0):
    G.add_glow(img, x, y, r, color, 2.0 * k, halo=halo * k, halo_r=r * 4, extent=r * 30)
    if spikes:
        L = int(r * 18)
        x0, x1, y0, y1 = G.box(x, y, L)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = np.abs(xx - x), np.abs(yy - y)
        sp = np.exp(-dy / 1.3) * np.exp(-dx / (L * 0.3)) + np.exp(-dx / 1.3) * np.exp(-dy / (L * 0.3))
        img[y0:y1, x0:x1] += (sp * spikes * k)[..., None] * np.asarray(color, np.float32)


def glitch(img, amount, seed):
    """RGB split + horizontal slice displacement. amount 0..1."""
    if amount <= 0.01:
        return img
    rng = np.random.default_rng(seed)
    out = img.copy()
    off = int(4 + 34 * amount)
    out[..., 0] = np.roll(img[..., 0], off, axis=1)
    out[..., 2] = np.roll(img[..., 2], -off, axis=1)
    nsl = int(3 + 12 * amount)
    for _ in range(nsl):
        y0 = rng.integers(0, H - 20)
        h = rng.integers(8, int(30 + 140 * amount))
        dx = int(rng.normal(0, 80 * amount))
        out[y0:y0 + h] = np.roll(out[y0:y0 + h], dx, axis=1)
    if amount > 0.4:
        for _ in range(int(6 * amount)):
            y0, x0 = rng.integers(0, H - 60), rng.integers(0, W - 200)
            out[y0:y0 + rng.integers(6, 40), x0:x0 + rng.integers(40, 300)] *= rng.uniform(0.0, 2.2)
    return out


def zoom_frame(img, s, cx=W / 2, cy=H / 2):
    """Scale the frame by s about (cx, cy) (s>1 zooms in)."""
    if abs(s - 1) < 1e-4:
        return img
    ext = (cx - cx / s, cy - cy / s, cx + (W - cx) / s, cy + (H - cy) / s)
    out = np.empty_like(img)
    for ch in range(3):
        im = Image.fromarray(img[..., ch])
        out[..., ch] = np.asarray(im.transform((W, H), Image.EXTENT, ext, Image.BILINEAR))
    return out


# ======================================================================= scenes
def s1(c):
    t = c.t
    img = base(c, stars=1.0, streak=3.5, neb=0.25)
    tact = c.lt("s1_actually")
    zoom = 1 + 0.10 * t / c.D
    pulse = 1 + 0.035 * np.sin(TAU * 1.6 * t)
    punch = 1 + 0.10 * np.exp(-max(0.0, t - tact) * 7) * (t >= tact)
    s = zoom * pulse * pop_scale(t, 0.3, 0.5) * punch
    a = min(1.0, t / 0.08 + 0.2)
    im1 = G.text_rgba("HOW BIG IS THE", 92, fill=WHITE, stroke=6, max_w=640)
    im2 = G.text_rgba("UNIVERSE?", 150, fill=YELLOW, stroke=8, max_w=660)
    G.glow_text(img, im1, CX, 700 - (s - 1) * 70, CYAN_GLOW, k=0.9, radius=22, alpha=a, scale=s)
    G.glow_text(img, im2, CX, 840, GOLD_GLOW, k=1.1, radius=26, alpha=a, scale=s)
    return img


def _orbit(theta, ex, ey, rx=300, ry=88, tilt=-0.32):
    px, py = rx * np.cos(theta), ry * np.sin(theta)
    ct, st = np.cos(tilt), np.sin(tilt)
    return ex + px * ct - py * st, ey + px * st + py * ct, np.sin(theta)


def s2(c):
    t = c.t
    img = base(c, stars=0.9, streak=1.0, neb=0.15)
    ex, ey, R = 540, 860, 200
    l0, l1 = c.lt("s2_lap0"), c.lt("s2_lap1")
    slow = 1.4
    if t < l0:
        th, trail = slow * t, 1.1
    elif t < l1:
        p = (t - l0) / (l1 - l0)
        th, trail = slow * l0 + 7 * TAU * p, 3.2
    else:
        th, trail = slow * l0 + 7 * TAU + slow * (t - l1), 1.1
    A.draw_planet(img, ex, ey, R, A.earth_tex(), rot=0.3 * c.gt, atmo=(0.3, 0.55, 1.0), spec=0.25)
    s = np.linspace(0, 1, 260)
    thetas = th - trail * s
    x, y, z = _orbit(thetas, ex, ey)
    hidden = (z < 0) & (np.hypot(x - ex, y - ey) < R + 2)
    w = (1 - s) ** 1.6 * (~hidden)
    col = np.array([0.75, 0.92, 1.0], np.float32)
    G.splat(img, x, y, (w * 0.9)[:, None] * col, spread=0.7)
    buf = G.splat_buffer(x, y, (w * 1.4)[:, None] * col, 4)
    img += G.upsample(ndimage.gaussian_filter(buf, (2.2, 2.2, 0)), 4) * 2.2
    if not hidden[0]:
        G.add_glow(img, x[0], y[0], 7, (0.9, 0.97, 1.0), 2.5, halo=0.4, halo_r=22, extent=150)
    # labels
    if t < l0:
        label(img, "LIGHT SPEED", 420, t, 0.15, size=78, tracking=4)
        label(img, "299,792 km every second", 505, t, 0.3, size=42, color=(190, 215, 255), weight="b")
    elif t < l1:
        p = (t - l0) / (l1 - l0)
        fixed_text(img, f"{p:.2f} s", "0.00 s", 420, 110, YELLOW, GOLD_GLOW)
        label(img, f"LAP {min(7, int(p * 7) + 1)} / 7", 520, size=46, weight="b")
    else:
        label(img, "1 SECOND", 420, t, l1, size=110, color=YELLOW, glow=GOLD_GLOW, pop=0.5)
        label(img, "7 laps around Earth", 520, t, l1 + 0.1, size=46, weight="b")
    return img


def s3(c):
    t = c.t
    img = base(c, stars=0.9, neb=0.15)
    ox = 10 * np.sin(c.gt * 0.9)
    E = np.array([235 + ox, 1010.0]); Er = 120
    M = np.array([815 + ox, 640.0]); Mr = 82
    A.draw_planet(img, E[0], E[1], Er, A.earth_tex(), rot=0.3 * c.gt, atmo=(0.3, 0.55, 1.0), spec=0.2)
    A.draw_planet(img, M[0], M[1], Mr, A.moon_tex(), rot=0.05 * c.gt, light=(-0.7, 0.2, 0.6), ambient=0.04)
    b0, b1 = c.lt("s3_beam0"), c.lt("s3_beam1")
    u = (M - E) / np.linalg.norm(M - E)
    p0, p1 = E + u * (Er + 4), M - u * (Mr + 2)
    if t > b0:
        p = min(1.0, (t - b0) / (b1 - b0))
        beam(img, p0, p0 + (p1 - p0) * p, head=p < 1)
        fixed_text(img, f"{1.3 * p:.1f} s", "0.0 s", 420, 100, WHITE, CYAN_GLOW) if p < 1 else None
        if p >= 1:
            dt = t - b1
            G.add_glow(img, M[0], M[1], Mr * 1.1, (0.7, 0.85, 1.0), 0.9 * np.exp(-dt * 3), extent=Mr * 3)
            label(img, "1.3 light-seconds", 420, t, b1, size=80, color=YELLOW, glow=GOLD_GLOW)
            label(img, "384,400 km to the Moon", 505, t, b1 + 0.12, size=42, weight="b")
    return img


def s4(c):
    t = c.t
    img = base(c, stars=0.7, neb=0.12)
    S = np.array([650.0, 820.0]); Sr = 215
    E = np.array([150.0, 1100.0]); Er = 26
    A.draw_sun(img, S[0], S[1], Sr, c.gt)
    A.draw_planet(img, E[0], E[1], Er, A.earth_tex(), rot=0.3 * c.gt, atmo=(0.3, 0.55, 1.0),
                  light=(0.8, -0.5, 0.4))
    b0, b1 = c.lt("s4_beam0"), c.lt("s4_beam1")
    u = (S - E) / np.linalg.norm(S - E)
    p0, p1 = E + u * (Er + 3), S - u * (Sr - 4)
    p = float(np.clip((t - b0) / (b1 - b0), 0, 1))
    if t > b0:
        beam(img, p0, p0 + (p1 - p0) * p, head=p < 1)
    secs = int(round(500 * p))
    col = YELLOW if p >= 1 else WHITE
    fixed_text(img, f"{secs // 60}:{secs % 60:02d}", "8:20", 410, 130, col, GOLD_GLOW, k=1.0)
    label(img, "minutes at light speed", 510, t, 0.1, size=42, weight="b")
    return img


def s5(c):
    t = c.t
    img = base(c, stars=1.0, neb=0.12)
    sun = (185.0, 560.0)
    star_point(img, *sun, (1.0, 0.9, 0.7), k=1.3, r=4, halo=0.5, spikes=0.9)
    px = 590 - 14 * t + 6 * np.sin(t * 0.7)
    py = 900 - 6 * t
    ang = 7 * np.sin(t * 0.45)
    dish = (px - 40, py - 30)
    # faint dashed link back toward the Sun / Earth
    im, d = rgb_layer()
    dashed(d, sun, dish, (60, 90, 140), width=2)
    # radio waves leaving the dish toward the Sun
    dirv = np.array(sun) - np.array(dish)
    base_ang = np.degrees(np.arctan2(dirv[1], dirv[0]))
    for e in c.ev["s5_beeps"]:
        ph = (c.gt - e) / 1.4
        if 0 <= ph < 1:
            r = 30 + 330 * ph
            a = int(200 * (1 - ph) ** 1.5)
            d.arc([dish[0] - r, dish[1] - r, dish[0] + r, dish[1] + r], base_ang - 28, base_ang + 28,
                  fill=(a // 3, int(a * 0.8), a), width=4)
    add_rgb_layer(img, im, 1.0, glow=8, glow_k=1.5)
    spr = A.probe_sprite().rotate(ang, resample=Image.BICUBIC, expand=True)
    G.blit(img, spr, px, py, 1.0)
    # sunlight glint on the dish
    G.add_glow(img, dish[0] - 10, dish[1] - 12, 18, (1.0, 0.95, 0.85), 0.18, extent=60)
    tday = c.lt("s5_day")
    if t < tday:
        label(img, "VOYAGER 1", 420, t, 0.12, size=88, tracking=6)
        label(img, "launched 1977 · 49 years flying", 505, t, 0.3, size=40, weight="b",
              color=(190, 215, 255))
    else:
        label(img, "~1 light-day", 420, t, tday, size=96, color=YELLOW, glow=GOLD_GLOW, pop=0.5)
        label(img, "≈ 25 billion km from the Sun", 505, t, tday + 0.12, size=40, weight="b",
              color=(190, 215, 255))
    return img


PLANETS = [(0.39, (0.7, 0.65, 0.6)), (0.72, (1.0, 0.85, 0.55)), (1.0, (0.4, 0.65, 1.0)),
           (1.52, (1.0, 0.45, 0.3)), (5.2, (1.0, 0.8, 0.6)), (9.5, (1.0, 0.9, 0.65)),
           (19.2, (0.6, 0.9, 1.0)), (30.0, (0.4, 0.55, 1.0))]


def s6(c):
    t = c.t
    img = base(c, stars=1.0, streak=1.5, neb=0.15)
    q = G.ease_in_out(t / 1.9)
    k = 260 * (8 / 260) ** q
    cx = G.lerp(540, 250, q)
    cy = G.lerp(860, 1040, q)
    im, d = rgb_layer()
    for i, (a_, col) in enumerate(PLANETS):
        rx = k * np.sqrt(a_)
        ry = rx * 0.36
        al = float(G.smoothstep(6, 30, rx))
        if al <= 0.02:
            continue
        oc = tuple(int(v * al) for v in (60, 95, 150))
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=oc, width=2)
        th = c.gt * (1.5 / a_ ** 0.8) + i * 1.3
        x, y = cx + rx * np.cos(th), cy + ry * np.sin(th)
        rp = max(1.5, min(9, rx * 0.025 + 2))
        d.ellipse([x - rp, y - rp, x + rp, y + rp], fill=tuple(int(255 * v * al) for v in col))
    add_rgb_layer(img, im, 1.0, glow=6, glow_k=0.8)
    G.add_glow(img, cx, cy, max(3.0, 0.06 * k), (1.0, 0.85, 0.5), 2.2, halo=0.35, halo_r=max(10, 0.2 * k),
               extent=max(80, k * 0.9))
    P = (720.0, 630.0)
    pa = float(G.smoothstep(0.35, 0.8, q))
    if pa > 0:
        star_point(img, *P, (1.0, 0.32, 0.18), k=pa * (1.4 + 0.1 * np.sin(c.gt * 9)), r=7, halo=0.8, spikes=0.6)
    if q > 0.8:
        im2, d2 = rgb_layer()
        u = np.array(P) - np.array([cx, cy])
        u /= np.linalg.norm(u)
        dashed(d2, np.array([cx, cy]) + u * 30, np.array(P) - u * 30, (255, 220, 120), width=3)
        add_rgb_layer(img, im2, float(G.smoothstep(0.8, 1.0, q)) * 0.8, glow=6)
        label(img, "Sun", cy + 60, t, None, size=40, weight="b", x=cx, alpha=float(G.smoothstep(0.85, 1, q)))
    label(img, "Proxima Centauri", 420, t, c.lt("s6_name"), size=72, glow=(1.0, 0.35, 0.2))
    label(img, "4.2 light-years", 510, t, c.lt("s6_dist"), size=64, color=YELLOW, glow=GOLD_GLOW)
    return img


MW = dict(seed=1)
AND = dict(seed=2, b=0.22, bulge=0.24, arm_sigma=0.28, blue=(0.75, 0.82, 1.0))


def s7(c):
    t = c.t
    img = base(c, stars=0.7, neb=0.18)
    R = 405 * (1.08 - 0.08 * t / c.D)
    gx, gy = 530, 880
    A.draw_galaxy(img, A.galaxy_particles(**MW), gx, gy, R, 0.12 * c.gt, tilt=0.78, pa=0.15)
    tr = c.lt("s7_ruler")
    if t < tr:
        label(img, "OUR GALAXY", 420, t, 0.15, size=78, tracking=4)
    else:
        p = G.ease_out((t - tr) / 0.35)
        half = 395 * p
        y = 515
        im, d = rgb_layer()
        d.line([(gx - half, y), (gx + half, y)], fill=(235, 240, 255), width=4)
        for sgn in (-1, 1):
            d.line([(gx + sgn * half, y - 18), (gx + sgn * half, y + 18)], fill=(235, 240, 255), width=4)
        for k in range(1, 10):
            xk = gx - 395 + 79 * k
            if abs(xk - gx) <= half:
                d.line([(xk, y - 8), (xk, y + 8)], fill=(180, 190, 220), width=2)
        add_rgb_layer(img, im, 1.0, glow=6, glow_k=0.7)
        label(img, "100,000 light-years", 445, t, tr + 0.1, size=66, color=YELLOW, glow=GOLD_GLOW)
    return img


def s8(c):
    t = c.t
    img = base(c, stars=0.55, neb=0.15)
    q = G.ease_in_out(t / 2.3)
    R = 405 * (90 / 405) ** q
    gx, gy = G.lerp(530, 290, q), G.lerp(880, 1010, q)
    A.draw_galaxy(img, A.galaxy_particles(**MW), gx, gy, R, 0.12 * c.gt, tilt=0.78, pa=0.15)
    aa = float(G.smoothstep(0.3, 0.75, q))
    AX, AY = 715, 690
    if aa > 0:
        A.draw_galaxy(img, A.galaxy_particles(**AND), AX, AY, G.lerp(60, 175, q), 0.05 * c.gt + 1.0,
                      tilt=0.32, pa=-0.62, alpha=aa)
    if q > 0.75:
        im, d = rgb_layer()
        u = np.array([AX - gx, AY - gy])
        u /= np.linalg.norm(u)
        dashed(d, np.array([gx, gy]) + u * (R * 0.9), np.array([AX, AY]) - u * 120, (255, 220, 120), width=3)
        add_rgb_layer(img, im, float(G.smoothstep(0.75, 1, q)) * 0.8, glow=6)
        label(img, "Milky Way", gy + 78, t, None, size=40, weight="b", x=gx, alpha=float(G.smoothstep(0.8, 1, q)))
        label(img, "Andromeda", AY - 115, t, None, size=44, weight="b", x=AX, alpha=float(G.smoothstep(0.8, 1, q)))
    label(img, "2,500,000 light-years", 420, t, c.lt("s8_dist"), size=66, color=YELLOW, glow=GOLD_GLOW)
    return img


class _Lani:
    def __init__(self):
        rng = np.random.default_rng(51)
        ns = 11
        self.th = np.linspace(0, TAU, ns, endpoint=False) + rng.normal(0, 0.18, ns)
        self.curl = rng.uniform(0.5, 1.1, ns) * rng.choice([-1, 1], ns)
        self.wig = rng.uniform(0, TAU, ns)
        n_g, n_d = 70, 380
        def mk(n):
            s = rng.integers(0, ns, n)
            return dict(s=s, ph=rng.random(n), v=rng.uniform(0.09, 0.15, n), o=rng.normal(0, 1, n))
        self.g = mk(n_g * ns)
        self.d = mk(n_d * ns)
        pal = np.array([[1.0, 0.85, 0.6], [0.7, 0.8, 1.0], [1.0, 0.6, 0.8], [0.8, 0.95, 1.0]])
        self.gcol = pal[rng.integers(0, 4, len(self.g["s"]))] * rng.uniform(0.3, 0.8, (len(self.g["s"]), 1))

    def path(self, s, u, o, Rmax=1250):
        r = Rmax * (1 - u) ** 1.25 + 10
        th = self.th[s] + self.curl[s] * u ** 1.4 + 0.25 * np.sin(3 * u + self.wig[s])
        lat = o * 55 * (r / Rmax) ** 0.8
        x = r * np.cos(th) - lat * np.sin(th)
        y = r * np.sin(th) + lat * np.cos(th)
        return x, y, r


_LANI = None


def s9(c):
    global _LANI
    _LANI = _LANI or _Lani()
    L = _LANI
    t = c.t
    img = base(c, stars=0.45, neb=0.2)
    ax, ay = 555, 850
    z = 1.12 - 0.12 * t / c.D
    im, d = rgb_layer()
    uu = np.linspace(0, 0.97, 90)
    for s in range(len(L.th)):
        x, y, _ = L.path(np.full_like(uu, s, dtype=int), uu, np.zeros_like(uu))
        pts = list(zip(ax + x * z, ay + y * z))
        d.line(pts, fill=(45, 80, 150), width=3)
    add_rgb_layer(img, im, 0.45, glow=10, glow_k=0.9)
    for grp, wk, spread in ((L.d, 0.10, 0.0), (L.g, 0.9, 0.55)):
        u = np.mod(grp["ph"] + c.gt * grp["v"], 1.0)
        x, y, r = L.path(grp["s"], u, grp["o"])
        fade = G.smoothstep(0, 0.08, u) * G.smoothstep(0.99, 0.85, u)
        col = L.gcol if grp is L.g else np.array([[0.55, 0.65, 1.0]])
        w = (fade * wk)[:, None] * col
        X, Y = ax + x * z, ay + y * z
        G.splat(img, X, Y, w, spread)
        if grp is L.g:
            u2 = np.mod(u - 0.006, 1.0)
            x2, y2, _ = L.path(grp["s"], u2, grp["o"])
            G.splat(img, ax + x2 * z, ay + y2 * z, w * 0.4, 0.3)
            buf = G.splat_buffer(X, Y, w, 4)
            img += 1.6 * G.upsample(ndimage.gaussian_filter(buf, (1.5, 1.5, 0)), 4)
    G.add_glow(img, ax, ay, 38, (1.0, 0.8, 0.55), 0.9, halo=0.35, halo_r=110, extent=600)
    label(img, "LANIAKEA", 420, t, c.lt("s9_lan"), size=104, tracking=12, glow=(0.4, 0.6, 1.0), glow_k=1.0)
    tc = c.lt("s9_count")
    if t < tc:
        label(img, "our supercluster", 515, t, c.lt("s9_lan") + 0.15, size=44, weight="b", t_off=tc - 0.1)
    else:
        label(img, "~100,000 galaxies", 515, t, tc, size=56, color=YELLOW, glow=GOLD_GLOW)
    return img


def s10(c):
    t = c.t
    img = base(c, stars=0.3, neb=0.22)
    P, C, Lz = A.cosmic_web()
    cw = 0.32 * c.t + 0.3
    roll = 0.06 * c.t - 0.1
    zr = np.mod(P[:, 2] - cw, Lz) + 0.12
    x, y = P[:, 0] + 0.15 * np.sin(c.t * 0.5), P[:, 1]
    cr, sr = np.cos(roll), np.sin(roll)
    f = 520.0
    sx = CX + f * (x * cr - y * sr) / zr
    sy = 860 + f * (x * sr + y * cr) / zr
    fog = np.exp(-zr * 0.35) * G.smoothstep(0.12, 0.5, zr) * G.smoothstep(Lz + 0.12, Lz - 0.35, zr)
    near = G.smoothstep(1.0, 0.3, zr)
    w = C * fog[:, None].astype(np.float32)
    G.splat(img, sx, sy, w * (1.1 + 1.5 * near)[:, None].astype(np.float32), 0.35)
    buf = G.splat_buffer(sx, sy, w * (1 + 0.8 * near)[:, None].astype(np.float32), 4)
    g = ndimage.gaussian_filter(buf, (1.0, 1.0, 0)) * 0.9 + ndimage.gaussian_filter(buf, (4, 4, 0)) * 1.1
    img += G.upsample(g, 4)
    label(img, "COSMIC WEB", 420, t, c.lt("s10_label"), size=96, tracking=8, glow=(0.6, 0.3, 1.0), glow_k=1.0)
    label(img, "galaxies strung along giant filaments", 505, t, c.lt("s10_label") + 0.15, size=36,
          weight="b", color=(210, 200, 255))
    return img


_HDF = None


def s11(c):
    global _HDF
    t = c.t
    z0, z1 = c.lt("s11_zoom0"), c.lt("s11_zoom1")
    s_small, s_big = 70.0, 2250.0
    if t < z0:
        s = s_small * (1 + 0.02 * np.sin(t * 6))
    elif t < z1:
        p = G.ease_in_out((t - z0) / (z1 - z0))
        s = s_small * (s_big / s_small) ** p
    else:
        s = s_big * (1 + 0.035 * (t - z1))
    cx, cy = 540.0, 830.0
    zf = s / s_small
    prev = max(s_small, s / 1.25) / s_small if z0 <= t < z1 else zf
    img = base(c, stars=1.0, neb=0.15 * float(G.smoothstep(900, 200, s)), zoom2d=zf, zoom2d_prev=prev,
               center=(cx, cy))
    if _HDF is None:
        _HDF = A.hdf_texture()
    tex = _HDF
    T = tex.width
    x0, y0, x1, y1 = cx - s / 2, cy - s / 2, cx + s / 2, cy + s / 2
    X0, Y0, X1, Y1 = int(max(0, np.floor(x0))), int(max(0, np.floor(y0))), int(min(W, np.ceil(x1))), int(min(H, np.ceil(y1)))
    if s < 900:
        si = max(2, int(round(s)))
        sm = tex.resize((si, si), Image.BOX)
        rgb = np.asarray(sm, np.float32) / 255.0
        ox, oy = int(round(x0)), int(round(y0))
        G.over(img, rgb, np.ones(rgb.shape[:2], np.float32), ox, oy)
    else:
        u0 = (X0 - x0) / s * T; u1 = (X1 - x0) / s * T
        v0 = (Y0 - y0) / s * T; v1 = (Y1 - y0) / s * T
        part = tex.transform((X1 - X0, Y1 - Y0), Image.EXTENT, (u0, v0, u1, v1), Image.BILINEAR)
        img[Y0:Y1, X0:X1] = np.asarray(part, np.float32) / 255.0 * 1.15
    if s < 1100:
        a = float(G.smoothstep(1100, 500, s))
        im, d = rgb_layer()
        m = s / 2 + 10
        L = max(12, s * 0.28)
        col = (int(230 * a), int(235 * a), int(255 * a))
        for sx_, sy_ in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            px, py = cx + sx_ * m, cy + sy_ * m
            d.line([(px, py), (px - sx_ * L, py)], fill=col, width=3)
            d.line([(px, py), (px, py - sy_ * L)], fill=col, width=3)
        add_rgb_layer(img, im, 1.0, glow=6, glow_k=0.6)
    if t < z0:
        label(img, "empty patch of sky?", cy - 95, t, 0.5, size=44, weight="b", t_off=z0 - 0.05)
    if t > z1 - 0.15:
        rng = np.random.default_rng(int(c.gt * 3))
        r2 = np.random.default_rng(77)
        for k in range(22):
            tk = z1 - 0.1 + r2.uniform(0, 1.6)
            gx_, gy_ = r2.uniform(80, 900), r2.uniform(560, 1500)
            dt = t - tk
            if 0 <= dt < 0.45:
                kk = np.sin(np.pi * dt / 0.45)
                star_point(img, gx_, gy_, (1.0, 0.95, 0.85), k=0.7 * kk, r=2.5, halo=0.3, spikes=1.4)
        band = np.ones((H, 1, 1), np.float32)
        band[280:600, 0, 0] = 1 - 0.55 * np.sin(np.linspace(0, np.pi, 320))
        img *= band
        label(img, "Hubble Deep Field", 420, t, z1, size=74, glow=(0.5, 0.6, 1.0))
        label(img, "~3,000 galaxies in one tiny patch", 505, t, z1 + 0.15, size=40, weight="b",
              color=(255, 230, 150))
    return img


_CLOCK_R = 390


def draw_clock(img, t, cx=540, cy=840, k=0.4, speed=1.0):
    im, d = rgb_layer()
    R = _CLOCK_R
    col = (110, 160, 255)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=col, width=5)
    d.ellipse([cx - R + 22, cy - R + 22, cx + R - 22, cy + R - 22], outline=(50, 80, 150), width=2)
    for i in range(60):
        a = TAU * i / 60
        r0 = R - (46 if i % 5 == 0 else 26)
        w = 7 if i % 5 == 0 else 3
        d.line([(cx + r0 * np.sin(a), cy - r0 * np.cos(a)), (cx + (R - 8) * np.sin(a), cy - (R - 8) * np.cos(a))],
               fill=col, width=w)
    ticks = t * 4 * speed
    b = np.floor(ticks)
    snap = min(1.0, (ticks - b) / 0.18)
    snap = 1 - (1 - snap) ** 3
    am = TAU * (b + snap) / 60
    ah = am / 12 + 1.0
    for ang, L, w in ((ah, R * 0.5, 12), (am, R * 0.78, 7)):
        d.line([(cx, cy), (cx + L * np.sin(ang), cy - L * np.cos(ang))], fill=(170, 200, 255), width=w)
    sec = TAU * (t * 2.0 * speed) % TAU
    d.line([(cx - 60 * np.sin(sec), cy + 60 * np.cos(sec)), (cx + R * 0.86 * np.sin(sec), cy - R * 0.86 * np.cos(sec))],
           fill=(255, 120, 90), width=3)
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(200, 220, 255))
    add_rgb_layer(img, im, k, glow=10, glow_k=k * 1.5)


def text_1380(img, t_num, t, alpha=1.0, scale_y=1.0):
    if t < t_num:
        return
    v = 13.8 * G.ease_out((t - t_num) / 0.55)
    im1 = G.text_rgba(f"{v:.1f} BILLION", 120, fill=YELLOW, stroke=8, max_w=760)
    im2 = G.text_rgba("YEARS OLD", 112, fill=WHITE, stroke=8, max_w=760)
    s = pop_scale(t - t_num, 0.25, 0.35)
    for im, y, gl in ((im1, 770, GOLD_GLOW), (im2, 905, CYAN_GLOW)):
        if scale_y != 1.0:
            im = im.resize((im.width, max(1, int(im.height * scale_y))), Image.BICUBIC)
        G.glow_text(img, im, CX, y, gl, k=1.0, radius=22, alpha=alpha, scale=s)


def s12(c):
    t = c.t
    img = base(c, stars=0.6, neb=0.2)
    tn = c.lt("s12_num")
    draw_clock(img, c.gt, k=0.32, speed=1.0 + 2.0 * float(G.smoothstep(tn, tn + 0.6, t)))
    label(img, "now the crazy part…", 420, t, c.lt("s12_line"), size=56, weight="b")
    text_1380(img, tn, t)
    return img


def s13(c):
    t = c.t
    tr = c.lt("s13_reveal")
    img = base(c, stars=0.6, neb=0.2 + 0.15 * float(t > tr))
    if t < tr - 0.08:
        draw_clock(img, c.gt, k=0.32, speed=3.0)
        text_1380(img, -10, t)
        rng = np.random.default_rng(int(c.gt * 30))
        amt = 0.15 * (rng.random() < 0.35) + 0.25 * float(G.smoothstep(tr - 0.5, tr - 0.08, t))
        return glitch(img, amt, int(c.gt * 30))
    if t < tr + 0.1:  # flip: old text squashes away, new text unfolds
        p = (t - (tr - 0.08)) / 0.18
        if p < 0.5:
            text_1380(img, -10, t, scale_y=max(0.02, np.cos(np.pi * p)))
        else:
            _text93(img, t, tr, scale_y=max(0.02, -np.cos(np.pi * p)))
        return glitch(img, 0.9, int(c.gt * 30))
    dt = t - tr
    rr = 60 + 1200 * G.ease_out(dt / 1.0)
    im, d = rgb_layer()
    a = max(0.0, 1 - dt / 1.0)
    col = tuple(int(v * a) for v in (120, 170, 255))
    d.ellipse([CX - rr, 840 - rr, CX + rr, 840 + rr], outline=col, width=8)
    add_rgb_layer(img, im, 1.0, glow=14, glow_k=1.8)
    G.add_glow(img, CX, 840, 260, (0.3, 0.4, 1.0), 0.25 * np.exp(-dt * 2), extent=800)
    _text93(img, t, tr)
    img = zoom_frame(img, 1 + 0.07 * np.exp(-dt * 6), CX, 840)
    g = 0.7 * np.exp(-dt * 7)
    rng = np.random.default_rng(int(c.gt * 30) + 5)
    if rng.random() < 0.12 and dt > 0.6:
        g = 0.25
    img = glitch(img, g, int(c.gt * 30) + 1)
    amp = 30 * np.exp(-dt * 4.5)
    if amp > 0.5:
        dx, dy = rng.normal(0, amp, 2)
        img = np.roll(img, (int(dy), int(dx)), axis=(0, 1))
    return img


def _text93(img, t, tr, scale_y=1.0):
    ims = [(G.text_rgba("93 BILLION", 150, fill=YELLOW, stroke=9, max_w=760), 720, GOLD_GLOW),
           (G.text_rgba("LIGHT-YEARS", 116, fill=WHITE, stroke=8, max_w=760), 870, CYAN_GLOW),
           (G.text_rgba("WIDE", 116, fill=WHITE, stroke=8, max_w=760), 1000, CYAN_GLOW)]
    s = pop_scale(t - tr, 0.3, 0.45) if scale_y == 1.0 else 1.0
    for im, y, gl in ims:
        if scale_y != 1.0:
            im = im.resize((im.width, max(1, int(im.height * scale_y))), Image.BICUBIC)
        G.glow_text(img, im, CX, y, gl, k=1.1, radius=24, scale=s)


def _gal_sprites():
    global _GS
    if "_GS" in globals():
        return _GS
    out = []
    for k in range(6):
        xy, rgb = A.galaxy_particles(seed=100 + k, n=6000, b=0.25 + 0.05 * k, bulge=0.2)
        ang = k * 1.1
        tilt = 0.45 + 0.1 * k
        x = xy[:, 0] * np.cos(ang) - xy[:, 1] * np.sin(ang)
        y = (xy[:, 0] * np.sin(ang) + xy[:, 1] * np.cos(ang)) * tilt
        S = 64
        buf = np.zeros((S, S, 3), np.float32)
        xi = np.clip((S / 2 + x * 26).astype(int), 0, S - 1)
        yi = np.clip((S / 2 + y * 26).astype(int), 0, S - 1)
        np.add.at(buf, (yi, xi), rgb * 0.5)
        buf = ndimage.gaussian_filter(buf, (0.8, 0.8, 0)) + ndimage.gaussian_filter(buf, (3, 3, 0)) * 0.8
        out.append(buf)
    _GS = out
    return out


def _redshift_color(r):
    stops = [(1.0, (0.45, 0.65, 1.0)), (1.25, (0.4, 1.0, 0.7)), (1.5, (1.0, 0.9, 0.3)),
             (1.75, (1.0, 0.5, 0.2)), (2.0, (1.0, 0.2, 0.15))]
    for (r0, c0), (r1, c1) in zip(stops, stops[1:]):
        if r <= r1:
            f = max(0.0, (r - r0) / (r1 - r0))
            return tuple(a + (b - a) * f for a, b in zip(c0, c1))
    return stops[-1][1]


def s14(c):
    t = c.t
    img = base(c, stars=0.5, neb=0.15)
    D = c.D
    kexp = np.log(2.0) / D
    a = np.exp(kexp * t)
    cx, cy, sp = 540.0, 860.0, 150.0
    im, d = rgb_layer()
    step = sp * a
    for i in range(-8, 9):
        x = cx + i * step
        if -10 < x < W + 10:
            d.line([(x, 0), (x, H)], fill=(35, 75, 135), width=2)
    for j in range(-12, 13):
        y = cy + j * step
        if -10 < y < H + 10:
            d.line([(0, y), (W, y)], fill=(35, 75, 135), width=2)
    add_rgb_layer(img, im, 1.0, glow=8, glow_k=0.8)
    spr = _gal_sprites()
    for i in range(-6, 7):
        for j in range(-8, 9):
            x, y = cx + i * step, cy + j * step
            if -40 < x < W + 40 and -40 < y < H + 40:
                g = spr[(i * 7 + j * 3) % 6]
                G.add(img, g, int(x - 32), int(y - 32), 1.0 if (i, j) != (0, 0) else 1.5)
    # light beams travelling toward us (centre), stretched by the expansion
    beams = [((3, -3), 0.15), ((-4, 2), 0.7), ((2, 4), 1.4), ((-3, -4), 2.2)]
    tt = np.linspace(0, D + 0.5, 600)
    at = np.exp(kexp * tt)
    im2, d2 = rgb_layer()
    cpx = 300.0
    for (bi, bj), te in beams:
        if t < te:
            continue
        m = (tt >= te) & (tt <= t)
        chi_travel = np.trapezoid(cpx / (sp * at[m]), tt[m]) if m.sum() > 1 else 0.0
        e = np.array([bi, bj], float)
        L0 = np.linalg.norm(e)
        chi = max(0.0, L0 - chi_travel)
        u = -e / L0
        head = np.array([cx, cy]) - u * chi * step
        emit = np.array([cx, cy]) + e * step
        stretch = a / np.exp(kexp * te)
        lam = 26 * stretch
        Lw = min(260.0, np.linalg.norm(head - emit))
        ss = np.linspace(0, Lw, 120)
        nrm = np.array([-u[1], u[0]])
        amp = 10 * (1 - ss / max(Lw, 1)) ** 0.5
        pts = head[None, :] - u[None, :] * ss[:, None] + nrm[None, :] * (amp * np.sin(TAU * ss / lam + 5 * t))[:, None]
        col = tuple(int(255 * v) for v in _redshift_color(stretch))
        d2.line([tuple(p) for p in pts], fill=col, width=5)
        G.add_glow(img, head[0], head[1], 6, np.array(col) / 255, 1.6, halo=0.2, halo_r=18, extent=90)
    add_rgb_layer(img, im2, 1.0, glow=10, glow_k=2.0)
    label(img, "us", cy + 52, t, 0.3, size=38, color=YELLOW, glow=GOLD_GLOW, weight="b", x=cx)
    label(img, "SPACE IS EXPANDING", 420, t, 0.25, size=72, tracking=3)
    label(img, "light gets stretched redder", 505, t, c.lt("s14_light"), size=44, weight="b",
          color=(255, 150, 120), glow=(1.0, 0.3, 0.2))
    return img


_SPHERE = None


def s15(c):
    global _SPHERE
    t = c.t
    D = c.D
    void = float(G.smoothstep(0.1, D - 0.4, t))
    img = base(c, stars=0.55 - 0.42 * void, neb=0.06)
    if _SPHERE is None:
        _SPHERE = A.hdf_texture().resize((720, 720), Image.BOX)
    r = G.lerp(330, 72, G.ease_in_out((t - 0.1) / (D - 0.5)))
    cx, cy = 540.0, 870.0
    ri = int(round(2 * r))
    tex = np.asarray(_SPHERE.resize((ri, ri), Image.BOX), np.float32) / 255.0
    yy, xx = np.mgrid[0:ri, 0:ri].astype(np.float32)
    dd = np.sqrt((xx - ri / 2 + 0.5) ** 2 + (yy - ri / 2 + 0.5) ** 2) / r
    alpha = np.clip((1 - dd) * r, 0, 1)
    rim = np.clip(dd, 0, 1) ** 6
    rgb = tex * 1.25 + rim[..., None] * np.array([0.3, 0.55, 1.0]) * 1.3
    G.add_glow(img, cx, cy, r * 0.95, (0.25, 0.45, 1.0), 0.5, halo=0.22, halo_r=r * 0.8, extent=r * 3)
    G.over(img, rgb.astype(np.float32), alpha, int(round(cx - ri / 2)), int(round(cy - ri / 2)))
    label(img, "what we can see", cy - r - 58, t, 0.35, size=50, weight="b", glow=(0.3, 0.5, 1.0))
    q1, q2 = c.lt("s15_q1"), c.lt("s15_q2")
    for (x, y, size, ton, al) in ((805, 560, 104, q1, 0.9), (250, 1430, 84, q1 + 0.45, 0.6),
                                  (820, 1390, 72, q2, 0.5), (230, 600, 64, q2 + 0.25, 0.45)):
        label(img, "…?", y, t, ton, size=size, x=x, alpha=al, glow=(0.4, 0.4, 0.8), pop=0.3)
    return img


def s16(c):
    t = c.t
    td, tc = c.lt("s16_dot"), c.lt("s16_card")
    img = base(c, stars=1.0, streak=2.5 if t < td else 1.0, neb=0.12)
    if t < td:
        p = t / max(td, 0.1)
        R = 40 * (3200 / 40) ** (p ** 1.3)
        a = float(G.smoothstep(2600, 900, R))
        A.draw_galaxy(img, A.galaxy_particles(**MW), 540, 860, R, 0.12 * c.gt + 0.4, tilt=0.8, pa=0.15,
                      alpha=a)
        return img
    dt = t - td
    da = 1.0 if t < tc else max(0.35, 1 - (t - tc) / 0.3)
    dx, dy = 540, 880
    G.add_glow(img, dx, dy, 4.5, (0.55, 0.75, 1.0), 2.5 * da, halo=0.5 * da, halo_r=14, extent=140)
    im, d = rgb_layer()
    for k in range(3):
        ph = ((dt - k * 0.35) / 1.05) % 1.0 if dt - k * 0.35 > 0 else None
        if ph is None:
            continue
        rr = 10 + 110 * ph
        v = int(200 * (1 - ph) ** 2 * da)
        d.ellipse([dx - rr, dy - rr, dx + rr, dy + rr], outline=(v // 2, int(v * 0.8), v), width=3)
    d.line([(dx + 22, dy - 22), (dx + 95, dy - 95)], fill=(int(230 * da),) * 3, width=4)
    add_rgb_layer(img, im, 1.0, glow=6, glow_k=1.0)
    label(img, "you are here", dy - 140, t, td, size=58, color=YELLOW, glow=GOLD_GLOW, pop=0.5,
          alpha=da, x=600)
    if t >= tc:
        dc = t - tc
        img *= 1 - 0.35 * min(1.0, dc / 0.25)
        s = pop_scale(dc, 0.3, 0.55) * (1 + 0.02 * np.sin(dc * 5))
        f1 = G.text_rgba("Follow", 150, fill=WHITE, stroke=9, max_w=700)
        G.glow_text(img, f1, CX, 770, (1.0, 0.2, 0.45), k=1.2, radius=26, scale=s, alpha=min(1, dc / 0.08))
        f2 = for_more_sprite()
        G.glow_text(img, f2, CX, 925, (0.2, 0.9, 1.0), k=0.9, radius=22, scale=pop_scale(dc - 0.08, 0.3, 0.55),
                    alpha=float(np.clip((dc - 0.08) / 0.08, 0, 1)))
    return img


_FM = None


def for_more_sprite():
    global _FM
    if _FM is None:
        txt = G.text_rgba("for more", 100, fill=WHITE, stroke=7, max_w=600)
        em = G.emoji_rgba("🚀", int(txt.height * 0.95))
        out = Image.new("RGBA", (txt.width + 24 + em.width, max(txt.height, em.height)), (0, 0, 0, 0))
        out.paste(txt, (0, (out.height - txt.height) // 2), txt)
        out.paste(em, (txt.width + 24, (out.height - em.height) // 2), em)
        _FM = out
    return _FM


SCENES = {1: s1, 2: s2, 3: s3, 4: s4, 5: s5, 6: s6, 7: s7, 8: s8, 9: s9, 10: s10, 11: s11,
          12: s12, 13: s13, 14: s14, 15: s15, 16: s16}
