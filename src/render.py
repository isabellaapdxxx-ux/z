"""Render the video.

  python src/render.py frames --times 0 3.2 10 ...   -> PNG stills (for checking)
  python src/render.py video --workers 4               -> build/video_noaudio.mp4
  python src/render.py mux                             -> final_video.mp4
"""
import argparse
import math
import os
import subprocess
import sys
import time
from multiprocessing import Process

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, 'build')
sys.path.insert(0, HERE)

from script_data import DURATION, FPS  # noqa: E402

W, H = 1080, 1920
NFRAMES = int(round(DURATION * FPS))

_caps = None


def caps():
    global _caps
    if _caps is None:
        import overlay as O
        _caps = O.Captions(os.path.join(BUILD, 'vo_timing.json'))
    return _caps


def louver(slide):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    off = -slide * (W + 200)
    d.rectangle([off - 60, 0, off + W + 60, H], fill=(8, 6, 5, 255))
    for y in range(-40, H + 80, 88):
        d.polygon([(off, y), (off + W, y - 30), (off + W, y + 18), (off, y + 48)], fill=(0, 0, 0, 0))
    d.rectangle([off - 60, 0, off + 30, H], fill=(25, 18, 14, 255))
    d.rectangle([off + W - 30, 0, off + W + 60, H], fill=(25, 18, 14, 255))
    return im


def stripes(alpha):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for y in range(-200, H + 300, 150):
        d.polygon([(0, y), (W, y - 260), (W, y - 225), (0, y + 35)], fill=(255, 215, 150, int(60 * alpha)))
    return im.filter(ImageFilter.GaussianBlur(6))


_stripe_cache = {}


def compose(f):
    import overlay as O
    import shots as SH
    t = f / FPS
    fr = SH.shot_at(t)
    img = fr['img']
    if fr['blur'] > 0.3:
        img = img.filter(ImageFilter.GaussianBlur(fr['blur']))
    sx, sy = O.shake(t, fr['shake']) if fr['shake'] else (0, 0)
    rot = fr['rot'] + (sx / 4000.0 if fr['shake'] else 0)
    img = O.transform2d(img, fr['zoom'], sx + fr['dx'], sy + fr['dy'], rot)
    sl = fr['slats']
    if sl is not None:
        if isinstance(sl, tuple) or sl >= 1.0:
            slide = sl[1] if isinstance(sl, tuple) else 0.0
            if slide < 1.0:
                lv = louver(slide)
                img.paste(lv, (0, 0), lv)
        else:
            key = round(sl, 2)
            if key not in _stripe_cache:
                _stripe_cache[key] = stripes(sl * 4)
            s = _stripe_cache[key]
            img.paste(s, (0, 0), s)
    if fr['lids'] is not None:
        o = fr['lids']
        d = ImageDraw.Draw(img)
        hgt = int((1 - o) * H / 2) + (0 if o >= 1 else 2)
        if hgt > 0:
            d.rectangle([0, 0, W, hgt], fill=(0, 0, 0))
            d.rectangle([0, H - hgt, W, H], fill=(0, 0, 0))
    img = O.post(img, t, f, vig=fr['vig'], grain_amt=fr['grain'], bloom=fr['bloom'], tint=fr['tint'],
                 flash=fr['flash'], chroma=fr['chroma'], bright=fr['bright'], contrast=fr['contrast'])
    if fr['rb']:
        arr = np.asarray(img).astype(np.float32)
        col = np.array((255, 30, 30) if fr['rb'] > 0 else (40, 80, 255), np.float32)
        y, x = np.ogrid[0:H, 0:W]
        edge = np.clip((np.abs(x - W / 2) / (W / 2)) ** 3, 0, 1)[:, :, None] * abs(fr['rb']) * 2
        arr = arr * (1 - edge) + col * edge
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if fr['glitch'] > 0:
        img = O.glitch(img, fr['glitch'], f)
    if fr['hud'] == 'rewind':
        O.rewind_hud(img, t)
    caps().draw(img, t)
    O.draw_corner(img, t)
    return img


def worker(idx, f0, f1, out):
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
           '-i', '-', '-c:v', 'libx264', '-preset', 'fast', '-crf', '12', '-pix_fmt', 'yuv420p', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for f in range(f0, f1):
        img = compose(f)
        p.stdin.write(img.tobytes())
        if (f - f0) % 60 == 0:
            el = time.time() - t0
            done = f - f0 + 1
            print(f'[w{idx}] {done}/{f1 - f0} frames, {el / done:.2f}s/frame', flush=True)
    p.stdin.close()
    p.wait()


