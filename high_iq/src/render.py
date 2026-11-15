"""Render the 60 s vertical video (1080x1920, 30 fps) from build/timeline.json.

All visuals are drawn with skia (anti-aliased vector shapes, blur-mask neon glow).
Scenes are timed by the voiceover word timestamps. Captions are burned in, 2-4 words
at a time, with the spoken word highlighted in yellow.

    python render.py preview 1.0 7.5 20     # PNG stills at those seconds -> build/preview/
    python render.py video                  # build/video.mp4 (silent)
    python render.py mux                    # final MP4 with build/mix.wav
"""
import json, math, os, subprocess, sys
import numpy as np
import skia

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "build")
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
W, H, FPS = 1080, 1920, 30
FONT_DIR = "/usr/share/fonts/opentype/inter"

# palette
BG_TOP, BG_BOT = (5, 6, 14), (12, 7, 28)
CYAN = (46, 200, 255)
BLUE = (70, 120, 255)
PURPLE = (170, 90, 255)
MAGENTA = (230, 80, 240)
GOLD = (255, 200, 60)
YELLOW = (255, 226, 50)
WHITE = (255, 255, 255)
RED = (255, 70, 100)
GREEN = (80, 255, 170)

TL = None
EV = None
G = {}   # per-process cache (fonts, precomputed geometry)


# ------------------------------------------------------------------ helpers
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def prog(t, t0, dur):
    return clamp((t - t0) / dur) if dur > 0 else float(t >= t0)


def ease_out(p):
    return 1 - (1 - p) ** 3


def ease_io(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_back(p, s=2.2):
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def pop(t, t0, dur=0.38):
    return ease_back(prog(t, t0, dur))


def lerp(a, b, p):
    return a + (b - a) * p


def col(c, a=1.0):
    return skia.Color4f(c[0] / 255, c[1] / 255, c[2] / 255, clamp(a))


def mix(c1, c2, p):
    return tuple(int(lerp(a, b, p)) for a, b in zip(c1, c2))


def paint(c=WHITE, a=1.0, stroke=None, blur=0, cap="round", shader=None, blend=None):
    p = skia.Paint(AntiAlias=True, Color4f=col(c, a))
    if stroke is not None:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        p.setStrokeCap(skia.Paint.kRound_Cap if cap == "round" else skia.Paint.kButt_Cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    if blur:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    if shader is not None:
        p.setShader(shader)
    if blend is not None:
        p.setBlendMode(blend)
    return p


def font(weight, size):
    key = (weight, round(size, 1))
    if key not in G.setdefault("fonts", {}):
        tf = G.setdefault("tf", {})
        if weight not in tf:
            name = {"black": "Inter-Black.otf", "xbold": "Inter-ExtraBold.otf", "bold": "Inter-Bold.otf",
                    "semi": "Inter-SemiBold.otf", "dblack": "InterDisplay-Black.otf"}[weight]
            tf[weight] = skia.Typeface.MakeFromFile(os.path.join(FONT_DIR, name))
        f = skia.Font(tf[weight], size)
        f.setEdging(skia.Font.Edging.kAntiAlias)
        f.setSubpixel(True)
        G["fonts"][key] = f
    return G["fonts"][key]


def text_w(s, f):
    return f.measureText(s)


def draw_text(c, s, x, y, size, color=WHITE, a=1.0, weight="black", align="center", glow=0,
              glow_color=None, outline=0, outline_color=(0, 0, 0), shader=None, spacing=0.0):
    """Draw text with baseline at y. Returns the drawn width."""
    if a <= 0.003 or not s:
        return 0
    f = font(weight, size)
    if spacing:
        widths = f.getWidths(f.textToGlyphs(s))
        w = sum(widths) + spacing * (len(s) - 1)
    else:
        w = text_w(s, f)
    x0 = x - w / 2 if align == "center" else x - w if align == "right" else x

    def emit(p):
        if spacing:
            xx = x0
            for ch, cw in zip(s, widths):
                c.drawString(ch, xx, y, f, p)
                xx += cw + spacing
        else:
            c.drawString(s, x0, y, f, p)
    if glow:
        emit(paint(glow_color or color, 0.85 * a, blur=glow))
    if outline:
        emit(paint(outline_color, a, stroke=outline))
    p = paint(color, a)
    if shader is not None:
        p.setShader(shader)
    emit(p)
    return w


def neon_path(c, path, color, width=6, a=1.0, glow=16, core=True):
    if a <= 0.003:
        return
    c.drawPath(path, paint(color, 0.9 * a, stroke=width * 2.2, blur=glow))
    c.drawPath(path, paint(color, a, stroke=width))
    if core:
        c.drawPath(path, paint(mix(color, WHITE, 0.65), 0.85 * a, stroke=max(1.0, width * 0.38)))


def glow_circle(c, x, y, r, color, a=1.0, glow=None):
    if a <= 0.003:
        return
    c.drawCircle(x, y, r * 2.2, paint(color, 0.35 * a, blur=glow or r * 1.4))
    c.drawCircle(x, y, r, paint(color, a))
    c.drawCircle(x, y, r * 0.45, paint(mix(color, WHITE, 0.7), a))


def rrect(x, y, w, h, r):
    return skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), r, r)


def layer(c, a):
    """Group opacity."""
    c.saveLayer(None, skia.Paint(Alphaf=clamp(a)))


# ------------------------------------------------------------------ static geometry
def brain_path():
    """Stylized brain: two lobed hemispheres built from unioned circles."""
    if "brain" in G:
        return G["brain"]
    lobes = [(-150, 0, 72), (-118, -72, 74), (-45, -106, 72), (-62, -10, 84), (-122, 66, 62),
             (-52, 84, 66), (-20, 30, 62), (-18, -60, 62)]
    left = skia.Path()
    for x, y, r in lobes:
        left = skia.Op(left, _circle(x, y, r), skia.PathOp.kUnion_PathOp)
    clip = skia.Path()
    clip.addRect(skia.Rect.MakeLTRB(-300, -300, -7, 300))
    left = skia.Op(left, clip, skia.PathOp.kIntersect_PathOp)
    m = skia.Matrix.Scale(-1, 1)
    right = skia.Path(left)
    right.transform(m)
    folds = skia.Path()
    for sx in (-1, 1):
        f = [((-178, -10), (-140, -40), (-110, 0), (-80, -30)),
             ((-150, 60), (-120, 30), (-95, 70), (-60, 40)),
             ((-110, -120), (-90, -80), (-60, -110), (-40, -70)),
             ((-70, 110), (-60, 70), (-35, 100), (-20, 60)),
             ((-60, -40), (-40, -10), (-30, -50), (-15, -15))]
        for (p0, p1, p2, p3) in f:
            folds.moveTo(sx * p0[0], p0[1])
            folds.cubicTo(sx * p1[0], p1[1], sx * p2[0], p2[1], sx * p3[0], p3[1])
    nodes = [(-140, -20), (-100, -80), (-40, -60), (-80, 40), (-130, 70), (-40, 90), (-30, 10),
             (140, -20), (100, -80), (40, -60), (80, 40), (130, 70), (40, 90), (30, 10), (0, -120)]
    links = []
    for i, a in enumerate(nodes):
        for j, b in enumerate(nodes):
            if i < j and math.dist(a, b) < 95:
                links.append((a, b))
    G["brain"] = (left, right, folds, nodes, links)
    return G["brain"]


def _circle(x, y, r):
    p = skia.Path()
    p.addCircle(x, y, r)
    return p


