"""2D overlays and post effects: captions, title cards, corner text, glitch,
vignette, grain, bloom, camera shake/zoom."""
import json
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

import assets as A

W, H = 1080, 1920
# TikTok safe area (avoid right action rail and bottom description/UI)
SAFE_L, SAFE_R = 70, 900
CAP_CY = 1330
CAP_SIZE = 88
RED = (235, 35, 35)
WHITE = (255, 255, 255)


# ------------------------------------------------------------------ captions

class Captions:
    def __init__(self, timing_path):
        data = json.load(open(timing_path))
        self.titles = data['titles']
        self.chunks = []
        for L in data['lines']:
            words = L['words']
            # split into chunks at segment-ending punctuation or every 5 words
            segs, cur = [], []
            for w in words:
                cur.append(w)
                if w['w'].endswith(('...', '.', '?', '!')):
                    segs.append(cur)
                    cur = []
            if cur:
                segs.append(cur)
            for sg in segs:  # balanced split, max 6 words per chunk
                n = len(sg)
                k = -(-n // 6)
                base = 0
                for c in range(k):
                    m = n // k + (1 if c < n % k else 0)
                    self.chunks.append(sg[base:base + m])
                    base += m
        # display windows
        for i, ch in enumerate(self.chunks):
            t0 = ch[0]['t0']
            t_end = ch[-1]['t1'] + 0.55
            if i + 1 < len(self.chunks):
                nxt = self.chunks[i + 1][0]['t0']
                if nxt - ch[-1]['t1'] < 1.0:
                    t_end = nxt
                else:
                    t_end = min(t_end, nxt)
            ch_info = {'words': ch, 't0': t0, 't1': t_end}
            self.chunks[i] = ch_info
        for ch in self.chunks:
            ch['layout'] = self._layout([w['w'] for w in ch['words']], [w['key'] for w in ch['words']])

    def _layout(self, words, keys, size=CAP_SIZE):
        maxw = SAFE_R - SAFE_L
        while True:
            fnt = A.font(A.FONT_BLACK, size)
            disp = [w.upper() if k else w for w, k in zip(words, keys)]
            sp = fnt.getlength(' ')
            lines, cur, curw = [], [], 0
            for i, w in enumerate(disp):
                wl = fnt.getlength(w)
                if cur and curw + sp + wl > maxw:
                    lines.append(cur)
                    cur, curw = [], 0
                cur.append((i, w, wl))
                curw += (sp if len(cur) > 1 else 0) + wl
            if cur:
                lines.append(cur)
            if len(lines) <= 2 or size < 60:
                break
            size -= 6
        lh = size * 1.18
        pos = {}
        top = CAP_CY - lh * len(lines) / 2
        cx = (SAFE_L + SAFE_R) / 2
        for li, line in enumerate(lines):
            tw = sum(wl for _, _, wl in line) + sp * (len(line) - 1)
            x = cx - tw / 2
            for i, w, wl in line:
                pos[i] = (x + wl / 2, top + li * lh + lh / 2, w)
                x += wl + sp
        return {'size': size, 'pos': pos}

    def draw(self, img, t):
        d = ImageDraw.Draw(img)
        for ch in self.chunks:
            if not (ch['t0'] <= t < ch['t1']):
                continue
            size = ch['layout']['size']
            for i, w in enumerate(ch['words']):
                if t < w['t0']:
                    continue
                age = t - w['t0']
                pop = 1.0 + 0.32 * max(0.0, 1 - age / 0.13) ** 2
                s = int(size * pop)
                fnt = A.font(A.FONT_BLACK, s)
                x, y, txt = ch['layout']['pos'][i]
                col = RED if w['key'] else WHITE
                sw = max(6, s // 10)
                d.text((x + 5, y + 7), txt, font=fnt, fill=(0, 0, 0), anchor='mm', stroke_width=sw,
                       stroke_fill=(0, 0, 0))
                d.text((x, y), txt, font=fnt, fill=col, anchor='mm', stroke_width=sw, stroke_fill=(0, 0, 0))
        for (t0, t1, text) in self.titles:
            if t0 <= t < t1:
                draw_title(img, text, t - t0, t1 - t0)


def draw_title(img, text, age, dur):
    d = ImageDraw.Draw(img)
    size = 150
    while A.font(A.FONT_BLACK, size).getlength(text) > (SAFE_R - SAFE_L) * 0.88:
        size -= 4
    pop = 1.0 + 0.4 * max(0.0, 1 - age / 0.15) ** 2
    s = int(size * pop)
    fnt = A.font(A.FONT_BLACK, s)
    cx, cy = (SAFE_L + SAFE_R) / 2, 900
    r = random.Random(int(age * 30))
    jx, jy = (r.randint(-6, 6), r.randint(-4, 4)) if age < 0.5 or r.random() < 0.15 else (0, 0)
    if 'Part' in text:
        col = WHITE
        d.text((cx + jx + 6, cy + jy + 8), text, font=fnt, fill=(0, 0, 0), anchor='mm', stroke_width=14,
               stroke_fill=(0, 0, 0))
        d.text((cx + jx, cy + jy), text, font=fnt, fill=RED, anchor='mm', stroke_width=12, stroke_fill=(0, 0, 0))
    else:
        for off, c in ((-8, (255, 0, 60)), (8, (0, 220, 255))):
            d.text((cx + jx + off, cy + jy), text, font=fnt, fill=c, anchor='mm')
        d.text((cx + jx, cy + jy), text, font=fnt, fill=(255, 245, 120), anchor='mm', stroke_width=10,
               stroke_fill=(0, 0, 0))


@lru_cache(maxsize=1)
def corner_text():
    fnt = A.font(A.FONT_BLACK, 46)
    txt = 'wait for the ending '
    tw = int(fnt.getlength(txt))
    im = Image.new('RGBA', (tw + 70, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((6, 35), txt, font=fnt, fill=(255, 255, 255, 255), anchor='lm', stroke_width=5, stroke_fill=(0, 0, 0, 255))
    try:
        ef = A.font(A.FONT_EMOJI, 109)
        em = Image.new('RGBA', (140, 140), (0, 0, 0, 0))
        ImageDraw.Draw(em).text((70, 70), '\U0001F440', font=ef, embedded_color=True, anchor='mm')
        em = em.crop(em.getbbox())
        em = em.resize((52, max(1, round(52 * em.height / em.width))), Image.LANCZOS)
        im.alpha_composite(em, (tw + 6, 35 - em.height // 2))
    except Exception:
        pass
    return im


def draw_corner(img, t):
    c = corner_text()
    # gentle pulse
    img.paste(c, (44, 205), c)


# ------------------------------------------------------------------ post effects

def transform2d(img, zoom=1.0, dx=0.0, dy=0.0, rot=0.0, cx=None, cy=None):
    """Zoom about (cx,cy) + offset + small rotation (radians)."""
    if zoom == 1.0 and dx == 0 and dy == 0 and rot == 0:
        return img
    w, h = img.size
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    c, s = math.cos(rot), math.sin(rot)
    # output (x,y) -> input: p_in = C + R^-1 (p_out - C - d) / zoom
    a = c / zoom
    b = s / zoom
    d_ = -s / zoom
    e = c / zoom
    ox = w / 2 + dx
    oy = h / 2 + dy
    tx = cx - a * ox - b * oy
    ty = cy - d_ * ox - e * oy
    return img.transform((w, h), Image.AFFINE, (a, b, tx, d_, e, ty), Image.BILINEAR)


def shake(t, amp, freq=22.0, seed=0):
    r = random.Random(seed + int(t * freq))
    r2 = random.Random(seed + int(t * freq) + 1)
    f = (t * freq) % 1.0
    ax, ay = r.uniform(-1, 1), r.uniform(-1, 1)
    bx, by = r2.uniform(-1, 1), r2.uniform(-1, 1)
    k = f * f * (3 - 2 * f)
    return (ax + (bx - ax) * k) * amp, (ay + (by - ay) * k) * amp


@lru_cache(maxsize=4)
def vignette_mask(strength):
    y, x = np.mgrid[0:H, 0:W]
    nx = (x - W / 2) / (W / 2)
    ny = (y - H / 2) / (H / 2)
    r = np.sqrt(nx ** 2 * 1.0 + ny ** 2 * 0.85)
    v = 1 - strength * np.clip(r - 0.35, 0, 1) ** 1.6
    return np.clip(v, 0, 1).astype(np.float32)[:, :, None]


_grain_cache = {}


def grain(k):
    if k not in _grain_cache:
        rs = np.random.default_rng(k)
        g = rs.normal(0, 1, (H // 2, W // 2)).astype(np.float32)
        g = np.kron(g, np.ones((2, 2), np.float32))
        _grain_cache[k] = g[:, :, None]
    return _grain_cache[k]


def post(img, t, frame, vig=0.6, grain_amt=6.0, bloom=0.0, tint=None, flash=0.0, chroma=0, bright=1.0,
         contrast=1.0):
    if bloom > 0:
        small = img.resize((W // 6, H // 6), Image.BILINEAR)
        small = small.point(lambda v: max(0, v - 150) * 2)
        small = small.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
        img = Image.blend(img, ImageChops.add(img, small), min(1.0, bloom))
    arr = np.asarray(img).astype(np.float32)
    if chroma:
        arr = arr.copy()
        arr[:, :, 0] = np.roll(arr[:, :, 0], chroma, axis=1)
        arr[:, :, 2] = np.roll(arr[:, :, 2], -chroma, axis=1)
    if contrast != 1.0:
        arr = (arr - 128) * contrast + 128
    if bright != 1.0:
        arr *= bright
    if tint is not None:
        col, amt = tint
        arr = arr * (1 - amt) + arr * np.array(col, np.float32)[None, None, :] / 255.0 * amt
    if vig > 0:
        arr *= vignette_mask(round(vig, 2))
    if flash:
        col = (255, 255, 255) if not isinstance(flash, tuple) else flash[0]
        amt = flash if not isinstance(flash, tuple) else flash[1]
        arr = arr * (1 - amt) + np.array(col, np.float32)[None, None, :] * amt
    if grain_amt > 0:
        arr += grain(frame % 8) * grain_amt
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def glitch(img, amount, seed):
    """VHS/digital glitch: slice displacement, RGB split, noise bars, scanlines."""
    r = random.Random(seed)
    arr = np.asarray(img).copy()
    h, w, _ = arr.shape
    n = int(6 + 18 * amount)
    for _ in range(n):
        y0 = r.randint(0, h - 20)
        hh = r.randint(8, int(30 + 120 * amount))
        dx = int(r.uniform(-1, 1) * 160 * amount)
        arr[y0:y0 + hh] = np.roll(arr[y0:y0 + hh], dx, axis=1)
    sh = int(18 * amount) + 2
    out = arr.copy()
    out[:, :, 0] = np.roll(arr[:, :, 0], sh, axis=1)
    out[:, :, 2] = np.roll(arr[:, :, 2], -sh, axis=1)
    out[::4] = (out[::4] * 0.7).astype(np.uint8)
    for _ in range(int(3 * amount) + 1):
        y0 = r.randint(0, h - 40)
        hh = r.randint(4, 30)
        out[y0:y0 + hh] = np.clip(out[y0:y0 + hh].astype(int) + r.randint(40, 120), 0, 255).astype(np.uint8)
    return Image.fromarray(out)


def rewind_hud(img, t):
    d = ImageDraw.Draw(img)
    fnt = A.font(A.FONT_MONO, 64)
    if int(t * 4) % 2 == 0:
        d.text((90, 420), '◀◀ REWIND', font=fnt, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
    d.text((90, 1560), 'PM 03:12', font=A.font(A.FONT_MONO, 48), fill=(255, 255, 255), stroke_width=4,
           stroke_fill=(0, 0, 0))
    return img
