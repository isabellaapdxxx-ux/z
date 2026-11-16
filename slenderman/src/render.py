"""Render frames (scenes + film grain, vignette, flicker, VHS glitches, captions),
encode H.264 in parallel segments and mux with the mixed audio.

  python src/render.py preview 1.0 5.0 ...   # PNG stills + contact sheet
  python src/render.py video [--workers 4]
  python src/render.py mux
"""
import json
import os
import re
import subprocess
import sys
from multiprocessing import Pool

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from art import font
from config import BLACK, DUR, FPS, GLITCH_CUTS, H, MINI_GLITCHES, W
import scenes
import transitions

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
B = os.path.join(ROOT, "build")
NF = int(round(DUR * FPS))

# ------------------------------------------------------------------ captions
CAP_CX, CAP_CY, CAP_MAXW = 520, 1235, 800   # lower-middle third, clear of TikTok's right rail and bottom UI
RED = (255, 38, 38)


def build_chunks():
    tl = json.load(open(f"{B}/timeline.json"))
    chunks = []
    for line in tl:
        toks = line["text"].split()
        words = line["words"]
        # align TTS boundary words to script tokens (keeps punctuation for phrasing)
        ti = 0
        aligned = []
        for w in words:
            target = re.sub(r"[^a-z0-9']", "", w["text"].lower())
            got, parts = "", []
            while ti < len(toks) and len(got) < len(target):
                parts.append(toks[ti])
                got += re.sub(r"[^a-z0-9']", "", toks[ti].lower())
                ti += 1
            aligned.append(dict(w, disp=" ".join(parts) if parts else w["text"]))
        # split into clauses at punctuation / pauses, then into balanced 2-3 word groups
        clauses, cur = [], []
        for k, w in enumerate(aligned):
            cur.append(w)
            nxt = aligned[k + 1] if k + 1 < len(aligned) else None
            if nxt is None or w["disp"][-1] in ",.:;?!" or nxt["start"] - w["end"] > 0.35:
                clauses.append(cur)
                cur = []
        for cl in clauses:
            n = len(cl)
            chars = len(" ".join(w["disp"] for w in cl))
            if n <= 3 or (n == 4 and chars <= 15):
                sizes = [n]
            else:
                k = -(-n // 3)                      # fewest groups of <= 3 words
                sizes = [n // k + (1 if i < n % k else 0) for i in range(k)]
            i = 0
            for sz in sizes:
                chunks.append(cl[i:i + sz])
                i += sz
    out = []
    for i, g in enumerate(chunks):
        start = g[0]["start"] - 0.04
        end = g[-1]["end"] + 0.25
        if i + 1 < len(chunks):
            end = min(max(end, g[-1]["end"] + 0.05), chunks[i + 1][0]["start"] - 0.04)
            if chunks[i + 1][0]["start"] - g[-1]["end"] < 0.3:
                end = chunks[i + 1][0]["start"] - 0.04
        end = min(end, BLACK - 0.05)
        words = [(re.sub(r"[.,:;]$", "", w["disp"]).upper(), w["hl"]) for w in g]
        out.append(dict(start=start, end=end, words=words))
    return out


def render_caption(words, size=100):
    while True:
        f = font(size, "Black")
        space = size * 0.28
        widths = [f.getlength(w) for w, _ in words]
        total = sum(widths) + space * (len(words) - 1)
        if total <= CAP_MAXW or size <= 60:
            break
        size -= 4
    stroke = max(6, int(size * 0.11))
    pad = stroke + 30
    im = Image.new("RGBA", (int(total + 2 * pad), int(size * 1.35 + 2 * pad)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = pad
    y = pad + size * 0.62
    shadow = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ds = ImageDraw.Draw(shadow)
    for (w, hl), wd in zip(words, widths):
        ds.text((x + 4, y + 7), w, font=f, fill=(0, 0, 0, 170), anchor="lm", stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
        d.text((x, y), w, font=f, fill=RED + (255,) if hl else (255, 255, 255, 255), anchor="lm",
               stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        x += wd + space
    sh = np.asarray(shadow, np.float32) / 255
    sh = cv2.GaussianBlur(sh, (0, 0), 6)
    a = np.asarray(im, np.float32) / 255
    alpha = a[..., 3:] + sh[..., 3:] * (1 - a[..., 3:])
    rgb = (a[..., :3] * a[..., 3:]) / np.maximum(alpha, 1e-4)
    return np.concatenate([rgb, alpha], -1)


class Captions:
    def __init__(self):
        self.chunks = build_chunks()
        self.cache = {}

    def apply(self, img, t):
        for i, c in enumerate(self.chunks):
            if c["start"] <= t < c["end"]:
                if i not in self.cache:
                    self.cache[i] = render_caption(c["words"])
                cap = self.cache[i]
                age = t - c["start"]
                sc = 1.0 + 0.14 * max(0.0, 1 - age / 0.12)
                if sc != 1.0:
                    cap = cv2.resize(cap, None, fx=sc, fy=sc, interpolation=cv2.INTER_LINEAR)
                h, w = cap.shape[:2]
                x0, y0 = int(CAP_CX - w / 2), int(CAP_CY - h / 2)
                x0c, y0c = max(0, x0), max(0, y0)
                x1c, y1c = min(W, x0 + w), min(H, y0 + h)
                sub = cap[y0c - y0:y1c - y0, x0c - x0:x1c - x0]
                a = sub[..., 3:]
                img[y0c:y1c, x0c:x1c] = img[y0c:y1c, x0c:x1c] * (1 - a) + sub[..., :3] * a
        return img


# ------------------------------------------------------------------ post effects
class Post:
    def __init__(self):
        rng = np.random.default_rng(77)
        self.grain = [rng.standard_normal((H // 2, W // 2)).astype(np.float32) for _ in range(10)]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx / W - 0.5) * 1.15) ** 2 + ((yy / H - 0.5) * 0.95) ** 2)
        self.vig = np.clip(1 - 1.25 * np.clip(r - 0.22, 0, 1) ** 1.5, 0.15, 1)[..., None]
        # flicker curve: slow wobble + random dips
        n = NF + 10
        fl = np.convolve(rng.standard_normal(n), np.ones(4) / 4, mode="same") * 0.035
        dips = rng.random(n) < 0.035
        fl[dips] -= rng.uniform(0.08, 0.22, dips.sum())
        self.flicker = 1 + fl
        self.captions = Captions()

    def glitch_amount(self, t):
        for c in GLITCH_CUTS:
            if c - 0.07 <= t < c + 0.13:
                return 1.0
        for m in MINI_GLITCHES:
            if m <= t < m + 0.09:
                return 0.45
        return 0.0

    def glitch(self, img, s, seed):
        rng = np.random.default_rng(seed)
        dx = int(8 + 30 * s)
        img[..., 0] = np.roll(img[..., 0], dx, axis=1)
        img[..., 2] = np.roll(img[..., 2], -dx, axis=1)
        for _ in range(int(3 + 7 * s)):
            y0 = int(rng.integers(0, H - 20))
            h = int(rng.integers(8, int(30 + 140 * s)))
            img[y0:y0 + h] = np.roll(img[y0:y0 + h], int(rng.integers(-160, 160) * s), axis=1)
        static = rng.random((H // 6, W // 6)).astype(np.float32)
        static = cv2.resize(static, (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
        a = 0.15 + 0.4 * s * rng.random()
        img = img * (1 - a) + static * a
        if rng.random() < 0.6:
            y0 = int(rng.integers(0, H - 60))
            img[y0:y0 + int(rng.integers(6, 40))] = 0.85
        img[::4] *= 0.75
        return img

    def apply(self, img, t, fi, scene):
        if scene.__class__.__name__ == "Black":
            return img
        img = np.power(np.clip(img, 0, None), 1.08) * 1.04 + 0.012
        img *= self.flicker[fi]
        img *= self.vig
        g = cv2.resize(self.grain[(fi * 7) % 10], (W, H), interpolation=cv2.INTER_LINEAR)
        if fi % 2:
            g = g[::-1]
        img += (g * (0.035 + 0.03 * (1 - np.clip(img.mean(-1), 0, 1))))[..., None]
        s = self.glitch_amount(t)
        if s > 0:
            img = self.glitch(np.clip(img, 0, 1), s, fi)
        img = self.captions.apply(np.clip(img, 0, 1), t)
        return img


_post = None


def render_frame(fi):
    global _post
    if _post is None:
        _post = Post()
    t = fi / FPS
    name, sc = scenes.scene_at(t)
    graded = lambda s_: np.clip(s_.frame(t), 0, 1.5) * np.asarray(s_.grade, np.float32)
    tr = transitions.active(t)
    if tr is not None:
        kind, p, opts, a, b = tr
        img = transitions.apply(kind, graded(scenes.get_scene(a)), graded(scenes.get_scene(b)), p, opts, fi)
    else:
        img = graded(sc)
    img = _post.apply(img.astype(np.float32), t, fi, sc)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def encode_segment(args):
    k, f0, f1 = args
    out = f"{B}/seg{k:02d}.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "12M", "-bufsize", "24M",
                          "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-g", "60",
                          "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", out],
                         stdin=subprocess.PIPE)
    for fi in range(f0, f1):
        p.stdin.write(render_frame(fi).tobytes())
        if (fi - f0) % 60 == 0:
            print(f"seg{k}: frame {fi}/{f1}", flush=True)
    p.stdin.close()
    assert p.wait() == 0
    return out


def video(workers):
    # split on scene boundaries so each worker only builds the scenes it needs
    bounds = np.linspace(0, NF, workers + 1).astype(int)
    jobs = [(k, bounds[k], bounds[k + 1]) for k in range(workers)]
    with Pool(workers) as pool:
        segs = pool.map(encode_segment, jobs)
    with open(f"{B}/segs.txt", "w") as f:
        for s in segs:
            f.write(f"file '{os.path.abspath(s)}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", f"{B}/segs.txt",
                    "-c", "copy", f"{B}/video.mp4"], check=True)


def mux():
    out = os.path.join(ROOT, "slenderman_tiktok.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", f"{B}/video.mp4", "-i", f"{B}/mix.wav",
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{DUR:.3f}", "-movflags", "+faststart", out], check=True)
    print(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height,r_frame_rate,duration,nb_frames",
                                   "-of", "default=nw=1", out]).decode())


def preview(times):
    os.makedirs(f"{B}/preview", exist_ok=True)
    thumbs = []
    for t in times:
        fi = int(round(t * FPS))
        img = render_frame(fi)
        cv2.imwrite(f"{B}/preview/f{t:05.2f}.png", img[..., ::-1])
        thumbs.append(cv2.resize(img, (270, 480), interpolation=cv2.INTER_AREA))
    cols = int(os.environ.get("COLS", 6))
    rows = (len(thumbs) + cols - 1) // cols
    sheet = np.zeros((rows * 480, cols * 270, 3), np.uint8)
    for i, th in enumerate(thumbs):
        sheet[(i // cols) * 480:(i // cols + 1) * 480, (i % cols) * 270:(i % cols + 1) * 270] = th
    cv2.imwrite(f"{B}/preview/sheet.png", sheet[..., ::-1])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "preview":
        preview([float(x) for x in sys.argv[2:]])
    elif cmd == "video":
        w = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
        video(w)
    elif cmd == "mux":
        mux()
    elif cmd == "chunks":
        for c in build_chunks():
            print(f"{c['start']:6.2f}-{c['end']:6.2f}  " + " ".join(w + ("*" if h else "") for w, h in c["words"]))
