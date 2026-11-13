"""The 30-second timeline. `frame(i)` returns the finished uint8 RGB frame i (0..899).

Scenes (seconds):
  0-3   light line sweeps across and reveals the phone silhouette
  3-7   slow rotation, light gliding over the titanium edge
  7-11  push into the camera plateau, lenses light up one by one
  11-15 screen turns on (animated wallpaper), bezels shrink
  15-19 montage: chip / battery / rain / night photo (1 s each)
  19-24 360-degree spin, lands front-facing, particle burst
  24-28 title card
  28-30 fade to black + fan-made disclaimer
"""
import math

import numpy as np
from PIL import Image

import captions
import phone3d as P
import screens as S
from common import (_box_axis, FPS, H, W, ORANGE, TI_BLUE, TI_BLUE_HI, blur, ease_in_out, ease_in_out_cubic,
                    ease_in_out_sine, ease_out_cubic, ease_out_quart, finish, font, lin, pixel_grid,
                    quantize, smoothstep, text_layer, vignette, zoom)

f32 = np.float32
SS = 2  # supersampling for the 3D renders

# Transition / sync times shared with the audio
FLASH_TIMES = (3.0, 19.0, 24.0)
WHIP_TIMES = (7.0, 11.0, 15.0)
LENS_TIMES = (7.80, 8.60, 9.40)
LANDING = 22.30


# ----------------------------------------------------------------------------- helpers
def backdrop(t, glow=1.0, bok=1.0, center=(W / 2, H * 0.47), warm=0.0):
    xs, ys = pixel_grid()
    d = np.sqrt(((xs - center[0]) / 900) ** 2 + ((ys - center[1]) / 620) ** 2)
    g = np.exp(-d ** 2 * 1.6)
    img = (g[..., None] * (np.array([0.0026, 0.0042, 0.0115], f32) + ORANGE * 0.0012 * warm)) * glow
    if bok > 0:
        img += S.bokeh(t, level=bok)
    return img


def comp(bg, rgb, a):
    return bg * (1 - a[..., None]) + rgb


def dof(img, depth, focus, rng_mm, sigma=7.0):
    coc = np.clip(np.abs(depth - focus) / rng_mm, 0, 1)[..., None]
    return img * (1 - coc) + blur(img, sigma) * coc


def motion_blur_h(img, length):
    """Smooth horizontal motion blur (two box passes ~ triangular kernel of the given length)."""
    r = int(round(length / 4))
    if r < 1:
        return img
    return _box_axis(_box_axis(img, r, 1), r, 1)


def sweep_phi(t, t0, t1, a=-1.7, b=1.7):
    return a + (b - a) * ease_in_out_sine(lin(t, t0, t1))


# ----------------------------------------------------------------------------- scene 1: 0-3 s
S1_POSE = (214.0, -6.0, -14.0)


def scene1(t):
    k = ease_in_out_sine(t / 3.0)
    R = P.rot(*S1_POSE)
    cam = P.Camera((0, 0, 730 - 60 * k), (0, 0, 0), fov=22)
    line_x = -30 + (W + 100) * ease_in_out_sine(lin(t, 0.20, 2.30))
    level = 1.0 + 0.5 * ease_in_out(lin(t, 2.3, 3.0))
    sweep_i = 7.0 * (1 - 0.8 * lin(t, 1.9, 2.6))
    st = dict(rig=P.silhouette_rig(level), ambient=(0.0006, 0.0008, 0.0016), back_albedo=0.5,
              sweep=dict(phi=-1.4 + 2.8 * line_x / W, I=sweep_i, w=0.07))
    rgb, a, e, d = P.render(cam, R, np.zeros(3, f32), st, ss=SS)
    xs, ys = pixel_grid()
    reveal = smoothstep(line_x + 30, line_x - 200, xs)
    img = rgb * reveal[..., None]
    scan = np.exp(-((xs - line_x) / 70) ** 2) * a
    img += scan[..., None] * np.array([0.10, 0.16, 0.30], f32)
    glow_k = ease_in_out(lin(t, 1.2, 3.0))
    img += backdrop(t, glow=0.8 * glow_k, bok=0.0)
    vis = lin(t, 0.15, 0.45) * (1 - lin(t, 1.95, 2.25))
    img += S.light_line(line_x, vis)
    return img, dict(bloom=dict(threshold=0.6, strength=0.9))


