"""Fit the voice clips into exactly 60 s and derive every scene's timing.

1. Measure the processed TTS clips.
2. If lead-in + speech + pauses would end later than DURATION - TAIL_MIN
   (= the ~58 s voice budget), speed every clip up with ffmpeg atempo
   (never above MAX_ATEMPO), then shrink the pauses toward their floors.
   If it is short, the pauses grow (up to GAP_STRETCH_MAX); the rest is tail.
3. Scene i starts LEAD before its line (frame aligned); scene 16 ends at 60 s.
Writes build/timeline.json and build/tts/lineNN_final.npy.
"""
import json
import subprocess

import numpy as np

from config import (BUILD, DURATION, FPS, GAP_DEFAULT, GAP_FLOOR_DEFAULT, GAP_FLOORS, GAPS,
                    GAP_STRETCH_MAX, LEAD_DEFAULT, LEAD_IN, LEADS, LINES, MAX_ATEMPO, N_FRAMES,
                    SR, TAIL_MIN, TRANSITIONS, VOICE_TARGET_MAX)
from tts import TTS_DIR


def atempo(clip, factor):
    if abs(factor - 1.0) < 1e-4:
        return clip
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
         "-af", f"atempo={factor:.5f}", "-f", "f32le", "-"],
        input=clip.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(out, np.float32).copy()


def split_words(words):
    """edge-tts sometimes returns several words in one boundary ('49 years')."""
    out = []
    for w in words:
        parts = w["text"].split()
        if len(parts) == 1:
            out.append(dict(w))
            continue
        lens = np.array([len(p) + 1.0 for p in parts])
        edges = np.concatenate([[0], np.cumsum(lens)]) / lens.sum()
        for k, p in enumerate(parts):
            out.append({"text": p, "t0": w["t0"] + edges[k] * (w["t1"] - w["t0"]),
                        "t1": w["t0"] + edges[k + 1] * (w["t1"] - w["t0"])})
    return out


def build():
    meta = json.loads((TTS_DIR / "meta.json").read_text())
    clips = [np.load(TTS_DIR / f"line{i:02d}.npy") for i in range(1, len(LINES) + 1)]
    speech = sum(len(c) for c in clips) / SR
    n = len(LINES)
    gaps = {i: GAPS.get(i, GAP_DEFAULT) for i in range(2, n + 1)}
    floors = {i: GAP_FLOORS.get(i, GAP_FLOOR_DEFAULT) for i in range(2, n + 1)}
    end_budget = min(VOICE_TARGET_MAX + 0.6, DURATION - TAIL_MIN)
    voice_total = LEAD_IN + speech + sum(gaps.values())
    factor = 1.0
    if voice_total > VOICE_TARGET_MAX:
        need = speech / max(1e-3, end_budget - LEAD_IN - sum(gaps.values()))
        factor = float(np.clip(need, 1.0, MAX_ATEMPO))
    clips = [atempo(c, factor) for c in clips]
    durs = [len(c) / SR for c in clips]
    room = end_budget - LEAD_IN - sum(durs)  # what the pauses may use
    G = sum(gaps.values())
    if room < G:  # shrink pauses toward their floors
        F = sum(floors.values())
        if room < F:
            raise SystemExit(f"voice too long even at atempo {factor:.3f}: needs "
                             f"{LEAD_IN + sum(durs) + F + TAIL_MIN:.2f}s")
        k = (room - F) / (G - F)
        gaps = {i: floors[i] + (g - floors[i]) * k for i, g in gaps.items()}
    else:  # stretch pauses (the remainder becomes the closing hold)
        k = min(GAP_STRETCH_MAX / max(gaps.values()), room / G)
        k = max(1.0, k)
        gaps = {i: g * k for i, g in gaps.items()}

    starts, t = [], LEAD_IN
    for i in range(1, n + 1):
        if i > 1:
            t += gaps[i]
        starts.append(t)
        t += durs[i - 1]
    voice_end = t

    lines = []
    for i in range(1, n + 1):
        src = meta["lines"][i - 1]
        scale = durs[i - 1] / src["duration"]
        words = [{"text": w["text"], "t0": starts[i - 1] + w["t0"] * scale,
                  "t1": starts[i - 1] + w["t1"] * scale} for w in split_words(src["words"])]
        lines.append({"index": i, "text": LINES[i - 1], "start": starts[i - 1],
                      "end": starts[i - 1] + durs[i - 1], "words": words})
        np.save(TTS_DIR / f"line{i:02d}_final.npy", clips[i - 1])

    frames = [0] + [int(round((starts[i - 1] - LEADS.get(i, LEAD_DEFAULT)) * FPS))
                    for i in range(2, n + 1)] + [N_FRAMES]
    scenes = []
    for i in range(1, n + 1):
        f0, f1 = frames[i - 1], frames[i]
        tr = TRANSITIONS.get(i)
        scenes.append({"index": i, "f0": f0, "f1": f1, "start": f0 / FPS, "end": f1 / FPS,
                       "transition": {"kind": tr[0], "dur": tr[1]} if tr else None})
    tl = {"atempo": factor, "speech": sum(durs), "voice_end": voice_end,
          "tail": DURATION - voice_end, "gaps": gaps, "lines": lines, "scenes": scenes}
    (BUILD / "timeline.json").write_text(json.dumps(tl, indent=1))
    print(f"  atempo {factor:.3f}  speech {sum(durs):.2f}s  voice ends {voice_end:.2f}s  "
          f"tail {DURATION - voice_end:.2f}s")
    print("  pauses: " + " ".join(f"{i}:{g:.2f}" for i, g in gaps.items()))
    for s in scenes:
        print(f"  scene {s['index']:2d}: {s['start']:6.2f}-{s['end']:6.2f}  ({(s['f1'] - s['f0']) / FPS:.2f}s)")
    return tl


if __name__ == "__main__":
    build()
