"""The 13 procedural scenes. Each scene renders a 1080x1920 float RGB frame for
a time t (seconds, global). Static layers are drawn once at 1.1x size and
animated with Ken Burns moves, overlays and per-scene effects."""
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

from art import (blur, comp, draw_figure, fbm, font, forest, lerp, mask_from_draw, old_photo, over, paste,
                 text_layer)
from config import H, SCENES, W

BW, BH = 1188, 2112
B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build")


def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def kb(base, z, cx, cy, dx=0.0, dy=0.0, rot=0.0):
    """Ken Burns view: zoom z (1 = whole base), centre (cx, cy) in 0..1 of base."""
    bh, bw = base.shape[:2]
    s = z * W / bw
    hw, hh = W / (2 * s), H / (2 * s)
    px = np.clip(cx * bw, hw, bw - hw)
    py = np.clip(cy * bh, hh, bh - hh)
    M = cv2.getRotationMatrix2D((float(px), float(py)), rot, s)
    M[0, 2] += W / 2 - px + dx
    M[1, 2] += H / 2 - py + dy
    out = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out, M


def tx(M, x, y):
    return M[0, 0] * x + M[0, 1] * y + M[0, 2], M[1, 0] * x + M[1, 1] * y + M[1, 2]


class Fog:
    def __init__(self, seed, strength=0.35, color=(0.55, 0.6, 0.64), speed=(26, -14)):
        self.tex = [fbm(H // 4, W // 4 + 260, seed + k, octaves=5) ** 1.6 for k in range(2)]
        self.strength, self.color, self.speed = strength, np.asarray(color, np.float32), speed

    def apply(self, img, tl, strength=None):
        a = self.strength if strength is None else strength
        f = 0
        for tex, sp in zip(self.tex, self.speed):
            o = int(abs(sp) * tl / 4) % 250
            o = o if sp > 0 else 250 - o
            f = f + tex[:, o:o + W // 4]
        f = cv2.resize(f * 0.5, (W, H), interpolation=cv2.INTER_LINEAR)
        yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        f = f * (0.5 + 0.7 * np.exp(-((yy - 0.62) / 0.3) ** 2))
        m = (a * f)[..., None]
        return img * (1 - m) + self.color * m


def load_timeline():
    return json.load(open(f"{B}/timeline.json"))


def word_time(text, after=0.0):
    for line in load_timeline():
        for w in line["words"]:
            if w["start"] >= after and w["text"].lower().strip(".,'") == text.lower():
                return w["start"]
    raise KeyError(text)


# --------------------------------------------------------------------------- scenes
class Scene:
    fog = None
    grade = (0.93, 1.0, 1.07)

    def __init__(self, start, end):
        self.start, self.end = start, end


class Hook(Scene):
    def __init__(self, s, e):
        super().__init__(s, e)
        self.base = forest(BW, BH, 11, tint=(0.30, 0.36, 0.42),
                           fig=dict(layer=3, x=594, y=1560, h=1050, clear=0.12))
        self.fog = Fog(1, 0.32)
        self.jump = word_time("don't") - 0.04

    def frame(self, t):
        tl = t - self.start
        if t < self.jump:
            z = 1.0 + 0.12 * ease(tl / 2.3)
            img, _ = kb(self.base, z, 0.5, 0.55)
        else:
            z = 1.95 + 0.25 * ease((t - self.jump) / 1.6)
            img, _ = kb(self.base, z, 0.5, 0.33)
        img = self.fog.apply(img, tl)
        if t < 0.10:
            return img * 0
        flash = np.exp(-(t - 0.10) / 0.10) * 0.9
        flash += np.exp(-max(0, t - self.jump) / 0.06) * 0.5 * (t >= self.jump)
        return img + flash


class Forum(Scene):
    grade = (0.95, 1.0, 1.05)

    def __init__(self, s, e):
        super().__init__(s, e)
        img = np.zeros((BH, BW, 3), np.float32)
        yy = np.linspace(0, 1, BH, dtype=np.float32)[:, None, None]
        img[:] = lerp((0.015, 0.018, 0.022), (0.04, 0.045, 0.05), yy)
        # desk
        img[1500:] = np.asarray((0.05, 0.04, 0.035), np.float32) * (0.7 + 0.5 * cv2.resize(fbm(40, 150, 3), (BW, BH - 1500)))[..., None]
        # monitor casing
        cx, cy, cw, ch = 594, 960, 980, 820
        case = mask_from_draw(BW, BH, lambda d: d.rounded_rectangle([cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2], 60, fill=255))
        img = comp(img, blur(case, 1.5), (0.13, 0.13, 0.125))
        stand = mask_from_draw(BW, BH, lambda d: d.polygon([(cx - 120, cy + ch / 2), (cx + 120, cy + ch / 2), (cx + 220, 1540), (cx - 220, 1540)], fill=255))
        img = comp(img, blur(stand, 1.5), (0.09, 0.09, 0.085))
        # screen page
        sw, sh = 860, 660
        self.sx0, self.sy0 = cx - sw // 2, cy - sh // 2 - 30
        page = np.ones((sh, sw, 3), np.float32) * np.array([0.78, 0.80, 0.84], np.float32)
        page[:70] = (0.10, 0.16, 0.30)
        page[70:150] = (0.88, 0.89, 0.92)
        thumb = cv2.resize(Photo.make_photo(fig=True, small=True), (220, 166))
        items = [(24, 35, "FORUMS  ›  PHOTOSHOP  ›  CONTESTS", 26, "Bold", (235, 238, 245, 255), "lm"),
                 (24, 110, "Create Paranormal Images", 40, "Black", (20, 25, 40, 255), "lm"),
                 (sw - 24, 110, "June 2009", 26, "SemiBold", (90, 95, 110, 255), "rm")]
        y = 175
        rng = np.random.default_rng(4)
        for k in range(3):
            page[y:y + 140, 16:sw - 16] = (0.90, 0.91, 0.93)
            page[y:y + 140, 16:170] = (0.80, 0.82, 0.87)
            items.append((28, y + 24, f"user_{rng.integers(100, 999)}", 22, "Bold", (30, 40, 80, 255), "lm"))
            items.append((28, y + 52, "Posted: 06-2009", 18, "Medium", (80, 85, 100, 255), "lm"))
            if k == 1:
                page[y + 8:y + 8 + 124, 190:190 + 164] = cv2.resize(thumb, (164, 124))
                xs = 370
            else:
                xs = 190
            for j in range(4):
                L = rng.uniform(0.4, 1.0) * (sw - 40 - xs)
                page[y + 22 + j * 28:y + 34 + j * 28, xs:int(xs + L)] = (0.55, 0.57, 0.62)
            y += 160
        rgb, a = text_layer(sw, sh, items)
        page = page * (1 - a[..., None]) + rgb * a[..., None]
        page[::3] *= 0.82  # scanlines
        yy2, xx2 = np.mgrid[0:sh, 0:sw].astype(np.float32)
        vig = 1 - 0.35 * (((xx2 / sw - 0.5) * 2) ** 4 + ((yy2 / sh - 0.5) * 2) ** 4)
        page *= vig[..., None] * np.array([0.85, 0.92, 1.0], np.float32)
        scr = mask_from_draw(BW, BH, lambda d: d.rounded_rectangle([self.sx0, self.sy0, self.sx0 + sw, self.sy0 + sh], 26, fill=255))
        full = np.zeros_like(img)
        full[self.sy0:self.sy0 + sh, self.sx0:self.sx0 + sw] = page
        img = img * (1 - scr[..., None]) + full * scr[..., None]
        glow = blur(full * scr[..., None], 90) * 0.9
        self.base = np.clip(img + glow * (1 - case[..., None] * 0.7), 0, 1)
        self.thumb_xy = (self.sx0 + 190 + 82, self.sy0 + 175 + 160 + 70)

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        z = 1.0 + 0.30 * ease(tl / T)
        img, M = kb(self.base, z, 0.5, 0.45 - 0.02 * ease(tl / T))
        img *= 0.96 + 0.04 * np.sin(tl * 47)
        # mouse cursor gliding to the attached photo
        p = ease((tl - 0.6) / 3.2)
        x0, y0 = self.sx0 + 700, self.sy0 + 600
        x1, y1 = self.thumb_xy
        cxp, cyp = tx(M, x0 + (x1 - x0) * p, y0 + (y1 - y0) * p)
        s = M[0, 0] * 1.4
        pts = np.array([[0, 0], [0, 34], [9, 26], [16, 41], [22, 38], [15, 24], [27, 24]], np.float32) * s + (cxp, cyp)
        cv2.fillPoly(img, [pts.astype(np.int32)], (0.95, 0.95, 0.95), cv2.LINE_AA)
        cv2.polylines(img, [pts.astype(np.int32)], True, (0, 0, 0), 2, cv2.LINE_AA)
        return img


class Photo(Scene):
    grade = (1.0, 1.0, 1.0)

    @staticmethod
    def make_photo(fig=True, small=False, seed=21):
        w, h = (480, 360) if small else (980, 740)
        k = w / 980
        kids = dict(layer=3, color=(0.13, 0.13, 0.13), list=[(220 * k, 690 * k, 190 * k, 0.6), (360 * k, 700 * k, 170 * k, -0.4),
                                                             (610 * k, 705 * k, 200 * k, 0.2), (800 * k, 690 * k, 160 * k, 0.9)])
        f = dict(layer=1, x=700 * k, y=560 * k, h=520 * k, clear=0.14, pale=1.05) if fig else None
        img = forest(w, h, seed, horizon=0.66, tint=(0.80, 0.80, 0.78), layers=4, density=0.55, fig=f, kids=kids,
                     ground_dark=0.42, fog_amt=1.2)
        return old_photo(img, seed, sepia=0.4, border=0.045)

    def __init__(self, s, e):
        super().__init__(s, e)
        table = np.zeros((BH, BW, 3), np.float32)
        grain = cv2.resize(fbm(30, 400, 5, octaves=6), (BW, BH))
        table[:] = (np.array([0.07, 0.05, 0.04], np.float32) * (0.6 + 0.8 * grain[..., None]))
        self.bases = []
        for fig in (False, True):
            ph = self.make_photo(fig)
            self.bases.append(np.clip(paste(table, ph, 594, 1000, angle=-3.0), 0, 1))
        self.reveal = word_time("one", 10) - 0.05
        # where the figure sits on the table (photo centre 594,1000; content offset)
        self.fig_c = (594 + (700 - 490) * 1.0, 1000 + (330 - 370))

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        base = self.bases[1] if t >= self.reveal else self.bases[0]
        p = ease(tl / T)
        cx = lerp(0.5, self.fig_c[0] / BW, p * 0.8)
        cy = lerp(0.47, self.fig_c[1] / BH, p * 0.8)
        img, _ = kb(base, 1.05 + 0.55 * p, float(cx), float(cy), rot=-1.0 * p)
        return img


class Layer(Scene):
    grade = (0.97, 1.0, 1.03)

    def __init__(self, s, e):
        super().__init__(s, e)
        ui = np.zeros((BH, BW, 3), np.float32) + np.array([0.13, 0.13, 0.14], np.float32)
        ph = [Photo.make_photo(f) for f in (False, True)]
        # canvas: crop around the figure, scaled up
        ch, cw = ph[0].shape[:2]
        x0, y0 = 480, 60
        crop = [p[y0:y0 + 520, x0:x0 + 470] for p in ph]
        cv_w, cv_h = 1040, int(1040 * 520 / 470)
        self.cv = (74, 560, cv_w, cv_h)
        self.bases = []
        items = [(150, 300, "Layers", 34, "Bold", (220, 220, 225, 255), "lm"),
                 (190, 382, "Layer 1  (figure)", 30, "Medium", (230, 230, 235, 255), "lm"),
                 (190, 462, "Background", 30, "Medium", (200, 200, 205, 255), "lm")]
        rgb, a = text_layer(BW, BH, items)
        for c in crop:
            u = ui.copy()
            u[260:500, 100:1090] = (0.18, 0.18, 0.19)
            u[345:420, 100:1090] = (0.24, 0.30, 0.42)
            u[560 - 6:560 + cv_h + 6, 74 - 6:74 + cv_w + 6] = 0.06
            u[560:560 + cv_h, 74:74 + cv_w] = cv2.resize(c, (cv_w, cv_h), interpolation=cv2.INTER_CUBIC)
            u = u * (1 - a[..., None]) + rgb * a[..., None]
            for k in range(6):  # tool icons
                u[600 + k * 90:660 + k * 90, 14:60] = (0.22, 0.22, 0.24)
            self.bases.append(u)
        # figure box in canvas coords (photo figure at x≈700+44, y≈560+33 - h)
        sx = cv_w / 470
        fx, fy, fh = 700 + 44 - x0, 593 - y0, 520
        self.box = (74 + (fx - 0.13 * fh) * sx, 560 + (fy - fh - 10) * sx, 74 + (fx + 0.13 * fh) * sx, 560 + (fy + 10) * sx)
        self.blink = word_time("invented", 17) + 0.05

    def visible(self, t):
        if self.blink <= t < self.blink + 1.2:
            return int((t - self.blink) / 0.2) % 2 == 1
        return True

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        vis = self.visible(t)
        base = self.bases[1 if vis else 0]
        z = 1.0 + 0.18 * ease(tl / T)
        img, M = kb(base, z, 0.5, 0.5)
        # eye icon
        ex, ey = tx(M, 140, 382)
        r = int(16 * M[0, 0])
        cv2.ellipse(img, (int(ex), int(ey)), (r, int(r * 0.6)), 0, 0, 360, (0.9, 0.9, 0.9), 2, cv2.LINE_AA)
        if vis:
            cv2.circle(img, (int(ex), int(ey)), int(r * 0.35), (0.9, 0.9, 0.9), -1, cv2.LINE_AA)
        ex2, ey2 = tx(M, 140, 462)
        cv2.ellipse(img, (int(ex2), int(ey2)), (r, int(r * 0.6)), 0, 0, 360, (0.8, 0.8, 0.8), 2, cv2.LINE_AA)
        cv2.circle(img, (int(ex2), int(ey2)), int(r * 0.35), (0.8, 0.8, 0.8), -1, cv2.LINE_AA)
        # marching ants around the figure
        x0, y0 = tx(M, self.box[0], self.box[1])
        x1, y1 = tx(M, self.box[2], self.box[3])
        off = int(tl * 40) % 24
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
            L = int(np.hypot(bx - ax, by - ay))
            for d in range(-off, L, 24):
                s0, s1 = max(0, d), min(L, d + 12)
                if s1 <= s0:
                    continue
                p0 = (int(ax + (bx - ax) * s0 / L), int(ay + (by - ay) * s0 / L))
                p1 = (int(ax + (bx - ax) * s1 / L), int(ay + (by - ay) * s1 / L))
                cv2.line(img, p0, p1, (1, 1, 1), 3)
        return img


class Spread(Scene):
    grade = (0.95, 1.0, 1.05)

    def __init__(self, s, e):
        super().__init__(s, e)
        rng = np.random.default_rng(31)
        T = e - s
        nodes = [(W / 2, H * 0.46, 0.0, -1)]
        for i in range(220):
            par = int(rng.integers(0, len(nodes)))
            px, py, pt, _ = nodes[par]
            ang = rng.uniform(0, 2 * np.pi)
            r = rng.uniform(70, 170)
            x, y = px + np.cos(ang) * r, py + np.sin(ang) * r * 1.2
            if not (-50 < x < W + 50 and 120 < y < H - 120):
                continue
            nodes.append((x, y, pt + rng.uniform(0.12, 0.5) * (T / 4.4), par))
        self.nodes = nodes
        bg = fbm(H // 8, W // 8, 32) * 0.05
        self.bg = np.repeat(cv2.resize(bg, (W, H))[..., None], 3, 2) * np.array([0.6, 0.8, 1.0], np.float32)
        icon = np.zeros((300, 200, 3), np.float32)
        self.icon = draw_figure(icon, 100, 290, 280, (0.05, 0.05, 0.06), (0.9, 0.9, 0.88), 0.8)
        self.years = {}
        for y in range(2009, 2014):
            self.years[y] = text_layer(600, 160, [(300, 80, str(y), 120, "Black", (230, 235, 245, 230), "mm")])

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        img = self.bg.copy()
        lines = np.zeros((H // 2, W // 2, 3), np.float32)
        z = 1.25 - 0.25 * ease(tl / T)
        cxp, cyp = W / 2, H * 0.46
        P = lambda x, y: (int((cxp + (x - cxp) * z) / 2), int((cyp + (y - cyp) * z) / 2))
        for x, y, ts, par in self.nodes:
            if ts > tl or par < 0:
                continue
            px, py, _, _ = self.nodes[par]
            g = min(1, (tl - ts) / 0.25)
            ex, ey = px + (x - px) * g, py + (y - py) * g
            cv2.line(lines, P(px, py), P(ex, ey), (0.35, 0.45, 0.6), 1, cv2.LINE_AA)
            if g >= 1:
                cv2.circle(lines, P(x, y), 3, (0.8, 0.9, 1.0), -1, cv2.LINE_AA)
        lines = cv2.resize(lines, (W, H))
        img = img + lines + blur(lines, 9) * 1.6
        # the figure at the centre of the web
        ih, iw = self.icon.shape[:2]
        x0, y0 = int(cxp - iw / 2), int(cyp - ih * 0.75)
        a = (self.icon.sum(-1) > 0.02).astype(np.float32)
        a = blur(a, 1)
        over(img, self.icon, a, x0, y0)
        yr = 2009 + min(4, int(tl / T * 5))
        rgb, al = self.years[yr]
        over(img, rgb, al, W // 2 - 300, 230)
        return img


class Faceless(Scene):
    grade = (0.92, 0.98, 1.06)

    def __init__(self, s, e):
        super().__init__(s, e)
        bg = forest(BW, BH, 51, tint=(0.26, 0.31, 0.36), layers=5)
        bg = blur(bg, 7) * 0.8
        self.base = draw_figure(bg, 594, 305 + 7000, 7000, (0.018, 0.018, 0.022), (0.80, 0.80, 0.77), 1.5)
        self.fog = Fog(52, 0.22)
        self.p1 = word_time("eyes", 25) - 0.37
        self.p2 = word_time("mouth", 27) - 0.29

    def frame(self, t):
        tl = t - self.start
        z = 1.0 + 0.08 * ease(tl / 5)
        if t >= self.p1:
            z *= 1.14
        if t >= self.p2:
            z *= 1.14
        sway = 6 * np.sin(tl * 0.9)
        img, _ = kb(self.base, z, 0.5, 0.36, dx=sway, rot=0.4 * np.sin(tl * 0.6))
        return self.fog.apply(img, tl)


class Polaroids(Scene):
    def __init__(self, s, e):
        super().__init__(s, e)
        grain = cv2.resize(fbm(30, 400, 61, octaves=6), (BW, BH))
        table = np.array([0.06, 0.045, 0.04], np.float32) * (0.6 + 0.8 * grain[..., None])
        specs = [((0.55, 0.60, 0.50), dict(layer=0, x=380, y=330, h=150, clear=0.2), 62),
                 ((0.58, 0.50, 0.45), dict(layer=1, x=180, y=380, h=270, clear=0.18), 63),
                 ((0.34, 0.37, 0.44), dict(layer=2, x=300, y=470, h=420, clear=0.15), 64)]
        self.photos = []
        for tint, fig, seed in specs:
            img = forest(560, 560, seed, horizon=0.62, tint=tint, layers=4, density=0.5, fig=fig, ground_dark=0.2)
            g = img.mean(-1, keepdims=True)
            img = np.clip((g + (img - g) * 0.55) * np.array([1.08, 1.0, 0.86], np.float32) * 1.1 + 0.04, 0, 1)
            self.photos.append(old_photo(img, seed, sepia=0.0, border=0.06, bottom=0.26) if False else self._polaroid(img, seed))
        self.places = [(420, 760, -8.0), (790, 1020, 6.0), (590, 1290, -2.0)]
        tl_times = [-1.0, 1.75, 3.45]   # first photo is already on the table when the whip lands
        self.times = [s + x for x in tl_times]
        self.table = table
        self.cache = {}

    @staticmethod
    def _polaroid(img, seed):
        rng = np.random.default_rng(seed)
        h, w = img.shape[:2]
        img = img + rng.normal(0, 0.03, img.shape).astype(np.float32)
        b, bb = 34, 130
        out = np.ones((h + b + bb, w + 2 * b, 3), np.float32) * np.array([0.88, 0.87, 0.83], np.float32)
        out[b:b + h, b:b + w] = np.clip(img, 0, 1)
        return out

    def state(self, n):
        if n not in self.cache:
            img = self.table.copy()
            for k in range(n):
                x, y, a = self.places[k]
                img = paste(img, self.photos[k], x, y, a)
            self.cache[n] = img
        return self.cache[n]

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        n_done = sum(t >= ts + 0.2 for ts in self.times)
        img = self.state(n_done)
        for k, ts in enumerate(self.times):
            if ts <= t < ts + 0.2:
                p = ease((t - ts) / 0.2)
                x, y, a = self.places[k]
                ph = self.photos[k]
                sc = 1.35 - 0.35 * p
                ph2 = cv2.resize(ph, None, fx=sc, fy=sc)
                img = paste(img, ph2, x, y, a + 10 * (1 - p), alpha=p)
        z = 1.0 + 0.22 * ease(tl / T)
        out, _ = kb(img, z, 0.5, lerp(0.45, 0.6, ease(tl / T)).item())
        return out


class Camcorder(Scene):
    grade = (0.9, 1.04, 0.92)

    def __init__(self, s, e):
        super().__init__(s, e)
        self.base = forest(BW, BH, 81, tint=(0.30, 0.35, 0.31), layers=6,
                           fig=dict(layer=2, x=760, y=1420, h=700, clear=0.14))
        self.fog = Fog(82, 0.25, color=(0.45, 0.52, 0.46))
        self.zoom_t = word_time("feel", 37) - 0.05
        self.hud = {}
        for k, blink in enumerate((True, False)):
            items = [(W - 90, 270, "JUN. 21 2009", 40, "Bold", (235, 235, 235, 255), "rm"),
                     (90, 1740 - 1500, "", 10, "Bold", (0, 0, 0, 0), "lm")]
            if blink:
                items.append((140, 270, "REC", 44, "Bold", (235, 235, 235, 255), "lm"))
            self.hud[blink] = text_layer(W, 360, items)

    def frame(self, t):
        tl = t - self.start
        rng = np.random.default_rng(int(t * 30))
        dx = 14 * np.sin(tl * 1.7) + 7 * np.sin(tl * 4.3 + 1) + rng.normal(0, 1.5)
        dy = 10 * np.sin(tl * 1.3 + 2) + 5 * np.sin(tl * 5.1) + rng.normal(0, 1.5)
        rot = 0.6 * np.sin(tl * 0.8)
        if t < self.zoom_t:
            z, cx, cy = 1.05 + 0.1 * tl / 5, 0.55, 0.5
        else:
            p = ease((t - self.zoom_t) / 0.45)
            z, cx, cy = 1.15 + 1.35 * p, 0.55 + 0.09 * p, 0.5 - 0.15 * p
        img, _ = kb(self.base, z, cx, cy, dx, dy, rot)
        img = self.fog.apply(img, tl)
        g = img.mean(-1, keepdims=True)
        img = g + (img - g) * 0.4
        img[::2] *= 0.9
        # rolling tracking band
        y = int((tl * 260) % (H + 200)) - 100
        y0, y1 = max(0, y), min(H, y + 40)
        if y1 > y0:
            img[y0:y1] = np.roll(img[y0:y1], 18, axis=1) * 0.7 + rng.random((y1 - y0, W, 1)).astype(np.float32) * 0.3
        # bottom head-switching noise
        img[H - 26:] = np.roll(img[H - 26:], 30, axis=1) * 0.6 + rng.random((26, W, 1)).astype(np.float32) * 0.25
        blink = int(tl * 1.6) % 2 == 0
        rgb, a = self.hud[blink]
        over(img, rgb, a, 0, 0)
        if blink:
            cv2.circle(img, (110, 270), 15, (0.9, 0.1, 0.1), -1, cv2.LINE_AA)
        secs = int(tl) + 7
        rgb2, a2 = text_layer(380, 80, [(370, 40, f"AM 3:12:{secs:02d}", 40, "Bold", (235, 235, 235, 255), "rm")])
        over(img, rgb2, a2, W - 90 - 370, 300)
        # battery + viewfinder corners
        cv2.rectangle(img, (W - 210, 365), (W - 120, 405), (0.9, 0.9, 0.9), 3)
        cv2.rectangle(img, (W - 120, 375), (W - 110, 395), (0.9, 0.9, 0.9), -1)
        cv2.rectangle(img, (W - 202, 373), (W - 175, 397), (0.9, 0.9, 0.9), -1)
        for (x, y_, sx, sy) in [(60, 200, 1, 1), (W - 60, 200, -1, 1), (60, 1560, 1, -1), (W - 60, 1560, -1, -1)]:
            cv2.line(img, (x, y_), (x + 80 * sx, y_), (0.85, 0.85, 0.85), 4)
            cv2.line(img, (x, y_), (x, y_ + 80 * sy), (0.85, 0.85, 0.85), 4)
        # chroma bleed
        img[..., 0] = np.roll(img[..., 0], 4, axis=1)
        img[..., 2] = np.roll(img[..., 2], -4, axis=1)
        return img


class Sightings(Scene):
    def __init__(self, s, e):
        super().__init__(s, e)
        rng = np.random.default_rng(91)
        thumbs = []
        for k in range(8):
            tint = [(0.35, 0.4, 0.45), (0.5, 0.52, 0.48), (0.3, 0.3, 0.36), (0.55, 0.5, 0.46)][k % 4]
            fh = rng.uniform(140, 300)
            img = forest(480, 400, 100 + k, horizon=0.62, tint=tint, layers=4, density=0.6,
                         fig=dict(layer=int(rng.integers(0, 3)), x=rng.uniform(120, 360), y=250 + fh * 0.5, h=fh, clear=0.18))
            g = img.mean(-1, keepdims=True)
            thumbs.append(np.clip(g + (img - g) * 0.5, 0, 1))
        posts = ["found this on my old camera", "anyone else see him??", "taken behind the school",
                 "he wasn't there when I took it", "my cousin swears this is real", "look at the tree line",
                 "why is he always watching", "I can't unsee it"]
        CH = 640
        self.tall = np.zeros((CH * 5 + 200, BW, 3), np.float32) + np.array([0.035, 0.035, 0.04], np.float32)
        items = []
        for k in range(10):
            col, row = k % 2, k // 2
            x0, y0 = 50 + col * 560, 100 + row * CH
            m = mask_from_draw(BW, self.tall.shape[0], lambda d: d.rounded_rectangle([x0, y0, x0 + 528, y0 + CH - 40], 24, fill=255))
            self.tall = comp(self.tall, m, (0.10, 0.10, 0.11))
            th = cv2.resize(thumbs[k % 8], (488, 400))
            self.tall[y0 + 90:y0 + 490, x0 + 20:x0 + 508] = th
            cv2.circle(self.tall, (x0 + 50, y0 + 46), 24, (0.3, 0.3, 0.33), -1, cv2.LINE_AA)
            self.tall[y0 + 34:y0 + 58, x0 + 90:x0 + 90 + int(rng.uniform(140, 260))] = (0.3, 0.3, 0.33)
            items.append((x0 + 24, y0 + 535, posts[k % 8], 28, "SemiBold", (215, 215, 220, 255), "lm"))
            self.tall[y0 + 565:y0 + 581, x0 + 24:x0 + 24 + int(rng.uniform(200, 420))] = (0.25, 0.25, 0.28)
        rgb, a = text_layer(BW, self.tall.shape[0], items)
        self.tall = self.tall * (1 - a[..., None]) + rgb * a[..., None]

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        span = self.tall.shape[0] - BH
        y = int(span * ease(tl / T) * 0.95)
        base = self.tall[y:y + BH]
        img, _ = kb(base, 1.0, 0.5, 0.5)
        return img


class Twist(Scene):
    grade = (1.25, 0.62, 0.58)

    def __init__(self, s, e):
        super().__init__(s, e)
        self.with_fig = forest(BW, BH, 11, tint=(0.30, 0.36, 0.42), fig=dict(layer=3, x=594, y=1560, h=1050, clear=0.12))
        self.empty = forest(BW, BH, 11, tint=(0.30, 0.36, 0.42), fig=dict(layer=3, x=594, y=1560, h=1050, clear=0.12, alpha=0.0))
        self.fog = Fog(12, 0.3, color=(0.5, 0.45, 0.45))
        self.hit = 44.08

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        base = self.with_fig if t < self.hit else self.empty
        img, _ = kb(base, 1.18 - 0.16 * ease(tl / T), 0.5, 0.55)
        img = self.fog.apply(img, tl)
        g = img.mean(-1, keepdims=True)
        img = g + (img - g) * 0.3
        if t >= self.hit:
            img = img + np.exp(-(t - self.hit) / 0.12) * 0.9
        return img


class Screens(Scene):
    def __init__(self, s, e):
        super().__init__(s, e)
        rng = np.random.default_rng(111)
        thumbs = []
        for k in range(6):
            tint = [(0.35, 0.4, 0.5), (0.45, 0.45, 0.42), (0.28, 0.3, 0.38)][k % 3]
            img = forest(360, 280, 120 + k, horizon=0.62, tint=tint, layers=4, density=0.6,
                         fig=dict(layer=2, x=rng.uniform(120, 240), y=230, h=200, clear=0.2))
            thumbs.append(img)
        base = np.zeros((BH, BW, 3), np.float32) + 0.01
        self.rects = []
        cols, rows = 4, 9
        cw, ch = BW / cols, BH / rows
        for r in range(rows):
            for c in range(cols):
                w = cw * rng.uniform(0.78, 0.9)
                h = ch * rng.uniform(0.72, 0.86)
                x0 = int(c * cw + (cw - w) / 2 + rng.uniform(-6, 6))
                y0 = int(r * ch + (ch - h) / 2 + rng.uniform(-6, 6))
                x1, y1 = int(x0 + w), int(y0 + h)
                base[y0 - 10:y1 + 10, x0 - 10:x1 + 10] = 0.06
                th = cv2.resize(thumbs[int(rng.integers(0, 6))], (x1 - x0, y1 - y0))
                th = th * np.array(rng.uniform(0.75, 1.15, 3), np.float32)
                th[::3] *= 0.8
                base[y0:y1, x0:x1] = th
                self.rects.append((x0, y0, x1, y1))
        glow = blur(base, 30) * 0.5
        self.base = np.clip(base + glow, 0, 1)

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        rng = np.random.default_rng(int(t * 30) + 5)
        base = self.base.copy()
        for k in rng.choice(len(self.rects), 4, replace=False):
            x0, y0, x1, y1 = self.rects[k]
            base[y0:y1, x0:x1] *= rng.uniform(0.2, 0.7)
        z = 2.4 - 1.4 * ease(tl / T)
        img, _ = kb(base, z, 0.5, 0.5)
        return img


class Viewer(Scene):
    grade = (0.9, 0.98, 1.1)

    def __init__(self, s, e):
        super().__init__(s, e)
        room = np.zeros((BH, BW, 3), np.float32) + np.array([0.012, 0.014, 0.02], np.float32)
        sx0, sy0, sw, sh = 254, 640, 680, 480
        self.scr = (sx0, sy0, sw, sh)
        scr_img = forest(sw, sh, 141, horizon=0.62, tint=(0.38, 0.44, 0.52), layers=5,
                         fig=dict(layer=3, x=sw * 0.55, y=sh * 0.82, h=sh * 0.75, clear=0.15))
        scr_img[::3] *= 0.85
        bez = mask_from_draw(BW, BH, lambda d: d.rounded_rectangle([sx0 - 30, sy0 - 30, sx0 + sw + 30, sy0 + sh + 30], 20, fill=255))
        room = comp(room, bez, (0.03, 0.03, 0.035))
        on = room.copy()
        on[sy0:sy0 + sh, sx0:sx0 + sw] = scr_img
        glow_src = np.zeros_like(room)
        glow_src[sy0:sy0 + sh, sx0:sx0 + sw] = scr_img
        glow = blur(glow_src, 120) * 2.2 + blur(glow_src, 30) * 0.6
        # desk
        desk = mask_from_draw(BW, BH, lambda d: d.rectangle([0, 1250, BW, BH], fill=255))
        # person from behind: head + hoodie shoulders (generic silhouette)
        def person(d):
            d.ellipse([440, 1060, 700, 1360], fill=255)
            d.polygon([(250, BH), (300, 1520), (420, 1380), (560, 1340), (720, 1380), (860, 1520), (930, BH)], fill=255)
            d.rectangle([520, 1300, 620, 1420], fill=255)
        pm = blur(mask_from_draw(BW, BH, person), 2)
        rim = np.clip(pm - cv2.erode(pm, np.ones((9, 9), np.uint8)), 0, 1)
        rim = blur(rim, 3) * (np.clip(1.4 - (np.mgrid[0:BH, 0:BW][0] - 1000) / 600, 0, 1))
        self.bases = []
        for k, (img, g) in enumerate([(on, glow), (room.copy(), glow * 0.07)]):
            b = img + g * (1 - bez[..., None] * 0.8)
            b = comp(b, desk * (1 - pm), (b[1250:1260].mean((0, 1)) * 0.5 + 0.01))
            b = comp(b, pm, (0.004, 0.004, 0.006))
            if k == 0:
                b = b + rim[..., None] * np.array([0.35, 0.42, 0.55], np.float32)
            self.bases.append(np.clip(b, 0, 1))
        self.off = word_time("he", 54.5) - 0.05

    def frame(self, t):
        tl = t - self.start
        T = self.end - self.start
        z = 1.0 + 0.3 * ease(tl / T)
        if t < self.off:
            img, M = kb(self.bases[0], z, 0.5, 0.48)
            return img
        img, M = kb(self.bases[1], z, 0.5, 0.48)
        p = (t - self.off) / 0.14  # CRT switch-off: collapse to a line, then a dot
        if p < 1:
            sx0, sy0, sw, sh = self.scr
            x0, y0 = tx(M, sx0, sy0 + sh / 2)
            x1, _ = tx(M, sx0 + sw, sy0)
            hh = max(2, int((1 - p) * 30))
            cv2.rectangle(img, (int(x0), int(y0 - hh)), (int(x1), int(y0 + hh)), (0.9, 0.95, 1.0), -1)
        return img


class Final(Scene):
    grade = (0.9, 0.97, 1.08)

    def __init__(self, s, e):
        super().__init__(s, e)
        self.base = forest(BW, BH, 131, tint=(0.24, 0.28, 0.33), layers=6,
                           fig=dict(layer=4, x=594, y=2900, h=2500, clear=0.12, arms_out=0.01))
        self.fog = Fog(132, 0.35, color=(0.42, 0.47, 0.52))
        self.worse = word_time("worse", 57) - 0.03

    def frame(self, t):
        tl = t - self.start
        z = 1.0 + 0.28 * ease(tl / 1.2) ** 1.2
        if t >= self.worse:
            z = 1.65 + 0.15 * ease((t - self.worse) / 1.6)
        img, _ = kb(self.base, z, 0.5, 0.2)
        return self.fog.apply(img, tl)


class Black(Scene):
    def frame(self, t):
        return np.zeros((H, W, 3), np.float32)


CLASSES = dict(hook=Hook, forum=Forum, photo=Photo, layer=Layer, spread=Spread, faceless=Faceless,
               polaroids=Polaroids, camcorder=Camcorder, sightings=Sightings, twist=Twist, screens=Screens,
               viewer=Viewer, final=Final, black=Black)
_cache = {}


def get_scene(name):
    if name not in _cache:
        s, e = [(s, e) for s, e, n in SCENES if n == name][0]
        _cache[name] = CLASSES[name](s, e)
    return _cache[name]


def scene_at(t):
    for s, e, name in SCENES:
        if s <= t < e or (name == "black" and t >= s):
            if name not in _cache:
                _cache[name] = CLASSES[name](s, e)
            return name, _cache[name]
    raise ValueError(t)