# ----------------------------------------------------------------------------- scene 2: 3-7 s
def scene2(t):
    lt = t - 3.0
    k = ease_in_out_sine(lt / 4.0)
    yaw = S1_POSE[0] - 76 * k
    pitch = S1_POSE[1] + 3 * k
    roll = S1_POSE[2] + 7 * k
    R = P.rot(yaw, pitch, roll)
    cam = P.Camera((0, 0, 670 - 95 * k), (0, 0, 0), fov=22)
    gy = (P.HY + 30) - (2 * P.HY + 60) * ease_in_out_sine(lin(lt, 0.6, 3.4))
    st = dict(rig=P.studio_rig(), sweep=dict(phi=sweep_phi(lt, 0.5, 3.7, -1.9, 1.6), I=9.0, w=0.05),
              glide=dict(y=gy, w=9.0, I=2.2))
    rgb, a, e, d = P.render(cam, R, np.zeros(3, f32), st, ss=SS)
    img = comp(backdrop(t, glow=1.0, bok=0.8), rgb, a)
    img += S.dust(t, level=0.5)
    return img, dict(bloom=dict(threshold=0.7, strength=0.7))


# ----------------------------------------------------------------------------- scene 3: 7-11 s
def lens_glow(t):
    out = []
    for T in LENS_TIMES:
        x = t - T
        g = ease_out_cubic(lin(x, 0.0, 0.30)) + (0.8 * math.exp(-x / 0.18) if x >= 0 else 0.0)
        out.append(g * (0.92 + 0.08 * math.sin(t * 9 + T)))
    return out


def scene3(t):
    lt = t - 7.0
    k = ease_in_out_sine(lt / 4.0)
    R = P.rot(191 + 7 * k, 12 - 5 * k, -7 + 3 * k)
    bump = R @ np.array([P.BCX, P.BCY, P.ZB], f32)
    dist = 340 - 232 * k
    cam = P.Camera(bump + np.array([0, 0, dist], f32), bump, fov=22)
    st = dict(rig=P.studio_rig(key=0.9, side=0.8), lens_glow=lens_glow(t),
              sweep=dict(phi=sweep_phi(lt, 2.9, 3.9, -1.2, 1.4), I=8.0, w=0.05))
    rgb, a, e, d = P.render(cam, R, np.zeros(3, f32), st, ss=SS)
    img = comp(backdrop(t, glow=0.8, bok=0.6), rgb, a)
    img = dof(img, d, dist, dist * 0.55, sigma=6 + 4 * k)
    return img, dict(bloom=dict(threshold=0.6, strength=0.8, radii=(5, 18, 60)))


# ----------------------------------------------------------------------------- scene 4: 11-15 s
def scene4(t):
    lt = t - 11.0
    k = ease_in_out_sine(lt / 4.0)
    R = P.rot(-14 + 11 * k, 5 - 3 * k, 0.0)
    cam = P.Camera((0, 0, 615 - 60 * k), (0, 0, 0), fov=22, shift=(0, -26))
    on = ease_out_cubic(lin(lt, 0.45, 0.85))
    flash = 0.6 * math.exp(-(lt - 0.45) / 0.22) if lt >= 0.45 else 0.0
    bezel = 4.7 - (4.7 - P.SCREEN_MIN_BEZEL) * ease_in_out_cubic(lin(lt, 1.05, 2.65))
    ui = ease_in_out(lin(lt, 1.25, 1.85))
    boost = 1 + 0.30 * ease_in_out(lin(lt, 3.0, 3.8))
    tex = S.lock_screen(t, ui)
    st = dict(rig=P.studio_rig(key=0.8), front_refl=0.18 + 0.30 * on,
              sweep=dict(phi=sweep_phi(lt, 2.2, 3.6, 1.6, -1.6), I=7.0, w=0.05),
              screen=dict(tex=tex, bezel=bezel, bright=0.72 * on * (1 + flash) * boost))
    rgb, a, e, d = P.render(cam, R, np.zeros(3, f32), st, ss=SS)
    bg = backdrop(t, glow=1.0 + 0.8 * on, bok=0.7, center=(W / 2, H / 2 - 26))
    img = comp(bg, rgb, a)
    # light spill from the screen onto the darkness behind
    img += blur(e, 70) * 0.28 * on
    return img, dict(bloom=dict(threshold=0.8, strength=0.45))


