"""Every shot of the video. Each shot function returns a frame spec:
   {'scene': Scene, 'cam': Camera} or {'img': PIL image}, plus post-processing params (see fx.DEFAULTS).
"""
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

import assets as A
import sets as SE
from config import SHOTS, W, H
from engine3d import Camera, Light, Renderer, box

R = Renderer(W, H, 1)


# ------------------------------------------------------------------ helpers

def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def ease(u):
    u = clamp(u)
    return u * u * (3 - 2 * u)


def ease_out(u):
    u = clamp(u)
    return 1 - (1 - u) ** 3


def ease_in(u):
    u = clamp(u)
    return u ** 3


def lerp(a, b, u):
    return a + (b - a) * u


def lv(a, b, u):
    return tuple(lerp(x, y, u) for x, y in zip(a, b))


def yaw_to(src, dst):
    return math.degrees(math.atan2(dst[0] - src[0], dst[2] - src[2]))


def flicker(t, seed=0, rate=13.0, depth=0.45):
    """Irregular bulb flicker in [1-depth, 1]."""
    v = (math.sin(t * rate + seed) * 0.5 + math.sin(t * rate * 2.71 + seed * 3) * 0.3 +
         math.sin(t * rate * 6.13 + seed * 7) * 0.2)
    k = 1.0 if v > -0.55 else 0.15
    return 1 - depth * (1 - k) - depth * 0.15 * (0.5 + 0.5 * math.sin(t * 40 + seed))


def handheld(t, amp=0.06, seed=0):
    return (math.sin(t * 1.3 + seed) * amp + math.sin(t * 2.9 + seed * 2) * amp * 0.5,
            math.sin(t * 1.7 + seed * 3) * amp * 0.7 + math.sin(t * 3.3 + seed) * amp * 0.3, 0.0)


def pose(base, **over):
    d = dict(base)
    d.update(over)
    return d


def add3(a, b):
    return tuple(x + y for x, y in zip(a, b))


def frame(scene, cam, **post):
    d = dict(scene=scene, cam=cam)
    d.update(post)
    return d


GRADE_DAY = dict(tint=(0.86, 0.93, 1.08), sat=0.72, contrast=1.05, fog=0.18)
GRADE_NIGHT = dict(tint=(0.8, 0.9, 1.2), sat=0.85, contrast=1.08, fog=0.28)
GRADE_BASE = dict(tint=(1.0, 0.97, 0.88), sat=0.8, contrast=1.12, fog=0.22)
GRADE_GREEN = dict(tint=(0.9, 1.1, 0.85), sat=0.9, contrast=1.05, fog=0.2)


# ================================================================== HOOK / payoff composition

def gray_step(u):
    """Mr. Gray stepping out of the dark behind Timmy (used by the hook and its payoff)."""
    gz = lerp(-10.5, -5.2, ease_out(u))
    phase = u * 5.0
    w = A.walk(phase * math.pi, 18)
    w['bob'] *= 0.5
    dark = lerp(0.12, 0.85, ease(clamp((u - 0.15) / 0.85)))
    return A.character(A.GRAY, (-2.0, 0, gz), yaw=8, expr='blank', head_pitch=-12, color_mul=dark, **w)


def hook_comp(t, u, gray=True, expr='scared', struggle=0.25, push=(9.6, 8.2), phone=False):
    swing = 0.35 * math.sin(t * 2.4)
    fl = flicker(t * 1.3, seed=2, depth=0.5)
    parts = SE.tied_timmy(expr=expr, struggle=struggle, t=t, head_pitch=-6, phone=phone)
    if gray:
        parts = parts + gray_step(u)
    sc = SE.basement(bulb=fl, bulb_swing=swing, ambient=0.1, extra=parts)
    z = lerp(push[0], push[1], u)
    cam = Camera(add3((0.3, 5.0, z - 1.5), handheld(t, 0.05)), (-0.7, 4.7, -3.0), fov=62)
    return sc, cam


def hook_basement(lt, u, gt, p):
    sc, cam = hook_comp(gt, u)
    return frame(sc, cam, zoom=1.08 + 0.12 * u, shake=5 + 4 * u, chroma=2, **GRADE_BASE, vig=0.75)


def hook_zoom_face(lt, u, gt, p):
    swing = 0.35 * math.sin(gt * 2.4)
    gray = A.character(A.GRAY, (-2.0, 0, -5.2), yaw=8, expr='stare', head_pitch=-6)
    sc = SE.basement(bulb=1.0, bulb_swing=swing, ambient=0.07, extra=SE.tied_timmy(t=gt) + gray)
    cam = Camera((-1.6, 5.9, 1.5), (-2.0, 5.75, -5.2), fov=lerp(46, 40, u))
    z = 1.0 + 0.75 * ease_out(lt / 0.3)
    k = max(0.0, 1 - lt / 0.6)
    return frame(sc, cam, zoom=z, shake=38 * k + 6, flash=0.8 * max(0, 1 - lt / 0.18), chroma=int(4 + 14 * k),
                 tint=(1.15, 0.9, 0.88), sat=0.75, contrast=1.25, vig=0.85, fog=0.1)


def hook_black(lt, u, gt, p):
    if lt < 0.16:
        d = hook_zoom_face(0.99, 0.99, 2.49, p)
        d.update(glitch=1.0, flash=0.0)
        return d
    g = 0.0
    for c in (0.42, 0.71):
        if c <= lt < c + 0.07:
            g = 0.8
    return dict(img=Image.new('RGB', (W, H), (0, 0, 0)), glitch=g, static=0.08 + g * 0.4, vig=0, grain=10, fog=0)


def hook_rewind(lt, u, gt, p):
    # fast reverse playback through the story, back to its first frame
    tau = lerp(71.0, 4.05, u ** 0.85)
    d = shot_at(tau, rewind=True)
    d = dict(d)
    d.update(glitch=0.55 + 0.3 * math.sin(lt * 50) ** 2, hud='rewind', chroma=8, static=0.12, tracking=1.0,
             shake=0, flash=0)
    return d


# ================================================================== SETUP

def gray_at_fence(expr='blank', head_yaw=0, color_mul=1.0, head_pitch=-4):
    return A.character(A.GRAY, (2.6, 0, 4.0), yaw=-90, expr=expr, head_yaw=head_yaw, head_pitch=head_pitch,
                       color_mul=color_mul)


def ball(pos):
    return [box(pos, (0.9, 0.9, 0.9), (220, 50, 45), outline=0.7)]


