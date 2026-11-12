"""Shot list: maps every time t in [0,120) to a rendered frame + post settings."""
import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from engine3d import Renderer, Camera, Light, Quad, Box, box, T, S, RX, RY, RZ, rad, disc
import assets as A
import sets as SE
import inserts as I

W, H = 1080, 1920
SS = 2
R = Renderer(W, H, ss=SS)

CX, CY, CZ = SE.CHAIR_POS

_TIMING = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'build', 'vo_timing.json')


def word_t(lid, word, default):
    """Start time of a spoken word (so visual hits stay synced with the voice/bass hits)."""
    try:
        for L in json.load(open(_TIMING))['lines']:
            if L['id'] == lid:
                for w in L['words']:
                    if word.lower() in w['w'].lower():
                        return w['t0']
    except (OSError, ValueError, KeyError):
        pass
    return default


T_LOCKED = word_t('s6', 'LOCKED', 23.35)
T_MISSING = word_t('d3', 'MISSING', 39.33)
T_KILLER = word_t('d7', 'KILLER', 51.37)


# ------------------------------------------------------------------ helpers

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def lerp(a, b, k):
    return a + (b - a) * k


def lv(a, b, k):
    return tuple(lerp(x, y, k) for x, y in zip(a, b))


def decay(lt, k=6.0):
    return math.exp(-max(0.0, lt) * k)


def punch(lt, amt=0.15, dur=0.22):
    """zoom punch: starts at 1+amt and eases to 1."""
    if lt < 0:
        return 1.0
    return 1.0 + amt * (1 - ease(lt / dur))


def render(sc, cam):
    img = R.render(sc, cam)
    return img.reduce(SS) if SS > 1 else img


def F(img, **kw):
    d = dict(img=img, zoom=1.0, dx=0.0, dy=0.0, rot=0.0, shake=0.0, vig=0.55, grain=5.0, bloom=0.0,
             tint=None, flash=0.0, chroma=0, glitch=0.0, bright=1.0, contrast=1.0, hud=None, blur=0.0,
             lids=None, slats=None, rb=0.0)
    d.update(kw)
    return d


def walk_path(p0, p1, t, t0, t1, step=0.6):
    k = clamp((t - t0) / (t1 - t0))
    pos = lv(p0, p1, k)
    yaw = math.degrees(math.atan2(p1[0] - p0[0], p1[2] - p0[2]))
    moving = 0 < k < 1
    phase = 2 * math.pi * (t - t0) / (2 * step) if moving else 0.0
    return pos, yaw, A.walk(phase) if moving else {}


def stair_y(x):
    """Height of the basement stair top surface at x (stairs rise right -> left)."""
    if x > 7.1:
        return 0.0
    i = int(round((6.5 - x) / 1.15))
    i = max(0, min(11, i))
    return (i + 1) * 0.8 + 0.11


def police_lights(t, pos_r, pos_b, inten=3.0, rate=3.0):
    on = math.sin(t * rate * 2 * math.pi) > 0
    return [Light(pos_r, (255, 30, 30), inten if on else inten * 0.08, 12.0),
            Light(pos_b, (40, 80, 255), inten * 0.08 if on else inten, 12.0)], on


# ------------------------------------------------------------------ basement

def bscene(phone='ended', phone_glow=1.0, stair=1.0, bulb=1.0, extra=(), sec=10, amb=0.07, chair=True):
    sc = SE.basement(stair, bulb, phone_glow if phone == 'ended' else 0.0, extra, amb)
    if chair:
        sc.add(A.chair(SE.CHAIR_POS))
        sc.floor_shadows.append((disc((CX, CZ + 0.2), 1.9), 110))
    if phone:
        sc.add(A.phone_obj(SE.PHONE_POS, -12, phone, scale=1.7))
    x, y, z = SE.CLOCK_POS
    sc.add(Quad([(x - 1, y + 1, z), (x + 1, y + 1, z), (x + 1, y - 1, z), (x - 1, y - 1, z)],
                A.clock_tex(11, 58, sec % 60), bias=2))
    # soft fill on the boy's face (moonlight)
    sc.add(Light((-1.5, 6.0, 3.0), (120, 140, 200), 0.45, 6.0))
    return sc


def boy_tied(t, expr='scared', struggle=0.0, head_yaw=0.0, head_pitch=0.0, tied=True, arms=None):
    j = struggle * math.sin(t * 23) + struggle * 0.5 * math.sin(t * 37 + 1)
    kw = dict(arm_l=-30, arm_r=-30) if tied else dict(arm_l=10, arm_r=10)
    if arms:
        kw.update(arms)
    return A.character(A.BOY, (CX + 0.06 * j, 0, CZ), 4 * j, expr, leg_l=90 + 4 * j, leg_r=90 - 4 * j,
                       head_yaw=head_yaw + 9 * j, head_pitch=head_pitch, lean=2 * j, tied=tied, **kw)


def hook_state(t):
    """Basement at 'hook time' t in [0,3]: cousin walking toward the boy."""
    sc = bscene(sec=int(t) + 2)
    sc.add(boy_tied(t, 'scared', 0.25 + 0.2 * decay(t, 3)))
    pos, yaw, wk = walk_path((4.7, 0, -9.4), (3.4, 0, -6.4), t, -0.2, 3.4, 0.6)
    cou = A.character(A.COUSIN, pos, yaw, 'creepy', **wk)
    sc.add(cou)
    sc.add(Light((pos[0] - 1.5, 6.5, pos[2] + 3.5), (150, 170, 230), 0.9, 4.0))
    sc.cast.append((cou, SE.STAIR_BULB, 175))
    return sc


HOOK_CAM0 = ((0.0, 6.6, 9.4), (0.3, 2.7, -3.2))
HOOK_CAM1 = ((0.3, 6.1, 7.4), (0.5, 2.9, -3.4))


def hook_cam(t):
    k = ease(t / 3.0)
    return Camera(lv(HOOK_CAM0[0], HOOK_CAM1[0], k), lv(HOOK_CAM0[1], HOOK_CAM1[1], k), fov=58)


