"""Render every scene (with its incoming transition baked in) to its own
H.264 file, then join them with the concat demuxer (-c copy)."""
import json
import os
import subprocess
import sys
import time
from multiprocessing import Pool

import numpy as np
from scipy import ndimage

import assets as A
import gfx as G
import scenes as SC
from captions import Captions
from config import BUILD, FPS, H, W

SEG_DIR = BUILD / "segments"
ZC = (540, 860)  # zoom-transition centre


class Ctx:
    def __init__(self, tl):
        self.tl = tl
        self.ev = SC.events(tl)
        cam = SC.Camera(tl, self.ev)
        self.stars = A.Starfield(cam.camz, cam.camx, cam.camy)
        self.scenes = {s["index"]: s for s in tl["scenes"]}

    def at(self, idx, gt):
        s = self.scenes[idx]
        self.idx, self.gt = idx, gt
        self.start, self.D = s["start"], s["end"] - s["start"]
        self.t = gt - self.start
        return self

    def lt(self, name):
        return self.ev[name] - self.start


def render_scene(c, idx, gt):
    return SC.SCENES[idx](c.at(idx, gt))


# ------------------------------------------------------------------ transitions
def _shift_add(out, src, off, axis):
    N = src.shape[axis]
    if abs(off) >= N:
        return
    if axis == 1:
        if off >= 0:
            out[:, off:] += src[:, :N - off]
        else:
            out[:, :N + off] += src[:, -off:]
    else:
        if off >= 0:
            out[off:] += src[:N - off]
        else:
            out[:N + off] += src[-off:]


def transition(kind, A_, B_, p, seed):
    if kind.startswith("whip"):
        e = 0.5 - 0.5 * np.cos(np.pi * p)
        axis, sign = {"whip_left": (1, -1), "whip_right": (1, 1),
                      "whip_up": (0, -1), "whip_down": (0, 1)}[kind]
        N = W if axis == 1 else H
        off = int(round(e * N))
        out = np.zeros_like(A_)
        _shift_add(out, A_, sign * off, axis)
        _shift_add(out, B_, sign * (off - N), axis)
        size = int(1 + 260 * np.sin(np.pi * p) * (N / W) ** 0.5)
        if size > 2:
            out = ndimage.uniform_filter1d(out, size, axis=axis, mode="nearest")
        return out
    if kind == "zoom_out":  # old shot shrinks away, new shot settles from close-up
        q = G.ease_in_out(p)
        a = SC.zoom_frame(A_, 1 - 0.7 * q, *ZC)
        b = SC.zoom_frame(B_, 2.2 - 1.2 * q, *ZC)
        b = 0.5 * b + 0.5 * SC.zoom_frame(B_, (2.2 - 1.2 * q) * (1 + 0.06 * (1 - q)), *ZC)
        w = float(G.smoothstep(0.1, 0.8, p))
        return a * (1 - w) + b * w
    if kind == "zoom_in":  # punch through the old shot into the new one
        q = G.ease_in_out(p)
        a = SC.zoom_frame(A_, 1 + 1.8 * q, *ZC)
        a = 0.5 * a + 0.5 * SC.zoom_frame(A_, (1 + 1.8 * q) * 1.08, *ZC)
        b = SC.zoom_frame(B_, 0.5 + 0.5 * q, *ZC)
        w = float(G.smoothstep(0.2, 0.85, p))
        return a * (1 - w) + b * w
    if kind == "flash":
        base = A_ if p < 0.5 else B_
        f = (1 - abs(2 * p - 1)) ** 1.4
        return base * (1 - 0.5 * f) + 1.8 * f
    if kind == "glitch":
        rng = np.random.default_rng(seed)
        base = B_ if rng.random() < p ** 0.8 else A_
        return SC.glitch(base, 0.25 + 0.75 * np.sin(np.pi * p), seed)
    if kind == "fade_black":
        if p < 0.5:
            return A_ * (1 - G.ease_in_out(2 * p))
        return B_ * G.ease_in_out(2 * p - 1)
    raise ValueError(kind)


def compose(c, caps, f):
    """Final RGB uint8 frame for global frame index f."""
    gt = f / FPS
    idx = next(s["index"] for s in c.tl["scenes"] if s["f0"] <= f < s["f1"])
    s = c.scenes[idx]
    img = render_scene(c, idx, gt)
    tr = s["transition"]
    if tr:
        nfr = tr["dur"] * FPS
        k = f - s["f0"]
        if k < nfr:
            p = (k + 0.5) / nfr
            prev = render_scene(c, idx - 1, gt)
            img = transition(tr["kind"], prev, img, p, seed=f)
    img = G.bloom(img)
    img *= G.vignette()
    out = G.to_u8(G.tonemap(img))
    return caps.draw(out, gt)


def _encoder(path):
    return subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "60", "-threads", "2",
         "-video_track_timescale", "15360", str(path)],
        stdin=subprocess.PIPE)


def _job(args):
    idx, tl = args
    c = Ctx(tl)
    caps = Captions(tl)
    s = c.scenes[idx]
    path = SEG_DIR / f"scene{idx:02d}.mp4"
    t0 = time.time()
    enc = _encoder(path)
    for f in range(s["f0"], s["f1"]):
        enc.stdin.write(compose(c, caps, f).tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError(f"encoder failed for scene {idx}")
    n = s["f1"] - s["f0"]
    print(f"  scene {idx:2d}: {n} frames in {time.time() - t0:5.1f}s", flush=True)
    return idx


def render_video(workers=None, only=None):
    tl = json.loads((BUILD / "timeline.json").read_text())
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    A.hdf_texture()  # build the shared texture once before forking
    todo = [s["index"] for s in tl["scenes"] if not only or s["index"] in only]
    todo.sort(key=lambda i: -(c := tl["scenes"][i - 1])["f1"] + c["f0"])
    workers = workers or os.cpu_count()
    with Pool(workers) as pool:
        for _ in pool.imap_unordered(_job, [(i, tl) for i in todo]):
            pass
    lst = SEG_DIR / "concat.txt"
    lst.write_text("".join(f"file 'scene{s['index']:02d}.mp4'\n" for s in tl["scenes"]))
    out = BUILD / "video.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(out)], check=True)
    return out


def stills(times, out_dir=None):
    """Export single frames (global seconds) as PNG for checking."""
    from PIL import Image
    tl = json.loads((BUILD / "timeline.json").read_text())
    out_dir = out_dir or BUILD / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    c = Ctx(tl)
    caps = Captions(tl)
    paths = []
    for t in times:
        f = min(int(round(t * FPS)), tl["scenes"][-1]["f1"] - 1)
        p = out_dir / f"frame_{f:04d}.png"
        Image.fromarray(compose(c, caps, f)).save(p)
        paths.append(p)
    return paths


if __name__ == "__main__":
    if sys.argv[1] == "stills":
        for p in stills([float(x) for x in sys.argv[2:]]):
            print(p)
    elif sys.argv[1] == "video":
        only = [int(x) for x in sys.argv[2:]] or None
        print(render_video(only=only))
