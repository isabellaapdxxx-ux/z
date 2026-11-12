"""Full-frame 2D insert shots (phone UI in hand, newspaper, list, clock)."""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import assets as A

W, H = 1080, 1920
SKIN = (236, 196, 140)


@lru_cache(maxsize=4)
def dark_bg(kind):
    if kind == 'closet':
        im = A.sky_bg(W, H, (18, 14, 12), (8, 6, 6)).copy()
        d = ImageDraw.Draw(im, 'RGBA')
        for k in range(9):  # slat light stripes
            y = 120 + k * 200
            d.polygon([(0, y), (W, y - 260), (W, y - 230), (0, y + 30)], fill=(255, 220, 160, 18))
        return im
    if kind == 'desk':
        im = Image.new('RGB', (W, H), (40, 28, 20))
        d = ImageDraw.Draw(im)
        for y in range(0, H, 60):
            d.line([(0, y), (W, y + 30)], fill=(48, 34, 24), width=18)
        return im
    if kind == 'wall':
        im = Image.new('RGB', (W, H), (60, 62, 68))
        d = ImageDraw.Draw(im)
        for r, y in enumerate(range(0, H, 140)):
            off = 0 if r % 2 == 0 else 150
            for x in range(-300 + off, W, 300):
                d.rectangle([x + 6, y + 6, x + 294, y + 134], fill=(72, 75, 82) if (x // 300 + r) % 2 else (66, 69, 76))
        return im
    return Image.new('RGB', (W, H), (0, 0, 0))


def light_mask(cx, cy, r, amb=0.12):
    y, x = np.ogrid[0:H, 0:W]
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r
    m = np.clip(1.15 - d, 0, 1) ** 1.3
    return (amb + (1 - amb) * m).astype(np.float32)[:, :, None]


def apply_light(img, cx, cy, r, amb=0.12, col=(1.0, 0.97, 0.88)):
    arr = np.asarray(img).astype(np.float32) * light_mask(cx, cy, r, amb) * np.array(col, np.float32)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def paste_rot(base, tex, cx, cy, scale, angle):
    t = tex.resize((int(tex.width * scale), int(tex.height * scale)), Image.LANCZOS).rotate(
        angle, resample=Image.BICUBIC, expand=True)
    base.paste(t, (int(cx - t.width / 2), int(cy - t.height / 2)), t)


# ------------------------------------------------------------------ phone in hand

PX0, PY0, PX1, PY1 = 250, 300, 830, 1480  # phone body
SX0, SY0, SX1, SY1 = 285, 360, 795, 1420  # screen


def _screen(state, t, typed='', press=None):
    w, h = SX1 - SX0, SY1 - SY0
    im = Image.new('RGB', (w, h), (14, 16, 24))
    d = ImageDraw.Draw(im)
    fb = lambda s: A.font(A.FONT_BOLD, s)
    fk = lambda s: A.font(A.FONT_BLACK, s)
    d.text((30, 18), '11:58', font=fb(30), fill=(255, 255, 255))
    d.text((w - 30, 18), '▮▮▮  41%', font=fb(26), fill=(255, 255, 255), anchor='ra')
    if state == 'dial':
        d.text((w / 2, 170), typed or ' ', font=fk(120), fill=(255, 255, 255), anchor='mm')
        keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#']
        for i, k in enumerate(keys):
            cx = w / 2 + (i % 3 - 1) * 150
            cy = 380 + (i // 3) * 140
            fill = (90, 95, 110) if k == press else (40, 44, 56)
            d.ellipse([cx - 58, cy - 58, cx + 58, cy + 58], fill=fill)
            d.text((cx, cy), k, font=fk(54), fill=(255, 255, 255), anchor='mm')
        d.ellipse([w / 2 - 58, 940 - 58, w / 2 + 58, 940 + 58], fill=(40, 200, 90))
    elif state in ('calling', 'connected'):
        d.ellipse([w / 2 - 90, 110, w / 2 + 90, 290], fill=(60, 64, 80))
        d.text((w / 2, 200), 'SOS', font=fk(56), fill=(255, 80, 80), anchor='mm')
        d.text((w / 2, 380), '911', font=fk(130), fill=(255, 255, 255), anchor='mm')
        if state == 'calling':
            dots = '.' * (1 + int(t * 3) % 3)
            d.text((w / 2, 490), 'calling' + dots, font=fb(52), fill=(120, 230, 140), anchor='mm')
        else:
            sec = int(t)
            d.text((w / 2, 490), f'00:{sec:02d}', font=fb(56), fill=(120, 230, 140), anchor='mm')
            d.text((w / 2, 560), 'Connected', font=fb(36), fill=(170, 170, 185), anchor='mm')
        for i, lab in enumerate(('mute', 'keypad', 'speaker')):
            cx = w / 2 + (i - 1) * 150
            d.ellipse([cx - 52, 660, cx + 52, 764], fill=(44, 48, 60))
            d.text((cx, 712), lab[0].upper(), font=fk(40), fill=(220, 220, 230), anchor='mm')
        d.ellipse([w / 2 - 62, 880, w / 2 + 62, 1004], fill=(225, 40, 40))
        d.rounded_rectangle([w / 2 - 34, 934, w / 2 + 34, 950], 6, fill=(255, 255, 255))
    elif state == 'traced':
        d.text((w / 2, 150), '911', font=fk(120), fill=(255, 255, 255), anchor='mm')
        d.text((w / 2, 250), 'Call ended  •  00:47', font=fb(38), fill=(255, 90, 90), anchor='mm')
        # map card
        d.rounded_rectangle([40, 320, w - 40, 760], 26, fill=(205, 222, 200))
        for k in range(7):
            d.line([(40, 360 + k * 60), (w - 40, 330 + k * 66)], fill=(250, 250, 250), width=14)
        for k in range(5):
            d.line([(80 + k * 100, 320), (40 + k * 110, 760)], fill=(250, 250, 250), width=12)
        d.rectangle([180, 450, 300, 560], fill=(190, 175, 160))
        px, py = w / 2 + 20, 520
        pulse = 30 + 25 * (t * 2 % 1)
        d.ellipse([px - pulse, py + 40 - pulse * 0.4, px + pulse, py + 40 + pulse * 0.4], outline=(230, 40, 40), width=5)
        d.ellipse([px - 34, py - 70, px + 34, py - 2], fill=(230, 40, 40))
        d.polygon([(px - 30, py - 26), (px + 30, py - 26), (px, py + 40)], fill=(230, 40, 40))
        d.ellipse([px - 13, py - 49, px + 13, py - 23], fill=(255, 255, 255))
        d.rounded_rectangle([40, 790, w - 40, 900], 22, fill=(30, 120, 60))
        d.text((w / 2, 845), 'LOCATION SHARED ✓', font=fk(40), fill=(255, 255, 255), anchor='mm')
        d.text((w / 2, 950), '42 Maple St.', font=fb(40), fill=(220, 220, 230), anchor='mm')
    elif state == 'black':
        pass
    return im


def phone_insert(state, t, typed='', press=None, bg='closet', shake_xy=(0, 0), glow=1.0, tilt=0.0):
    base = dark_bg(bg).copy()
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # glow behind phone
    gl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(gl).ellipse([PX0 - 160, PY0 - 120, PX1 + 160, PY1 + 120], fill=(120, 150, 255, int(90 * glow)))
    gl = gl.filter(ImageFilter.GaussianBlur(90))
    base.paste(gl, (0, 0), gl)
    # back hand / palm
    d.rectangle([330, 1150, 900, 1920], fill=SKIN, outline=(170, 130, 90), width=6)
    d.rectangle([780, 1120, 900, 1400], fill=(225, 185, 130), outline=(170, 130, 90), width=6)
    # phone body
    d.rounded_rectangle([PX0, PY0, PX1, PY1], 60, fill=(22, 22, 28), outline=(70, 70, 80), width=6)
    layer.paste(_screen(state, t, typed, press), (SX0, SY0))
    # fingers wrapping right edge
    for k in range(3):
        y = 760 + k * 170
        d.rectangle([790, y, 900, y + 140], fill=SKIN, outline=(170, 130, 90), width=6)
    # thumb on left
    d.rectangle([190, 1120, 330, 1460], fill=SKIN, outline=(170, 130, 90), width=6)
    if tilt:
        layer = layer.rotate(tilt, resample=Image.BICUBIC, center=(W / 2, H * 0.6))
    base.paste(layer, (int(shake_xy[0]), int(shake_xy[1])), layer)
    return base


# ------------------------------------------------------------------ paper inserts

def newspaper_insert(lt, dur):
    k = lt / dur
    base = dark_bg('desk').copy()
    paste_rot(base, A.newspaper_tex(1), 540, 780, 1.45 + 0.15 * k, -4 + 2 * k)
    paste_rot(base, A.newspaper_tex(3, 'BOY, 11, MISSING', 'Last seen near Maple Street'), 760, 1420, 1.0, 9)
    paste_rot(base, A.poster_tex(4, 'NOAH K.'), 230, 1400, 1.2, -12)
    fx = 540 + 260 * math.sin(lt * 1.3)
    fy = 760 + 220 * math.cos(lt * 0.9)
    return apply_light(base, fx, fy, 760, 0.1)


def list_insert(lt, dur, circle):
    base = dark_bg('desk').copy()
    tex = A.list_tex(round(circle, 2))
    k = min(1.0, lt / 0.9)
    ease = k * k * (3 - 2 * k)
    scale = 1.55 + 0.5 * ease + 0.04 * lt
    # pan down the list towards the last name (ends above the caption area)
    cy = 760 - 760 * ease
    paste_rot(base, tex, 540, cy + 400, scale, 2)
    return apply_light(base, 540, 820, 780, 0.12)


def clock_insert(sec, lt):
    base = dark_bg('wall').copy()
    tex = A.clock_tex(11, 58, sec)
    s = 2.6 + 0.12 * lt
    paste_rot(base, tex, 540, 780, s, 0)
    return apply_light(base, 600, 700, 900, 0.18, (0.85, 0.9, 1.1))