# ----------------------------------------------------------------------------- scene 5: montage
_RAIN = None


def _rain_assets():
    global _RAIN
    if _RAIN is None:
        R = P.rot(203, 16, -24)
        cam = P.Camera((0, 0, 560), (0, 0, 0), fov=22, shift=(40, -10))
        st = dict(rig=P.studio_rig(key=0.35, front=0.5, side=0.6, top=0.4, rim_warm=1.2, rim_cool=1.3),
                  back_albedo=0.7, sweep=dict(phi=0.7, I=5.0, w=0.08))
        rgb, a, e, d = P.render(cam, R, np.zeros(3, f32), st, ss=SS)
        dark, light = S.droplets_layer(a)
        ys, xs = np.nonzero(a > 0.99)
        sel = np.random.default_rng(3).integers(0, ys.size, 6000)
        _RAIN = dict(rgb=rgb, a=a, dark=dark, light=light, pts=(ys[sel], xs[sel]))
    return _RAIN


def rain_shot(tl, t):
    A = _rain_assets()
    xs, ys = pixel_grid()
    bg = (np.array([0.0020, 0.0035, 0.0085], f32) * (1 - ys / H * 0.6)[..., None]
          + S.bokeh(t, n=9, seed=17, level=1.2))
    ph = A["rgb"] * (1 - 0.55 * A["dark"])[..., None] + A["light"][..., None] * np.array([0.10, 0.13, 0.18], f32)
    # a glint racing across the wet glass
    gx = -300 + 2400 * tl
    glint = np.exp(-(((xs - gx) + 0.6 * (ys - H / 2)) / 90) ** 2) * A["a"]
    ph += glint[..., None] * (0.05 + 0.6 * A["light"][..., None]) * np.array([0.7, 0.8, 1.0], f32)
    img = comp(bg, ph, A["a"])
    img += S.splashes(tl, A["pts"])
    img = zoom(img, 1.0 + 0.05 * tl)
    img += S.rain_streaks(tl)
    return img


def night_shot(tl, t):
    R = P.rot(-9, 3, 4)
    cam = P.Camera((0, 0, 585 - 30 * tl), (0, 0, 0), fov=22, shift=(0, -50))
    kk = ease_in_out_cubic(lin(tl, 0.08, 0.80))
    tex = S.night_screen(kk)
    st = dict(rig=P.studio_rig(key=0.7), screen=dict(tex=tex, bezel=P.SCREEN_MIN_BEZEL, bright=0.95),
              sweep=dict(phi=0.9, I=3.0, w=0.06))
    rgb, a, e, d = P.render(cam, R, np.zeros(3, f32), st, ss=SS)
    img = comp(backdrop(t, glow=1.0 + kk, bok=0.5, center=(W / 2, H / 2 - 20)), rgb, a)
    img += blur(e, 70) * (0.2 + 0.35 * kk)
    return img


def scene5(t):
    lt = t - 15.0
    shot = min(3, int(lt + 1e-9))
    tl = lt - shot
    if shot == 0:
        img = S.chip_frame(tl)
    elif shot == 1:
        img = S.battery_frame(tl)
    elif shot == 2:
        img = rain_shot(tl, t)
    else:
        img = night_shot(tl, t)
    punch = 1.0 + 0.05 * (1 - ease_out_cubic(lin(tl, 0.0, 0.18)))
    img = zoom(img, punch)
    return img, dict(bloom=dict(threshold=0.7, strength=0.65))