def sh_hook_wide(t, lt):
    img = render(hook_state(lt), hook_cam(lt))
    return F(img, zoom=punch(lt, 0.14, 0.3), shake=34 * decay(lt, 5) + 4, flash=((200, 20, 20), 0.22 * decay(lt, 12)),
             bloom=0.6, vig=0.7, chroma=int(10 * decay(lt, 8)))


def sh_hook_face(t, lt):
    tt = 3.0 + lt
    sc = bscene(sec=5)
    sc.add(boy_tied(tt, 'scared', 0.6))
    cou = A.character(A.COUSIN, (3.0, 0, -5.9), -40, 'creepy')
    sc.add(cou)
    sc.cast.append((cou, SE.STAIR_BULB, 175))
    cam = Camera((CX + 0.3, 4.9, CZ + 3.4), (CX, 4.55, CZ), fov=50)
    img = render(sc, cam)
    return F(img, zoom=punch(lt, 0.35, 0.18) * (1 + 0.06 * lt), shake=16 * decay(lt, 3) + 6, vig=0.75, bloom=0.4,
             tint=((255, 120, 120), 0.15 * ease(lt / 0.9)), chroma=int(8 * decay(lt, 7)))


def sh_hook_cousin(t, lt):
    sc = bscene(sec=6)
    sc.add(boy_tied(t, 'scared', 0.3))
    sc.add(A.character(A.COUSIN, (3.4, 0, -6.2), -20, 'creepy', head_pitch=-12, head_yaw=5))
    sc.add(Light((4.0, 1.2, -3.0), (255, 40, 40), 1.4, 4.0))
    sc.add(Light((3.8, 2.0, -3.6), (170, 200, 255), 0.8, 4.0))
    cam = Camera((4.5, 2.4, -2.3), (3.4, 5.35, -6.2), fov=52, roll=rad(-6))
    img = render(sc, cam)
    return F(img, zoom=1.0 + 0.12 * lt, shake=5, vig=0.75, bloom=0.4, contrast=1.1)


def sh_rewind(t, lt):
    d = 1.25
    if lt < d - 0.2:
        ht = clamp(3.0 - lt / (d - 0.2) * 3.0, 0, 3)
        img = render(hook_state(ht), hook_cam(ht))
        g = 0.75
    else:
        img = sh_ext_day(6.05, 0.0)['img']
        g = 0.9
    return F(img, glitch=g, hud='rewind', chroma=6, bright=1.15, contrast=0.9, vig=0.4, grain=14,
             tint=((180, 200, 255), 0.25))


# ------------------------------------------------------------------ 1. normal day

def sh_ext_day(t, lt):
    sc = SE.exterior(False)
    bz = lerp(22, 7.5, clamp(lt / 3.95))
    phase = 2 * math.pi * lt / 1.1
    sc.add(A.character(A.BOY, (2.0, 0, bz), 180, 'smile', **A.walk(phase)))
    sc.floor_shadows.append((disc((2.0, bz), 1.4), 70))
    wave = 25 * math.sin(lt * 9)
    sc.add(A.character(A.COUSIN, (2.0, 0, -3.2), 0, 'smile', arm_r=165, roll_r=10 + wave))
    sc.floor_shadows.append((disc((2.0, -3.2), 1.5), 70))
    k = ease(lt / 3.95)
    cam = Camera(lv((9.0, 6.0, 33.0), (7.0, 5.5, 17.5), k), lv((1.5, 4.5, 8.0), (2.0, 4.6, -2.0), k), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.25, grain=3, bloom=0.2, contrast=1.05)


def sh_living_hello(t, lt):
    sc = SE.room('living', [Light((8, 6.2, -8), (255, 220, 160), 1.0, 8)], ambient=0.45, sun=0.4)
    pos, yaw, wk = walk_path((9.0, 0, 4.4), (2.0, 0, 5.0), t, 10.0, 12.2, 0.5)
    sc.add(A.character(A.BOY, pos, yaw if wk else -80, 'smile', **wk))
    sc.floor_shadows.append((disc((pos[0], pos[2]), 1.4), 60))
    waving = 12.3 < t < 14.6
    cw = dict(arm_r=165, roll_r=10 + 25 * math.sin(t * 10)) if waving else dict(arm_r=10)
    sc.add(A.character(A.COUSIN, (-1.8, 0, 4.6), 40 if t > 11.5 else 15, 'smile', head_yaw=10, **cw))
    sc.floor_shadows.append((disc((-1.8, 4.6), 1.5), 60))
    k = ease(lt / 5.2)
    cam = Camera(lv((1.0, 6.8, 16.5), (0.2, 6.2, 14.5), k), lv((0.5, 3.8, 3.0), (0.0, 4.1, 3.5), k), fov=60)
    img = render(sc, cam)
    return F(img, vig=0.3, grain=3, bloom=0.15)


def sh_couch(t, lt):
    tvc = (130, 180, 255) if int(t * 4) % 2 else (255, 180, 120)
    sc = SE.room('living', [Light((0, 5, -8.0), tvc, 1.6, 9), Light((8, 6.2, -8), (255, 220, 160), 0.6, 8)],
                 ambient=0.32, sun=0.25)
    sc.add(Quad([(-3.5, 6.9, -9.08), (3.5, 6.9, -9.08), (3.5, 3.1, -9.08), (-3.5, 3.1, -9.08)],
                A.tv_tex(int(t * 8) % 40), lit=False, bias=2))
    bob = 0.06 * math.sin(t * 7)
    sc.add(A.character(A.BOY, (2.2, 0.5, 2.0), 180, 'happy', leg_l=90, leg_r=90, arm_l=60, arm_r=60, bob=bob))
    laugh = 'happy' if int(t * 1.2) % 2 == 0 else 'smile'
    hy = -25 if t > 17.3 else 0
    sc.add(A.character(A.COUSIN, (-2.4, 0.26, 2.0), 180, laugh, leg_l=90, leg_r=90, arm_l=60, arm_r=60,
                       head_yaw=hy))
    for x in (2.2, -2.6):  # controllers
        sc.add(box((x, 3.0, -0.25), (1.4, 0.35, 0.6), (40, 40, 45), bias=1))
    k = ease(lt / 4.1)
    cam = Camera(lv((2.6, 6.3, -8.0), (1.5, 5.9, -7.0), k), (0.0, 4.0, 2.0), fov=60)
    img = render(sc, cam)
    return F(img, vig=0.35, grain=3, bloom=0.3)


