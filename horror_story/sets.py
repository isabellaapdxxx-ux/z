"""Blocky sets: suburban street (day/night), Mr. Gray's basement, Timmy's hallway/bedroom, police cars."""
import math
import random
from functools import lru_cache

import numpy as np

import assets as A
from engine3d import Box, Quad, Light, Scene, T, S, RX, RY, RZ, rad, box

TOP_ONLY = ('bottom', 'left', 'right', 'front', 'back')


def tiles_floor(x0, x1, z0, z1, y, tile, colors, seed=0, layer=0, jitter=10, outline=0.88):
    r = random.Random(seed)
    out = []
    nx = max(1, int(round((x1 - x0) / tile)))
    nz = max(1, int(round((z1 - z0) / tile)))
    tx, tz = (x1 - x0) / nx, (z1 - z0) / nz
    for i in range(nx):
        for j in range(nz):
            c = np.array(r.choice(colors), float) + r.uniform(-jitter, jitter)
            out.append(box((x0 + (i + .5) * tx, y - 0.25, z0 + (j + .5) * tz), (tx, 0.5, tz), c, layer=layer,
                           hide=TOP_ONLY, outline=outline))
    return out


def tiles_wall(axis, fixed, a0, a1, y0, y1, tw, th, colors, normal, seed=0, layer=0, jitter=8, outline=0.8,
               holes=()):
    """Wall made of block tiles. axis 'x': wall spans x at z=fixed; 'z': spans z at x=fixed.
    normal = +1/-1: which side faces the room. holes: list of (a0,a1,y0,y1) to leave open."""
    r = random.Random(seed)
    out = []
    ny = max(1, int(round((y1 - y0) / th)))
    hh = (y1 - y0) / ny
    for j in range(ny):
        off = (tw / 2) * (j % 2)
        a = a0 - off
        while a < a1:
            b0, b1 = max(a, a0), min(a + tw, a1)
            a += tw
            if b1 - b0 < 0.05:
                continue
            yc = y0 + (j + .5) * hh
            am = (b0 + b1) / 2
            if any(h0 <= am <= h1 and hy0 <= yc <= hy1 for h0, h1, hy0, hy1 in holes):
                continue
            c = np.array(r.choice(colors), float) + r.uniform(-jitter, jitter)
            if axis == 'x':
                show = 'front' if normal > 0 else 'back'
                hide = tuple(f for f in ('front', 'back', 'left', 'right', 'top', 'bottom') if f != show)
                out.append(box((am, yc, fixed), (b1 - b0, hh, 0.4), c, layer=layer, hide=hide, outline=outline))
            else:
                show = 'right' if normal > 0 else 'left'
                hide = tuple(f for f in ('front', 'back', 'left', 'right', 'top', 'bottom') if f != show)
                out.append(box((fixed, yc, am), (0.4, hh, b1 - b0), c, layer=layer, hide=hide, outline=outline))
    return out


def quad_z(cx, cy, z, w, h, img, facing=1, **kw):
    """Vertical quad in an x-y plane at depth z facing +z (facing=1) or -z."""
    if facing > 0:
        P = [(cx - w / 2, cy + h / 2, z), (cx + w / 2, cy + h / 2, z), (cx + w / 2, cy - h / 2, z),
             (cx - w / 2, cy - h / 2, z)]
    else:
        P = [(cx + w / 2, cy + h / 2, z), (cx - w / 2, cy + h / 2, z), (cx - w / 2, cy - h / 2, z),
             (cx + w / 2, cy - h / 2, z)]
    return Quad(P, img, **kw)


def quad_x(cz, cy, x, w, h, img, facing=1, **kw):
    """Vertical quad in a z-y plane at x, facing +x (facing=1) or -x."""
    if facing > 0:
        P = [(x, cy + h / 2, cz + w / 2), (x, cy + h / 2, cz - w / 2), (x, cy - h / 2, cz - w / 2),
             (x, cy - h / 2, cz + w / 2)]
    else:
        P = [(x, cy + h / 2, cz - w / 2), (x, cy + h / 2, cz + w / 2), (x, cy - h / 2, cz + w / 2),
             (x, cy - h / 2, cz - w / 2)]
    return Quad(P, img, **kw)


# ============================================================== props

