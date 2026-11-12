"""Original blocky characters, pixel faces and procedural textures (all generated in code)."""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine3d import Box, T, S, RX, RY, RZ, rad

FONT_BLACK = '/usr/share/fonts/opentype/inter/Inter-Black.otf'
FONT_BOLD = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'
FONT_SEMI = '/usr/share/fonts/opentype/inter/Inter-SemiBold.otf'
FONT_MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
FONT_EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'


@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, size)


# ============================================================== pixel faces
# 12x12 pixel-art faces, scaled up with NEAREST for a crisp blocky look.
_FACES = {
    'happy': [
        "............",
        "............",
        "............",
        "...##..##...",
        "...#w..#w...",
        "...##..##...",
        "............",
        "..#......#..",
        "...######...",
        "............",
        "............",
        "............"],
    'neutral': [
        "............",
        "............",
        "............",
        "...##..##...",
        "...#w..#w...",
        "...##..##...",
        "............",
        "............",
        "....####....",
        "............",
        "............",
        "............"],
    'worried': [
        "............",
        "............",
        "..##....##..",
        "...##..##...",
        "...#w..#w...",
        "...##..##...",
        "............",
        "....####....",
        "...#....#...",
        "............",
        "............",
        "............"],
    'scared': [
        "............",
        "..#......#..",
        "...#....#...",
        "..www..www..",
        "..w#w..w#w..",
        "..www..www.b",
        "...........b",
        "....####....",
        "....#rr#....",
        "....####....",
        "............",
        "............"],
    'whisper': [
        "............",
        "............",
        "..##....##..",
        "...##..##...",
        "...#w..#w...",
        "...##..##...",
        "............",
        ".....##.....",
        ".....##.....",
        "............",
        "............",
        "............"],
    'closed': [
        "............",
        "............",
        "............",
        "............",
        "...##..##...",
        "............",
        "............",
        "............",
        ".....##.....",
        "............",
        "............",
        "............"],
    'relief': [
        "............",
        "............",
        "............",
        "............",
        "..##....##..",
        "...#....#...",
        "............",
        "...#....#...",
        "....####....",
        "............",
        "............",
        "............"],
    # Mr. Gray: flat black eyes, never blinking, one long thin smile
    'blank': [
        "............",
        "............",
        "............",
        "...##..##...",
        "...##..##...",
        "............",
        "............",
        ".#........#.",
        "..########..",
        "............",
        "............",
        "............"],
    'stare': [
        "............",
        "............",
        "..###..###..",
        "..###..###..",
        "..#w#..#w#..",
        "..###..###..",
        "............",
        "#..........#",
        ".##########.",
        "..#.#.#.#.#.",
        "............",
        "............"],
    'cop': [
        "............",
        "............",
        "..###..###..",
        "............",
        "...##..##...",
        "...##..##...",
        "............",
        "............",
        "...######...",
        "............",
        "............",
        "............"],
}
_PAL = {'#': (18, 18, 22, 255), 'w': (245, 245, 245, 255), 'r': (140, 30, 40, 255), 'b': (120, 190, 255, 255)}


@lru_cache(maxsize=None)
def face_tex(expr):
    rows = _FACES[expr]
    im = Image.new('RGBA', (12, 12), (0, 0, 0, 0))
    px = im.load()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in _PAL:
                px[x, y] = _PAL[ch]
    return im.resize((240, 240), Image.NEAREST)