def hall_scene(night=False, flash=None):
    if not night:
        lights = [Light((0, 8.5, -6), (255, 230, 190), 1.2, 7), Light((0, 8.5, -18), (255, 230, 190), 1.0, 7),
                  Light((0, 7.0, -27), (190, 210, 255), 0.6, 5)]
        sc = SE.room('hall', lights, ambient=0.28, sun=0.15, fog=0.02, fogc=(20, 18, 16))
    else:
        sc = SE.room('hall', [Light((0, 8.0, -4), (90, 110, 170), 0.35, 8), Light((2.0, 6.0, -14), (110, 130, 200), 0.9, 8)], ambient=0.05, sun=0.0, fog=0.05,
                     fogc=(2, 2, 5))
    return sc


def sh_hallway(t, lt):
    sc = hall_scene()
    sc.add(SE.locked_door((0, 0, -29.85)))
    k = ease(lt / 5.7)
    hit = t - T_LOCKED
    cam = Camera(lv((0.6, 5.6, 3.0), (0.2, 4.9, -19.5), k), (0.0, 4.4, -30), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.6 + 0.2 * k, grain=4, zoom=1.0 + (0.25 * ease(hit / 0.25) if hit > 0 else 0),
             shake=(10 * decay(hit, 4) if hit > 0 else 0), tint=((255, 90, 90), 0.25 * decay(hit, 2)) if hit > 0 else None)


def sh_boy_asks(t, lt):
    sc = hall_scene()
    sc.add(SE.locked_door((0, 0, -29.85)))
    sc.add(A.character(A.BOY, (0.4, 0, -25.0), 15, 'worried', head_yaw=-30, head_pitch=8))
    sc.floor_shadows.append((disc((0.4, -25.0), 1.4), 80))
    cam = Camera((2.2, 5.4, -16.5), (0.2, 4.3, -26.0), fov=52)
    img = render(sc, cam)
    return F(img, vig=0.6, grain=4, zoom=1 + 0.04 * lt)


def sh_cousin_snap(t, lt):
    hit = t - 26.55
    flick = 0.35 if (hit > 0 and int(hit * 12) % 3 == 0 and hit < 0.8) else 1.0
    sc = SE.room('hall', [Light((0, 8.5, -18), (255, 230, 190), 1.0 * flick, 7),
                          Light((0, 3.0, -23.0), (255, 60, 60), 0.6 if hit > 0 else 0.0, 5)],
                 ambient=0.22 * flick, sun=0.1, fog=0.02, fogc=(20, 18, 16))
    expr = 'smile' if hit < 0 else 'blank'
    sc.add(A.character(A.COUSIN, (0.5, 0, -20.0), 180, expr, head_pitch=-6 if hit > 0 else 0))
    cam = Camera((-0.5, 5.0, -25.8), (0.5, 5.0, -20.0), fov=50, roll=rad(5 if hit > 0 else 0))
    img = render(sc, cam)
    return F(img, vig=0.65, grain=5, zoom=(punch(hit, 0.18, 0.2) if hit > 0 else 1.0) * (1 + 0.035 * lt),
             shake=(20 * decay(hit, 5) + 2 if hit > 0 else 0),
             tint=((255, 70, 70), 0.3 * decay(hit, 1.0)) if hit > 0 else None, contrast=1.08)


# ------------------------------------------------------------------ 2. discovery

def sh_keys(t, lt):
    cx = lerp(-14, 2, clamp((t - 30.4) / 3.0))
    car = [Light((cx, 4.5, -11), (255, 245, 210), 1.6 * clamp(1 - (t - 30.4) / 3.2), 7)]
    sc = SE.room('living', [Light((8, 6.2, -8), (255, 200, 140), 1.6, 9), Light((3, 6, 4), (120, 140, 200), 0.6, 8)] + car, ambient=0.1, sun=0.06,
                 fogc=(5, 5, 10))
    glint = 2.5 if int(t * 3) % 2 == 0 else 0.6
    for k in range(3):
        sc.add(Box(T(-1.6 + k * 0.35, 1.25, -2.4 + 0.1 * k) @ RY(rad(30 * k)) @ S(0.25, 0.08, 0.8),
                   (230, 190, 60), emissive=glint * 0.5, bias=2))
    sc.add(box((-1.3, 1.22, -2.0), (0.6, 0.05, 0.6), (200, 200, 210), bias=2))
    sc.add(A.character(A.BOY, (3.5, 0, 0.5), -130, 'worried', head_pitch=20))
    k = ease(lt / 4.4)
    cam = Camera(lv((6.5, 7.0, 7.5), (-0.6, 3.4, 1.0), k), lv((0.5, 2.5, -2.0), (-1.3, 1.3, -2.3), k), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.7, grain=6, bloom=0.5)


def sh_hall_night(t, lt):
    sc = hall_scene(True)
    open_a = 80 * ease((t - 36.5) / 1.4)
    sc.add(SE.locked_door((0, 0, -29.85), open_angle=open_a, padlock=t < 36.25))
    bz = lerp(-20.5, -25.2, clamp((t - 34.4) / 1.6))
    walking = t < 36.0
    wk = A.walk(2 * math.pi * (t - 34.4) / 1.24) if walking else {}
    sc.add(A.character(A.BOY, (0.3, 0, bz), 180, 'worried', **{**wk, 'arm_r': 70}))
    sc.add(Light((0.9, 3.6, bz - 1.2), (235, 240, 255), 4.0, 16, spot_dir=(0, -0.08, -1), spot_cos=0.9, spot_soft=0.06))
    cam = Camera((1.8, 6.2, bz + 6.5), (0.0, 4.2, -30), fov=54)
    img = render(sc, cam)
    return F(img, vig=0.75, grain=8, bloom=0.4, shake=3)


