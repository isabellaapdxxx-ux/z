"""Soundtrack: voice stem, synthesized ambient music, synthesized SFX, then an
ffmpeg mix (music ducked under the voice with sidechaincompress, loudnorm to
-14 LUFS), trimmed/padded to exactly 60.0 s."""
import json
import re
import subprocess

import numpy as np
from scipy import signal

import scenes as SC
from config import BUILD, DURATION, LINES, SR
from tts import TTS_DIR

N = int(round(DURATION * SR))
AUD = BUILD / "audio"
RNG = np.random.default_rng(2026)


# ------------------------------------------------------------------ helpers
def write_wav(path, x):
    x = np.asarray(x, np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-",
                    "-c:a", "pcm_f32le", str(path)], input=x.tobytes(), check=True)


def lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1])


def place(buf, x, t, gain=1.0):
    i = int(round(t * SR))
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    if j > i:
        buf[i:j] += x[: j - i] * gain


def env(n, a, d, shape=4.0):
    """Attack (samples) then exponential-ish decay over the rest."""
    e = np.ones(n)
    a = max(1, min(a, n))
    e[:a] = np.linspace(0, 1, a)
    e[a:] = np.exp(-shape * np.linspace(0, 1, n - a))
    return e


def pan(x, p):
    """p in [-1, 1] (scalar or array) -> stereo."""
    p = np.asarray(p)
    l = np.cos((p + 1) * np.pi / 4)
    r = np.sin((p + 1) * np.pi / 4)
    return np.stack([x * l, x * r], 1)


