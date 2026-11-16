"""Synthesize the sound design (drone, wind, heartbeat, booms, static, ringing,
reversed-reverb whoosh) and mix it under the voice. Everything is generated
here from noise and sine waves; no samples or recordings are used.
Writes build/mix.wav (48 kHz stereo, 60.000 s) and prints level checks."""
import json, os, sys
import numpy as np
import pyloudnorm as pyln
from scipy import signal
from scipy.io import wavfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *

B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build")
N = int(DUR * SR)
t = np.arange(N) / SR
rng = np.random.default_rng(2009)


def db(x):
    return 10 ** (x / 20)


def sos(kind, f, order=4):
    return signal.butter(order, f, btype=kind, fs=SR, output="sos")


def filt(x, kind, f, order=4):
    return signal.sosfilt(sos(kind, f, order), x, axis=0)


def smooth_noise(n, rate_hz, seed):
    """Slowly varying random curve in [0,1]."""
    r = np.random.default_rng(seed)
    k = max(4, int(n / SR * rate_hz) + 4)
    pts = r.random(k)
    xs = np.linspace(0, n, k)
    from scipy.interpolate import CubicSpline
    y = CubicSpline(xs, pts)(np.arange(n))
    return np.clip(y, 0, 1)


def place(dst, src, at):
    i = int(round(at * SR))
    if i >= len(dst):
        return
    j = min(len(dst), i + len(src))
    dst[i:j] += src[: j - i]


def stereo(m, width=0.0):
    return np.stack([m, m], axis=1)


def norm_rms(x, target_db):
    r = np.sqrt(np.mean(x ** 2)) + 1e-12
    return x * db(target_db) / r


def reverb_ir(seconds, decay, seed, stereo_out=True):
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    tt = np.arange(n) / SR
    chans = []
    for c in range(2 if stereo_out else 1):
        ir = r.standard_normal(n) * np.exp(-tt / decay)
        ir = filt(ir, "low", 6000, 2)
        chans.append(ir / np.sqrt(np.sum(ir ** 2)))
    return np.stack(chans, 1) if stereo_out else chans[0]


def conv_st(mono, ir):
    return np.stack([signal.fftconvolve(mono, ir[:, c])[: len(mono) + len(ir)] for c in range(2)], 1)


# ---------------------------------------------------------------- voice
sr_v, voice = wavfile.read(f"{B}/voice.wav")
voice = voice.astype(np.float64)[:N]
voice = np.pad(voice, (0, N - len(voice)))
timeline = json.load(open(f"{B}/timeline.json"))

# voice envelope for ducking (fast attack, slow release)
env = np.abs(voice)
win = int(0.02 * SR)
env = np.sqrt(np.convolve(env ** 2, np.ones(win) / win, mode="same"))
att, rel = np.exp(-1 / (0.015 * SR)), np.exp(-1 / (0.35 * SR))
e = signal.lfilter([1 - rel], [1, -rel], env)  # release-smoothed
e = np.maximum(e, signal.lfilter([1 - att], [1, -att], env))
e = np.clip(e / (np.percentile(e[e > 1e-4], 90) + 1e-9), 0, 1)
duck = 1 - 0.6 * e               # up to ~ -8 dB under speech
duck_light = 1 - 0.35 * e
duck_heavy = 1 - 0.8 * e         # ~ -14 dB: static/ringing never sit on top of words

# ---------------------------------------------------------------- drone
f0 = 43.65  # F1
lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.07 * t)
drone = np.zeros((N, 2))
for c, det in enumerate([1.0, 1.003]):
    d = (np.sin(2 * np.pi * f0 * det * t)
         + 0.55 * np.sin(2 * np.pi * f0 * 1.5 * det * t + 0.3)
         + 0.30 * np.sin(2 * np.pi * f0 * 2.0 * det * t + 1.1)
         + 0.16 * np.sin(2 * np.pi * f0 * 2.0 * 1.0595 * det * t + 2.0)   # minor 2nd rub
         + 0.10 * np.sin(2 * np.pi * f0 * 4.0 * 1.0595 * t * (1 + 0.004 * c)))
    rumble = filt(rng.standard_normal(N), "band", [25, 110], 2) * 2.0
    drone[:, c] = (d + rumble) * lfo
# eerie high pad: band-limited noise sweeping slowly
pad = np.zeros((N, 2))
for c in range(2):
    nz = rng.standard_normal(N)
    pad[:, c] = filt(nz, "band", [700, 1300], 2) * (0.4 + 0.6 * smooth_noise(N, 0.15, 11 + c))
drone = norm_rms(drone, -30) + norm_rms(pad, -48)
# swell slightly over the video
drone *= (0.8 + 0.35 * (t / DUR))[:, None]