def locked_scene(beam_yaw=0.0, beam_pitch=0.08, src=(0.8, 3.6, 5.5), boy=None, extra=()):
    d = (math.sin(beam_yaw), beam_pitch, -math.cos(beam_yaw))
    lights = [Light(src, (235, 240, 255), 5.0, 18, spot_dir=d, spot_cos=0.9, spot_soft=0.05),
              Light((0, 7.0, 7.5), (60, 70, 110), 0.5, 10)] + list(extra)
    sc = SE.room('locked', lights, ambient=0.05, sun=0.0, fog=0.03, fogc=(3, 3, 6))
    if boy:
        sc.add(boy)
    return sc


def sh_posters(t, lt):
    yaw = rad(lerp(-38, 30, ease(lt / 3.3)))
    boy = A.character(A.BOY, (0.0, 0, 5.0), 180, 'scared', arm_r=80, roll_r=-5)
    sc = locked_scene(yaw, 0.12, boy=boy)
    hit = t - T_MISSING
    k = ease(lt / 3.3)
    cam = Camera(lv((2.4, 6.4, 12.0), (1.6, 5.6, 9.5), k), lv((-2.5, 4.8, -8.0), (2.0, 4.8, -8.0), k), fov=58)
    img = render(sc, cam)
    return F(img, vig=0.7, grain=7, bloom=0.4, zoom=(punch(hit, 0.12, 0.25) if hit > 0 else 1.0),
             shake=(14 * decay(hit, 4) if hit > 0 else 2))


def sh_newspaper(t, lt):
    img = I.newspaper_insert(lt, 3.6)
    return F(img, vig=0.6, grain=8, shake=3)


def sh_desk(t, lt):
    sc = locked_scene(rad(28), -0.35, src=(2.5, 6.2, 0.5))
    k = ease(lt / 2.7)
    cam = Camera(lv((1.0, 7.0, 1.5), (3.2, 6.0, -2.6), k), lv((3.0, 2.5, -5.0), (3.3, 2.5, -5.3), k), fov=54)
    img = render(sc, cam)
    return F(img, vig=0.7, grain=7, bloom=0.3)


def sh_list(t, lt):
    circle = ease((t - 47.9) / 0.7)
    img = I.list_insert(lt, 2.4, circle)
    hit = t - 47.6
    return F(img, vig=0.65, grain=7, zoom=punch(hit, 0.2, 0.25), shake=12 * decay(hit, 3) + 2,
             flash=((255, 40, 40), 0.35 * decay(hit, 6)))


def sh_boy_face(t, lt):
    boy = A.character(A.BOY, (0.0, 0, 2.0), 0, 'scared', arm_r=60)
    sc = locked_scene(rad(180), 0.0, src=(0.6, 3.0, 2.8),
                      extra=[Light((0.5, 2.4, 3.6), (220, 230, 255), 1.6, 3.5)])
    sc.add(boy)
    hit = t - T_KILLER
    cam = Camera((0.35, 4.9, 6.0), (0.0, 4.55, 2.0), fov=50)
    img = render(sc, cam)
    return F(img, vig=0.75, grain=7, bloom=0.3, zoom=(1 + 0.05 * lt) * (punch(hit, 0.22, 0.2) if hit > 0 else 1),
             shake=(22 * decay(hit, 4) + 3 if hit > 0 else 3),
             tint=((255, 60, 60), 0.3 * decay(hit, 1.5)) if hit > 0 else None)


def sh_front_door(t, lt):
    sweep = clamp((t - 53.0) / 1.6)
    head = lerp(0, -55, ease((t - 52.9) / 0.5))
    boy = A.character(A.BOY, (0.0, 0, 2.0), 0, 'scared', arm_r=40, head_yaw=head)
    car = Light((lerp(-9, 9, sweep), 4.0, 8.0), (255, 245, 210), 2.5 * math.sin(math.pi * sweep), 12)
    sc = locked_scene(rad(170), -0.1, src=(0.6, 3.2, 2.8), extra=[car])
    sc.add(boy)
    hit = t - 54.35
    cam = Camera((2.6, 5.4, 9.0), (0.0, 4.0, 2.0), fov=54)
    img = render(sc, cam)
    return F(img, vig=0.75, grain=7, bloom=0.3, shake=(16 * decay(hit, 4) if hit > 0 else 2),
             zoom=(punch(hit, 0.1, 0.2) if hit > 0 else 1.0))


# ------------------------------------------------------------------ 3. the call

def closet_scene(phone_at=(-0.3, 1.8, 1.6), glow=1.0):
    lights = [Light(phone_at, (170, 200, 255), 2.4 * glow, 3.0), Light((0, 5, 6), (255, 200, 140), 0.25, 6)]
    return SE.room('closet', lights, ambient=0.03, sun=0.0, fog=0.04, fogc=(2, 2, 4))


def crouch_boy(t, expr, phone_ear=False):
    arms = dict(arm_l=70, arm_r=150, roll_r=-25) if phone_ear else dict(arm_l=75, arm_r=75)
    j = 0.04 * math.sin(t * 13)
    return A.character(A.BOY, (-0.2 + j, -1.5, 0.3), 0, expr, leg_l=85, leg_r=80, lean=12, **arms)


def sh_closet(t, lt):
    sc = closet_scene()
    sc.add(crouch_boy(t, 'scared'))
    k = ease(lt / 3.0)
    cam = Camera(lv((0.9, 3.4, 6.2), (0.5, 3.0, 4.6), k), (-0.2, 2.4, 0.3), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.75, grain=8, bloom=0.5, slats=0.25)


def sh_phone_ui(t, lt):
    presses = [(58.15, '9'), (58.53, '1'), (58.91, '1')]
    typed = ''.join(d for (tp, d) in presses if t >= tp)
    press = next((d for (tp, d) in presses if 0 <= t - tp < 0.16), None)
    if t < 59.25:
        img = I.phone_insert('dial', lt, typed, press)
    elif t < 60.9:
        img = I.phone_insert('calling', t - 59.25)
    else:
        img = I.phone_insert('connected', t - 60.9 + 1)
    return F(img, vig=0.6, grain=6, shake=5, bloom=0.3, zoom=1.0 + 0.03 * lt)