def draw_brain(c, x, y, s, t, a=1.0, energy=1.0):
    left, right, folds, nodes, links = brain_path()
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    pulse = 0.5 + 0.5 * math.sin(t * 3.2)
    for hemi in (left, right):
        sh = skia.GradientShader.MakeRadial(skia.Point(0, -40), 260,
                                            [col((70, 30, 140), 0.95 * a), col((18, 10, 45), 0.95 * a)])
        c.drawPath(hemi, skia.Paint(AntiAlias=True, Shader=sh))
    c.save()
    c.clipPath(skia.Op(left, right, skia.PathOp.kUnion_PathOp), doAntiAlias=True)
    c.drawPath(folds, paint(MAGENTA, 0.55 * a, stroke=5, blur=4))
    c.drawPath(folds, paint(mix(MAGENTA, WHITE, 0.3), 0.75 * a, stroke=3))
    for (p, q) in links:
        c.drawLine(p[0], p[1], q[0], q[1], paint(CYAN, 0.35 * a * energy, stroke=2))
    for k, (nx, ny) in enumerate(nodes):
        ph = 0.5 + 0.5 * math.sin(t * 4 + k * 1.7)
        glow_circle(c, nx, ny, 5 + 3 * ph, CYAN, a * (0.4 + 0.6 * ph) * energy, glow=10)
    c.restore()
    for hemi in (left, right):
        neon_path(c, hemi, PURPLE, 6, a * (0.85 + 0.15 * pulse), glow=18 + 8 * pulse)
    c.restore()


def stadium_points():
    if "stadium" in G:
        return G["stadium"]
    rng = np.random.default_rng(3)
    rings = []
    n_rings = 30
    for k in range(n_rings):
        f = k / (n_rings - 1)
        rx, ry = lerp(250, 485, f), lerp(140, 300, f)
        circ = 2 * math.pi * math.sqrt((rx * rx + ry * ry) / 2)
        n = int(circ / 8.3)
        th = np.linspace(0, 2 * math.pi, n, endpoint=False) + rng.random() * 0.1
        # aisles every 30 degrees
        keep = (np.mod(np.degrees(th) + 7, 30) > 2.6)
        th = th[keep]
        x = 540 + rx * np.cos(th)
        y = 720 + ry * np.sin(th) - (1 - f) * 0 - f * 46   # upper tiers rise (bowl)
        depth = (np.sin(th) + 1) / 2                      # 0 far side .. 1 near side
        group = rng.integers(0, 4, len(th))
        rings.append(dict(x=x, y=y, depth=depth, group=group, rx=rx, ry=ry, f=f))
    # the one gold dot: near side, lower right
    gr = rings[17]
    gi = int(np.argmin(np.abs(np.degrees(np.arctan2((gr["y"] - 720 + 0.6 * 46) / gr["ry"],
                                                    (gr["x"] - 540) / gr["rx"])) - 52)))
    G["stadium"] = (rings, (float(gr["x"][gi]), float(gr["y"][gi])), (17, gi))
    total = sum(len(r["x"]) for r in rings)
    G["stadium_n"] = total
    return G["stadium"]


def vignette():
    if "vig" in G:
        return G["vig"]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.45) / (H * 0.62)) ** 2)
    a = (np.clip(d - 0.55, 0, 1) ** 1.6 * 255 * 0.85).clip(0, 255).astype(np.uint8)
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., 3] = a
    G["vig"] = skia.Image.fromarray(arr)
    return G["vig"]


def particles():
    if "parts" in G:
        return G["parts"]
    rng = np.random.default_rng(11)
    n = 90
    G["parts"] = dict(x=rng.random(n) * W, y=rng.random(n) * H, sp=10 + rng.random(n) * 35,
                      r=1.2 + rng.random(n) ** 3 * 4.5, ph=rng.random(n) * 6.28,
                      c=rng.integers(0, 3, n), drift=rng.random(n) * 6.28)
    return G["parts"]


# ------------------------------------------------------------------ background
def draw_background(c, t):
    sh = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, H)], [col(BG_TOP), col(BG_BOT)])
    c.drawPaint(skia.Paint(Shader=sh))
    # drifting color blobs
    for (cx, cy, r, cc, a, sp) in [(200, 380, 520, PURPLE, 0.16, 0.13), (900, 1450, 600, BLUE, 0.13, 0.11),
                                   (850, 300, 380, CYAN, 0.07, 0.17)]:
        x = cx + 80 * math.sin(t * sp * 2 + cx)
        y = cy + 60 * math.cos(t * sp * 1.6 + cy)
        rs = skia.GradientShader.MakeRadial(skia.Point(x, y), r, [col(cc, a), col(cc, 0)])
        c.drawCircle(x, y, r, skia.Paint(Shader=rs))
    # perspective grid floor
    hz = 1240
    vp = (540, hz - 260)
    gp = paint(PURPLE, 0.10, stroke=2)
    for k in range(-12, 13):
        xb = 540 + k * 150
        x0 = lerp(vp[0], xb, (hz - vp[1]) / (H - vp[1]))
        c.drawLine(x0, hz, xb, H, gp)
    off = (t * 0.55) % 1.0
    for k in range(14):
        z = (k + off) / 14
        y = hz + (H - hz) * z ** 2.2
        c.drawLine(0, y, W, y, paint(PURPLE, 0.04 + 0.14 * z, stroke=1.5 + 1.5 * z))
    fade = skia.GradientShader.MakeLinear([skia.Point(0, hz - 10), skia.Point(0, hz + 220)],
                                          [col(BG_BOT, 1), col(BG_BOT, 0)])
    c.drawRect(skia.Rect.MakeLTRB(0, hz - 10, W, hz + 220), skia.Paint(Shader=fade))
    # faint dot grid in the upper area
    dp = paint(BLUE, 0.07, stroke=3)
    pts = [skia.Point(x, y) for x in range(60, W, 80) for y in range(60 + int((t * 12) % 80) - 80, hz, 80)]
    c.drawPoints(skia.Canvas.kPoints_PointMode, pts, dp)
    # floating particles
    P = particles()
    cols = [CYAN, PURPLE, BLUE]
    for i in range(len(P["x"])):
        y = (P["y"][i] - P["sp"][i] * t) % (H + 40) - 20
        x = P["x"][i] + 18 * math.sin(t * 0.6 + P["drift"][i])
        tw = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 2.2 + P["ph"][i]))
        r = P["r"][i]
        cc = cols[P["c"][i]]
        c.drawCircle(x, y, r * 3, paint(cc, 0.10 * tw))
        c.drawCircle(x, y, r, paint(mix(cc, WHITE, 0.4), 0.55 * tw))