# ----------------------------------------------------------------------------- scene 6: 19-24 s
def scene6_pose(lt):
    spin = ease_out_quart(lin(lt, 0.0, LANDING - 19.0))
    app = ease_out_cubic(lin(lt, 0.0, LANDING - 19.0))
    yaw = -360.0 * (1 - spin)
    pitch = 16.0 * (1 - app)
    roll = -24.0 * (1 - app)
    push = ease_in_out_sine(lin(lt, LANDING - 19.0, 5.0))
    dist = 1550 - 920 * app - 55 * push
    pos = np.array([0, -60 * (1 - app), 0], f32)
    return P.rot(yaw, pitch, roll), pos, dist


def scene6(t):
    lt = t - 19.0
    R, pos, dist = scene6_pose(lt)
    cam = P.Camera((0, 0, dist), (0, 0, 0), fov=22, shift=(0, -22))
    tex = S.lock_screen(t, 1.0)
    gy = (P.HY + 30) - (2 * P.HY + 60) * ease_in_out_sine(lin(lt, 3.5, 4.7))
    st = dict(rig=P.studio_rig(), screen=dict(tex=tex, bezel=P.SCREEN_MIN_BEZEL, bright=0.75),
              sweep=dict(phi=sweep_phi(lt, 3.6, 4.7, -1.6, 1.6), I=8.0, w=0.05),
              glide=dict(y=gy, w=9.0, I=1.6 * lin(lt, 3.4, 3.6)))
    rgb, a, e, d = P.render(cam, R, pos, st, ss=SS)
    cx, cy, _ = cam.project(pos[None])
    origin = (float(cx[0]), float(cy[0]))
    tau = t - LANDING
    behind, front = S.particles(tau, origin=origin)
    landed = ease_in_out(lin(tau, -0.1, 0.4))
    bg = backdrop(t, glow=1.0 + 1.2 * landed, bok=0.8, center=origin, warm=landed)
    bg += behind
    img = comp(bg, rgb, a)
    img += front
    img += blur(e, 70) * 0.25
    img += S.dust(t, level=0.8)
    return img, dict(bloom=dict(threshold=0.7, strength=0.7))


# ----------------------------------------------------------------------------- scene 7/8: 24-30 s
def scene7(t):
    lt = t - 24.0
    fade = 1 - ease_in_out(lin(t, 28.0, 28.7))
    img = backdrop(t, glow=1.6 * fade, bok=0.7 * fade, center=(W / 2, H * 0.46), warm=1.0)
    img += S.dust(t, level=0.6 * fade)
    tau = t - LANDING
    behind, front = S.particles(tau, origin=(W / 2, H / 2 - 22))
    img += (behind + front) * fade * (1 - lin(lt, 0, 1.2))
    return img, dict(bloom=dict(threshold=0.7, strength=0.6))


_TITLE = {}


def _title_layers():
    if not _TITLE:
        _TITLE["main"] = text_layer("iPhone 18 Pro Max", font("InterDisplay-SemiBold.otf", 168), pad=90)
        _TITLE["sub"] = text_layer("Coming soon.", font("InterDisplay-Medium.otf", 56), pad=60)
        _TITLE["disc"] = text_layer("Fan-made concept – not affiliated with Apple",
                                    font("Inter-Regular.otf", 30), pad=40)
        _TITLE["glow"] = blur(_TITLE["main"], 24)
    return _TITLE


def _place(disp, alpha, color, cx, cy, op, scale=1.0):
    if op <= 0:
        return
    a = alpha
    if abs(scale - 1) > 1e-3:
        h, w = a.shape
        a = np.asarray(Image.fromarray(a, "F").resize((max(1, int(w * scale)), max(1, int(h * scale))),
                                                       Image.BICUBIC)).clip(0, 1)
    h, w = a.shape
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    sub = a[ya - y0:yb - y0, xa - x0:xb - x0, None] * op
    col = color if np.ndim(color) == 1 else color[ya - y0:yb - y0, xa - x0:xb - x0]
    region = disp[ya:yb, xa:xb]
    region *= (1 - sub)
    region += col * sub