def tree(x, z, h=9, seed=0, night=False):
    r = random.Random(seed)
    k = 0.45 if night else 1.0
    trunk = (int(90 * k), int(62 * k), int(40 * k))
    out = [box((x, h * 0.3, z), (1.2, h * 0.6, 1.2), trunk)]
    for i in range(3):
        s = 6 - i * 1.6
        g = (int((40 + r.randint(0, 20)) * k), int((95 + r.randint(0, 30)) * k), int((50 + r.randint(0, 15)) * k))
        out.append(box((x + r.uniform(-.4, .4), h * 0.6 + i * 1.9, z + r.uniform(-.4, .4)), (s, 2.2, s), g,
                       rot=RY(rad(r.uniform(0, 30)))))
    return out


def picket_fence(x, z0, z1, h=3.4, color=(205, 200, 185)):
    out = []
    z = z0
    while z <= z1:
        out.append(box((x, h / 2, z), (0.25, h, 0.6), color, outline=0.7))
        z += 1.0
    for y in (h * 0.3, h * 0.75):
        out.append(box((x, y, (z0 + z1) / 2), (0.15, 0.35, z1 - z0), tuple(c * 0.85 for c in color)))
    return out


def lamp_post(x, z, on):
    out = [box((x, 5, z), (0.4, 10, 0.4), (40, 42, 48)),
           box((x, 10.2, z + 0.6), (0.4, 0.3, 1.6), (40, 42, 48)),
           box((x, 9.9, z + 1.2), (1.0, 0.5, 1.0), (255, 230, 170) if on else (90, 90, 90),
               emissive=1.6 if on else 0.0)]
    return out


def mailbox(x, z, number, night):
    k = 0.6 if night else 1.0
    return [box((x, 1.6, z), (0.3, 3.2, 0.3), (60 * k, 50 * k, 40 * k)),
            box((x, 3.5, z), (1.0, 0.9, 1.6), (40 * k, 40 * k, 45 * k),
                decals={'right': A.house_number_tex(number), 'left': A.house_number_tex(number)})]


def gable_roof(x0, x1, z0, z1, y, rise, color):
    """Roof ridge along x."""
    zc = (z0 + z1) / 2
    half = (z1 - z0) / 2 + 1.0
    ang = math.atan2(rise, half)
    L = math.hypot(half, rise)
    out = []
    for side in (-1, 1):
        rot = RX(side * ang)
        out.append(box((((x0 + x1) / 2), y + rise / 2, zc + side * half / 2), (x1 - x0 + 2, 0.6, L), color, rot=rot,
                       outline=0.75))
    # gable triangles approximated by stacked boxes
    n = 5
    for i in range(n):
        hh = rise / n
        wz = (z1 - z0) * (1 - (i + .5) / n)
        for xx in (x0 + 0.3, x1 - 0.3):
            out.append(box((xx, y + hh * (i + .5), zc), (0.6, hh, wz), tuple(c * 1.25 for c in color)))
    return out


def house(x0, x1, z0, z1, height, wall, roof, door_x, windows, night, lit_windows=(), porch=None,
          number=None, basement_window=None, basement_on=False, seed=0):
    out = []
    xc, zc = (x0 + x1) / 2, (z0 + z1) / 2
    out.append(box((xc, height / 2, zc), (x1 - x0, height, z1 - z0), wall, outline=0.85))
    # trim stripes
    out.append(box((xc, 0.4, z1 + 0.05), (x1 - x0 + 0.2, 0.8, 0.2), tuple(c * 0.7 for c in wall)))
    out += gable_roof(x0, x1, z0, z1, height, 5.5, roof)
    # door
    out.append(Quad([(door_x - 1.4, 6.0, z1 + 0.03), (door_x + 1.4, 6.0, z1 + 0.03), (door_x + 1.4, 0.2, z1 + 0.03),
                     (door_x - 1.4, 0.2, z1 + 0.03)], A.door_tex(), layer=1, bias=0.5))
    out.append(box((door_x, 0.25, z1 + 1.2), (4.5, 0.5, 2.4), (110, 110, 112)))
    for i, (wx, wy) in enumerate(windows):
        lit = i in lit_windows
        out.append(Quad([(wx - 1.6, wy + 1.6, z1 + 0.03), (wx + 1.6, wy + 1.6, z1 + 0.03), (wx + 1.6, wy - 1.6, z1 + 0.03),
                         (wx - 1.6, wy - 1.6, z1 + 0.03)], A.window_tex(lit), layer=1, bias=0.5,
                        lit=not lit))
    if basement_window is not None:
        bx = basement_window
        out.append(Quad([(bx - 1.6, 1.7, z1 + 0.04), (bx + 1.6, 1.7, z1 + 0.04), (bx + 1.6, 0.1, z1 + 0.04),
                         (bx - 1.6, 0.1, z1 + 0.04)], A.basement_window_tex(basement_on), layer=1, bias=0.6,
                        lit=not basement_on, emissive=0))
    if number:
        out.append(Quad([(door_x + 2.0, 6.0, z1 + 0.04), (door_x + 3.6, 6.0, z1 + 0.04),
                         (door_x + 3.6, 5.3, z1 + 0.04), (door_x + 2.0, 5.3, z1 + 0.04)],
                        A.house_number_tex(number), layer=1, bias=0.6))
    return out