def sh_whisper(t, lt):
    sc = closet_scene(phone_at=(0.6, 4.0, 1.4))
    sc.add(crouch_boy(t, 'whisper', True))
    cam = Camera((0.9, 3.9, 4.6), (-0.25, 3.0, 0.3), fov=52)
    img = render(sc, cam)
    return F(img, vig=0.8, grain=8, bloom=0.4, zoom=1.0 + 0.04 * lt, shake=4, slats=0.2)


def bedroom_night(cpos, cyaw, expr, wk, backlight=1.0):
    lights = [Light((3, 7, -9), (255, 200, 140), 2.2 * backlight, 12), Light((0, 4, 9), (120, 140, 220), 1.0, 7)]
    sc = SE.room('living', lights, ambient=0.12, sun=0.06, fog=0.02, fogc=(3, 3, 6))
    sc.add(A.character(A.COUSIN, cpos, cyaw, expr, **wk))
    return sc


def sh_pov_slats(t, lt):
    pos, yaw, wk = walk_path((-1.0, 0, -8.5), (0.0, 0, 3.5), t, 67.0, 71.2, 0.62)
    sc = bedroom_night(pos, 0, 'blank', wk)
    cam = Camera((0, 4.2, 12.0), (0.0, 3.9, 0.0), fov=58)
    img = render(sc, cam)
    return F(img, vig=0.8, grain=9, slats=1.0, shake=3)


def sh_found_you(t, lt):
    sc = bedroom_night((0, 0, 6.5), 0, 'creepy', {}, backlight=2.0)
    sc.add(Light((0, 2.8, 10.8), (170, 200, 255), 1.4, 4.0))
    sc.cast = []
    cam = Camera((0, 4.4, 12.4), (0, 5.3, 6.0), fov=54)
    img = render(sc, cam)
    hit = t - 71.45
    slide = ease((t - 70.8) / 0.35)
    z = 1.0 + (0.08 * ease((t - 71.45) / 1.0) if hit > 0 else 0) + 0.5 * ease((t - 72.3) / 0.3)
    return F(img, vig=0.8, grain=9, slats=(1.0, slide), zoom=z * (punch(hit, 0.15, 0.2) if hit > 0 else 1),
             shake=(18 * decay(hit, 3) + 3 if hit > 0 else 3), flash=((255, 255, 255), 0.4 * decay(hit, 10)) if hit > 0 else 0)


def sh_black(t, lt):
    img = Image.new('RGB', (W, H), (0, 0, 0))
    beats = [73.1 + k * 0.85 for k in range(4)]
    pulse = max([decay(t - b, 5) if t >= b else 0 for b in beats] + [0])
    return F(img, vig=0.0, grain=4, tint=None, flash=((90, 0, 0), 0.25 * pulse))


# ------------------------------------------------------------------ 4. kidnapped

def sh_wake(t, lt):
    expr = 'closed' if t < 75.55 else 'scared'
    sc = bscene(sec=0)
    sc.add(boy_tied(t, expr, 0.15, head_pitch=-15 if t < 75.55 else 0))
    k = ease((t - 76.2) / 2.4)
    cam = Camera(lv((CX + 0.2, 4.8, CZ + 4.0), HOOK_CAM0[0], k), lv((CX, 4.5, CZ), HOOK_CAM0[1], k), fov=56)
    img = render(sc, cam)
    # eyelids: closed -> open -> blink -> open
    tl = t - 75.0
    if tl < 0.35:
        o = ease(tl / 0.35) * 0.5
    elif tl < 0.5:
        o = 0.5 - ease((tl - 0.35) / 0.15) * 0.5
    else:
        o = ease((tl - 0.5) / 0.5)
    return F(img, vig=0.7, grain=6, bloom=0.5, lids=o, blur=max(0.0, 10 * (1 - (t - 75.0) / 1.6)))


def s4_cousin_walk(t):
    return walk_path((5.4, 0, -8.8), (-0.6, 0, -2.6), t, 78.6, 81.6, 0.62)


def sh_cousin_returns(t, lt):
    sc = bscene(sec=int(t - 70))
    sc.add(boy_tied(t, 'scared', 0.35, head_yaw=20))
    pos, yaw, wk = s4_cousin_walk(t)
    cou = A.character(A.COUSIN, pos, yaw, 'creepy', **wk)
    sc.add(cou)
    sc.add(Light((pos[0] - 1.5, 6.5, pos[2] + 3.5), (150, 170, 230), 0.9, 4.0))
    sc.cast.append((cou, SE.STAIR_BULB, 175))
    k = ease(lt / 3.2)
    cam = Camera(lv(HOOK_CAM0[0], HOOK_CAM1[0], k), lv(HOOK_CAM0[1], HOOK_CAM1[1], k), fov=58)
    img = render(sc, cam)
    return F(img, vig=0.7, grain=6, bloom=0.5)


_rnd = random.Random(11)
PIECES = [((_rnd.uniform(-3, 3), _rnd.uniform(3, 7), _rnd.uniform(-3, 3)), _rnd.uniform(0.15, 0.4),
           _rnd.choice([(20, 20, 24), (40, 40, 50), (160, 190, 230)])) for _ in range(14)]


def sh_smash(t, lt):
    hit = t - 82.2
    smashed = hit >= 0
    sc = bscene(phone='cracked' if smashed else 'ended', sec=int(t - 70))
    sc.add(boy_tied(t, 'scared', 0.5))
    if t < 82.05:
        leg = 75 * ease((t - 81.8) / 0.25)
    elif t < 82.2:
        leg = lerp(75, 5, (t - 82.05) / 0.15)
    else:
        leg = 5
    sc.add(A.character(A.COUSIN, (-0.6, 0, -2.6), -30, 'angry', leg_r=leg, lean=-6 if leg > 30 else 3,
                       arm_l=-15, arm_r=20))
    if smashed:
        px, _, pz = SE.PHONE_POS
        for (vx, vy, vz), s, c in PIECES:
            tt = min(hit, 0.9)
            y = max(0.1, 0.2 + vy * tt - 9.8 * tt * tt)
            sc.add(Box(T(px + vx * tt, y, pz + vz * tt) @ RY(tt * 8) @ RX(tt * 6) @ S(s, s * 0.4, s), c, bias=1))
    cam = Camera((-3.6, 1.8, 3.6), (-1.2, 1.4, -1.0), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.7, grain=6, bloom=0.5, zoom=(punch(hit, 0.2, 0.25) if smashed else 1.0),
             shake=(40 * decay(hit, 5) + 2 if smashed else 2),
             flash=((255, 255, 255), 0.6 * decay(hit, 12)) if smashed else 0, chroma=int(12 * decay(hit, 6)) if smashed else 0)


