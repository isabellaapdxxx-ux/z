#!/usr/bin/env python3
"""
make_tiktok_ad.py: a 30.0 s vertical TikTok ad for the iPhone 17 Pro Max,
built entirely in code (Pillow + NumPy + ffmpeg).

FAN-MADE creator-style ad. NOT an official Apple ad. No Apple logo, no Apple
photos/videos, no Apple music: the phone is drawn with Pillow, and the
music and sound effects are synthesized with NumPy.

Pipeline
  1. voiceover   edge-tts -> gTTS -> ffmpeg flite (first one that works)
  2. captions    word timings -> 2-3 word chunks -> burned in + .srt
  3. audio       music (120 BPM, drop at 10 s) + SFX + ducking -> -14 LUFS
  4. previews    busiest frame of each scene -> output/previews/*.png
  5. scenes      each scene -> its own .mp4 (transitions drawn inside)
  6. concat      ffmpeg concat demuxer -> add audio -> output/tiktok_ad.mp4
  7. verify      ffprobe duration == 30.00 s (trim/pad if needed)

Usage
  python make_tiktok_ad.py                 # full build
  python make_tiktok_ad.py --preview-only  # stop after the preview PNGs
  python make_tiktok_ad.py --workers 4     # parallel scene renders
"""

# =============================================================================
# CONFIG: change text, colors, voice and timings here
# =============================================================================
CONFIG = {
    # ---- output ---------------------------------------------------------------
    "out_dir": "output",
    "final_name": "tiktok_ad.mp4",
    "srt_name": "tiktok_ad.srt",
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "duration": 30.0,
    "crf": 18,
    "x264_preset": "medium",

    # ---- TikTok UI safe zone (text must stay inside) -------------------------
    "safe_top": 150,     # nothing in the top 150 px
    "safe_bottom": 400,  # nothing in the bottom 400 px
    "safe_right": 150,   # nothing in the right 150 px
    "safe_left": 40,     # small extra margin on the left
    # text is centred in the safe column, not on the full frame
    # (centre = (safe_left + width - safe_right) / 2 = 485)

    # ---- colors ---------------------------------------------------------------
    "colors": {
        "bg_top": (6, 7, 12),
        "bg_bottom": (2, 2, 5),
        "orange": (255, 122, 26),
        "orange_hot": (255, 160, 60),
        "blue": (40, 120, 255),
        "blue_soft": (90, 160, 255),
        "white": (255, 255, 255),
        "grey": (150, 155, 165),
        "red": (255, 59, 48),
        "caption_fill": (255, 255, 255),
        "caption_active": (255, 122, 26),
        "caption_stroke": (0, 0, 0),
    },
    # phone finishes (body, highlight, plateau): drawn, not photographed
    "phone_colors": {
        "Cosmic Orange": {"body": (226, 104, 40), "hi": (255, 168, 108), "plate": (238, 124, 58), "swatch": (236, 110, 44)},
        "Deep Blue":     {"body": (42, 58, 92),   "hi": (108, 132, 178), "plate": (54, 72, 110),  "swatch": (48, 70, 120)},
        "Silver":        {"body": (200, 202, 206), "hi": (245, 246, 248), "plate": (214, 216, 220), "swatch": (222, 224, 228)},
    },

    # ---- fonts ----------------------------------------------------------------
    # first existing file wins (Montserrat / Poppins Bold / Inter Black)
    "font_black": [
        "fonts/Montserrat-Black.ttf",
        "fonts/Poppins-Bold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Black.otf",
        "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "font_bold": [
        "fonts/Montserrat-Bold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "font_emoji": "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",

    # ---- voice ----------------------------------------------------------------
    "tts_engines": ["edge", "gtts", "flite"],   # tried in this order
    "edge_voice": "en-US-GuyNeural",
    "edge_rate": "+10%",
    "gtts_lang": "en",
    "gtts_tld": "com",
    "flite_voice": "slt",
    "vo_offset": 0.12,          # each line starts this long after its scene starts
    "vo_tail": 0.10,            # each line must end this long before the scene ends
    "vo_max_gap": 0.22,         # longer pauses inside a line are shortened to this
    "vo_max_speedup": 1.35,     # atempo limit when a line is still too long

    # ---- audio mix ------------------------------------------------------------
    "sample_rate": 48000,
    "bpm": 120,
    "drop_time": 10.0,
    "voice_peak_db": -3.0,      # voice normalized to about -3 dBFS peak
    "music_db": -18.0,          # music peak level under the voice (ducked), dBFS
    "music_db_open": -11.0,     # music peak level when nobody is talking, dBFS
    "sfx_db": -7.0,             # SFX peak level
    "target_lufs": -14.0,       # TikTok loudness
    "true_peak_db": -1.5,

    # ---- captions -------------------------------------------------------------
    "caption_y": 1365,          # centre line of the caption block (lower-middle)
    "caption_size": 82,
    "caption_stroke": 9,
    "caption_max_words": 3,
    "caption_max_chars": 16,
    "caption_uppercase": True,

    # ---- end card -------------------------------------------------------------
    "cta_text": "Get yours now – link in bio",
    "trademark_text": "iPhone is a trademark of Apple Inc.",
    "disclaimer_text": "Fan-made ad · not affiliated with Apple",

    # ---- transitions (one per cut, in order) ---------------------------------
    "transition_len": 0.40,     # seconds, centred on each cut (0.3-0.5 s)
    "transitions": ["whip", "flash", "zoom_punch", "glitch", "spin"],
}

# Scenes: 6 x 5 s. "vo" is spoken; "texts" are the animated on-screen titles.
# text anim: "pop" | "bounce" | "slide"   (t = seconds into the scene)
SCENES = [
    {
        "name": "hook",
        "vo": "This phone is UNREAL. Seriously, look at this thing!",
        "texts": [
            {"t": 1.25, "text": "This phone is", "size": 64, "y": 225, "anim": "slide", "color": "white"},
            {"t": 1.55, "text": "UNREAL 🤯", "size": 142, "y": 335, "anim": "bounce", "color": "orange"},
        ],
    },
    {
        "name": "problem",
        "vo": "Tired of your phone dying by noon? Blurry zoom shots? Not anymore.",
        "texts": [
            {"t": 0.30, "text": "Tired of your phone", "size": 64, "y": 225, "anim": "slide", "color": "white", "until": 2.30},
            {"t": 0.50, "text": "dying by noon?", "size": 86, "y": 310, "anim": "bounce", "color": "red", "until": 2.30},
            {"t": 2.40, "text": "Blurry zoom", "size": 86, "y": 235, "anim": "bounce", "color": "white"},
            {"t": 2.60, "text": "shots?", "size": 86, "y": 330, "anim": "slide", "color": "red"},
        ],
    },
    {
        "name": "reveal",
        "vo": "Meet the iPhone 17 Pro Max: new aluminum unibody, vapor chamber cooling.",
        "texts": [
            {"t": 0.25, "text": "MEET", "size": 58, "y": 215, "anim": "pop", "color": "grey"},
            {"t": 0.45, "text": "iPhone 17 Pro Max", "size": 96, "y": 300, "anim": "slide", "color": "white"},
            {"t": 2.45, "text": "Aluminum unibody", "size": 40, "y": 1185, "anim": "pill", "color": "orange"},
            {"t": 2.95, "text": "Vapor chamber cooling", "size": 40, "y": 1250, "anim": "pill", "color": "blue"},
        ],
    },
    {
        "name": "camera",
        "vo": "Three 48MP cameras, up to 8x optical-quality zoom. Every shot, crystal clear.",
        "texts": [
            {"t": 0.25, "text": "TRIPLE 48MP", "size": 104, "y": 225, "anim": "bounce", "color": "white"},
            {"t": 0.55, "text": "PRO CAMERA SYSTEM", "size": 48, "y": 320, "anim": "slide", "color": "blue_soft", "until": 2.85},
            {"t": 2.95, "text": "UP TO 8x ZOOM", "size": 64, "y": 322, "anim": "bounce", "color": "orange"},
        ],
    },
    {
        "name": "power",
        "vo": "A19 Pro chip, insanely fast for gaming. Plus the biggest battery ever in an iPhone.",
        "texts": [
            {"t": 0.25, "text": "A19 PRO CHIP", "size": 100, "y": 225, "anim": "bounce", "color": "white", "until": 2.45},
            {"t": 0.55, "text": "Built for gaming", "size": 52, "y": 318, "anim": "slide", "color": "orange", "until": 2.45},
            {"t": 2.50, "text": "BIGGEST BATTERY", "size": 92, "y": 225, "anim": "bounce", "color": "white"},
            {"t": 2.70, "text": "ever in an iPhone", "size": 52, "y": 318, "anim": "slide", "color": "orange"},
        ],
    },
    {
        "name": "cta",
        "vo": "Cosmic Orange, Deep Blue, or Silver. Get yours now, link in bio!",
        "texts": [
            {"t": 0.30, "text": "Pick your color", "size": 76, "y": 225, "anim": "slide", "color": "white"},
        ],
    },
]
SCENE_LEN = 5.0

# Product-claim notes (checked against Apple's Sept 2025 newsroom/spec pages):
#  A19 Pro chip | three 48MP Fusion cameras, 8x optical-quality zoom (200 mm) |
#  aluminum unibody + laser-welded vapor chamber | Pro Max: largest battery and
#  best battery life ever in an iPhone | Cosmic Orange, Deep Blue, Silver.

# =============================================================================
# end of CONFIG
# =============================================================================

import argparse
import asyncio
import importlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import wave

C = CONFIG
W, H, FPS = C["width"], C["height"], C["fps"]
DUR = C["duration"]
NFRAMES = int(round(DUR * FPS))
SR = C["sample_rate"]
NS = int(round(DUR * SR))
SAFE = (C["safe_left"], C["safe_top"], W - C["safe_right"], H - C["safe_bottom"])  # x0,y0,x1,y1
CX = (SAFE[0] + SAFE[2]) // 2          # text centre column
PHONE_CX = 515                          # visual centre for drawings
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, C["out_dir"])
BUILD = os.path.join(OUT, "build")
PREV = os.path.join(OUT, "previews")