# ============================================================== street

GRAY_BASEMENT_WIN = (13.0, 0.9, 0.05)  # x, y, z (front face of Gray's house)
GRAY_PORCH = (16.5, 6.8, 0.6)


@lru_cache(maxsize=None)
def _street_static(night):
    k = 0.55 if night else 1.0
    out = []
    grass = [(60, 105, 55), (55, 98, 50), (66, 112, 60)]
    if night:
        grass = [tuple(int(c * 0.5) for c in g) for g in grass]
    out += tiles_floor(-48, 48, -30, 14, 0, 4, grass, seed=1)
    walk = [(150, 150, 145), (140, 140, 138)]
    out += tiles_floor(-48, 48, 14, 17, 0.15, 3, [tuple(int(c * k) for c in w) for w in walk], seed=2)
    out += tiles_floor(-48, 48, 17, 31, 0.0, 6, [(int(46 * k), int(46 * k), int(52 * k))], seed=3, jitter=3)
    for i in range(-8, 9):
        out.append(box((i * 6, 0.02, 24), (3, 0.04, 0.4), (int(200 * k), int(170 * k), int(40 * k)), layer=0,
                       hide=TOP_ONLY))
    out += tiles_floor(-48, 48, 31, 60, 0, 6, grass, seed=4)
    # far houses across the street (facing -z)
    for i, x in enumerate((-36, -12, 12, 36)):
        c = (120, 110, 100) if i % 2 else (100, 115, 125)
        c = tuple(int(v * k) for v in c)
        out.append(box((x, 6, 46), (18, 12, 12), c))
        out += gable_roof(x - 9, x + 9, 40, 52, 12, 4, tuple(int(v * k) for v in (70, 50, 45)))
    # Timmy's house (left) and Mr. Gray's house (right)
    tw = tuple(int(c * k) for c in (160, 180, 200))
    out += house(-32, -8, -16, 0, 15, tw, tuple(int(c * k) for c in (150, 60, 50)), -20,
                 [(-27, 4.2), (-13, 4.2), (-27, 11), (-13, 11)], night, lit_windows=(0,) if night else (),
                 number='40', seed=1)
    gw = tuple(int(c * k) for c in (88, 90, 96))
    out += house(8, 30, -16, 0, 10, gw, tuple(int(c * k) for c in (38, 38, 44)), 19, [(25, 5)], night,
                 number='42', seed=2)
    out += picket_fence(0, -14, 12)
    out += tree(-40, 4, seed=1, night=night) + tree(38, 6, seed=2, night=night) + tree(-4, -24, seed=3, night=night)
    out += tree(44, -10, seed=4, night=night)
    out += mailbox(-14, 13, '40', night) + mailbox(22, 13, '42', night)
    out += lamp_post(-2, 16, night)
    out += lamp_post(40, 16, night)
    # driveway / walkway to Gray's door
    out += tiles_floor(17.5, 20.5, 0, 14, 0.05, 3, [tuple(int(c * k) for c in (120, 118, 112))], seed=6)
    out += tiles_floor(-21.5, -18.5, 0, 14, 0.05, 3, [tuple(int(c * k) for c in (120, 118, 112))], seed=7)
    return out