def tv_filter(x, cutoffs, btype="low", block=512, q=None):
    """Time-varying 2nd-order filter: cutoffs is a per-sample array (Hz)."""
    out = np.empty_like(x)
    zi = None
    for i in range(0, len(x), block):
        fc = float(np.clip(cutoffs[min(i + block // 2, len(cutoffs) - 1)], 20, SR * 0.45))
        if btype == "band":
            bw = fc / (q or 2.0)
            sos = signal.butter(1, [max(20, fc - bw / 2), min(SR * 0.45, fc + bw / 2)], "bandpass", fs=SR, output="sos")
        else:
            sos = signal.butter(2, fc, btype, fs=SR, output="sos")
        if zi is None:
            zi = np.zeros((sos.shape[0], 2))
        out[i:i + block], zi = signal.sosfilt(sos, x[i:i + block], zi=zi)
    return out


def reverb(x, seconds=2.6, wet=0.35, seed=3):
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.empty_like(x)
    for c in range(x.shape[1]):
        ir = rng.standard_normal(n) * np.exp(-t * 6.9 / seconds)
        ir = signal.sosfilt(signal.butter(1, 5000, "low", fs=SR, output="sos"), ir)
        ir /= np.sqrt(np.sum(ir ** 2))
        out[:, c] = signal.fftconvolve(x[:, c], ir)[: len(x)]
    return x * (1 - wet) + out * wet * 1.4


# ------------------------------------------------------------------ voice
def voice_track(tl):
    v = np.zeros((N, 2))
    for line in tl["lines"]:
        clip = np.load(TTS_DIR / f"line{line['index']:02d}_final.npy").astype(np.float64)
        place(v, clip, line["start"])
    return v


# ------------------------------------------------------------------ music
NOTE = lambda m: 440.0 * 2 ** ((m - 69) / 12)
CHORDS = {  # midi notes
    "Dm": [38, 45, 50, 53, 57, 64],
    "Bb": [34, 41, 46, 50, 53, 60],
    "Gm": [31, 43, 50, 55, 58, 62],
    "F": [29, 41, 48, 53, 57, 64],
}


def music_track(tl, ev):
    S = {s["index"]: s for s in tl["scenes"]}
    t = np.arange(N) / SR
    drop0, drop1 = ev["silence0"], ev["silence1"]
    sched = [(0, "Dm"), (S[5]["start"], "Bb"), (S[7]["start"], "Dm"), (S[9]["start"], "F"),
             (S[10]["start"], "Gm"), (S[11]["start"], "Bb"), (drop1, "Dm"), (S[13]["start"], "Bb"),
             (S[14]["start"], "F"), (S[14]["start"] + 3.0, "Gm"), (S[15]["start"], "Dm"), (S[16]["start"], "Bb"),
             (S[16]["start"] + 1.8, "Dm")]
    raw = np.zeros((N, 2))
    sub = np.zeros(N)
    xf = 1.2
    for k, (t0, name) in enumerate(sched):
        t1 = sched[k + 1][0] if k + 1 < len(sched) else DURATION + 1
        gate = np.clip((t - t0 + xf / 2) / xf, 0, 1) * np.clip((t1 + xf / 2 - t) / xf, 0, 1)
        idx = np.nonzero(gate > 0)[0]
        if len(idx) == 0:
            continue
        tt = t[idx]
        for j, m in enumerate(CHORDS[name]):
            f = NOTE(m)
            for det, p in ((-0.07, -0.7), (0.0, 0.0), (0.07, 0.7)):
                ff = f * 2 ** (det / 12)
                ph = RNG.random()
                saw = 2 * ((ff * tt + ph) % 1.0) - 1
                amp = 0.16 / (1 + j * 0.25)
                raw[idx] += pan(saw * amp * gate[idx], p * (0.4 + 0.1 * j))
        root = NOTE(CHORDS[name][0])
        while root > 60:
            root /= 2
        sub[idx] += np.sin(TAU * root * tt) * gate[idx]
    # intensity + filter sweep automation
    def ramp(points):
        xs, ys = zip(*points)
        return np.interp(t, xs, ys)
    s5, s11e = S[5]["start"], S[11]["end"]
    level = ramp([(0, 0.0), (0.4, 0.55), (s5, 0.55), (s11e - 0.2, 1.0), (drop0, 1.05),
                  (drop1, 1.25), (S[15]["start"], 1.2), (S[15]["start"] + 1.2, 0.7),
                  (S[16]["start"], 0.75), (DURATION - 0.5, 0.85), (DURATION, 0.0)])
    cutoff = ramp([(0, 380), (s5, 450), (s11e, 2400), (drop0, 2600), (drop1, 900),
                   (drop1 + 1.5, 3200), (S[14]["end"], 2600), (S[15]["start"] + 1.0, 420),
                   (S[16]["start"], 600), (S[16]["start"] + 1.5, 1600), (DURATION, 1400)])
    cutoff *= 1 + 0.12 * np.sin(TAU * t / 7.0)  # slow sweep wobble
    pad = np.stack([tv_filter(raw[:, c], cutoff) for c in range(2)], 1)
    # shimmer layer: high soft sines, builds through the zoom-out and returns after the drop
    sh = np.zeros(N)
    for m, a in ((74, 1.0), (81, 0.7), (86, 0.5), (88, 0.35)):
        f = NOTE(m)
        sh += a * np.sin(TAU * f * t + RNG.random() * 6) * (0.6 + 0.4 * np.sin(TAU * t * RNG.uniform(0.1, 0.3) + RNG.random() * 6))
    sh_lvl = ramp([(0, 0), (s5, 0.0), (S[9]["start"], 0.5), (s11e, 1.0), (drop0, 0.0), (drop1, 0.0),
                   (drop1 + 0.8, 1.0), (S[15]["start"], 0.6), (S[15]["end"], 0.2), (DURATION, 0.5)])
    shimmer = pan(sh * sh_lvl * 0.035, np.sin(TAU * t / 9))
    # pulse layer after the drop: filtered octave saw gated on 8th notes (~100 bpm)
    bpm = 100
    beat = (t - drop1) * bpm / 60 * 2
    gate8 = np.where(beat > 0, np.exp(-((beat % 1.0) * 5)), 0) * ramp([(0, 0), (drop1, 0), (drop1 + 0.1, 1),
                                                                       (S[14]["end"], 1), (S[15]["start"] + 0.5, 0), (DURATION, 0)])
    pulse = (2 * ((NOTE(50) * t) % 1) - 1) * gate8 * 0.12
    pulse = signal.sosfilt(signal.butter(2, 900, "low", fs=SR, output="sos"), pulse)
    sub_lvl = ramp([(0, 0), (0.5, 0.18), (drop0, 0.25), (drop1, 0.42), (S[15]["start"], 0.35), (DURATION, 0.25)])
    mus = pad * level[:, None] + shimmer + pan(pulse, 0.0) + np.stack([sub * sub_lvl] * 2, 1) * level[:, None] * 0.6
    mus = reverb(mus, 3.0, 0.4, seed=5)
    # hard silence for one beat before "Now the crazy part"
    gate = np.ones(N)
    i0, i1 = int(drop0 * SR), int(drop1 * SR)
    f = int(0.03 * SR)
    gate[i0:i1] = 0
    gate[i0 - f:i0] = np.linspace(1, 0, f)
    gate[i1:i1 + f] = np.linspace(0, 1, f)
    return mus * gate[:, None]


TAU = 2 * np.pi


# ------------------------------------------------------------------ sfx
def whoosh(dur, f0, f1, direction=1.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = rng.standard_normal(n)
    s = np.linspace(0, 1, n)
    fc = f0 * (f1 / f0) ** s
    y = tv_filter(x, fc, "band", block=256, q=1.6)
    e = np.where(s < 0.6, (s / 0.6) ** 2.2, np.exp(-(s - 0.6) / 0.4 * 4))
    return pan(y * e * 0.55, direction * np.linspace(-0.8, 0.8, n))


def tick(k=1.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int(0.012 * SR)
    t = np.arange(n) / SR
    x = (rng.standard_normal(n) * 0.5 + np.sin(TAU * 4200 * t)) * np.exp(-t * 600)
    return x * 0.35 * k


def beep(seed=0):
    out = np.zeros(int(0.5 * SR))
    for j, (f, t0) in enumerate(((1480, 0.0), (1760, 0.16))):
        n = int(0.09 * SR)
        t = np.arange(n) / SR
        b = np.sin(TAU * f * t + 0.6 * np.sin(TAU * 31 * t)) * env(n, int(0.004 * SR), 0, 2.0)
        i = int(t0 * SR)
        out[i:i + n] += b
    rng = np.random.default_rng(seed)
    out += rng.standard_normal(len(out)) * 0.05 * np.exp(-np.arange(len(out)) / SR * 6)
    out = signal.sosfilt(signal.butter(2, [700, 3200], "bandpass", fs=SR, output="sos"), out)
    return out * 0.16


def shimmer_fx(seed=0, dur=2.2):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros((n, 2))
    scale = [74, 76, 78, 81, 83, 86, 88, 90, 93, 95, 98]  # D major pentatonic-ish
    for _ in range(46):
        f = NOTE(rng.choice(scale)) * rng.choice([1, 2])
        t0 = rng.uniform(0, dur * 0.65)
        L = rng.uniform(0.25, 0.8)
        m = int(L * SR)
        tt = np.arange(m) / SR
        x = np.sin(TAU * f * tt) * np.exp(-tt * 5 / L) * rng.uniform(0.3, 1.0)
        i = int(t0 * SR)
        j = min(n, i + m)
        out[i:j] += pan(x[: j - i], rng.uniform(-0.9, 0.9))
    return out * 0.09


def riser(dur, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    s = np.linspace(0, 1, n)
    noise = tv_filter(rng.standard_normal(n), 250 * (24 ** s), "band", block=256, q=1.2)
    f = 110 * 2 ** (3 * s ** 1.5)
    tone = signal.sawtooth(TAU * np.cumsum(f) / SR) * 0.25
    tone = tv_filter(tone, 400 + 3000 * s)
    x = (noise * 0.8 + tone) * s ** 2.5
    x[-int(0.008 * SR):] *= np.linspace(1, 0, int(0.008 * SR))
    return pan(x * 0.75, 0.25 * np.sin(TAU * s * 3))


def boom():
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    f = 30 + 34 * np.exp(-t * 4)
    x = np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    click = RNG.standard_normal(n) * np.exp(-t * 90) * 0.6
    thump = signal.sosfilt(signal.butter(2, 160, "low", fs=SR, output="sos"), RNG.standard_normal(n)) * np.exp(-t * 7) * 2.0
    y = np.tanh((x * 1.1 + click + thump) * 1.4) * 0.9
    return y


def glitch_fx(seed=0, dur=0.45):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros(n)
    i = 0
    while i < n:
        m = int(rng.uniform(0.015, 0.06) * SR)
        kind = rng.integers(0, 3)
        tt = np.arange(m) / SR
        if kind == 0:
            seg = np.sign(np.sin(TAU * rng.uniform(80, 1400) * tt))
        elif kind == 1:
            seg = rng.standard_normal(m)
        else:
            seg = np.zeros(m)
        hold = rng.integers(4, 40)  # sample-and-hold "bitcrush"
        seg = np.repeat(seg[::hold], hold)[:m]
        seg = np.round(seg * 4) / 4
        j = min(n, i + m)
        out[i:j] = seg[: j - i] * rng.uniform(0.3, 0.8)
        i = j
    return pan(out * 0.28, rng.uniform(-0.5, 0.5))


def rumble(dur, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    x = np.cumsum(rng.standard_normal(n))
    x = signal.sosfilt(signal.butter(2, [25, 110], "bandpass", fs=SR, output="sos"), x)
    x /= np.abs(x).max() + 1e-9
    s = np.linspace(0, 1, n)
    e = np.clip(s / 0.2, 0, 1) * np.clip((1 - s) / 0.25, 0, 1) * (0.75 + 0.25 * np.sin(TAU * s * 2.3))
    return x * e * 0.8


def pop():
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    f = 260 + 900 * np.exp(-t * 45)
    x = np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t * 32)
    return x * 0.55


def sfx_track(tl, ev):
    S = {s["index"]: s for s in tl["scenes"]}
    out = np.zeros((N, 2))
    rng = np.random.default_rng(9)
    # whoosh on every transition, varied pitch/direction/length
    for (idx, start, kind, dur) in ev["transitions"]:
        if kind == "flash":
            continue  # the riser leads into the flash; silence follows
        L = rng.uniform(0.55, 0.8)
        if kind == "zoom_out":
            f0, f1 = rng.uniform(2200, 3200), rng.uniform(250, 450)
        elif kind == "zoom_in":
            f0, f1 = rng.uniform(250, 400), rng.uniform(2500, 4000)
        elif kind == "fade_black":
            f0, f1, L = 900, 150, 1.0
        else:
            f0, f1 = rng.uniform(400, 900), rng.uniform(1800, 4200)
            if rng.random() < 0.5:
                f0, f1 = f1, f0
        direction = -1.0 if kind in ("whip_left", "whip_up") else 1.0
        gain = 0.5 if kind == "glitch" else 0.8
        place(out, whoosh(L, f0, f1, direction, seed=idx), start + dur / 2 - L * 0.6, gain)
    # ticking under the timers (scenes 2 and 4)
    for t0, t1, rate, k in ((ev["s2_lap0"], ev["s2_lap1"], 14.0, 0.8), (ev["s4_beam0"], ev["s4_beam1"], 20.0, 0.9)):
        t = t0
        j = 0
        while t < t1:
            place(out, tick(k * (1.0 if j % 4 == 0 else 0.7), seed=j), t, 1.0)
            t += 1 / rate
            j += 1
    # softer clock ticks in scene 12 / start of 13
    t = S[12]["start"] + 0.75
    j = 0
    while t < ev["s13_reveal"] - 0.1:
        place(out, tick(0.35, seed=100 + j), t, 1.0)
        t += 0.25
        j += 1
    # Voyager radio beeps
    for k, t in enumerate(ev["s5_beeps"]):
        if t < S[5]["end"]:
            place(out, pan(beep(seed=k), -0.3), t, 1.0)
    # Hubble shimmer
    place(out, shimmer_fx(seed=4), ev["s11_zoom1"] - 0.25, 1.0)
    # 93 billion reveal: sub boom + glitch
    place(out, boom(), ev["s13_reveal"], 1.0)
    place(out, glitch_fx(seed=13), ev["s13_reveal"] - 0.06, 1.0)
    place(out, glitch_fx(seed=12, dur=0.3), S[13]["start"], 0.8)
    # low rumble in the void
    place(out, rumble(S[15]["end"] - S[15]["start"] + 0.4), S[15]["start"] - 0.1, 1.0)
    # "you are here" pop
    place(out, pop(), ev["s16_dot"], 1.0)
    place(out, pop() * 0.6, ev["s16_card"], 1.0)
    out = reverb(out, 1.6, 0.18, seed=8)
    # riser into scene 12 stays dry so it cuts hard at the flash -> one beat of silence
    place(out, riser(ev["riser1"] - ev["riser0"]), ev["riser0"], 1.0)
    return out


# ------------------------------------------------------------------ mix
def build():
    AUD.mkdir(parents=True, exist_ok=True)
    tl = json.loads((BUILD / "timeline.json").read_text())
    ev = SC.events(tl)
    stems = {"voice": voice_track(tl), "music": music_track(tl, ev), "sfx": sfx_track(tl, ev)}
    for k, x in stems.items():
        write_wav(AUD / f"{k}_raw.wav", x)
    # stem levels: voice -16 LUFS, music ~8 LU under it (=> about -22 LUFS once the
    # final mix is normalised to -14), SFX by ear relative to the voice
    targets = {"voice": -16.0, "music": -24.0, "sfx": -21.0}
    for k, x in stems.items():
        g = 10 ** ((targets[k] - lufs(AUD / f"{k}_raw.wav")) / 20)
        write_wav(AUD / f"{k}.wav", x * g)
    mix = AUD / "mix.wav"
    fc = ("[0:a]asplit=2[v][sc];"
          "[1:a][sc]sidechaincompress=threshold=0.02:ratio=5:attack=20:release=380:makeup=1[duck];"
          "[v][duck][2:a]amix=inputs=3:normalize=0:duration=longest[m]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(AUD / "voice.wav"), "-i", str(AUD / "music.wav"),
                    "-i", str(AUD / "sfx.wav"), "-filter_complex", fc, "-map", "[m]", "-c:a", "pcm_f32le", str(mix)],
                   check=True)
    # two-pass loudnorm to -14 LUFS, then exactly 60.0 s
    ln = "loudnorm=I=-14:TP=-1.5:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mix), "-af", ln + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    meas = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    ln2 = (f"{ln}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:measured_LRA={meas['input_lra']}"
           f":measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
    final = AUD / "final.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mix), "-af",
                    f"{ln2},aresample={SR},apad=whole_len={N},atrim=end_sample={N}",
                    "-ar", str(SR), "-c:a", "pcm_s16le", str(final)], check=True)
    print(f"  final mix: {lufs(final):.1f} LUFS")
    return final


if __name__ == "__main__":
    build()