# -----------------------------------------------------------------------------
# setup
# -----------------------------------------------------------------------------
def ensure_packages():
    """Install missing Python packages (Pillow, NumPy, edge-tts, gTTS)."""
    need = {"PIL": "pillow", "numpy": "numpy", "edge_tts": "edge-tts", "gtts": "gTTS"}
    missing = []
    for mod, pkg in need.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[setup] installing {' '.join(missing)}")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=False)
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"[setup] {tool} not found: install ffmpeg first (apt install ffmpeg / brew install ffmpeg)")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_duration(path, stream=None):
    args = ["ffprobe", "-v", "error"]
    if stream:
        args += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        args += ["-show_entries", "format=duration"]
    out = subprocess.run(args + ["-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    return float(out.splitlines()[0]) if out else 0.0


def first_existing(paths):
    for p in paths:
        q = p if os.path.isabs(p) else os.path.join(ROOT, p)
        if os.path.exists(q):
            return q
    raise FileNotFoundError(f"none of these fonts exist: {paths}")


def write_wav(path, x):
    import numpy as np
    x = np.atleast_2d(np.asarray(x, dtype=np.float32))
    if x.shape[0] < x.shape[1]:
        x = x.T
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def read_audio(path):
    """Decode any audio file to mono float32 at SR via ffmpeg."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


# -----------------------------------------------------------------------------
# 1. VOICEOVER
# -----------------------------------------------------------------------------
def tts_edge(text, mp3):
    import edge_tts

    async def go():
        kw = dict(rate=C["edge_rate"], boundary="WordBoundary")
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            kw["proxy"] = proxy
        com = edge_tts.Communicate(text, C["edge_voice"], **kw)
        audio, words = bytearray(), []
        async for ch in com.stream():
            if ch["type"] == "audio":
                audio += ch["data"]
            elif ch["type"] == "WordBoundary":
                words.append({"w": ch["text"], "s": ch["offset"] / 1e7, "e": (ch["offset"] + ch["duration"]) / 1e7})
        return bytes(audio), words

    audio, words = asyncio.run(asyncio.wait_for(go(), 60))
    if not audio:
        raise RuntimeError("edge-tts returned no audio")
    open(mp3, "wb").write(audio)
    return words


def tts_gtts(text, mp3):
    from gtts import gTTS
    gTTS(text=text, lang=C["gtts_lang"], tld=C["gtts_tld"]).save(mp3)
    return None   # no word timings -> estimated


def tts_flite(text, wav):
    safe = text.replace("'", "").replace(":", ",").replace("\\", "")
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"flite=text='{safe}':voice={C['flite_voice']}", wav])
    return None


def estimate_words(text, audio):
    """Spread words over the voiced part of the audio, weighted by length."""
    import numpy as np
    env = np.abs(audio)
    thr = max(env.max() * 0.05, 1e-4)
    idx = np.where(env > thr)[0]
    a, b = (idx[0] / SR, idx[-1] / SR) if len(idx) else (0, len(audio) / SR)
    toks = text.split()
    wts = [len(re.sub(r"\W", "", t)) + 2 + (4 if re.search(r"[.,!?:]$", t) else 0) for t in toks]
    tot, acc, out = sum(wts), 0.0, []
    for t, wt in zip(toks, wts):
        s = a + (b - a) * acc / tot
        acc += wt
        e = a + (b - a) * (acc - (4 if re.search(r"[.,!?:]$", t) else 0)) / tot
        out.append({"w": re.sub(r"[.,!?:]+$", "", t), "s": s, "e": e})
    return out


def attach_punct(text, words):
    """TTS word timings drop punctuation: copy it back from the script text
    (captions break chunks at sentence ends)."""
    toks, ti, rem = text.split(), 0, ""
    for w in words:
        cw = re.sub(r"[^\w]", "", w["w"]).lower()
        if not rem:
            if ti >= len(toks):
                break
            rem = re.sub(r"[^\w]", "", toks[ti]).lower()
            ti += 1
        rem = rem[len(cw):] if (cw and rem.startswith(cw)) else ""
        if not rem:
            pm = re.search(r"[.,!?:;]+$", toks[ti - 1])
            if pm and not re.search(r"[.,!?:;]$", w["w"]):
                w["w"] += pm.group(0)
    return words


def compress_gaps(audio, words, max_gap):
    """Shorten long pauses between words (keeps max_gap of silence)."""
    import numpy as np
    pieces, new_words, t_out, cursor = [], [], 0.0, 0.0
    head = max(0.0, words[0]["s"] - 0.03)
    cursor = head
    for i, w in enumerate(words):
        gap = w["s"] - cursor
        if gap > max_gap and i > 0:
            # keep the first and last max_gap/2 of the pause
            keep = max_gap / 2
            pieces.append(audio[int(cursor * SR):int((cursor + keep) * SR)])
            pieces.append(audio[int((w["s"] - keep) * SR):int(w["s"] * SR)])
            t_out += 2 * keep
        else:
            pieces.append(audio[int(cursor * SR):int(w["s"] * SR)])
            t_out += w["s"] - cursor
        seg = audio[int(w["s"] * SR):int(w["e"] * SR)]
        new_words.append({"w": w["w"], "s": t_out, "e": t_out + len(seg) / SR})
        pieces.append(seg)
        t_out += len(seg) / SR
        cursor = w["e"]
    pieces.append(audio[int(cursor * SR):int((cursor + 0.25) * SR)])
    out = np.concatenate(pieces)
    fade = min(len(out), int(0.01 * SR))
    out[-fade:] *= np.linspace(1, 0, fade)
    return out, new_words


def atempo(audio, factor):
    """Speed up without changing pitch (ffmpeg atempo)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                          "-af", f"atempo={factor:.4f}", "-f", "f32le", "-"],
                         input=audio.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def make_voiceover():
    """Returns (voice track [NS], words [{w,s,e} absolute], engine name)."""
    import numpy as np
    vdir = os.path.join(BUILD, "vo")
    os.makedirs(vdir, exist_ok=True)
    track = np.zeros(NS, np.float32)
    all_words, engine_used = [], None
    for i, sc in enumerate(SCENES):
        text = sc["vo"]
        audio = words = None
        for eng in ([engine_used] if engine_used else C["tts_engines"]):
            try:
                if eng == "edge":
                    f = os.path.join(vdir, f"line{i}.mp3")
                    words = tts_edge(text, f)
                elif eng == "gtts":
                    f = os.path.join(vdir, f"line{i}.mp3")
                    words = tts_gtts(text, f)
                else:
                    f = os.path.join(vdir, f"line{i}.wav")
                    words = tts_flite(text, f)
                audio = read_audio(f)
                engine_used = eng
                break
            except Exception as ex:   # fall through to the next engine
                print(f"[voice] {eng} failed: {type(ex).__name__}: {str(ex)[:120]}")
        if audio is None:
            if engine_used:   # engine stopped working mid-way: retry the whole chain
                engine_used = None
                return make_voiceover()
            sys.exit("[voice] no TTS engine worked")
        if not words:
            words = estimate_words(text, audio)
        words = attach_punct(text, words)
        audio, words = compress_gaps(audio, words, C["vo_max_gap"])
        slot = SCENE_LEN - C["vo_offset"] - C["vo_tail"]
        dur = len(audio) / SR
        if dur > slot:
            f = min(dur / slot, C["vo_max_speedup"])
            audio = atempo(audio, f)
            words = [{"w": w["w"], "s": w["s"] / f, "e": w["e"] / f} for w in words]
            print(f"[voice] line {i + 1}: {dur:.2f}s -> atempo {f:.3f} -> {len(audio) / SR:.2f}s")
        audio = audio[:int(slot * SR)]
        t0 = i * SCENE_LEN + C["vo_offset"]
        a = int(t0 * SR)
        track[a:a + len(audio)] += audio
        for w in words:
            all_words.append({"w": w["w"], "s": round(t0 + w["s"], 3), "e": round(t0 + min(w["e"], slot), 3), "scene": i})
        print(f"[voice] line {i + 1} ({engine_used}): {len(audio) / SR:.2f}s, {len(words)} words @ {t0:.2f}s")
    pk = np.abs(track).max() + 1e-9
    track *= 10 ** (C["voice_peak_db"] / 20) / pk
    nwords = sum(len(s["vo"].split()) for s in SCENES)
    print(f"[voice] engine={engine_used}, script = {nwords} words")
    return track, all_words, engine_used


# -----------------------------------------------------------------------------
# 2. CAPTIONS
# -----------------------------------------------------------------------------
def make_chunks(words):
    """Group words into 2-3 word chunks, breaking at punctuation and scene ends."""
    chunks, cur = [], []

    def flush():
        if cur:
            chunks.append({"words": list(cur), "s": cur[0]["s"], "e": cur[-1]["e"], "scene": cur[0]["scene"]})
            cur.clear()

    for i, w in enumerate(words):
        if cur and (w["scene"] != cur[0]["scene"]):
            flush()
        cur.append(w)
        txt = " ".join(x["w"] for x in cur)
        nxt = words[i + 1] if i + 1 < len(words) else None
        punct = bool(re.search(r"[.,!?:]$", w["w"]))
        too_long = nxt is not None and len(txt) + 1 + len(nxt["w"]) > C["caption_max_chars"]
        if len(cur) >= C["caption_max_words"] or punct or too_long or nxt is None:
            flush()
    # display window: from first word to the next chunk (or +0.35 s), clipped to the scene
    for i, ch in enumerate(chunks):
        scene_end = (ch["scene"] + 1) * SCENE_LEN
        nxt = chunks[i + 1]["s"] if i + 1 < len(chunks) else DUR
        ch["show_s"] = ch["s"]
        ch["show_e"] = min(nxt, ch["e"] + 0.45, scene_end - 0.02)
    return chunks


def caption_word(w):
    w = re.sub(r"[.,:;]+$", "", w)
    return w.upper() if C["caption_uppercase"] else w


def fmt_srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(chunks, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, ch in enumerate(chunks, 1):
            f.write(f"{i}\n{fmt_srt_time(ch['show_s'])} --> {fmt_srt_time(ch['show_e'])}\n")
            f.write(" ".join(re.sub(r"[.,:;]+$", "", w["w"]) for w in ch["words"]) + "\n\n")


# -----------------------------------------------------------------------------
# 3. AUDIO: music, SFX, ducking, loudness
# -----------------------------------------------------------------------------
# Visual events that also drive sounds and camera shake (absolute seconds).
EVENTS = {
    "hook_land": 1.20,                     # phone lands -> glow burst + impact
    "riser": (7.35, 10.0),                 # riser before the reveal
    "drop": 10.0,                          # beat drop / reveal
    "shutters": [18.05, 19.35],            # camera shutter clicks
    "zoom_steps": [16.45, 16.95, 17.45, 17.95],  # viewfinder 1x, then 2x, 4x, 8x
    "powerup": (22.55, 24.35),             # battery bar fills
    "ding": 26.10,                         # CTA button lands
    "shakes": [(1.20, 0.8), (10.0, 1.6), (15.0, 0.6), (20.0, 0.6), (25.0, 0.6), (26.10, 0.5)],
}


def sfx_text_times():
    out = []
    for i, sc in enumerate(SCENES):
        for tx in sc["texts"]:
            out.append(i * SCENE_LEN + tx["t"])
    return out


def _np():
    import numpy as np
    return np


def tv_filter(x, fc, kind="lp", q=1.0, n=2048, hop=512):
    """Time-varying FFT filter (overlap-add). fc: float or callable(t_seconds)->Hz."""
    np = _np()
    pad = np.concatenate([np.zeros(n), x, np.zeros(n)])
    nb = (len(pad) - n) // hop + 1
    win = np.hanning(n).astype(np.float32)
    idx = np.arange(n)[None, :] + hop * np.arange(nb)[:, None]
    frames = pad[idx] * win
    spec = np.fft.rfft(frames, axis=1)
    f = np.fft.rfftfreq(n, 1 / SR)[None, :]
    tc = (np.arange(nb) * hop + n / 2 - n) / SR
    fcv = np.array([fc(t) for t in tc]) if callable(fc) else np.full(nb, float(fc))
    fcv = np.maximum(fcv, 20.0)[:, None]
    r = f / fcv
    if kind == "lp":
        m = 1 / np.sqrt(1 + r ** (4 * q))
    elif kind == "hp":
        m = 1 / np.sqrt(1 + (1 / np.maximum(r, 1e-6)) ** (4 * q))
    else:  # band
        m = np.exp(-0.5 * (np.log2(np.maximum(r, 1e-6)) / (0.55 / q)) ** 2)
    out_frames = np.fft.irfft(spec * m, n=n, axis=1) * win
    out = np.zeros(len(pad))
    for b in range(nb):
        out[b * hop:b * hop + n] += out_frames[b]
    norm = np.zeros(len(pad))
    for b in range(nb):
        norm[b * hop:b * hop + n] += win ** 2
    out /= np.maximum(norm, 1e-3)
    return out[n:n + len(x)].astype(np.float32)


def env_exp(n, decay):
    np = _np()
    return np.exp(-np.arange(n) / (decay * SR)).astype(np.float32)


def add_at(buf, t, sig, gain=1.0):
    a = int(round(t * SR))
    if a >= buf.shape[-1] or a + len(sig) <= 0:
        return
    s0 = max(0, -a)
    a = max(a, 0)
    b = min(buf.shape[-1], a + len(sig) - s0)
    buf[..., a:b] += sig[s0:s0 + (b - a)] * gain


def saw(f, n, phase=0.0):
    np = _np()
    t = np.arange(n) / SR
    return (2 * ((f * t + phase) % 1.0) - 1).astype(np.float32)


def sine(f, n):
    np = _np()
    return np.sin(2 * np.pi * np.cumsum(np.broadcast_to(f, (n,)) / SR)).astype(np.float32)


def kick(n=int(0.45 * 48000)):
    np = _np()
    t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t / 0.035)
    s = sine(f, n) * env_exp(n, 0.16)
    s[:200] += np.random.default_rng(1).normal(0, 0.4, 200) * np.linspace(1, 0, 200)
    return np.tanh(1.6 * s)


def hat(open_=False, rng=None):
    np = _np()
    n = int((0.22 if open_ else 0.05) * SR)
    rng = rng or np.random.default_rng(2)
    s = np.diff(rng.normal(0, 1, n + 1)).astype(np.float32)
    return s * env_exp(n, 0.07 if open_ else 0.012) * 0.35


def clap(rng=None):
    np = _np()
    n = int(0.25 * SR)
    rng = rng or np.random.default_rng(3)
    s = tv_filter(rng.normal(0, 1, n).astype(np.float32), 1400, "band", 0.7)
    e = env_exp(n, 0.06)
    for k in (0.0, 0.011, 0.022):     # three tiny hits = clap
        e[int(k * SR):int(k * SR) + 120] += 0.6
    return s * e * 0.9


CHORDS = [  # Am, F, C, G (one per bar = 2 s at 120 BPM)
    (55.00, [220.00, 261.63, 329.63]),
    (43.65, [174.61, 220.00, 261.63]),
    (65.41, [261.63, 329.63, 392.00]),
    (49.00, [196.00, 246.94, 293.66]),
]


def make_music():
    """Original 120 BPM techy beat: intro -> tension -> riser -> DROP at 10 s."""
    np = _np()
    rng = np.random.default_rng(7)
    beat = 60.0 / C["bpm"]
    bar = 4 * beat
    drop = C["drop_time"]
    drums = np.zeros(NS, np.float32)
    bass = np.zeros(NS, np.float32)
    synth = np.zeros(NS, np.float32)
    pad = np.zeros(NS, np.float32)
    K, CL = kick(), clap()

    nbeats = int(DUR / beat)
    for b in range(nbeats):
        t = b * beat
        intro = t < 5.0
        tension = 5.0 <= t < drop
        if intro:
            add_at(drums, t, K, 0.75)
        elif tension:
            if t >= 7.5 and b % 2 == 0:
                add_at(drums, t, K, 0.5)
        else:
            add_at(drums, t, K, 1.0)
            if b % 2 == 1:
                add_at(drums, t, CL, 0.8)
        # hats: 8ths (16ths after the drop)
        steps = 4 if t >= drop else 2
        for k in range(steps):
            tt = t + k * beat / steps
            open_ = (t >= drop and k == steps // 2)
            g = 0.55 if (k % 2 == 0) else 0.35
            if tension and tt < 7.5:
                g *= 0.6
            add_at(drums, tt, hat(open_, rng), g)
    # snare roll into the drop (accelerating)
    t = 8.0
    while t < drop - 0.02:
        frac = (t - 8.0) / 2.0
        add_at(drums, t, CL[:int(0.12 * SR)], 0.25 + 0.6 * frac)
        t += beat / (2 if frac < 0.5 else 4 if frac < 0.8 else 8)
    # end hit
    add_at(drums, 29.5, K, 1.0)

    # bass + arp + pad
    for bi in range(int(math.ceil(DUR / bar))):
        t0 = bi * bar
        root, notes = CHORDS[bi % 4]
        # pad (whole bar)
        n = int(bar * SR) + int(0.3 * SR)
        p = sum(saw(f * d, n, rng.random()) for f in notes for d in (0.997, 1.003)) / 6
        e = np.minimum(1, np.arange(n) / (0.25 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.3 * SR))
        add_at(pad, t0, p * e, 1.0)
        # arp 16ths
        seq = notes + [notes[0] * 2, notes[1] * 2, notes[2], notes[1], notes[0] * 2]
        for k in range(16):
            tt = t0 + k * beat / 4
            f = seq[k % len(seq)] * 2
            nn = int(0.22 * SR)
            s = (saw(f, nn) * 0.6 + np.sign(sine(f * 1.001, nn)) * 0.4) * env_exp(nn, 0.07)
            add_at(synth, tt, s, 0.9 if k % 4 == 0 else 0.6)
        # bass
        if t0 + bar <= drop:
            if t0 < 5.0:
                nn = int(bar * SR)
                s = sine(root * 2, nn) * np.minimum(1, (nn - np.arange(nn)) / (0.1 * SR))
                add_at(bass, t0, s, 0.5)
        else:
            for k in range(8):
                tt = t0 + k * beat / 2
                if tt < drop:
                    continue
                f = root * (2 if k % 2 else 1) * 2
                nn = int(beat / 2 * SR)
                s = (saw(f, nn) * 0.7 + sine(f / 2, nn) * 0.8) * np.minimum(1, (nn - np.arange(nn)) / (0.03 * SR))
                add_at(bass, tt, s * env_exp(nn, 0.3), 0.9)

    tt = np.arange(NS) / SR
    # filter automation: everything muffled during the tension, opens with the riser
    def cut_synth(t):
        if t < 5.0:
            return 2600
        if t < 7.4:
            return 700
        if t < drop:
            return 700 * (6000 / 700) ** ((t - 7.4) / (drop - 7.4))
        return 5500
    synth = tv_filter(synth, cut_synth, "lp", 1.0)
    pad = tv_filter(pad, lambda t: 1600 if t < 5 else 650 if t < drop else 1200, "lp")
    bass = tv_filter(bass, 900, "lp")

    # sidechain pump from the kick after the drop
    ph = (tt % beat) / beat
    pump = np.where(tt >= drop, 0.45 + 0.55 * np.minimum(1, ph / 0.35), 1.0).astype(np.float32)
    pad_g = np.where(tt < drop, 0.9, 0.45).astype(np.float32)
    music = drums * 0.9 + bass * pump * 0.8 + synth * pump * 0.38 + pad * pump * pad_g * 0.35
    # tension: duck drums/synth a bit; small gap right before the drop
    gap = (tt > drop - 0.12) & (tt < drop)
    music[gap] *= np.linspace(1, 0.1, gap.sum())
    # fade the last 0.35 s so the ad ends clean
    fo = int(0.35 * SR)
    music[-fo:] *= np.linspace(1, 0, fo) ** 2
    return music.astype(np.float32)


# ---- sound effects -----------------------------------------------------------
def sfx_whoosh(d=0.45, seed=0):
    np = _np()
    n = int(d * SR)
    x = np.random.default_rng(seed).normal(0, 1, n).astype(np.float32)
    x = tv_filter(x, lambda t: 300 * (12 ** min(1, max(0, t / d))), "band", 0.6)
    pos = np.arange(n) / n
    e = np.where(pos < 0.75, (pos / 0.75) ** 2.2, ((1 - pos) / 0.25) ** 1.5)
    return x * e


def sfx_pop():
    np = _np()
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    s = sine(380 + 900 * np.exp(-t / 0.018), n) * env_exp(n, 0.035)
    s[:60] += np.random.default_rng(4).normal(0, 0.3, 60)
    return s


def sfx_riser(d):
    np = _np()
    n = int(d * SR)
    t = np.arange(n) / SR
    noise = tv_filter(np.random.default_rng(5).normal(0, 1, n).astype(np.float32),
                      lambda tt: 400 * (20 ** min(1, max(0, tt / d))), "hp", 1.0)
    f = 180 * (10 ** (t / d)) * (1 + 0.01 * np.sin(2 * np.pi * 6 * t))
    tone = (sine(f, n) + 0.5 * sine(f * 1.5, n))
    e = (t / d) ** 2.5
    return (noise * 0.6 + tone * 0.35) * e


def sfx_impact():
    np = _np()
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    boom = sine(32 + 60 * np.exp(-t / 0.08), n) * env_exp(n, 0.45)
    crack = tv_filter(np.random.default_rng(6).normal(0, 1, n).astype(np.float32), 2500, "lp") * env_exp(n, 0.12)
    return np.tanh(1.5 * (boom + 0.5 * crack))


def sfx_shutter():
    np = _np()
    n = int(0.16 * SR)
    rng = np.random.default_rng(8)
    s = np.zeros(n, np.float32)
    for k, g in ((0.0, 1.0), (0.065, 0.8)):
        m = int(0.025 * SR)
        c = tv_filter(rng.normal(0, 1, m).astype(np.float32), 3500, "band", 0.8) * env_exp(m, 0.004)
        c += sine(1800, m) * env_exp(m, 0.002) * 0.4
        add_at(s, k, c, g)
    return s


def sfx_tick():
    np = _np()
    n = int(0.05 * SR)
    return sine(2400, n) * env_exp(n, 0.008)


def sfx_powerup(d):
    np = _np()
    n = int(d * SR)
    t = np.arange(n) / SR
    f = 140 * (7 ** (t / d))
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * np.cumsum(10 + 22 * t / d) / SR)
    s = (sine(f, n) * 0.6 + np.sign(sine(f * 2, n)) * 0.15) * trem * np.minimum(1, t / 0.05)
    s = tv_filter(s, lambda tt: 800 + 4000 * tt / d, "lp")
    m = int(0.9 * SR)
    chime = sum(sine(fq, m) * env_exp(m, 0.25) / (k + 1) for k, fq in enumerate((1046.5, 1568.0, 2093.0)))
    out = np.zeros(n + m, np.float32)
    out[:n] += s
    out[n - int(0.02 * SR):n - int(0.02 * SR) + m] += chime * 0.6
    return out


def sfx_ding():
    np = _np()
    n = int(1.6 * SR)
    f0 = 1318.5
    s = sum(sine(f0 * r, n) * env_exp(n, dcy) * g
            for r, dcy, g in ((1, 0.6, 1), (2.0, 0.35, 0.5), (2.76, 0.25, 0.35), (5.4, 0.1, 0.2)))
    return s * np.minimum(1, np.arange(n) / 40)


def norm_peak(x, db):
    np = _np()
    return x * (10 ** (db / 20) / (np.abs(x).max() + 1e-9))


def make_sfx():
    """Returns stereo SFX bed (2, NS)."""
    np = _np()
    L = np.zeros(NS, np.float32)
    R = np.zeros(NS, np.float32)
    db = C["sfx_db"]

    def put(t, sig, gdb=0.0, pan=0.0):
        sig = norm_peak(sig, db + gdb)
        add_at(L, t, sig, math.cos((pan + 1) * math.pi / 4) * math.sqrt(2))
        add_at(R, t, sig, math.sin((pan + 1) * math.pi / 4) * math.sqrt(2))

    # whoosh on every transition (peaks at the cut), panned the way the cut moves
    for k in range(1, len(SCENES)):
        w = sfx_whoosh(0.5, seed=k)
        cut = k * SCENE_LEN
        half = int(len(w) * 0.75)
        put(cut - half / SR, w[:half], -1.0, -0.4)
        put(cut, w[half:], -1.0, 0.4)
    for t in sfx_text_times():          # pop on every text
        put(t, sfx_pop(), -6.0)
    put(EVENTS["hook_land"], sfx_impact(), -3.0)
    a, b = EVENTS["riser"]
    put(a, sfx_riser(b - a), -2.0)
    put(EVENTS["drop"], sfx_impact(), 0.0)
    for t in EVENTS["zoom_steps"]:
        put(t, sfx_tick(), -10.0)
    for t in EVENTS["shutters"]:
        put(t, sfx_shutter(), -1.0)
    a, b = EVENTS["powerup"]
    put(a, sfx_powerup(b - a), -3.0)
    put(EVENTS["ding"], sfx_ding(), -2.0)
    return np.stack([L, R])


def ebur128(path):
    """Integrated loudness (LUFS) and true peak (dBTP) measured by ffmpeg."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    i_ = float(re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summ).group(1))
    m = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ)
    return i_, float(m.group(1)) if m else 0.0


def limiter(x, ceil_db, block=128):
    """Look-ahead peak limiter (stereo-linked), NumPy only."""
    np = _np()
    ceil = 10 ** (ceil_db / 20)
    peak = np.abs(x).max(axis=0)
    nb = int(math.ceil(len(peak) / block))
    pk = np.pad(peak, (0, nb * block - len(peak))).reshape(nb, block).max(axis=1)
    g = np.minimum(1.0, ceil / np.maximum(pk, 1e-9))
    gd = g.copy()
    for s in (-2, -1, 1, 2):            # dilate the gain dips (look-ahead + hold)
        gd = np.minimum(gd, np.roll(g, s))
    gs = np.repeat(gd, block)[:len(peak)]
    k = np.ones(block * 2) / (block * 2)
    gs = np.convolve(gs, k, mode="same")
    y = x * gs[None, :]
    return np.clip(y, -ceil, ceil)


def make_audio(voice):
    """Music + SFX + voice, ducked, loudness-normalized. Writes build/mix.wav."""
    np = _np()
    print("[audio] synthesizing music + SFX ...")
    music = make_music()
    sfx = make_sfx()
    # --- music level and ducking under the voice --------------------------------
    rms = lambda s: math.sqrt(float(np.mean(s.astype(np.float64) ** 2)) + 1e-12)
    music *= 10 ** (C["music_db_open"] / 20) / (np.abs(music[int(10 * SR):]).max() + 1e-9)
    hop = int(0.01 * SR)
    v = np.abs(voice)
    nv = len(v) // hop
    ve = v[:nv * hop].reshape(nv, hop).max(axis=1)
    active = (ve > 10 ** (-38 / 20)).astype(np.float32)
    # hold 0.25 s, then smooth (attack ~60 ms, release ~300 ms)
    hold = np.convolve(active, np.ones(25), mode="full")[:nv] > 0
    act = hold.astype(np.float32)
    sm = np.zeros_like(act)
    a_up, a_dn = 1 - math.exp(-1 / 6), 1 - math.exp(-1 / 30)
    for i in range(1, nv):
        c = a_up if act[i] > sm[i - 1] else a_dn
        sm[i] = sm[i - 1] + c * (act[i] - sm[i - 1])
    duck_db = (C["music_db"] - C["music_db_open"]) * sm
    duck = np.repeat(10 ** (duck_db / 20), hop)
    duck = np.pad(duck, (0, NS - len(duck)), constant_values=duck[-1])
    music *= duck
    # --- stereo mix ---------------------------------------------------------------
    d = int(0.012 * SR)       # a little width on the music
    mL = music
    mR = np.concatenate([np.zeros(d, np.float32), music[:-d]]) * 0.6 + music * 0.4
    for name, stem in (("voice", voice), ("music", music), ("sfx", sfx)):
        write_wav(os.path.join(BUILD, f"stem_{name}.wav"), stem)      # stems, for checking/remixing
    mix = np.stack([mL + voice, mR + voice]) + sfx
    mix = limiter(mix, -1.0)
    raw = os.path.join(BUILD, "mix_raw.wav")
    write_wav(raw, mix)
    # --- loudness: measure with ffmpeg EBU R128, gain + limiter, repeat ----------
    out = os.path.join(BUILD, "mix.wav")
    cur = mix
    for it in range(4):
        write_wav(out, cur)
        lufs, tp = ebur128(out)
        print(f"[audio] pass {it + 1}: {lufs:.2f} LUFS, true peak {tp:.2f} dBTP")
        if abs(lufs - C["target_lufs"]) < 0.3 and tp <= C["true_peak_db"] + 0.3:
            break
        cur = limiter(cur * 10 ** ((C["target_lufs"] - lufs) / 20), C["true_peak_db"] - 0.6)
    # voice/music level report
    v_pk = 20 * math.log10(np.abs(voice).max() + 1e-9)
    print(f"[audio] pre-norm levels: voice peak {v_pk:.1f} dBFS, voice RMS {20 * math.log10(rms(voice[np.abs(voice) > 1e-3]) + 1e-9):.1f} dBFS; "
          f"music peak {C['music_db_open']:.0f} dBFS open / {C['music_db']:.0f} dBFS under the voice")
    return out


# -----------------------------------------------------------------------------
# 4. GRAPHICS CORE (Pillow + NumPy)
# -----------------------------------------------------------------------------
from functools import lru_cache

_CACHE = {}
SAFE_REPORT = []          # (scene, text, bbox) for anything outside the safe zone


def P():
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
    return Image, ImageDraw, ImageFilter, ImageFont, ImageChops


def col(name_or_rgb):
    return C["colors"][name_or_rgb] if isinstance(name_or_rgb, str) else tuple(name_or_rgb)


@lru_cache(maxsize=64)
def font(kind, size):
    _, _, _, ImageFont, _ = P()
    if kind == "emoji":
        return ImageFont.truetype(C["font_emoji"], 109)    # CBDT emoji font: fixed size
    return ImageFont.truetype(first_existing(C["font_black"] if kind == "black" else C["font_bold"]), size)


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out_cubic(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_out_back(x, s=1.9):
    x = clamp01(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def spring(x, freq=3.2, damp=5.5):
    """0 -> 1 with a decaying overshoot (scale bounce)."""
    if x <= 0:
        return 0.0
    return 1 - math.exp(-damp * x) * math.cos(2 * math.pi * freq * x)


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF


def text_sprite(text, size, fill, stroke=0, stroke_fill=(0, 0, 0), glow=None, kind="black"):
    """RGBA sprite of a text line (emoji supported), with optional outline + glow."""
    key = ("txt", text, size, tuple(fill), stroke, tuple(stroke_fill), glow, kind)
    if key in _CACHE:
        return _CACHE[key]
    Image, ImageDraw, ImageFilter, _, _ = P()
    f = font(kind, size)
    runs, cur = [], ""
    for ch in text:
        if is_emoji(ch) or ch == "️":
            if cur:
                runs.append(("t", cur))
                cur = ""
            if ch != "️":
                runs.append(("e", ch))
        else:
            cur += ch
    if cur:
        runs.append(("t", cur))
    asc, desc = f.getmetrics()
    lh = asc + desc
    pieces, total_w = [], 0
    for kind_, s in runs:
        if kind_ == "t":
            l, t, r, b = f.getbbox(s, stroke_width=stroke)
            im = Image.new("RGBA", (r - l + 2, lh + 2 * stroke), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((-l + 1, stroke), s, font=f, fill=tuple(fill) + (255,),
                                    stroke_width=stroke, stroke_fill=tuple(stroke_fill) + (255,))
            pieces.append(im)
        else:
            ef = font("emoji", 0)
            em = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(em).text((8, 8), s, font=ef, embedded_color=True)
            em = em.crop(em.getbbox())
            sz = int(size * 0.95)
            em = em.resize((int(em.width * sz / em.height), sz), Image.LANCZOS)
            im = Image.new("RGBA", (em.width + int(size * 0.08), lh + 2 * stroke), (0, 0, 0, 0))
            im.alpha_composite(em, (int(size * 0.04), stroke + int(asc - sz * 0.88)))
            pieces.append(im)
        total_w += pieces[-1].width
    hgt = max(p.height for p in pieces)
    out = Image.new("RGBA", (total_w, hgt), (0, 0, 0, 0))
    x = 0
    for p in pieces:
        out.alpha_composite(p, (x, 0))
        x += p.width
    out = out.crop(out.getbbox())
    if glow:
        pad = int(size * 0.45)
        g = Image.new("RGBA", (out.width + 2 * pad, out.height + 2 * pad), (0, 0, 0, 0))
        a = out.getchannel("A").point(lambda v: int(v * 0.85))
        tint = Image.new("RGBA", out.size, col(glow) + (255,))
        tint.putalpha(a)
        g.alpha_composite(tint, (pad, pad))
        g = g.filter(ImageFilter.GaussianBlur(size * 0.18))
        g.alpha_composite(out, (pad, pad))
        out = g
        out.info["pad"] = pad
    _CACHE[key] = out
    return out


def scaled(sprite, s):
    Image = P()[0]
    if abs(s - 1) < 1e-3:
        return sprite
    w, h = max(1, int(sprite.width * s)), max(1, int(sprite.height * s))
    return sprite.resize((w, h), Image.BILINEAR)


def with_alpha(sprite, a):
    if a >= 0.999:
        return sprite
    s = sprite.copy()
    s.putalpha(s.getchannel("A").point(lambda v: int(v * a)))
    return s


def paste(canvas, sprite, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    """Alpha-composite `sprite` centred at (cx, cy)."""
    Image = P()[0]
    if alpha <= 0.003 or scale <= 0.01:
        return
    s = scaled(sprite, scale)
    if angle:
        s = s.rotate(angle, resample=Image.BICUBIC, expand=True)
    s = with_alpha(s, alpha)
    x, y = int(round(cx - s.width / 2)), int(round(cy - s.height / 2))
    # clip to canvas
    l, t = max(0, -x), max(0, -y)
    r, b = min(s.width, W - x), min(s.height, H - y)
    if r <= l or b <= t:
        return
    if (l, t, r, b) != (0, 0, s.width, s.height):
        s = s.crop((l, t, r, b))
    if canvas.mode == "RGBA":
        canvas.alpha_composite(s, (x + l, y + t))
    else:
        canvas.paste(s, (x + l, y + t), s)


# ---- light (additive) -----------------------------------------------------------
def radial_light(radius, color, falloff=2.2):
    """float32 RGB array of a soft round light (additive)."""
    np = _np()
    radius = max(4, int(radius))
    key = ("rad", radius, tuple(color), falloff)
    if key in _CACHE:
        return _CACHE[key]
    y, x = np.mgrid[-radius:radius, -radius:radius].astype(np.float32) + 0.5
    d = np.sqrt(x * x + y * y) / radius
    a = np.clip(1 - d, 0, 1) ** falloff
    arr = a[..., None] * np.array(color, np.float32)[None, None, :]
    _CACHE[key] = arr
    return arr


def rrect_light(w, h, r, spread, color, falloff=1.8):
    """Glow around a rounded rectangle (w x h, corner r), `spread` px wide."""
    np = _np()
    key = ("rrl", w, h, r, spread, tuple(color), falloff)
    if key in _CACHE:
        return _CACHE[key]
    hw, hh = w / 2 + spread, h / 2 + spread
    ys, xs = np.mgrid[-hh:hh:2, -hw:hw:2].astype(np.float32)       # half-res
    qx = np.abs(xs) - (w / 2 - r)
    qy = np.abs(ys) - (h / 2 - r)
    dist = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - r
    a = np.clip(1 - np.maximum(dist, 0) / spread, 0, 1) ** falloff
    arr = a[..., None] * np.array(color, np.float32)[None, None, :]
    arr = arr.repeat(2, 0).repeat(2, 1)
    _CACHE[key] = arr
    return arr


def add_light(canvas, light, cx, cy, gain=1.0):
    """Additively blend a float RGB light array into the RGBA canvas."""
    np = _np()
    Image = P()[0]
    if gain <= 0.003:
        return
    lh, lw = light.shape[:2]
    x0, y0 = int(cx - lw / 2), int(cy - lh / 2)
    l, t = max(0, x0), max(0, y0)
    r, b = min(W, x0 + lw), min(H, y0 + lh)
    if r <= l or b <= t:
        return
    reg = np.asarray(canvas.crop((l, t, r, b))).astype(np.float32)
    add = light[t - y0:b - y0, l - x0:r - x0] * gain
    reg[..., :3] = reg[..., :3] + add
    if canvas.mode == "RGBA":
        reg[..., 3] = np.maximum(reg[..., 3], np.minimum(255, add.max(axis=2) * 3))
    canvas.paste(Image.fromarray(np.clip(reg, 0, 255).astype(np.uint8), canvas.mode), (l, t))


# ---- background ---------------------------------------------------------------------
MOODS = {   # (orange gain, blue gain, red gain, base brightness)
    "hook": (1.0, 0.9, 0.0, 1.0),
    "problem": (0.15, 0.6, 0.35, 0.75),
    "reveal": (1.35, 0.55, 0.0, 1.0),
    "camera": (0.45, 1.25, 0.0, 1.0),
    "power": (1.0, 1.0, 0.0, 1.0),
    "cta": (1.1, 0.9, 0.0, 1.0),
}


def background(mood, t, energy=1.0):
    """Dark gradient + two drifting orange/blue glows + faint grid + particles."""
    np = _np()
    Image, ImageDraw, *_ = P()
    og, bg, rg, base = MOODS[mood]
    sw, sh = 135, 240
    y, x = np.mgrid[0:sh, 0:sw].astype(np.float32)
    y /= sh
    x /= sw
    top, bot = np.array(col("bg_top"), np.float32), np.array(col("bg_bottom"), np.float32)
    img = (top[None, None] * (1 - y[..., None]) + bot[None, None] * y[..., None]) * base

    def blob(cx, cy, rx, ry, color, g):
        d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
        return np.exp(-d)[..., None] * np.array(color, np.float32)[None, None] * g

    img += blob(0.15 + 0.08 * math.sin(t * 0.7), 0.30 + 0.05 * math.cos(t * 0.5), 0.55, 0.30, col("orange"), 0.30 * og * energy)
    img += blob(0.90 + 0.06 * math.cos(t * 0.6), 0.70 + 0.05 * math.sin(t * 0.8), 0.55, 0.32, col("blue"), 0.32 * bg * energy)
    if rg:
        img += blob(0.5, 0.45, 0.6, 0.35, col("red"), 0.18 * rg * (0.7 + 0.3 * math.sin(t * 6)))
    # vignette
    v = 1 - 0.55 * (((x - 0.5) * 1.6) ** 2 + ((y - 0.5) * 1.2) ** 2)
    img *= np.clip(v, 0.25, 1)[..., None]
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").resize((W, H), Image.BICUBIC)
    # faint perspective grid at the bottom (tech vibe)
    d = ImageDraw.Draw(im, "RGBA")
    hz = 1240
    for i in range(-8, 9):
        d.line([(W / 2 + i * 40, hz), (W / 2 + i * 260, H)], fill=(80, 110, 160, 13), width=2)
    for k in range(9):
        yy = hz + (H - hz) * ((k + (t * 0.8) % 1) / 9) ** 1.8
        d.line([(0, yy), (W, yy)], fill=(80, 110, 160, int(5 + 12 * (yy - hz) / (H - hz))), width=2)
    # drifting particles
    rng = random.Random(11)
    for i in range(46):
        px = (rng.random() * W + t * 18 * (rng.random() - 0.5)) % W
        py = (rng.random() * H - t * (20 + 50 * rng.random())) % H
        r = 1 + rng.random() * 2.4
        c = col("orange") if i % 3 == 0 else col("blue_soft")
        a = int(60 + 120 * rng.random() * (0.6 + 0.4 * math.sin(t * 2 + i)))
        d.ellipse([px - r, py - r, px + r, py + r], fill=c + (a,))
    return im


# ---- the phone (drawn, stylized) ------------------------------------------------------
PHONE_RATIO = 0.477      # width / height


def _metal(w, h, rgb, hi, angle_shift=0.0):
    """Brushed-metal shading as an RGB numpy array."""
    np = _np()
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    shade = 0.82 + 0.18 * np.cos((x - 0.28 - angle_shift) * 2.6) - 0.10 * y
    sheen = np.exp(-((x * 0.9 + y * 0.35 - 0.42 - angle_shift) / 0.10) ** 2) * 0.22
    base = np.array(rgb, np.float32)[None, None]
    hil = np.array(hi, np.float32)[None, None]
    out = base * shade[..., None] + (hil - base) * sheen[..., None]
    return np.clip(out, 0, 255)


def _lens(d, im, cx, cy, s):
    """One camera lens: metal ring, black barrel, glassy element, reflections."""
    _, ImageDraw, *_ = P()
    dr = ImageDraw.Draw(im, "RGBA")
    R = d / 2
    dr.ellipse([cx - R - 3 * s, cy - R - 3 * s, cx + R + 3 * s, cy + R + 3 * s], fill=(10, 10, 12, 140))
    for k in range(8):   # graded ring
        f = k / 7
        c = int(70 + 80 * (1 - f))
        rr = R * (1 - 0.02 * k)
        dr.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(c, c, c + 6, 255))
    dr.ellipse([cx - R * 0.84, cy - R * 0.84, cx + R * 0.84, cy + R * 0.84], fill=(8, 8, 10, 255))
    dr.ellipse([cx - R * 0.66, cy - R * 0.66, cx + R * 0.66, cy + R * 0.66], fill=(18, 20, 30, 255))
    dr.ellipse([cx - R * 0.46, cy - R * 0.46, cx + R * 0.46, cy + R * 0.46], fill=(12, 16, 34, 255))
    dr.ellipse([cx - R * 0.30, cy - R * 0.30, cx + R * 0.30, cy + R * 0.30], fill=(30, 34, 80, 255))
    dr.ellipse([cx - R * 0.14, cy - R * 0.14, cx + R * 0.14, cy + R * 0.14], fill=(6, 6, 12, 255))
    # reflections
    dr.arc([cx - R * 0.6, cy - R * 0.6, cx + R * 0.6, cy + R * 0.6], 200, 260, fill=(170, 190, 255, 170), width=max(2, int(R * 0.06)))
    dr.ellipse([cx - R * 0.32, cy - R * 0.38, cx - R * 0.16, cy - R * 0.22], fill=(255, 255, 255, 200))
    dr.ellipse([cx + R * 0.14, cy + R * 0.10, cx + R * 0.30, cy + R * 0.26], fill=(150, 90, 255, 120))


def phone_face(color_name, side="back", h=1000):
    """High-quality RGBA sprite of the phone face (back with camera plateau, or front)."""
    key = ("phone", color_name, side, h)
    if key in _CACHE:
        return _CACHE[key]
    np = _np()
    Image, ImageDraw, ImageFilter, *_ = P()
    ss = 2 if h <= 1400 else 1               # supersample small sprites
    Hh = h * ss
    Ww = int(round(Hh * PHONE_RATIO))
    s = Ww / 500.0
    pc = C["phone_colors"][color_name]
    R = int(Ww * 0.165)
    mask = Image.new("L", (Ww, Hh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, Ww - 1, Hh - 1], R, fill=255)
    if side == "back":
        body = Image.fromarray(_metal(Ww, Hh, pc["body"], pc["hi"]).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(body, "RGBA")
        # lower glass panel (subtle)
        m = int(0.05 * Ww)
        d.rounded_rectangle([m, int(Hh * 0.335), Ww - m, Hh - m], int(R * 0.75),
                            fill=tuple(int(c * 0.97) for c in pc["body"]) + (60,))
        # full-width camera plateau
        pm = int(0.028 * Ww)
        pt, pb = int(0.026 * Hh), int(0.300 * Hh)
        sh = Image.new("RGBA", (Ww, Hh), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([pm, pt + 10 * s, Ww - pm, pb + 16 * s], int(R * 0.85), fill=(0, 0, 0, 120))
        sh = sh.filter(ImageFilter.GaussianBlur(10 * s))
        body.paste(sh, (0, 0), sh)
        plate = Image.fromarray(_metal(Ww - 2 * pm, pb - pt, pc["plate"], pc["hi"], 0.1).astype(np.uint8), "RGB").convert("RGBA")
        pmask = Image.new("L", plate.size, 0)
        ImageDraw.Draw(pmask).rounded_rectangle([0, 0, plate.width - 1, plate.height - 1], int(R * 0.85), fill=255)
        plate.putalpha(pmask)
        body.paste(plate, (pm, pt), plate)
        d = ImageDraw.Draw(body, "RGBA")
        d.rounded_rectangle([pm, pt, Ww - pm, pb], int(R * 0.85), outline=tuple(pc["hi"]) + (150,), width=max(2, int(3 * s)))
        # lenses (triangle) + flash + LiDAR + mic
        ld = 0.300 * Ww
        _lens(ld, body, 0.235 * Ww, pt + 0.255 * (pb - pt), s)
        _lens(ld, body, 0.235 * Ww, pt + 0.745 * (pb - pt), s)
        _lens(ld, body, 0.555 * Ww, pt + 0.500 * (pb - pt), s)
        fx, fy, fr = 0.80 * Ww, pt + 0.25 * (pb - pt), 0.050 * Ww
        d.ellipse([fx - fr, fy - fr, fx + fr, fy + fr], fill=(250, 236, 200, 255), outline=(120, 120, 120, 255), width=max(1, int(2 * s)))
        d.ellipse([fx - fr * 0.5, fy - fr * 0.5, fx + fr * 0.5, fy + fr * 0.5], fill=(255, 250, 230, 255))
        lx, ly, lr = 0.80 * Ww, pt + 0.75 * (pb - pt), 0.045 * Ww
        d.ellipse([lx - lr, ly - lr, lx + lr, ly + lr], fill=(12, 12, 14, 255))
        d.ellipse([lx - lr * 0.4, ly - lr * 0.4, lx - lr * 0.1, ly - lr * 0.1], fill=(80, 80, 90, 255))
        mx, my = 0.80 * Ww, pt + 0.5 * (pb - pt)
        d.ellipse([mx - 4 * s, my - 4 * s, mx + 4 * s, my + 4 * s], fill=(20, 20, 20, 255))
    else:
        body = Image.new("RGB", (Ww, Hh), tuple(pc["body"]))
        d = ImageDraw.Draw(body, "RGBA")
        rim = int(0.022 * Ww)
        d.rounded_rectangle([rim, rim, Ww - rim, Hh - rim], R - rim, fill=(4, 4, 6, 255))
        b = int(0.045 * Ww)
        sw_, sh_ = Ww - 2 * b, Hh - 2 * b
        yy, xx = np.mgrid[0:sh_:4, 0:sw_:4].astype(np.float32)
        xx /= sw_
        yy /= sh_
        scr = (np.exp(-(((xx - 0.2) / 0.5) ** 2 + ((yy - 0.25) / 0.35) ** 2))[..., None] * np.array(col("orange"), np.float32)
               + np.exp(-(((xx - 0.85) / 0.55) ** 2 + ((yy - 0.8) / 0.4) ** 2))[..., None] * np.array(col("blue"), np.float32))
        scr = np.clip(scr + 8, 0, 255).astype(np.uint8)
        screen = Image.fromarray(scr, "RGB").resize((sw_, sh_), Image.BICUBIC).convert("RGBA")
        smask = Image.new("L", (sw_, sh_), 0)
        ImageDraw.Draw(smask).rounded_rectangle([0, 0, sw_ - 1, sh_ - 1], R - b, fill=255)
        screen.putalpha(smask)
        body.paste(screen, (b, b), screen)
        d = ImageDraw.Draw(body, "RGBA")
        iw, ih = 0.28 * Ww, 0.036 * Ww * 2.1
        d.rounded_rectangle([Ww / 2 - iw / 2, b + 0.022 * Hh, Ww / 2 + iw / 2, b + 0.022 * Hh + ih], ih / 2, fill=(0, 0, 0, 255))
    # rim light + edge darkening
    d = ImageDraw.Draw(body, "RGBA")
    d.rounded_rectangle([1, 1, Ww - 2, Hh - 2], R, outline=tuple(pc["hi"]) + (200,), width=max(2, int(4 * s)))
    d.rounded_rectangle([5 * s, 5 * s, Ww - 5 * s, Hh - 5 * s], R - 4 * s, outline=(0, 0, 0, 70), width=max(1, int(3 * s)))
    body.putalpha(mask)
    if ss > 1:
        body = body.resize((Ww // ss, Hh // ss), Image.LANCZOS)
    _CACHE[key] = body
    return body


def phone_view(color_name, theta=0.0, height=800, base_h=1000):
    """Phone turned by `theta` around the vertical axis (radians), at `height` px.
    Shows the back when cos(theta) > 0, the front otherwise, plus the side edge."""
    np = _np()
    Image, ImageDraw, *_ = P()
    c, sn = math.cos(theta), math.sin(theta)
    side = "back" if c >= 0 else "front"
    face = phone_face(color_name, side, base_h)
    k = height / face.height
    fw = max(2, int(face.width * k * abs(c)))
    fh = int(face.height * k)
    face_s = face.resize((fw, fh), Image.BILINEAR)
    thick = int(face.width * k * 0.115 * abs(sn))
    out = Image.new("RGBA", (fw + thick + 2, fh), (0, 0, 0, 0))
    if thick > 1:
        pc = C["phone_colors"][color_name]
        edge = Image.new("RGBA", (thick, fh), tuple(int(v * 0.7) for v in pc["body"]) + (255,))
        ImageDraw.Draw(edge).rectangle([0, 0, max(0, thick // 3), fh], fill=tuple(pc["hi"]) + (255,))
        em = Image.new("L", (thick, fh), 0)
        ImageDraw.Draw(em).rounded_rectangle([0, 0, thick - 1, fh - 1], min(thick // 2, fh // 8), fill=255)
        edge.putalpha(em)
        ex = fw - thick // 2 if (sn * c) > 0 else 0
        fx = 0 if (sn * c) > 0 else thick // 2
        out.alpha_composite(edge, (min(ex, out.width - thick), 0))
        out.alpha_composite(face_s, (fx, 0))
    else:
        out.alpha_composite(face_s, (0, 0))
    if abs(c) < 0.999:   # darken as it turns away from the light
        f = 0.55 + 0.45 * abs(c)
        arr = np.asarray(out).astype(np.float32)
        arr[..., :3] *= f
        out = Image.fromarray(arr.astype(np.uint8), "RGBA")
    return out


def draw_phone(canvas, color_name, cx, cy, height, theta=0.0, tilt=0.0, glow=None, glow_gain=1.0, shadow=True):
    """Phone + glow + floor shadow centred at (cx, cy)."""
    pw = height * PHONE_RATIO
    if glow and glow_gain > 0:
        gl = rrect_light(int(pw * max(0.3, abs(math.cos(theta)))), int(height), int(pw * 0.17), int(height * 0.28), col(glow))
        add_light(canvas, gl, cx, cy, 0.85 * glow_gain)
    spr = phone_view(color_name, theta, int(height))
    paste(canvas, spr, cx, cy, 1.0, 1.0, tilt)


# -----------------------------------------------------------------------------
# 5. TEXT ANIMATION, CAPTIONS, TRANSITIONS, SHAKE
# -----------------------------------------------------------------------------
WORDS, CHUNKS = [], []        # filled from the voiceover before rendering


def text_state(spec, t):
    """(alpha, scale, dx, dy) for an animated title at scene time t, or None."""
    dt = t - spec["t"]
    if dt < 0:
        return None
    a, s, dx, dy = 1.0, 1.0, 0.0, 0.0
    anim = spec["anim"]
    if anim == "pop":
        s = ease_out_back(dt / 0.28)
        a = clamp01(dt / 0.08)
    elif anim == "bounce":
        s = 0.35 + 0.65 * spring(dt, 2.6, 8.0)
        a = clamp01(dt / 0.06)
    elif anim == "slide":
        dy = 80 * (1 - ease_out_cubic(dt / 0.35))
        a = clamp01(dt / 0.2)
    elif anim == "pill":
        dx = -140 * (1 - ease_out_cubic(dt / 0.35))
        a = clamp01(dt / 0.2)
    if spec.get("until") is not None and t > spec["until"]:
        o = (t - spec["until"]) / 0.15
        if o >= 1:
            return None
        a *= 1 - o
        s *= 1 + 0.25 * o
    return a, s, dx, dy


MAX_SCALE = {"pop": 1.12, "bounce": 1.14, "slide": 1.0, "pill": 1.0}


def title_sprite(spec):
    key = ("title", spec["text"], spec["size"], spec["color"], spec["anim"])
    if key in _CACHE:
        return _CACHE[key]
    Image, ImageDraw, *_ = P()
    c = col(spec["color"])
    size = spec["size"]
    maxw = (SAFE[2] - SAFE[0]) - 30
    if spec["anim"] == "pill":
        txt = text_sprite(spec["text"], size, col("white"), kind="bold")
        pw, ph = txt.width + 110, int(size * 1.7)
        im = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, pw - 1, ph - 1], ph // 2, fill=(14, 16, 24, 215), outline=c + (255,), width=3)
        d.ellipse([28, ph / 2 - 9, 46, ph / 2 + 9], fill=c + (255,))
        im.alpha_composite(txt, (70, (ph - txt.height) // 2))
        out = im
    else:
        while True:
            glow = spec["color"] if spec["color"] not in ("white", "grey") else (0, 0, 0)
            out = text_sprite(spec["text"], size, c, glow=glow)
            pad = out.info.get("pad", 0)
            if out.width - 2 * pad <= maxw / MAX_SCALE[spec["anim"]] or size < 20:
                break
            size -= 4
    _CACHE[key] = out
    return out


def check_safe(scene, label, cx, cy, w, h):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if x0 < SAFE[0] or y0 < SAFE[1] or x1 > SAFE[2] or y1 > SAFE[3]:
        SAFE_REPORT.append((scene, label, (int(x0), int(y0), int(x1), int(y1))))


def draw_titles(cv, si, t):
    n = 0
    for spec in SCENES[si]["texts"]:
        st = text_state(spec, t)
        if st is None:
            continue
        a, s, dx, dy = st
        spr = title_sprite(spec)
        cx = CX + dx
        if spec["anim"] == "pill":
            cx = CX + dx
        paste(cv, spr, cx, spec["y"] + dy, s, a)
        pad = spr.info.get("pad", 0)
        m = MAX_SCALE[spec["anim"]]
        check_safe(si, spec["text"], CX, spec["y"], (spr.width - 2 * pad) * m, (spr.height - 2 * pad) * m)
        n += 1
    return n


def label(cv, text, cx, cy, size, color, alpha=1.0, kind="bold", si=None, scale=1.0, glow=None):
    """Small static text (also safe-zone checked)."""
    if alpha <= 0.003:
        return
    spr = text_sprite(text, size, col(color), kind=kind, glow=glow)
    paste(cv, spr, cx, cy, scale, alpha)
    pad = spr.info.get("pad", 0)
    check_safe(si, text, cx, cy, (spr.width - 2 * pad) * scale, (spr.height - 2 * pad) * scale)


def caption_line(ci, active):
    """Sprite of one caption chunk with the active word highlighted."""
    key = ("cap", ci, active)
    if key in _CACHE:
        return _CACHE[key]
    Image, ImageDraw, *_ = P()
    words = [caption_word(w["w"]) for w in CHUNKS[ci]["words"]]
    size = C["caption_size"]
    maxw = (SAFE[2] - SAFE[0]) - 40
    while True:
        f = font("black", size)
        stroke = max(4, int(C["caption_stroke"] * size / C["caption_size"]))
        gap = int(size * 0.26)
        widths = [f.getbbox(w, stroke_width=stroke)[2] - f.getbbox(w, stroke_width=stroke)[0] for w in words]
        tw = sum(widths) + gap * (len(words) - 1)
        if tw <= maxw or size <= 40:
            break
        size -= 4
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (tw + 20, asc + desc + 2 * stroke + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 10
    for i, w in enumerate(words):
        l = f.getbbox(w, stroke_width=stroke)[0]
        fill = col("caption_active") if i == active else col("caption_fill")
        d.text((x - l, stroke + 4), w, font=f, fill=fill + (255,), stroke_width=stroke,
               stroke_fill=col("caption_stroke") + (255,))
        x += widths[i] + gap
    im = im.crop(im.getbbox())
    _CACHE[key] = im
    return im


def draw_captions(cv, T):
    for ci, ch in enumerate(CHUNKS):
        if ch["show_s"] <= T < ch["show_e"]:
            active = 0
            for k, w in enumerate(ch["words"]):
                if T >= w["s"] - 0.03:
                    active = k
            spr = caption_line(ci, active)
            dt = T - ch["show_s"]
            s = 0.78 + 0.22 * ease_out_back(dt / 0.16, 2.2)
            paste(cv, spr, CX, C["caption_y"], s, clamp01(dt / 0.05))
            check_safe("captions", " ".join(w["w"] for w in ch["words"]), CX, C["caption_y"], spr.width * 1.04, spr.height * 1.04)
            return 1
    return 0


# ---- transitions (each 0.3-0.5 s, centred on the cut) ---------------------------------
def tr_whip(A, B, p):
    np = _np()
    Image = P()[0]
    e = ease_in_out(p)
    off = int(W * e)
    a, b = np.asarray(A.convert("RGB")), np.asarray(B.convert("RGB"))
    out = np.concatenate([a[:, off:], b[:, :off]], axis=1) if off > 0 else a.copy()
    v = int(260 * math.sin(math.pi * p)) + 1          # motion blur width = speed
    if v > 2:
        cs = np.cumsum(np.pad(out.astype(np.float32), ((0, 0), (v, 0), (0, 0)), mode="edge"), axis=1)
        out = (cs[:, v:] - cs[:, :-v]) / v
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def tr_flash(A, B, p):
    Image = P()[0]
    white = Image.new(A.mode, (W, H), (255,) * len(A.mode))
    if p < 0.5:
        return Image.blend(A, white, (p / 0.5) ** 2)
    return Image.blend(B, white, ((1 - p) / 0.5) ** 1.6)


def _zoom(img, z):
    Image = P()[0]
    cw, ch = W / z, H / z
    box = (int((W - cw) / 2), int((H - ch) / 2), int((W + cw) / 2), int((H + ch) / 2))
    return img.resize((W, H), Image.BILINEAR, box=box)


def tr_zoom_punch(A, B, p):
    Image = P()[0]
    if p < 0.5:
        q = p / 0.5
        z = 1 + 0.9 * q ** 2
        img = A
    else:
        q = (1 - p) / 0.5
        z = 1 + 0.7 * q ** 2
        img = B
    # radial zoom blur: average of nearby zoom levels (spread grows with speed)
    sp = 0.05 * q
    out = _zoom(img, z)
    for i, zz in enumerate((z * (1 + sp / 2), z * (1 + sp))):
        out = Image.blend(out, _zoom(img, zz), 1 / (i + 2))
    k = 1 + 0.6 * math.sin(math.pi * p)
    return Image.eval(out, lambda v: min(255, int(v * k)))


def tr_glitch(A, B, p):
    np = _np()
    Image = P()[0]
    rng = np.random.default_rng(int(p * 1000) + 3)
    a, b = np.asarray(A.convert("RGB")), np.asarray(B.convert("RGB"))
    base = (a if p < 0.5 else b).copy()
    other = b if p < 0.5 else a
    amp = math.sin(math.pi * p)
    # displaced horizontal bands, some from the other scene
    for _ in range(int(6 + 18 * amp)):
        y0 = int(rng.integers(0, H - 20))
        hgt = int(rng.integers(8, 90))
        sh = int(rng.normal(0, 120 * amp))
        src = other if rng.random() < 0.35 else base
        base[y0:y0 + hgt] = np.roll(src[y0:y0 + hgt], sh, axis=1)
    # RGB split
    s = int(4 + 34 * amp)
    out = base.copy()
    out[..., 0] = np.roll(base[..., 0], s, axis=1)
    out[..., 2] = np.roll(base[..., 2], -s, axis=1)
    out[::4] = (out[::4] * 0.6).astype(np.uint8)            # scanlines
    if rng.random() < 0.3 * amp:
        out = 255 - out                                       # inverted flicker frame
    return Image.fromarray(out, "RGB")


def tr_spin(A, B, p):
    Image = P()[0]
    bgc = col("bg_bottom")
    if p < 0.5:
        q = ease_in_out(p / 0.5)
        img, ang, z = A, 160 * q, 1 - 0.55 * q
    else:
        q = ease_in_out((1 - p) / 0.5)
        img, ang, z = B, -160 * q, 1 - 0.55 * q
    small = img.resize((int(W * z), int(H * z)), Image.BILINEAR)
    out = Image.new("RGB", (W, H), bgc)
    out.paste(small.convert("RGB"), ((W - small.width) // 2, (H - small.height) // 2))
    r1 = out.rotate(ang, resample=Image.BILINEAR, fillcolor=bgc)
    r2 = out.rotate(ang * 0.85, resample=Image.BILINEAR, fillcolor=bgc)
    return Image.blend(r1, r2, 0.4)


TRANSITIONS = {"whip": tr_whip, "flash": tr_flash, "zoom_punch": tr_zoom_punch, "glitch": tr_glitch, "spin": tr_spin}


def shake(img, T):
    """Camera shake on the beat drops (EVENTS['shakes'])."""
    Image = P()[0]
    amp = 0.0
    for t0, strength in EVENTS["shakes"]:
        if 0 <= T - t0 < 0.5:
            amp += strength * 18 * math.exp(-(T - t0) / 0.11)
    if amp < 0.6:
        return img
    dx, dy = amp * math.sin(T * 91), amp * math.cos(T * 67)
    rot = math.radians(amp * 0.07 * math.sin(T * 53))
    z = 1 + 2.4 * amp / W
    c, s = math.cos(rot) / z, math.sin(rot) / z
    cx, cy = W / 2, H / 2
    # inverse affine: output -> input
    a, b = c, s
    d, e = -s, c
    cxi = cx - a * cx - b * cy + dx
    cyi = cy - d * cx - e * cy + dy
    return img.transform((W, H), Image.AFFINE, (a, b, cxi, d, e, cyi), resample=Image.BILINEAR)


# -----------------------------------------------------------------------------
# 6. SCENES (pure functions of scene time t; t may run a little < 0 or > 5
#    because transitions overlap neighbouring scenes)
# -----------------------------------------------------------------------------
def streak_light(length, thick, color):
    np = _np()
    key = ("streak", length, thick, tuple(color))
    if key not in _CACHE:
        y, x = np.mgrid[-thick * 3:thick * 3, -length:length].astype(np.float32)
        a = np.exp(-(x / (length * 0.45)) ** 2) * np.exp(-(y / thick) ** 2)
        _CACHE[key] = a[..., None] * np.array(color, np.float32)[None, None]
    return _CACHE[key]


def rays(cv, cx, cy, n, ang, alpha, color, length=1500, width_deg=5.0):
    _, ImageDraw, *_ = P()
    if alpha <= 2:
        return
    ov = P()[0].new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i in range(n):
        a0 = math.radians(ang + i * 360 / n)
        a1 = a0 + math.radians(width_deg)
        d.polygon([(cx, cy), (cx + length * math.cos(a0), cy + length * math.sin(a0)),
                   (cx + length * math.cos(a1), cy + length * math.sin(a1))], fill=col(color) + (int(alpha),))
    cv.paste(ov, (0, 0), ov)


# ---- procedural night city + moon (crisp at any zoom) ----------------------------------
def _world_data():
    if "world" in _CACHE:
        return _CACHE["world"]
    rng = random.Random(42)
    stars = [(rng.random(), rng.random() * 0.75, rng.random()) for _ in range(160)]
    craters = [(rng.uniform(-0.6, 0.6), rng.uniform(-0.6, 0.6), rng.uniform(0.06, 0.2)) for _ in range(16)]
    craters = [c for c in craters if c[0] ** 2 + c[1] ** 2 < 0.55]
    blds, x = [], -0.02
    while x < 1.02:
        w = rng.uniform(0.035, 0.08)
        top = rng.uniform(0.80, 0.97)
        wins = [(rng.random() < 0.45, rng.random()) for _ in range(200)]
        blds.append((x, w, top, rng.choice([(22, 24, 36), (28, 30, 44), (18, 20, 30)]), wins))
        x += w + rng.uniform(0.002, 0.01)
    mtn1 = [(i / 24, 0.80 - 0.07 * abs(math.sin(i * 1.7)) - 0.03 * rng.random()) for i in range(25)]
    mtn2 = [(i / 18, 0.84 - 0.05 * abs(math.sin(i * 2.3 + 1)) - 0.02 * rng.random()) for i in range(19)]
    _CACHE["world"] = (stars, craters, blds, mtn1, mtn2)
    return _CACHE["world"]


MOON = (0.70, 0.30, 0.042)


def draw_world(w, h, zoom, target=(MOON[0], MOON[1])):
    """Render the scene seen through a camera at `zoom`, zooming into `target`."""
    np = _np()
    Image, ImageDraw, *_ = P()
    stars, craters, blds, mtn1, mtn2 = _world_data()
    span_y = h / w                       # world height visible at zoom 1
    c0 = (0.5, 1.17 - span_y / 2)
    cx = target[0] + (c0[0] - target[0]) / zoom
    cy = target[1] + (c0[1] - target[1]) / zoom
    k = w * zoom

    def S(x, y):
        return ((x - cx) * k + w / 2, (y - cy) * k + h / 2)

    # sky gradient by world y
    ys = cy + (np.arange(h, dtype=np.float32) - h / 2) / k
    top, mid, hor = np.array([6, 10, 34.]), np.array([34, 30, 84.]), np.array([255, 120, 56.])
    a = np.clip(ys / 0.6, 0, 1)[:, None]
    b = np.clip((ys - 0.6) / 0.28, 0, 1)[:, None]
    sky = top * (1 - a) + mid * a
    sky = sky * (1 - b) + hor * b
    img = Image.fromarray(np.repeat(sky[:, None, :], w, axis=1).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for sx, sy, br in stars:
        px, py = S(sx, sy)
        if -5 < px < w + 5 and -5 < py < h + 5:
            r = 0.8 + 1.2 * br * min(zoom, 3) ** 0.5
            d.ellipse([px - r, py - r, px + r, py + r], fill=(255, 255, 255, int(120 + 120 * br)))
    # moon + glow + craters
    mx, my = S(MOON[0], MOON[1])
    mr = MOON[2] * k
    for i in range(4, 0, -1):
        rr = mr * (1 + 0.12 * i)
        d.ellipse([mx - rr, my - rr, mx + rr, my + rr], fill=(255, 230, 190, 14))
    d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(238, 232, 214, 255))
    for ox, oy, rr in craters:
        x0, y0, r0 = mx + ox * mr, my + oy * mr, rr * mr
        d.ellipse([x0 - r0, y0 - r0, x0 + r0, y0 + r0], fill=(196, 190, 176, 255))
        d.ellipse([x0 - r0 * 0.8, y0 - r0 * 0.75, x0 + r0 * 0.75, y0 + r0 * 0.8], fill=(214, 208, 192, 255))
    d.chord([mx - mr, my - mr, mx + mr, my + mr], 300, 120, fill=(0, 0, 20, 22))  # soft shade
    # mountains
    for pts, c in ((mtn1, (30, 26, 60, 255)), (mtn2, (20, 18, 40, 255))):
        poly = [S(x, y) for x, y in pts] + [S(1.05, 1.2), S(-0.05, 1.2)]
        d.polygon(poly, fill=c)
    # skyline + windows
    for x, bw, top_, c, wins in blds:
        x0, y0 = S(x, top_)
        x1, y1 = S(x + bw, 1.2)
        if x1 < 0 or x0 > w or y0 > h:
            continue
        d.rectangle([x0, y0, x1, y1], fill=c + (255,))
        ww, wh = bw / 6, 0.008
        if ww * k < 1.2:
            continue
        i = 0
        yy = top_ + 0.012
        while yy < 1.17 and i < len(wins):
            for col_ in range(3):
                lit, tone = wins[i % len(wins)]
                i += 1
                if lit:
                    a0, b0 = S(x + bw * (0.12 + 0.3 * col_), yy)
                    a1, b1 = S(x + bw * (0.12 + 0.3 * col_) + ww, yy + wh)
                    if a1 > 0 and a0 < w and b1 > 0 and b0 < h:
                        d.rectangle([a0, b0, a1, b1], fill=(255, int(190 + 50 * tone), int(110 + 60 * tone), 230))
            yy += 0.022
    return img


def blurry_world(w, h):
    """The 'bad zoom' version: tiny digital crop blown up, noisy, smeared."""
    np = _np()
    Image, _, ImageFilter, *_ = P()
    if ("blurry", w, h) in _CACHE:
        return _CACHE[("blurry", w, h)]
    small = draw_world(w // 16, h // 16, 6.0).convert("RGB")
    big = small.resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(9))
    arr = np.asarray(big).astype(np.float32)
    arr += np.random.default_rng(1).normal(0, 16, arr.shape)
    g = arr.mean(axis=2, keepdims=True)
    arr = arr * 0.55 + g * 0.45                       # washed out
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    _CACHE[("blurry", w, h)] = out
    return out


def rounded_mask(w, h, r):
    Image, ImageDraw, *_ = P()
    key = ("rmask", w, h, r)
    if key not in _CACHE:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255)
        _CACHE[key] = m
    return _CACHE[key]


# ---- scene 1: HOOK ------------------------------------------------------------------------
def scene_hook(t):
    _, ImageDraw, *_ = P()
    land = EVENTS["hook_land"]
    burst = math.exp(-max(0, t - land) / 0.35) if t >= land else 0.0
    cv = background("hook", t, 0.8 + 0.7 * burst)
    cx, cy, H_ph = PHONE_CX, 835, 690
    p = clamp01(t / land)
    e = ease_out_cubic(p)
    if t < land:
        height = 140 + (H_ph - 140) * e
        theta = (1 - e) * 5 * math.pi
        tilt = -28 * (1 - e)
        y = cy + 260 * (1 - e)
    else:
        q = t - land
        height = H_ph * (1 + 0.05 * math.exp(-q / 0.12) * math.cos(q * 30))
        theta = 0.38 * math.sin(q * 1.25)
        tilt = 2.5 * math.sin(q * 0.9)
        y = cy - 10 * math.sin(q * 2.0)
    # rays + burst behind the phone
    if t >= land:
        q = t - land
        rays(cv, cx, cy, 16, t * 18, 30 + 90 * burst, "orange_hot")
        add_light(cv, radial_light(720, col("orange")), cx, cy, 1.3 * burst + 0.25)
        d = ImageDraw.Draw(cv, "RGBA")
        if q < 0.8:
            r = 150 + 1300 * ease_out_cubic(q / 0.8)
            a = int(255 * (1 - q / 0.8))
            for wdt, c in ((26, col("orange")), (10, col("orange_hot")), (4, (255, 255, 255))):
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c + (a // (2 if wdt > 20 else 1),), width=wdt)
            rng = random.Random(5)
            for _ in range(60):
                ang = rng.uniform(0, 2 * math.pi)
                sp = rng.uniform(500, 1500)
                dist = sp * q * (1 - 0.35 * q)
                x0, y0 = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
                x1, y1 = cx + math.cos(ang) * (dist - 40), cy + math.sin(ang) * (dist - 40)
                d.line([x1, y1, x0, y0], fill=col("orange_hot") + (int(255 * (1 - q / 0.8)),), width=4)
    else:
        add_light(cv, radial_light(int(300 + 300 * e), col("blue")), cx, y, 0.6 * e)
    draw_phone(cv, "Cosmic Orange", cx, y, height, theta, tilt, glow="orange", glow_gain=0.6 + 0.8 * burst)
    add_light(cv, radial_light(260, col("orange")), cx, y + height / 2 + 30, 0.35)
    n = draw_titles(cv, 0, t)
    return cv, n + 2


# ---- scene 2: PROBLEM ------------------------------------------------------------------------
def scene_problem(t):
    Image, ImageDraw, *_ = P()
    tense = clamp01((t - 2.4) / 2.6)
    cv = background("problem", t, 0.8 + 0.6 * tense)
    n = 0
    if t < 2.5:
        # an old, dying generic phone (not the iPhone)
        a = 1.0 - clamp01((t - 2.3) / 0.2)
        jit = 7 * math.sin(t * 90) if 0.9 < t < 1.5 else 0
        cx, cy, ph = PHONE_CX + jit, 830, 700
        pw = int(ph * PHONE_RATIO)
        body = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(body)
        d.rounded_rectangle([0, 0, pw - 1, ph - 1], 46, fill=(64, 66, 72, 255), outline=(110, 112, 120, 255), width=4)
        d.rounded_rectangle([14, 14, pw - 15, ph - 15], 34, fill=(8, 8, 12, 255))
        off = clamp01((t - 1.95) / 0.3)           # screen shuts off (CRT collapse)
        if off < 1:
            sh = int((ph - 60) * (1 - off) ** 2) + 4
            d.rounded_rectangle([22, ph / 2 - sh / 2, pw - 23, ph / 2 + sh / 2], 26, fill=(30, 14, 18, 255))
        paste(cv, body, cx, cy, 1, a)
        if off < 0.6:
            alpha = a * (1 - off / 0.6)
            label(cv, "12:00", cx, cy - 190, 96, "white", alpha, "black", 1)
            label(cv, "PM", cx, cy - 110, 40, "grey", alpha, "bold", 1)
            # battery icon
            bw, bh = 230, 104
            d = ImageDraw.Draw(cv, "RGBA")
            x0, y0 = cx - bw / 2, cy + 10
            ca = int(255 * alpha)
            d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], 22, outline=(235, 235, 240, ca), width=8)
            d.rounded_rectangle([x0 + bw + 6, y0 + 32, x0 + bw + 20, y0 + bh - 32], 5, fill=(235, 235, 240, ca))
            if int(t * 4) % 2 == 0:
                d.rounded_rectangle([x0 + 16, y0 + 16, x0 + 36, y0 + bh - 16], 6, fill=col("red") + (ca,))
            label(cv, "1%", cx, cy + 190, 84, "red", alpha, "black", 1)
            if t > 0.9:
                pa = alpha * clamp01((t - 0.9) / 0.15)
                label(cv, "LOW BATTERY", cx, cy + 290, 38, "red", pa, "black", 1,
                      scale=1 + 0.15 * math.exp(-(t - 0.9) / 0.1))
        n += 4
    if t >= 2.35:
        q = t - 2.35
        e = ease_out_cubic(q / 0.4)
        cw, ch = 640, 720
        card = Image.new("RGBA", (cw + 28, ch + 28), (240, 240, 244, 255))
        photo = blurry_world(cw, ch).copy()
        card.alpha_composite(photo, (14, 14))
        card.putalpha(rounded_mask(cw + 28, ch + 28, 24))
        fade = clamp01((t - 4.25) / 0.6)
        cy = 820 + 600 * (1 - e)
        ang = -9 + 6 * e + 1.2 * math.sin(t * 13) * (0.4 + tense)
        paste(cv, card, PHONE_CX + 4 * math.sin(t * 17), cy, 1 - 0.12 * fade, 1 - 0.75 * fade, ang)
        d = ImageDraw.Draw(cv, "RGBA")
        # searching focus brackets
        fs = 120 + 18 * math.sin(t * 22)
        fx, fy = PHONE_CX, cy
        for sx in (-1, 1):
            for sy in (-1, 1):
                d.line([fx + sx * fs, fy + sy * fs, fx + sx * (fs - 40), fy + sy * fs], fill=col("red") + (220,), width=6)
                d.line([fx + sx * fs, fy + sy * fs, fx + sx * fs, fy + sy * (fs - 40)], fill=col("red") + (220,), width=6)
        label(cv, "8x DIGITAL", PHONE_CX - 170, cy + ch / 2 - 50, 32, "white", (1 - fade) * clamp01((q - 0.4) / 0.15), "black", 1)
        if t >= 3.2:          # big red X stamp
            s = ease_out_back((t - 3.2) / 0.25, 2.5)
            L = 150 * s
            a = int(240 * (1 - fade))
            d.line([fx - L, fy - L, fx + L, fy + L], fill=col("red") + (a,), width=34)
            d.line([fx - L, fy + L, fx + L, fy - L], fill=col("red") + (a,), width=34)
        n += 3
    # tension: the light closes in before the reveal
    if t > 4.0:
        add_light(cv, radial_light(520, col("orange")), PHONE_CX, 830, 1.6 * clamp01((t - 4.0) / 1.0) ** 2)
    n += draw_titles(cv, 1, t)
    return cv, n


# ---- scene 3: REVEAL ------------------------------------------------------------------------
def scene_reveal(t):
    cv = background("reveal", t, 1.25)
    cx, cy = PHONE_CX, 765
    beat = math.exp(-((t * 2) % 1) / 0.18)                     # light pulse on every beat
    rays(cv, cx, cy, 14, -t * 14, 45 + 35 * beat, "orange", width_deg=6)
    add_light(cv, radial_light(760, col("orange")), cx, cy, 0.45 + 0.3 * beat)
    p = clamp01(t / 0.95)
    height = 120 + (720 - 120) * ease_out_back(p, 1.4)
    theta = -1.1 * (1 - ease_out_cubic(p)) + 0.22 * math.sin(max(0, t - 0.9) * 1.1)
    draw_phone(cv, "Cosmic Orange", cx, cy, height, theta, 0, glow="orange", glow_gain=0.75 + 0.35 * beat)
    if 0.45 < t < 1.25:                                         # anamorphic flare sweep
        q = (t - 0.45) / 0.8
        add_light(cv, streak_light(700, 10, (255, 190, 130)), cx - 400 + 800 * q, cy - 260, 1.6 * math.sin(math.pi * q))
    if t > 2.95:                                                # vapor chamber: cool blue flow over the phone
        q = clamp01((t - 2.95) / 0.5)
        add_light(cv, radial_light(300, col("blue")), cx, cy - 120 + 60 * math.sin(t * 3), 0.5 * q)
    n = draw_titles(cv, 2, t)
    return cv, n + 2


# ---- scene 4: CAMERA ------------------------------------------------------------------------
ZOOM_LEVELS = [1, 2, 4, 8]


def zoom_at(t):
    """Viewfinder zoom (log-smooth steps 1x -> 2x -> 4x -> 8x)."""
    steps = [s - 15.0 for s in EVENTS["zoom_steps"][1:]]
    lz = 0.0
    for i, s in enumerate(steps):
        lz += ease_in_out((t - s) / 0.32)
    return 2 ** lz


def draw_phone_closeup(cv, color_name, z, base_h=2600):
    """Big zoom into the camera plateau: crop the hi-res sprite, then scale."""
    Image = P()[0]
    face = phone_face(color_name, "back", base_h)
    hp = 740 * z                                    # on-screen phone height
    k = hp / face.height
    focus = (0.40 * face.width, 0.163 * face.height)
    q = clamp01((z - 1) / 1.2)
    start = (PHONE_CX + (focus[0] - face.width / 2) * k, 820 + (focus[1] - face.height / 2) * k)
    fsx = start[0] + (PHONE_CX - start[0]) * q      # focus point slides to the centre
    fsy = start[1] + (790 - start[1]) * q
    ox, oy = fsx - focus[0] * k, fsy - focus[1] * k   # sprite origin on screen
    l, tp = max(0, -ox / k), max(0, -oy / k)
    r, b = min(face.width, (W - ox) / k), min(face.height, (H - oy) / k)
    if r <= l or b <= tp:
        return
    crop = face.crop((int(l), int(tp), int(math.ceil(r)), int(math.ceil(b))))
    sw, sh = max(1, int(crop.width * k)), max(1, int(crop.height * k))
    crop = crop.resize((sw, sh), Image.BILINEAR)
    if z < 1.6:
        gl = rrect_light(int(face.width * k), int(hp), int(face.width * k * 0.17), 200, col("blue"))
        add_light(cv, gl, ox + face.width * k / 2, oy + hp / 2, 0.8)
    cv.paste(crop, (int(max(0, ox)), int(max(0, oy))), crop)


def scene_camera(t):
    Image, ImageDraw, *_ = P()
    cv = background("camera", t, 1.1)
    n = 0
    vf_in = 1.30                      # viewfinder iris-opens here
    if t < vf_in + 0.38:
        z = 1 + 2.4 * ease_in_out((t - 0.15) / (vf_in - 0.1))
        draw_phone_closeup(cv, "Deep Blue", z)
        if 0.7 < t < 1.3:             # glint across the lenses
            q = (t - 0.7) / 0.6
            add_light(cv, streak_light(420, 8, (190, 215, 255)), PHONE_CX - 300 + 600 * q, 790, 1.4 * math.sin(math.pi * q))
        n += 2
    if t >= vf_in:
        cw, ch = 700, 830
        vcx, vcy = PHONE_CX, 790
        zoom = zoom_at(t)
        view = draw_world(cw, ch, zoom)
        d = ImageDraw.Draw(view, "RGBA")
        # viewfinder UI
        for sx, sy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            x = 30 if sx == 0 else cw - 30
            y = 30 if sy == 0 else ch - 30
            dx = 50 if sx == 0 else -50
            dy = 50 if sy == 0 else -50
            d.line([x, y, x + dx, y], fill=(255, 255, 255, 200), width=5)
            d.line([x, y, x, y + dy], fill=(255, 255, 255, 200), width=5)
        lock = clamp01((t - 2.6) / 0.25)
        fs = 95 - 20 * lock + (0 if lock else 6 * math.sin(t * 25))
        fc = (255, 204, 0, 230)
        mx, my = cw / 2, ch / 2 - 0.0
        for sx in (-1, 1):
            for sy in (-1, 1):
                d.line([mx + sx * fs, my + sy * fs, mx + sx * (fs - 26), my + sy * fs], fill=fc, width=5)
                d.line([mx + sx * fs, my + sy * fs, mx + sx * fs, my + sy * (fs - 26)], fill=fc, width=5)
        for st in EVENTS["shutters"]:          # shutter flash
            q = t - (st - 15.0)
            if 0 <= q < 0.18:
                view = Image.blend(view, Image.new("RGB", view.size, (255, 255, 255)), 0.85 * (1 - q / 0.18))
        view.putalpha(rounded_mask(cw, ch, 40))
        # iris reveal from the lens
        q = clamp01((t - vf_in) / 0.38)
        if q < 1:
            m = Image.new("L", (cw, ch), 0)
            R = 40 + 620 * ease_in_out(q)
            ImageDraw.Draw(m).ellipse([cw / 2 - R, ch / 2 - R, cw / 2 + R, ch / 2 + R], fill=255)
            from PIL import ImageChops
            view.putalpha(ImageChops.multiply(view.getchannel("A"), m))
        bump = 1.0
        for st in EVENTS["shutters"]:
            qq = t - (st - 15.0)
            if 0 <= qq < 0.25:
                bump = 1 - 0.03 * math.sin(math.pi * qq / 0.25)
        add_light(cv, rrect_light(cw, ch, 40, 90, col("blue")), vcx, vcy, 0.7 * q)
        paste(cv, view, vcx, vcy, bump)
        # zoom selector (inside the viewfinder)
        if q >= 1:
            dd = ImageDraw.Draw(cv, "RGBA")
            cur = max(i for i, zl in enumerate(ZOOM_LEVELS) if zoom >= zl * 0.92)
            for i, zl in enumerate(ZOOM_LEVELS):
                x = vcx - 165 + i * 110
                y = vcy + ch / 2 - 75
                act = i == cur
                r = 40 if act else 30
                dd.ellipse([x - r, y - r, x + r, y + r], fill=(0, 0, 0, 170), outline=(255, 255, 255, 60) if not act else col("orange") + (255,), width=3)
                label(cv, f"{zl}x", x, y, 30 if act else 24, "orange" if act else "white", 1.0, "black", 3)
            label(cv, "48MP", vcx + cw / 2 - 85, vcy - ch / 2 + 48, 28, "white", 1.0, "black", 3)
            if zoom > 7.5:
                dd.rounded_rectangle([vcx - 190, vcy - ch / 2 + 82, vcx + 190, vcy - ch / 2 + 138], 28, fill=(0, 0, 0, 170))
                label(cv, "8x  OPTICAL-QUALITY", vcx, vcy - ch / 2 + 110, 30, "orange", clamp01((t - 3.2) / 0.2), "black", 3, glow=(0, 0, 0))
        n += 5
    n += draw_titles(cv, 3, t)
    return cv, n


# ---- scene 5: POWER ------------------------------------------------------------------------
def chip_sprite():
    if "chip" in _CACHE:
        return _CACHE["chip"]
    Image, ImageDraw, ImageFilter, *_ = P()
    S = 460
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(14):                      # pins
        o = 70 + i * 23
        for (x0, y0, x1, y1) in ((o, 6, o + 10, 40), (o, S - 40, o + 10, S - 6), (6, o, 40, o + 10), (S - 40, o, S - 6, o + 10)):
            d.rounded_rectangle([x0, y0, x1, y1], 3, fill=(196, 160, 96, 255))
    d.rounded_rectangle([34, 34, S - 34, S - 34], 44, fill=(24, 26, 32, 255))
    for i in range(10):                      # orange -> blue gradient border
        f = i / 9
        c = tuple(int(col("orange")[k] * (1 - f) + col("blue")[k] * f) for k in range(3))
        d.rounded_rectangle([48 + i, 48 + i, S - 48 - i, S - 48 - i], 36, outline=c + (255,), width=1)
    d.rounded_rectangle([60, 60, S - 60, S - 60], 30, fill=(14, 15, 20, 255))
    t1 = text_sprite("A19", 132, col("white"), glow="orange")
    t2 = text_sprite("PRO", 58, col("grey"))
    im.alpha_composite(t1, (S // 2 - t1.width // 2, 190 - t1.height // 2))
    im.alpha_composite(t2, (S // 2 - t2.width // 2, 310 - t2.height // 2))
    _CACHE["chip"] = im
    return im


def scene_power(t):
    Image, ImageDraw, *_ = P()
    cv = background("power", t, 1.1)
    cx, cy = PHONE_CX, 760
    d = ImageDraw.Draw(cv, "RGBA")
    beat = math.exp(-((t * 2) % 1) / 0.18)
    n = 0
    swap = 2.45
    if t < swap + 0.22:
        out = clamp01((t - swap) / 0.22)
        rng = random.Random(3)
        for i in range(34):                  # speed streaks = "insanely fast"
            y = rng.uniform(420, 1180)
            ln = rng.uniform(120, 420)
            sp = rng.uniform(1800, 3200)
            x = (rng.uniform(0, W + ln) - t * sp) % (W + 2 * ln) - ln
            c = col("orange") if i % 2 else col("blue_soft")
            d.line([x, y, x + ln, y], fill=c + (int(120 * (1 - out)),), width=rng.choice((2, 3, 4)))
        for i in range(12):                  # circuit traces with travelling pulses
            ang = i * math.pi / 6 + 0.2
            x1, y1 = cx + 1000 * math.cos(ang), cy + 1000 * math.sin(ang)
            d.line([cx, cy, x1, y1], fill=(60, 90, 150, int(90 * (1 - out))), width=3)
            for k in range(2):
                f = ((t * 1.6 + i * 0.13 + k * 0.5) % 1)
                px, py = cx + (240 + 760 * f) * math.cos(ang), cy + (240 + 760 * f) * math.sin(ang)
                d.ellipse([px - 7, py - 7, px + 7, py + 7], fill=col("orange_hot") + (int(230 * (1 - out)),))
        s = (0.4 + 0.6 * spring(t - 0.1, 2.4, 7.0)) * (1 - 0.4 * out)
        add_light(cv, rrect_light(400, 400, 50, 160, col("orange")), cx, cy, (0.8 + 0.6 * beat) * (1 - out))
        if t >= 0.1:
            paste(cv, chip_sprite(), cx, cy - 120 * out, s, 1 - out)
        n += 3
    bat_in = swap + 0.2
    if t >= bat_in:
        q = t - bat_in
        a0, a1 = EVENTS["powerup"][0] - 20.0, EVENTS["powerup"][1] - 20.0
        lvl = ease_in_out((t - a0) / (a1 - a0))
        full = t >= a1
        s = 0.4 + 0.6 * spring(q, 2.4, 7.0)
        bw, bh = 600, 270
        bx, by = cx - 10, cy - 30
        bat = Image.new("RGBA", (bw + 50, bh + 20), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bat)
        bd.rounded_rectangle([5, 10, bw, bh + 10], 48, fill=(16, 17, 24, 255), outline=(240, 240, 245, 255), width=12)
        bd.rounded_rectangle([bw + 10, bh / 2 - 40, bw + 38, bh / 2 + 60], 10, fill=(240, 240, 245, 255))
        fw = int((bw - 52) * lvl)
        if fw > 4:
            np = _np()
            g = np.linspace(0, 1, fw)[None, :, None]
            c0, c1 = np.array(col("orange"), np.float32), np.array((255, 214, 90), np.float32)
            grad = (c0 * (1 - g) + c1 * g).repeat(bh - 42, 0)
            fill = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
            fill.putalpha(rounded_mask(fw, bh - 42, 28))
            bat.alpha_composite(fill, (26, 31))
        # lightning bolt
        bolt = [(0.56, 0.16), (0.40, 0.55), (0.52, 0.55), (0.44, 0.86), (0.62, 0.43), (0.50, 0.43), (0.58, 0.16)]
        bd.polygon([(bw * x, 10 + bh * y) for x, y in bolt], fill=(255, 255, 255, 255), outline=(20, 20, 20, 255))
        if fw > 4:
            add_light(cv, radial_light(170, (255, 200, 90)), bx + 22 + (-bw / 2 - 20 + 26 + fw) * s, by, 0.9 * (1 - lvl * 0.3) * s)
        add_light(cv, rrect_light(int(bw * s), int(bh * s), int(48 * s), 140, col("orange")), bx, by, (0.5 + 0.9 * lvl + (0.8 if full else 0) * math.exp(-(t - a1) / 0.3)) * s)
        paste(cv, bat, bx + 22, by, s)
        pct = int(round(100 * lvl))
        label(cv, f"{pct}%", cx, by + bh / 2 + 110, 112, "white", clamp01(q / 0.2), "black", 4,
              scale=1 + (0.12 * math.exp(-(t - a1) / 0.15) if full else 0), glow="orange" if full else None)
        label(cv, "ALL-DAY+ BATTERY LIFE", cx, by + bh / 2 + 215, 40, "orange", clamp01((q - 0.3) / 0.2), "black", 4)
        if full:                               # charge-complete ring
            qq = t - a1
            if qq < 0.6:
                r = 200 + 700 * ease_out_cubic(qq / 0.6)
                d = ImageDraw.Draw(cv, "RGBA")
                d.ellipse([bx - r, by - r, bx + r, by + r], outline=(255, 214, 90, int(220 * (1 - qq / 0.6))), width=10)
        else:                                  # charge particles flowing in
            rng = random.Random(9)
            d = ImageDraw.Draw(cv, "RGBA")
            for i in range(26):
                f = (t * 1.3 + rng.random()) % 1
                px = bx + rng.uniform(-300, 300) * (1 - f)
                py = by + 420 - 400 * f
                d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 200, 90, int(200 * (1 - f))))
        n += 4
    n += draw_titles(cv, 4, t)
    return cv, n


# ---- scene 6: CALL TO ACTION ------------------------------------------------------------------------
def color_times():
    """When the voiceover says each color (scene time), from the word timings."""
    base = {"Cosmic Orange": 0.1, "Deep Blue": 0.95, "Silver": 1.7, "get": 2.6}
    for w in WORDS:
        if w["scene"] != 5:
            continue
        lw = w["w"].lower().strip(",.!")
        tt = w["s"] - 25.0
        if lw == "cosmic":
            base["Cosmic Orange"] = tt
        elif lw == "deep":
            base["Deep Blue"] = tt
        elif lw == "silver":
            base["Silver"] = tt
        elif lw == "get":
            base["get"] = tt
    return base


def scene_cta(t):
    Image, ImageDraw, *_ = P()
    cv = background("cta", t, 1.1)
    ct = color_times()
    names = ["Deep Blue", "Cosmic Orange", "Silver"]          # left, centre, right
    if t < ct["Deep Blue"] - 0.05:
        sel = "Cosmic Orange"
    elif t < ct["Silver"] - 0.05:
        sel = "Deep Blue"
    elif t < ct["get"] - 0.1:
        sel = "Silver"
    else:
        sel = "Cosmic Orange"
    glow_of = {"Cosmic Orange": "orange", "Deep Blue": "blue", "Silver": (200, 214, 235)}
    beat = math.exp(-((t * 2) % 1) / 0.18)
    add_light(cv, radial_light(640, col(glow_of[sel])), PHONE_CX, 650, 0.55 + 0.25 * beat)
    layout = {"Deep Blue": (285, 660, 470, 9, 0.5, 0.12), "Cosmic Orange": (PHONE_CX, 640, 560, 0, 0.0, 0.0),
              "Silver": (745, 660, 470, -9, -0.5, 0.24)}
    for name in ("Deep Blue", "Silver", "Cosmic Orange"):
        x, y, h, tilt, th, delay = layout[name]
        e = ease_out_back((t - delay) / 0.5, 1.3)
        on = name == sel
        y = y + 520 * (1 - e) - (26 if on else 0) - 8 * math.sin(t * 2 + delay * 10)
        h = h * (1.06 if on else 1.0)
        draw_phone(cv, name, x, y, h, th + 0.12 * math.sin(t * 1.3 + delay * 6), tilt,
                   glow=glow_of[name], glow_gain=1.1 if on else 0.25)
    # color swatches
    d = ImageDraw.Draw(cv, "RGBA")
    sw_y = 1010
    for i, name in enumerate(["Cosmic Orange", "Deep Blue", "Silver"]):
        x = (285, PHONE_CX, 745)[i]
        a = clamp01((t - 0.35 - 0.1 * i) / 0.2)
        if a <= 0:
            continue
        on = name == sel
        r = 34 * (1.15 if on else 1.0) * ease_out_back((t - 0.35 - 0.1 * i) / 0.3)
        if on:
            d.ellipse([x - r - 11, sw_y - r - 11, x + r + 11, sw_y + r + 11], outline=(255, 255, 255, 255), width=4)
        d.ellipse([x - r, sw_y - r, x + r, sw_y + r], fill=C["phone_colors"][name]["swatch"] + (255,),
                  outline=(255, 255, 255, 90), width=2)
        label(cv, name, x, sw_y + 64, 31, "white" if on else "grey", a, "bold", 5)
    # pulsing CTA button
    tb = EVENTS["ding"] - 25.0
    if t >= tb:
        q = t - tb
        key = ("cta_btn",)
        if key not in _CACHE:
            size = 50
            while True:
                txt = text_sprite(C["cta_text"], size, col("white"))
                if txt.width + 110 <= (SAFE[2] - SAFE[0]) - 40 or size < 24:
                    break
                size -= 2
            bw, bh = txt.width + 110, 116
            btn = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
            np = _np()
            g = np.linspace(0, 1, bw)[None, :, None]
            grad = (np.array(col("orange"), np.float32) * (1 - g) + np.array((255, 70, 40), np.float32) * g).repeat(bh, 0)
            btn = Image.fromarray(grad.astype(np.uint8), "RGB").convert("RGBA")
            btn.putalpha(rounded_mask(bw, bh, bh // 2))
            ImageDraw.Draw(btn).rounded_rectangle([2, 2, bw - 3, bh - 3], bh // 2, outline=(255, 210, 160, 255), width=3)
            btn.alpha_composite(txt, ((bw - txt.width) // 2, (bh - txt.height) // 2))
            _CACHE[key] = btn
        btn = _CACHE[key]
        by = 1190
        s = (0.3 + 0.7 * spring(q, 2.4, 7.5)) * (1 + 0.05 * beat)
        add_light(cv, rrect_light(btn.width, btn.height, btn.height // 2, 90, col("orange")), CX, by, 0.6 + 0.6 * beat)
        ph = (t * 2) % 1                        # ripple ring every beat
        if q > 0.3:
            rs = 1 + 0.22 * ph
            d = ImageDraw.Draw(cv, "RGBA")
            bw2, bh2 = btn.width * rs / 2, btn.height * rs / 2
            d.rounded_rectangle([CX - bw2, by - bh2, CX + bw2, by + bh2], bh2, outline=col("orange_hot") + (int(170 * (1 - ph)),), width=4)
        paste(cv, btn, CX, by, s)
        check_safe(5, "CTA button", CX, by, btn.width * 1.05, btn.height * 1.05)
    # trademark + disclaimer (small, inside the safe zone)
    a = clamp01((t - 0.4) / 0.3) * 0.9
    label(cv, C["trademark_text"], CX, 1465, 25, "grey", a, "bold", 5)
    label(cv, C["disclaimer_text"], CX, 1500, 22, "grey", a * 0.8, "bold", 5)
    n = 8 + draw_titles(cv, 5, t)
    return cv, n


RENDERERS = [scene_hook, scene_problem, scene_reveal, scene_camera, scene_power, scene_cta]


# -----------------------------------------------------------------------------
# 7. FRAMES, PREVIEWS, RENDER, CONCAT, MUX, VERIFY
# -----------------------------------------------------------------------------
def apply_timing(words):
    """Install the voiceover word timings (captions + VO-synced events)."""
    global WORDS, CHUNKS
    WORDS = words
    CHUNKS = make_chunks(words)
    for w in words:                          # CTA button lands on "Get yours now"
        if w["scene"] == 5 and w["w"].lower().startswith("get"):
            EVENTS["ding"] = round(w["s"] - 0.08, 3)
            EVENTS["shakes"][-1] = (EVENTS["ding"], 0.5)
            break


def transition_at(T):
    """(cut index k, progress p) if T is inside a transition window, else None."""
    D = C["transition_len"]
    k = int(round(T / SCENE_LEN))
    if 1 <= k < len(SCENES):
        p = (T - (k * SCENE_LEN - D / 2)) / D
        if 0 <= p < 1:
            return k, p
    return None


def compose(F):
    T = F / FPS
    tr = transition_at(T)
    if tr:
        k, p = tr
        A, _ = RENDERERS[k - 1](T - (k - 1) * SCENE_LEN)
        B, _ = RENDERERS[k](T - k * SCENE_LEN)
        img, busy = TRANSITIONS[C["transitions"][k - 1]](A, B, p), 0
    else:
        si = min(int(T // SCENE_LEN), len(SCENES) - 1)
        img, busy = RENDERERS[si](T - si * SCENE_LEN)
    img = shake(img, T)
    busy += draw_captions(img, T)
    return img.convert("RGB"), busy


def _worker_init(words):
    apply_timing(words)


def render_scene_file(args):
    si, path = args
    f0, f1 = int(si * SCENE_LEN * FPS), int((si + 1) * SCENE_LEN * FPS)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-preset", C["x264_preset"], "-crf", str(C["crf"]), "-pix_fmt", "yuv420p",
           "-r", str(FPS), "-g", str(FPS), "-movflags", "+faststart", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for F in range(f0, f1):
        img, _ = compose(F)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for scene {si + 1}")
    return si, time.time() - t0, list(SAFE_REPORT)


def busiest_frame(si):
    """Pick the busiest frame of a scene: most elements on screen, then most detail."""
    np = _np()
    Image = P()[0]
    best = None
    f0, f1 = int(si * SCENE_LEN * FPS), int((si + 1) * SCENE_LEN * FPS)
    for F in range(f0, f1, 5):
        if transition_at(F / FPS):
            continue
        img, busy = compose(F)
        g = np.asarray(img.resize((270, 480), Image.BILINEAR).convert("L")).astype(np.float32)
        detail = float(np.abs(np.diff(g, axis=0)).mean() + np.abs(np.diff(g, axis=1)).mean())
        score = busy * 100 + detail
        if best is None or score > best[0]:
            best = (score, F, img)
    return best[1], best[2]


def zone_overlay(img):
    Image, ImageDraw, *_ = P()
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    red = (255, 0, 60, 70)
    d.rectangle([0, 0, W, SAFE[1]], fill=red)
    d.rectangle([0, SAFE[3], W, H], fill=red)
    d.rectangle([SAFE[2], SAFE[1], W, SAFE[3]], fill=red)
    d.rectangle(list(SAFE), outline=(0, 255, 120, 220), width=4)
    out = img.convert("RGBA")
    out.alpha_composite(ov)
    return out.convert("RGB")


def _preview_one(si):
    F, img = busiest_frame(si)
    name = SCENES[si]["name"]
    img.save(os.path.join(PREV, f"scene{si + 1}_{name}.png"))
    zone_overlay(img).save(os.path.join(PREV, f"scene{si + 1}_{name}_zones.png"))
    return si, F, list(SAFE_REPORT)


def make_previews(pool):
    Image = P()[0]
    os.makedirs(PREV, exist_ok=True)
    res = sorted(pool.map(_preview_one, range(len(SCENES))))
    thumbs = []
    for si, F, rep in res:
        SAFE_REPORT.extend(rep)
        print(f"[preview] scene {si + 1} ({SCENES[si]['name']}): busiest frame {F} (t={F / FPS:.2f}s)")
        thumbs.append(Image.open(os.path.join(PREV, f"scene{si + 1}_{SCENES[si]['name']}_zones.png")).resize((360, 640)))
    sheet = Image.new("RGB", (360 * 3 + 40, 640 * 2 + 30), (20, 20, 24))
    for i, th in enumerate(thumbs):
        sheet.paste(th, (10 + (i % 3) * 370, 10 + (i // 3) * 650))
    sheet.save(os.path.join(PREV, "contact_sheet.png"))
    print(f"[preview] saved {PREV}/ (scene PNGs, *_zones.png with the TikTok UI zones, contact_sheet.png)")


def report_safe_zone():
    seen = {}
    for scene, text, box in SAFE_REPORT:
        seen[(scene, text)] = box
    if seen:
        print("[layout] WARNING: text outside the TikTok safe zone:")
        for (scene, text), box in seen.items():
            print(f"         scene {scene}: '{text}' bbox={box}  safe={SAFE}")
    else:
        print(f"[layout] all text inside the safe zone x={SAFE[0]}..{SAFE[2]}, y={SAFE[1]}..{SAFE[3]}")
    return not seen


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_name,codec_type,width,height,pix_fmt,r_frame_rate,duration,nb_frames,sample_rate",
                          "-of", "json", path], capture_output=True, text=True).stdout
    return json.loads(out)


def mux(video, audio, out, extra_v=None):
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0"]
    cmd += extra_v or ["-c:v", "copy"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-t", f"{DUR:.3f}", "-movflags", "+faststart", out]
    run(cmd)


def fix_duration(final, video, audio):
    """Trim or pad so the file is exactly DUR seconds."""
    d = ffprobe_duration(final)
    if abs(d - DUR) < 0.005:
        return d
    print(f"[verify] duration {d:.3f}s != {DUR:.2f}s -> fixing")
    tmp = final + ".fix.mp4"
    if d > DUR:
        mux(video, audio, tmp, ["-c:v", "libx264", "-crf", str(C["crf"]), "-pix_fmt", "yuv420p", "-frames:v", str(NFRAMES)])
    else:
        pad = DUR - d + 0.1
        run(["ffmpeg", "-v", "error", "-y", "-i", video, "-i", audio, "-filter_complex",
             f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f}[v];[1:a]apad=pad_dur={pad:.3f}[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", str(C["crf"]), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-t", f"{DUR:.3f}", "-movflags", "+faststart", tmp])
    os.replace(tmp, final)
    return ffprobe_duration(final)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview-only", action="store_true", help="stop after the preview PNGs")
    ap.add_argument("--workers", type=int, default=max(1, min(6, os.cpu_count() or 2)))
    args = ap.parse_args()
    t_start = time.time()
    ensure_packages()
    os.makedirs(BUILD, exist_ok=True)
    print(f"[setup] {W}x{H} @ {FPS} fps, {DUR:.1f}s = {NFRAMES} frames, font: {os.path.basename(first_existing(C['font_black']))}")

    # 1-2. voiceover + captions
    voice, words, engine = make_voiceover()
    apply_timing(words)
    srt = os.path.join(OUT, C["srt_name"])
    write_srt(CHUNKS, srt)
    json.dump({"engine": engine, "words": words, "events": EVENTS}, open(os.path.join(BUILD, "timing.json"), "w"), indent=1)
    print(f"[captions] {len(CHUNKS)} chunks -> {srt}")

    # 3. audio
    mix = make_audio(voice)

    import multiprocessing as mp
    pool = mp.Pool(args.workers, initializer=_worker_init, initargs=(words,))
    # 4. previews (busiest frame per scene) BEFORE the full render
    make_previews(pool)
    ok = report_safe_zone()
    if args.preview_only:
        pool.close()
        print("[done] preview only")
        return

    # 5. render each scene to its own .mp4
    files = [os.path.join(BUILD, f"scene{i + 1}_{sc['name']}.mp4") for i, sc in enumerate(SCENES)]
    for si, secs, rep in pool.imap_unordered(render_scene_file, list(enumerate(files))):
        SAFE_REPORT.extend(rep)
        print(f"[render] scene {si + 1} ({SCENES[si]['name']}) done in {secs:.0f}s -> {ffprobe_duration(files[si]):.3f}s")
    pool.close()
    pool.join()
    ok = report_safe_zone() and ok

    # 6. concat demuxer + audio
    lst = os.path.join(BUILD, "concat.txt")
    with open(lst, "w") as f:
        for p in files:
            f.write(f"file '{p}'\n")
    video = os.path.join(BUILD, "video_only.mp4")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", video])
    final = os.path.join(OUT, C["final_name"])
    mux(video, mix, final)

    # 7. verify
    dur = fix_duration(final, video, mix)
    info = probe(final)
    lufs, tp = ebur128(final)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    print(f"[verify] video {v['codec_name']} {v['width']}x{v['height']} {v['pix_fmt']} {v['r_frame_rate']} "
          f"frames={v.get('nb_frames')} dur={float(v['duration']):.3f}s")
    print(f"[verify] audio {a['codec_name']} {a['sample_rate']} Hz dur={float(a['duration']):.3f}s, "
          f"loudness {lufs:.1f} LUFS, true peak {tp:.1f} dBTP")
    print(f"[verify] voice engine: {engine}; captions: {srt}")
    print(f"[done] built in {time.time() - t_start:.0f}s")
    print(f"FINAL DURATION: {dur:.2f} s")
    print(f"OUTPUT: {os.path.relpath(final, ROOT)}")


if __name__ == "__main__":
    main()