def street(night=False, basement_on=False, porch=1.0, sold_sign=True, extra=(), lights=(), ambient=None,
           bg=None):
    sc = Scene()
    sc.add(_street_static(night))
    # basement window of Gray's house
    bx, by, bz = GRAY_BASEMENT_WIN
    sc.add(Quad([(bx - 1.6, 1.7, bz), (bx + 1.6, 1.7, bz), (bx + 1.6, 0.1, bz), (bx - 1.6, 0.1, bz)],
                A.basement_window_tex(bool(basement_on)), layer=1, bias=0.6, lit=not basement_on))
    if sold_sign:
        sc.add(box((25, 1.6, 9), (0.3, 3.2, 0.3), (90, 70, 50) if not night else (45, 35, 25)),
               Quad([(23.8, 4.6, 9.2), (26.2, 4.6, 9.2), (26.2, 3.0, 9.2), (23.8, 3.0, 9.2)], A.sold_sign_tex(),
                    bias=0.5))
    if night:
        sc.ambient = np.array([0.24, 0.27, 0.4])
        sc.sun = np.array([0.18, 0.22, 0.36])
        sc.sun_dir = np.array([-0.3, 0.8, 0.5]) / np.linalg.norm([-0.3, 0.8, 0.5])
        sc.fog_color = np.array([10, 14, 30], float)
        sc.fog_density = 0.012
        sc.background = A.sky_bg(540, 960, 'night') if bg is None else bg
        # sickly green porch light on Gray's house
        px, py, pz = GRAY_PORCH
        sc.add(box((px, py, pz), (0.7, 0.9, 0.5), (170, 255, 120), emissive=2.0 * porch + 0.1))
        if porch > 0.05:
            sc.add(Light((px, py - 0.5, pz + 1.5), (150, 255, 110), 1.6 * porch, radius=7))
        sc.add(Light((-2, 9.5, 17.2), (255, 220, 160), 1.3, radius=9))
        sc.add(Light((-20, 7, 2.5), (255, 200, 140), 0.6, radius=5))
        if basement_on:
            sc.add(Light((bx, 1.2, 2.0), (170, 255, 120), 1.2 * float(basement_on), radius=4))
    else:
        sc.ambient = np.array([0.42, 0.44, 0.5])
        sc.sun = np.array([0.5, 0.5, 0.55])
        sc.fog_color = np.array([120, 130, 145], float)
        sc.fog_density = 0.008
        sc.background = A.sky_bg(540, 960, 'day') if bg is None else bg
    sc.add(list(extra))
    for L in lights:
        sc.add(L)
    if ambient is not None:
        sc.ambient = np.array(ambient)
    return sc


# ============================================================== police car

def police_car(pos, yaw=0, phase=0.0, k=1.0):
    """Blocky cruiser; front faces +x after yaw=0. phase toggles light bar red/blue."""
    x, y, z = pos
    M0 = T(x, y, z) @ RY(rad(yaw))
    out = []

    def B(c, s, col, **kw):
        M = M0 @ T(*c) @ S(*s)
        return Box(M, tuple(v * k for v in col), outline=0.75, **kw)
    out.append(B((0, 1.6, 0), (9, 1.8, 4.2), (235, 235, 240), decals={'front': A.police_door_tex(),
                                                                         'back': A.police_door_tex()}))
    out.append(B((-0.4, 3.2, 0), (5, 1.6, 3.9), (30, 30, 36)))
    out.append(B((-0.4, 3.3, 0), (4.6, 1.2, 3.95), (70, 90, 120)))
    for wx in (-3, 3):
        for wz in (-2.1, 2.1):
            out.append(B((wx, 0.75, wz), (1.6, 1.5, 0.6), (15, 15, 15)))
    red_on = (int(phase * 2) % 2) == 0
    out.append(Box(M0 @ T(-0.4, 4.25, -0.9) @ S(0.8, 0.5, 1.6), (255, 40, 40) if red_on else (90, 10, 10),
                   emissive=2.5 if red_on else 0.2))
    out.append(Box(M0 @ T(-0.4, 4.25, 0.9) @ S(0.8, 0.5, 1.6), (40, 80, 255) if not red_on else (10, 20, 90),
                   emissive=2.5 if not red_on else 0.2))
    out.append(B((4.55, 1.9, 1.3), (0.1, 0.5, 0.9), (255, 250, 220)))
    out.append(B((4.55, 1.9, -1.3), (0.1, 0.5, 0.9), (255, 250, 220)))
    return out, red_on


def police_lights(pos, phase, intensity=2.2, radius=12):
    red_on = (int(phase * 2) % 2) == 0
    x, y, z = pos
    if red_on:
        return [Light((x, y + 5, z), (255, 40, 40), intensity, radius=radius)]
    return [Light((x, y + 5, z), (50, 90, 255), intensity, radius=radius)]


# ============================================================== basement

