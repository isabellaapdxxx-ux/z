"""Procedural drawing primitives: noise, foggy forests, the faceless figure,
children silhouettes, old-photo treatment. Images are float32 RGB in [0, 1]."""
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/opentype/inter/"


def font(size, weight="Black"):
    return ImageFont.truetype(f"{FONT_DIR}Inter-{weight}.otf", size)


def lerp(a, b, t):
    return np.asarray(a, np.float32) + (np.asarray(b, np.float32) - np.asarray(a, np.float32)) * t


def fbm(h, w, seed, octaves=5, base=3, persistence=0.55):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gh = base * 2 ** o
        gw = max(2, int(round(gh * w / h)))
        g = rng.random((gh + 1, gw + 1)).astype(np.float32)
        out += amp * cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC)
        tot += amp
        amp *= persistence
    out /= tot
    return (out - out.min()) / (out.max() - out.min() + 1e-6)


def blur(img, r):
    if r <= 0.3:
        return img
    k = int(r * 3) * 2 + 1
    return cv2.GaussianBlur(img, (k, k), r)


def mask_from_draw(w, h, fn):
    m = Image.new("L", (w, h), 0)
    fn(ImageDraw.Draw(m))
    return np.asarray(m, np.float32) / 255.0


def comp(img, mask, color):
    """Composite a flat colour (or colour image) through a mask."""
    m = mask[..., None]
    return img * (1 - m) + np.asarray(color, np.float32) * m


# ----------------------------------------------------------------- figure
def figure_polys(x, y, H, arms_out=0.0):
    """Polygons for the tall faceless figure. Returns dict part -> list of polygons/ellipses."""
    top = y - H
    P = lambda dx, dy: (x + dx * H, top + dy * H)
    head = [P(-0.028, 0.004), P(0.028, 0.104)]  # ellipse bbox
    neck = [P(-0.011, 0.09), P(0.011, 0.09), P(0.013, 0.14), P(-0.013, 0.14)]
    torso = [P(-0.03, 0.125), P(-0.086, 0.155), P(-0.092, 0.18), P(-0.074, 0.31), P(-0.056, 0.47),
             P(0.056, 0.47), P(0.074, 0.31), P(0.092, 0.18), P(0.086, 0.155), P(0.03, 0.125)]
    legs = [[P(-0.054, 0.44), P(-0.006, 0.44), P(-0.016, 0.995), P(-0.036, 1.0), P(-0.044, 0.995)],
            [P(0.054, 0.44), P(0.006, 0.44), P(0.016, 0.995), P(0.036, 1.0), P(0.044, 0.995)]]
    arms = []
    fingers = []
    for s in (-1, 1):
        sx = 0.088 * s
        hx = (0.112 + arms_out) * s
        arms.append([P(sx - 0.016 * s, 0.16), P(sx + 0.014 * s, 0.165), P(hx + 0.009 * s, 0.67),
                     P(hx - 0.007 * s, 0.67)])
        for k, (fx, fl) in enumerate([(-0.006, 0.07), (0.0, 0.085), (0.006, 0.075), (0.011, 0.06)]):
            fingers.append([P(hx + fx * s, 0.665), P(hx + fx * s + 0.003 * s, 0.665),
                            P(hx + (fx + 0.004) * s, 0.665 + fl), P(hx + (fx + 0.002) * s, 0.665 + fl)])
    shirt = [P(-0.024, 0.128), P(0.024, 0.128), P(0.0, 0.25)]
    tie = [P(-0.006, 0.135), P(0.006, 0.135), P(0.010, 0.225), P(0.0, 0.248), P(-0.010, 0.225)]
    return dict(head=head, neck=neck, torso=torso, legs=legs, arms=arms, fingers=fingers, shirt=shirt, tie=tie)


def draw_figure(img, x, y, H, suit, pale, blur_r=0.8, arms_out=0.0, alpha=1.0):
    h, w = img.shape[:2]
    p = figure_polys(x, y, H, arms_out)

    def body(d):
        d.polygon(p["torso"], fill=255)
        for l in p["legs"] + p["arms"] + p["fingers"]:
            d.polygon(l, fill=255)

    m_body = blur(mask_from_draw(w, h, body), blur_r) * alpha
    img = comp(img, m_body, suit)
    m_shirt = blur(mask_from_draw(w, h, lambda d: d.polygon(p["shirt"], fill=255)), blur_r) * alpha
    img = comp(img, m_shirt, lerp(suit, pale, 0.5))
    m_neck = blur(mask_from_draw(w, h, lambda d: d.polygon(p["neck"], fill=255)), blur_r) * alpha
    img = comp(img, m_neck, lerp(pale, suit, 0.78))
    m_tie = blur(mask_from_draw(w, h, lambda d: d.polygon(p["tie"], fill=255)), blur_r) * alpha
    img = comp(img, m_tie, np.asarray(suit) * 0.6)
    # head: pale, with soft shading (no features at all)
    (x0, y0), (x1, y1) = p["head"]
    m_head = blur(mask_from_draw(w, h, lambda d: d.ellipse([x0, y0, x1, y1], fill=255)), blur_r) * alpha
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 + 1e-3, (y1 - y0) / 2 + 1e-3
    d2 = ((xx - cx + 0.25 * rx) / rx) ** 2 + ((yy - cy + 0.3 * ry) / ry) ** 2
    shade = np.clip(1.05 - 0.45 * d2, 0.45, 1.0)
    shade *= 1 - 0.38 * np.clip((yy - cy) / ry, 0, 1) ** 2          # chin falls into shadow
    shade = shade[..., None]
    img = img * (1 - m_head[..., None]) + (np.asarray(pale, np.float32) * shade) * m_head[..., None]
    return img