def street_pan(lt, u, gt, p):
    x = lerp(-22, 8, ease(u))
    ph = gt * 6
    tx = lerp(-11, -7, u)
    timmy = A.character(A.TIMMY, (tx, 0, 6), yaw=90, expr='happy', **A.walk(ph))
    bz = 6 + 0.5
    parts = timmy + ball((tx + 1.6, 0.45 + abs(math.sin(gt * 5)) * 1.0, bz)) + gray_at_fence()
    sc = SE.street(False, extra=parts)
    cam = Camera((x, 9, 40), (x + 5, 3.5, 2), fov=66)
    return frame(sc, cam, **GRADE_DAY)


def yard_play(lt, u, gt, p):
    kick = clamp((lt - 0.7) / 0.25)
    tx = lerp(-12, -9.5, ease(clamp(lt / 0.8)))
    leg = 50 * math.sin(kick * math.pi) if kick < 1 else 0
    w = A.walk(gt * 8, 30) if lt < 0.8 else dict(leg_r=-leg, arm_l=20 * math.sin(kick * math.pi))
    timmy = A.character(A.TIMMY, (tx, 0, 6), yaw=80, expr='happy', **w)
    bu = clamp((lt - 0.85) / 0.85)
    bpos = (lerp(tx + 1.4, tx + 11, ease_out(bu)), 0.45 + 2.2 * math.sin(math.pi * bu), lerp(6.3, 4, bu))
    sc = SE.street(False, extra=timmy + ball(bpos) + gray_at_fence())
    cam = Camera(add3((-16 + 2 * u, 4.2, 17), handheld(gt, 0.08)), (-8.5, 2.6, 5), fov=58)
    return frame(sc, cam, **GRADE_DAY)


def gray_house_push(lt, u, gt, p):
    sc = SE.street(False, extra=gray_at_fence())
    z = lerp(42, 27, ease(u))
    cam = Camera((19 - 4 * u, 6.5, z), (19, 5, 0), fov=64)
    return frame(sc, cam, **GRADE_DAY)


def gray_tilt_up(lt, u, gt, p):
    sc = SE.street(False, extra=gray_at_fence())
    ty = lerp(1.0, 6.6, ease(u))
    cam = Camera((-4.5, lerp(1.0, 2.6, u), 5.5), (2.6, ty, 4.0), fov=60)
    return frame(sc, cam, **GRADE_DAY, vig=0.7)


def gray_face_close(lt, u, gt, p):
    sc = SE.street(False, extra=gray_at_fence(p.get('expr', 'blank')))
    cam = Camera((-4.5, 6.0, 4.9), (2.6, 5.6, 4.0), fov=36)
    return frame(sc, cam, zoom=1.0 + 0.15 * u, **GRADE_DAY, vig=0.75)


def timmy_turns(lt, u, gt, p):
    hy = 75 * ease(clamp((lt - 0.4) / 0.7))
    expr = 'happy' if lt < 0.9 else 'worried'
    timmy = A.character(A.TIMMY, (-8, 0, 5), yaw=0, expr=expr, head_yaw=hy)
    sc = SE.street(False, extra=timmy + ball((-9.6, 0.45, 6.0)) + gray_at_fence())
    cam = Camera((-10.5 + 0.5 * u, 3.8, 13 - 1.5 * u), (-8, 3.3, 5), fov=50)
    return frame(sc, cam, **GRADE_DAY)


def fence_wide(lt, u, gt, p):
    timmy = A.character(A.TIMMY, (-9, 0, 4.2), yaw=90, expr='worried', arm_l=10, arm_r=10)
    sc = SE.street(False, extra=timmy + gray_at_fence())
    cam = Camera((-15.5 + 1.5 * u, 5.0, 2.5 - 0.6 * u), (2.6, 4.6, 4.0), fov=50)
    return frame(sc, cam, **GRADE_DAY, vig=0.7)


def gray_eyes(lt, u, gt, p):
    sc = SE.street(False, extra=gray_at_fence('blank'))
    cam = Camera((-3.0, 5.85, 4.1), (2.6, 5.85, 4.0), fov=lerp(22, 17, u))
    return frame(sc, cam, zoom=1.0 + 0.1 * u, **GRADE_DAY, vig=0.85)


def timmy_waves(lt, u, gt, p):
    wave = math.sin(lt * 11) * 25
    up = ease(clamp(lt / 0.3)) * (1 - ease(clamp((lt - 1.3) / 0.4)))
    expr = 'happy' if lt < 1.0 else 'worried'
    timmy = A.character(A.TIMMY, (-8, 0, 5), yaw=90, expr=expr, arm_r=lerp(0, 160, up), roll_r=wave * up)
    sc = SE.street(False, extra=timmy + gray_at_fence())
    cam = Camera((0.5, 4.6, 8.5), (-8, 3.0, 5), fov=lerp(58, 52, u))
    return frame(sc, cam, **GRADE_DAY)


def gray_watches_leave(lt, u, gt, p):
    tp = lv((-8, 0, 5), (-19.5, 0, 1.8), ease(u))
    timmy = A.character(A.TIMMY, tp, yaw=yaw_to((-8, 0, 5), (-19.5, 0, 1.8)), expr='worried', **A.walk(gt * 7))
    hy = lerp(-5, -30, ease(u))  # head follows Timmy (body faces -x)
    gray = A.character(A.GRAY, (2.6, 0, 4.0), yaw=-90, expr='blank', head_yaw=hy)
    sc = SE.street(False, extra=timmy + gray)
    cam = Camera((6.5, 7.8, 6.5), (-12, 3.0, 3.0), fov=56)
    return frame(sc, cam, **GRADE_DAY, bright=lerp(1.0, 0.75, u))


# ================================================================== DISCOVERY

def basement_light_on(gt):
    """Gray's basement window: off, then flickers on at 23.3s; goes out at 57.8s; flickers on at the very end."""
    if gt < 23.3:
        return 0.0
    if gt < 23.7:
        return 1.0 if int(gt * 25) % 3 else 0.0
    if 57.8 <= gt < 115:
        if gt < 58.3:
            return 1.0 if int(gt * 20) % 2 else 0.0
        return 0.0
    if gt >= 115:
        # final beat: flickers back on at 118.6
        if gt < 118.6:
            return 0.0
        k = gt - 118.6
        if k < 0.5:
            return 1.0 if int(k * 22) % 3 == 1 else 0.0
        return 1.0
    return 1.0


def porch_level(gt):
    return flicker(gt, seed=5, rate=9, depth=0.75)


def night_street(lt, u, gt, p):
    sc = SE.street(True, basement_on=basement_light_on(gt), porch=porch_level(gt))
    cam = Camera((lerp(-8, -2, u), 9, 38), (10, 2.5, 0), fov=62)
    return frame(sc, cam, **GRADE_NIGHT)


