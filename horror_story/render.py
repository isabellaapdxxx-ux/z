"""Render the video.

  python render.py frames 0 1.5 3 ...      -> preview/frame_<t>.png
  python render.py video --workers 4       -> build/video.mp4 (no audio, rendered in parallel segments)
  python render.py mux                     -> ../horror_story.mp4 (H.264 + AAC, trimmed to exactly 120.0 s)
"""
import argparse
import os
import subprocess
import sys
import time
from multiprocessing import Process

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, 'build')
sys.path.insert(0, HERE)

from config import FPS, NFRAMES, W, H, DURATION  # noqa: E402


def compose(f):
    import fx
    import shots as SH
    t = f / FPS
    spec = SH.shot_at(t)
    img = spec['img'] if 'img' in spec else SH.R.render(spec['scene'], spec['cam'])
    if img.size != (W, H):
        img = img.resize((W, H), Image.BICUBIC)
    img = fx.post(img.convert('RGB'), spec, t, f)
    fx.draw_captions(img, t)
    fx.draw_teaser(img, t)
    return img


from PIL import Image  # noqa: E402


def worker(idx, f0, f1, out):
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS),
           '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for f in range(f0, f1):
        p.stdin.write(compose(f).tobytes())
        if (f - f0) % 90 == 0:
            done = f - f0 + 1
            print(f'[w{idx}] {done}/{f1 - f0}  {(time.time() - t0) / done:.2f}s/frame', flush=True)
    p.stdin.close()
    p.wait()


def video(workers):
    os.makedirs(BUILD, exist_ok=True)
    # interleave chunk sizes so heavy and light scenes spread over workers
    nchunks = workers * 4
    bounds = [round(i * NFRAMES / nchunks) for i in range(nchunks + 1)]
    chunks = [(i, bounds[i], bounds[i + 1], os.path.join(BUILD, f'seg_{i:03d}.mp4')) for i in range(nchunks)]
    queue = list(chunks)
    running = []
    while queue or running:
        while queue and len(running) < workers:
            c = queue.pop(0)
            pr = Process(target=worker, args=c)
            pr.start()
            running.append(pr)
        for pr in list(running):
            if not pr.is_alive():
                pr.join()
                running.remove(pr)
        time.sleep(0.5)
    lst = os.path.join(BUILD, 'segments.txt')
    with open(lst, 'w') as fh:
        for c in chunks:
            fh.write(f"file '{c[3]}'\n")
    subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy',
                           os.path.join(BUILD, 'video.mp4')])
    print('video ->', os.path.join(BUILD, 'video.mp4'))


def mux():
    out = os.path.join(ROOT, 'horror_story.mp4')
    subprocess.check_call(['ffmpeg', '-v', 'error', '-y', '-i', os.path.join(BUILD, 'video.mp4'),
                           '-i', os.path.join(BUILD, 'audio.wav'), '-map', '0:v:0', '-map', '1:a:0',
                           # ~5 Mbps H.264 High: TikTok-friendly size (the grain makes CRF encodes huge)
                           '-c:v', 'libx264', '-preset', 'slow', '-b:v', '5000k', '-maxrate', '7000k', '-bufsize',
                           '10000k', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-r', str(FPS),
                           '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
                           '-t', f'{DURATION:.3f}', '-movflags', '+faststart', out])
    print('final ->', out)


def frames(times, outdir):
    os.makedirs(outdir, exist_ok=True)
    for t in times:
        f = min(NFRAMES - 1, int(round(float(t) * FPS)))
        img = compose(f)
        p = os.path.join(outdir, f'frame_{float(t):06.2f}s.png')
        img.save(p)
        print(p)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['frames', 'video', 'mux'])
    ap.add_argument('times', nargs='*')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--out', default=os.path.join(HERE, 'preview'))
    a = ap.parse_args()
    if a.mode == 'frames':
        frames(a.times, a.out)
    elif a.mode == 'video':
        video(a.workers)
    else:
        mux()