BASE_Y = 13.0
STAIR_X0, STAIR_X1 = 7.5, 11.5
N_STEPS = 7
RISE = 0.79
RUN = 1.2
LANDING_Y = N_STEPS * RISE  # 5.53


def stair_pos(s):
    """Position on the stairs for progress s in [0,1] (0 = top landing at the door, 1 = basement floor)."""
    # top: landing in front of the door
    zt, yt = -11.0, LANDING_Y
    zb, yb = -3.0 + 1.6, 0.0
    if s <= 0.12:
        return (9.5, yt, zt + s / 0.12 * 0.8)
    u = (s - 0.12) / 0.88
    z = (zt + 0.8) + ((zb) - (zt + 0.8)) * u
    # quantized step heights
    steps_done = u * N_STEPS
    y = LANDING_Y - min(N_STEPS, math.floor(steps_done + 0.15)) * RISE
    return (9.5, max(0.0, y), z)


@lru_cache(maxsize=None)
def _basement_static():
    out = []
    conc = [(70, 72, 70), (64, 66, 64), (76, 78, 74)]
    out += tiles_floor(-12, 12, -12, 12, 0, 4, conc, seed=11)
    block = [(92, 94, 90), (86, 88, 84), (98, 98, 92)]
    out += tiles_wall('x', -12, -12, 12, 0, BASE_Y, 4, 2.6, block, +1, seed=12,
                      holes=[(STAIR_X0 + 0.3, STAIR_X1 - 0.3, LANDING_Y + 0.1, 12.5)])
    out += tiles_wall('z', -12, -12, 12, 0, BASE_Y, 4, 2.6, block, +1, seed=13)
    out += tiles_wall('z', 12, -12, 12, 0, BASE_Y, 4, 2.6, block, -1, seed=14)
    out += tiles_wall('x', 12, -12, 12, 0, BASE_Y, 4, 2.6, block, -1, seed=15, holes=[(-2.2, 2.2, 10.2, 12.4)])
    # ceiling + beams
    out.append(box((0, BASE_Y + 0.25, 0), (24, 0.5, 24), (40, 32, 26), hide=('top',)))
    for z in range(-10, 12, 4):
        out.append(box((0, BASE_Y - 0.4, z), (24, 0.8, 0.8), (70, 52, 36)))
    # stairs (right wall, rising toward the back)
    wood = (105, 78, 52)
    for i in range(N_STEPS):
        zc = -3.0 - i * RUN
        top = (i + 1) * RISE
        out.append(box(((STAIR_X0 + STAIR_X1) / 2, top / 2, zc), (STAIR_X1 - STAIR_X0, top, RUN), wood, outline=0.6))
    out.append(box(((STAIR_X0 + STAIR_X1) / 2, LANDING_Y / 2, -11.2), (STAIR_X1 - STAIR_X0, LANDING_Y, 1.6), wood,
                   outline=0.6))
    # railing
    out.append(box((STAIR_X0 - 0.1, 4.2, -6.5), (0.25, 0.25, 9.5), (80, 60, 40), rot=RX(-math.atan2(5.5, 9.0))))
    for i in range(0, N_STEPS, 2):
        zc = -3.0 - i * RUN
        out.append(box((STAIR_X0 - 0.1, (i + 1) * RISE + 1.6, zc), (0.2, 3.2, 0.2), (80, 60, 40)))
    # door frame
    out.append(box((9.5, 12.6, -11.85), (4.4, 0.4, 0.3), (60, 45, 30)))
    for xx in (STAIR_X0 + 0.2, STAIR_X1 - 0.2):
        out.append(box((xx, (LANDING_Y + 12.6) / 2, -11.85), (0.4, 12.6 - LANDING_Y, 0.3), (60, 45, 30)))
    # missing posters wall (left wall)
    r = random.Random(3)
    k = 0
    for row in range(3):
        for col in range(5):
            cz = -8.5 + col * 3.2 + r.uniform(-0.3, 0.3)
            cy = 4.6 + row * 2.8 + r.uniform(-0.2, 0.2)
            img = A.poster_tex(k)
            k += 1
            ang = r.uniform(-0.06, 0.06)
            P = np.array([(-11.78, cy + 1.2, cz + 0.9), (-11.78, cy + 1.2, cz - 0.9), (-11.78, cy - 1.2, cz - 0.9),
                          (-11.78, cy - 1.2, cz + 0.9)])
            P[:, 1] += np.array([1, -1, -1, 1]) * ang * 0.9 * np.array([1, 1, 1, 1])
            out.append(Quad(P, img, layer=1, bias=0.4 + row * 0.01))
    # red string between some posters (a "conspiracy wall")
    # workbench on back wall
    out.append(box((-1, 3.0, -10.8), (8, 0.4, 2.2), (95, 70, 45)))
    for xx in (-4.6, 2.6):
        out.append(box((xx, 1.4, -10.8), (0.4, 2.8, 1.8), (75, 55, 35)))
    out.append(box((-2.5, 3.5, -10.6), (1.6, 0.6, 1.0), (140, 30, 30)))  # toolbox
    out.append(box((0.8, 3.45, -10.9), (2.2, 0.5, 0.6), (60, 60, 64)))
    # shovel leaning on back wall + dirt pile
    out.append(box((-7.5, 3.0, -11.3), (0.25, 5.6, 0.25), (120, 85, 50), rot=RX(rad(-10))))
    out.append(box((-7.5, 0.6, -10.8), (1.1, 1.3, 0.2), (130, 135, 140), rot=RX(rad(-10))))
    for i, (dx, dz, s) in enumerate(((-9.5, -9.5, 2.4), (-8.6, -8.4, 1.6), (-10.2, -8.2, 1.4))):
        out.append(box((dx, s * 0.3, dz), (s, s * 0.6, s), (70, 50, 32)))
    # shelves near the stairs
    out.append(box((5.0, 4.0, -11.4), (3.0, 8.0, 1.0), (60, 46, 32)))
    for yy in (2.2, 4.6, 7.0):
        out.append(box((5.0, yy, -10.85), (2.8, 0.2, 0.2), (80, 60, 40)))
        out.append(box((4.4, yy + 0.5, -11.0), (0.7, 0.8, 0.6), (110, 120, 70)))
        out.append(box((5.6, yy + 0.4, -11.0), (0.6, 0.6, 0.6), (90, 90, 110)))
    # old boiler
    out.append(box((-9.0, 3.0, 9.0), (3.2, 6.0, 3.2), (55, 58, 60)))
    return out