@lru_cache(maxsize=2)
def window_view(on):
    sc = SE.street(True, basement_on=on, porch=1.0)
    r = Renderer(720, 540, 1)
    return r.render(sc, Camera((-13, 11, 1.8), (12, 1.0, 0.2), fov=34)).convert('RGBA')


def bedroom_window(lt, u, gt, p):
    hy = 10 * math.sin(lt * 1.5)
    timmy = A.character(A.TIMMY, (0.3, 0, -3.6), yaw=180, expr='worried', head_yaw=hy, arm_l=20, arm_r=20)
    sc = SE.bedroom(window_view(True), extra=timmy)
    cam = Camera((1.2, 6.4, lerp(7.5, 6.0, u)), (0, 5.0, -6), fov=62)
    return frame(sc, cam, **GRADE_NIGHT, vig=0.8)


def window_frame_overlay():
    return 'bedroom'


def pov_basement_light(lt, u, gt, p):
    sc = SE.street(True, basement_on=basement_light_on(gt), porch=porch_level(gt))
    cam = Camera((-13, 11, 1.8), (12.5, 1.0, 0.2), fov=lerp(34, 14, ease(u)))
    return frame(sc, cam, **GRADE_NIGHT, overlay='bedroom', vig=0.8)


def porch_sneak(lt, u, gt, p):
    tp = lv((-3.0, 0, 13.2), (5.0, 0, 10.0), u)
    timmy = A.character(A.TIMMY, tp, yaw=yaw_to((-3, 0, 13.2), (5, 0, 10)), expr='worried', lean=22,
                        **{k: v for k, v in A.walk(gt * 6, 24).items()})
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=timmy)
    cam = Camera((17.5, 2.6, 4.5), (3.5, 2.2, 11.5), fov=56)
    return frame(sc, cam, **GRADE_NIGHT)


def lawn_creep(lt, u, gt, p):
    tp = lv((5.0, 0, 9.0), (11.5, 0, 3.6), u)
    w = A.walk(gt * 6, 24)
    timmy = A.character(A.TIMMY, tp, yaw=yaw_to((5, 0, 9), (11.5, 0, 3.6)), expr='worried', lean=25, **w)
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=timmy)
    cam = Camera((tp[0] - 3, 3.2, tp[2] + 13), (tp[0] + 1.0, 2.0, tp[2]), fov=58)
    return frame(sc, cam, **GRADE_NIGHT)


def crouched_timmy(pos, yaw, expr, lean=38, **kw):
    return A.character(A.TIMMY, (pos[0], pos[1] - 0.7, pos[2]), yaw=yaw, expr=expr, lean=lean, leg_l=-60, leg_r=-60,
                       arm_l=50, arm_r=50, **kw)


def kneel_window(lt, u, gt, p):
    timmy = crouched_timmy((13, 0, 2.4), 180, 'worried', head_pitch=-20)
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=timmy)
    cam = Camera((lerp(22.0, 20.5, u), 2.8, 7.5), (12.8, 1.4, 1.2), fov=56)
    return frame(sc, cam, **GRADE_NIGHT)


# ---- views through the cellar window
WIN_CAM = (0.0, 11.3, 11.4)


def drag_gray(gx, gt, stop=False):
    w = A.walk(gt * 4.2, 20) if not stop else {}
    gray = A.character(A.GRAY, (gx, 0, -3.0), yaw=-90, expr='blank', **pose(w, lean=16 if not stop else 0, arm_l=-38,
                                                                              arm_r=-38))
    return gray + SE.bag((gx + 4.2, 0, -3.0), yaw=0)


def window_drag(lt, u, gt, p):
    gx = lerp(5.0, -1.0, u)
    sc = SE.basement(bulb=0.6, green=flicker(gt, 3, 7, 0.3), extra=drag_gray(gx, gt), ambient=0.14, fog=0.02)
    cam = Camera(WIN_CAM, (lerp(1.5, 0.5, u), 2.0, -3.0), fov=lerp(58, 52, u))
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar')


def window_bag_close(lt, u, gt, p):
    gx = lerp(-1.0, -3.2, u)
    sc = SE.basement(bulb=0.6, green=flicker(gt, 3, 7, 0.3), extra=drag_gray(gx, gt), ambient=0.14, fog=0.02)
    cam = Camera((1.5, 10.0, 11.4), (gx + 4.8, 0.8, -3.0), fov=lerp(34, 28, u))
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar')


def window_posters(lt, u, gt, p):
    sc = SE.basement(bulb=0.6, green=flicker(gt, 3, 7, 0.3), extra=drag_gray(-3.2, gt, stop=True), ambient=0.14,
                     fog=0.02)
    tz = lerp(-8.5, 5.0, ease(u))
    cam = Camera((-1.0, 11.0, 11.4), (-11.8, 7.2, tz), fov=34)
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar')


def window_shovel(lt, u, gt, p):
    sc = SE.basement(bulb=0.6, green=flicker(gt, 3, 7, 0.3), extra=drag_gray(-3.2, gt, stop=True), ambient=0.14,
                     fog=0.02)
    cam = Camera(WIN_CAM, (-8.2, 2.4, -10.5), fov=lerp(30, 22, ease(u)))
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar')


def timmy_face_green(lt, u, gt, p):
    timmy = crouched_timmy((13, 0, 2.6), 180, 'scared', head_pitch=-14)
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=timmy)
    sc.add(Light((13, 1.3, 0.8), (150, 255, 110), 2.4, radius=4))
    cam = Camera((13.3, 2.3, 0.3 + 0.2 * u), (13.0, 2.7, 3.0), fov=lerp(64, 56, u))
    return frame(sc, cam, **GRADE_GREEN, heart=0.6, vig=0.85)


def gray_back_turned(head_yaw=0.0, head_pitch=0.0, expr='blank', head_roll=0.0):
    gray = A.character(A.GRAY, (-1.0, 0, -3.0), yaw=180, expr=expr, head_yaw=head_yaw, head_pitch=head_pitch,
                       head_roll=head_roll)
    return gray + SE.bag((2.2, 0, -3.6), yaw=20)


def window_gray_still(lt, u, gt, p):
    sc = SE.basement(bulb=0.6, green=flicker(gt, 3, 7, 0.3), extra=gray_back_turned(), ambient=0.14, fog=0.02)
    cam = Camera(WIN_CAM, (-1.0, 4.0, -3.0), fov=lerp(46, 38, u))
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar')


# ================================================================== SPOTTED

def window_head_turn(lt, u, gt, p):
    hy = 180 * ease(clamp((u - 0.15) / 0.85))
    pitch = 22 * ease(clamp((u - 0.5) / 0.5))
    sc = SE.basement(bulb=0.35, green=flicker(gt, 3, 7, 0.45), extra=gray_back_turned(hy, pitch), ambient=0.14,
                     fog=0.02)
    cam = Camera(WIN_CAM, (-1.0, 5.0, -3.0), fov=lerp(38, 26, ease(u)))
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar', vig=0.85)


