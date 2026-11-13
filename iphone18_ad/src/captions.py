"""Burned-in captions (white, bold, centred near the bottom, soft dark shadow) and the SRT export."""
import numpy as np

from common import H, W, blur, font, text_layer

FADE = 0.3
CAPTION_Y = 968          # vertical centre of the caption line
CAPTION_FONT = ("Inter-Bold.otf", 54)

CAPTIONS = [
    (0.0, 3.0, "Something big is coming."),
    (3.0, 7.0, "iPhone 18 Pro Max"),
    (7.0, 11.0, "A camera that sees everything."),
    (11.0, 15.0, "The biggest, brightest display yet."),
    (15.0, 16.0, "Faster."),
    (16.0, 17.0, "Longer."),
    (17.0, 18.0, "Tougher."),
    (18.0, 19.0, "Brighter."),
    (19.0, 24.0, "Pro. Beyond Max."),
]

_cache = {}


def _layers(text):
    if text not in _cache:
        a = text_layer(text, font(*CAPTION_FONT), pad=70)
        tight = blur(np.roll(a, 3, axis=0), 4.0)      # close shadow, nudged down 3 px
        soft = blur(a, 16.0)                          # wide soft halo
        _cache[text] = (a, np.clip(tight * 0.85 + soft * 0.55, 0, 1))
    return _cache[text]


def opacity(t, start, end):
    return max(0.0, min(1.0, (t - start) / FADE, (end - t) / FADE))


def draw(disp, t):
    """Composite the active caption onto a display-space float frame in place."""
    for start, end, text in CAPTIONS:
        if start <= t < end:
            op = opacity(t, start, end)
            if op <= 0:
                continue
            a, sh = _layers(text)
            h, w = a.shape
            x0, y0 = W // 2 - w // 2, CAPTION_Y - h // 2
            region = disp[y0:y0 + h, x0:x0 + w]
            region *= (1 - sh * op * 0.82)[..., None]
            region *= (1 - a * op)[..., None]
            region += (a * op)[..., None] * 1.0
    return disp


def _ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path):
    lines = []
    for i, (start, end, text) in enumerate(CAPTIONS, 1):
        lines += [str(i), f"{_ts(start)} --> {_ts(end)}", text, ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