# ------------------------------------------------------------------ scene 1: hook
def scene_hook(c, t):
    e = EV
    intro = ease_out(prog(t, 0, 0.6))
    draw_brain(c, 540, 400 + 10 * math.sin(t * 2), 0.95 + 0.05 * intro + 0.02 * math.sin(t * 3), t,
               a=0.75 + 0.25 * intro, energy=0.6 + 0.4 * prog(t, e["n2"], 0.5))
    # "2 IN 100" counter
    y = 790
    f_big = 200
    s2 = pop(t, e["n2"])
    s100 = pop(t, e["n100"])
    w2 = text_w("2", font("dblack", f_big))
    wr = text_w(" IN 100", font("dblack", f_big * 0.62))
    x0 = 540 - (w2 + wr) / 2
    if s2 > 0:
        c.save(); c.translate(x0 + w2 / 2, y - 70); c.scale(s2, s2)
        draw_text(c, "2", 0, 70, f_big, YELLOW, glow=26, glow_color=GOLD, weight="dblack")
        c.restore()
    else:  # slot-machine digits spinning until the "2" lands
        d = str(int(t * 23) * 7 % 10)
        jit = 12 * math.sin(t * 40)
        draw_text(c, d, x0 + w2 / 2, y + jit, f_big, GOLD, 0.55, glow=18, weight="dblack")
        draw_text(c, " IN 100", x0 + w2 + wr / 2, y, f_big * 0.62, WHITE, 0.22, weight="dblack")
    if s100 > 0 and t >= e["n100"]:
        n = int(round(100 * ease_out(prog(t, e["n100"], 0.45))))
        c.save(); c.translate(x0 + w2 + wr / 2, y - 40); c.scale(s100, s100)
        draw_text(c, f" IN {n}", 0, 40, f_big * 0.62, WHITE, glow=20, glow_color=CYAN, weight="dblack")
        c.restore()
    # IQ 130+ tag
    st = pop(t, e["iq130"])
    if st > 0:
        c.save(); c.translate(540, 862); c.scale(st, st)
        c.drawRRect(rrect(-150, -36, 300, 72, 36), paint(PURPLE, 0.25))
        c.drawRRect(rrect(-150, -36, 300, 72, 36), paint(PURPLE, 0.9, stroke=4, blur=6))
        c.drawRRect(rrect(-150, -36, 300, 72, 36), paint(MAGENTA, 1.0, stroke=3))
        draw_text(c, "IQ 130+", 0, 15, 44, WHITE, weight="black")
        c.restore()
    # 10 x 10 people grid, 2 lit
    gp = prog(t, e["n100"], 0.7)
    if gp > 0:
        sp = 31
        x0g, y0g = 540 - 4.5 * sp, 935
        lit = prog(t, e["iq130"] + 0.15, 0.3)
        for i in range(10):
            for j in range(10):
                k = i + j
                a = clamp(gp * 19 - k)
                if a <= 0:
                    continue
                x, y = x0g + i * sp, y0g + j * sp
                if (i, j) in ((6, 3), (2, 7)) and lit > 0:
                    glow_circle(c, x, y, 9 + 3 * ease_back(lit), GOLD, 1.0, glow=14)
                else:
                    c.drawCircle(x, y, 8.5 * a, paint(BLUE, 0.55 * a))
                    c.drawCircle(x, y, 8.5 * a, paint(CYAN, 0.6 * a, stroke=1.5))


# ------------------------------------------------------------------ scenes 2-3: bell curve
def pdf(iq):
    return math.exp(-0.5 * ((iq - 100) / 15) ** 2)


def scene_curve(c, t):
    e = EV
    z = ease_io(prog(t, e["zoom"], 1.25))
    lo = lerp(40, 112, z)
    hi = lo + lerp(120, 62, z)
    gamma = lerp(1.0, 0.36, z)
    base, peak = 1110, 540
    xl, xr = 80, 1000

    def X(iq):
        return xl + (iq - lo) / (hi - lo) * (xr - xl)

    def Y(iq):
        return base - peak * (pdf(iq) ** gamma) * lerp(1.0, 0.92, z)

    draw_p = ease_io(prog(t, e["curve"], 1.7))
    # axis
    ax_a = clamp(prog(t, e["curve"] - 0.2, 0.4))
    c.drawLine(xl - 20, base, xr + 20, base, paint(WHITE, 0.35 * ax_a, stroke=3))
    # title
    t1 = ax_a * (1 - prog(t, e["zoom"], 0.4))
    draw_text(c, "THE IQ BELL CURVE", 540, 330, 50, WHITE, t1, weight="xbold", spacing=3)
    t2 = prog(t, e["zoom"] + 0.5, 0.4) * (1 - prog(t, e["r30000"] + 0.9, 0.5) * 0)
    draw_text(c, "THE RIGHT TAIL", 540, 205, 42, CYAN, t2, weight="xbold", spacing=4)

    # curve path (only visible domain)
    step = (hi - lo) / 220
    iqs = [lo - 2 + k * step for k in range(int((hi - lo + 4) / step) + 1)]
    curve = skia.Path()
    for k, q in enumerate(iqs):
        (curve.moveTo if k == 0 else curve.lineTo)(X(q), Y(q))

    def region(a_iq, b_iq):
        a_iq, b_iq = max(a_iq, lo - 2), min(b_iq, hi + 2)
        if b_iq <= a_iq:
            return None
        r = skia.Path()
        r.moveTo(X(a_iq), base)
        n = 80
        for k in range(n + 1):
            q = a_iq + (b_iq - a_iq) * k / n
            r.lineTo(X(q), Y(q))
        r.lineTo(X(b_iq), base)
        r.close()
        return r

    c.save()
    c.clipRect(skia.Rect.MakeLTRB(0, 235 if z > 0 else 380, W, base + 2))
    # 68% band
    sh = prog(t, e["shade68"], 0.6)
    band_a = sh * (1 - z)
    if band_a > 0:
        mid = lerp(100, 85, sh), lerp(100, 115, sh)
        r = region(*mid)
        g = skia.GradientShader.MakeLinear([skia.Point(0, base - peak), skia.Point(0, base)],
                                           [col(CYAN, 0.55 * band_a), col(BLUE, 0.15 * band_a)])
        c.drawPath(r, skia.Paint(AntiAlias=True, Shader=g))
    # tail regions
    for key, thr, cc in (("t130", 130, PURPLE), ("t145", 145, CYAN), ("t160", 160, GOLD)):
        p = prog(t, e[key], 0.55)
        if p > 0:
            r = region(thr, lerp(thr, 200, ease_out(p)))
            if r is not None:
                g = skia.GradientShader.MakeLinear([skia.Point(0, base - peak * 0.7), skia.Point(0, base)],
                                                   [col(cc, 0.75), col(cc, 0.25)])
                c.drawPath(r, skia.Paint(AntiAlias=True, Shader=g))
    # the curve drawing itself
    pm = skia.PathMeasure(curve, False)
    seg = skia.Path()
    L = pm.getLength()
    if z > 0:
        seg = curve
    else:
        pm.getSegment(0, L * draw_p, seg, True)
    neon_path(c, seg, CYAN, 6, 1.0, glow=16)
    if 0 < draw_p < 1 and z == 0:
        pos = pm.getPosTan(L * draw_p)[0]
        glow_circle(c, pos.x(), pos.y(), 9, WHITE, 1.0, glow=16)
    c.restore()

    # average line + labels
    la = pop(t, e["avg"])
    if la > 0 and z < 1:
        xa = X(100)
        a = 1 - z
        dash = skia.Paint(AntiAlias=True, Color4f=col(WHITE, 0.55 * a), StrokeWidth=3,
                          Style=skia.Paint.kStroke_Style, PathEffect=skia.DashPathEffect.Make([14, 12], -t * 30))
        c.drawLine(xa, base, xa, lerp(base, base - peak - 20, clamp(la)), dash)
        draw_text(c, "AVERAGE", xa, base - peak - 40, 32, WHITE, 0.8 * a * clamp(la), weight="bold", spacing=3)
    for key, iq in (("l85", 85), ("avg", 100), ("l115", 115)):
        s = pop(t, e[key])
        if s > 0:
            x = X(iq)
            a = 1 - z
            c.drawLine(x, base - 12, x, base + 12, paint(WHITE, 0.8 * a, stroke=3))
            c.save(); c.translate(x, base + 58); c.scale(s, s)
            draw_text(c, str(iq), 0, 0, 46, WHITE if iq == 100 else CYAN, a, glow=10, glow_color=CYAN)
            c.restore()
    if sh > 0 and z < 1:
        s = ease_back(prog(t, e["shade68"] + 0.15, 0.4))
        c.save(); c.translate(540, base - 170); c.scale(s, s)
        draw_text(c, "68%", 0, 0, 110, WHITE, 1 - z, glow=20, glow_color=CYAN, weight="dblack")
        c.restore()
        draw_text(c, "OF PEOPLE", 540, base - 110, 34, WHITE, (1 - z) * prog(t, e["shade68"] + 0.3, 0.3),
                  weight="xbold", spacing=3)

    # tail markers and callout cards
    cards = [("t130", 130, PURPLE, "130+", [("gifted", "GIFTED", 0.0), ("p2", "2%", 1.0)]),
             ("t145", 145, CYAN, "145+", [("r1000", "1 in 1,000", 1.0)]),
             ("t160", 160, GOLD, "160+", [("r30000", "1 in 30,000", 1.0)])]
    if z > 0:
        for tick in (115, 130, 145, 160, 175):
            x = X(tick)
            if xl - 10 < x < xr + 10:
                c.drawLine(x, base - 10, x, base + 10, paint(WHITE, 0.5 * z, stroke=3))
                if tick in (115, 175):
                    draw_text(c, str(tick), x, base + 54, 38, WHITE, 0.45 * z, weight="bold")
    for i, (key, thr, cc, label, extras) in enumerate(cards):
        s = pop(t, e[key])
        if s <= 0:
            continue
        x = X(thr)
        flash = 1 - prog(t, e[key], 0.6)
        c.drawLine(x, base, x, lerp(base, 245 + i * 125 + 100, clamp(s)),
                   paint(cc, 0.9, stroke=3 + 3 * flash, blur=0))
        c.drawLine(x, base, x, lerp(base, 245 + i * 125 + 100, clamp(s)), paint(cc, 0.6, stroke=10, blur=10))
        c.save(); c.translate(x, base + 56); c.scale(s, s)
        draw_text(c, str(thr), 0, 0, 46, cc, 1, glow=12)
        c.restore()
        # card
        cy = 245 + i * 125
        c.save(); c.translate(540, cy + 50); c.scale(lerp(0.6, 1, clamp(s)), s); c.translate(-540, -cy - 50)
        rr = rrect(85, cy, 910, 100, 26)
        c.drawRRect(rr, paint((14, 10, 34), 0.86))
        c.drawRRect(rr, paint(cc, 0.65, stroke=8, blur=10))
        c.drawRRect(rr, paint(cc, 1, stroke=3))
        draw_text(c, label, 125, cy + 70, 60, cc, 1, align="left", glow=12, weight="dblack")
        for (ek, txt, side) in extras:
            pe = pop(t, e[ek])
            if pe <= 0:
                continue
            if side == 0.0:  # tag next to the threshold
                tw = text_w(txt, font("black", 32)) + 36
                xx = 125 + text_w(label, font("dblack", 60)) + 26
                c.save(); c.translate(xx + tw / 2, cy + 50); c.scale(pe, pe)
                c.drawRRect(rrect(-tw / 2, -24, tw, 48, 24), paint(cc, 0.9))
                draw_text(c, txt, 0, 12, 32, (20, 8, 40), weight="black", spacing=1.5)
                c.restore()
            else:
                c.save(); c.translate(955, cy + 50); c.scale(pe, pe)
                draw_text(c, txt, 0, 22, 62, WHITE, 1, align="right", glow=14, glow_color=cc, weight="dblack")
                c.restore()
        c.restore()
    # flash on 160 reveal
    fl = 1 - prog(t, e["t160"], 0.35)
    if 0 < fl < 1:
        c.drawRect(skia.Rect.MakeWH(W, H), paint(GOLD, 0.22 * fl))