def window_stare(lt, u, gt, p):
    sc = SE.basement(bulb=0.35, green=0.9, extra=gray_back_turned(180, 22, head_roll=lerp(0, 12, u)), ambient=0.14,
                     fog=0.02)
    cam = Camera(WIN_CAM, (-1.0, 5.9, -3.0), fov=lerp(22, 19, u))
    return frame(sc, cam, **GRADE_GREEN, overlay='cellar', vig=0.9)


def jumpscare_window(lt, u, gt, p):
    sc = SE.basement(bulb=1.0, green=1.0, extra=gray_back_turned(180, 22, 'stare', head_roll=12), ambient=0.1,
                     fog=0.02)
    cam = Camera(WIN_CAM, (-1.0, 5.75, -3.0), fov=20)
    k = max(0.0, 1 - lt / 0.7)
    return frame(sc, cam, zoom=1.0 + 0.6 * ease_out(lt / 0.12), shake=48 * k + 4, flash=0.85 * max(0, 1 - lt / 0.15),
                 chroma=int(4 + 16 * k), tint=(1.1, 1.0, 0.85), sat=0.8, contrast=1.3, overlay='cellar', vig=0.9,
                 fog=0.05)


def timmy_falls_back(lt, u, gt, p):
    fall = ease_out(clamp(lt / 0.45))
    up = ease(clamp((lt - 1.0) / 0.6))
    if lt < 1.0:
        timmy = A.character(A.TIMMY, (13, lerp(-0.7, -1.5, fall), lerp(2.6, 4.6, fall)), yaw=180, expr='scared',
                            lean=lerp(38, -35, fall), leg_l=-80, leg_r=-60, arm_l=lerp(50, 120, fall),
                            arm_r=lerp(50, 110, fall))
    else:
        timmy = A.character(A.TIMMY, (13, lerp(-1.5, 0, up), 4.6), yaw=lerp(180, 330, up), expr='scared',
                            lean=lerp(-20, 15, up), **A.walk(gt * 12, 40 * up))
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=timmy)
    cam = Camera(add3((20.0, 3.2, 10.0), handheld(gt * 3, 0.15)), (13, 1.6, 3.8), fov=56)
    return frame(sc, cam, **GRADE_NIGHT, shake=10 * (1 - fall) + 4, heart=1.0)


def run_lawn(lt, u, gt, p):
    a, b = (11.5, 0, 6.0), (0.5, 0, 14.0)
    tp = lv(a, b, u)
    timmy = A.character(A.TIMMY, tp, yaw=yaw_to(a, b), expr='scared', **A.run(gt * 15))
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=timmy)
    cam = Camera(add3((tp[0] - 7.5, 3.0, tp[2] + 6.5), handheld(gt * 4, 0.25)), add3(tp, (1, 2.5, -1)), fov=60)
    return frame(sc, cam, **GRADE_NIGHT, shake=7, heart=1.0)


def look_back_light_off(lt, u, gt, p):
    sc = SE.street(True, basement_on=basement_light_on(gt), porch=porch_level(gt))
    cam = Camera(add3((-1.5, 4.0, 15.0), handheld(gt * 2, 0.08)), (13, 1.0, 0.2), fov=lerp(36, 22, ease(u)))
    return frame(sc, cam, **GRADE_NIGHT, heart=1.0)


def door_slam(lt, u, gt, p):
    a, b = (-14.0, 0, 11.5), (-20.0, 0, 1.2)
    tp = lv(a, b, ease(clamp(lt / 1.3)))
    parts = [] if lt > 1.3 else A.character(A.TIMMY, tp, yaw=yaw_to(a, b), expr='scared', **A.run(gt * 15))
    sc = SE.street(True, basement_on=0, porch=porch_level(gt), extra=parts)
    cam = Camera((-17.5, 4.2, 15.5), (-19.5, 3.4, 1.0), fov=58)
    slam = lt > 1.3
    return frame(sc, cam, **GRADE_NIGHT, shake=22 * max(0, 1 - (lt - 1.3) / 0.4) if slam else 3, heart=1.0)


def hall_panting(lt, u, gt, p):
    breath = abs(math.sin(lt * 5.5)) * 0.12
    timmy = A.character(A.TIMMY, (0, 0, -8.9), yaw=0, expr='scared' if lt < 1.1 else 'worried', bob=breath,
                        head_pitch=-6 + 10 * breath, arm_l=-15, arm_r=-15, roll_l=20, roll_r=20)
    sc = SE.hallway(lamp=0.45, extra=timmy)
    cam = Camera((0.8, 4.4, lerp(2.0, -0.5, u)), (0, 3.4, -9.0), fov=56)
    return frame(sc, cam, tint=(0.85, 0.9, 1.15), sat=0.8, contrast=1.1, fog=0.2, heart=0.8)


# ================================================================== KIDNAPPED

def hall_shadow_behind(lt, u, gt, p):
    tp = lv((0, 0, -6.0), (0, 0, -2.0), ease(clamp(lt / 1.6)))
    timmy = A.character(A.TIMMY, tp, yaw=0, expr='worried', **A.walk(gt * 5, 15 * (1 - clamp((lt - 1.6) / 0.2))))
    gu = ease(clamp((lt - 0.3) / 1.5))
    gp = lv((-7.5, 0, -4.8), (-0.6, 0, -4.4), gu)
    gray = A.character(A.GRAY, gp, yaw=lerp(90, 10, gu), expr='blank', color_mul=lerp(0.15, 0.6, gu),
                       **A.walk(gt * 4, 14 * (1 - gu)))
    sc = SE.hallway(lamp=0.35, extra=timmy + gray)
    cam = Camera((0.5, 4.6, lerp(7.0, 5.5, u)), (0, 4.0, -4.0), fov=58)
    return frame(sc, cam, tint=(0.85, 0.9, 1.15), sat=0.75, contrast=1.15, fog=0.25, vig=0.85)


