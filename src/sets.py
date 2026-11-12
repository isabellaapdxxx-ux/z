"""Set builders. Each returns a Scene (static geometry) — characters/props that
animate are added by the shot functions."""
import math
import random
from functools import lru_cache

import numpy as np

from engine3d import Scene, Light, Quad, Box, box, T, S, RX, RY, RZ, rad, disc
import assets as A


def quad_wall(cx, cy, z, w, h, img, layer=1, bias=0.0, lit=True, emissive=0.0):
    """Quad on a wall facing +z at plane z."""
    return Quad([(cx - w / 2, cy + h / 2, z), (cx + w / 2, cy + h / 2, z), (cx + w / 2, cy - h / 2, z),
                 (cx - w / 2, cy - h / 2, z)], img, layer=layer, bias=bias, lit=lit, emissive=emissive)


def quad_wall_x(cx_z, cy, x, w, h, img, facing=1, layer=1, bias=0.0, lit=True):
    """Quad on a wall at plane x facing +x (facing=1) or -x (facing=-1)."""
    z = cx_z
    if facing > 0:
        P = [(x, cy + h / 2, z - w / 2), (x, cy + h / 2, z + w / 2), (x, cy - h / 2, z + w / 2), (x, cy - h / 2, z - w / 2)]
    else:
        P = [(x, cy + h / 2, z + w / 2), (x, cy + h / 2, z - w / 2), (x, cy - h / 2, z - w / 2), (x, cy - h / 2, z + w / 2)]
    return Quad(P, img, layer=layer, bias=bias, lit=lit)


# ====================================================================== BASEMENT

STAIR_TOP_LIGHT = (-8.0, 11.5, -10.5)
STAIR_BULB = (6.6, 8.2, -10.6)
CHAIR_POS = (1.2, 0, -3.0)
PHONE_POS = (-1.5, 0, -0.6)
CLOCK_POS = (3.6, 7.0, -11.9)


@lru_cache(maxsize=1)
def _basement_static():
    out = []
    out += A.tiled_floor(-10, 10, -12, 10, 0, 2.0, [(92, 92, 98), (86, 87, 93)], jitter=0.06, seed=1)
    # cinder block walls
    blk = [(104, 108, 116), (97, 100, 108)]
    out += A.tiled_wall('x', -12, -10, 10, 0, 10, 2.0, blk, 1, jitter=0.07, seed=2,
                        skip=lambda a, y: (-1.0 < a < 1.0 and 6 < y < 8))
    out += A.tiled_wall('z', -10, -12, 10, 0, 10, 2.0, blk, 1, jitter=0.07, seed=3)
    out += A.tiled_wall('z', 10, -12, 10, 0, 10, 2.0, blk, -1, jitter=0.07, seed=4)
    # ceiling joists
    for k in range(9):
        out.append(box((0, 9.8, -11 + k * 2.5), (20, 0.5, 0.5), (70, 50, 35), layer=0))
    out.append(box((0, 10.2, 0), (20, 0.2, 24), (40, 32, 26), layer=0))
    # stairs along back wall rising right -> left
    for i in range(12):
        h = (i + 1) * 0.8
        x = 6.5 - i * 1.15
        out.append(box((x, h / 2, -10.6), (1.15, h, 2.6), (95, 70, 50), outline=0.75, layer=1, bias=-6))
        out.append(box((x, h + 0.05, -10.6), (1.2, 0.12, 2.7), (120, 90, 60), outline=0.75, layer=1, bias=-6))
    for i in range(0, 12, 2):  # railing posts
        x = 6.5 - i * 1.15
        h = (i + 1) * 0.8
        out.append(box((x, h + 1.4, -9.35), (0.15, 2.8, 0.15), (60, 45, 35), layer=1, bias=-5))
    # high window (back wall)
    out.append(quad_wall(0, 7, -11.98, 2, 2, A.window_tex(True), layer=0, bias=1, lit=False))
    # shelves right wall
    for y in (1.5, 3.5, 5.5):
        out.append(box((8.8, y, -4), (2.2, 0.2, 6), (90, 70, 50), bias=-3))
    rnd = random.Random(3)
    for y in (1.5, 3.5, 5.5):
        for k in range(3):
            s = rnd.uniform(0.9, 1.5)
            out.append(box((8.8, y + 0.1 + s / 2, -6 + k * 2 + rnd.uniform(-.3, .3)), (s * 1.2, s, s),
                           rnd.choice([(150, 120, 80), (140, 110, 70), (120, 95, 60)]), bias=-2))
    # water heater + pipes
    out.append(box((-7.5, 3, -6.5), (2.2, 6, 2.2), (150, 150, 145), bias=-4))
    out.append(box((-7.5, 7.5, -6.5), (0.4, 3, 0.4), (120, 90, 60), bias=-4))
    out.append(box((-4, 9.3, -11.5), (12, 0.35, 0.35), (130, 90, 60), layer=0))
    # old boxes left front
    out.append(box((-8, 1, 3), (2.2, 2, 2.2), (140, 110, 70)))
    out.append(box((-8.2, 2.7, 3.3), (1.6, 1.4, 1.6), (130, 100, 65)))
    return out


