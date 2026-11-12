"""Post-processing (shake, zoom, grade, fog, grain, vignette, glitch, VHS), overlays and TikTok captions."""
import math
import random
import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import assets as A
from config import CAPTIONS, TEASER, DURATION, W, H

DEFAULTS = dict(zoom=1.0, dx=0.0, dy=0.0, rot=0.0, shake=0.0, flash=0.0, tint=None, sat=1.0, contrast=1.0, bright=1.0,
                chroma=0, glitch=0.0, vig=0.6, grain=7.0, fog=0.2, police=0.0, police_phase=0.0, overlay=None,
                blur=0.0, black=0.0, lids=None, hud=None, static=0.0, tracking=0.0, heart=0.0)


# ------------------------------------------------------------------ geometry

def transform2d(img, zoom=1.0, dx=0.0, dy=0.0, rot=0.0):
    if zoom == 1.0 and dx == 0 and dy == 0 and rot == 0:
        return img
    w, h = img.size
    c, s = math.cos(rot), math.sin(rot)
    a, b, d_, e = c / zoom, s / zoom, -s / zoom, c / zoom
    ox, oy = w / 2 + dx, h / 2 + dy
    tx = w / 2 - a * ox - b * oy
    ty = h / 2 - d_ * ox - e * oy
    return img.transform((w, h), Image.AFFINE, (a, b, tx, d_, e, ty), Image.BILINEAR)


def shake_offset(t, amp, freq=24.0, seed=0):
    r = random.Random(seed + int(t * freq))
    r2 = random.Random(seed + int(t * freq) + 1)
    f = (t * freq) % 1.0
    k = f * f * (3 - 2 * f)
    ax, ay = r.uniform(-1, 1), r.uniform(-1, 1)
    bx, by = r2.uniform(-1, 1), r2.uniform(-1, 1)
    return (ax + (bx - ax) * k) * amp, (ay + (by - ay) * k) * amp


# ------------------------------------------------------------------ cached layers

@lru_cache(maxsize=8)
def vignette(strength):
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (x - W / 2) / (W / 2)
    ny = (y - H / 2) / (H / 2)
    r = np.sqrt(nx ** 2 + 0.8 * ny ** 2)
    v = 1 - strength * np.clip(r - 0.3, 0, 1.2) ** 1.5
    return np.clip(v, 0, 1)[:, :, None].astype(np.float32)


_grain = {}


