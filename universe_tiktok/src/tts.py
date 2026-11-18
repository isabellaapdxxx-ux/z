"""Voiceover: one edge-tts clip per script line, with word-boundary timings.

Raw clips (mp3 + word boundaries) are cached in build/tts/ and only requested
again when the text/voice/rate change. Every run then decodes them to 48 kHz
mono, trims the silence around the speech, tightens over-long pauses inside a
line, and writes build/tts/lineNN.npy plus build/tts/meta.json (measured
length and per-word times relative to the processed clip).
"""
import asyncio
import json
import os
import ssl
import subprocess
import time

import numpy as np

from config import BUILD, LINES, RATE, SR, VOICE, VOICE_FALLBACK

TTS_DIR = BUILD / "tts"
MAX_PAUSE = 0.28  # longest silence kept inside one line (s)


def _patch_ssl():
    """edge-tts pins certifi's CA bundle; honour SSL_CERT_FILE when it is set
    (needed behind TLS-inspecting proxies)."""
    import edge_tts.communicate as ec
    cafile = os.environ.get("SSL_CERT_FILE")
    if cafile and os.path.exists(cafile):
        ec._SSL_CTX = ssl.create_default_context(cafile=cafile)


async def _synth(text, voice, path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary")
    words = []
    with open(path, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"t0": ch["offset"] / 1e7,
                              "t1": (ch["offset"] + ch["duration"]) / 1e7,
                              "text": ch["text"]})
    if not words or os.path.getsize(path) < 1000:
        raise RuntimeError("empty TTS response")
    return words


def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1",
                          "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def _env_db(audio, hop):
    n = len(audio) // hop
    rms = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(rms)


def process(audio, words, pre=0.04, post=0.14):
    """Trim edges, cap inner pauses at MAX_PAUSE. Returns clip, words."""
    hop = SR // 100
    db = _env_db(audio, hop)
    thr = max(-52.0, db.max() - 40.0)
    loud = db > thr
    idx = np.nonzero(loud)[0]
    s = max(0, idx[0] * hop - int(pre * SR))
    e = min(len(audio), (idx[-1] + 1) * hop + int(post * SR))
    # inner silent runs
    cuts = []  # (sample position in original, samples removed)
    run_start = None
    for k in range(idx[0], idx[-1] + 1):
        if not loud[k]:
            run_start = k if run_start is None else run_start
        elif run_start is not None:
            L = (k - run_start) * hop
            if L > MAX_PAUSE * SR:
                remove = L - int(MAX_PAUSE * SR)
                mid = run_start * hop + int(MAX_PAUSE * SR * 0.5)
                cuts.append((mid, remove))
            run_start = None
    xf = int(0.008 * SR)
    pieces, pos = [], s
    for mid, rem in cuts:
        pieces.append(audio[pos:mid])
        pos = mid + rem
    pieces.append(audio[pos:e])
    clip = pieces[0]
    for p in pieces[1:]:
        ramp = np.linspace(0, 1, xf, dtype=np.float32)
        joint = clip[-xf:] * (1 - ramp) + p[:xf] * ramp
        clip = np.concatenate([clip[:-xf], joint, p[xf:]])

    def remap(t):
        n = t * SR
        shift = sum(rem + xf for mid, rem in cuts if mid < n) if cuts else 0
        return max(0.0, (n - s - shift) / SR)

    fade = int(0.012 * SR)
    clip = clip.copy()
    clip[:fade] *= np.linspace(0, 1, fade)
    clip[-fade * 3:] *= np.linspace(1, 0, fade * 3)
    dur = len(clip) / SR
    ws = [{"text": w["text"], "t0": min(dur, remap(w["t0"])), "t1": min(dur, remap(w["t1"]))}
          for w in words]
    return clip, ws


def _fetch_all(voice, fresh):
    _patch_ssl()
    for i, text in enumerate(LINES, 1):
        mp3 = TTS_DIR / f"raw{i:02d}.mp3"
        js = TTS_DIR / f"raw{i:02d}.json"
        if js.exists() and mp3.exists() and not fresh:
            info = json.loads(js.read_text())
            if info["text"] == text and info["voice"] == voice and info["rate"] == RATE:
                continue
        for attempt in range(8):
            try:
                words = asyncio.run(_synth(text, voice, mp3))
                break
            except Exception as exc:  # transient network / service hiccup
                print(f"  tts line {i} ({voice}) attempt {attempt + 1} failed: {exc}")
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"TTS failed for line {i} with {voice}")
        js.write_text(json.dumps({"text": text, "voice": voice, "rate": RATE, "words": words}))
        print(f"  fetched line {i:2d} ({voice})")


def generate(fresh=False):
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    voice = VOICE
    try:
        _fetch_all(VOICE, fresh)
    except RuntimeError as exc:
        print(f"  {exc}; switching every line to {VOICE_FALLBACK}")
        voice = VOICE_FALLBACK
        _fetch_all(VOICE_FALLBACK, fresh)
    meta = {"voice": voice, "lines": []}
    for i, text in enumerate(LINES, 1):
        info = json.loads((TTS_DIR / f"raw{i:02d}.json").read_text())
        clip, ws = process(decode(TTS_DIR / f"raw{i:02d}.mp3"), info["words"])
        np.save(TTS_DIR / f"line{i:02d}.npy", clip)
        meta["lines"].append({"index": i, "text": text, "duration": len(clip) / SR, "words": ws})
    (TTS_DIR / "meta.json").write_text(json.dumps(meta, indent=1))
    print(f"  voice {voice}: speech total {sum(l['duration'] for l in meta['lines']):.2f}s")
    return meta


if __name__ == "__main__":
    import sys
    m = generate(fresh="--fresh" in sys.argv)
    for l in m["lines"]:
        print(l["index"], round(l["duration"], 2), " ".join(f"{w['text']}@{w['t0']:.2f}" for w in l["words"]))