@lru_cache(maxsize=None)
def shirt_tex(kind):
    s = 240
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == 'timmy':
        # yellow star on a blue shirt
        cx, cy, r1, r2 = 120, 110, 52, 22
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = r1 if i % 2 == 0 else r2
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d.polygon(pts, fill=(255, 210, 60, 255))
    elif kind == 'suit':
        # white shirt V, dark tie, lapels
        d.polygon([(80, 0), (160, 0), (120, 120)], fill=(225, 225, 225, 255))
        d.polygon([(110, 10), (130, 10), (136, 130), (120, 150), (104, 130)], fill=(30, 30, 36, 255))
        d.line([(80, 0), (120, 130)], fill=(70, 70, 76, 255), width=6)
        d.line([(160, 0), (120, 130)], fill=(70, 70, 76, 255), width=6)
        for y in (150, 195):
            d.rectangle([116, y, 124, y + 8], fill=(20, 20, 24, 255))
    elif kind == 'cop':
        d.polygon([(170, 40), (200, 40), (204, 70), (185, 86), (166, 70)], fill=(240, 200, 70, 255))
        d.line([(120, 0), (120, 240)], fill=(15, 22, 50, 255), width=5)
        for y in (50, 110, 170):
            d.rectangle([115, y, 125, y + 10], fill=(220, 220, 220, 255))
        d.rectangle([0, 220, 240, 240], fill=(15, 15, 15, 255))
        d.rectangle([110, 220, 130, 240], fill=(200, 180, 60, 255))
    elif kind == 'blanket':
        for i in range(0, 240, 30):
            d.line([(i, 0), (i, 240)], fill=(120, 40, 20, 140), width=7)
            d.line([(0, i), (240, i)], fill=(120, 40, 20, 140), width=7)
    return im


# ============================================================== characters

class Look:
    def __init__(self, skin, shirt, pants, hair, decal=None, hair_style='short', hat=None, height=1.0,
                 arm=None, shoes=(30, 30, 34)):
        self.skin, self.shirt, self.pants, self.hair = skin, shirt, pants, hair
        self.decal, self.hair_style, self.hat, self.height = decal, hair_style, hat, height
        self.arm = arm or shirt
        self.shoes = shoes


TIMMY = Look(skin=(240, 200, 150), shirt=(45, 115, 225), pants=(60, 66, 90), hair=(105, 65, 35),
             decal='timmy', hair_style='spiky', height=0.82, shoes=(200, 60, 50))
GRAY = Look(skin=(196, 196, 190), shirt=(112, 114, 120), pants=(92, 94, 100), hair=(70, 70, 72),
            decal='suit', hair_style='slick', height=1.22, shoes=(15, 15, 18))
COP = Look(skin=(185, 135, 95), shirt=(30, 48, 105), pants=(20, 28, 60), hair=(30, 25, 20),
           decal='cop', hat=(20, 28, 60))
COP2 = Look(skin=(236, 200, 160), shirt=(30, 48, 105), pants=(20, 28, 60), hair=(150, 100, 50),
            decal='cop', hat=(20, 28, 60))