# ----------------------------------------------------------------- trees
def draw_tree(d, rng, x, ground, h_img, bw, lean, branchiness):
    top_w = bw * 0.55
    xt = x + lean
    d.polygon([(x - bw / 2, ground + 8), (x + bw / 2, ground + 8), (xt + top_w / 2, -40), (xt - top_w / 2, -40)], fill=255)
    n_br = int(rng.integers(2, 6) * branchiness)
    for _ in range(n_br):
        fy = rng.uniform(0.08, 0.75)
        by = ground - fy * (ground + 40)
        bx = x + lean * (ground - by) / (ground + 40)
        side = rng.choice([-1, 1])
        L = rng.uniform(0.6, 1.6) * h_img * 0.06 * (bw / 30) ** 0.5
        ang = np.deg2rad(rng.uniform(25, 65))
        ex, ey = bx + side * L * np.sin(ang), by - L * np.cos(ang)
        thick = max(1.5, bw * 0.16)
        d.polygon([(bx, by - thick), (bx, by + thick), (ex, ey)], fill=255)
        # twig
        tx, ty = bx + side * L * 0.55 * np.sin(ang), by - L * 0.55 * np.cos(ang)
        d.line([(tx, ty), (tx + side * L * 0.35, ty - L * 0.45)], fill=255, width=max(1, int(thick * 0.5)))