# ------------------------------------------------------------------ scene 4: stadium
def scene_stadium(c, t):
    e = EV
    rings, gold, (gr, gi) = stadium_points()
    gp = ease_io(prog(t, e["gold"] + 0.25, 2.2))
    zoom = lerp(1.0, 1.22, gp)
    c.save()
    c.translate(540, 720); c.scale(zoom, zoom)
    c.translate(-lerp(540, gold[0], gp * 0.55), -lerp(720, gold[1], gp * 0.55))
    # structure: outer wall and field
    outer = skia.Path(); outer.addOval(skia.Rect.MakeLTRB(540 - 505, 720 - 46 - 322, 540 + 505, 720 - 46 + 322))
    neon_path(c, outer, PURPLE, 4, 0.8, glow=14)
    outer2 = skia.Path(); outer2.addOval(skia.Rect.MakeLTRB(540 - 505, 720 - 46 - 322 + 40, 540 + 505, 720 - 46 + 322 + 40))
    c.drawPath(outer2, paint(PURPLE, 0.35, stroke=3))
    field = skia.Rect.MakeLTRB(540 - 228, 720 - 124, 540 + 228, 720 + 124)
    fg = skia.GradientShader.MakeRadial(skia.Point(540, 720), 260, [col((20, 80, 70), 0.9), col((8, 30, 34), 0.9)])
    c.drawOval(field, skia.Paint(AntiAlias=True, Shader=fg))
    fp = paint(GREEN, 0.55, stroke=3)
    c.drawOval(field, fp)
    c.drawLine(540, 720 - 124, 540, 720 + 124, fp)
    c.drawCircle(540, 720, 42, fp)
    c.drawRect(skia.Rect.MakeLTRB(540 - 228, 720 - 50, 540 - 170, 720 + 50), fp)
    c.drawRect(skia.Rect.MakeLTRB(540 + 170, 720 - 50, 540 + 228, 720 + 50), fp)
    # crowd dots, filling ring by ring
    fill = prog(t, e["fill"] - 0.1, 1.3)
    cols = [(70, 110, 220), (130, 80, 230), (60, 170, 240), (110, 120, 200)]
    for k, r in enumerate(rings):
        ra = clamp(fill * (len(rings) + 6) - k * 1.0, 0, 1)
        if ra <= 0:
            continue
        for gidx in range(4):
            m = r["group"] == gidx
            tw = 0.55 + 0.45 * math.sin(t * 3.1 + gidx * 1.9 + k * 0.4)
            for near in (0, 1):
                mm = m & ((r["depth"] > 0.5) == bool(near))
                if not mm.any():
                    continue
                pts = [skia.Point(float(x), float(y)) for x, y in zip(r["x"][mm], r["y"][mm])]
                size = lerp(3.2, 5.6, r["f"] * 0.5 + 0.5 * near)
                p = paint(cols[gidx], ra * (0.45 + 0.35 * tw) * (0.75 + 0.25 * near), stroke=size)
                c.drawPoints(skia.Canvas.kPoints_PointMode, pts, p)
    # the gold dot
    g = prog(t, e["gold"], 0.25)
    if g > 0:
        x, y = gold
        for k in range(3):
            ph = ((t - e["gold"]) * 0.9 + k / 3) % 1.0
            c.drawCircle(x, y, 10 + ph * 90, paint(GOLD, (1 - ph) * 0.8 * g, stroke=3))
        glow_circle(c, x, y, 7 + 3 * ease_back(g) + 1.5 * math.sin(t * 6), GOLD, 1, glow=22)
        c.drawCircle(x, y, 60, paint(GOLD, 0.25 * g, blur=40))
    c.restore()
    # label
    s = pop(t, e["gold"] + 0.1)
    if s > 0:
        c.save(); c.translate(540, 245); c.scale(s, s)
        draw_text(c, "1 in 30,000", 0, 0, 92, GOLD, glow=22, weight="dblack")
        c.restore()
        draw_text(c, "ONE PERSON IN A FULL STADIUM", 540, 310, 34, WHITE, prog(t, e["gold"] + 0.35, 0.4) * 0.85,
                  weight="xbold", spacing=2)
    else:
        n = int(G["stadium_n"] * ease_out(fill)) * 5
        draw_text(c, f"{n:,}", 540, 245, 92, WHITE, prog(t, e["fill"], 0.3), glow=16, glow_color=BLUE,
                  weight="dblack")
        draw_text(c, "FANS", 540, 310, 34, WHITE, prog(t, e["fill"], 0.3) * 0.8, weight="xbold", spacing=4)