def character(look, pos, yaw=0.0, expr='happy', arm_l=0, arm_r=0, roll_l=0, roll_r=0, leg_l=0, leg_r=0,
              head_yaw=0, head_pitch=0, head_roll=0, lean=0, bob=0.0, sit=False, tied=False, blanket=False,
              layer=1, bias=0.0, outline=0.8, color_mul=1.0):
    """Blocky character, feet at pos (or seat at pos[1]+... when sit). Front faces +z after yaw (deg)."""
    sc = look.height
    root = T(*pos) @ RY(rad(yaw)) @ S(sc) @ T(0, bob, 0)
    kw = dict(layer=layer, bias=bias, outline=outline)

    def C(c):
        return tuple(min(255, v * color_mul) for v in c)

    parts = []
    hip = root @ T(0, 2, 0) @ RX(-rad(lean))
    # legs (upper+shoe)
    for side, a in ((-1, leg_l), (1, leg_r)):
        if sit:
            M = root @ T(0.5 * side, 2, 0) @ RX(-rad(90))
            parts.append(Box(M @ T(0, -0.6, 0) @ S(0.98, 1.2, 1), C(look.pants), **kw))
            M2 = root @ T(0.5 * side, 2, 1.2) @ RX(-rad(a))
            parts.append(Box(M2 @ T(0, -0.9, 0) @ S(0.96, 1.8, 0.96), C(look.pants), **kw))
            parts.append(Box(M2 @ T(0, -1.9, 0.1) @ S(1.0, 0.3, 1.15), C(look.shoes), **kw))
        else:
            M = root @ T(0.5 * side, 2, 0) @ RX(-rad(a))
            parts.append(Box(M @ T(0, -0.9, 0) @ S(0.98, 1.8, 1), C(look.pants), **kw))
            parts.append(Box(M @ T(0, -1.88, 0.06) @ S(1.0, 0.26, 1.12), C(look.shoes), **kw))
    dec = {'front': shirt_tex(look.decal)} if look.decal else {}
    parts.append(Box(hip @ T(0, 1, 0) @ S(2, 2, 1), C(look.shirt), decals=dec, **kw))
    for side, a, r in ((-1, arm_l, roll_l), (1, arm_r, roll_r)):
        Ms = hip @ T(1.5 * side, 1.85, 0) @ RZ(rad(r) * side) @ RX(-rad(a))
        parts.append(Box(Ms @ T(0, -0.6, 0) @ S(1, 1.2, 1), C(look.arm), **kw))
        parts.append(Box(Ms @ T(0, -1.5, 0) @ S(0.98, 0.7, 0.98), C(look.skin), **kw))
    neck = hip @ T(0, 2, 0) @ RY(rad(head_yaw)) @ RX(-rad(head_pitch)) @ RZ(rad(head_roll))
    parts.append(Box(neck @ T(0, 0.65, 0) @ S(1.25, 1.25, 1.25), C(look.skin), decals={'front': face_tex(expr)}, **kw))
    hc = C(look.hair)
    if look.hat:
        parts.append(Box(neck @ T(0, 1.4, 0) @ S(1.38, 0.38, 1.38), C(look.hat), **kw))
        parts.append(Box(neck @ T(0, 1.24, 0.66) @ S(1.38, 0.08, 0.55), (12, 12, 16), **kw))
        parts.append(Box(neck @ T(0, 1.42, 0.7) @ S(0.28, 0.24, 0.02), (235, 195, 60), **kw))
    elif look.hair_style == 'spiky':
        parts.append(Box(neck @ T(0, 1.34, -0.04) @ S(1.33, 0.22, 1.33), hc, **kw))
        parts.append(Box(neck @ T(0, 0.95, -0.6) @ S(1.33, 0.7, 0.2), hc, **kw))
        parts.append(Box(neck @ T(-0.3, 1.5, 0.12) @ RZ(rad(20)) @ S(0.34, 0.3, 0.6), hc, **kw))
        parts.append(Box(neck @ T(0.25, 1.52, 0.05) @ RZ(rad(-15)) @ S(0.4, 0.34, 0.6), hc, **kw))
        parts.append(Box(neck @ T(0, 1.2, 0.62) @ S(1.3, 0.16, 0.06), hc, **kw))
    else:  # slicked-back
        parts.append(Box(neck @ T(0, 1.33, -0.08) @ S(1.31, 0.18, 1.36), hc, **kw))
        parts.append(Box(neck @ T(0, 0.9, -0.63) @ S(1.31, 0.8, 0.12), hc, **kw))
    if tied:
        rope = (165, 125, 70)
        parts.append(Box(hip @ T(0, 0.65, -0.05) @ S(2.1, 0.22, 1.2), rope, **kw))
        parts.append(Box(hip @ T(0, 1.35, -0.05) @ S(2.1, 0.22, 1.2), rope, **kw))
    if blanket:
        parts.append(Box(hip @ T(0, 1.0, 0) @ S(2.6, 2.3, 1.45), (185, 80, 35), decals={'front': shirt_tex('blanket')},
                         **kw))
        parts.append(Box(hip @ T(0, 2.1, -0.1) @ S(2.4, 0.5, 1.3), (185, 80, 35), **kw))
    return parts


def walk(phase, amp=32):
    s = math.sin(phase)
    return dict(leg_l=amp * s, leg_r=-amp * s, arm_l=-amp * s * 0.9, arm_r=amp * s * 0.9,
                bob=abs(math.cos(phase)) * 0.14)


def run(phase):
    d = walk(phase, 55)
    d['lean'] = 14
    d['bob'] = abs(math.cos(phase)) * 0.3
    return d


