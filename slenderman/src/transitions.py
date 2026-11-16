"""Scene transitions. Each one blends the outgoing frame A and the incoming
frame B (both already colour-graded) for progress p in [0, 1] across the
transition window, which is centred on the cut."""
import cv2
import numpy as np

from art import fbm
from config import H, SCENES, TRANSITIONS, W


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def active(t):
    """Return (kind, p, opts, scene_a, scene_b) when t falls inside a transition."""
    for k, (cut, kind, pre, post, opts) in enumerate(TRANSITIONS):
        if cut - pre <= t < cut + post:
            a = [n for s, e, n in SCENES if abs(e - cut) < 1e-6][0]
            b = [n for s, e, n in SCENES if abs(s - cut) < 1e-6][0]
            return kind, (t - (cut - pre)) / (pre + post), dict(opts, seed=int(cut * 100)), a, b
    return None


def _scale(img, s, cx=0.5, cy=0.5):
    px, py = cx * W, cy * H
    M = np.float32([[s, 0, px - s * px], [0, s, py - s * py]])
    return cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def _radial(img, s, amount, cx, cy, n=5):
    if amount < 0.004:
        return _scale(img, s, cx, cy)
    acc = np.zeros_like(img)
    for k in range(n):
        acc += _scale(img, s * (1 + amount * k / (n - 1)), cx, cy)
    return acc / n


def zoom(A, B, p, opts, rng):
    """Zoom-through: A rushes towards the camera with radial blur, B lands from a punch-in."""
    cx, cy = opts.get("cx", 0.5), opts.get("cy", 0.5)
    if p < 0.5:
        q = ease(p * 2) ** 1.6
        out = _radial(A, 1 + 0.9 * q, 0.18 * q, cx, cy) * (1 + 0.5 * q)
    else:
        q = 1 - ease((p - 0.5) * 2)
        out = _radial(B, 1 + 0.45 * q, 0.14 * q, cx, cy) * (1 + 0.5 * q ** 2)
    return out


def whip(A, B, p, opts, rng):
    """Whip pan: both frames slide as one strip with heavy motion blur at peak speed."""
    dx, dy = opts["dir"]
    e = ease(p)
    span = W if dx else H
    off = e * span
    M_a = np.float32([[1, 0, dx * off], [0, 1, dy * off]])
    M_b = np.float32([[1, 0, dx * (off - span)], [0, 1, dy * (off - span)]])
    a = cv2.warpAffine(A, M_a, (W, H), borderMode=cv2.BORDER_CONSTANT)
    b = cv2.warpAffine(B, M_b, (W, H), borderMode=cv2.BORDER_CONSTANT)
    out = a + b
    k = int(2 + 520 * np.sin(np.pi * p) ** 2)
    out = cv2.blur(out, (k, 1) if dx else (1, k))
    return out


_burn_mask = None


def burn(A, B, p, opts, rng):
    """Organic noise dissolve with a hot edge, like film burning through."""
    global _burn_mask
    if _burn_mask is None:
        _burn_mask = cv2.resize(fbm(H // 8, W // 8, 404, octaves=5), (W, H))
    thr = -0.15 + 1.3 * ease(p)
    d = _burn_mask - (1 - thr)
    m = np.clip(d * 6 + 0.5, 0, 1)[..., None]                     # 1 = B visible
    edge = np.exp(-(d / 0.05) ** 2)[..., None] * np.array([1.0, 0.55, 0.25], np.float32) * 0.9
    return A * (1 - m) + B * m + edge * (0.15 < p < 0.95)


def flash(A, B, p, opts, rng):
    w = np.sin(np.pi * np.clip(p, 0, 1)) ** 0.7
    base = A if p < 0.4 else B
    return base * (1 - 0.6 * w) + 1.0 * w


def dip(A, B, p, opts, rng):
    if p < 0.6:
        return A * (1 - ease(p / 0.6))
    return B * ease((p - 0.6) / 0.4)


_fog = None


def fog(A, B, p, opts, rng):
    """A bank of fog rolls across, thickens to almost white-out, and clears on B."""
    global _fog
    if _fog is None:
        _fog = cv2.resize(fbm(H // 6, W // 3, 505, octaves=5), (2 * W, H))
    o = int(p * W)
    f = _fog[:, o:o + W]
    dens = np.sin(np.pi * p) ** 1.3
    a = np.clip(dens * (0.55 + 0.6 * f), 0, 0.93)[..., None]
    base = A * (1 - ease((p - 0.35) / 0.3)) + B * ease((p - 0.35) / 0.3)
    return base * (1 - a) + np.array([0.55, 0.58, 0.62], np.float32) * a


def slice_wipe(A, B, p, opts, rng):
    """VHS slice wipe: horizontal bands jump to the new scene one by one, offset sideways."""
    r = np.random.default_rng(int(opts.get("seed", 7)))
    out = A.copy()
    y = 0
    jitter = np.sin(np.pi * p)
    while y < H:
        h = int(r.integers(14, 110))
        thr = r.random() * 0.8 + 0.1
        src = B if p > thr else A
        shift = int(r.integers(-120, 120) * jitter)
        band = np.roll(src[y:y + h], shift, axis=1)
        out[y:y + h] = band
        y += h
    return out


def vhs(A, B, p, opts, rng):
    """Tape rewind: picture rolls vertically, loses colour and tracking, then locks on B."""
    src = A if p < 0.5 else B
    q = np.sin(np.pi * p)
    roll = int((p if p < 0.5 else p - 1) * 2.2 * H)
    out = np.roll(src, roll, axis=0)
    g = out.mean(-1, keepdims=True)
    out = g + (out - g) * (1 - 0.7 * q)
    # black frame bar where the roll wraps
    bar = (roll % H)
    out[max(0, bar - 30):bar + 30] *= 0.05
    for _ in range(int(4 + 10 * q)):
        y0 = int(rng.integers(0, H - 12))
        out[y0:y0 + int(rng.integers(2, 12))] = rng.random() * 0.6 + 0.4
    return out


KINDS = dict(zoom=zoom, whip=whip, burn=burn, flash=flash, dip=dip, fog=fog, slice=slice_wipe, vhs=vhs)


def apply(kind, A, B, p, opts, fi):
    rng = np.random.default_rng(fi + 999)
    return KINDS[kind](A, B, p, opts, rng)