def basement(stair_light=1.0, bulb=1.0, phone_glow=1.0, extra_lights=(), ambient=0.07):
    sc = Scene()
    sc.ambient = np.array([ambient, ambient, ambient * 1.25])
    sc.sun = np.array([0.0, 0.0, 0.0])
    sc.fog_color = np.array([4, 4, 8], float)
    sc.fog_density = 0.035
    sc.background = (5, 5, 8)
    sc.add(_basement_static())
    if stair_light > 0:
        sc.add(Light(STAIR_TOP_LIGHT, (255, 185, 110), 2.4 * stair_light, 9.0))
    if bulb > 0:
        sc.add(Light(STAIR_BULB, (255, 200, 130), 1.6 * bulb, 7.0))
        sc.add(box(STAIR_BULB, (0.35, 0.45, 0.35), (255, 230, 170), emissive=2.5 * bulb, bias=-3))
        sc.add(box((STAIR_BULB[0], STAIR_BULB[1] + 1.0, STAIR_BULB[2]), (0.06, 2.0, 0.06), (30, 30, 30), bias=-3))
    sc.add(Light((0, 7, -10.5), (90, 110, 170), 0.8, 6.0))  # moonlight from window
    if phone_glow > 0:
        sc.add(Light((PHONE_POS[0], 0.9, PHONE_POS[2]), (170, 200, 255), 2.6 * phone_glow, 2.6))
    for L in extra_lights:
        sc.add(L)
    return sc


# ====================================================================== EXTERIOR

@lru_cache(maxsize=2)
def _house_static(night):
    out = []
    grass = [(80, 170, 70), (74, 160, 64)] if not night else [(30, 60, 40), (27, 55, 36)]
    out += A.tiled_floor(-40, 40, -30, 30, 0, 4.0, grass, jitter=0.05, seed=5)
    side = (170, 170, 165) if not night else (70, 72, 80)
    for k in range(10):  # sidewalk
        out.append(box((2, 0.06, 26 - k * 4), (4, 0.12, 3.9), side, layer=0, outline=0.8))
    road = (60, 60, 65) if not night else (25, 25, 30)
    out.append(box((0, 0.05, 30), (80, 0.1, 8), road, layer=0))
    wall = (230, 215, 190) if not night else (90, 88, 100)
    roof = (170, 60, 50) if not night else (70, 30, 35)
    # house body
    out.append(box((0, 6, -12), (24, 12, 14), wall, outline=0.85))
    for k in range(5):
        out.append(box((0, 12.5 + k * 1.1, -12), (26 - k * 4.6, 1.1, 15), roof, outline=0.8))
    out.append(box((2, 3.5, -4.9), (3.6, 7, 0.3), (120, 70, 40), outline=0.7))  # door
    out.append(box((3.2, 3.5, -4.7), (0.3, 0.3, 0.2), (230, 190, 60)))
    for x in (-7, 8.5):
        out.append(Quad([(x - 2, 8, -4.98), (x + 2, 8, -4.98), (x + 2, 3.5, -4.98), (x - 2, 3.5, -4.98)],
                        A.window_tex(False) if not night else A.window_tex(True), lit=not night, bias=1,
                        emissive=0.0))
    # trees
    for (x, z) in ((-16, -2), (16, -4), (-20, 10), (20, 12)):
        out.append(box((x, 3, z), (1.6, 6, 1.6), (110, 75, 45)))
        out.append(box((x, 8, z), (6, 5, 6), (50, 140, 60) if not night else (20, 50, 30), outline=0.8))
    # fence
    for k in range(18):
        x = -34 + k * 4
        if -3 < x < 6:
            continue
        out.append(box((x, 1.2, 14), (0.4, 2.4, 0.4), (240, 240, 240) if not night else (110, 110, 120)))
    out.append(box((-18.5, 1.8, 14), (31, 0.3, 0.2), (240, 240, 240) if not night else (110, 110, 120)))
    out.append(box((22, 1.8, 14), (32, 0.3, 0.2), (240, 240, 240) if not night else (110, 110, 120)))
    return out


