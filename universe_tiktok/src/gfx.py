"""Drawing primitives on float32 RGB frames (H, W, 3), linear-ish 0..1+ values."""
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

from config import FONT_BOLD, FONT_EMOJI, FONT_XBOLD, H, W

HW = H * W


def frame():
    return np.zeros((H, W, 3), np.float32)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


# ------------------------------------------------------------------ splatting
def splat(img, x, y, rgb, spread=0.0):
    """Additively splat points with bilinear weights. rgb: (N,3) weights.
    spread>0 adds 4 neighbours at +-1 px with weight `spread` (bigger dots)."""
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    rgb = np.asarray(rgb, np.float32)
    m = (x > -2) & (x < W + 1) & (y > -2) & (y < H + 1)
    if not m.any():
        return
    x, y, rgb = x[m], y[m], rgb[m]
    if spread > 0:
        xs = [x, x + 1.2, x - 1.2, x, x]
        ys = [y, y, y, y + 1.2, y - 1.2]
        ws = [rgb] + [rgb * spread] * 4
        x = np.concatenate(xs)
        y = np.concatenate(ys)
        rgb = np.concatenate(ws)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    idx, wts = [], []
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                      (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xx, yy = x0 + dx, y0 + dy
        ok = (xx >= 0) & (xx < W) & (yy >= 0) & (yy < H)
        idx.append((yy * W + xx)[ok])
        wts.append((rgb * w)[ok])
    idx = np.concatenate(idx)
    wts = np.concatenate(wts)
    flat = img.reshape(HW, 3)
    for c in range(3):
        flat[:, c] += np.bincount(idx, wts[:, c], minlength=HW).astype(np.float32)


def splat_buffer(x, y, rgb, scale=1):
    """Splat into a separate (H/scale, W/scale, 3) buffer (for blurred glows)."""
    h, w = H // scale, W // scale
    buf = np.zeros((h, w, 3), np.float32)
    x = np.asarray(x, np.float32) / scale
    y = np.asarray(y, np.float32) / scale
    xi = np.round(x).astype(np.int32)
    yi = np.round(y).astype(np.int32)
    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    idx = yi[ok] * w + xi[ok]
    rgb = np.asarray(rgb, np.float32)[ok]
    flat = buf.reshape(-1, 3)
    for c in range(3):
        flat[:, c] += np.bincount(idx, rgb[:, c], minlength=h * w).astype(np.float32)
    return buf


def upsample(buf, scale):
    """Bilinear upsample a (h, w, 3) float buffer to full frame."""
    if scale == 1:
        return buf
    out = np.empty((H, W, 3), np.float32)
    for c in range(3):
        out[..., c] = np.asarray(Image.fromarray(buf[..., c]).resize((W, H), Image.BILINEAR))
    return out


def blur(buf, sigma):
    return ndimage.gaussian_filter(buf, (sigma, sigma, 0), mode="constant")


# ------------------------------------------------------------------ shapes
def box(cx, cy, r):
    x0, x1 = int(max(0, np.floor(cx - r))), int(min(W, np.ceil(cx + r) + 1))
    y0, y1 = int(max(0, np.floor(cy - r))), int(min(H, np.ceil(cy + r) + 1))
    return x0, x1, y0, y1


def add_glow(img, cx, cy, r, color, strength=1.0, halo=0.0, halo_r=None, extent=None):
    """Gaussian core (sigma=r) plus optional 1/(1+d^2) halo."""
    halo_r = halo_r or r * 3
    ext = extent or (max(3.2 * r, halo_r * (8 if halo else 0)))
    x0, x1, y0, y1 = box(cx, cy, ext)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    v = strength * np.exp(-d2 / (2 * r * r))
    if halo:
        # taper the halo to zero inside the box so no rectangle edge shows
        win = smoothstep(ext * ext, ext * ext * 0.25, d2).astype(np.float32)
        v = v + halo * win / (1 + d2 / (halo_r * halo_r))
    img[y0:y1, x0:x1] += v[..., None] * np.asarray(color, np.float32)


def disc_alpha(cx, cy, r, x0, x1, y0, y1):
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    return np.clip(r - d + 0.5, 0, 1), xx, yy


def over(img, rgb, alpha, x0, y0):
    """Alpha-composite rgb (h,w,3) with alpha (h,w) at (x0,y0), clipped."""
    h, w = alpha.shape
    X0, Y0 = max(0, x0), max(0, y0)
    X1, Y1 = min(W, x0 + w), min(H, y0 + h)
    if X0 >= X1 or Y0 >= Y1:
        return
    a = alpha[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0, None]
    c = rgb[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0]
    reg = img[Y0:Y1, X0:X1]
    reg *= (1 - a)
    reg += c * a


def add(img, rgb, x0, y0, k=1.0):
    h, w = rgb.shape[:2]
    X0, Y0 = max(0, x0), max(0, y0)
    X1, Y1 = min(W, x0 + w), min(H, y0 + h)
    if X0 >= X1 or Y0 >= Y1:
        return
    img[Y0:Y1, X0:X1] += k * rgb[Y0 - y0:Y1 - y0, X0 - x0:X1 - x0]


# ------------------------------------------------------------------ layers drawn with PIL
class Layer:
    """A PIL 'L' layer the size of the frame for anti-aliased lines/shapes.
    Use .draw, then .add_to(img, color, k) (additive) and optional glow."""

    def __init__(self, scale=2):
        self.s = scale  # supersampling factor
        self.im = Image.new("L", (W * scale, H * scale), 0)
        self.draw = ImageDraw.Draw(self.im)

    def P(self, *pts):
        return [(x * self.s, y * self.s) for x, y in pts]

    def line(self, pts, width, fill=255):
        self.draw.line(self.P(*pts), fill=fill, width=max(1, int(round(width * self.s))))

    def ellipse(self, cx, cy, rx, ry, outline=None, fill=None, width=1):
        s = self.s
        self.draw.ellipse([(cx - rx) * s, (cy - ry) * s, (cx + rx) * s, (cy + ry) * s],
                          outline=outline, fill=fill, width=max(1, int(width * s)))

    def array(self, glow=0.0):
        im = self.im.resize((W, H), Image.BOX) if self.s > 1 else self.im
        a = np.asarray(im, np.float32) / 255.0
        if glow:
            g = im.resize((W // 4, H // 4), Image.BOX).filter(ImageFilter.GaussianBlur(glow / 4))
            g = np.asarray(g.resize((W, H), Image.BILINEAR), np.float32) / 255.0
            return a, g
        return a, None

    def add_to(self, img, color, k=1.0, glow=0.0, glow_k=1.5):
        a, g = self.array(glow)
        col = np.asarray(color, np.float32)
        img += (a * k)[..., None] * col
        if g is not None:
            img += (g * glow_k)[..., None] * col


# ------------------------------------------------------------------ text
@lru_cache(maxsize=None)
def font(size, bold="x"):
    return ImageFont.truetype(str(FONT_XBOLD if bold == "x" else FONT_BOLD), size)


@lru_cache(maxsize=256)
def text_rgba(text, size, fill=(255, 255, 255), stroke=0, stroke_fill=(0, 0, 0),
              max_w=None, weight="x", tracking=0):
    """Tightly cropped RGBA text image (PIL). Shrinks to fit max_w."""
    while True:
        f = font(size, weight)
        if tracking:
            widths = [f.getlength(ch) for ch in text]
            tw = sum(widths) + tracking * (len(text) - 1)
        else:
            tw = f.getlength(text)
        if not max_w or tw + 2 * stroke <= max_w or size <= 20:
            break
        size = int(size * 0.95)
    asc, desc = f.getmetrics()
    pad = stroke + 6
    im = Image.new("RGBA", (int(tw) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if tracking:
        x = pad
        for ch, cw in zip(text, widths):
            d.text((x, pad), ch, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += cw + tracking
    else:
        d.text((pad, pad), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    bb = im.getbbox() or (0, 0, 1, 1)
    return im.crop((bb[0] - 2, bb[1] - 2, bb[2] + 2, bb[3] + 2))


@lru_cache(maxsize=8)
def emoji_rgba(ch, size):
    f = ImageFont.truetype(FONT_EMOJI, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)


def pil_to_np(im):
    a = np.asarray(im, np.float32) / 255.0
    return a[..., :3], a[..., 3]


def blit(img, im, cx, cy, alpha=1.0, scale=1.0, tint=None):
    """Composite a PIL RGBA image centred at (cx, cy)."""
    if alpha <= 0.003:
        return
    if abs(scale - 1.0) > 1e-3:
        w = max(1, int(round(im.width * scale)))
        h = max(1, int(round(im.height * scale)))
        im = im.resize((w, h), Image.BICUBIC)
    rgb, a = pil_to_np(im)
    if tint is not None:
        rgb = rgb * np.asarray(tint, np.float32)
    x0 = int(round(cx - im.width / 2))
    y0 = int(round(cy - im.height / 2))
    over(img, rgb, a * alpha, x0, y0)


_GLOW_CACHE = {}


def _glow_of(im, radius):
    key = (id(im), radius)
    hit = _GLOW_CACHE.get(key)
    if hit is not None and hit[0] is im:
        return hit[1]
    a = im.getchannel("A")
    small = a.resize((max(1, im.width // 2), max(1, im.height // 2)), Image.BOX)
    pad = int(radius * 1.5)
    canvas = Image.new("L", (small.width + 2 * pad, small.height + 2 * pad), 0)
    canvas.paste(small, (pad, pad))
    g = canvas.filter(ImageFilter.GaussianBlur(radius / 2))
    g = g.resize((g.width * 2, g.height * 2), Image.BILINEAR)
    if len(_GLOW_CACHE) > 400:
        _GLOW_CACHE.clear()
    _GLOW_CACHE[key] = (im, g)  # keep `im` alive so its id stays unique
    return g


def glow_text(img, im, cx, cy, color, k=1.0, radius=24, alpha=1.0, scale=1.0):
    """Text with an additive coloured glow behind it (glow cached per sprite)."""
    if alpha <= 0.003:
        return
    g = _glow_of(im, radius)
    if abs(scale - 1.0) > 1e-3:
        g = g.resize((max(1, int(g.width * scale)), max(1, int(g.height * scale))), Image.BILINEAR)
    ga = np.asarray(g, np.float32) / 255.0
    gx = int(round(cx - ga.shape[1] / 2))
    gy = int(round(cy - ga.shape[0] / 2))
    add(img, ga[..., None] * np.asarray(color, np.float32), gx, gy, k * alpha)
    blit(img, im, cx, cy, alpha, scale)


# ------------------------------------------------------------------ post
_VIG = None


def vignette():
    global _VIG
    if _VIG is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
        _VIG = (1 - 0.45 * smoothstep(0.55, 1.25, d)).astype(np.float32)[..., None]
    return _VIG


def bloom(img, threshold=0.55, k=0.6):
    s = 4
    small = img.reshape(H // s, s, W // s, s, 3).mean(axis=(1, 3))
    hi = np.maximum(small - threshold, 0)
    g1 = ndimage.gaussian_filter(hi, (4, 4, 0))
    g2 = ndimage.gaussian_filter(hi, (16, 16, 0))
    g = g1 * 0.6 + g2 * 0.8
    return img + k * upsample(g, s)


def tonemap(img):
    x = np.maximum(img, 0)
    knee = 0.8
    y = np.where(x < knee, x, knee + (1 - knee) * (1 - np.exp(-(x - knee) / (1 - knee))))
    return y


def to_u8(img):
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


# ------------------------------------------------------------------ noise textures
def value_noise(h, w, octaves=5, seed=0, base=4):
    """Tileable fractal noise in [0,1], shape (h, w): sum of wrapped,
    Gaussian-filtered white noise at halving scales."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp = 1.0
    for o in range(octaves):
        sigma = max(0.6, min(h, w) / (base * 2 ** o) / 1.5)
        n = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), sigma, mode="wrap")
        out += amp * n / (n.std() + 1e-9)
        amp *= 0.55
    out = (out - out.min()) / (out.max() - out.min() + 1e-6)
    return out
