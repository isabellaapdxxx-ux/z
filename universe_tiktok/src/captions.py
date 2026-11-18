"""TikTok-style burned-in captions: 2-4 words at a time, current word yellow,
synced to the edge-tts word boundaries. Drawn on the final uint8 frame."""
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import gfx as G

CAP_X = 515          # centre (left of centre: keeps clear of TikTok's right-hand buttons)
CAP_Y = 1195         # inside the middle third (640-1280), far above the bottom 300 px
MAX_W = 780          # 125..905 px, so nothing enters the right 150 px
SIZE = 84
HILITE = (255, 222, 0)


def _norm(s):
    return re.sub(r"[^a-z0-9.']", "", s.lower().replace("’", "'"))


def _display(token):
    tok = token.replace("’", "'")
    tok = re.sub(r"^[…\.,]+", "", tok)
    tok = re.sub(r"[…\.,;:]+$", "", tok)
    return tok


class Captions:
    def __init__(self, tl):
        self.groups = []
        for line in tl["lines"]:
            toks = line["text"].split()
            ti = 0
            words = []
            for w in line["words"]:
                disp, brk = w["text"], False
                for j in range(ti, min(ti + 3, len(toks))):
                    if _norm(toks[j]) == _norm(w["text"]) or _norm(toks[j]).startswith(_norm(w["text"])):
                        disp, brk = _display(toks[j]), bool(re.search(r"[\.,\?!…]$", toks[j]))
                        ti = j + 1
                        break
                words.append({"text": disp, "t0": w["t0"], "t1": w["t1"], "brk": brk})
            group = []
            for w in words:
                if group:
                    chars = sum(len(g["text"]) + 1 for g in group) + len(w["text"])
                    if (len(group) >= 3 or chars > 15 or group[-1]["brk"]
                            or w["t0"] - group[-1]["t1"] > 0.3):
                        self.groups.append(group)
                        group = []
                group.append(w)
            if group:
                self.groups.append(group)
        # avoid one-word orphans when the previous group has room
        merged = []
        for g in self.groups:
            if (merged and len(g) == 1 and len(merged[-1]) < 3 and not merged[-1][-1]["brk"]
                    and sum(len(x["text"]) + 1 for x in merged[-1]) + len(g[0]["text"]) <= 16
                    and g[0]["t0"] - merged[-1][-1]["t1"] < 0.25):
                merged[-1] = merged[-1] + g
            else:
                merged.append(g)
        self.groups = merged
        for i, g in enumerate(self.groups):
            start = g[0]["t0"] - 0.05
            end = g[-1]["t1"] + 0.45
            if i + 1 < len(self.groups):
                end = min(end, self.groups[i + 1][0]["t0"] - 0.05)
            g_meta = {"start": start, "end": max(end, start + 0.2)}
            self.groups[i] = (g, g_meta)
        self._cache = {}

    def _render(self, gi, hi):
        key = (gi, hi)
        if key in self._cache:
            return self._cache[key]
        words = self.groups[gi][0]
        size = SIZE
        while True:
            f = G.font(size, "b")
            space = f.getlength(" ")
            widths = [f.getlength(w["text"]) for w in words]
            total = sum(widths) + space * (len(words) - 1)
            if total <= MAX_W - 20 or size < 50:
                break
            size -= 4
        stroke = max(6, size // 9)
        asc, desc = f.getmetrics()
        pad = stroke + 16
        Wd, Hd = int(total) + 2 * pad, asc + desc + 2 * pad
        shadow = Image.new("L", (Wd, Hd), 0)
        ds = ImageDraw.Draw(shadow)
        im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = pad
        for k, (w, ww) in enumerate(zip(words, widths)):
            fill = HILITE if k == hi else (255, 255, 255)
            ds.text((x, pad + 6), w["text"], font=f, fill=255, stroke_width=stroke)
            d.text((x, pad), w["text"], font=f, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += ww + space
        shadow = shadow.filter(ImageFilter.GaussianBlur(7))
        sh = np.asarray(shadow, np.float32) / 255.0 * 0.65
        arr = np.asarray(im, np.float32) / 255.0
        a = arr[..., 3]
        rgb = arr[..., :3]
        out_a = a + sh * (1 - a)
        out_rgb = rgb * (a / np.maximum(out_a, 1e-4))[..., None]
        res = (out_rgb.astype(np.float32), out_a.astype(np.float32))
        self._cache[key] = res
        return res

    def draw(self, frame_u8, gt):
        for gi, (words, m) in enumerate(self.groups):
            if m["start"] <= gt < m["end"]:
                break
        else:
            return frame_u8
        hi = 0
        for k, w in enumerate(words):
            if w["t0"] <= gt:
                hi = k
        rgb, a = self._render(gi, hi)
        dt = gt - m["start"]
        s = 0.8 + 0.2 * G.ease_out(dt / 0.12) if dt < 0.12 else 1.0
        if s != 1.0:
            h, w = a.shape
            nw, nh = max(1, int(w * s)), max(1, int(h * s))
            rgb = np.stack([np.asarray(Image.fromarray(rgb[..., c]).resize((nw, nh), Image.BILINEAR)) for c in range(3)], -1)
            a = np.asarray(Image.fromarray(a).resize((nw, nh), Image.BILINEAR))
        h, w = a.shape
        x0 = int(round(CAP_X - w / 2))
        y0 = int(round(CAP_Y - h / 2))
        reg = frame_u8[y0:y0 + h, x0:x0 + w].astype(np.float32) / 255.0
        aa = a[..., None]
        reg = reg * (1 - aa) + rgb * aa
        frame_u8[y0:y0 + h, x0:x0 + w] = (np.clip(reg, 0, 1) * 255 + 0.5).astype(np.uint8)
        return frame_u8
