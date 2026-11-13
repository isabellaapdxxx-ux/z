"""Build driver.

  python render.py preview 2 9 20 26      # render single frames (seconds) to build/preview/
  python render.py video [--workers 4]    # all 900 frames -> build/video.mp4 (H.264, BT.709)
  python render.py audio                  # build/audio.wav (see audio.py)
  python render.py mux                    # -> iphone18_ad.mp4 + captions.srt
  python render.py check                  # ffprobe: durations, frame count, peaks
  python render.py stills 2 9 20 26       # PNG stills from the final MP4 -> stills/
"""
import json
import os
import subprocess
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
FINAL = os.path.join(ROOT, "iphone18_ad.mp4")
SRT = os.path.join(ROOT, "captions.srt")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import FPS, H, N_FRAMES, W  # noqa: E402


def _frame(i):
    import film
    return i, film.render_frame(i).tobytes()


def preview(times):
    import film
    from PIL import Image
    out = os.path.join(BUILD, "preview")
    os.makedirs(out, exist_ok=True)
    for s in times:
        i = int(round(float(s) * FPS))
        t0 = time.time()
        img = film.render_frame(i)
        Image.fromarray(img).save(os.path.join(out, f"f{i:04d}_{float(s):05.2f}s.png"))
        print(f"frame {i} ({s}s) {time.time() - t0:.2f}s", flush=True)


def video(workers=4, first=0, last=N_FRAMES):
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "video.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-tune", "film",
           "-x264-params", "aq-mode=3", "-g", "60",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
           "-r", str(FPS), out]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    with Pool(workers) as pool:
        for n, (i, buf) in enumerate(pool.imap(_frame, range(first, last), chunksize=1)):
            enc.stdin.write(buf)
            if n % 30 == 0:
                el = time.time() - t0
                print(f"frame {i}/{last}  {el:6.1f}s elapsed  ~{el / (n + 1) * (last - first - n - 1):6.0f}s left",
                      flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    print(f"video done in {time.time() - t0:.0f}s -> {out}")


def audio():
    import audio as A
    A.build(os.path.join(BUILD, "audio.wav"))


def mux():
    import captions
    v, a = os.path.join(BUILD, "video.mp4"), os.path.join(BUILD, "audio.wav")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", v, "-i", a, "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", FINAL]
    subprocess.run(cmd, check=True)
    captions.write_srt(SRT)
    print("wrote", FINAL, "and", SRT)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                        "stream=index,codec_name,codec_type,width,height,r_frame_rate,sample_rate,channels,"
                        "duration,duration_ts,time_base,nb_frames,nb_read_frames:format=duration",
                        "-of", "json", path], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def check(path=FINAL):
    info = probe(path)
    print(json.dumps(info, indent=2))
    ok = True
    for s in info["streams"]:
        dur = float(s["duration"])
        if s["codec_type"] == "video":
            n = int(s["nb_read_frames"])
            print(f"video: {s['codec_name']} {s['width']}x{s['height']} {s['r_frame_rate']} "
                  f"duration={dur:.3f}s frames={n}")
            ok &= abs(dur - 30.0) < 5e-4 and n == N_FRAMES and s["width"] == W and s["height"] == H
        else:
            print(f"audio: {s['codec_name']} {s['sample_rate']} Hz ch={s['channels']} duration={dur:.3f}s")
            ok &= abs(dur - 30.0) < 5e-4 and s["sample_rate"] == "48000"
    print("format duration:", info["format"]["duration"])
    # decoded audio length and peak
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-f", "f32le", "-ac", "2", "-"],
                       capture_output=True, check=True)
    import numpy as np
    pcm = np.frombuffer(r.stdout, np.float32)
    print(f"decoded audio samples/ch = {pcm.size // 2} ({pcm.size / 2 / 48000:.4f}s), "
          f"peak = {20 * np.log10(np.abs(pcm).max() + 1e-12):.2f} dBFS")
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
    return ok


def stills(times):
    out = os.path.join(ROOT, "stills")
    os.makedirs(out, exist_ok=True)
    for s in times:
        n = int(round(float(s) * FPS))
        p = os.path.join(out, f"still_{float(s):04.1f}s.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", FINAL, "-vf", f"select=eq(n\\,{n})",
                        "-vframes", "1", "-update", "1", p], check=True)
        print("wrote", p)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    args = sys.argv[2:]
    if cmd == "preview":
        preview(args)
    elif cmd == "video":
        w = int(args[args.index("--workers") + 1]) if "--workers" in args else 4
        video(w)
    elif cmd == "audio":
        audio()
    elif cmd == "mux":
        mux()
    elif cmd == "check":
        sys.exit(0 if check(args[0] if args else FINAL) else 1)
    elif cmd == "stills":
        stills(args or ["2", "9", "20", "26"])
    else:
        print(__doc__)