def forest(w, h, seed, horizon=0.6, tint=(0.36, 0.42, 0.47), layers=6, density=1.0, fig=None,
           ground_dark=0.02, fog_amt=1.0, kids=None, sky_light=1.0):
    """Foggy forest. fig = dict(layer, x, y, h, alpha) places the figure among the trees."""
    rng = np.random.default_rng(seed)
    tint = np.asarray(tint, np.float32)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    sky_top = tint * 0.25
    hz = tint * sky_light
    sky = sky_top + (hz - sky_top) * np.clip(yy / horizon, 0, 1) ** 1.4
    gnd = hz + (np.full(3, ground_dark, np.float32) - hz) * np.clip((yy - horizon) / (1 - horizon), 0, 1) ** 0.7
    img = np.where(yy < horizon, sky, gnd) * np.ones((1, w, 1), np.float32)
    mott = fbm(h // 4, w // 4, seed + 1)
    img *= (0.8 + 0.4 * cv2.resize(mott, (w, h)))[..., None]
    near_col = np.full(3, 0.008, np.float32)
    for i in range(layers):
        dpt = i / max(1, layers - 1)
        col = lerp(hz * 0.9, near_col, dpt ** 0.75)
        ground = horizon * h + dpt * (h * (1 - horizon)) * 0.6 + rng.uniform(-8, 8)
        count = max(1, int((13 - 9 * dpt) * density * w / 1080))
        xs = np.sort(rng.uniform(-0.05 * w, 1.05 * w, count))
        bws = (5 + 80 * dpt ** 1.8) * (w / 1080) * rng.uniform(0.7, 1.3, count)

        def trees(d):
            for x, bw in zip(xs, bws):
                if fig is not None and i >= fig["layer"] and abs(x - fig["x"]) < fig["h"] * fig.get("clear", 0.13) + bw / 2:
                    continue  # keep the figure readable
                draw_tree(d, rng, x, ground + rng.uniform(-10, 10), h, bw, rng.uniform(-0.03, 0.03) * h, 1 + dpt)

        m = blur(mask_from_draw(w, h, trees), (1 - dpt) * 5 + 0.7)
        img = comp(img, m, col)
        if kids is not None and kids["layer"] == i:
            img = draw_kids(img, kids, col)
        if fig is not None and fig["layer"] == i:
            suit = col * 0.55
            pale = lerp(hz, (0.88, 0.87, 0.84), 0.55 + 0.45 * dpt ** 0.6) * fig.get("pale", 1.0)
            img = draw_figure(img, fig["x"], fig["y"], fig["h"], suit, pale, (1 - dpt) * 3 + 0.8,
                              fig.get("arms_out", 0.0), fig.get("alpha", 1.0))
        if i < layers - 1:  # haze between depth layers
            f = cv2.resize(fbm(h // 6, w // 6, seed + 10 + i, octaves=4), (w, h))
            band = np.exp(-((yy[..., 0] - horizon - 0.05) / 0.25) ** 2)
            a = (0.10 + 0.18 * f * band) * fog_amt
            img = img * (1 - a[..., None]) + hz * a[..., None]
    return np.clip(img, 0, 1)


def draw_kids(img, kids, col):
    """Small generic silhouettes of children (no faces) for the old 'photo'."""
    h, w = img.shape[:2]
    c = np.asarray(kids.get("color", col), np.float32)

    def fn(d):
        for (x, y, s, pose) in kids["list"]:
            hr = 0.09 * s
            d.ellipse([x - hr, y - s, x + hr, y - s + 2 * hr], fill=255)
            d.polygon([(x - 0.11 * s, y - s + 2 * hr), (x + 0.11 * s, y - s + 2 * hr),
                       (x + 0.15 * s, y - 0.45 * s), (x - 0.15 * s, y - 0.45 * s)], fill=255)
            d.polygon([(x - 0.1 * s, y - 0.46 * s), (x - 0.02 * s, y - 0.46 * s), (x - 0.05 * s - pose * 0.05 * s, y), (x - 0.11 * s - pose * 0.05 * s, y)], fill=255)
            d.polygon([(x + 0.1 * s, y - 0.46 * s), (x + 0.02 * s, y - 0.46 * s), (x + 0.05 * s + pose * 0.08 * s, y), (x + 0.11 * s + pose * 0.08 * s, y)], fill=255)
            for sd in (-1, 1):
                ax = x + sd * 0.12 * s
                d.polygon([(ax, y - s + 2.3 * hr), (ax + sd * 0.04 * s, y - s + 2.3 * hr),
                           (ax + sd * (0.06 + 0.12 * pose) * s, y - 0.5 * s), (ax + sd * (0.02 + 0.12 * pose) * s, y - 0.5 * s)], fill=255)

    m = blur(mask_from_draw(w, h, fn), 1.0)
    return comp(img, m, c)


# ----------------------------------------------------------------- photo treatment
def old_photo(img, seed, sepia=0.25, contrast=1.15, border=0.05, bottom=None):
    """Black & white aged photo with white border; returns RGB float."""
    rng = np.random.default_rng(seed)
    g = img @ np.array([0.3, 0.59, 0.11], np.float32)
    g = np.clip((g - 0.5) * contrast + 0.5, 0, 1)
    h, w = g.shape
    g = g + rng.normal(0, 0.035, g.shape).astype(np.float32)
    g = g * (0.85 + 0.15 * cv2.resize(fbm(h // 8, w // 8, seed), (w, h)))
    # scratches + dust
    for _ in range(14):
        x = rng.uniform(0, w)
        cv2.line(g, (int(x), 0), (int(x + rng.uniform(-30, 30)), h), float(rng.uniform(0.6, 0.95)), 1)
    for _ in range(120):
        cv2.circle(g, (int(rng.uniform(0, w)), int(rng.uniform(0, h))), int(rng.integers(1, 3)), float(rng.uniform(0, 1) > 0.5), -1)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    v = 1 - 0.45 * (((xx / w - 0.5) * 1.6) ** 2 + ((yy / h - 0.5) * 1.6) ** 2)
    g = np.clip(g * v, 0, 1)
    rgb = np.stack([g * (1 + 0.08 * sepia), g * (1 + 0.02 * sepia), g * (1 - 0.12 * sepia)], -1)
    b = int(border * w)
    bb = b if bottom is None else int(bottom * w)
    out = np.ones((h + b + bb, w + 2 * b, 3), np.float32) * np.array([0.86, 0.84, 0.78], np.float32)
    out[b:b + h, b:b + w] = np.clip(rgb, 0, 1)
    return out


def paste(dst, src, x, y, angle=0.0, shadow=True, alpha=1.0):
    """Paste src centred at (x, y) rotated by angle degrees, with a soft shadow."""
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    M[0, 2] += x - w / 2
    M[1, 2] += y - h / 2
    rgb = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR)
    m = cv2.warpAffine(np.ones((h, w), np.float32), M, (W, H), flags=cv2.INTER_LINEAR)
    if shadow:
        Ms = M.copy()
        Ms[0, 2] += 18
        Ms[1, 2] += 26
        sm = blur(cv2.warpAffine(np.ones((h, w), np.float32), Ms, (W, H)), 22) * 0.7 * alpha
        dst = dst * (1 - sm[..., None])
    m = m * alpha
    return dst * (1 - m[..., None]) + rgb * m[..., None]


def text_layer(w, h, items):
    """items: (x, y, text, size, weight, rgba, anchor). Returns (rgb, alpha) float arrays."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x, y, s, size, weight, col, anchor in items:
        d.text((x, y), s, font=font(size, weight), fill=col, anchor=anchor)
    a = np.asarray(im, np.float32) / 255.0
    return a[..., :3], a[..., 3]


def over(dst, rgb, a, x=0, y=0):
    h, w = a.shape
    region = dst[y:y + h, x:x + w]
    region[:] = region * (1 - a[..., None]) + rgb * a[..., None]
    return dst