def grabbed(lt, u, gt, p):
    k = ease_out(clamp(lt / 0.15))
    timmy = A.character(A.TIMMY, (0, 0, -2.0), yaw=0, expr='scared', arm_l=60 * k, arm_r=60 * k, lean=-10 * k)
    gray = A.character(A.GRAY, (-0.2, 0, -3.3), yaw=0, expr='stare', arm_l=lerp(0, 75, k), arm_r=lerp(0, 75, k),
                       roll_l=-15 * k, roll_r=-15 * k, lean=12 * k, color_mul=0.45, head_pitch=-20)
    sc = SE.hallway(lamp=0.35, extra=timmy + gray)
    cam = Camera((0.5, 4.8, 5.0), (0, 4.4, -3.0), fov=lerp(58, 40, k))
    black = clamp((lt - 0.35) / 0.2)
    return frame(sc, cam, shake=55, flash=0.7 * max(0, 1 - lt / 0.12), chroma=14, glitch=0.5 if lt < 0.12 else 0,
                 tint=(1.2, 0.85, 0.85), contrast=1.3, black=black, vig=0.9)


def blackout(lt, u, gt, p):
    return dict(img=Image.new('RGB', (W, H), (0, 0, 0)), vig=0, grain=9, fog=0)


def wake_blur(lt, u, gt, p):
    sc, cam = hook_comp(gt, 0.0, gray=False, expr='closed' if lt < 0.9 else 'worried', struggle=0.0)
    # eyelids: open, close, open
    o = 0.0
    if lt < 0.6:
        o = ease(lt / 0.6) * 0.5
    elif lt < 0.9:
        o = lerp(0.5, 0.05, (lt - 0.6) / 0.3)
    else:
        o = lerp(0.05, 1.0, ease((lt - 0.9) / 0.8))
    return frame(sc, cam, blur=lerp(14, 0, ease(u)), lids=o, **GRADE_BASE, vig=0.9)


def tied_matching_hook(lt, u, gt, p):
    # identical framing to the hook; this time nobody is behind him (yet)
    sc, cam = hook_comp(gt, u * 0.6, gray=False, expr='scared', struggle=0.4)
    return frame(sc, cam, zoom=1.08 + 0.12 * u, shake=3, **GRADE_BASE, vig=0.75)


def tied_struggle_close(lt, u, gt, p):
    sc = SE.basement(bulb=flicker(gt, 2, 13, 0.4), bulb_swing=0.35 * math.sin(gt * 2.4),
                     extra=SE.tied_timmy(expr='scared', struggle=1.0, t=gt))
    cam = Camera(add3((0.4, 3.6, 5.5), handheld(gt, 0.06)), (0, 3.2, 0), fov=lerp(46, 40, u))
    return frame(sc, cam, **GRADE_BASE, shake=4, heart=0.9)


def gray_on_stairs(s, gt, moving=True, color_mul=0.25, expr='blank'):
    pos = SE.stair_pos(s)
    w = A.walk(gt * 3.2, 20) if moving else {}
    return A.character(A.GRAY, pos, yaw=0, expr=expr, color_mul=color_mul, **w)


def stairs_door_opens(lt, u, gt, p):
    do = ease(clamp((lt - 0.4) / 0.9))
    gray = gray_on_stairs(0.0, gt, moving=False, color_mul=0.12) if lt > 0.9 else []
    sc = SE.basement(bulb=flicker(gt, 2, 13, 0.4) * 0.6, bulb_swing=0.35 * math.sin(gt * 2.4), door_open=do,
                     door_light=do, extra=SE.tied_timmy(t=gt) + gray)
    cam = Camera((9.3, 2.2, 4.5), (9.5, 8.6, -11.8), fov=lerp(62, 54, u))
    return frame(sc, cam, **GRADE_BASE, vig=0.85, heart=1.0)


def stairs_feet(lt, u, gt, p):
    s = lerp(0.18, 0.45, u)
    sc = SE.basement(bulb=0.5, door_open=1, door_light=1, extra=gray_on_stairs(s, gt, color_mul=0.75))
    pos = SE.stair_pos(s)
    cam = Camera((3.5, pos[1] + 1.4, pos[2] + 2.5), (9.5, pos[1] + 0.9, pos[2] - 0.3), fov=44)
    return frame(sc, cam, **GRADE_BASE, vig=0.85, heart=1.0)


def timmy_looks_stairs(lt, u, gt, p):
    hy = 70 * ease(clamp(lt / 0.7))
    sc = SE.basement(bulb=flicker(gt, 2, 13, 0.4), bulb_swing=0.35 * math.sin(gt * 2.4), door_open=1, door_light=1,
                     extra=SE.tied_timmy(expr='scared', head_yaw=hy, t=gt, struggle=0.2))
    cam = Camera((3.0, 4.2, 6.0 - 0.8 * u), (0, 3.5, 0), fov=46)
    return frame(sc, cam, **GRADE_BASE, heart=1.0)


def gray_halfway(lt, u, gt, p):
    # Gray stops halfway and tilts his head while he waits
    gray = A.character(A.GRAY, SE.stair_pos(0.5), yaw=0, expr='blank', color_mul=0.7, head_roll=lerp(0, 18, ease(u)))
    sc = SE.basement(bulb=0.6, door_open=1, door_light=1, extra=SE.tied_timmy(t=gt) + gray)
    cam = Camera((8.6, 1.6, 3.0), add3(SE.stair_pos(0.5), (0, 5.2, 0)), fov=lerp(40, 28, ease(u)))
    return frame(sc, cam, **GRADE_BASE, vig=0.85, heart=1.0)


POCKET = (1.05, 2.55, 0.45)


def pocket_glow(lt, u, gt, p):
    g = 0.5 + 0.5 * math.sin(lt * 4)
    glow = [box(POCKET, (0.12, 0.3, 0.5), (170, 210, 255), emissive=0.5 + 1.8 * g)]
    sc = SE.basement(bulb=0.5, door_open=1, door_light=0.7,
                     extra=SE.tied_timmy(expr='worried', head_pitch=-30, head_yaw=20, t=gt) + glow)
    sc.add(Light(add3(POCKET, (0.6, 0.3, 0.5)), (150, 200, 255), 1.4 * g, radius=2.0))
    cam = Camera((4.0, 3.8, 4.4), POCKET, fov=lerp(48, 40, u))
    return frame(sc, cam, **GRADE_BASE, heart=1.0)


def phone_parts(pos, screen=None, tilt=0.0):
    from engine3d import T, S, RX, Box
    M = T(*pos) @ RX(-tilt)
    parts = [Box(M @ S(0.55, 0.08, 1.0), (25, 25, 30), outline=0.6)]
    if screen is not None:
        from engine3d import Quad
        import numpy as np
        P = np.array([[-0.24, 0.05, -0.45, 1], [0.24, 0.05, -0.45, 1], [0.24, 0.05, 0.45, 1], [-0.24, 0.05, 0.45, 1]])
        Pw = (M @ P.T).T[:, :3]
        parts.append(Quad(Pw, screen, lit=False, bias=0.3))
    return parts