def sh_nobody(t, lt):
    sc = bscene(phone='cracked', sec=int(t - 70), extra=[Light((-1.2, 0.8, 0.5), (255, 30, 30), 1.6, 4.5)])
    sc.add(boy_tied(t, 'scared', 0.3))
    sc.add(A.character(A.COUSIN, (-0.6, 0, -2.6), -20, 'blank', head_pitch=-14))
    cam = Camera((-1.3, 2.5, 1.7), (-0.6, 5.35, -2.6), fov=54, roll=rad(7))
    img = render(sc, cam)
    hit = t - 83.5
    return F(img, vig=0.8, grain=7, bloom=0.4, zoom=(1 + 0.05 * lt) * (punch(hit, 0.12, 0.2) if hit > 0 else 1),
             shake=(14 * decay(hit, 4) + 2 if hit > 0 else 2), tint=((255, 60, 60), 0.18))


def sh_clock_boy(t, lt):
    sc = bscene(phone='cracked', sec=int(t - 75), bulb=0.8)
    sc.add(boy_tied(t, 'scared', 0.55, head_yaw=15 * math.sin(t * 1.5)))
    sc.add(A.character(A.COUSIN, (-3.6, 0, -1.0), 60, 'blank'))
    k = ease(lt / 4.5)
    cam = Camera(lv((CX + 0.4, 5.4, CZ + 7.4), (CX + 0.5, 5.3, CZ + 6.2), k), (CX + 1.5, 5.6, -6.0), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.75, grain=7, bloom=0.4, shake=3)


def sh_upstairs(t, lt):
    door_shut = t >= 93.1
    stair = 0.0 if door_shut else 1.0
    if door_shut and t < 93.25:
        stair = 0.5
    sc = bscene(phone='cracked', sec=int(t - 75), stair=stair, bulb=0.7)
    sc.add(boy_tied(t, 'scared', 0.3, head_yaw=-35))
    k = clamp((t - 90.6) / 2.5)
    x = lerp(5.2, -4.2, k)
    if k < 1:
        cou = A.character(A.COUSIN, (x, stair_y(x), -10.4), -90, 'blank', **A.walk(2 * math.pi * (t - 90.6) / 0.9))
        sc.add([setattr(b, 'bias', 2.0) or b for b in cou])
        sc.add(Light((x + 1.0, stair_y(x) + 5.5, -8.0), (255, 190, 120), 1.3, 5.0))
    cam = Camera((2.5, 7.0, 10.5), (-0.5, 4.8, -7.0), fov=58)
    img = render(sc, cam)
    hit = t - 93.1
    return F(img, vig=0.75, grain=7, bloom=0.4, shake=(10 * decay(hit, 5) if hit > 0 else 2))


def sh_clock(t, lt):
    sec = 10 + int(t - 85.0)
    img = I.clock_insert(sec, lt)
    beat = (t - 86.0) % 0.95
    return F(img, vig=0.8, grain=7, zoom=1.0 + 0.012 * math.exp(-beat * 8), tint=((255, 80, 80), 0.08))


def sh_struggle(t, lt):
    on = clamp((t - 99.4) / 0.3)
    sc = bscene(phone='cracked', sec=int(t - 75), stair=on * 1.2, bulb=0.35)
    strug = 1.0 if (96.6 < t < 98.2 or 98.4 < t < 99.6) else 0.25
    look = -55 * ease((t - 99.5) / 0.4)
    expr = 'scared' if t > 99.4 else 'worried'
    sc.add(boy_tied(t, expr, strug, head_yaw=look))
    if t > 100.0:
        x = lerp(-2.0, 4.5, clamp((t - 100.0) / 1.0))
        cou = A.character(A.COUSIN, (x, stair_y(x), -10.4), 90, 'blank', **A.walk(2 * math.pi * (t - 100.0) / 1.0))
        sc.add([setattr(b, 'bias', 2.0) or b for b in cou])
    k = ease(lt / 4.5)
    cam = Camera(lv((CX - 0.5, 5.4, CZ + 6.5), (CX - 0.3, 5.1, CZ + 5.0), k), (CX - 0.4, 4.0, CZ - 1.0), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.8, grain=8, bloom=0.4, shake=(9 if strug > 0.5 else 2))


def sh_time_to_go(t, lt):
    sc = bscene(phone='cracked', sec=int(t - 75), stair=1.2, bulb=0.6)
    sc.add(boy_tied(t, 'scared', 0.3))
    pos, yaw, wk = walk_path((5.0, 0, -8.6), (2.9, 0, -5.6), t, 100.9, 102.4, 0.55)
    cou = A.character(A.COUSIN, pos, yaw, 'creepy', **wk)
    sc.add(cou)
    sc.cast.append((cou, SE.STAIR_BULB, 170))
    sc.add(Light((2.0, 2.0, -2.0), (170, 200, 255), 0.7, 4.0))
    k = ease(lt / 1.8)
    cam = Camera(lv((1.6, 4.2, -0.6), (1.9, 4.4, -1.6), k), (pos[0], 5.0, pos[2]), fov=52)
    img = render(sc, cam)
    return F(img, vig=0.8, grain=7, bloom=0.5, zoom=1.0 + 0.06 * lt)


def sh_gasp(t, lt):
    flick = []
    if t > 104.25:
        flick, _ = police_lights(t, (CX - 1, 5.5, CZ + 3), (CX + 1, 5.5, CZ + 3), 1.6, 3.0)
    sc = bscene(phone='cracked', sec=int(t - 75), stair=1.0, bulb=0.6, extra=flick)
    sc.add(boy_tied(t, 'scared', 0.6))
    cam = Camera((CX + 0.1, 4.75, CZ + 2.7), (CX, 4.6, CZ), fov=50)
    img = render(sc, cam)
    hb = (t - 101.0) % 0.5
    return F(img, vig=0.85, grain=8, bloom=0.4, zoom=1.0 + 0.35 * ease(lt / 1.8) + 0.02 * math.exp(-hb * 10),
             shake=5 + 10 * ease(lt / 1.8), tint=((255, 50, 50), 0.12 + 0.1 * math.exp(-hb * 8)))