# ------------------------------------------------------------------ scene 5: DNA
def scene_dna(c, t):
    e = EV
    t0 = TL["scenes"][4]["start"]
    intro = ease_out(prog(t, t0, 0.8))
    cx, cy = 540, 850
    L, A, period = 820, 118, 320
    ang = math.radians(16)
    ca, sa = math.cos(ang), math.sin(ang)
    spin = t * 2.1

    def pt(u, v):
        # axis direction (sa, ca) i.e. tilted from vertical; v perpendicular
        return cx + u * sa + v * ca, cy + u * ca - v * sa

    c.save()
    c.translate(cx, cy); c.scale(lerp(0.7, 1, intro), lerp(0.7, 1, intro)); c.translate(-cx, -cy)
    layer(c, intro)
    us = np.linspace(-L / 2, L / 2, 260)
    ph = 2 * math.pi * us / period + spin
    s1, z1 = np.sin(ph), np.cos(ph)
    strands = []
    for sign, cc in ((1, CYAN), (-1, PURPLE)):
        v = A * s1 * sign
        z = z1 * sign
        back, front = skia.Path(), skia.Path()
        prev_side = None
        for k in range(len(us)):
            x, y = pt(us[k], v[k])
            side = z[k] > 0
            path = front if side else back
            if side != prev_side:
                if k > 0:
                    xp, yp = pt(us[k - 1], v[k - 1])
                    path.moveTo(xp, yp)
                    path.lineTo(x, y)
                else:
                    path.moveTo(x, y)
            else:
                path.lineTo(x, y)
            prev_side = side
        strands.append((back, front, cc))
    # back strands
    for back, front, cc in strands:
        c.drawPath(back, paint(mix(cc, (20, 20, 60), 0.5), 0.55, stroke=9))
    # rungs
    th = e["thousands"]
    rng = np.random.default_rng(5)
    n_r = 26
    flash_t = th + rng.random(n_r) * 1.6
    for k in range(n_r):
        u = -L / 2 + (k + 0.5) * L / n_r
        p = 2 * math.pi * u / period + spin
        v1, z = A * math.sin(p), math.cos(p)
        x1, y1 = pt(u, v1)
        x2, y2 = pt(u, -v1)
        xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
        depth = 0.45 + 0.55 * abs(math.cos(p))
        a = 0.35 + 0.55 * depth
        c.drawLine(x1, y1, xm, ym, paint(CYAN, a, stroke=7))
        c.drawLine(xm, ym, x2, y2, paint(MAGENTA, a, stroke=7))
        fl = prog(t, flash_t[k], 0.15) * (1 - prog(t, flash_t[k] + 0.25, 0.5))
        if t >= th:
            fl = max(fl, 0.35 * (0.5 + 0.5 * math.sin(t * 7 + k)) * prog(t, th + 1.6, 0.5))
        if fl > 0:
            c.drawLine(x1, y1, x2, y2, paint(GOLD, fl, stroke=10, blur=8))
            c.drawLine(x1, y1, x2, y2, paint(mix(GOLD, WHITE, 0.5), fl, stroke=4))
            if prog(t, flash_t[k], 0.1) > 0 and t < flash_t[k] + 1.2:
                q = prog(t, flash_t[k], 1.2)
                draw_text(c, "+", xm + 40 * math.sin(k), ym - 120 * q, 40, GOLD, (1 - q) * 0.9, weight="black")
    # front strands
    for back, front, cc in strands:
        neon_path(c, front, cc, 9, 1.0, glow=14)
    c.restore()
    c.restore()

    # heritability text
    hp = pop(t, e["herit"])
    gene_t = e["gene"]
    fade = 1 - prog(t, gene_t - 0.2, 0.35)
    if hp > 0 and fade > 0:
        h80 = prog(t, e["herit80"], 0.25)
        txt = "50–80%" if h80 > 0 else "50%"
        shader = skia.GradientShader.MakeLinear([skia.Point(240, 0), skia.Point(840, 0)], [col(CYAN), col(MAGENTA)])
        c.save(); c.translate(540, 250); c.scale(hp * fade + (1 - fade) * 0.9, hp * fade + (1 - fade) * 0.9)
        draw_text(c, txt, 0, 0, 150, WHITE, fade, glow=24, glow_color=PURPLE, shader=shader, weight="dblack")
        c.restore()
        draw_text(c, "HERITABLE", 540, 330, 54, WHITE, fade * h80, weight="black", spacing=8, glow=10,
                  glow_color=CYAN)
    # no single genius gene
    gp = pop(t, gene_t)
    gfade = 1 - prog(t, th - 0.3, 0.25)
    if gp > 0 and gfade > 0:
        c.save(); c.translate(540, 250); c.scale(gp, gp)
        layer(c, gfade)
        rr = rrect(-300, -70, 600, 140, 30)
        c.drawRRect(rr, paint((14, 10, 34), 0.9))
        c.drawRRect(rr, paint(MAGENTA, 1, stroke=4))
        c.drawRRect(rr, paint(MAGENTA, 0.6, stroke=10, blur=10))
        draw_text(c, "GENIUS GENE", 0, 22, 64, WHITE, weight="dblack", spacing=2)
        x = prog(t, e["gene_x"], 0.25)
        if x > 0:
            c.drawLine(-280, 0, lerp(-280, 280, ease_out(x)), 0, paint(RED, 1, stroke=12))
            c.drawLine(-280, 0, lerp(-280, 280, ease_out(x)), 0, paint(RED, 0.8, stroke=24, blur=12))
            draw_text(c, "DOESN'T EXIST", 0, 120, 40, RED, prog(t, e["gene_x"] + 0.1, 0.25), weight="black",
                      spacing=3)
        c.restore()
        c.restore()
    tp = pop(t, th)
    if tp > 0:
        c.save(); c.translate(540, 250); c.scale(tp, tp)
        draw_text(c, "1000s", 0, 0, 140, GOLD, glow=24, weight="dblack")
        c.restore()
        draw_text(c, "OF TINY DIFFERENCES", 540, 330, 44, WHITE, prog(t, th + 0.2, 0.3), weight="black", spacing=3)


# ------------------------------------------------------------------ scene 6: environment icons
def icon_apple(c, a):
    body = skia.Path()
    body.moveTo(0, -38)
    body.cubicTo(30, -62, 78, -44, 72, 6)
    body.cubicTo(68, 52, 34, 82, 10, 70)
    body.cubicTo(4, 67, -4, 67, -10, 70)
    body.cubicTo(-34, 82, -68, 52, -72, 6)
    body.cubicTo(-78, -44, -30, -62, 0, -38)
    body.close()
    sh = skia.GradientShader.MakeRadial(skia.Point(-20, -10), 110, [col((120, 20, 50), 0.9 * a), col((40, 6, 20), 0.9 * a)])
    c.drawPath(body, skia.Paint(AntiAlias=True, Shader=sh))
    neon_path(c, body, RED, 6, a)
    stem = skia.Path(); stem.moveTo(0, -38); stem.quadTo(4, -64, 16, -80)
    neon_path(c, stem, (200, 140, 90), 6, a, glow=8)
    leaf = skia.Path(); leaf.moveTo(6, -58); leaf.quadTo(30, -96, 62, -78); leaf.quadTo(40, -50, 6, -58); leaf.close()
    c.drawPath(leaf, paint(GREEN, 0.35 * a))
    neon_path(c, leaf, GREEN, 4, a, glow=10)
    c.drawCircle(-36, -12, 9, paint(WHITE, 0.5 * a))