def phone_out(lt, u, gt, p):
    k = ease(clamp(lt / 1.4))
    pos = lv(POCKET, (0.35, 2.75, 1.25), k)
    sc = SE.basement(bulb=0.5, door_open=1, door_light=0.7,
                     extra=SE.tied_timmy(expr='worried', head_pitch=-30, t=gt, struggle=0.6 * (1 - k)) +
                     phone_parts(pos, phone_screen('lock') if k > 0.6 else None, tilt=0.2))
    sc.add(Light(add3(pos, (0, 0.8, 0.3)), (150, 200, 255), 1.4, radius=2.2))
    cam = Camera((0.6, 5.0, 5.2), (0.2, 2.9, 0.4), fov=42)
    return frame(sc, cam, **GRADE_BASE, heart=1.0)


def phone_lap_close(lt, u, gt, p):
    pos = (0.35, 2.75, 1.25)
    sc = SE.basement(bulb=0.4, door_open=1, door_light=0.6,
                     extra=SE.tied_timmy(expr='worried', head_pitch=-35, t=gt) +
                     phone_parts(pos, phone_screen('lock'), tilt=0.2))
    sc.add(Light(add3(pos, (0, 1.0, 0.3)), (150, 200, 255), 1.8, radius=2.6))
    cam = Camera((0.3, lerp(5.6, 5.0, u), 2.6), pos, fov=lerp(40, 32, u))
    return frame(sc, cam, **GRADE_BASE, heart=1.0)


def stairs_wide_descend(lt, u, gt, p):
    s = lerp(0.5, 0.78, u)
    sc = SE.basement(bulb=flicker(gt, 2, 13, 0.4), bulb_swing=0.35 * math.sin(gt * 2.4), door_open=1, door_light=1,
                     extra=SE.tied_timmy(expr='scared', head_yaw=60, t=gt) + gray_on_stairs(s, gt, color_mul=0.8))
    cam = Camera((-6.5, 7.0, lerp(9.0, 8.0, u)), (4.0, 3.2, -5.5), fov=60)
    return frame(sc, cam, **GRADE_BASE, heart=1.0)


# ================================================================== THE CALL (phone UI)