# ------------------------------------------------------------------ 5. rescue

def cop_on_stairs(look, t, t0, t1, x0, x1, after=None):
    k = clamp((t - t0) / (t1 - t0))
    x = lerp(x0, x1, k)
    if k < 1:
        return A.character(look, (x, stair_y(x), -10.4), 90, 'cop', **{**A.walk(2 * math.pi * (t - t0) / 0.5), 'arm_r': 80}), (x, stair_y(x), -10.4)
    p0 = (x1, 0, -10.4)
    pos, yaw, wk = walk_path(p0, after, t, t1, t1 + 1.0, 0.3)
    return A.character(look, pos, yaw, 'cop', **{**wk, 'arm_r': 80}), pos


def sh_bust_in(t, lt):
    pl, red = police_lights(t, (-5.0, 9.0, -10.0), (-3.0, 9.0, -10.0), 4.0, 3.0)
    bash = t - 105.35
    extra = list(pl)
    if bash > 0:
        extra.append(Light((-6.0, 10.5, -10.5), (255, 250, 240), 3.0 * decay(bash, 2) + 0.8, 12))
    sc = bscene(phone='cracked', sec=int(t - 75), stair=0.5, bulb=0.6, extra=extra)
    sc.add(boy_tied(t, 'scared', 0.4))
    hands = 170 * ease((t - 106.6) / 0.4)
    cyaw = lerp(-30, -110, ease((t - 105.4) / 0.4))
    sc.add(A.character(A.COUSIN, (2.4, 0, -4.8), cyaw, 'angry', arm_l=hands, arm_r=hands))
    if t > 105.55:
        c1, p1 = cop_on_stairs(A.COP, t, 105.55, 106.9, -1.2, 6.8, (4.5, 0, -6.8))
        c2, p2 = cop_on_stairs(A.COP2, t, 105.9, 107.3, -3.5, 6.8, (6.0, 0, -8.6))
        for c in (c1, c2):
            sc.add([setattr(b, 'bias', 2.5) or b for b in c])
        for p in (p1, p2):
            sc.add(Light((p[0] + 0.8, p[1] + 3.6, p[2] + 1.0), (240, 245, 255), 3.0, 14, spot_dir=(-0.7, -0.3, 0.6),
                         spot_cos=0.9, spot_soft=0.05))
    cam = Camera((0.6, 7.2, 9.6), (0.6, 4.2, -6.0), fov=60)
    img = render(sc, cam)
    return F(img, vig=0.6, grain=6, bloom=0.8, shake=(42 * decay(bash, 4) + 4 if bash > 0 else 6),
             zoom=(punch(bash, 0.15, 0.25) if bash > 0 else 1.0),
             flash=((255, 255, 255), 0.7 * decay(bash, 9)) if bash > 0 else 0)


def sh_arrest(t, lt):
    pl, red = police_lights(t, (-3.0, 7.0, 2.0), (3.0, 7.0, 2.0), 2.4, 3.0)
    sc = bscene(phone='cracked', sec=int(t - 75), stair=0.6, bulb=0.6, extra=pl)
    sc.add(boy_tied(t, 'worried', 0.15))
    sc.add(A.character(A.COUSIN, (-2.6, 0, -1.6), 15, 'angry', arm_l=-35, arm_r=-35, roll_l=-12, roll_r=-12,
                       head_yaw=-15 if int(t * 2) % 3 else 15))
    sc.add(A.character(A.COP, (-0.4, 0, -3.4), -45, 'cop', arm_l=60, arm_r=70, roll_l=-10, roll_r=-10))
    hit = t - 108.55
    if hit > 0:
        sc.add(box((-2.6, 2.6, -2.25), (1.2, 0.2, 0.25), (200, 200, 210), emissive=0.6, bias=3))
    cam = Camera((-1.2, 5.8, 6.2), (-2.4, 4.0, -2.0), fov=54)
    img = render(sc, cam)
    return F(img, vig=0.6, grain=6, bloom=0.7, zoom=(1 + 0.03 * lt) * (punch(hit, 0.08, 0.2) if hit > 0 else 1),
             shake=(8 * decay(hit, 6) + 2 if hit > 0 else 2), flash=((255, 255, 255), 0.25 * decay(hit, 14)) if hit > 0 else 0)


def sh_traced(t, lt):
    img = I.phone_insert('traced', lt, bg='wall')
    on = math.sin(t * 3 * 2 * math.pi) > 0
    return F(img, vig=0.6, grain=6, bloom=0.3, zoom=1.0 + 0.03 * lt, rb=0.18 if on else -0.18)


def sh_safe(t, lt):
    pl, red = police_lights(t, (-3.0, 7.0, 2.0), (4.0, 7.0, 2.0), 1.6, 1.5)
    sc = bscene(phone='cracked', sec=int(t - 75), stair=1.0, bulb=0.8, extra=pl)
    sc.add(boy_tied(t, 'relief', 0.0, tied=False, head_yaw=-25))
    sc.add(A.character(A.COP2, (-1.4, -0.9, -1.8), 70, 'cop', leg_l=80, leg_r=-10, arm_r=75, roll_r=-10))
    cam = Camera((CX - 0.4, 5.3, CZ + 7.0), (CX - 1.1, 3.8, CZ), fov=56)
    img = render(sc, cam)
    return F(img, vig=0.55, grain=5, bloom=0.6, zoom=1.0 + 0.03 * lt)


# ------------------------------------------------------------------ 6. ending