def limit_audio(src, dst, gain_db=-1.6, ceiling=0.6, look_ms=3.0, release_ms=80.0):
    """Lookahead peak limiter (numpy) so the AAC encode keeps true peaks below about -1 dBTP."""
    from scipy.io import wavfile
    from scipy.ndimage import maximum_filter1d
    from scipy.signal import lfilter
    sr, x = wavfile.read(src)
    x = x.astype(np.float64) / 32768 * 10 ** (gain_db / 20)
    peak = np.abs(x).max(1)
    la = int(sr * look_ms / 1000)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    g = -maximum_filter1d(-need, size=2 * la + 1)          # min over the lookahead window
    a = math.exp(-1.0 / (sr * release_ms / 1000))
    # smooth recovery (release), never above the required gain
    g_s = np.minimum(g, lfilter([1 - a], [1, -a], g, zi=[g[0] * a])[0])
    # short attack ramp ahead of each peak (min-filter, then moving average over the lookahead)
    g_s = -maximum_filter1d(-g_s, size=la + 1)
    g_s = np.convolve(g_s, np.ones(la) / la, mode='same')
    y = x * g_s[:, None]
    y = np.clip(y, -ceiling, ceiling)
    fade = int(sr * 0.003)
    y[:fade] *= np.linspace(0, 1, fade)[:, None]
    wavfile.write(dst, sr, (y * 32767).astype(np.int16))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['frames', 'video', 'mux'])
    ap.add_argument('--times', type=float, nargs='*', default=[])
    ap.add_argument('--out', default=os.path.join(BUILD, 'frames'))
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--end', type=int, default=NFRAMES)
    a = ap.parse_args()
    os.makedirs(BUILD, exist_ok=True)
    if a.mode == 'frames':
        os.makedirs(a.out, exist_ok=True)
        for t in a.times:
            f = int(round(t * FPS))
            img = compose(f)
            p = os.path.join(a.out, f'f{f:05d}.png')
            img.save(p)
            print(p)
    elif a.mode == 'video':
        segdir = os.path.join(BUILD, 'segments')
        os.makedirs(segdir, exist_ok=True)
        n = a.end - a.start
        # interleave chunks so heavy scenes are spread across workers
        chunk = 150
        ranges = [(s, min(s + chunk, a.end)) for s in range(a.start, a.end, chunk)]
        groups = [ranges[i::a.workers] for i in range(a.workers)]

        def run_group(gi, rs):
            for (s, e) in rs:
                out = os.path.join(segdir, f'seg_{s:05d}.mp4')
                if os.path.exists(out) and os.path.getsize(out) > 1000:
                    continue
                worker(gi, s, e, out + '.tmp.mp4')
                os.replace(out + '.tmp.mp4', out)
        procs = [Process(target=run_group, args=(i, g)) for i, g in enumerate(groups)]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        segs = sorted(x for x in os.listdir(segdir) if x.startswith('seg_') and x.endswith('.mp4') and 'tmp' not in x)
        with open(os.path.join(segdir, 'list.txt'), 'w') as fh:
            for s in segs:
                fh.write(f"file '{s}'\n")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i',
                        os.path.join(segdir, 'list.txt'), '-c', 'copy', os.path.join(BUILD, 'video_noaudio.mp4')],
                       check=True)
        print('wrote build/video_noaudio.mp4')
    elif a.mode == 'mux':
        out = os.path.join(ROOT, 'final_video.mp4')
        apath = os.path.join(BUILD, 'audio_final.wav')
        limit_audio(os.path.join(BUILD, 'audio.wav'), apath)
        cmd = ['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(BUILD, 'video_noaudio.mp4'), '-i',
               apath,
               '-map', '0:v:0', '-map', '1:a:0',
               '-c:v', 'libx264', '-preset', 'slow', '-crf', '21', '-maxrate', '5M', '-bufsize', '10M',
               '-profile:v', 'high', '-level', '4.1', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-g', '60',
               '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
               '-t', f'{DURATION:.3f}', '-movflags', '+faststart', out]
        subprocess.run(cmd, check=True)
        print('wrote', out)


if __name__ == '__main__':
    main()