@lru_cache(maxsize=64)
def phone_screen(state, text=''):
    w, h = 360, 720
    im = Image.new('RGBA', (w, h), (12, 14, 22, 255))
    d = ImageDraw.Draw(im)
    f = A.font
    if state == 'lock':
        for y in range(h):
            c = int(20 + 40 * y / h)
            d.line([(0, y), (w, y)], fill=(c // 2, c // 2, c, 255))
        d.text((w / 2, 150), '2:13', font=f(A.FONT_BOLD, 96), fill=(240, 240, 250), anchor='mm')
        d.text((w / 2, 225), 'Saturday', font=f(A.FONT_SEMI, 30), fill=(200, 200, 220), anchor='mm')
        d.rounded_rectangle([110, 640, 250, 650], 5, fill=(220, 220, 230))
    return im


def draw_phone_ui(state, lt, gt):
    """Full-frame phone insert, drawn at 1080x1920."""
    bg = _phone_bg()
    img = bg.copy()
    d = ImageDraw.Draw(img, 'RGBA')
    f = A.font
    # hand (blocky) holding the phone
    skin = (232, 192, 142)
    px0, py0, px1, py1 = 230, 330, 850, 1650
    d.rectangle([px0 - 60, 1150, px0 + 60, 1700], fill=skin)
    d.rectangle([px1 - 40, 1050, px1 + 70, 1450], fill=skin)
    d.rounded_rectangle([px0, py0, px1, py1], 70, fill=(20, 20, 24))
    sx0, sy0, sx1, sy1 = px0 + 28, py0 + 28, px1 - 28, py1 - 28
    d.rounded_rectangle([sx0, sy0, sx1, sy1], 48, fill=(16, 18, 28))
    cx = (sx0 + sx1) / 2
    d.rounded_rectangle([cx - 70, sy0 + 18, cx + 70, sy0 + 50], 16, fill=(0, 0, 0))
    d.text((sx0 + 50, sy0 + 34), '2:13', font=f(A.FONT_BOLD, 34), fill=(230, 230, 240), anchor='lm')
    d.text((sx1 - 50, sy0 + 34), '▮▮▮ 12%', font=f(A.FONT_BOLD, 28), fill=(230, 80, 70), anchor='rm')
    if state == 'dial':
        presses = [0.3, 0.9, 1.5]
        digits = '911'
        n = sum(1 for tp in presses if lt >= tp)
        d.text((cx, sy0 + 230), digits[:n] if n else ' ', font=f(A.FONT_SEMI, 120), fill=(245, 245, 250), anchor='mm')
        keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#']
        active = None
        for i, tp in enumerate(presses):
            if tp <= lt < tp + 0.22:
                active = digits[i]
        for i, k in enumerate(keys):
            r_, c_ = divmod(i, 3)
            kx = cx + (c_ - 1) * 165
            ky = sy0 + 470 + r_ * 160
            on = (k == active)
            d.ellipse([kx - 64, ky - 64, kx + 64, ky + 64], fill=(230, 230, 240) if on else (52, 54, 66))
            d.text((kx, ky), k, font=f(A.FONT_SEMI, 64), fill=(20, 20, 30) if on else (240, 240, 245), anchor='mm')
        d.ellipse([cx - 66, sy1 - 190, cx + 66, sy1 - 58], fill=(40, 190, 80))
        d.text((cx, sy1 - 124), '✆', font=f('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 70), fill=(255, 255, 255),
               anchor='mm')
        # thumb
        if active is not None:
            i = digits.index(active) if active != '1' else 0
            k_i = keys.index(active)
            r_, c_ = divmod(k_i, 3)
            kx, ky = cx + (c_ - 1) * 165, sy0 + 470 + r_ * 160
            d.rectangle([kx - 10, ky + 20, kx + 130, ky + 520], fill=skin)
            d.rectangle([kx - 10, ky + 20, kx + 130, ky + 60], fill=(205, 165, 120))
    elif state in ('calling', 'connected'):
        d.ellipse([cx - 120, sy0 + 200, cx + 120, sy0 + 440], fill=(200, 40, 45))
        d.text((cx, sy0 + 320), 'SOS', font=f(A.FONT_BLACK, 76), fill=(255, 255, 255), anchor='mm')
        d.text((cx, sy0 + 530), '911', font=f(A.FONT_BOLD, 110), fill=(245, 245, 250), anchor='mm')
        if state == 'calling':
            dots = '.' * (1 + int(lt * 3) % 3)
            d.text((cx, sy0 + 630), 'Calling' + dots, font=f(A.FONT_SEMI, 46), fill=(180, 185, 200), anchor='mm')
        else:
            secs = 4 + int(lt)
            d.text((cx, sy0 + 630), f'Emergency  00:{secs:02d}', font=f(A.FONT_SEMI, 46), fill=(120, 230, 140),
                   anchor='mm')
            # voice level bars (Timmy whispering)
            for i in range(9):
                hgt = 10 + 50 * abs(math.sin(gt * 9 + i * 1.3)) * (0.6 + 0.4 * math.sin(i))
                x = cx - 160 + i * 40
                d.rectangle([x, sy0 + 730 - hgt, x + 22, sy0 + 730 + hgt], fill=(120, 230, 140))
        for i, (lab, col) in enumerate((('mute', (52, 54, 66)), ('keypad', (52, 54, 66)), ('speaker', (52, 54, 66)))):
            kx = cx + (i - 1) * 170
            ky = sy0 + 930
            d.ellipse([kx - 60, ky - 60, kx + 60, ky + 60], fill=col)
            d.text((kx, ky + 95), lab, font=f(A.FONT_SEMI, 30), fill=(200, 200, 210), anchor='mm')
        d.ellipse([cx - 70, sy1 - 200, cx + 70, sy1 - 60], fill=(220, 50, 50))
        d.rectangle([cx - 40, sy1 - 138, cx + 40, sy1 - 122], fill=(255, 255, 255))
        if state == 'calling':
            pr = (lt * 1.4) % 1.0
            rr = 120 + 90 * pr
            d.ellipse([cx - rr, sy0 + 320 - rr, cx + rr, sy0 + 320 + rr], outline=(255, 80, 80, int(200 * (1 - pr))),
                      width=8)
    # screen glare
    d.polygon([(sx0, sy0 + 200), (sx0 + 200, sy0), (sx0 + 320, sy0), (sx0, sy0 + 320)], fill=(255, 255, 255, 12))
    return img


@lru_cache(maxsize=1)
def _phone_bg():
    sc, cam = hook_comp(80.0, 0.0, gray=False)
    img = R.render(sc, cam)
    return img.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(v * 0.6))


def phone_dial(lt, u, gt, p):
    return dict(img=draw_phone_ui('dial', lt, gt), zoom=1.0 + 0.05 * u, shake=2, vig=0.7, fog=0, heart=1.0)


def phone_ringing(lt, u, gt, p):
    return dict(img=draw_phone_ui('calling', lt, gt), zoom=1.05 + 0.06 * u, shake=3, vig=0.75, fog=0, heart=1.0)


def phone_connected(lt, u, gt, p):
    return dict(img=draw_phone_ui('connected', lt, gt), zoom=1.1 + 0.06 * u, shake=3, vig=0.75, fog=0, heart=1.0)


def whisper_close(lt, u, gt, p):
    talk = int(gt * 7) % 2 == 0
    expr = 'whisper' if talk else 'worried'
    pos = (0.35, 2.75, 1.25)
    sc = SE.basement(bulb=0.45, bulb_swing=0.35 * math.sin(gt * 2.4), door_open=1, door_light=0.6,
                     extra=SE.tied_timmy(expr=expr, head_pitch=-22, t=gt) + phone_parts(pos, phone_screen('lock'), 0.2))
    sc.add(Light((0.3, 3.0, 2.0), (150, 200, 255), 1.6, radius=3.0))
    fov = 50 if p.get('line', 0) == 0 else 42
    cam = Camera(add3((0.6, 3.6, 4.6), handheld(gt, 0.04)), (0, 3.4, 0), fov=lerp(fov, fov - 4, u))
    return frame(sc, cam, **GRADE_BASE, vig=0.85, heart=1.0)


def gray_floor_behind(lt, u, gt, p):
    a, b = (9.5, 0, -1.6), (4.0, 0, -6.5)
    gp = lv(a, b, u)
    gray = A.character(A.GRAY, gp, yaw=yaw_to(a, b), expr='blank', color_mul=0.8, **A.walk(gt * 3.2, 20))
    sc = SE.basement(bulb=flicker(gt, 2, 13, 0.4), bulb_swing=0.35 * math.sin(gt * 2.4), door_open=1, door_light=0.8,
                     extra=SE.tied_timmy(expr='whisper', head_pitch=-22, t=gt) + gray)
    cam = Camera((-3.5, 4.2, 10.0 - u), (3.0, 3.2, -4.0), fov=58)
    return frame(sc, cam, **GRADE_BASE, vig=0.8, heart=1.0)


def shadow_over_timmy(lt, u, gt, p):
    # the exact hook shot: the payoff (the hook's 1.5 s maps onto these 2 s)
    sc, cam = hook_comp(gt, u)
    return frame(sc, cam, zoom=1.08 + 0.12 * u, shake=5 + 4 * u, chroma=2, **GRADE_BASE, vig=0.75, heart=1.0)


# ================================================================== JUST IN TIME

def gray_reaches(lt, u, gt, p):
    k = ease(u)
    gp = lv((-2.4, 0, -5.2), (-2.0, 0, -2.6), ease(clamp(lt / 1.2)))
    gray = A.character(A.GRAY, gp, yaw=30, expr='blank', arm_r=lerp(0, 95, k), arm_l=lerp(0, 50, k), head_pitch=-20,
                       lean=10 * k, color_mul=lerp(0.75, 1.0, k))
    sc = SE.basement(bulb=flicker(gt, 2, 13, 0.4), bulb_swing=0.35 * math.sin(gt * 2.4), door_open=1, door_light=0.5,
                     extra=SE.tied_timmy(expr='scared', t=gt, struggle=0.8) + gray)
    cam = Camera(add3((-5.5, 4.6, lerp(8.0, 6.8, u)), handheld(gt, 0.05)), (-0.8, 4.4, -2), fov=lerp(62, 56, u))
    return frame(sc, cam, **GRADE_BASE, vig=0.85, shake=3 + 4 * u, heart=1.0)


def police_arrive(lt, u, gt, p):
    k = ease_out(clamp(lt / 1.4))
    c1, red1 = SE.police_car((lerp(48, 21, k), 0, 21.5), yaw=0, phase=gt * 2.2)
    c2, _ = SE.police_car((lerp(-40, 6, ease_out(clamp((lt - 0.2) / 1.5))), 0, 25.0), yaw=180, phase=gt * 2.2 + 0.5)
    sc = SE.street(True, basement_on=1, porch=porch_level(gt), extra=c1 + c2,
                   lights=SE.police_lights((21, 0, 21.5), gt * 2.2, 3.0, 16) + SE.police_lights((6, 0, 25), gt * 2.2 + 0.5,
                                                                                               3.0, 16))
    cam = Camera(add3((4.0, 5.0, 40.0), handheld(gt * 2, 0.1)), (20, 2.0, 19), fov=58)
    return frame(sc, cam, **GRADE_NIGHT, police=0.9, police_phase=gt * 2.2, shake=26 * max(0, 1 - lt / 0.5) + 3,
                 flash=(0.6 * max(0, 1 - lt / 0.2), (255, 60, 60)))


def door_burst(lt, u, gt, p):
    do = ease_out(clamp((lt - 0.08) / 0.15))
    cops = []
    if lt > 0.2:
        cops = A.character(A.COP, SE.stair_pos(0.02), yaw=0, expr='cop', arm_r=80, arm_l=70, color_mul=0.5)
    gray = A.character(A.GRAY, (-0.6, 0, -3.0), yaw=lerp(10, 90, ease(clamp(lt / 0.6))), expr='blank', arm_r=40)
    sc = SE.basement(bulb=0.7, door_open=do, door_light=do, police=do, police_phase=gt * 2.2,
                     extra=SE.tied_timmy(expr='scared', t=gt) + gray + cops)
    cam = Camera((1.2, 2.8, 2.6), (9.5, 8.4, -11.5), fov=52)
    return frame(sc, cam, **GRADE_BASE, police=0.6, police_phase=gt * 2.2,
                 shake=30 * max(0, 1 - abs(lt - 0.15) / 0.5) + 3, flash=(0.5 * max(0, 1 - abs(lt - 0.15) / 0.2),
                                                                         (255, 255, 255)))


def police_rush(lt, u, gt, p):
    s1 = lerp(0.1, 1.0, ease(clamp(lt / 1.6)))
    s2 = lerp(0.0, 0.8, ease(clamp((lt - 0.3) / 1.6)))
    c1 = A.character(A.COP, SE.stair_pos(s1), yaw=0, expr='cop', **pose(A.run(gt * 12), arm_r=80))
    c2 = A.character(A.COP2, SE.stair_pos(s2), yaw=0, expr='cop', **pose(A.run(gt * 12 + 1), arm_r=80))
    gray = A.character(A.GRAY, (-0.6, 0, -3.0), yaw=90, expr='blank', head_yaw=-10)
    flash = Light(add3(SE.stair_pos(s1), (0, 4.5, 1.5)), (255, 250, 220), 2.2, radius=10, spot_dir=(-0.6, -0.5, 0.7),
                  spot_cos=0.8, spot_soft=0.15)
    sc = SE.basement(bulb=0.7, door_open=1, door_light=1, police=1.0, police_phase=gt * 2.2, flash_light=flash,
                     extra=SE.tied_timmy(expr='worried', t=gt) + gray + c1 + c2)
    cam = Camera(add3((-5.0, 8.0, 10.5), handheld(gt * 3, 0.12)), (4.0, 3.0, -4.0), fov=62)
    return frame(sc, cam, **GRADE_BASE, police=0.7, police_phase=gt * 2.2, shake=5)


def arrest(lt, u, gt, p):
    gp = lv((-0.6, 0, -3.0), (3.5, 0, -2.0), ease(u))
    w = A.walk(gt * 4, 14)
    gray = A.character(A.GRAY, gp, yaw=80, expr='blank', arm_l=-30, arm_r=-30, roll_l=-20, roll_r=-20,
                       head_yaw=lerp(0, -80, ease(clamp((u - 0.5) / 0.4))), leg_l=w['leg_l'], leg_r=w['leg_r'])
    c1 = A.character(A.COP, add3(gp, (0.5, 0, 2.2)), yaw=80, expr='cop', **pose(A.walk(gt * 4, 14), arm_l=45))
    c2 = A.character(A.COP2, add3(gp, (-0.2, 0, -2.2)), yaw=80, expr='cop', **pose(A.walk(gt * 4 + 1, 14), arm_r=45))
    sc = SE.basement(bulb=0.8, door_open=1, door_light=1, police=1.0, police_phase=gt * 2.2,
                     extra=SE.tied_timmy(expr='relief', t=gt) + gray + c1 + c2)
    cam = Camera((lerp(8.5, 7.5, u), 5.4, lerp(7.0, 6.0, u)), add3(gp, (0, 4.2, 0)), fov=56)
    return frame(sc, cam, **GRADE_BASE, police=0.6, police_phase=gt * 2.2)


# ================================================================== ENDING

def blanket_safe(lt, u, gt, p):
    timmy = A.character(A.TIMMY, (7.0, 0.1, 15.6), yaw=10, expr='relief', sit=True, blanket=True, arm_l=60, arm_r=60)
    curb = [box((7.0, 0.5, 15.4), (3.5, 1.0, 2.0), (90, 90, 95))]
    cop = A.character(A.COP, (9.6, 0, 15.2), yaw=-60, expr='cop', arm_l=20)
    car, _ = SE.police_car((16, 0, 21.0), yaw=0, phase=gt * 2.2)
    car2, _ = SE.police_car((28, 0, 23.0), yaw=20, phase=gt * 2.2 + 0.5)
    sc = SE.street(True, basement_on=basement_light_on(gt), porch=0.0, extra=timmy + curb + cop + car + car2,
                   lights=SE.police_lights((16, 0, 21), gt * 2.2, 2.6, 14) + SE.police_lights((28, 0, 23), gt * 2.2 + 0.5,
                                                                                               2.0, 14))
    cam = Camera((lerp(3.0, 4.5, u), 4.0, lerp(26.0, 24.5, u)), (8.5, 3.0, 13.0), fov=50)
    return frame(sc, cam, **GRADE_NIGHT, police=0.45, police_phase=gt * 2.2)


def final_flicker(lt, u, gt, p):
    car, _ = SE.police_car((16, 0, 21.0), yaw=0, phase=gt * 2.2)
    on = basement_light_on(gt)
    sc = SE.street(True, basement_on=on, porch=0.0, extra=car,
                   lights=SE.police_lights((16, 0, 21), gt * 2.2, 2.0, 14))
    cam = Camera((lerp(6.0, 9.0, ease(u)), 2.6, lerp(17.0, 11.0, ease(u))), (13.0, 1.0, 0.2), fov=lerp(40, 30, u))
    return frame(sc, cam, **GRADE_NIGHT, police=0.25 * (1 - u), police_phase=gt * 2.2, vig=0.85)


# ================================================================== dispatcher

_SHOT_FUNCS = {name: globals()[name] for _, _, name, _ in SHOTS}


def shot_at(t, rewind=False):
    for a, b, name, params in SHOTS:
        if a <= t < b or (b == SHOTS[-1][1] and t >= b):
            lt = t - a
            u = clamp(lt / (b - a))
            d = _SHOT_FUNCS[name](lt, u, t, params)
            d['shot'] = name
            return d
    raise ValueError(t)