def icon_moon(c, a, t):
    m = skia.Op(_circle(0, 0, 68), _circle(34, -24, 60), skia.PathOp.kDifference_PathOp)
    c.drawPath(m, paint(BLUE, 0.35 * a))
    neon_path(c, m, (120, 170, 255), 6, a)
    for k in range(3):
        q = (t * 0.45 + k / 3) % 1
        draw_text(c, "z", 40 + 30 * k + 10 * q, -30 - 70 * q - 18 * k, 34 + 10 * k, (180, 210, 255),
                  a * math.sin(math.pi * q), weight="black")


def icon_books(c, a):
    specs = [(-70, 30, 118, PURPLE), (-28, 34, 136, CYAN), (10, 28, 104, MAGENTA)]
    for x, w, h, cc in specs:
        r = rrect(x, 66 - h, w, h, 6)
        c.drawRRect(r, paint(cc, 0.25 * a))
        c.drawRRect(r, paint(cc, 0.6 * a, stroke=10, blur=8))
        c.drawRRect(r, paint(cc, a, stroke=4))
        c.drawLine(x + 6, 66 - h + 22, x + w - 6, 66 - h + 22, paint(cc, a, stroke=3))
        c.drawLine(x + 6, 66 - 22, x + w - 6, 66 - 22, paint(cc, a, stroke=3))
    c.save(); c.translate(64, 66); c.rotate(-18)
    r = rrect(0, -112, 30, 112, 6)
    c.drawRRect(r, paint(GOLD, 0.25 * a)); c.drawRRect(r, paint(GOLD, 0.6 * a, stroke=10, blur=8))
    c.drawRRect(r, paint(GOLD, a, stroke=4))
    c.restore()
    c.drawLine(-90, 68, 100, 68, paint(WHITE, 0.6 * a, stroke=4))


def icon_bulb(c, a, on, t):
    if on > 0:
        c.drawCircle(0, -24, 120, paint(YELLOW, 0.22 * on * a, blur=50))
        for k in range(10):
            ang = k * 36 + t * 20
            c.save(); c.rotate(ang)
            c.drawLine(0, -24 - 82, 0, -24 - 104 - 8 * math.sin(t * 6 + k), paint(YELLOW, 0.8 * on * a, stroke=5))
            c.restore()
    bulb = skia.Path()
    bulb.addCircle(0, -24, 58)
    neck = skia.Path(); neck.addRect(skia.Rect.MakeLTRB(-26, 20, 26, 52))
    shape = skia.Op(bulb, neck, skia.PathOp.kUnion_PathOp)
    c.drawPath(shape, paint(mix((60, 50, 10), YELLOW, on), (0.3 + 0.4 * on) * a))
    neon_path(c, shape, YELLOW, 6, a)
    fil = skia.Path(); fil.moveTo(-16, 18); fil.lineTo(-16, -10); fil.lineTo(-6, -24); fil.lineTo(4, -10)
    fil.lineTo(14, -24); fil.lineTo(16, 18)
    c.drawPath(fil, paint(mix(GOLD, WHITE, on), a, stroke=4))
    for k in range(3):
        c.drawLine(-26, 60 + 10 * k, 26, 60 + 10 * k, paint((200, 200, 220), a, stroke=6))


def scene_icons(c, t):
    e = EV
    sp = pop(t, e["env"])
    if sp > 0:
        c.save(); c.translate(540, 300); c.scale(sp, sp)
        shader = skia.GradientShader.MakeLinear([skia.Point(-330, 0), skia.Point(330, 0)], [col(CYAN), col(PURPLE)])
        draw_text(c, "ENVIRONMENT", 0, 0, 96, WHITE, glow=20, glow_color=BLUE, shader=shader, weight="dblack")
        c.restore()
    tiles = [("food", "NUTRITION", 295, 545, RED), ("sleep", "SLEEP", 785, 545, BLUE),
             ("books", "EDUCATION", 295, 990, PURPLE), ("bulb", "CURIOSITY", 785, 990, YELLOW)]
    grow = prog(t, e["grow"], 0.6)
    # energy links to the centre brain
    if grow > 0:
        for _, _, x, y, cc in tiles:
            q = ease_out(grow)
            xe, ye = lerp(x, 540, q * 0.7), lerp(y, 768, q * 0.7)
            c.drawLine(x, y, xe, ye, paint(cc, 0.55, stroke=5, blur=6))
            c.drawLine(x, y, xe, ye, paint(mix(cc, WHITE, 0.5), 0.8, stroke=2))
            ph = ((t - e["grow"]) * 1.4) % 1
            c.drawCircle(lerp(x, 540, ph * 0.8), lerp(y, 768, ph * 0.8), 6, paint(WHITE, 0.9 * q))
    for key, label, x, y, cc in tiles:
        s = pop(t, e[key], 0.45)
        if s <= 0:
            c.drawRRect(rrect(x - 130, y - 160, 260, 320, 34), paint(cc, 0.12, stroke=3))
            continue
        bob = 6 * math.sin(t * 2 + x)
        c.save(); c.translate(x, y + bob); c.scale(s, s)
        r = rrect(-130, -160, 260, 320, 34)
        c.drawRRect(r, paint((16, 12, 38), 0.85))
        lit = 1 - prog(t, e[key], 0.8)
        c.drawRRect(r, paint(cc, 0.45 + 0.4 * lit, stroke=8 + 10 * lit, blur=12))
        c.drawRRect(r, paint(cc, 0.95, stroke=3))
        c.save(); c.translate(0, -30)
        if key == "food":
            icon_apple(c, 1)
        elif key == "sleep":
            icon_moon(c, 1, t)
        elif key == "books":
            icon_books(c, 1)
        else:
            icon_bulb(c, 1, prog(t, e[key] + 0.1, 0.3), t)
        c.restore()
        draw_text(c, label, 0, 128, 34, WHITE, 1, weight="black", spacing=2)
        c.restore()
    if grow > 0:
        draw_brain(c, 540, 768, lerp(0.15, 0.36, ease_back(grow)), t, 1.0)