# ============================================================== textures

@lru_cache(maxsize=None)
def portrait(seed):
    """Small pixel portrait of a missing kid (original, random colors)."""
    r = random.Random(seed)
    im = Image.new('RGB', (12, 12), (r.randint(150, 200),) * 3)
    d = ImageDraw.Draw(im)
    skin = r.choice([(240, 200, 150), (200, 150, 110), (150, 105, 70), (230, 185, 140)])
    hair = r.choice([(30, 20, 15), (110, 70, 30), (200, 160, 70), (60, 40, 30), (150, 50, 20)])
    shirt = r.choice([(200, 60, 60), (60, 140, 70), (230, 180, 50), (130, 70, 170), (60, 60, 70)])
    d.rectangle([0, 9, 11, 11], fill=shirt)
    d.rectangle([3, 2, 8, 8], fill=skin)
    d.rectangle([3, 1, 8, 2], fill=hair)
    if r.random() < 0.5:
        d.rectangle([2, 2, 2, 7], fill=hair)
        d.rectangle([9, 2, 9, 7], fill=hair)
    d.point([(4, 4), (7, 4)], fill=(20, 20, 20))
    d.line([(5, 7), (6, 7)], fill=(60, 30, 30))
    return im.resize((96, 96), Image.NEAREST)


@lru_cache(maxsize=None)
def poster_tex(seed):
    r = random.Random(seed * 7 + 3)
    w, h = 150, 200
    paper = (222 - r.randint(0, 30), 214 - r.randint(0, 30), 190 - r.randint(0, 40), 255)
    im = Image.new('RGBA', (w, h), paper)
    d = ImageDraw.Draw(im)
    d.text((w / 2, 22), 'MISSING', font=font(FONT_BLACK, 30), fill=(170, 20, 20), anchor='mm')
    im.paste(portrait(seed), (27, 42))
    for i in range(3):
        y = 150 + i * 14
        d.rectangle([20, y, 20 + r.randint(60, 110), y + 6], fill=(60, 55, 50))
    # tape + worn edges
    d.rectangle([60, 0, 90, 8], fill=(240, 235, 200, 200))
    for _ in range(40):
        x, y = r.randint(0, w - 1), r.randint(0, h - 1)
        d.point((x, y), fill=(120, 110, 90, 255))
    return im