def exterior(night=False):
    sc = Scene()
    if not night:
        sc.background = A.sky_bg(540, 960, (70, 150, 255), (190, 225, 255))
        sc.ambient = np.array([0.5, 0.5, 0.55])
        sc.sun = np.array([0.6, 0.58, 0.5])
        sc.fog_color = np.array([190, 225, 255], float)
        sc.fog_density = 0.006
    else:
        sc.background = A.sky_bg(540, 960, (5, 6, 18), (25, 25, 50))
        sc.ambient = np.array([0.14, 0.14, 0.22])
        sc.sun = np.array([0.12, 0.12, 0.2])
        sc.fog_color = np.array([12, 12, 26], float)
        sc.fog_density = 0.02
    sc.add(_house_static(night))
    return sc


def police_car(pos, yaw=0, phase=0.0, layer=1, bias=0.0):
    root = T(*pos) @ RY(rad(yaw))
    kw = dict(layer=layer, bias=bias, outline=0.8)
    out = [Box(root @ T(0, 1.6, 0) @ S(12, 2.0, 5.2), (235, 235, 240), **kw),
           Box(root @ T(0, 1.0, 0) @ S(12.2, 0.9, 5.3), (25, 25, 30), **kw),
           Box(root @ T(-0.3, 5.35, 0) @ S(6.8, 0.3, 4.8), (235, 235, 240), **kw),
           Box(root @ T(-0.3, 2.75, 0) @ S(6.6, 0.3, 4.9), (25, 25, 30), **kw)]
    for x in (-3.5, -0.3, 2.9):
        for z in (-2.3, 2.3):
            out.append(Box(root @ T(x, 3.95, z) @ S(0.35, 2.6, 0.3), (30, 30, 36), **kw))
    out.append(Box(root @ T(-0.3, 3.4, -1.9) @ S(6.4, 1.6, 0.6), (35, 35, 40), layer=layer, bias=bias - 2))
    for x in (-3.8, 3.8):
        for z in (-2.5, 2.5):
            out.append(Box(root @ T(x, 0.9, z) @ S(1.8, 1.8, 0.6), (15, 15, 15), **kw))
    # light bar
    red_on = math.sin(phase * 2 * math.pi) > 0
    out.append(Box(root @ T(-1.4, 5.75, 0) @ S(1.6, 0.45, 1.2), (255, 40, 40) if red_on else (90, 20, 20),
                   emissive=3.0 if red_on else 0.0, **kw))
    out.append(Box(root @ T(0.4, 5.75, 0) @ S(1.6, 0.45, 1.2), (40, 80, 255) if not red_on else (20, 25, 90),
                   emissive=3.0 if not red_on else 0.0, **kw))
    # door text decal (on +z side)
    P = [(root @ np.array([x, y, 2.62, 1.0]))[:3] for x, y in ((-3.5, 2.5), (2.5, 2.5), (2.5, 0.9), (-3.5, 0.9))]
    out.append(Quad(P, A.police_door_tex(), layer=layer, bias=bias + 0.5))
    return out, red_on


# ====================================================================== INTERIOR (living room / hallway / rooms)