def chair(pos, yaw=0.0):
    x, y, z = pos
    M0 = T(x, y, z) @ RY(rad(yaw))
    col = (95, 70, 45)
    out = [Box(M0 @ T(0, 1.9, 0) @ S(2.6, 0.3, 2.4), col, outline=0.6),
           Box(M0 @ T(0, 3.6, -1.1) @ S(2.6, 3.2, 0.3), col, outline=0.6)]
    for sx in (-1.1, 1.1):
        for sz in (-1.0, 1.0):
            out.append(Box(M0 @ T(sx, 0.9, sz) @ S(0.3, 1.8, 0.3), col, outline=0.6))
    return out


def tied_timmy(expr='scared', struggle=0.0, head_yaw=0.0, head_pitch=0.0, t=0.0, color_mul=1.0, phone=False):
    """Timmy tied to the chair at the basement center, facing +z."""
    wob = math.sin(t * 23) * struggle
    parts = chair((0, 0, 0))
    parts += A.character(A.TIMMY, (wob * 0.15, 0.25, -0.2), yaw=wob * 3, expr=expr, sit=True, tied=True,
                         arm_l=-25 + wob * 8, arm_r=-25 - wob * 8, roll_l=-8, roll_r=-8, leg_l=0, leg_r=0,
                         head_yaw=head_yaw + wob * 6, head_pitch=head_pitch, color_mul=color_mul)
    # ropes around chair legs
    parts.append(box((0, 0.9, 1.3), (2.6, 0.2, 0.2), (165, 125, 70)))
    if phone:
        parts.append(box((0.9, 2.6, 0.9), (0.5, 0.05, 0.9), (180, 220, 255), emissive=2.0))
    return parts


def bag(pos, yaw=0.0, k=1.0):
    x, y, z = pos
    M0 = T(x, y, z) @ RY(rad(yaw))
    col = tuple(c * k for c in (24, 24, 28))
    return [Box(M0 @ T(0, 0.75, 0) @ S(4.6, 1.5, 1.8), col, outline=0.6),
            Box(M0 @ T(-0.8, 1.6, 0.1) @ S(2.0, 0.6, 1.4), col, outline=0.6),
            Box(M0 @ T(1.4, 1.4, -0.1) @ S(1.4, 0.5, 1.2), col, outline=0.6),
            Box(M0 @ T(2.6, 0.75, 0) @ S(0.6, 0.5, 0.5), tuple(c * k for c in (150, 120, 70)))]