# ------------------------------------------------------------------ scene 7: scale + "not all"
def scene_scale(c, t):
    e = EV
    t0 = TL["scenes"][6]["start"]
    tn, tu, tt = e["nature"], e["nurture"], e["together"]
    ring_t = e["ring"] - 0.45
    out = ease_io(prog(t, ring_t, 0.6))
    if t < tn:
        th = lerp(-4, -10, prog(t, t0, tn - t0))
    elif t < tu:
        th = lerp(-10, -15, ease_out(prog(t, tn, 0.4)))
    else:
        tau = t - tu
        th = -15 * math.exp(-2.1 * tau) * math.cos(4.4 * tau)
    if out < 1:
        c.save()
        c.translate(540, 760); s = lerp(1, 0.55, out); c.scale(s, s); c.translate(-540, -760 - 600 * out)
        layer(c, 1 - out * 0.85)
        px, py = 540, 560
        # base and post
        tri = skia.Path(); tri.moveTo(540, py + 10); tri.lineTo(450, 1110); tri.lineTo(630, 1110); tri.close()
        c.drawPath(tri, paint((24, 16, 50), 0.9))
        neon_path(c, tri, PURPLE, 5, 1)
        c.drawRRect(rrect(400, 1100, 280, 26, 12), paint(PURPLE, 0.9))
        # beam
        c.save(); c.translate(px, py); c.rotate(th)
        beam = rrect(-360, -10, 720, 20, 10)
        c.drawRRect(beam, paint((30, 20, 60), 1))
        c.drawRRect(beam, paint(CYAN, 0.55, stroke=10, blur=10))
        c.drawRRect(beam, paint(CYAN, 1, stroke=4))
        c.restore()
        glow_circle(c, px, py, 18, GOLD, 1, glow=16)
        rad = math.radians(th)
        for side, word, cc, key in ((-1, "NATURE", CYAN, "nature"), (1, "NURTURE", MAGENTA, "nurture")):
            hx = px + side * 340 * math.cos(rad)
            hy = py + side * 340 * math.sin(rad)
            pan_y = hy + 250
            for dx in (-110, 110):
                c.drawLine(hx, hy, hx + dx, pan_y, paint(WHITE, 0.45, stroke=3))
            pan = skia.Path(); pan.moveTo(hx - 140, pan_y)
            pan.cubicTo(hx - 110, pan_y + 70, hx + 110, pan_y + 70, hx + 140, pan_y); pan.close()
            c.drawPath(pan, paint(cc, 0.25))
            neon_path(c, pan, cc, 5, 1)
            glow_circle(c, hx, hy, 8, WHITE, 0.9, glow=8)
            s = pop(t, e[key])
            if s > 0:
                c.save(); c.translate(hx, pan_y - 22); c.scale(s, s)
                draw_text(c, word, 0, 0, 62, WHITE, 1, glow=18, glow_color=cc, weight="dblack")
                # tiny emblem above the word
                if key == "nature":
                    for k in range(7):
                        yy = -150 + k * 14
                        w = 34 * math.sin(k * 0.9 + t * 3)
                        c.drawLine(-w, yy, w, yy, paint(CYAN if k % 2 else MAGENTA, 0.9, stroke=4))
                else:
                    c.drawRRect(rrect(-44, -150, 40, 84, 5), paint(MAGENTA, 1, stroke=4))
                    c.drawRRect(rrect(4, -140, 40, 74, 5), paint(PURPLE, 1, stroke=4))
                c.restore()
        tg = pop(t, tt)
        if tg > 0:
            c.save(); c.translate(540, 300); c.scale(tg, tg)
            draw_text(c, "BOTH MATTER", 0, 0, 92, GOLD, glow=22, weight="dblack")
            c.restore()
            q = prog(t, tt, 0.9)
            c.drawCircle(px, py, 30 + 300 * q, paint(GOLD, (1 - q) * 0.8, stroke=4))
        c.restore()
        c.restore()
    if out <= 0:
        return
    # "IQ measures some kinds of intelligence, not all of them"
    cx, cy, R = 540, 760, 270
    kinds = [("LOGIC", True), ("MEMORY", True), ("SPATIAL", True), ("CREATIVITY", False), ("EMPATHY", False),
             ("SOCIAL", False)]
    ap = ease_out(prog(t, ring_t + 0.2, 0.6))
    some = prog(t, e["some"], 0.5)
    notall = prog(t, e["notall"], 0.5)
    head = pop(t, e["ring"])
    if head > 0:
        c.save(); c.translate(540, 300); c.scale(head, head)
        draw_text(c, "IQ ≠ ALL", 0, 0, 110, WHITE, glow=22, glow_color=PURPLE, weight="dblack")
        c.restore()
        draw_text(c, "INTELLIGENCE", 540, 370, 50, CYAN, prog(t, e["ring"] + 0.2, 0.3), weight="black", spacing=8)
    for k, (name, iq) in enumerate(kinds):
        a0 = -90 + k * 60 + 3
        sweep = 54 * ap
        rect = skia.Rect.MakeLTRB(cx - R, cy - R, cx + R, cy + R)
        arc = skia.Path(); arc.addArc(rect, a0, sweep)
        lit = some if iq else notall
        cc = CYAN if iq else MAGENTA
        c.drawPath(arc, paint(cc, 0.18 + 0.2 * lit, stroke=70, cap="butt"))
        if lit > 0:
            c.drawPath(arc, paint(cc, 0.6 * lit, stroke=78, blur=16, cap="butt"))
            c.drawPath(arc, paint(cc, 0.85 * lit, stroke=70, cap="butt"))
        mid = math.radians(a0 + 27)
        cm = math.cos(mid)
        lx, ly = cx + (R + 70) * cm, cy + (R + 82) * math.sin(mid) + 12
        al = "left" if cm > 0.8 else "right" if cm < -0.8 else "center"
        draw_text(c, name, lx, ly, 34, WHITE, ap * (0.5 + 0.5 * lit), weight="black", align=al)
    if ap > 0:
        draw_text(c, "IQ", cx, cy + 40, 120, WHITE, ap, glow=20, glow_color=CYAN, weight="dblack")
        draw_text(c, "MEASURES", cx, cy - 80, 34, CYAN, some, weight="black", spacing=4)
        draw_text(c, "THESE", cx, cy + 110, 34, CYAN, some * (1 - prog(t, e["notall"] - 0.2, 0.15)),
                  weight="black", spacing=4)
        draw_text(c, "NOT THESE", cx, cy + 110, 34, MAGENTA, prog(t, e["notall"], 0.25), weight="black", spacing=4)


SCENES = {1: scene_hook, 2: scene_curve, 4: scene_stadium, 5: scene_dna, 6: scene_icons, 7: scene_scale}
TRANS = {2: "zoom", 4: "whip", 5: "glitch", 6: "slide", 7: "whip"}
TD = 0.42  # transition length (s)


# ------------------------------------------------------------------ captions
def build_chunks():
    words = TL["words"]
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end_sent = nxt is None or nxt["sent"] != w["sent"]
        chars = sum(len(x["text"]) + 1 for x in cur)
        punct = w["text"][-1] in ",.?!:"
        nxt_len = len(nxt["text"]) if nxt else 0
        left_in_sent = sum(1 for x in words[i + 1:] if x["sent"] == w["sent"])
        if end_sent or len(cur) == 4 or (len(cur) >= 2 and punct) or (len(cur) >= 2 and chars + nxt_len > 15):
            if not end_sent and left_in_sent == 1 and len(cur) <= 3 and chars + nxt_len <= 20:
                continue  # avoid an orphan word: take the last word into this chunk
            chunks.append(cur)
            cur = []
    out = []
    for k, ch in enumerate(chunks):
        start = 0.0 if k == 0 else ch[0]["start"] - 0.06
        nxt = chunks[k + 1][0]["start"] - 0.06 if k + 1 < len(chunks) else 1e9
        end = min(nxt, ch[-1]["end"] + 0.45)
        if nxt - ch[-1]["end"] < 0.7:
            end = nxt
        out.append(dict(words=ch, start=start, end=end))
    return out