@lru_cache(maxsize=None)
def concrete_tex(seed=0, base=(70, 72, 70), size=128):
    rs = np.random.default_rng(seed)
    n = rs.normal(0, 1, (size // 8, size // 8))
    n = np.kron(n, np.ones((8, 8)))
    arr = np.clip(np.array(base)[None, None, :] + n[:, :, None] * 8, 0, 255).astype(np.uint8)
    im = Image.fromarray(arr).convert('RGBA')
    return im


@lru_cache(maxsize=None)
def sky_bg(w, h, kind):
    y = np.linspace(0, 1, h)[:, None, None]
    if kind == 'day':
        top, bot = np.array([70, 88, 120]), np.array([150, 160, 170])
    elif kind == 'dusk':
        top, bot = np.array([30, 36, 70]), np.array([110, 90, 110])
    else:  # night
        top, bot = np.array([4, 6, 18]), np.array([22, 30, 60])
    arr = top * (1 - y) + bot * y
    arr = np.broadcast_to(arr, (h, w, 3)).astype(np.float32).copy()
    im = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(im)
    r = random.Random(5)
    if kind == 'night':
        for _ in range(int(w * h / 9000)):
            x, yy = r.randint(0, w), r.randint(0, int(h * 0.55))
            s = r.choice([1, 1, 2])
            c = r.randint(140, 230)
            d.rectangle([x, yy, x + s, yy + s], fill=(c, c, c + 10 if c < 245 else 255))
        # blocky moon
        mx, my, ms = int(w * 0.74), int(h * 0.12), int(w * 0.1)
        glow = Image.new('L', (w, h), 0)
        ImageDraw.Draw(glow).ellipse([mx - ms * 2, my - ms * 2, mx + ms * 2, my + ms * 2], fill=60)
        glow = glow.filter(ImageFilter.GaussianBlur(ms * 0.8))
        im = Image.composite(Image.new('RGB', (w, h), (120, 140, 190)), im, glow)
        d = ImageDraw.Draw(im)
        d.rectangle([mx - ms // 2, my - ms // 2, mx + ms // 2, my + ms // 2], fill=(220, 225, 200))
        d.rectangle([mx - ms // 2 + ms // 5, my - ms // 6, mx - ms // 2 + ms // 3, my], fill=(190, 195, 175))
        d.rectangle([mx + ms // 8, my + ms // 8, mx + ms // 3, my + ms // 3], fill=(195, 198, 178))
    else:
        # flat blocky clouds
        for _ in range(9):
            cx, cy = r.randint(-100, w), r.randint(int(h * 0.05), int(h * 0.4))
            cw, ch = r.randint(w // 6, w // 3), r.randint(h // 40, h // 22)
            g = 160 if kind == 'day' else 80
            d.rectangle([cx, cy, cx + cw, cy + ch], fill=(g, g + 5, g + 15))
            d.rectangle([cx + cw // 5, cy - ch // 2, cx + cw * 3 // 4, cy], fill=(g, g + 5, g + 15))
    return im


@lru_cache(maxsize=None)
def window_tex(lit, color=(255, 220, 140), cross=True):
    w, h = 120, 120
    if lit:
        im = Image.new('RGBA', (w, h), color + (255,))
    else:
        im = Image.new('RGBA', (w, h), (25, 30, 45, 255))
    d = ImageDraw.Draw(im)
    if cross:
        d.rectangle([56, 0, 64, h], fill=(235, 235, 230, 255))
        d.rectangle([0, 56, w, 64], fill=(235, 235, 230, 255))
    d.rectangle([0, 0, w - 1, h - 1], outline=(235, 235, 230, 255), width=8)
    return im


@lru_cache(maxsize=None)
def basement_window_tex(on):
    w, h = 160, 80
    if on:
        im = Image.new('RGBA', (w, h), (190, 230, 120, 255))
    else:
        im = Image.new('RGBA', (w, h), (12, 14, 18, 255))
    d = ImageDraw.Draw(im)
    for x in range(20, w, 30):
        d.rectangle([x, 0, x + 5, h], fill=(40, 40, 40, 255))
    d.rectangle([0, 0, w - 1, h - 1], outline=(50, 50, 50, 255), width=6)
    return im


@lru_cache(maxsize=None)
def door_tex(color=(120, 60, 40), knob=(220, 190, 80)):
    w, h = 100, 200
    im = Image.new('RGBA', (w, h), color + (255,))
    d = ImageDraw.Draw(im)
    dk = tuple(int(c * 0.7) for c in color)
    d.rectangle([14, 16, 86, 90], outline=dk, width=6)
    d.rectangle([14, 110, 86, 184], outline=dk, width=6)
    d.rectangle([76, 98, 88, 110], fill=knob)
    return im


@lru_cache(maxsize=None)
def house_number_tex(text):
    im = Image.new('RGBA', (160, 70), (25, 25, 28, 255))
    d = ImageDraw.Draw(im)
    d.text((80, 35), text, font=font(FONT_BLACK, 44), fill=(220, 200, 140), anchor='mm')
    return im


@lru_cache(maxsize=None)
def sold_sign_tex():
    im = Image.new('RGBA', (200, 120), (200, 30, 30, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, 193, 113], outline=(255, 255, 255), width=5)
    d.text((100, 60), 'SOLD', font=font(FONT_BLACK, 62), fill=(255, 255, 255), anchor='mm')
    return im


@lru_cache(maxsize=None)
def police_door_tex():
    im = Image.new('RGBA', (200, 100), (235, 235, 240, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 60, 200, 74], fill=(20, 40, 110))
    d.text((100, 34), 'POLICE', font=font(FONT_BLACK, 40), fill=(20, 40, 110), anchor='mm')
    return im