def basement(bulb=1.0, bulb_swing=0.0, bulb_z=2.2, door_open=0.0, door_light=0.0, green=0.0, ambient=0.13, police=0.0,
             police_phase=0.0, flash_light=None, extra=(), fog=0.028, moon_window=0.5):
    sc = Scene()
    sc.add(_basement_static())
    sc.ambient = np.array([0.9, 1.0, 1.25]) * ambient
    sc.sun = np.array([0.0, 0.0, 0.0])
    sc.fog_color = np.array([4, 5, 9], float)
    sc.fog_density = fog
    sc.background = (4, 5, 8)
    # hanging bulb (swing about x)
    bx = math.sin(bulb_swing) * 2.0
    by = 10.0 + (1 - math.cos(bulb_swing)) * 2.0
    cord_len = BASE_Y - by
    sc.add(box((bx / 2, by + cord_len / 2, bulb_z), (0.08, cord_len, 0.08), (20, 20, 20), rot=RZ(-bulb_swing * 0.5)))
    sc.add(box((bx, by - 0.3, bulb_z), (0.6, 0.7, 0.6), (255, 240, 170), emissive=0.2 + 2.4 * bulb))
    if bulb > 0.02:
        sc.add(Light((bx, by - 1.2, bulb_z), (255, 225, 150), 3.0 * bulb, radius=8.5))
    if green > 0:
        # sickly green work lamp near the posters
        sc.add(box((-5.0, 12.2, 3.0), (1.0, 0.7, 1.0), (170, 255, 130), emissive=2.0 * green))
        sc.add(Light((-5.0, 10.5, 2.0), (150, 255, 110), 3.0 * green, radius=13))
    # cellar window glow (moonlight) in front wall
    if moon_window > 0:
        sc.add(quad_z(0, 11.3, 11.75, 4.2, 2.1, A.window_tex(True, (60, 80, 140), cross=False), facing=-1, lit=False,
                      bias=0.5))
    # door at the top of the stairs (hinged on x=STAIR_X0+0.3)
    hx = STAIR_X0 + 0.3
    ang = door_open * rad(100)
    M = T(hx, (LANDING_Y + 12.4) / 2, -11.85) @ RY(ang) @ T(1.7, 0, 0) @ S(3.4, 12.4 - LANDING_Y, 0.25)
    sc.add(Box(M, (75, 52, 35), decals={'front': A.door_tex((75, 52, 35))}, layer=1, bias=0.3, outline=0.7))
    if door_light > 0:
        # light spilling through the doorway
        sc.add(quad_z(9.5, (LANDING_Y + 12.4) / 2, -11.95, 3.4, 12.4 - LANDING_Y,
                      A.window_tex(True, (255, 230, 180), cross=False), lit=False, layer=0, bias=0))
        sc.add(Light((9.5, LANDING_Y + 4, -9.5), (255, 220, 170), 2.2 * door_light, radius=9))
        sc.add(Light((6.0, 5.0, 0.0), (200, 175, 150), 1.1 * door_light, radius=9))  # fill on the stairs
    if police > 0:
        red_on = (int(police_phase * 2) % 2) == 0
        col = (255, 40, 40) if red_on else (50, 90, 255)
        sc.add(Light((9.5, LANDING_Y + 4, -9.0), col, 3.0 * police, radius=16))
        sc.add(Light((0, 11.0, 11.0), col if not red_on else (50, 90, 255), 1.6 * police, radius=14))
    if flash_light is not None:
        sc.add(flash_light)
    sc.add(list(extra))
    return sc


# ============================================================== Timmy's house (hallway / bedroom)

