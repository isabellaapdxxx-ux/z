"""Procedural textures, characters and props (all original, code-generated)."""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from engine3d import Box, Quad, T, S, RX, RY, RZ, rad, box

FONT_BLACK = '/usr/share/fonts/opentype/inter/Inter-Black.otf'
FONT_BOLD = '/usr/share/fonts/opentype/inter/Inter-Bold.otf'
FONT_SEMI = '/usr/share/fonts/opentype/inter/Inter-SemiBold.otf'
FONT_SERIF = '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'
FONT_MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'
FONT_EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'


@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(path, size)


def _down(im, k=4):
    return im.resize((im.width // k, im.height // k), Image.LANCZOS)


# ------------------------------------------------------------------ faces

@lru_cache(maxsize=None)
def face_tex(expr):
    K = 4
    s = 256 * K
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    blk = (20, 20, 24, 255)
    wht = (250, 250, 250, 255)

    def E(x0, y0, x1, y1, **kw):
        d.ellipse([x0 * K, y0 * K, x1 * K, y1 * K], **kw)

    def L(pts, w, col=blk):
        d.line([(x * K, y * K) for x, y in pts], fill=col, width=w * K, joint='curve')

    if expr in ('smile', 'happy', 'neutral', 'cop', 'worried', 'whisper', 'relief'):
        E(78, 82, 104, 128, fill=blk)
        E(152, 82, 178, 128, fill=blk)
        E(84, 88, 92, 98, fill=wht)
        E(158, 88, 166, 98, fill=wht)
        if expr in ('smile', 'happy', 'relief'):
            d.arc([84 * K, 120 * K, 172 * K, 180 * K], 20, 160, fill=blk, width=8 * K)
        elif expr == 'neutral':
            L([(100, 160), (156, 160)], 7)
        elif expr == 'cop':
            L([(70, 72), (108, 78)], 8)
            L([(186, 72), (148, 78)], 8)
            L([(104, 160), (152, 158)], 7)
        elif expr == 'worried':
            L([(72, 70), (106, 60)], 7)
            L([(184, 70), (150, 60)], 7)
            d.arc([96 * K, 150 * K, 160 * K, 190 * K], 200, 340, fill=blk, width=7 * K)
        elif expr == 'whisper':
            L([(72, 70), (106, 60)], 7)
            L([(184, 70), (150, 60)], 7)
            E(118, 150, 138, 172, fill=blk)
    elif expr == 'scared':
        E(66, 70, 114, 132, fill=wht, outline=blk, width=6 * K)
        E(142, 70, 190, 132, fill=wht, outline=blk, width=6 * K)
        E(82, 90, 98, 108, fill=blk)
        E(158, 90, 174, 108, fill=blk)
        L([(64, 58), (110, 46)], 7)
        L([(192, 58), (146, 46)], 7)
        E(108, 146, 148, 196, fill=blk)
        E(116, 172, 140, 192, fill=(150, 40, 50, 255))
        # sweat drop
        d.polygon([(206 * K, 70 * K), (198 * K, 92 * K), (214 * K, 92 * K)], fill=(140, 200, 255, 255))
        E(198, 86, 214, 102, fill=(140, 200, 255, 255))
    elif expr == 'closed':
        d.arc([74 * K, 92 * K, 110 * K, 118 * K], 200, 340, fill=blk, width=7 * K)
        d.arc([146 * K, 92 * K, 182 * K, 118 * K], 200, 340, fill=blk, width=7 * K)
        L([(110, 162), (146, 162)], 6)
    elif expr in ('creepy', 'blank', 'angry', 'stare'):
        # heavy-lidded dark eyes with tiny pale pupils
        if expr == 'angry':
            L([(62, 66), (112, 90)], 10)
            L([(194, 66), (144, 90)], 10)
        E(74, 88, 112, 120, fill=blk)
        E(144, 88, 182, 120, fill=blk)
        d.rectangle([70 * K, 82 * K, 116 * K, 98 * K], fill=(0, 0, 0, 0))
        d.rectangle([140 * K, 82 * K, 186 * K, 98 * K], fill=(0, 0, 0, 0))
        L([(70, 98), (116, 98)], 6)
        L([(140, 98), (186, 98)], 6)
        pup = (235, 235, 235, 255) if expr != 'stare' else (255, 60, 60, 255)
        E(90, 104, 98, 112, fill=pup)
        E(160, 104, 168, 112, fill=pup)
        # dark circles
        d.arc([72 * K, 112 * K, 114 * K, 132 * K], 20, 160, fill=(60, 50, 70, 200), width=4 * K)
        d.arc([142 * K, 112 * K, 184 * K, 132 * K], 20, 160, fill=(60, 50, 70, 200), width=4 * K)
        if expr == 'creepy':
            d.arc([60 * K, 120 * K, 196 * K, 176 * K], 15, 165, fill=blk, width=7 * K)
            L([(66, 140), (60, 132)], 5)
            L([(190, 140), (196, 132)], 5)
        elif expr == 'angry':
            d.rectangle([92 * K, 156 * K, 164 * K, 178 * K], fill=blk)
            for x in range(100, 164, 12):
                L([(x, 158), (x, 176)], 2, (230, 230, 230, 255))
        else:
            L([(100, 164), (156, 164)], 6)
    return _down(im, K)


def flat_tex(w, h, color, text=None, fnt=None, tcol=(255, 255, 255)):
    im = Image.new('RGBA', (w, h), color)
    if text:
        d = ImageDraw.Draw(im)
        d.text((w / 2, h / 2), text, font=fnt, fill=tcol, anchor='mm')
    return im


@lru_cache(maxsize=None)
def shirt_tex(kind):
    K = 2
    s = 256 * K
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if kind == 'boy':
        # simple white lightning bolt logo
        pts = [(140, 50), (95, 135), (128, 135), (108, 210), (165, 115), (132, 115), (152, 50)]
        d.polygon([(x * K, y * K) for x, y in pts], fill=(255, 220, 60, 255))
    elif kind == 'hoodie':
        d.rectangle([60 * K, 160 * K, 196 * K, 220 * K], outline=(10, 10, 12, 255), width=5 * K)
        d.line([(110 * K, 0), (104 * K, 80 * K)], fill=(200, 200, 200, 255), width=5 * K)
        d.line([(146 * K, 0), (152 * K, 80 * K)], fill=(200, 200, 200, 255), width=5 * K)
    elif kind == 'cop':
        d.polygon([(178 * K, 50 * K), (210 * K, 50 * K), (214 * K, 80 * K), (194 * K, 98 * K), (174 * K, 80 * K)],
                  fill=(240, 200, 70, 255), outline=(150, 110, 20, 255))
        d.rectangle([40 * K, 60 * K, 100 * K, 100 * K], outline=(20, 30, 60, 255), width=4 * K)
        d.line([(128 * K, 0), (128 * K, 256 * K)], fill=(20, 30, 60, 255), width=4 * K)
        for y in (60, 120, 180, 230):
            d.ellipse([(122) * K, y * K, 134 * K, (y + 12) * K], fill=(230, 230, 230, 255))
        d.rectangle([0, 236 * K, 256 * K, 256 * K], fill=(20, 20, 20, 255))
    elif kind == 'blanket':
        for i in range(0, 256, 32):
            d.line([(i * K, 0), (i * K, 256 * K)], fill=(160, 70, 30, 120), width=6 * K)
            d.line([(0, i * K), (256 * K, i * K)], fill=(160, 70, 30, 120), width=6 * K)
    return _down(im, K)


# ------------------------------------------------------------------ characters

class Look:
    def __init__(self, skin, shirt, pants, hair, shirt_decal=None, hair_style='short',
                 hat=None, hood=None, height=1.0, arm_color=None):
        self.skin, self.shirt, self.pants, self.hair = skin, shirt, pants, hair
        self.shirt_decal = shirt_decal
        self.hair_style = hair_style
        self.hat = hat
        self.hood = hood
        self.height = height
        self.arm_color = arm_color


BOY = Look(skin=(236, 196, 140), shirt=(40, 110, 220), pants=(75, 82, 105), hair=(110, 70, 40),
           shirt_decal='boy', hair_style='spiky')
COUSIN = Look(skin=(214, 190, 170), shirt=(32, 32, 38), pants=(70, 75, 62), hair=(25, 22, 22),
              shirt_decal='hoodie', hair_style='messy', hood=(28, 28, 34), height=1.12,
              arm_color=(32, 32, 38))
COP = Look(skin=(190, 140, 100), shirt=(28, 45, 95), pants=(22, 30, 60), hair=(30, 25, 20),
           shirt_decal='cop', hat=(22, 30, 60), arm_color=(28, 45, 95))
COP2 = Look(skin=(240, 205, 165), shirt=(28, 45, 95), pants=(22, 30, 60), hair=(150, 100, 50),
            shirt_decal='cop', hat=(22, 30, 60), arm_color=(28, 45, 95))


def character(look, pos, yaw=0.0, expr='smile', arm_l=0, arm_r=0, roll_l=0, roll_r=0,
              leg_l=0, leg_r=0, head_yaw=0, head_pitch=0, lean=0, bob=0.0, layer=1,
              bias=0.0, tied=False, blanket=False, outline=0.82):
    """Blocky character, feet at pos. Angles in degrees. Front faces +z (after yaw)."""
    sc = look.height
    root = T(*pos) @ RY(rad(yaw)) @ S(sc) @ T(0, bob, 0)
    hip = root @ T(0, 2, 0) @ RX(-rad(lean))
    parts = []
    kw = dict(layer=layer, bias=bias, outline=outline)
    # legs
    for side, a in ((-1, leg_l), (1, leg_r)):
        M = root @ T(0.5 * side, 2, 0) @ RX(-rad(a)) @ T(0, -1, 0) @ S(0.98, 2, 1)
        parts.append(Box(M, look.pants, **kw))
    # torso
    dec = {'front': shirt_tex(look.shirt_decal)} if look.shirt_decal else {}
    parts.append(Box(hip @ T(0, 1, 0) @ S(2, 2, 1), look.shirt, decals=dec, **kw))
    # arms
    for side, a, r in ((-1, arm_l, roll_l), (1, arm_r, roll_r)):
        Ms = hip @ T(1.5 * side, 1.85, 0) @ RZ(rad(r) * side) @ RX(-rad(a))
        parts.append(Box(Ms @ T(0, -0.55, 0) @ S(1, 1.1, 1), look.arm_color or look.shirt, **kw))
        parts.append(Box(Ms @ T(0, -1.5, 0) @ S(0.98, 0.9, 0.98), look.skin, **kw))
    # head
    neck = hip @ T(0, 2, 0) @ RY(rad(head_yaw)) @ RX(-rad(head_pitch))
    parts.append(Box(neck @ T(0, 0.62, 0) @ S(1.25, 1.2, 1.2), look.skin,
                     decals={'front': face_tex(expr)}, **kw))
    hc = look.hair
    if look.hat:
        parts.append(Box(neck @ T(0, 1.3, 0) @ S(1.4, 0.4, 1.4), look.hat, **kw))
        parts.append(Box(neck @ T(0, 1.14, 0.62) @ S(1.4, 0.08, 0.6), (15, 15, 20), **kw))
        parts.append(Box(neck @ T(0, 1.35, 0.71) @ S(0.3, 0.25, 0.02), (230, 190, 60), **kw))
    elif look.hair_style == 'spiky':
        parts.append(Box(neck @ T(0, 1.3, -0.05) @ S(1.35, 0.25, 1.32), hc, **kw))
        parts.append(Box(neck @ T(0, 0.95, -0.56) @ S(1.35, 0.7, 0.22), hc, **kw))
        parts.append(Box(neck @ T(-0.3, 1.45, 0.15) @ RZ(rad(20)) @ S(0.35, 0.3, 0.6), hc, **kw))
        parts.append(Box(neck @ T(0.25, 1.48, 0.1) @ RZ(rad(-15)) @ S(0.4, 0.35, 0.6), hc, **kw))
        parts.append(Box(neck @ T(0, 1.15, 0.6) @ S(1.3, 0.2, 0.08), hc, **kw))
    else:
        parts.append(Box(neck @ T(0, 1.3, -0.04) @ S(1.36, 0.28, 1.34), hc, **kw))
        parts.append(Box(neck @ T(0, 0.85, -0.57) @ S(1.36, 0.9, 0.22), hc, **kw))
        parts.append(Box(neck @ T(0.1, 1.16, 0.6) @ RZ(rad(-8)) @ S(1.2, 0.3, 0.1), hc, **kw))
    if look.hood:
        parts.append(Box(neck @ T(0, 0.55, -0.78) @ S(1.6, 1.3, 0.3), look.hood, **kw))
    if tied:
        rope = (150, 110, 60)
        parts.append(Box(hip @ T(0, 0.75, -0.05) @ S(2.12, 0.22, 1.25), rope, **kw))
        parts.append(Box(hip @ T(0, 1.4, -0.05) @ S(2.12, 0.22, 1.25), rope, **kw))
    if blanket:
        parts.append(Box(hip @ T(0, 1.05, -0.05) @ S(2.5, 2.4, 1.4), (190, 90, 40),
                         decals={'front': shirt_tex('blanket')}, **kw))
    return parts


def walk(phase, amp=35):
    s = math.sin(phase)
    return dict(leg_l=amp * s, leg_r=-amp * s, arm_l=-amp * s * 0.9, arm_r=amp * s * 0.9,
                bob=abs(math.cos(phase)) * 0.12)


# ------------------------------------------------------------------ textures

@lru_cache(maxsize=None)
def phone_screen(state, extra=''):
    w, h = 300, 600
    im = Image.new('RGBA', (w, h), (12, 14, 20, 255))
    d = ImageDraw.Draw(im)
    if state == 'ended':
        d.rectangle([0, 0, w, h], fill=(10, 10, 16, 255))
        d.text((w / 2, 150), '911', font=font(FONT_BLACK, 110), fill=(255, 255, 255), anchor='mm')
        d.text((w / 2, 245), 'call ended', font=font(FONT_BOLD, 40), fill=(255, 70, 70), anchor='mm')
        d.text((w / 2, 300), '00:47', font=font(FONT_SEMI, 34), fill=(170, 170, 180), anchor='mm')
        d.ellipse([w / 2 - 50, 440, w / 2 + 50, 540], fill=(220, 40, 40))
        d.rounded_rectangle([w / 2 - 28, 482, w / 2 + 28, 498], 6, fill=(255, 255, 255))
    elif state == 'calling':
        d.text((w / 2, 150), '911', font=font(FONT_BLACK, 110), fill=(255, 255, 255), anchor='mm')
        d.text((w / 2, 245), 'calling...', font=font(FONT_BOLD, 40), fill=(120, 230, 140), anchor='mm')
        d.ellipse([w / 2 - 50, 440, w / 2 + 50, 540], fill=(220, 40, 40))
    elif state == 'glow':
        d.rectangle([0, 0, w, h], fill=(200, 220, 255, 255))
    elif state == 'off':
        d.rectangle([0, 0, w, h], fill=(8, 8, 10, 255))
    elif state == 'cracked':
        d.rectangle([0, 0, w, h], fill=(8, 8, 10, 255))
        rnd = random.Random(4)
        for _ in range(14):
            x, y = 150 + rnd.uniform(-20, 20), 300 + rnd.uniform(-20, 20)
            a = rnd.uniform(0, 6.28)
            L = rnd.uniform(150, 400)
            d.line([(x, y), (x + L * math.cos(a), y + L * math.sin(a))], fill=(200, 200, 210), width=3)
    return im


@lru_cache(maxsize=None)
def portrait(seed):
    """Small blocky avatar portrait for missing posters."""
    rnd = random.Random(seed)
    im = Image.new('RGBA', (200, 200), (rnd.randint(150, 200), rnd.randint(150, 200), rnd.randint(160, 210), 255))
    d = ImageDraw.Draw(im)
    skin = rnd.choice([(236, 196, 140), (200, 150, 110), (150, 105, 75), (245, 215, 180)])
    shirt = rnd.choice([(200, 50, 50), (50, 150, 60), (230, 170, 30), (90, 60, 170), (40, 120, 200)])
    hair = rnd.choice([(40, 30, 20), (120, 80, 40), (220, 190, 90), (20, 20, 20), (150, 60, 30)])
    d.rectangle([40, 150, 160, 200], fill=shirt)
    d.rectangle([60, 50, 140, 145], fill=skin)
    d.rectangle([56, 38, 144, 62], fill=hair)
    d.rectangle([80, 85, 90, 100], fill=(20, 20, 20))
    d.rectangle([110, 85, 120, 100], fill=(20, 20, 20))
    d.arc([82, 100, 118, 128], 20, 160, fill=(20, 20, 20), width=4)
    return im


@lru_cache(maxsize=None)
def poster_tex(seed, name):
    w, h = 300, 400
    rnd = random.Random(seed)
    base = (238 - rnd.randint(0, 25), 232 - rnd.randint(0, 25), 210 - rnd.randint(0, 30))
    im = Image.new('RGBA', (w, h), base + (255,))
    d = ImageDraw.Draw(im)
    d.text((w / 2, 48), 'MISSING', font=font(FONT_BLACK, 64), fill=(200, 20, 20), anchor='mm')
    im.paste(portrait(seed), (50, 90))
    d.rectangle([50, 90, 250, 290], outline=(30, 30, 30), width=4)
    d.text((w / 2, 320), name, font=font(FONT_BLACK, 36), fill=(25, 25, 25), anchor='mm')
    d.text((w / 2, 358), 'HAVE YOU SEEN ME?', font=font(FONT_BOLD, 22), fill=(60, 60, 60), anchor='mm')
    for _ in range(6):  # wear
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        d.ellipse([x, y, x + rnd.randint(10, 40), y + rnd.randint(10, 40)], fill=base[:2] + (base[2] - 30, 90))
    d.rectangle([0, 0, w - 1, h - 1], outline=(150, 140, 120), width=3)
    return im


@lru_cache(maxsize=None)
def newspaper_tex(seed=1, headline='LOCAL KIDS VANISH', sub='Police have no leads after third disappearance'):
    w, h = 600, 760
    rnd = random.Random(seed)
    im = Image.new('RGBA', (w, h), (226, 220, 200, 255))
    d = ImageDraw.Draw(im)
    d.text((w / 2, 40), 'THE MAPLE GAZETTE', font=font(FONT_SERIF, 34), fill=(30, 30, 30), anchor='mm')
    d.line([(20, 70), (w - 20, 70)], fill=(30, 30, 30), width=3)
    d.text((w / 2, 125), headline, font=font(FONT_SERIF, 52), fill=(15, 15, 15), anchor='mm')
    d.text((w / 2, 180), sub, font=font(FONT_SERIF, 22), fill=(60, 60, 60), anchor='mm')
    im.paste(portrait(seed + 10).resize((220, 220)), (30, 220))
    im.paste(portrait(seed + 11).resize((220, 220)), (350, 220))
    for col in range(3):
        x0 = 30 + col * 190
        for i in range(14):
            y = 470 + i * 19
            d.line([(x0, y), (x0 + rnd.randint(120, 170), y)], fill=(110, 110, 110), width=6)
    return im


NAMES = ['Ethan R.', 'Maya L.', 'Jordan P.', 'Chloe S.', 'Noah K.', 'Ava M.']


@lru_cache(maxsize=None)
def list_tex(circle=1.0):
    w, h = 600, 800
    im = Image.new('RGBA', (w, h), (245, 242, 228, 255))
    d = ImageDraw.Draw(im)
    for i in range(16):
        y = 120 + i * 44
        d.line([(0, y), (w, y)], fill=(150, 180, 220), width=2)
    d.line([(70, 0), (70, h)], fill=(220, 120, 120), width=3)
    f = font(FONT_MONO, 40)
    d.text((100, 60), 'THE LIST', font=font(FONT_MONO, 52), fill=(30, 30, 30))
    for i, n in enumerate(NAMES):
        y = 150 + i * 88
        d.text((100, y), f'{i + 1}. {n}', font=f, fill=(30, 30, 40))
        d.line([(92, y + 24), (100 + d.textlength(f'{i + 1}. {n}', font=f) + 10, y + 20)],
               fill=(200, 20, 20), width=6)
    y = 150 + len(NAMES) * 88
    d.text((100, y), f'{len(NAMES) + 1}. TYLER', font=font(FONT_MONO, 48), fill=(20, 20, 30))
    if circle > 0:
        # partial red circle (animated by circle 0..1)
        d.arc([80, y - 22, 420, y + 80], -200, -200 + 360 * circle, fill=(220, 20, 20), width=8)
    return im


@lru_cache(maxsize=None)
def sign_tex(text, bg=(230, 200, 40), fg=(20, 20, 20), w=360, h=160, size=64):
    im = Image.new('RGBA', (w, h), bg + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([6, 6, w - 7, h - 7], outline=fg, width=6)
    d.text((w / 2, h / 2), text, font=font(FONT_BLACK, size), fill=fg, anchor='mm')
    return im


def clock_tex(hour, minute, second):
    s = 300
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([4, 4, s - 4, s - 4], fill=(235, 230, 215), outline=(40, 40, 40), width=14)
    c = s / 2
    for i in range(12):
        a = i / 12 * 2 * math.pi
        d.line([(c + 110 * math.sin(a), c - 110 * math.cos(a)), (c + 128 * math.sin(a), c - 128 * math.cos(a))],
               fill=(30, 30, 30), width=8 if i % 3 == 0 else 4)

    def hand(frac, L, wdt, col):
        a = frac * 2 * math.pi
        d.line([(c, c), (c + L * math.sin(a), c - L * math.cos(a))], fill=col, width=wdt)
    hand(((hour % 12) + minute / 60) / 12, 70, 12, (20, 20, 20))
    hand((minute + second / 60) / 60, 105, 8, (20, 20, 20))
    hand(second / 60, 115, 3, (210, 20, 20))
    d.ellipse([c - 9, c - 9, c + 9, c + 9], fill=(20, 20, 20))
    return im


@lru_cache(maxsize=None)
def tv_tex(frame):
    """Colorful blocky 'game' on the TV (frame index for animation)."""
    w, h = 320, 180
    im = Image.new('RGBA', (w, h), (110, 190, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 120, w, h], fill=(70, 180, 70))
    off = (frame * 6) % 80
    for i in range(-1, 6):
        x = i * 80 - off
        d.rectangle([x, 80, x + 30, 120], fill=(150, 100, 60))
        d.rectangle([x - 10, 50, x + 40, 85], fill=(40, 140, 50))
    d.rectangle([140, 90, 160, 120], fill=(230, 60, 60))
    d.rectangle([142, 74, 158, 90], fill=(240, 200, 140))
    d.text((10, 6), 'SCORE 0' + str(1200 + frame * 10)[-4:], font=font(FONT_BLACK, 18), fill=(255, 255, 255))
    return im


@lru_cache(maxsize=None)
def pizza_tex():
    im = Image.new('RGBA', (256, 256), (210, 170, 110, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([20, 20, 236, 236], fill=(220, 150, 60))
    d.ellipse([34, 34, 222, 222], fill=(230, 80, 40))
    d.ellipse([44, 44, 212, 212], fill=(250, 210, 90))
    rnd = random.Random(2)
    for _ in range(9):
        x, y = rnd.randint(70, 180), rnd.randint(70, 180)
        d.ellipse([x, y, x + 24, y + 24], fill=(170, 40, 40))
    d.line([(128, 20), (128, 236)], fill=(200, 140, 60), width=3)
    d.line([(20, 128), (236, 128)], fill=(200, 140, 60), width=3)
    return im


@lru_cache(maxsize=None)
def window_tex(night=False):
    w, h = 200, 240
    top, bot = ((20, 25, 60), (10, 10, 25)) if night else ((120, 190, 255), (200, 230, 255))
    im = Image.new('RGBA', (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        k = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - k) + bot[i] * k) for i in range(3)) + (255,))
    if night:
        d.ellipse([130, 30, 170, 70], fill=(230, 230, 210))
    d.rectangle([0, 0, w - 1, h - 1], outline=(240, 240, 240), width=14)
    d.line([(w / 2, 0), (w / 2, h)], fill=(240, 240, 240), width=10)
    d.line([(0, h / 2), (w, h / 2)], fill=(240, 240, 240), width=10)
    return im


@lru_cache(maxsize=None)
def police_door_tex():
    im = Image.new('RGBA', (400, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((200, 100), 'POLICE', font=font(FONT_BLACK, 84), fill=(20, 40, 110), anchor='mm')
    return im


@lru_cache(maxsize=None)
def sky_bg(w, h, top, bottom):
    a = np.linspace(0, 1, h)[:, None]
    t = np.array(top, float)[None, :]
    b = np.array(bottom, float)[None, :]
    col = t * (1 - a) + b * a
    arr = np.repeat(col[:, None, :], w, axis=1).astype(np.uint8)
    return Image.fromarray(arr, 'RGB')


# ------------------------------------------------------------------ environment builders

def tiled_floor(x0, x1, z0, z1, y, tile, colors, layer=0, outline=0.85, jitter=0.0, seed=0):
    rnd = random.Random(seed)
    out = []
    nx = max(1, int(round((x1 - x0) / tile)))
    nz = max(1, int(round((z1 - z0) / tile)))
    tx, tz = (x1 - x0) / nx, (z1 - z0) / nz
    for i in range(nx):
        for j in range(nz):
            c = colors[(i + j) % len(colors)]
            if jitter:
                k = 1 + rnd.uniform(-jitter, jitter)
                c = tuple(min(255, v * k) for v in c)
            out.append(box((x0 + (i + .5) * tx, y - 0.1, z0 + (j + .5) * tz), (tx, 0.2, tz), c,
                           layer=layer, outline=outline, hide=('bottom',)))
    return out


def tiled_wall(axis, fixed, a0, a1, y0, y1, tile, colors, normal_sign, layer=0, outline=0.85, jitter=0.0,
               seed=0, thick=0.2, skip=None):
    """Wall made of tiles. axis='x' -> wall spans x (plane z=fixed); axis='z' -> spans z (plane x=fixed)."""
    rnd = random.Random(seed)
    out = []
    na = max(1, int(round((a1 - a0) / tile)))
    ny = max(1, int(round((y1 - y0) / tile)))
    ta, ty = (a1 - a0) / na, (y1 - y0) / ny
    for i in range(na):
        for j in range(ny):
            a = a0 + (i + .5) * ta
            y = y0 + (j + .5) * ty
            if skip and skip(a, y):
                continue
            c = colors[(i + j) % len(colors)]
            if jitter:
                k = 1 + rnd.uniform(-jitter, jitter)
                c = tuple(min(255, v * k) for v in c)
            if axis == 'x':
                out.append(box((a, y, fixed - normal_sign * thick / 2), (ta, ty, thick), c, layer=layer,
                               outline=outline))
            else:
                out.append(box((fixed - normal_sign * thick / 2, y, a), (thick, ty, ta), c, layer=layer,
                               outline=outline))
    return out


def chair(pos, yaw=0, color=(110, 75, 45), layer=1, bias=-0.3):
    root = T(*pos) @ RY(rad(yaw))
    kw = dict(layer=layer, bias=bias, outline=0.8)
    out = [Box(root @ T(0, 1.4, 0.2) @ S(2.4, 0.2, 2.4), color, **kw),
           Box(root @ T(0, 3.0, -1.0) @ S(2.4, 3.2, 0.25), color, **kw)]
    for x in (-1.05, 1.05):
        for z in (-0.85, 1.25):
            out.append(Box(root @ T(x, 0.65, z) @ S(0.25, 1.3, 0.25), color, **kw))
    return out


def phone_obj(pos, yaw=0, screen='ended', tilt=0.0, layer=1, bias=0.5, emissive=1.4, scale=1.0):
    """Phone lying on the floor (screen up)."""
    root = T(*pos) @ RY(rad(yaw)) @ RX(rad(tilt)) @ S(scale)
    body = Box(root @ T(0, 0.06, 0) @ S(0.7, 0.12, 1.4), (20, 20, 24), layer=layer, bias=bias)
    # screen quad slightly above
    hw, hd = 0.31, 0.64
    corners = [(-hw, 0.125, -hd), (hw, 0.125, -hd), (hw, 0.125, hd), (-hw, 0.125, hd)]
    P = [(root @ np.array([x, y, z, 1.0]))[:3] for x, y, z in corners]
    q = Quad(P, phone_screen(screen), layer=layer, bias=bias + 0.01, lit=False)
    return [body, q]