@lru_cache(maxsize=4)
def _room_static(kind):
    out = []
    if kind == 'living':
        out += A.tiled_floor(-12, 12, -10, 12, 0, 2.0, [(150, 105, 70), (140, 98, 64)], seed=7)
        wall = [(205, 185, 150), (198, 178, 144)]
        out += A.tiled_wall('x', -10, -12, 12, 0, 10, 4.0, wall, 1, seed=8, outline=0.95)
        out += A.tiled_wall('z', -12, -10, 12, 0, 10, 4.0, wall, 1, seed=9, outline=0.95)
        out += A.tiled_wall('z', 12, -10, 12, 0, 10, 4.0, wall, -1, seed=10, outline=0.95)
        # couch
        out.append(box((0, 1.2, 2), (9, 1.6, 3.5), (120, 50, 50), outline=0.8))
        out.append(box((0, 3.0, 3.4), (9, 2.6, 1.0), (110, 45, 45), outline=0.8))
        out.append(box((-4.8, 2.0, 2), (1.0, 2.4, 3.5), (110, 45, 45), outline=0.8))
        out.append(box((4.8, 2.0, 2), (1.0, 2.4, 3.5), (110, 45, 45), outline=0.8))
        # TV stand + TV (facing +z placed at back wall)
        out.append(box((0, 1.2, -8.8), (8, 2.4, 2), (70, 50, 35), outline=0.8))
        out.append(box((0, 5.0, -9.3), (7.4, 4.2, 0.4), (15, 15, 18)))
        # rug
        out.append(box((0, 0.03, -2.5), (10, 0.06, 7), (60, 90, 140), layer=0))
        # coffee table + pizza box
        out.append(box((0, 1.0, -2.5), (5, 0.3, 2.6), (90, 60, 40), outline=0.8))
        for x in (-2.2, 2.2):
            for z in (-3.5, -1.5):
                out.append(box((x, 0.45, z), (0.3, 0.9, 0.3), (80, 55, 35)))
        out.append(box((0.8, 1.3, -2.5), (2.4, 0.3, 2.0), (210, 170, 110)))
        out.append(Quad([(-0.4, 1.46, -3.5), (2.0, 1.46, -3.5), (2.0, 1.46, -1.5), (-0.4, 1.46, -1.5)],
                        A.pizza_tex(), bias=0.3))
        # window + lamp + picture
        out.append(quad_wall(-7, 6, -9.98, 4, 4.5, A.window_tex(False), layer=0, bias=1, lit=False))
        out.append(box((8, 3, -8), (0.3, 6, 0.3), (40, 40, 40)))
        out.append(box((8, 6.4, -8), (1.6, 1.2, 1.6), (250, 230, 180), emissive=1.2))
        # hallway opening on right wall
    elif kind == 'hall':
        out += A.tiled_floor(-4, 4, -30, 6, 0, 2.0, [(150, 105, 70), (140, 98, 64)], seed=11)
        wall = [(190, 200, 185), (182, 192, 177)]
        out += A.tiled_wall('z', -4, -30, 6, 0, 9, 3.0, wall, 1, seed=12, outline=0.95)
        out += A.tiled_wall('z', 4, -30, 6, 0, 9, 3.0, wall, -1, seed=13, outline=0.95)
        out += A.tiled_wall('x', -30, -4, 4, 0, 9, 3.0, wall, 1, seed=14, outline=0.95,
                            skip=lambda a, y: -1.5 < a < 1.5 and y < 7.5)
        out.append(box((0, 9.1, -12), (8, 0.2, 40), (230, 230, 225), layer=0))
        # side doors
        for z in (-8, -18):
            out.append(box((-3.85, 3.5, z), (0.2, 7, 3.2), (150, 110, 70), outline=0.7))
            out.append(box((3.85, 3.5, z - 4), (0.2, 7, 3.2), (150, 110, 70), outline=0.7))
        # frames
        out.append(quad_wall_x(-12, 5, -3.88, 2.4, 1.8, A.portrait(31), facing=1))
        out.append(quad_wall_x(-14, 5, 3.88, 2.4, 1.8, A.portrait(32), facing=-1))
    elif kind == 'locked':
        out += A.tiled_floor(-8, 8, -8, 8, 0, 2.0, [(70, 60, 55), (64, 55, 50)], seed=15)
        wall = [(80, 75, 70), (74, 70, 65)]
        out += A.tiled_wall('x', -8, -8, 8, 0, 9, 3.0, wall, 1, seed=16, outline=0.92)
        out += A.tiled_wall('z', -8, -8, 8, 0, 9, 3.0, wall, 1, seed=17, outline=0.92)
        out += A.tiled_wall('z', 8, -8, 8, 0, 9, 3.0, wall, -1, seed=18, outline=0.92)
        out.append(box((0, 9.1, 0), (16, 0.2, 16), (40, 38, 36), layer=0))
        # posters on back wall + left wall
        names = ['ETHAN R.', 'MAYA L.', 'JORDAN P.', 'CHLOE S.', 'NOAH K.', 'AVA M.']
        k = 0
        for row, y in enumerate((6.2, 3.4)):
            for col, x in enumerate((-5.2, -1.8, 1.6, 5.0)):
                if row == 1 and col == 3:
                    continue
                img = A.poster_tex(k, names[k % 6]) if not (row == 1 and col == 1) else A.newspaper_tex(1)
                rot = (k % 3 - 1) * 0.15
                w, h = 2.6, 3.4 * (0.95 if img.size[1] < 700 else 1.1)
                out.append(Quad([(x - w / 2 + rot, y + h / 2, -7.97), (x + w / 2 + rot, y + h / 2 - rot, -7.97),
                                 (x + w / 2 - rot, y - h / 2, -7.97), (x - w / 2 - rot, y - h / 2 + rot, -7.97)],
                                img, layer=0, bias=1))
                k += 1
        for j, z in enumerate((-5, -1.5)):
            out.append(quad_wall_x(z, 5.4, -7.97, 2.6, 3.4, A.poster_tex(10 + j, names[(j + 3) % 6]), facing=1,
                                   layer=0, bias=1))
        out.append(quad_wall_x(2.2, 5.0, -7.97, 3.2, 4.0, A.newspaper_tex(2, 'STILL MISSING', 'Search enters 3rd week'),
                               facing=1, layer=0, bias=1))
        # red string lines between posters (thin boxes)
        for (a, b) in (((-5.2, 6.2), (-1.8, 3.4)), ((-1.8, 3.4), (1.6, 6.2)), ((1.6, 6.2), (5.0, 6.2)),
                       ((1.6, 3.4), (5.0, 6.2))):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            out.append(Box(T(mx, my, -7.9) @ RZ(ang) @ S(L, 0.06, 0.04), (200, 20, 20), layer=0, bias=2))
        # desk
        out.append(box((3.5, 2.4, -5.5), (5, 0.3, 2.6), (80, 55, 40), outline=0.8))
        for x in (1.3, 5.7):
            out.append(box((x, 1.15, -5.5), (0.3, 2.3, 2.3), (70, 48, 34)))
        out.append(Quad([(2.6, 2.57, -6.2), (4.0, 2.57, -6.2), (4.0, 2.57, -4.4), (2.6, 2.57, -4.4)],
                        A.list_tex(0.0), bias=0.6))
    elif kind == 'closet':
        out += A.tiled_floor(-3, 3, -3, 3, 0, 1.5, [(110, 80, 55), (100, 72, 50)], seed=19)
        wall = [(120, 110, 100), (112, 104, 94)]
        out += A.tiled_wall('x', -2.5, -3, 3, 0, 9, 1.5, wall, 1, seed=20, outline=0.92)
        out += A.tiled_wall('z', -3, -3, 3, 0, 9, 1.5, wall, 1, seed=21, outline=0.92)
        out += A.tiled_wall('z', 3, -3, 3, 0, 9, 1.5, wall, -1, seed=22, outline=0.92)
        out.append(box((0, 7.2, -1.2), (6, 0.15, 0.15), (160, 160, 160)))
        rnd = random.Random(4)
        for k in range(6):
            x = -2.3 + k * 0.9
            out.append(box((x, 5.0, -1.2), (0.6, 4.2, 1.8), rnd.choice([(60, 70, 110), (110, 50, 50), (60, 90, 60),
                                                                         (80, 80, 80)]), bias=-2))
        out.append(box((1.8, 0.8, -1.8), (1.6, 1.6, 1.6), (140, 110, 70)))
    return out