def draw_captions(c, t):
    if "chunks" not in G:
        G["chunks"] = build_chunks()
    ch = next((x for x in G["chunks"] if x["start"] <= t < x["end"]), None)
    if ch is None:
        return
    size = 80
    f = font("black", size)
    words = [w["text"].upper() for w in ch["words"]]
    space = size * 0.34
    widths = [text_w(w, f) for w in words]
    max_w = 860
    lines = [[0]]
    lw = widths[0]
    for i in range(1, len(words)):
        if lw + space + widths[i] > max_w:
            lines.append([i]); lw = widths[i]
        else:
            lines[-1].append(i); lw += space + widths[i]
    active = 0
    for i, w in enumerate(ch["words"]):
        if t >= w["start"] - 0.02:
            active = i
    p = prog(t, ch["start"], 0.14)
    s = lerp(0.82, 1.0, ease_back(p, 3.0))
    cx, cy = 520, 1330
    lh = size * 1.12
    y0 = cy - (len(lines) - 1) * lh / 2 + size * 0.36
    c.save(); c.translate(cx, cy); c.scale(s, s); c.translate(-cx, -cy)
    for li, line in enumerate(lines):
        tot = sum(widths[i] for i in line) + space * (len(line) - 1)
        x = cx - tot / 2
        y = y0 + li * lh
        for i in line:
            is_act = i == active
            wp = prog(t, ch["words"][i]["start"] - 0.02, 0.12) if is_act else 0
            sc = 1 + 0.05 * ease_back(wp) if is_act else 1.0
            wx = x + widths[i] / 2
            c.save(); c.translate(wx, y); c.scale(sc, sc)
            # shadow, outline, fill
            c.drawString(words[i], -widths[i] / 2, 8, f, paint((0, 0, 0), 0.55, blur=10))
            c.drawString(words[i], -widths[i] / 2, 0, f, paint((0, 0, 0), 1, stroke=17))
            c.drawString(words[i], -widths[i] / 2, 0, f, paint(YELLOW if is_act else WHITE, 1))
            c.restore()
            x += widths[i] + space
    c.restore()


# ------------------------------------------------------------------ frame composition
def scene_at(t):
    """[(scene_key, transform)] for time t."""
    starts = [(s["scene"], s["start"]) for s in TL["scenes"] if s["scene"] in SCENES]
    cur = 1
    for sc, st in starts:
        if t >= st:
            cur = sc
    return cur, starts


def render_scene_image(key, t):
    surf = G["scene_surf"]
    c = surf.getCanvas()
    c.clear(skia.Color4f(0, 0, 0, 0))
    SCENES[key](c, t)
    return surf.makeImageSnapshot()


def render_frame(i):
    t = i / FPS
    surf = G["surf"]
    c = surf.getCanvas()
    draw_background(c, t)
    cur, starts = scene_at(t)
    smap = dict(starts)
    order = [k for k, _ in starts]
    # transition window around each scene start
    trans = None
    for k in order[1:]:
        st = smap[k]
        if st - TD / 2 <= t < st + TD / 2:
            prev = order[order.index(k) - 1]
            trans = (prev, k, (t - (st - TD / 2)) / TD, TRANS.get(k, "zoom"))
    samp = skia.SamplingOptions(skia.FilterMode.kLinear)
    glitch = None
    if trans is None:
        img = render_scene_image(cur, t)
        c.drawImage(img, 0, 0)
    else:
        a, b, p, kind = trans
        ia = render_scene_image(a, t)
        ib = render_scene_image(b, t)
        if kind == "zoom":
            e = ease_io(p)
            for img, sc, al in ((ia, 1 + 0.55 * e, 1 - e), (ib, 0.75 + 0.25 * e, e)):
                c.save(); c.translate(W / 2, H * 0.42); c.scale(sc, sc); c.translate(-W / 2, -H * 0.42)
                c.drawImage(img, 0, 0, samp, skia.Paint(Alphaf=clamp(al)))
                c.restore()
            c.drawRect(skia.Rect.MakeWH(W, H), paint(WHITE, 0.18 * math.sin(math.pi * p)))
        elif kind in ("whip", "slide"):
            e = ease_io(p)
            vel = math.sin(math.pi * p)          # speed profile for motion blur
            horiz = kind == "whip"
            n = 7
            for img, off in ((ia, -e), (ib, 1 - e)):
                for k in range(n):
                    d = (off + vel * 0.12 * (k / (n - 1) - 0.5)) * (W if horiz else H)
                    c.drawImage(img, d if horiz else 0, 0 if horiz else d, samp,
                                skia.Paint(Alphaf=1.0 / n * 1.6 if k else 1.0 / n * 1.6))
        else:  # glitch: cut in the middle, the frame is broken up below
            img = ia if p < 0.5 else ib
            c.drawImage(img, 0, 0)
            glitch = p
    c.drawImage(vignette(), 0, 0)
    if glitch is not None:
        arr = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)
        arr[..., :3] = glitch_fx(arr[..., :3], glitch, i)
        c.drawImage(skia.Image.fromarray(np.ascontiguousarray(arr)), 0, 0)
    # captions go on top of transitions and glitches
    draw_captions(c, t)
    out = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)[..., :3]
    return np.ascontiguousarray(out)


def glitch_fx(arr, p, seed):
    rng = np.random.default_rng(seed)
    amt = math.sin(math.pi * p)
    out = arr.copy()
    # RGB split
    s = int(28 * amt)
    if s:
        out[..., 0] = np.roll(arr[..., 0], s, axis=1)
        out[..., 2] = np.roll(arr[..., 2], -s, axis=1)
    # displaced slices
    for _ in range(int(14 * amt) + 2):
        y = rng.integers(0, H - 10)
        h = rng.integers(8, 90)
        dx = int(rng.integers(-160, 160) * amt)
        out[y:y + h] = np.roll(out[y:y + h], dx, axis=1)
    # blocky color noise
    for _ in range(int(10 * amt)):
        y, x = rng.integers(0, H - 60), rng.integers(0, W - 200)
        out[y:y + rng.integers(10, 50), x:x + rng.integers(60, 200)] = rng.choice(
            [CYAN, MAGENTA, (255, 255, 255)], 1)[0]
    # scanlines
    out[::4] = (out[::4] * (1 - 0.35 * amt)).astype(np.uint8)
    return out


# ------------------------------------------------------------------ process setup
def init():
    global TL, EV
    TL = json.load(open(os.path.join(BUILD, "timeline.json")))
    EV = TL["events"]
    info = skia.ImageInfo.Make(W, H, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType)
    G["surf"] = skia.Surface.MakeRaster(info)
    G["scene_surf"] = skia.Surface.MakeRaster(info)
    stadium_points(); vignette(); brain_path(); particles()


def worker(i):
    return render_frame(i).tobytes()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "video"
    if mode == "preview":
        from PIL import Image
        init()
        os.makedirs(os.path.join(BUILD, "preview"), exist_ok=True)
        for s in sys.argv[2:]:
            i = int(round(float(s) * FPS))
            Image.fromarray(render_frame(i)).save(os.path.join(BUILD, "preview", f"f_{float(s):06.2f}.png"))
            print("wrote", s)
    elif mode == "video":
        import multiprocessing as mp, time
        tl = json.load(open(os.path.join(BUILD, "timeline.json")))
        n = int(round(tl["duration"] * FPS))
        out = os.path.join(BUILD, "video.mp4")
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                               "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                               "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2", "-g", "60",
                               "-threads", "2", out], stdin=subprocess.PIPE)
        t0 = time.time()
        with mp.Pool(int(os.environ.get("WORKERS", os.cpu_count())), initializer=init) as pool:
            for k, buf in enumerate(pool.imap(worker, range(n), chunksize=6)):
                ff.stdin.write(buf)
                if k % 150 == 0:
                    el = time.time() - t0
                    print(f"frame {k}/{n}  {el:.0f}s elapsed, eta {el / (k + 1) * (n - k - 1):.0f}s", flush=True)
        ff.stdin.close()
        ff.wait()
        print("video done", time.time() - t0)
    elif mode == "mux":
        out = os.path.join(ROOT, "high_iq_tiktok.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(BUILD, "video.mp4"),
                        "-i", os.path.join(BUILD, "mix.wav"), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                        "-t", "60.0", "-movflags", "+faststart", out], check=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