def grain(k):
    if k not in _grain:
        g = np.random.default_rng(100 + k).normal(0, 1, (H // 2, W // 2)).astype(np.float32)
        _grain[k] = np.kron(g, np.ones((2, 2), np.float32))[:, :, None]
    return _grain[k]


@lru_cache(maxsize=1)
def fog_tex():
    """Tileable soft noise for drifting fog (low resolution, upscaled)."""
    rs = np.random.default_rng(7)
    acc = np.zeros((96, 96), np.float32)
    for octave, amp in ((6, 1.0), (12, 0.5), (24, 0.25)):
        n = rs.random((octave, octave)).astype(np.float32)
        im = Image.fromarray((n * 255).astype(np.uint8)).resize((96, 96), Image.BICUBIC)
        acc += np.asarray(im, np.float32) / 255 * amp
    acc = (acc - acc.min()) / (acc.max() - acc.min())
    return acc


@lru_cache(maxsize=1)
def fog_ramp():
    y = np.linspace(0, 1, H, dtype=np.float32)
    return (0.25 + 0.75 * np.clip((y - 0.35) / 0.65, 0, 1))[:, None]


def fog_layer(t):
    tex = fog_tex()
    # two drifting copies
    a = np.roll(tex, int(t * 6) % 96, axis=1)
    b = np.roll(np.roll(tex.T, int(t * 3.5) % 96, axis=1), int(t * 2) % 96, axis=0)
    m = (a * 0.6 + b * 0.4)
    m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((W // 4, H // 4), Image.BICUBIC)
                   .resize((W, H), Image.BILINEAR), np.float32) / 255.0
    return (m * fog_ramp())[:, :, None]


_fog_cache = {}


def fog_at(t):
    # fog moves slowly: recompute ~6 times per second
    k = int(t * 6)
    if k not in _fog_cache:
        if len(_fog_cache) > 4:
            _fog_cache.clear()
        _fog_cache[k] = fog_layer(k / 6)
    return _fog_cache[k]


# ------------------------------------------------------------------ overlays

@lru_cache(maxsize=None)
def cellar_overlay():
    """Dirty basement window with bars, seen from outside."""
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fr = (14, 14, 12, 255)
    d.rectangle([0, 0, W, 170], fill=fr)
    d.rectangle([0, H - 300, W, H], fill=fr)
    d.rectangle([0, 0, 70, H], fill=fr)
    d.rectangle([W - 70, 0, W, H], fill=fr)
    for x in (300, 530, 760):
        d.rectangle([x, 170, x + 28, H - 300], fill=(28, 28, 26, 255))
        d.rectangle([x + 4, 170, x + 10, H - 300], fill=(60, 60, 55, 255))
    d.rectangle([70, 170, W - 70, 184], fill=(40, 40, 36, 255))
    # grime + cobweb corner
    r = random.Random(4)
    g = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    for _ in range(140):
        x, y = r.randint(70, W - 70), r.randint(170, H - 300)
        s = r.randint(10, 70)
        gd.ellipse([x - s, y - s, x + s, y + s], fill=(70, 80, 40, r.randint(10, 35)))
    g = g.filter(ImageFilter.GaussianBlur(14))
    im = Image.alpha_composite(g, im)
    d = ImageDraw.Draw(im)
    for i in range(7):
        a = i * 0.24
        d.line([(70, 184), (70 + 260 * math.cos(a), 184 + 260 * math.sin(a))], fill=(200, 200, 200, 70), width=2)
    for rr in (80, 140, 200):
        pts = [(70 + rr * math.cos(i * 0.24), 184 + rr * math.sin(i * 0.24)) for i in range(7)]
        d.line(pts, fill=(200, 200, 200, 60), width=2)
    return im


@lru_cache(maxsize=None)
def bedroom_overlay():
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fr = (200, 200, 195, 255)
    d.rectangle([0, 0, W, 200], fill=(12, 14, 24, 255))
    d.rectangle([0, H - 380, W, H], fill=(12, 14, 24, 255))
    d.rectangle([0, 0, 90, H], fill=(12, 14, 24, 255))
    d.rectangle([W - 90, 0, W, H], fill=(12, 14, 24, 255))
    d.rectangle([90, 200, W - 90, 230], fill=fr)
    d.rectangle([90, H - 410, W - 90, H - 380], fill=fr)
    d.rectangle([90, 200, 120, H - 380], fill=fr)
    d.rectangle([W - 120, 200, W - 90, H - 380], fill=fr)
    d.rectangle([W // 2 - 12, 200, W // 2 + 12, H - 380], fill=fr)
    d.rectangle([90, 960 - 12, W - 90, 960 + 12], fill=fr)
    # moonlit reflection streak on the glass
    d.polygon([(130, 700), (420, 240), (480, 240), (190, 700)], fill=(255, 255, 255, 18))
    return im


def rewind_hud(img, t):
    d = ImageDraw.Draw(img)
    f = A.font(A.FONT_MONO, 78)
    if int(t * 6) % 2 == 0:
        d.text((90, 430), '◀◀ REWIND', font=f, fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0))
    d.text((90, 1540), 'PLAY  ◀◀  -00:0' + str(int((4 - t) * 10) % 10), font=A.font(A.FONT_MONO, 44),
           fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))


# ------------------------------------------------------------------ effects

def glitch(arr, amount, seed):
    r = random.Random(seed)
    h, w, _ = arr.shape
    arr = arr.copy()
    for _ in range(int(5 + 16 * amount)):
        y0 = r.randint(0, h - 20)
        hh = r.randint(8, int(30 + 140 * amount))
        dx = int(r.uniform(-1, 1) * 180 * amount)
        arr[y0:y0 + hh] = np.roll(arr[y0:y0 + hh], dx, axis=1)
    sh = int(20 * amount) + 2
    out = arr.copy()
    out[:, :, 0] = np.roll(arr[:, :, 0], sh, axis=1)
    out[:, :, 2] = np.roll(arr[:, :, 2], -sh, axis=1)
    out[::4] *= 0.7
    for _ in range(int(3 * amount) + 1):
        y0 = r.randint(0, h - 40)
        hh = r.randint(4, 30)
        out[y0:y0 + hh] += r.randint(40, 130)
    # a few blocky colored macroblocks
    for _ in range(int(6 * amount)):
        x0, y0 = r.randint(0, w - 120), r.randint(0, h - 120)
        s = r.choice([32, 64, 96])
        out[y0:y0 + s, x0:x0 + s] = out[y0:y0 + s, x0:x0 + s].mean(axis=(0, 1)) * np.array(
            [r.uniform(.5, 1.5) for _ in range(3)], np.float32)
    return out


def static_noise(arr, amount, seed):
    rs = np.random.default_rng(seed)
    n = rs.random((H // 4, W // 4), dtype=np.float32)
    n = np.kron(n, np.ones((4, 4), np.float32))[:, :, None] * 255
    return arr * (1 - amount) + n * amount


def tracking_band(arr, t):
    """VHS tracking: a bright, wobbling, displaced band rolling up the screen."""
    y0 = int((1 - (t * 2.3) % 1.0) * (H + 300)) - 150
    y1 = y0 + 150
    a, b = max(0, y0), min(H, y1)
    if b > a:
        arr[a:b] = np.roll(arr[a:b], 40, axis=1) * 0.6 + 90
    # wobble every line slightly
    return arr


def police_glow(arr, strength, phase):
    red_on = (int(phase * 2) % 2) == 0
    col = np.array((255, 30, 30) if red_on else (40, 90, 255), np.float32)
    x = np.linspace(-1, 1, W, dtype=np.float32)
    edge = np.clip(np.abs(x) ** 2.5, 0, 1)
    # the active color glows from one side
    side = (x > 0) if red_on else (x < 0)
    m = (edge * (0.4 + 0.6 * side))[None, :, None] * strength
    return arr * (1 - m * 0.6) + col * m * 0.6 + col * 0.06 * strength


def post(img, spec, t, frame):
    s = dict(DEFAULTS)
    s.update({k: v for k, v in spec.items() if k in DEFAULTS})
    if s['blur'] > 0.3:
        img = img.filter(ImageFilter.GaussianBlur(s['blur']))
    sx, sy = shake_offset(t, s['shake']) if s['shake'] else (0.0, 0.0)
    img = transform2d(img, s['zoom'], s['dx'] + sx, s['dy'] + sy, s['rot'] + (sx / 5000.0))
    if s['overlay'] == 'cellar':
        ov = cellar_overlay()
        img = img.copy()
        img.paste(ov, (0, 0), ov)
    elif s['overlay'] == 'bedroom':
        ov = bedroom_overlay()
        img = img.copy()
        img.paste(ov, (0, 0), ov)
    arr = np.asarray(img, dtype=np.float32)
    if s['chroma']:
        c = int(s['chroma'])
        arr = arr.copy()
        arr[:, :, 0] = np.roll(arr[:, :, 0], c, axis=1)
        arr[:, :, 2] = np.roll(arr[:, :, 2], -c, axis=1)
    if s['sat'] != 1.0:
        g = arr.mean(axis=2, keepdims=True)
        arr = g + (arr - g) * s['sat']
    if s['tint'] is not None:
        arr = arr * np.array(s['tint'], np.float32)[None, None, :]
    if s['contrast'] != 1.0:
        arr = (arr - 110) * s['contrast'] + 110
    if s['bright'] != 1.0:
        arr = arr * s['bright']
    if s['fog'] > 0:
        f = fog_at(t)
        arr = arr + (np.array([150, 165, 190], np.float32) - arr) * (f * s['fog'] * 0.55)
    if s['police'] > 0:
        arr = police_glow(arr, s['police'], s['police_phase'])
    vig = s['vig']
    if s['heart'] > 0:
        # vignette pulses with the heartbeat
        ph = (t * 2.0) % 1.0
        pulse = math.exp(-ph * 10) + 0.6 * math.exp(-max(0, ph - 0.18) * 10) * (ph > 0.18)
        vig = vig + 0.18 * s['heart'] * pulse
    if vig > 0:
        arr = arr * vignette(round(min(vig, 1.2), 2))
    if s['flash']:
        fl = s['flash']
        col, amt = ((255, 255, 255), fl) if not isinstance(fl, tuple) else (fl[1], fl[0])
        if amt > 0:
            arr = arr * (1 - amt) + np.array(col, np.float32)[None, None, :] * amt
    if s['static'] > 0:
        arr = static_noise(arr, s['static'], frame)
    if s['tracking'] > 0:
        arr = tracking_band(arr, t)
    if s['glitch'] > 0:
        arr = glitch(arr, s['glitch'], frame * 7 + 1)
    if s['grain'] > 0:
        arr = arr + grain(frame % 6) * s['grain']
    if s['black'] > 0:
        arr = arr * (1 - s['black'])
    if s['lids'] is not None:
        o = s['lids']
        hgt = int((1 - o) * H / 2)
        if hgt > 0:
            yy = np.arange(H)[:, None, None]
            m = np.clip(np.minimum(yy - hgt, (H - hgt) - yy) / 60.0, 0, 1)
            arr = arr * m
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if s['hud'] == 'rewind':
        rewind_hud(out, t)
    return out


# ------------------------------------------------------------------ captions

CAP_SIZE = 92
CAP_Y = 1270          # center of the caption block (lower-middle third, clear of TikTok's UI)
CAP_MAXW = 800
EMOJI_RE = re.compile('[\U0001F300-\U0001FAFF☀-➿]')


@lru_cache(maxsize=None)
def emoji_img(ch, size):
    f = A.font(A.FONT_EMOJI, 109)
    im = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    k = size / im.height
    return im.resize((max(1, int(im.width * k)), size), Image.LANCZOS)


def parse(text):
    """-> list of (word, style) with style in {'n','red','shake'}."""
    out = []
    style = 'n'
    for tok in text.split(' '):
        st = style
        w = tok
        if w.startswith('~'):
            st = 'shake'
            w = w[1:]
            style = 'shake'
        elif w.startswith('*') or w.startswith('"*'):
            st = 'red'
            w = w.replace('*', '', 1)
            style = 'red'
        end = False
        if '~' in w:
            w = w.replace('~', '')
            end = True
        if '*' in w:
            w = w.replace('*', '')
            end = True
        out.append((w, st))
        if end:
            style = 'n'
    return out


def layout(words, size):
    fnt = A.font(A.FONT_BLACK, size)
    space = size * 0.28
    lines, cur, cw = [], [], 0
    for w, st in words:
        ww = (emoji_img(w, int(size * 0.95)).width if EMOJI_RE.fullmatch(w) else fnt.getlength(w))
        if cur and cw + space + ww > CAP_MAXW:
            lines.append((cur, cw))
            cur, cw = [], 0
        cw = cw + (space if cur else 0) + ww
        cur.append((w, st, ww))
    if cur:
        lines.append((cur, cw))
    return lines, fnt, space


def render_caption(text, t_age, t):
    words = parse(text)
    size = CAP_SIZE if len(text) > 14 else int(CAP_SIZE * 1.35)
    lines, fnt, space = layout(words, size)
    lh = size * 1.18
    bw = int(max(cw for _, cw in lines) + 80)
    bh = int(lh * len(lines) + 60)
    im = Image.new('RGBA', (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    stroke = max(8, size // 9)
    for li, (ws, cw) in enumerate(lines):
        x = (bw - cw) / 2
        y = 30 + li * lh + lh / 2
        for w, st, ww in ws:
            ox = oy = 0
            if st == 'shake':
                r = random.Random(int(t * 30) * 31 + hash(w) % 97)
                ox, oy = r.uniform(-7, 7), r.uniform(-7, 7)
            if EMOJI_RE.fullmatch(w):
                e = emoji_img(w, int(size * 0.95))
                im.paste(e, (int(x), int(y - e.height / 2)), e)
            else:
                col = (255, 255, 255) if st == 'n' else (255, 38, 38)
                d.text((x + ox, y + oy), w, font=fnt, fill=col, anchor='lm', stroke_width=stroke,
                       stroke_fill=(0, 0, 0))
            x += ww + space
    return im


def pop_scale(age):
    if age < 0.09:
        return 0.55 + (1.14 - 0.55) * (age / 0.09)
    if age < 0.2:
        return 1.14 - 0.14 * ((age - 0.09) / 0.11)
    return 1.0


def draw_captions(img, t):
    for a, b, text in CAPTIONS:
        if a <= t < b or (b >= DURATION and t >= a):
            age = t - a
            cap = render_caption(text, age, t)
            # the hook caption must be big on frame 1: it lands oversized and settles instead of growing in
            sc = (1.0 + 0.18 * max(0.0, 1 - age / 0.15)) if a < 0.01 else pop_scale(age)
            if sc != 1.0:
                cap = cap.resize((max(1, int(cap.width * sc)), max(1, int(cap.height * sc))), Image.BILINEAR)
            img.paste(cap, (int(W / 2 - cap.width / 2), int(CAP_Y - cap.height / 2)), cap)
    return img


# ------------------------------------------------------------------ teaser / progress bar

@lru_cache(maxsize=1)
def teaser_label():
    size = 44
    fnt = A.font(A.FONT_BLACK, size)
    txt = TEASER.replace('😳', '').strip()
    tw = fnt.getlength(txt)
    e = emoji_img('😳', int(size * 1.05))
    bw = int(tw + 14 + e.width + 30)
    im = Image.new('RGBA', (bw, size + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((15, (size + 30) / 2), txt, font=fnt, fill=(255, 255, 255), anchor='lm', stroke_width=6,
           stroke_fill=(0, 0, 0))
    im.paste(e, (int(15 + tw + 14), int((size + 30 - e.height) / 2)), e)
    return im


BAR_Y = 300


def draw_teaser(img, t):
    lab = teaser_label()
    img.paste(lab, (int(W / 2 - lab.width / 2), BAR_Y - lab.height - 6), lab)
    d = ImageDraw.Draw(img, 'RGBA')
    bw, bh = 620, 16
    x0 = (W - bw) // 2
    d.rounded_rectangle([x0 - 3, BAR_Y - 3, x0 + bw + 3, BAR_Y + bh + 3], 11, fill=(0, 0, 0, 200))
    d.rounded_rectangle([x0, BAR_Y, x0 + bw, BAR_Y + bh], 8, fill=(255, 255, 255, 70))
    frac = min(1.0, t / DURATION)
    fw = max(bh, int(bw * frac))
    pulse = 0.5 + 0.5 * math.sin(t * 6)
    d.rounded_rectangle([x0, BAR_Y, x0 + fw, BAR_Y + bh], 8, fill=(235, int(30 + 30 * pulse), 40, 255))
    # skull-free "ending" marker at the end of the bar
    d.ellipse([x0 + bw - 8, BAR_Y - 6, x0 + bw + 20, BAR_Y + bh + 6], fill=(255, 255, 255, 230),
              outline=(0, 0, 0), width=3)
    return img