@lru_cache(maxsize=None)
def _hall_static():
    out = []
    wood = [(80, 58, 40), (72, 52, 36), (86, 62, 44)]
    out += tiles_floor(-7, 7, -10, 10, 0, 2.5, wood, seed=21)
    paper = [(48, 60, 92), (44, 56, 86)]
    out += tiles_wall('x', -10, -7, 7, 0, 11, 2.0, 11, paper, +1, seed=22, holes=[(-1.8, 1.8, 0, 7.5)])
    out += tiles_wall('z', -7, -10, 10, 0, 11, 2.0, 11, paper, +1, seed=23, holes=[(-6.6, -3.0, 0, 7.5)])
    out += tiles_wall('z', 7, -10, 10, 0, 11, 2.0, 11, paper, -1, seed=24)
    out += tiles_wall('x', 10, -7, 7, 0, 11, 2.0, 11, paper, -1, seed=25)
    out.append(box((0, 11.2, 0), (14, 0.4, 20), (30, 30, 36), hide=('top',)))
    # front door (behind Timmy when he enters) at z=-10 opening
    out.append(quad_z(0, 3.7, -9.75, 3.6, 7.4, A.door_tex((110, 50, 40)), facing=1, bias=0.5))
    # picture frames, side table, coat hooks
    out.append(box((6.7, 6.5, -4), (0.2, 2.4, 3.0), (60, 40, 25)))
    out.append(box((6.6, 6.5, -4), (0.2, 1.8, 2.4), (90, 110, 130)))
    out.append(box((5.8, 1.6, 3.5), (1.6, 3.2, 3.0), (90, 66, 44)))
    out.append(box((5.8, 3.6, 3.5), (0.8, 0.8, 0.8), (230, 200, 120), emissive=0.4))
    # dark doorway on the left wall (z -6.6..-3) -> pitch black box behind it
    out.append(box((-9.0, 3.75, -4.8), (3.6, 7.5, 3.6), (2, 2, 3), hide=('right',)))
    return out


def hallway(lamp=0.4, ambient=0.16, flash=None, extra=(), lights=()):
    sc = Scene()
    sc.add(_hall_static())
    sc.ambient = np.array([0.8, 0.9, 1.3]) * ambient
    sc.sun = np.zeros(3)
    sc.fog_color = np.array([3, 4, 10], float)
    sc.fog_density = 0.04
    sc.background = (2, 2, 5)
    if lamp > 0:
        sc.add(Light((5.0, 5.0, 3.5), (255, 200, 130), 2.4 * lamp, radius=9))
    sc.add(Light((0, 6, -9.0), (90, 120, 200), 0.5, radius=7))  # moonlight from the door window
    sc.add(list(extra))
    for L in lights:
        sc.add(L)
    return sc


# ============================================================== Timmy's bedroom (window looking at Gray's house)

@lru_cache(maxsize=None)
def _bedroom_static():
    out = []
    wood = [(70, 52, 38), (64, 48, 34)]
    out += tiles_floor(-8, 8, -6, 8, 0, 2.5, wood, seed=31)
    paper = [(40, 52, 80), (36, 48, 74)]
    out += tiles_wall('x', -6, -8, 8, 0, 11, 2.0, 11, paper, +1, seed=32, holes=[(-3.0, 3.0, 3.2, 8.8)])
    out += tiles_wall('z', -8, -6, 8, 0, 11, 2.0, 11, paper, +1, seed=33)
    out += tiles_wall('z', 8, -6, 8, 0, 11, 2.0, 11, paper, -1, seed=34)
    out.append(box((0, 11.2, 1), (16, 0.4, 14), (25, 25, 30), hide=('top',)))
    # window frame
    for (cx, cy, w, h) in ((0, 3.0, 6.6, 0.4), (0, 9.0, 6.6, 0.4), (-3.2, 6, 0.4, 6.4), (3.2, 6, 0.4, 6.4),
                           (0, 6, 0.25, 6), (0, 6, 6, 0.25)):
        out.append(box((cx, cy, -5.85), (w, h, 0.3), (210, 210, 205)))
    # bed + toys
    out.append(box((-5.5, 1.0, 2.0), (4.0, 2.0, 7.0), (60, 80, 150)))
    out.append(box((-5.5, 2.3, -0.8), (3.0, 0.8, 1.6), (220, 220, 230)))
    out.append(box((5.5, 0.6, 3.0), (1.2, 1.2, 1.2), (220, 60, 50)))
    out.append(box((6.2, 1.6, -4.5), (2.5, 3.2, 1.6), (110, 80, 55)))
    return out


def bedroom(view_img, extra=()):
    sc = Scene()
    sc.add(_bedroom_static())
    sc.add(quad_z(0, 6, -6.6, 9.0, 6.75, view_img, facing=1, lit=False, layer=0))
    sc.ambient = np.array([0.08, 0.1, 0.16])
    sc.sun = np.zeros(3)
    sc.background = (2, 2, 5)
    sc.add(Light((0, 6.5, -4.0), (110, 140, 220), 1.6, radius=8))
    sc.add(list(extra))
    return sc
