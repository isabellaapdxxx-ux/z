#!/usr/bin/env python3
"""One-command build of the 60 s vertical TikTok "How big is the universe?".

    python build.py            # full build -> final_tiktok.mp4
    python build.py --fresh    # also re-request every voice clip from edge-tts
    python build.py --stills   # only export check frames (scenes 7, 10, 11, 13)

Steps: fonts -> voice (edge-tts) -> timeline (fit to 60.0 s) -> soundtrack
(numpy synth + ffmpeg sidechain/loudnorm) -> check stills -> scene renders
(transitions baked in) -> concat (-c copy) -> mux -> ffprobe checks.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from config import BUILD, DURATION, FONT_URLS, FPS, H, OUTPUT, W  # noqa: E402


def step(name):
    print(f"\n== {name}", flush=True)
    return time.time()


def ensure_fonts():
    for path, url in FONT_URLS.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"  downloading {path.name}")
            urllib.request.urlretrieve(url, path)


def check_stills():
    import render
    import scenes as SC
    tl = json.loads((BUILD / "timeline.json").read_text())
    ev = SC.events(tl)
    S = {s["index"]: s for s in tl["scenes"]}
    busiest = {  # moments with the most on screen (object + labels + caption)
        7: ev["s7_ruler"] + 0.6,
        10: S[10]["end"] - 0.3,
        11: ev["s11_zoom1"] + 0.45,
        13: ev["s13_reveal"] + 0.12,
    }
    paths = render.stills(list(busiest.values()), BUILD / "check_frames")
    for (scene, t), p in zip(busiest.items(), paths):
        target = p.with_name(f"scene{scene:02d}_{t:05.2f}s.png")
        p.replace(target)
        print(f"  {target.relative_to(BUILD.parent)}")


def mux(video, audio):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-ar", "48000", "-movflags", "+faststart", str(OUTPUT)], check=True)


def probe():
    out = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,codec_type,width,height,r_frame_rate,nb_frames,duration,sample_rate",
         "-of", "json", str(OUTPUT)], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in out["streams"] if s["codec_type"] == "video")
    a = next(s for s in out["streams"] if s["codec_type"] == "audio")
    fmt = float(out["format"]["duration"])
    print(f"  container {fmt:.3f}s | video {v['codec_name']} {v['width']}x{v['height']} {v['r_frame_rate']} fps "
          f"{v['nb_frames']} frames {float(v['duration']):.3f}s | audio {a['codec_name']} {a['sample_rate']} Hz "
          f"{float(a['duration']):.3f}s")
    ok = (v["codec_name"] == "h264" and a["codec_name"] == "aac" and v["width"] == W and v["height"] == H
          and v["r_frame_rate"] == f"{FPS}/1" and int(v["nb_frames"]) == int(DURATION * FPS)
          and abs(fmt - DURATION) < 0.0005 and abs(float(a["duration"]) - DURATION) < 0.0005)
    print("  CHECK " + ("PASSED" if ok else "FAILED"))
    return ok


def main():
    fresh = "--fresh" in sys.argv
    t = step("fonts")
    ensure_fonts()
    import tts
    import timeline
    t = step("voiceover (edge-tts)")
    tts.generate(fresh=fresh)
    t = step("timeline")
    timeline.build()
    t = step("check frames")
    check_stills()
    if "--stills" in sys.argv:
        return
    import audio
    import render
    t = step("soundtrack")
    wav = audio.build()
    t = step("video (scenes in parallel)")
    video = render.render_video()
    print(f"  rendered in {time.time() - t:.0f}s")
    step("mux")
    mux(video, wav)
    step("ffprobe checks")
    ok = probe()
    print(f"\n{'Done' if ok else 'Built with problems'}: {OUTPUT}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