def title_overlay(disp, t):
    if t < 24.0:
        return
    L = _title_layers()
    lt = t - 24.0
    out = 1 - ease_in_out(lin(t, 28.0, 28.6))
    op = ease_in_out(lin(lt, 0.05, 0.75)) * out
    sc = 1.06 - 0.06 * ease_out_cubic(lin(lt, 0.0, 1.4)) + 0.02 * ease_in_out_sine(lin(lt, 1.4, 4.0))
    cy = H * 0.455
    main = L["main"]
    h, w = main.shape
    # metallic fill: bright top, titanium-blue bottom, a light sweep crossing the letters
    yy, xx = np.mgrid[0:h, 0:w].astype(f32)
    gy = yy / h
    base = (np.array([0.98, 0.98, 1.0], f32) * (1 - smoothstep(0.35, 0.75, gy))[..., None]
            + np.array([0.70, 0.78, 0.92], f32) * smoothstep(0.35, 0.75, gy)[..., None])
    sx = -0.3 + 1.6 * ease_in_out_sine(lin(lt, 0.5, 2.2))
    band = np.exp(-(((xx / w) - sx + 0.25 * (gy - 0.5)) / 0.05) ** 2)
    color = np.clip(base + band[..., None] * np.array([0.25, 0.18, 0.08], f32), 0, 1)
    if abs(sc - 1) > 1e-3:
        color = np.stack([np.asarray(Image.fromarray(color[..., i], "F").resize(
            (int(w * sc), int(h * sc)), Image.BICUBIC)) for i in range(3)], -1).clip(0, 1)
    # glow behind the title
    g = L["glow"]
    gh, gw = g.shape
    gcol = np.ones((gh, gw, 3), f32) * np.array([0.30, 0.45, 0.85], f32)
    _place(disp, np.clip(g * 1.4, 0, 1), np.array([0.16, 0.26, 0.55], f32), W / 2, cy, op * 0.45, sc)
    _place(disp, main, color, W / 2, cy, op, sc)
    sub_op = ease_in_out(lin(lt, 0.9, 1.6)) * out
    rise = 18 * (1 - ease_out_cubic(lin(lt, 0.9, 1.8)))
    _place(disp, L["sub"], np.array([1.0, 0.72, 0.45], f32), W / 2, cy + 132 + rise, sub_op)


def disclaimer_overlay(disp, t):
    if t < 28.3:
        return
    L = _title_layers()
    op = ease_in_out(lin(t, 28.45, 28.95))
    _place(disp, L["disc"], np.array([0.62, 0.64, 0.68], f32), W / 2, H / 2, op)


# ----------------------------------------------------------------------------- frame assembly
def scene_at(t):
    if t < 3.0:
        return scene1(t)
    if t < 7.0:
        return scene2(t)
    if t < 11.0:
        return scene3(t)
    if t < 15.0:
        return scene4(t)
    if t < 19.0:
        return scene5(t)
    if t < 24.0:
        return scene6(t)
    return scene7(t)


def render_frame(i):
    t = i / FPS
    img, post = scene_at(t)
    # transitions
    expo = 1.0
    for T in FLASH_TIMES:
        if T <= t < T + 0.5:
            x = t - T
            expo += 0.6 * math.exp(-x / 0.08)
            xs, ys = pixel_grid()
            g = np.exp(-(((xs - W / 2) / 760) ** 2 + ((ys - H * 0.47) / 520) ** 2))
            img = img + g[..., None] * np.array([0.05, 0.065, 0.10], f32) * math.exp(-x / 0.07)
    for T in WHIP_TIMES:
        x = abs(t + 0.5 / FPS - T)
        if x < 0.17:
            s = (1 - x / 0.17) ** 2
            img = motion_blur_h(img, 260 * s)
            expo += 0.35 * s
    disp = finish(img, bloom_kw=post.get("bloom"), exposure=expo)
    disp = vignette(disp, 0.22)
    title_overlay(disp, t)
    disclaimer_overlay(disp, t)
    captions.draw(disp, t)
    return quantize(disp, i)
