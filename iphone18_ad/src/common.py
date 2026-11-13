"""Shared constants and image helpers for the iPhone 18 Pro Max concept ad.

All scene rendering happens in linear-light float32 RGB (H, W, 3). `finish()` adds
bloom, tone-maps, encodes to display gamma and returns float [0, 1] for overlays.
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
DURATION = 30.0
N_FRAMES = int(round(DURATION * FPS))  # 900

FONT_DIR = "/usr/share/fonts/opentype/inter"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Accent colours (linear light)
TI_BLUE = np.array([0.055, 0.105, 0.220], np.float32)      # deep titanium blue
TI_BLUE_HI = np.array([0.30, 0.48, 0.95], np.float32)      # bright blue glow
ORANGE = np.array([1.00, 0.36, 0.06], np.float32)          # warm orange
ORANGE_HI = np.array([1.00, 0.58, 0.22], np.float32)
CYAN = np.array([0.25, 0.75, 1.00], np.float32)
WHITE = np.array([1.0, 1.0, 1.0], np.float32)


# ----------------------------------------------------------------------------- easing
def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def lin(t, a, b):
    """0 before a, 1 after b, linear in between."""
    if b <= a:
        return float(t >= b)
    return float(min(1.0, max(0.0, (t - a) / (b - a))))


def ease_in_out(x):
    x = min(1.0, max(0.0, float(x)))
    return x * x * (3 - 2 * x)


def ease_in_out_cubic(x):
    x = min(1.0, max(0.0, float(x)))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_in_out_sine(x):
    x = min(1.0, max(0.0, float(x)))
    return -(math.cos(math.pi * x) - 1) / 2


def ease_out_cubic(x):
    x = min(1.0, max(0.0, float(x)))
    return 1 - (1 - x) ** 3


def ease_out_quart(x):
    x = min(1.0, max(0.0, float(x)))
    return 1 - (1 - x) ** 4


def ease_in_cubic(x):
    x = min(1.0, max(0.0, float(x)))
    return x ** 3


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return a + (b - a) * t


# ----------------------------------------------------------------------------- fonts
_font_cache = {}


def font(name, size):
    key = (name, size)
    if key not in _font_cache:
        path = os.path.join(FONT_DIR, name)
        try:
            _font_cache[key] = ImageFont.truetype(path, size)
        except OSError:
            _font_cache[key] = ImageFont.truetype(FALLBACK_FONT, size)
    return _font_cache[key]


def text_layer(text, fnt, tracking=0.0, pad=40):
    """Render text to a float alpha mask (h, w) with optional letter tracking (px).

    Returns (alpha, ascent_offset) where the text's visual box is centred.
    """
    if tracking == 0.0:
        l, t, r, b = fnt.getbbox(text)
        w, h = r - l + 2 * pad, b - t + 2 * pad
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((pad - l, pad - t), text, font=fnt, fill=255)
        return np.asarray(img, np.float32) / 255.0
    # manual tracking: draw glyph by glyph using advance widths
    widths = [fnt.getlength(c) for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    l, t, r, b = fnt.getbbox(text)
    w, h = int(math.ceil(total)) + 2 * pad, b - t + 2 * pad
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    x = pad - l
    for c, cw in zip(text, widths):
        d.text((x, pad - t), c, font=fnt, fill=255)
        x += cw + tracking
    return np.asarray(img, np.float32) / 255.0


# ----------------------------------------------------------------------------- blur
def _box_axis(a, r, axis):
    """Box blur of radius r (int) along axis using cumulative sums, edge-clamped."""
    if r < 1:
        return a
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(p, axis=axis, dtype=np.float32)
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * r + 1)


def _resize_f(a, size):
    """Resize float array (h, w[, c]) to size=(w, h) using Pillow 'F' bilinear."""
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize(size, Image.BILINEAR))
    return np.stack([_resize_f(a[..., i], size) for i in range(a.shape[2])], axis=-1)


def resize(a, size, resample=Image.BILINEAR):
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32), "F").resize(size, resample))
    return np.stack([resize(a[..., i], size, resample) for i in range(a.shape[2])], axis=-1)


def blur(a, sigma):
    """Approximate Gaussian blur (3 box passes) with automatic downsampling."""
    if sigma <= 0.3:
        return a
    h, w = a.shape[:2]
    f = 1
    while sigma / f > 6 and min(h, w) // (f * 2) >= 16:
        f *= 2
    small = a
    if f > 1:
        small = _resize_f(a, (max(1, w // f), max(1, h // f)))
    s = sigma / f
    r = max(1, int(round(math.sqrt(12 * s * s / 3 + 1) - 1) // 2))
    for _ in range(3):
        small = _box_axis(small, r, 0)
        small = _box_axis(small, r, 1)
    if f > 1:
        small = _resize_f(small, (w, h))
    return small.astype(np.float32)


# ----------------------------------------------------------------------------- compositing
def over(base, color, alpha):
    """Composite straight colour (3,) or (h,w,3) with alpha (h,w) over base, in place."""
    a = alpha[..., None]
    base *= (1 - a)
    base += color * a
    return base


def paste_add(base, layer, x0, y0):
    """Add a (h, w, 3) layer into base at integer offset, clipped to the frame."""
    h, w = layer.shape[:2]
    H_, W_ = base.shape[:2]
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W_, x0 + w), min(H_, y0 + h)
    if xa >= xb or ya >= yb:
        return base
    base[ya:yb, xa:xb] += layer[ya - y0:yb - y0, xa - x0:xb - x0]
    return base


def paste_over(base, color_layer, alpha, x0, y0):
    """Alpha-composite a (h, w, 3) straight-colour layer with alpha (h, w) at offset."""
    h, w = alpha.shape
    H_, W_ = base.shape[:2]
    xa, ya = max(0, x0), max(0, y0)
    xb, yb = min(W_, x0 + w), min(H_, y0 + h)
    if xa >= xb or ya >= yb:
        return base
    a = alpha[ya - y0:yb - y0, xa - x0:xb - x0, None]
    c = color_layer if np.ndim(color_layer) == 1 else color_layer[ya - y0:yb - y0, xa - x0:xb - x0]
    region = base[ya:yb, xa:xb]
    region *= (1 - a)
    region += c * a
    return base


def radial_glow(h, w, cx, cy, radius, color, power=2.0):
    """Soft radial falloff glow image (h, w, 3)."""
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / radius
    g = np.exp(-d ** power)
    return g[..., None] * np.asarray(color, np.float32)


_grid_cache = {}


def pixel_grid(h=H, w=W):
    key = (h, w)
    if key not in _grid_cache:
        ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
        _grid_cache[key] = (xs, ys)
    return _grid_cache[key]


def vignette(img, strength=0.35):
    xs, ys = pixel_grid(*img.shape[:2])
    h, w = img.shape[:2]
    d = ((xs - w / 2) / (w / 2)) ** 2 + ((ys - h / 2) / (h / 2)) ** 2
    v = 1 - strength * smoothstep(0.3, 2.0, d)
    img *= v[..., None]
    return img


def zoom(img, scale, cx=None, cy=None):
    """Scale an image about (cx, cy) keeping the frame size (scale > 1 zooms in)."""
    if abs(scale - 1.0) < 1e-4:
        return img
    h, w = img.shape[:2]
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    out = np.empty_like(img)
    # affine: src = (dst - c) / scale + c
    a = 1.0 / scale
    coeffs = (a, 0, cx - a * cx, 0, a, cy - a * cy)
    for i in range(img.shape[2]):
        out[..., i] = np.asarray(Image.fromarray(img[..., i], "F").transform(
            (w, h), Image.AFFINE, coeffs, resample=Image.BILINEAR))
    return out


# ----------------------------------------------------------------------------- post
def bloom(img, threshold=0.75, strength=0.6, radii=(6, 22, 70), weights=(0.5, 0.35, 0.25)):
    lum = img.max(axis=2, keepdims=True)
    bright = img * np.clip((lum - threshold) / np.maximum(lum, 1e-4), 0, None)
    acc = np.zeros_like(img)
    for r, wt in zip(radii, weights):
        acc += blur(bright, r) * wt
    return img + acc * strength


def tonemap(img, knee=0.62):
    """Identity below the knee, smooth exponential shoulder above (per channel)."""
    out = img.copy()
    m = img > knee
    x = img[m] - knee
    out[m] = knee + (1 - knee) * (1 - np.exp(-x / (1 - knee)))
    return out


def to_display(img):
    return np.power(np.clip(img, 0, 1), 1 / 2.2)


def to_linear(img):
    return np.power(np.clip(img, 0, 1), 2.2)


def finish(img, bloom_kw=None, exposure=1.0):
    if exposure != 1.0:
        img = img * exposure
    if bloom_kw is not False:
        img = bloom(img, **(bloom_kw or {}))
    return to_display(tonemap(img))


def quantize(disp, seed):
    """Display-space float -> uint8 with light triangular dither (fights banding)."""
    rng = np.random.default_rng(seed)
    n = (rng.random(disp.shape[:2], np.float32) - rng.random(disp.shape[:2], np.float32))[..., None]
    out = disp * 255.0 + n * 0.9
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)
