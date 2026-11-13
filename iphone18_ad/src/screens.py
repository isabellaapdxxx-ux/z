"""Procedural 2D content: screen textures (wallpaper, lock screen, night photo),
montage graphics (chip, battery), rain, particles, bokeh and the light line.

Textures are linear-light float32 (h, w, 3). Screen textures cover the display
area at the thinnest bezel (see phone3d.SCREEN_MIN_BEZEL) at TEX_PPMM px/mm.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import phone3d as P
from common import (H, W, CYAN, ORANGE, ORANGE_HI, TI_BLUE, TI_BLUE_HI, blur, font, pixel_grid,
                    resize, smoothstep, to_linear)

f32 = np.float32
TEX_PPMM = 10.0
SCR_W_MM = 2 * (P.HX - P.SCREEN_MIN_BEZEL)
SCR_H_MM = 2 * (P.HY - P.SCREEN_MIN_BEZEL)
TEX_W = int(round(SCR_W_MM * TEX_PPMM))
TEX_H = int(round(SCR_H_MM * TEX_PPMM))


def _mm(v):
    return v * TEX_PPMM


# ----------------------------------------------------------------------------- wallpaper
_WP_GRID = None


def wallpaper(t):
    """Layered silk waves in titanium blue -> violet -> magenta -> orange, flowing with time."""
    global _WP_GRID
    sw, sh = TEX_W // 2, TEX_H // 2
    if _WP_GRID is None:
        ys, xs = np.mgrid[0:sh, 0:sw].astype(f32)
        _WP_GRID = (xs / sw, ys / sh)
    u, v = _WP_GRID
    top = np.array([0.004, 0.006, 0.030], f32)
    mid = np.array([0.020, 0.045, 0.190], f32)
    img = top + (mid - top) * smoothstep(0.0, 0.55, v)[..., None]
    layers = [
        (0.30, 0.050, 2.2, 0.9, 0.35, (0.030, 0.090, 0.420)),
        (0.44, 0.060, 1.7, -0.7, 1.70, (0.110, 0.060, 0.520)),
        (0.57, 0.055, 2.6, 0.6, 3.10, (0.420, 0.040, 0.360)),
        (0.69, 0.050, 2.0, -0.8, 4.40, (0.950, 0.230, 0.040)),
        (0.81, 0.045, 2.9, 0.7, 5.60, (1.000, 0.520, 0.110)),
    ]
    for base, amp, freq, speed, ph, colr in layers:
        c = np.array(colr, f32)
        edge = (base + amp * np.sin(freq * 2 * math.pi * u + ph + speed * t)
                + 0.35 * amp * np.sin(2.3 * freq * 2 * math.pi * u - 1.7 * ph + 1.6 * speed * t))
        dv = v - edge
        inside = smoothstep(-0.002, 0.002, dv)
        # shadow cast onto the layer behind
        shadow = 1 - 0.55 * np.exp(-np.maximum(-dv, 0) / 0.035) * (dv < 0)
        img *= shadow[..., None]
        shade = 0.55 + 0.45 * np.exp(-np.maximum(dv, 0) / 0.09)
        layer = c * shade[..., None]
        img = img * (1 - inside[..., None]) + layer * inside[..., None]
        rim = np.exp(-(dv / 0.0045) ** 2) * 1.6 + np.exp(-(np.maximum(dv, 0) / 0.02)) * 0.25 * inside
        img += (c * 0.6 + 0.4) * rim[..., None] * 0.55
    return resize(img, (TEX_W, TEX_H), Image.BICUBIC).clip(0, None)


_LOCK_UI = None


def lock_ui():
    """Lock-screen UI as (alpha, colour) layers on the screen texture."""
    global _LOCK_UI
    if _LOCK_UI is None:
        img = Image.new("L", (TEX_W, TEX_H), 0)
        d = ImageDraw.Draw(img)
        fd = font("Inter-SemiBold.otf", int(_mm(4.0)))
        date = "Tuesday, September 8"
        l, t_, r, b = fd.getbbox(date)
        d.text(((TEX_W - (r - l)) / 2 - l, _mm(14.0) - t_), date, font=fd, fill=225)
        fc = font("InterDisplay-SemiBold.otf", int(_mm(25.0)))
        clock = "9:41"
        l, t_, r, b = fc.getbbox(clock)
        d.text(((TEX_W - (r - l)) / 2 - l, _mm(20.5) - t_), clock, font=fc, fill=245)
        # home indicator
        hw, hh = _mm(21.0), _mm(0.75)
        d.rounded_rectangle([TEX_W / 2 - hw, TEX_H - _mm(3.2) - hh, TEX_W / 2 + hw, TEX_H - _mm(3.2) + hh],
                            radius=hh, fill=235)
        # quick-action buttons
        btn = Image.new("L", (TEX_W, TEX_H), 0)
        bd = ImageDraw.Draw(btn)
        for cx in (_mm(13.0), TEX_W - _mm(13.0)):
            cy, rr = TEX_H - _mm(15.5), _mm(5.2)
            bd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=110)
        # icons: torch and camera (simple glyphs)
        cx, cy = _mm(13.0), TEX_H - _mm(15.5)
        d.rounded_rectangle([cx - _mm(1.0), cy - _mm(2.6), cx + _mm(1.0), cy + _mm(2.6)], radius=_mm(0.4), fill=240)
        d.rectangle([cx - _mm(1.5), cy - _mm(2.8), cx + _mm(1.5), cy - _mm(1.6)], fill=240)
        cx = TEX_W - _mm(13.0)
        d.rounded_rectangle([cx - _mm(2.6), cy - _mm(1.7), cx + _mm(2.6), cy + _mm(2.0)], radius=_mm(0.6), fill=240)
        d.ellipse([cx - _mm(1.1), cy - _mm(0.9), cx + _mm(1.1), cy + _mm(1.3)], fill=60)
        _LOCK_UI = (np.asarray(img, f32) / 255.0, np.asarray(btn, f32) / 255.0)
    return _LOCK_UI


def lock_screen(t, ui=1.0):
    tex = wallpaper(t)
    if ui > 0:
        txt, btn = lock_ui()
        tex *= (1 - 0.55 * btn * ui)[..., None]
        tex += (0.06 * btn * ui)[..., None]
        a = txt * ui
        tex = tex * (1 - a[..., None]) + 0.95 * a[..., None]
    return tex


# ----------------------------------------------------------------------------- night photo
def _value_noise(h, w, cells, rng, octaves=5, persistence=0.55):
    out = np.zeros((h, w), f32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        c = cells * (2 ** o)
        g = rng.random((max(2, int(c * h / w) + 2), c + 2)).astype(f32)
        up = np.asarray(Image.fromarray(g, "F").resize((w, h), Image.BICUBIC))
        out += up * amp
        total += amp
        amp *= persistence
    return out / total


_NIGHT = None


def night_photo():
    """A portrait night landscape: Milky Way, stars, mountains and a lake, linear float."""
    global _NIGHT
    if _NIGHT is not None:
        return _NIGHT
    rng = np.random.default_rng(7)
    h, w = TEX_H, TEX_W
    ys, xs = np.mgrid[0:h, 0:w].astype(f32)
    u, v = xs / w, ys / h
    horizon = 0.66
    sky = np.zeros((h, w, 3), f32)
    zen = np.array([0.004, 0.008, 0.035], f32)
    mid = np.array([0.020, 0.030, 0.120], f32)
    low = np.array([0.120, 0.060, 0.140], f32)
    glow = np.array([0.95, 0.38, 0.10], f32)
    k = np.clip(v / horizon, 0, 1)[..., None]
    sky = zen + (mid - zen) * smoothstep(0.0, 0.6, k) + (low - mid) * smoothstep(0.55, 1.0, k)
    sky += glow * (np.exp(-((v - horizon) / 0.06) ** 2) * (0.6 + 0.4 * np.exp(-((u - 0.62) / 0.35) ** 2)))[..., None] * 0.55
    # Milky Way band (diagonal) with dust lanes
    band_d = (u - 0.15) * 0.8 - (v - 0.05) * 0.6
    n1 = _value_noise(h, w, 6, rng)
    n2 = _value_noise(h, w, 14, rng)
    band = np.exp(-(band_d / 0.11) ** 2) * (0.55 + 0.9 * n1 - 0.25)
    dust = smoothstep(0.52, 0.66, n2) * np.exp(-(band_d / 0.035) ** 2)
    band = np.clip(band - dust * 0.6, 0, None) * smoothstep(horizon, horizon - 0.25, v)
    sky += (np.array([0.10, 0.08, 0.22], f32) + np.array([0.12, 0.06, 0.03], f32) * n2[..., None]) * band[..., None] * 0.9
    # stars
    ns = 1400
    sx, sy = rng.random(ns) * w, rng.random(ns) * h * horizon
    sb = rng.random(ns) ** 6 * 3.0 + 0.08
    star = np.zeros((h, w), f32)
    ix, iy = sx.astype(int), sy.astype(int)
    np.add.at(star, (iy, ix), sb)
    star = blur(star, 0.9) * 6 + blur(star, 3.0) * 1.5
    tint = 0.85 + 0.15 * np.stack([np.ones_like(u), np.ones_like(u) * 0.95, np.ones_like(u) * 1.1], -1)
    sky += star[..., None] * tint * 0.6
    # mountains
    img = sky
    for depth, (base, rough, colr) in enumerate([(0.58, 0.07, (0.010, 0.012, 0.032)),
                                                 (0.62, 0.05, (0.004, 0.006, 0.016)),
                                                 (0.655, 0.03, (0.0015, 0.002, 0.006))]):
        line = np.cumsum(rng.normal(0, 1, w)).astype(f32)
        line = np.asarray(Image.fromarray(line[None], "F").resize((w, 1), Image.BICUBIC))[0]
        line = (line - line.min()) / (np.ptp(line) + 1e-6)
        sm = np.convolve(line, np.ones(25) / 25, mode="same")
        ridge = base - rough * sm + 0.012 * np.sin(u[0] * 30 + depth)
        m = smoothstep(-0.0015, 0.0015, v - ridge[None, :])
        c = np.array(colr, f32)
        haze = np.exp(-np.maximum(v - ridge[None, :], 0) / 0.012)[..., None] * low * (0.25 - 0.08 * depth)
        img = img * (1 - m[..., None]) + (c + haze) * m[..., None]
    # lake reflection below horizon
    lake = v > horizon
    ry = np.clip(2 * horizon - v, 0, 1)
    ripple = 0.004 * np.sin(v * 900 + 4 * np.sin(u * 40)) * (v - horizon) * 8
    src_y = np.clip(((ry + ripple) * h).astype(int), 0, h - 1)
    refl = img[src_y, xs.astype(int)] * 0.45
    img = np.where(lake[..., None], refl, img)
    # cabin with warm windows on the far shore
    cx, cy = int(0.30 * w), int((horizon - 0.004) * h)
    img[cy - 14:cy, cx - 22:cx + 22] = (0.003, 0.003, 0.006)
    img[cy - 10:cy - 4, cx - 14:cx - 6] = (1.2, 0.55, 0.15)
    img[cy - 10:cy - 4, cx + 4:cx + 12] = (1.2, 0.55, 0.15)
    img += blur(np.where(img > 1.0, img, 0), 6) * 0.8
    _NIGHT = img.astype(f32)
    return _NIGHT


_NIGHT_UI = None


def night_ui():
    """Camera UI: shutter button and the yellow night-mode pill."""
    global _NIGHT_UI
    if _NIGHT_UI is None:
        a = Image.new("L", (TEX_W, TEX_H), 0)
        y = Image.new("L", (TEX_W, TEX_H), 0)
        d, dy = ImageDraw.Draw(a), ImageDraw.Draw(y)
        cx, cy = TEX_W / 2, TEX_H - _mm(16)
        r = _mm(6.5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=235, width=int(_mm(0.6)))
        r2 = _mm(5.4)
        d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=235)
        # night-mode pill top-left
        px0, py0, pw, ph = _mm(5.0), _mm(11.0), _mm(11.5), _mm(5.0)
        dy.rounded_rectangle([px0, py0, px0 + pw, py0 + ph], radius=ph / 2, fill=255)
        fm = font("Inter-Bold.otf", int(_mm(3.0)))
        d2 = ImageDraw.Draw(y)
        # moon glyph and "3s" knocked out of the pill
        mc = (px0 + _mm(3.0), py0 + ph / 2)
        d2.ellipse([mc[0] - _mm(1.5), mc[1] - _mm(1.5), mc[0] + _mm(1.5), mc[1] + _mm(1.5)], fill=0)
        d2.ellipse([mc[0] - _mm(0.7), mc[1] - _mm(1.9), mc[0] + _mm(2.1), mc[1] + _mm(0.9)], fill=255)
        l, t_, r_, b_ = fm.getbbox("3s")
        d2.text((px0 + _mm(5.6) - l, py0 + (ph - (b_ - t_)) / 2 - t_), "3s", font=fm, fill=0)
        _NIGHT_UI = (np.asarray(a, f32) / 255.0, np.asarray(y, f32) / 255.0)
    return _NIGHT_UI


def night_screen(k):
    """Night photo developing from dark and noisy (k=0) to bright and clean (k=1)."""
    img = night_photo()
    expo = 0.10 + 1.25 * k
    rng = np.random.default_rng(int(k * 1000))
    sm = (TEX_H // 4, TEX_W // 4)
    noise = rng.normal(0, 1, (sm[0], sm[1], 3)).astype(f32)
    noise = resize(noise, (TEX_W, TEX_H), Image.NEAREST)
    lum = img.mean(-1, keepdims=True)
    sat = 0.35 + 0.65 * k
    out = (lum + (img - lum) * sat) * expo
    out = out + noise * (0.025 * (1 - k) ** 1.5)
    ui_a, ui_y = night_ui()
    out = out * (1 - ui_a[..., None]) + 0.9 * ui_a[..., None]
    yellow = np.array([1.0, 0.72, 0.02], f32)
    out = out * (1 - ui_y[..., None]) + yellow * ui_y[..., None]
    return np.clip(out, 0, None)


# ----------------------------------------------------------------------------- chip
_CHIP = None


def _chip_assets():
    """Static PCB traces + chip package (linear float), built at 1.25x frame size."""
    global _CHIP
    if _CHIP is not None:
        return _CHIP
    S = 1.25
    cw, ch = int(W * S), int(H * S)
    cx, cy = cw / 2, ch / 2
    half = 230 * S
    rng = np.random.default_rng(3)
    traces = []
    for side in range(4):
        for k in range(14):
            off = (k - 6.5) / 6.5 * (half - 30 * S)
            # start point on the package edge, outward direction
            if side == 0:
                p, dvec, nvec = (cx + half, cy + off), (1, 0), (0, 1)
            elif side == 1:
                p, dvec, nvec = (cx - half, cy + off), (-1, 0), (0, 1)
            elif side == 2:
                p, dvec, nvec = (cx + off, cy + half), (0, 1), (1, 0)
            else:
                p, dvec, nvec = (cx + off, cy - half), (0, -1), (1, 0)
            sgn = 1 if off >= 0 else -1
            l1 = rng.uniform(30, 120) * S
            l2 = rng.uniform(40, 160) * S
            l3 = rng.uniform(150, 700) * S
            p0 = p
            p1 = (p0[0] + dvec[0] * l1, p0[1] + dvec[1] * l1)
            p2 = (p1[0] + (dvec[0] + sgn * nvec[0]) * l2 * 0.7, p1[1] + (dvec[1] + sgn * nvec[1]) * l2 * 0.7)
            p3 = (p2[0] + dvec[0] * l3, p2[1] + dvec[1] * l3)
            traces.append([p0, p1, p2, p3])
    base = Image.new("L", (cw, ch), 0)
    d = ImageDraw.Draw(base)
    for tr in traces:
        d.line(tr, fill=150, width=int(3 * S), joint="curve")
        x, y = tr[-1]
        r = 6 * S
        d.ellipse([x - r, y - r, x + r, y + r], outline=170, width=int(2 * S))
    # faint grid
    grid = Image.new("L", (cw, ch), 0)
    g = ImageDraw.Draw(grid)
    for gx in range(0, cw, int(48 * S)):
        g.line([(gx, 0), (gx, ch)], fill=18, width=1)
    for gy in range(0, ch, int(48 * S)):
        g.line([(0, gy), (cw, gy)], fill=18, width=1)
    tr_img = np.asarray(base, f32) / 255.0
    grid_img = np.asarray(grid, f32) / 255.0
    yy, xx = np.mgrid[0:ch, 0:cw].astype(f32)
    fall = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (700 * S) ** 2))
    layer = (tr_img[..., None] * np.array([0.05, 0.09, 0.18], f32) * 1.4
             + grid_img[..., None] * np.array([0.03, 0.05, 0.10], f32)) * fall[..., None]
    # package
    pk = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(pk).rounded_rectangle([cx - half, cy - half, cx + half, cy + half], radius=34 * S, fill=255)
    pk_a = np.asarray(pk.filter(ImageFilter.GaussianBlur(0.8)), f32) / 255.0
    rim = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(rim).rounded_rectangle([cx - half, cy - half, cx + half, cy + half], radius=34 * S,
                                          outline=255, width=int(4 * S))
    rim_a = np.asarray(rim.filter(ImageFilter.GaussianBlur(1.0)), f32) / 255.0
    dx, dy = (xx - cx) / half, (yy - cy) / half
    pkg = (np.array([0.004, 0.005, 0.008], f32)
           + np.array([0.012, 0.018, 0.032], f32) * np.clip(1 - 0.5 * (dx + dy), 0, 2)[..., None] * 0.5)
    rim_col = (np.array([0.35, 0.45, 0.65], f32) * smoothstep(0.4, -1.0, dx + dy)[..., None]
               + np.array([0.9, 0.45, 0.15], f32) * smoothstep(0.2, 1.2, dx + dy)[..., None])
    # die with fine grid
    di = 150 * S
    die_m = ((np.abs(xx - cx) < di) & (np.abs(yy - cy) < di)).astype(f32)
    fine = ((np.mod(xx - cx, 14 * S) < 1.6 * S) | (np.mod(yy - cy, 14 * S) < 1.6 * S)).astype(f32)
    die_m = blur(die_m, 1.0)
    # label
    lab = Image.new("L", (cw, ch), 0)
    fl = font("InterDisplay-SemiBold.otf", int(64 * S))
    txt = "A20 PRO"
    l, t_, r, b = fl.getbbox(txt)
    ImageDraw.Draw(lab).text((cx - (r - l) / 2 - l, cy - (b - t_) / 2 - t_), txt, font=fl, fill=255)
    lab_a = np.asarray(lab, f32) / 255.0
    halo = (blur(pk_a, 28 * S) * 0.7 + blur(pk_a, 90 * S) * 0.5) * (1 - pk_a)
    _CHIP = dict(S=S, cw=cw, ch=ch, cx=cx, cy=cy, half=half, traces=traces, layer=layer, pk_a=pk_a,
                 rim_a=rim_a, pkg=pkg, rim_col=rim_col, die_m=die_m, fine=fine, lab_a=lab_a, xx=xx, yy=yy,
                 halo=halo)
    return _CHIP


def _polyline_point(pts, s):
    """Point at arc length s along polyline pts (list of (x, y))."""
    for a, b in zip(pts[:-1], pts[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if s <= seg:
            f = s / seg
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        s -= seg
    return pts[-1]


def chip_frame(tl):
    """tl in [0, 1) over the 1 s shot. Returns linear float (H, W, 3)."""
    A = _chip_assets()
    S, cw, ch = A["S"], A["cw"], A["ch"]
    img = A["layer"].copy()
    # light pulses racing outward along the traces
    pulses = Image.new("L", (cw, ch), 0)
    pd = ImageDraw.Draw(pulses)
    warm = Image.new("L", (cw, ch), 0)
    wd = ImageDraw.Draw(warm)
    rng = np.random.default_rng(11)
    for i, tr in enumerate(A["traces"]):
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(tr[:-1], tr[1:]))
        delay = rng.uniform(0, 0.35)
        speed = rng.uniform(0.9, 1.6)
        s = (tl - delay) * speed * L
        if s <= 0:
            continue
        s = s % (L * 1.05)
        tail = 90 * S
        pts = [_polyline_point(tr, max(0.0, s - tail * f)) for f in np.linspace(0, 1, 8)]
        (wd if i % 3 == 0 else pd).line(pts, fill=255, width=int(4 * S))
        # lit section behind the pulse
        pd.line([_polyline_point(tr, x) for x in np.linspace(0, min(s, L), 12)], fill=60, width=int(3 * S))
    pa = np.asarray(pulses, f32) / 255.0
    wa = np.asarray(warm, f32) / 255.0
    lit = pa[..., None] * CYAN * 1.6 + wa[..., None] * ORANGE_HI * 2.2
    img += lit + blur(lit, 10 * S) * 1.4
    # package, rim, die glow and label
    a = A["pk_a"][..., None]
    img = img * (1 - a) + A["pkg"] * a
    img += A["rim_a"][..., None] * A["rim_col"] * 1.3
    pulse = 0.75 + 0.25 * math.sin(tl * 2 * math.pi * 2)
    die = A["die_m"][..., None] * (np.array([0.02, 0.04, 0.09], f32) + A["fine"][..., None] * TI_BLUE_HI * 0.30 * pulse)
    img += die
    lab = A["lab_a"][..., None]
    grad = smoothstep(A["cy"] - 40 * S, A["cy"] + 40 * S, A["yy"])[..., None]
    lab_col = np.array([1.0, 1.0, 1.0], f32) * (1 - grad) + np.array([0.75, 0.8, 0.9], f32) * grad
    img = img * (1 - lab) + lab_col * 1.15 * lab
    # halo
    img += A["halo"][..., None] * (TI_BLUE_HI * 0.22 + ORANGE * 0.06) * pulse
    # camera: quick pull-back with a slight rotation, cropped to the frame
    sc = 1.0 + 0.16 * (1 - tl) ** 2
    ang = -2.5 + 3.5 * tl
    out = np.empty((H, W, 3), f32)
    cosr, sinr = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    a_ = cosr / (sc / S)
    b_ = sinr / (sc / S)
    # inverse affine: src = M * (dst - centre) + chip centre
    coeffs = (a_, b_, A["cx"] - a_ * W / 2 - b_ * H / 2, -b_, a_, A["cy"] + b_ * W / 2 - a_ * H / 2)
    for c in range(3):
        out[..., c] = np.asarray(Image.fromarray(img[..., c], "F").transform((W, H), Image.AFFINE, coeffs,
                                                                             resample=Image.BILINEAR))
    return out


# ----------------------------------------------------------------------------- battery
def battery_frame(tl):
    img = np.zeros((H, W, 3), f32)
    xs, ys = pixel_grid()
    bw, bh, rr = 860, 330, 84
    cx, cy = W / 2 - 18, 560
    fill_k = 0.14 + 0.86 * (1 - (1 - min(1.0, tl / 0.82)) ** 3)
    # outline
    ol = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(ol)
    d.rounded_rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], radius=rr, outline=255, width=12)
    d.rounded_rectangle([cx + bw / 2 + 14, cy - 62, cx + bw / 2 + 40, cy + 62], radius=13, fill=255)
    ol_a = np.asarray(ol, f32) / 255.0
    # fill
    ins = 26
    fx0, fx1 = cx - bw / 2 + ins, cx + bw / 2 - ins
    fx = fx0 + (fx1 - fx0) * fill_k
    fm = Image.new("L", (W, H), 0)
    ImageDraw.Draw(fm).rounded_rectangle([fx0, cy - bh / 2 + ins, max(fx0 + 2 * (rr - ins), fx), cy + bh / 2 - ins],
                                         radius=rr - ins, fill=255)
    fm_a = np.asarray(fm, f32) / 255.0
    g = np.clip((xs - fx0) / (fx1 - fx0), 0, 1)[..., None]
    deep = np.array([0.010, 0.040, 0.300], f32)
    mid = np.array([0.020, 0.180, 0.700], f32)
    col = deep * (1 - g) ** 2 + mid * 2 * g * (1 - g) + ORANGE * 0.85 * g ** 2
    edge = np.exp(-((xs - fx) / 18) ** 2)[..., None] * (ORANGE_HI * 1.4 + 0.25)
    shine = np.exp(-((ys - (cy - bh / 2 + ins + 36)) / 14) ** 2)[..., None] * 0.10
    img += (col + edge * (fill_k < 0.995) + shine) * fm_a[..., None]
    img += blur((col + edge * 0.5) * fm_a[..., None], 34) * 0.35
    img += ol_a[..., None] * np.array([0.80, 0.84, 0.90], f32)
    # percentage counter
    pct = int(round(fill_k * 100))
    lay = Image.new("L", (W, H), 0)
    fp = font("InterDisplay-Bold.otf", 120)
    txt = f"{pct}%"
    l, t_, r, b = fp.getbbox("100%")
    tw = fp.getlength(txt)
    ImageDraw.Draw(lay).text((W / 2 - tw / 2, 250 - (b - t_) / 2 - t_), txt, font=fp, fill=255)
    la = np.asarray(lay, f32) / 255.0
    img = img * (1 - la[..., None]) + la[..., None] * 0.92
    sc = 1.04 - 0.04 * tl
    from common import zoom
    return zoom(img, sc)


# ----------------------------------------------------------------------------- light line
def light_line(x_line, intensity=1.0):
    xs, ys = pixel_grid()
    dx = np.abs(xs - x_line)
    vert = 0.30 + 0.70 * np.exp(-((ys - H * 0.47) / 430) ** 2)
    core = np.exp(-(dx / 1.3) ** 2) * 5.0 + np.exp(-dx / 10) * 0.55 + np.exp(-dx / 70) * 0.06
    col = np.array([0.80, 0.90, 1.0], f32)
    return (core * vert * intensity)[..., None] * col


# ----------------------------------------------------------------------------- bokeh / dust
def bokeh(t, n=7, seed=5, level=1.0, region=None):
    """Large out-of-focus light discs drifting slowly (depth-of-field glow)."""
    img = np.zeros((H, W, 3), f32)
    rng = np.random.default_rng(seed)
    for i in range(n):
        r = rng.uniform(50, 150)
        x = rng.uniform(-0.05, 1.05) * W + math.sin(t * 0.25 + i) * 30 + t * rng.uniform(-12, 12)
        y = rng.uniform(0.05, 0.95) * H + math.cos(t * 0.21 + 2 * i) * 20
        col = TI_BLUE_HI if i % 3 else ORANGE_HI
        a = rng.uniform(0.006, 0.016) * level
        x0, x1 = int(max(0, x - r - 3)), int(min(W, x + r + 3))
        y0, y1 = int(max(0, y - r - 3)), int(min(H, y + r + 3))
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(f32)
        d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2) / r
        disc = smoothstep(1.0, 0.82, d) * (0.8 + 0.2 * d ** 4)
        img[y0:y1, x0:x1] += disc[..., None] * col * a
    return img


def dust(t, n=90, seed=9, level=1.0):
    img = np.zeros((H, W), f32)
    rng = np.random.default_rng(seed)
    x = (rng.random(n) * W + t * rng.uniform(-20, 20, n)) % W
    y = (rng.random(n) * H - t * rng.uniform(5, 25, n)) % H
    b = rng.random(n) ** 3 * 1.5 * (0.6 + 0.4 * np.sin(t * 2 + rng.random(n) * 6))
    np.add.at(img, (y.astype(int), x.astype(int)), b * level)
    img = blur(img, 1.2) * 2.5 + blur(img, 5) * 1.0
    return img[..., None] * np.array([0.6, 0.75, 1.0], f32)


# ----------------------------------------------------------------------------- particles
def particles(tau, n=900, seed=21, origin=(W / 2, H / 2)):
    """Burst of glowing sparks tau seconds after the burst. Returns (behind, front) layers."""
    if tau < 0:
        z = np.zeros((H, W, 3), f32)
        return z, z
    rng = np.random.default_rng(seed)
    ang = rng.uniform(0, 2 * math.pi, n)
    speed = rng.uniform(250, 1700, n) * rng.choice([0.6, 1.0], n, p=[0.3, 0.7])
    drag = rng.uniform(1.2, 2.6, n)
    life = rng.uniform(0.9, 2.2, n)
    size = rng.choice([1, 2, 3], n, p=[0.55, 0.33, 0.12])
    group = rng.choice(4, n, p=[0.35, 0.25, 0.2, 0.2])
    front = rng.random(n) < 0.18
    ox, oy = origin
    ex = np.cos(ang)
    ey = np.sin(ang) * 0.72

    def pos(tt):
        d = speed / drag * (1 - np.exp(-drag * tt))
        return ox + ex * d, oy + ey * d + 30 * tt ** 2

    x1, y1 = pos(tau)
    x0, y0 = pos(max(0.0, tau - 0.045))
    fade = np.clip(1 - tau / life, 0, 1) ** 1.5 * np.clip(tau / 0.03, 0, 1)
    cols = [CYAN * 1.5, TI_BLUE_HI * 1.8, ORANGE_HI * 2.0, np.array([1.6, 1.6, 1.7], f32)]
    out = []
    for layer_front in (False, True):
        acc = np.zeros((H, W, 3), f32)
        for gi in range(4):
            sel = np.nonzero((group == gi) & (front == layer_front) & (fade > 0.01))[0]
            if sel.size == 0:
                continue
            im = Image.new("L", (W, H), 0)
            d = ImageDraw.Draw(im)
            for i in sel:
                d.line([(x0[i], y0[i]), (x1[i], y1[i])], fill=int(255 * fade[i]), width=int(size[i]))
            a = np.asarray(im, f32) / 255.0
            acc += a[..., None] * cols[gi]
        acc += blur(acc, 4) * 1.2 + blur(acc, 16) * 0.6
        out.append(acc)
    return out[0], out[1]


def shock_ring(tau, origin, life=0.55):
    if tau < 0 or tau > life:
        return np.zeros((H, W, 3), f32)
    xs, ys = pixel_grid()
    r = 60 + 1100 * (1 - (1 - tau / life) ** 2.5)
    d = np.sqrt((xs - origin[0]) ** 2 + ((ys - origin[1]) / 0.55) ** 2)
    ring = np.exp(-((d - r) / (6 + 30 * tau)) ** 2) * (1 - tau / life) ** 2.5
    return ring[..., None] * (TI_BLUE_HI * 0.16 + ORANGE * 0.05)


# ----------------------------------------------------------------------------- rain
def rain_streaks(t, n=420, seed=31):
    """Falling, motion-blurred rain drops in front of the camera (linear float)."""
    rng = np.random.default_rng(seed)
    depth = rng.random(n) ** 1.6
    x0 = rng.random(n) * (W + 300) - 150
    y0 = rng.random(n) * (H + 400)
    speed = 2200 + 2600 * depth
    length = 25 + 160 * depth * rng.uniform(0.6, 1.0, n)
    width = np.where(depth > 0.85, 3, np.where(depth > 0.55, 2, 1))
    alpha = (0.05 + 0.30 * depth) * rng.uniform(0.4, 1.0, n)
    near = Image.new("L", (W, H), 0)
    far = Image.new("L", (W, H), 0)
    dn, dfar = ImageDraw.Draw(near), ImageDraw.Draw(far)
    slant = 0.12
    for i in range(n):
        y = (y0[i] + speed[i] * t) % (H + 400) - 200
        x = x0[i] + slant * (y - y0[i])
        L = length[i]
        dd = dn if depth[i] > 0.8 else dfar
        dd.line([(x, y), (x - slant * L, y - L)], fill=int(255 * alpha[i]), width=int(width[i]))
    a = np.asarray(far, f32) / 255.0
    b = blur(np.asarray(near, f32) / 255.0, 2.5)
    return (a * 0.8 + b * 1.1)[..., None] * np.array([0.42, 0.52, 0.68], f32)


def droplets_layer(mask, seed=41, n=420):
    """Beaded water drops on the phone surface: returns (darken alpha, add light) arrays."""
    rng = np.random.default_rng(seed)
    ys, xs = np.nonzero(mask > 0.99)
    dark = np.zeros((H, W), f32)
    light = np.zeros((H, W), f32)
    if ys.size == 0:
        return dark, light
    pick = rng.integers(0, ys.size, n)
    S = 2
    dk = Image.new("L", (W * S, H * S), 0)
    lt = Image.new("L", (W * S, H * S), 0)
    d1, d2 = ImageDraw.Draw(dk), ImageDraw.Draw(lt)
    for i in pick:
        x, y = xs[i] * S, ys[i] * S
        r = rng.choice([2.0, 3.0, 4.0, 6.0, 8.0], p=[0.3, 0.3, 0.2, 0.13, 0.07]) * S
        ry = r * rng.uniform(0.85, 1.1)
        d1.ellipse([x - r, y - ry, x + r, y + ry], fill=150)
        d2.ellipse([x - r * 0.75, y - ry * 0.55, x + r * 0.75, y + ry * 0.85], fill=70)
        hr = max(1.0, r * 0.28)
        d2.ellipse([x - r * 0.45 - hr, y - ry * 0.45 - hr, x - r * 0.45 + hr, y - ry * 0.45 + hr], fill=255)
    dark = np.asarray(dk.resize((W, H), Image.LANCZOS), f32) / 255.0
    light = np.asarray(lt.resize((W, H), Image.LANCZOS), f32) / 255.0
    return dark * mask, light * mask


def splashes(t, mask_pts, seed=51, rate=70):
    """Tiny splash crowns where drops hit the phone. mask_pts = (ys, xs) candidate pixels."""
    rng = np.random.default_rng(seed)
    ys, xs = mask_pts
    acc = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(acc)
    if ys.size == 0:
        return np.zeros((H, W, 3), f32)
    nev = int(rate * 1.2)
    t_hit = rng.uniform(-0.2, 1.0, nev)
    idx = rng.integers(0, ys.size, nev)
    for th, i in zip(t_hit, idx):
        age = t - th
        if age < 0 or age > 0.16:
            continue
        k = age / 0.16
        x, y = xs[i], ys[i]
        rr = 4 + 26 * k
        a = int(255 * (1 - k) ** 1.5)
        d.ellipse([x - rr, y - rr * 0.45, x + rr, y + rr * 0.45], outline=a // 2, width=1)
        for j in range(7):
            an = j / 7 * 2 * math.pi + th * 10
            px, py = x + math.cos(an) * rr * 1.1, y + math.sin(an) * rr * 0.5 - 30 * k * (1 - k) * 4
            d.ellipse([px - 1.5, py - 1.5, px + 1.5, py + 1.5], fill=a)
    a = np.asarray(acc, f32) / 255.0
    return (a + blur(a, 2) * 0.8)[..., None] * np.array([0.75, 0.85, 1.0], f32)