# ---------------------------------------------------------------- wind / forest
wind = np.zeros((N, 2))
gust = 0.25 + 0.75 * smooth_noise(N, 0.35, 5) ** 1.5
for c in range(2):
    nz = rng.standard_normal(N)
    lo = filt(nz, "low", 500, 2)
    hi = filt(nz, "band", [900, 2600], 2) * (0.4 * smooth_noise(N, 0.5, 20 + c))  # whistle
    wind[:, c] = (lo + hi) * gust
wind = norm_rms(wind, -38)
# louder in the forest scenes, quieter "room tone" indoors/on screens
scene_gain = np.ones(N)
for s, e_, name in SCENES:
    g = {"hook": 1.2, "forum": 0.45, "photo": 0.8, "layer": 0.5, "spread": 0.5, "faceless": 1.0,
         "polaroids": 0.8, "camcorder": 1.4, "sightings": 0.6, "twist": 1.2, "screens": 0.45,
         "viewer": 0.5, "final": 1.3, "black": 0}[name]
    scene_gain[int(s * SR):int(e_ * SR)] = g
scene_gain = np.convolve(scene_gain, np.ones(int(0.25 * SR)) / int(0.25 * SR), mode="same")
wind *= scene_gain[:, None]
# a couple of twig snaps in pauses
twigs = np.zeros((N, 2))
for at, pan in [(3.45, 0.3), (31.0, 0.75), (43.6, 0.2)]:
    n = int(0.05 * SR)
    snap = filt(rng.standard_normal(n), "band", [1500, 5000], 2) * np.exp(-np.arange(n) / (0.006 * SR))
    snap = norm_rms(snap, -24)
    place(twigs[:, 0], snap * (1 - pan), at)
    place(twigs[:, 1], snap * pan, at)
twigs = twigs + 0.4 * conv_st(twigs.mean(1), reverb_ir(1.2, 0.3, 3))[:N]

# ---------------------------------------------------------------- heartbeat
def thump(freq, length, level):
    n = int(length * SR)
    tt = np.arange(n) / SR
    f = freq * (1 - 0.35 * tt / length)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * np.exp(-tt / (length / 4)) * (1 - np.exp(-tt / 0.003))
    click = filt(rng.standard_normal(n), "low", 180, 2) * np.exp(-tt / 0.01) * 0.5
    return (s + click) * level


heart = np.zeros(N)
tb = HEART_START
while tb < HEART_END - 0.25:
    p = (tb - HEART_START) / (HEART_END - HEART_START)
    bpm = 56 + 64 * p ** 1.6           # 56 -> 120 bpm
    lvl = 0.35 + 0.65 * p
    place(heart, thump(58, 0.20, lvl), tb)
    place(heart, thump(50, 0.18, lvl * 0.7), tb + 0.24 * (60 / bpm) ** 0.5 * 0.55)
    tb += 60 / bpm
heart = filt(heart, "low", 160, 2)
fade_in = np.clip((t - HEART_START) / 3, 0, 1)
heart = norm_rms(heart, -28) * fade_in
heart = stereo(heart)

# ---------------------------------------------------------------- booms
def boom(length=3.5):
    n = int(length * SR)
    tt = np.arange(n) / SR
    f = 28 + 62 * np.exp(-tt / 0.18)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / 0.9) * (1 - np.exp(-tt / 0.004))
    hit = filt(rng.standard_normal(n), "low", 260, 3) * np.exp(-tt / 0.12) * 0.9
    crack = filt(rng.standard_normal(n), "band", [900, 4000], 2) * np.exp(-tt / 0.02) * 0.25
    dry = sub + hit + crack
    wet = conv_st(dry, reverb_ir(3.0, 0.8, 9))[:n] * 0.6
    out = stereo(dry) + wet
    return out / np.abs(out).max()


booms = np.zeros((N, 2))
for at in BOOMS:
    place(booms, boom() * db(-10), at)