def room(kind, lights=(), ambient=0.4, sun=0.35, fog=0.0, fogc=(0, 0, 0), bg=(0, 0, 0)):
    sc = Scene()
    sc.add(_room_static(kind))
    sc.ambient = np.array([ambient, ambient, ambient * 1.05])
    sc.sun = np.array([sun, sun, sun * 0.95])
    sc.sun_dir = np.array([0.3, 0.8, 0.5]) / np.linalg.norm([0.3, 0.8, 0.5])
    sc.fog_density = fog
    sc.fog_color = np.array(fogc, float)
    sc.background = bg
    for L in lights:
        sc.add(L)
    return sc


def locked_door(pos, open_angle=0.0, padlock=True, sign=True, layer=1):
    """Door in a wall plane facing +z; hinge on left."""
    x, y, z = pos
    hinge = T(x - 1.5, 0, z) @ RY(rad(open_angle))
    out = [Box(hinge @ T(1.5, 3.5, 0) @ S(3.0, 7.0, 0.25), (95, 60, 40), layer=layer, outline=0.7)]
    out.append(Box(hinge @ T(2.6, 3.5, 0.2) @ S(0.25, 0.25, 0.2), (220, 190, 70), layer=layer))
    if padlock:
        out.append(Box(hinge @ T(2.6, 4.5, 0.35) @ S(0.6, 0.55, 0.3), (210, 170, 40), layer=layer, bias=0.5))
        out.append(Box(hinge @ T(2.6, 4.95, 0.35) @ S(0.4, 0.35, 0.08), (160, 160, 160), layer=layer, bias=0.5))
        out.append(Box(hinge @ T(2.6, 4.6, 0.16) @ S(1.4, 0.18, 0.08), (130, 130, 130), layer=layer, bias=0.4))
    if sign:
        P = [(hinge @ np.array([px, py, 0.14, 1.0]))[:3] for px, py in ((0.5, 6.2), (2.5, 6.2), (2.5, 5.3), (0.5, 5.3))]
        out.append(Quad(P, A.sign_tex('KEEP OUT', bg=(200, 30, 30), fg=(255, 255, 255)), layer=layer, bias=0.6))
    return out