def sh_car(t, lt):
    sc = SE.exterior(True)
    car, red = SE.police_car((-2.0, 0, 7.0), 0, phase=t * 1.5)
    sc.add(car)
    sc.add(Light((-3.4, 6.5, 8.5), (255, 30, 30), 3.0 if red else 0.2, 14))
    sc.add(Light((-1.6, 6.5, 8.5), (40, 80, 255), 0.2 if red else 3.0, 14))
    turn = -80 * ease((t - 116.2) / 0.7)
    cou = A.character(A.COUSIN, (-2.0, -0.9, 6.4), 90, 'stare' if t > 116.0 else 'blank', leg_l=90, leg_r=90,
                      arm_l=-30, arm_r=-30, head_yaw=turn)
    sc.add([setattr(b, 'bias', -1.0) or b for b in cou])
    sc.add(Light((-0.6, 4.2, 9.0), (255, 120, 120), 0.8, 3.0))
    sc.add(A.character(A.BOY, (3.2, 0, 14.0), 200, 'worried', blanket=True))
    sc.add(A.character(A.COP, (5.5, 0, 9.5), -70, 'cop'))
    k = ease((t - 115.0) / 4.3)
    cam = Camera(lv((6.5, 6.4, 21.5), (-0.9, 4.6, 12.2), k), lv((0.5, 4.4, 8.0), (-2.0, 4.35, 6.4), k), fov=56)
    img = render(sc, cam)
    hit = t - 118.15
    return F(img, vig=0.7, grain=6, bloom=0.8, zoom=(punch(hit, 0.12, 0.2) if hit > 0 else 1.0),
             shake=(14 * decay(hit, 4) + 2 if hit > 0 else 2))


def sh_loop(t, lt):
    img = render(hook_state(0.0), hook_cam(0.0))
    g = lerp(0.9, 0.25, ease(lt / 0.7))
    return F(img, glitch=g, chroma=int(lerp(14, 6, lt / 0.7)), bloom=0.6, vig=0.7, grain=10,
             zoom=1.0 + 0.14 * ease(lt / 0.7), shake=4 + 20 * ease(lt / 0.7))


SHOTS = [
    (0.00, 3.00, sh_hook_wide, 'Cold open: basement, boy tied up, phone "911 call ended", cousin\'s shadow approaches'),
    (3.00, 3.95, sh_hook_face, 'Zoom/shake on the boy\'s terrified face'),
    (3.95, 4.80, sh_hook_cousin, 'Low angle: cousin, "You shouldn\'t have looked in that room."'),
    (4.80, 6.05, sh_rewind, 'VHS glitch rewind + "3 HOURS EARLIER..."'),
    (6.05, 10.00, sh_ext_day, 'Sunny exterior: boy walks up to the house, cousin waves'),
    (10.00, 15.20, sh_living_hello, 'Living room: "Hey buddy! Make yourself at home."'),
    (15.20, 19.30, sh_couch, 'Couch: games and pizza, TV glow'),
    (19.30, 25.00, sh_hallway, 'Dolly down the hall to the padlocked KEEP OUT door (hit on LOCKED)'),
    (25.00, 26.50, sh_boy_asks, 'Boy: "What\'s in there?"'),
    (26.50, 30.00, sh_cousin_snap, 'Cousin\'s smile drops: "Nothing. Don\'t ever go in there."'),
    (30.00, 34.40, sh_keys, 'Night: car lights leave, keys glinting on the table'),
    (34.40, 38.00, sh_hall_night, 'Flashlight walk, padlock off, door creaks open'),
    (38.00, 41.30, sh_posters, 'Flashlight sweeps across MISSING posters'),
    (41.30, 44.90, sh_newspaper, 'Insert: newspaper clippings'),
    (44.90, 47.60, sh_desk, 'Push in on the desk and the list'),
    (47.60, 50.00, sh_list, 'Insert: names crossed out, "7. TYLER" circled in red'),
    (50.00, 52.70, sh_boy_face, 'Boy\'s face: "My cousin is a... KILLER?"'),
    (52.70, 55.00, sh_front_door, 'Headlights sweep, front door slams'),
    (55.00, 58.00, sh_closet, 'Boy hides in the closet, phone glow'),
    (58.00, 63.70, sh_phone_ui, 'Phone UI: dials 9-1-1, "calling...", connected'),
    (63.70, 68.00, sh_whisper, 'Whispering to the operator'),
    (68.00, 70.70, sh_pov_slats, 'POV through closet slats: cousin walking closer'),
    (70.70, 72.60, sh_found_you, 'Closet door opens: "Found you." -> cut to black'),
    (72.60, 75.00, sh_black, 'Black, heartbeat'),
    (75.00, 78.60, sh_wake, 'Eyes open: tied up in the basement (back to the opening)'),
    (78.60, 81.80, sh_cousin_returns, 'Cousin walks in: "You shouldn\'t have looked in that room."'),
    (81.80, 83.40, sh_smash, 'Cousin stomps and smashes the phone'),
    (83.40, 86.00, sh_nobody, '"Nobody\'s coming."'),
    (86.00, 90.50, sh_clock_boy, 'Boy struggles, clock on the wall'),
    (90.50, 93.50, sh_upstairs, 'Cousin goes upstairs, door shuts, light goes out'),
    (93.50, 96.50, sh_clock, 'Clock close-up 11:58, ticking'),
    (96.50, 101.00, sh_struggle, 'Struggling in the dark, the stair light comes back on'),
    (101.00, 102.80, sh_time_to_go, 'Cousin: "It\'s time to go."'),
    (102.80, 104.60, sh_gasp, 'Extreme close-up, gasp, first red/blue flicker'),
    (104.60, 107.60, sh_bust_in, 'Sirens, door bash, police rush down the stairs'),
    (107.60, 109.50, sh_arrest, 'Cousin handcuffed'),
    (109.50, 112.90, sh_traced, 'Phone UI: call went through, location shared'),
    (112.90, 115.00, sh_safe, 'Cop frees the boy: "You\'re safe now, kid."'),
    (115.00, 119.30, sh_car, 'Police car at night: cousin turns and stares through the window'),
    (119.30, 120.00, sh_loop, 'Glitch back into the opening shot (seamless loop)'),
]


def shot_at(t):
    for t0, t1, fn, _ in SHOTS:
        if t0 <= t < t1:
            return fn(t, t - t0)
    return SHOTS[-1][2](t, t - SHOTS[-1][0])