# ---------------------------------------------------------------- static / glitch bursts
def static_burst(length, seed, level_db):
    r = np.random.default_rng(seed)
    n = int(length * SR)
    nz = r.standard_normal(n)
    hold = r.integers(4, 18)
    nz = np.repeat(nz[::hold], hold)[:n]                 # sample-and-hold "bitcrush"
    nz = filt(nz, "band", [700, 7000], 2)
    gate = np.repeat(r.random(n // 480 + 1) > 0.3, 480)[:n].astype(float)
    gate = np.convolve(gate, np.ones(48) / 48, mode="same")
    tone = np.sin(2 * np.pi * r.uniform(900, 2400) * np.arange(n) / SR) * 0.3 * (r.random() > 0.5)
    env_ = np.minimum(1, np.arange(n) / (0.004 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.03 * SR))
    s = (nz + tone) * gate * env_
    s = norm_rms(s, level_db)
    pan = r.uniform(0.3, 0.7)
    return np.stack([s * (1 - pan) * 1.4, s * pan * 1.4], 1)


glitch = np.zeros((N, 2))
for k, c in enumerate(GLITCH_CUTS):
    place(glitch, static_burst(0.20, 100 + k, -21), c - 0.07)
for k, c in enumerate(MINI_GLITCHES):
    place(glitch, static_burst(0.09, 300 + k, -34), c)

# ---------------------------------------------------------------- ringing swell
ring = np.zeros(N)
i0, i1 = int(RING_START * SR), int(RING_END * SR)
tt = t[i0:i1] - RING_START
L = RING_END - RING_START
r_env = (np.exp(3.2 * tt / L) - 1) / (np.exp(3.2) - 1)
r_env *= np.minimum(1, (L - tt) / 0.012)               # hard (click-free) cut
ring[i0:i1] = (np.sin(2 * np.pi * 3520 * tt) + 0.8 * np.sin(2 * np.pi * 3527.5 * tt)
               + 0.15 * np.sin(2 * np.pi * 7040 * tt)) * r_env
ring = stereo(ring / 2.0 * db(-23))

# ---------------------------------------------------------------- reversed reverb into the final line
fl = [x for x in timeline if abs(x["start"] - FINAL_LINE_START) < 0.2][0]
seg = voice[int(fl["start"] * SR):int(fl["end"] * SR)]
wet = conv_st(seg, reverb_ir(2.2, 0.7, 21))
rev = wet[::-1]                                        # reversed reverb swell
rev = rev[-int((len(seg) * 0) + len(rev)):]
rev_len = len(rev) - len(seg)                          # swell that leads into the line
rev = rev[:rev_len] if rev_len > 0 else rev
rev = rev / np.abs(rev).max() * db(-16)
whoosh_rr = np.zeros((N, 2))
place(whoosh_rr, rev, FINAL_LINE_START - len(rev) / SR)
# noise whoosh: reversed-reverb noise burst that rises into the cut
n = int(1.6 * SR)
nb = filt(rng.standard_normal(int(0.08 * SR)), "band", [300, 5000], 2)
nw = conv_st(nb, reverb_ir(1.6, 0.45, 33))[:n]
nw = nw[::-1]
sweep = np.linspace(0, 1, n) ** 2
nw = nw * sweep[:, None]
nw = nw / np.abs(nw).max() * db(-14)
place(whoosh_rr, nw, CUTS[-2] - n / SR + 0.04)          # lands on the 56.3 s cut

# ---------------------------------------------------------------- mix
bed = (drone * duck[:, None] + wind * duck[:, None] + twigs + heart * duck_light[:, None])
fx = booms + (glitch + ring) * duck_heavy[:, None] + whoosh_rr
# everything thins out once the ringing cuts: let the last line breathe
after = np.clip((t - RING_END) / 0.05, 0, 1)
bed *= (1 - 0.55 * after)[:, None]
mix = stereo(voice) + bed + fx
# hard cut to silence on black
mix[int(BLACK * SR):] = 0
mix[int(BLACK * SR) - 240:int(BLACK * SR)] *= np.linspace(1, 0, 240)[:, None]

meter = pyln.Meter(SR)
lufs = meter.integrated_loudness(mix)
mix *= db(-14 - lufs)
# soft-knee peak safety (booms), then re-check
peak = np.abs(mix).max()
ceiling = db(-1.5)
if peak > ceiling:
    k = ceiling
    over = np.abs(mix) > k * 0.8
    m = np.abs(mix)
    comp = np.where(over, k * 0.8 + (k * 0.2) * np.tanh((m - k * 0.8) / (k * 0.2)), m)
    mix = np.sign(mix) * comp
wavfile.write(f"{B}/mix.wav", SR, mix.astype(np.float32))

# ---------------------------------------------------------------- checks
lufs2 = meter.integrated_loudness(mix)
print(f"mix integrated loudness {lufs2:.2f} LUFS, peak {20*np.log10(np.abs(mix).max()):.2f} dBFS, len {len(mix)/SR:.3f}s")
g = db(-14 - lufs)
v_st = stereo(voice) * g
b_st = (bed + fx) * g
band = sos("band", [300, 4000], 4)
v_sb = signal.sosfilt(band, v_st.mean(1))
b_sb = signal.sosfilt(band, b_st.mean(1))
worst = []
w = int(0.1 * SR)
rms = lambda y: 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
for x in timeline:
    a, b_ = int(x["start"] * SR), int(x["end"] * SR)
    vs = rms(v_sb[a:b_])
    gaps = []
    for k in range(a, b_ - w, w // 2):
        v_k = rms(v_sb[k:k + w])
        if v_k > vs - 6:                      # window where words are being spoken
            gaps.append(v_k - rms(b_sb[k:k + w]))
    worst.append(min(gaps))
    print(f"{x['start']:6.2f}s speech-band voice {vs:6.1f} dB | while speaking, voice exceeds effects by  min {min(gaps):5.1f} / median {np.median(gaps):5.1f} dB  {x['text'][:34]}")
print(f"WORST CASE voice-over-effects (speech band, 100 ms windows while speaking): {min(worst):.1f} dB")
