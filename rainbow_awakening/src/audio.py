"""Original soundtrack: synthesized music + sound effects + crowd reactions, mixed under the voice-over.

usage: python src/audio.py --models <dir> --build build

Reads build/vo.wav + build/timing.json (from voice.py). Writes build/music.wav, build/sfx.wav and
build/mix.wav (48 kHz stereo, exactly 90 s, about -14 LUFS, true peak <= -1.5 dBTP).
Event times below mirror the ones the renderer uses (web/scenes.js) so hits land on the picture.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from script import DURATION  # noqa: E402

SR = 48000
N = int(round(DURATION * SR))
rng = np.random.default_rng(1234)


# ============================================================ DSP helpers
def tt(d):
    return np.arange(int(round(d * SR))) / SR


def sos(kind, f, order=2):
    if kind == 'bp':
        return signal.butter(order, [f[0] / (SR / 2), f[1] / (SR / 2)], 'bandpass', output='sos')
    return signal.butter(order, min(f, SR / 2 - 100) / (SR / 2), kind, output='sos')


def lp(x, f, o=2): return signal.sosfilt(sos('low', f, o), x, axis=0)
def hp(x, f, o=2): return signal.sosfilt(sos('high', f, o), x, axis=0)
def bp(x, a, b, o=2): return signal.sosfilt(sos('bp', (a, b), o), x, axis=0)
def noise(d): return rng.standard_normal(int(round(d * SR)))
def mtof(m): return 440.0 * 2 ** ((m - 69) / 12)


def env(d, a=0.005, r=None, hold=None, curve=4.0):
    """attack + exponential release envelope."""
    t = tt(d)
    e = np.ones_like(t)
    na = max(1, int(a * SR))
    e[:na] = np.linspace(0, 1, na)
    if r is not None:
        start = hold if hold is not None else a
        k = t > start
        e[k] *= np.exp(-(t[k] - start) * curve / r)
    return e


def adsr(d, a=0.01, dcy=0.1, s=0.7, r=0.1):
    t = tt(d)
    e = np.interp(t, [0, a, a + dcy, max(a + dcy, d - r), d], [0, 1, s, s, 0])
    return e


def osc(kind, f, d, phase=0.0):
    t = tt(d)
    if callable(f):
        ph = np.cumsum(f(t)) / SR + phase
    elif np.ndim(f):
        ph = np.cumsum(f) / SR + phase
    else:
        ph = f * t + phase
    ph = ph % 1.0
    if kind == 'sin':
        return np.sin(2 * np.pi * ph)
    if kind == 'saw':
        return 2 * ph - 1
    if kind == 'sq':
        return np.where(ph < 0.5, 1.0, -1.0)
    if kind == 'tri':
        return 4 * np.abs(ph - 0.5) - 1
    raise ValueError(kind)


def st(x, pan=0.0):
    if x.ndim == 2:
        return x
    l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    return np.stack([x * l * 1.414, x * r * 1.414], 1)


_ir = {}


def reverb(x, decay=1.8, mix=0.3, bright=6000, pre=0.015):
    key = (decay, bright)
    if key not in _ir:
        t = tt(decay * 1.4)
        ir = np.stack([rng.standard_normal(len(t)), rng.standard_normal(len(t))], 1)
        ir *= np.exp(-t * 6.9 / decay)[:, None]
        ir = lp(ir, bright)
        ir = np.concatenate([np.zeros((int(pre * SR), 2)), ir])
        _ir[key] = ir / np.sqrt((ir ** 2).sum(0, keepdims=True))
    ir = _ir[key]
    x = st(x)
    wet = np.stack([signal.fftconvolve(x[:, c], ir[:, c]) for c in range(2)], 1)
    dry = np.concatenate([x, np.zeros((len(ir) - 1, 2))])
    return dry * (1 - mix) + wet * mix * 1.3


def varlp(x, fc):
    """one-pole lowpass with a time-varying cutoff (array, Hz)."""
    a = np.exp(-2 * np.pi * np.clip(fc, 20, SR / 2.2) / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s = (1 - a[i]) * x[i] + a[i] * s
        y[i] = s
    return y


class Bus:
    def __init__(self):
        self.b = np.zeros((N, 2))

    def add(self, x, t, gain=1.0, pan=0.0):
        x = st(np.asarray(x, float), pan) * gain
        i = int(round(t * SR))
        if i < 0:
            x, i = x[-i:], 0
        if i >= N:
            return
        n = min(len(x), N - i)
        self.b[i:i + n] += x[:n]


# ============================================================ instruments
def kick(g=1.0):
    d = 0.45
    f = 45 + 120 * np.exp(-tt(d) * 28)
    x = osc('sin', f, d) * env(d, 0.002, 0.3)
    x += lp(noise(d), 3000) * env(d, 0.001, 0.015) * 0.3
    return np.tanh(x * 1.6) * g


def snare(g=1.0):
    d = 0.3
    x = bp(noise(d), 1200, 7000) * env(d, 0.001, 0.13) * 0.8
    x += osc('sin', 185, d) * env(d, 0.001, 0.06) * 0.6
    return x * g


def clap(g=1.0):
    d = 0.3
    e = np.zeros(int(d * SR))
    for k, o in enumerate([0, 0.011, 0.022]):
        i = int(o * SR)
        e[i:] += np.exp(-np.arange(len(e) - i) / SR * (60 if k < 2 else 18))
    return bp(noise(d), 900, 5000) * e * 0.6 * g


def hat(g=1.0, open_=False):
    d = 0.25 if open_ else 0.06
    return hp(noise(d), 7000, 2) * env(d, 0.001, d * 0.5) * 0.35 * g


def crash(g=1.0):
    d = 2.2
    x = hp(noise(d), 4500) * env(d, 0.002, 1.4) * 0.5
    return reverb(x, 1.5, 0.3) * g


def bass_note(m, d, g=1.0):
    f = mtof(m)
    x = osc('saw', f, d) * 0.6 + osc('sq', f * 0.5, d) * 0.3
    x = lp(x, 900, 2) * adsr(d, 0.005, 0.08, 0.7, 0.04)
    return x * g


def pluck(m, d=0.25, g=1.0, kind='sq', bright=5000):
    f = mtof(m)
    x = osc(kind, f, d) * 0.5 + osc('sq', f * 1.005, d) * 0.25
    x = lp(x, bright) * env(d, 0.003, d * 0.6)
    return x * g


def bell(m, d=1.2, g=1.0, ratio=3.5, idx=2.0):
    f = mtof(m)
    t = tt(d)
    mod = np.sin(2 * np.pi * f * ratio * t) * idx * np.exp(-t * 4)
    x = np.sin(2 * np.pi * f * t + mod) * env(d, 0.002, d * 0.5)
    return x * g


def pad(notes, d, g=1.0, cutoff=2200, attack=0.6, release=0.8, kind='saw'):
    x = np.zeros(int(round(d * SR)))
    for m in notes:
        for det in (-0.12, 0.0, 0.11):
            x += osc(kind, mtof(m + det), d, rng.random())
    x = lp(x / (3 * len(notes)), cutoff, 2)
    return x * adsr(d, attack, 0.2, 0.9, release) * g


def piano(m, d=1.6, g=1.0):
    f = mtof(m)
    t = tt(d)
    x = sum(np.sin(2 * np.pi * f * k * t * (1 + 0.0004 * k * k)) * np.exp(-t * (1.8 + k * 0.9)) / k for k in range(1, 7))
    x *= env(d, 0.003, d)
    return x * g


def brass(notes, d, g=1.0):
    x = np.zeros(int(round(d * SR)))
    for m in notes:
        for det in (-0.08, 0.08):
            x += osc('saw', mtof(m + det), d, rng.random())
    t = tt(d)
    fc = 600 + 3200 * np.exp(-t * 6) + 500
    x = varlp(x / (2 * len(notes)), fc)
    return x * adsr(d, 0.02, 0.15, 0.75, 0.15) * g


def choir(notes, d, g=1.0):
    x = np.zeros(int(round(d * SR)))
    for m in notes:
        for det in (-0.15, -0.05, 0.06, 0.14):
            vib = lambda tq, m=m, det=det: mtof(m + det) * (1 + 0.004 * np.sin(2 * np.pi * 5.2 * tq + rng.random() * 6))
            x += osc('saw', vib, d)
    x /= 4 * len(notes)
    y = bp(x, 600, 900) * 1.2 + bp(x, 1100, 1400) * 0.8 + bp(x, 2400, 2900) * 0.35
    return y * adsr(d, 0.5, 0.3, 0.9, 0.6) * g


def timpani(g=1.0, m=38):
    d = 1.2
    f = mtof(m) * (1 + 0.15 * np.exp(-tt(d) * 20))
    x = osc('sin', f, d) * env(d, 0.003, 0.8) + lp(noise(d), 800) * env(d, 0.002, 0.08) * 0.4
    return x * g


# ============================================================ SFX
def whoosh(d=0.7, f0=300, f1=4000, g=1.0, rev=True):
    t = tt(d)
    k = t / d
    fc = f0 * (f1 / f0) ** np.sin(np.pi * k * 0.5)
    x = varlp(noise(d), fc) - varlp(noise(d), fc * 0.25) * 0.6
    x *= np.sin(np.pi * k) ** 1.5
    x /= np.abs(x).max() + 1e-9
    y = st(x * 0.9)
    y[:, 0] *= np.linspace(1.2, 0.6, len(t)); y[:, 1] *= np.linspace(0.6, 1.2, len(t))
    return (reverb(y, 0.8, 0.2) if rev else y) * g


def shimmer(d=2.0, g=1.0, base=84, seed=0):
    r = np.random.default_rng(seed)
    x = np.zeros(int(d * SR))
    for k in range(28):
        m = base + r.integers(0, 24)
        t0 = r.random() * d * 0.7
        dd = min(d - t0, 0.25 + r.random() * 0.9)
        b = bell(m, dd, 0.12 + r.random() * 0.1, ratio=2.01 + r.random(), idx=1.0)
        i = int(t0 * SR)
        x[i:i + len(b)] += b[:len(x) - i]
    x *= np.interp(tt(d), [0, 0.1, d * 0.6, d], [0, 1, 0.8, 0])
    return reverb(x, 2.2, 0.45, 9000) * g


def magic_hum(d=5.0, g=1.0):
    t = tt(d)
    x = np.zeros_like(t)
    for m, a in [(50, 0.5), (57, 0.35), (62, 0.3), (65, 0.25), (69, 0.15)]:
        x += np.sin(2 * np.pi * mtof(m) * t * (1 + 0.006 * np.sin(2 * np.pi * 4.5 * t + m))) * a
    x *= (0.75 + 0.25 * np.sin(2 * np.pi * 3 * t)) * np.interp(t, [0, 0.6, d - 0.8, d], [0, 1, 1, 0])
    return reverb(lp(x, 2500), 1.5, 0.35) * g


def clink(g=1.0, seed=0):
    r = np.random.default_rng(seed + 50)
    d = 0.25
    t = tt(d)
    x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (40 + 30 * r.random())) for f in r.uniform(1800, 5200, 4))
    x += hp(noise(d), 3000) * np.exp(-t * 200) * 0.6
    return x * 0.35 * g


def thud(g=1.0):
    d = 0.4
    x = osc('sin', 70 + 60 * np.exp(-tt(d) * 30), d) * env(d, 0.002, 0.2)
    x += lp(noise(d), 600) * env(d, 0.001, 0.05) * 0.5
    return x * g


def zap(g=1.0, up=False):
    d = 0.35
    f = (300 + 1800 * tt(d) / d) if up else (1600 * np.exp(-tt(d) * 9) + 120)
    x = osc('sq', f, d) * 0.3 + osc('saw', f * 1.5, d) * 0.2
    return lp(x, 6000) * env(d, 0.002, 0.2) * g


def blast(g=1.0):
    d = 0.9
    x = osc('sin', 60 + 200 * np.exp(-tt(d) * 14), d) * env(d, 0.002, 0.5) * 0.9
    x += bp(noise(d), 300, 4000) * env(d, 0.002, 0.25) * 0.6
    z = zap(0.6)
    x[:len(z)] += z
    return reverb(np.tanh(x * 1.4), 1.0, 0.2) * g


def explosion(g=1.0, d=2.4):
    t = tt(d)
    x = osc('sin', 38 + 80 * np.exp(-t * 6), d) * np.exp(-t * 2.2) * 1.0
    x += lp(noise(d), 900) * np.exp(-t * 3.5) * 0.9
    x += bp(noise(d), 1500, 8000) * np.exp(-t * 9) * 0.4
    return reverb(np.tanh(x * 1.5), 2.0, 0.3) * g


def chime(g=1.0, seed=1, up=True):
    notes = [84, 88, 91, 96, 100] if up else [96, 91, 88, 84]
    x = np.zeros(int(1.6 * SR))
    for k, m in enumerate(notes):
        b = bell(m, 1.0, 0.25)
        i = int(k * 0.055 * SR)
        x[i:i + len(b)] += b
    return reverb(x, 1.8, 0.4, 9000) * g


def bass_hit(g=1.0, d=2.8):
    t = tt(d)
    x = osc('sin', 34 + 40 * np.exp(-t * 4), d) * np.exp(-t * 1.3)
    x += lp(noise(d), 200) * np.exp(-t * 3) * 0.5
    x = np.tanh(x * 2.0) * 0.9
    return reverb(x, 2.5, 0.25, 3000) * g


def thunder(g=1.0, d=3.5, seed=3):
    r = np.random.default_rng(seed)
    t = tt(d)
    x = lp(np.cumsum(r.standard_normal(len(t))) * 0.02, 400)
    x = x - lp(x, 25)
    crack = hp(r.standard_normal(len(t)), 1500) * np.exp(-t * 18) * 0.25
    e = np.exp(-t * 1.1) * (0.6 + 0.4 * np.abs(np.sin(t * 7 + r.random())))
    y = (x / (np.abs(x).max() + 1e-9) + crack) * e
    return reverb(y, 2.5, 0.35, 2500) * g


def rising_hum(d, g=1.0):
    t = tt(d)
    k = t / d
    x = np.zeros_like(t)
    for m, a in [(45, 0.5), (52, 0.35), (57, 0.3), (64, 0.2), (69, 0.12)]:
        f = mtof(m) * (1 + 0.5 * k ** 1.5)
        x += osc('sin', f, d) * a
    x *= (0.7 + 0.3 * np.sin(2 * np.pi * (4 + 14 * k) * t)) * (0.15 + 0.85 * k ** 1.2)
    x += hp(noise(d), 4000) * 0.05 * k ** 2
    return reverb(x, 1.2, 0.25) * g


def fizzle(g=1.0):
    d = 1.6
    t = tt(d)
    f = 70 + 700 * np.exp(-t * 3.5)
    x = osc('saw', f, d) * 0.4 * np.exp(-t * 1.8)
    x = lp(x, 1800)
    cr = np.zeros_like(t)
    r = np.random.default_rng(9)
    for k in range(40):
        i = int(r.random() ** 1.5 * d * 0.8 * SR)
        n = int(0.004 * SR)
        cr[i:i + n] += r.standard_normal(n) * (1 - i / len(t))
    x += hp(cr, 2000) * 0.5
    return reverb(x, 0.8, 0.2) * g


def rumble(d, g=1.0, seed=4):
    r = np.random.default_rng(seed)
    t = tt(d)
    x = lp(np.cumsum(r.standard_normal(len(t))) * 0.01, 140)
    x = x - lp(x, 18)
    x /= np.abs(x).max() + 1e-9
    x *= 0.7 + 0.3 * np.sin(2 * np.pi * 6 * t) * np.sin(2 * np.pi * 0.7 * t)
    return x * g


def crack(g=1.0, seed=5):
    r = np.random.default_rng(seed)
    d = 0.9
    t = tt(d)
    x = np.zeros_like(t)
    for k in range(9):
        i = int((k * 0.03 + r.random() * 0.02) * SR)
        n = int(0.012 * SR)
        x[i:i + n] += r.standard_normal(n) * (1 - k / 10)
    x = hp(x, 1200) * 0.8 + lp(noise(d), 300) * np.exp(-t * 12) * 0.6
    x += sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 25) * 0.08 for f in r.uniform(2000, 6000, 5))
    return reverb(x, 1.4, 0.3) * g


def riser(d, g=1.0):
    t = tt(d)
    k = t / d
    fc = 300 * (12000 / 300) ** (k ** 1.6)
    x = varlp(noise(d), fc) * (k ** 2.2) * 0.9
    for m in (48, 55, 60, 64, 67):
        x += osc('saw', mtof(m) * (1 + 1.0 * k ** 2), d) * 0.06 * k ** 1.5
    x += osc('sin', 60 + 300 * k ** 2, d) * 0.3 * k ** 2
    return reverb(x, 1.0, 0.2) * g


def pop(g=1.0):
    d = 0.2
    f = 1400 * np.exp(-tt(d) * 25) + 300
    return osc('sin', f, d) * env(d, 0.001, 0.07) * g


def heartbeat(g=1.0):
    d = 0.7
    x = np.zeros(int(d * SR))
    for o, a in [(0, 1.0), (0.18, 0.7)]:
        b = osc('sin', 48 + 30 * np.exp(-tt(0.25) * 30), 0.25) * env(0.25, 0.004, 0.12) * a
        i = int(o * SR)
        x[i:i + len(b)] += b
    return lp(x, 300) * g


def footstep(g=1.0, seed=0):
    r = np.random.default_rng(seed + 300)
    d = 0.15
    x = bp(r.standard_normal(int(d * SR)), 200, 2500) * env(d, 0.002, 0.05)
    x += osc('sin', 90, d) * env(d, 0.002, 0.04) * 0.5
    return x * 0.4 * g


def crickets(d, g=1.0):
    t = tt(d)
    x = np.zeros_like(t)
    for f0, rate, ph in [(4300, 2.1, 0), (4700, 1.7, 1.3), (3900, 2.6, 2.1)]:
        gate = (np.sin(2 * np.pi * rate * t + ph) > 0.6) * (np.sin(2 * np.pi * 30 * t) > 0)
        x += np.sin(2 * np.pi * f0 * t) * lp(gate.astype(float), 300) * 0.08
    return x * np.interp(t, [0, 1, d - 1, d], [0, 1, 1, 0]) * g


# ============================================================ crowd reactions (layered kid voices via Kokoro)
class Crowd:
    VOICES = ['af_bella', 'af_sky', 'am_puck', 'am_echo', 'af_nova', 'bf_lily', 'am_liam', 'af_jessica', 'am_adam', 'af_heart']

    def __init__(self, models):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(os.path.join(models, 'kokoro-q8.onnx'), os.path.join(models, 'voices.bin'))
        self.cache = {}

    def line(self, text, voice, pitch, speed=1.0):
        key = (text, voice, pitch, speed)
        if key not in self.cache:
            x, sr = self.k.create(text, voice=voice, speed=speed, lang='en-us')
            with tempfile.TemporaryDirectory() as d:
                a, b = os.path.join(d, 'a.wav'), os.path.join(d, 'b.wav')
                sf.write(a, np.asarray(x, np.float32), sr)
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', a, '-af',
                                f'rubberband=pitch={pitch}:formant=shifted:pitchq=quality', '-ar', str(SR), '-ac', '1', b], check=True)
                y, _ = sf.read(b)
            y = np.nan_to_num(y)
            y /= np.abs(y).max() + 1e-9
            self.cache[key] = y
        return self.cache[key]

    def group(self, texts, n, spread, seed, pitch=(1.18, 1.38), speed=(0.95, 1.15), dur=None):
        r = np.random.default_rng(seed)
        out = np.zeros((int((spread + 3.0) * SR), 2))
        for k in range(n):
            v = self.VOICES[k % len(self.VOICES)]
            y = self.line(texts[k % len(texts)], v, round(float(r.uniform(*pitch)), 2), round(float(r.uniform(*speed)), 2))
            if dur:
                y = y[:int(dur * SR)] * np.interp(np.arange(min(len(y), int(dur * SR))), [0, int(dur * SR) * 0.8, int(dur * SR)], [1, 1, 0])
            i = int(r.uniform(0, spread) * SR)
            y = st(y * r.uniform(0.5, 1.0), r.uniform(-0.8, 0.8))
            n_ = min(len(y), len(out) - i)
            out[i:i + n_] += y[:n_]
        return reverb(out, 1.1, 0.25)


def gasp_noise(g=1.0, n=10, seed=6):
    r = np.random.default_rng(seed)
    out = np.zeros((int(1.0 * SR), 2))
    for k in range(n):
        d = r.uniform(0.25, 0.45)
        t = tt(d)
        x = bp(r.standard_normal(len(t)), 900 + r.random() * 600, 3500) * np.interp(t, [0, d * 0.7, d], [0, 1, 0]) ** 1.5
        i = int(r.uniform(0, 0.12) * SR)
        y = st(x * r.uniform(0.4, 1.0), r.uniform(-0.8, 0.8))
        out[i:i + len(y)] += y[:len(out) - i]
    return reverb(out, 0.9, 0.2) * g


# ============================================================ music
BEAT = 0.5          # 120 BPM
BAR = 2.0
PROG = [[48, 60, 64, 67], [43, 59, 62, 67], [45, 60, 64, 69], [41, 60, 65, 69]]   # C G Am F (bass + triad)
ARP = [[76, 79, 84, 79, 76, 79, 81, 79], [74, 79, 83, 79, 74, 79, 81, 83],
       [72, 76, 81, 76, 72, 76, 79, 76], [77, 81, 84, 81, 79, 77, 76, 74]]


def groove(mus, t0, bars, style):
    """Upbeat game groove anchored at t0 (bar grid)."""
    for b in range(bars):
        tb = t0 + b * BAR
        ch = PROG[b % 4]
        for s in range(8):          # eighth notes
            ts = tb + s * BEAT / 2
            if s % 4 == 0:
                mus.add(kick(0.9), ts)
            if style in ('town', 'yellow', 'gold') and s % 4 == 2:
                mus.add(clap(0.55) if style != 'gold' else snare(0.6), ts)
            if style == 'purple' and b >= 2 and s % 4 == 2:
                mus.add(clap(0.4), ts)
            mus.add(hat(0.5 if s % 2 else 0.8), ts, pan=0.3)
            if style == 'yellow':
                mus.add(hat(0.35), ts + BEAT / 4, pan=0.35)
            # bass: root, octave bounce
            mus.add(bass_note(ch[0] + (12 if s % 2 else 0), BEAT / 2 * 0.9, 0.55), ts)
            # arp
            m = ARP[b % 4][s]
            if style == 'purple':
                mus.add(bell(m + 12, 0.6, 0.12), ts, pan=-0.3)
            mus.add(pluck(m, 0.22, 0.16 if style != 'yellow' else 0.2), ts, pan=-0.2 + 0.4 * (s % 2))
        if style == 'gold':
            for s in (0, 3, 6):
                mus.add(brass(ch[1:], 0.4, 0.33), tb + s * BEAT / 2)
        else:
            mus.add(pad(ch[1:], BAR, 0.18, cutoff=1800, attack=0.15, release=0.3), tb)


def build_music(ev):
    mus = Bus()
    # ---- 0-5 hook: shimmering intro on C maj9, arpeggio, soft swell into the groove
    mus.add(pad([60, 64, 67, 71, 74], 5.2, 0.32, cutoff=2600, attack=0.4, release=0.6), 0.0)
    for k in range(16):
        m = [72, 76, 79, 83, 86, 83, 79, 76][k % 8]
        mus.add(bell(m, 0.7, 0.14), 0.25 * k + 0.0, pan=-0.4 + 0.8 * (k % 2))
    for k in range(4):
        mus.add(kick(0.35 + 0.1 * k), 2.0 + k * 0.5)
    mus.add(riser(1.0, 0.25), 4.0)
    # ---- 4-36 upbeat tiers (bar grid anchored at 4.0 -> scene cuts at 12, 20, 28, 36 land on bar lines)
    groove(mus, 4.0, 4, 'town')
    groove(mus, 12.0, 4, 'purple')
    groove(mus, 20.0, 4, 'yellow')
    groove(mus, 28.0, 4, 'gold')
    for tc in (5.0, 12.0, 20.0, 28.0):
        mus.add(crash(0.45), tc)
    mus.add(choir([60, 64, 67], 4.0, 0.35), 32.0)
    # ---- 36-46 black: dark drone, tritone bell motif, slow pulse
    mus.add(pad([33, 45, 48, 51], 10.2, 0.55, cutoff=700, attack=0.05, release=1.0), 36.0)
    mus.add(choir([57, 60, 63], 9.0, 0.22), 36.6)
    for k, m in enumerate([69, 75, 72, 68, 69, 75, 76, 75]):
        mus.add(bell(m, 1.6, 0.15, ratio=1.41, idx=3), 37.0 + k * 1.1, pan=-0.5 + (k % 2))
    for k in range(9):
        mus.add(timpani(0.35, 33), 36.0 + k * 1.1)
    # ---- 46-54 walk: tense and quiet
    for b, ch in enumerate([[45, 57, 60, 64], [41, 57, 60, 65], [38, 57, 62, 65], [40, 56, 59, 64]]):
        tb = 46.0 + b * 2.0
        mus.add(pad(ch[1:], 2.1, 0.2, cutoff=1200, attack=0.4, release=0.4), tb)
        mus.add(bass_note(ch[0], 1.9, 0.35), tb)
        for s in range(8):
            mus.add(pluck(ch[1 + s % 3] + 12, 0.12, 0.06, kind='tri'), tb + s * 0.25, pan=0.3)
    # ---- 54-62 touch: hold tension, cut to silence on the fizzle, sad sting after
    mus.add(pad([57, 60, 64, 69], ev['tDark'] - 54.0, 0.22, cutoff=1500, attack=0.2, release=0.1), 54.0)
    for k, m in enumerate([72, 71, 69, 68]):
        mus.add(piano(m, 1.4, 0.25), ev['tDark'] + 0.55 + k * 0.42)
    mus.add(pad([45, 52, 57, 60], 62.0 - ev['tLaugh'], 0.12, cutoff=900, attack=1.0, release=1.0), ev['tLaugh'])
    # ---- 62-70 sunset: soft sad piano
    chords = [[45, 57, 60, 64], [41, 57, 60, 65], [36, 55, 60, 64], [43, 55, 59, 62]]
    mel = [(0, 76, 1.0), (1.0, 74, 0.5), (1.5, 72, 0.5), (2.0, 72, 1.0), (3.0, 69, 1.0), (4.0, 67, 1.5),
           (5.5, 69, 0.5), (6.0, 71, 1.0), (7.0, 67, 1.0)]
    for b, ch in enumerate(chords):
        tb = 62.0 + b * 2.0
        mus.add(pad(ch[1:], 2.2, 0.16, cutoff=1300, attack=0.6, release=0.6, kind='tri'), tb)
        mus.add(piano(ch[0] + 12, 2.0, 0.25), tb)
        for s in (0, 1, 2, 3):
            mus.add(piano(ch[1 + s % 3], 1.0, 0.1), tb + s * 0.5, pan=-0.2)
    for o, m, d in mel:
        mus.add(piano(m, d + 0.8, 0.22), 62.0 + o, pan=0.15)
    # ---- 70-78 build
    mus.add(pad([33, 40, 45], 8.2, 0.4, cutoff=500, attack=0.1, release=0.2), 70.0)
    t = tt(8.0)
    strings = sum(osc('saw', mtof(m) * (1 + 0.5 * (t / 8) ** 2), 8.0) for m in (57, 64, 69)) / 3
    strings = lp(strings, 2500) * (0.05 + 0.3 * (t / 8) ** 2)
    mus.add(strings, 70.0, 0.9)
    for k in range(8):
        mus.add(timpani(0.5 + 0.06 * k, 33), 70.0 + k * 1.0)
    roll_t = 75.0
    while roll_t < 77.95:
        k = (roll_t - 75.0) / 3.0
        mus.add(snare(0.15 + 0.35 * k), roll_t)
        roll_t += 0.25 * (1 - 0.75 * k)
    # ---- 78-90 epic finale: big chords, choir, drums, arps
    prog = [[48, 60, 64, 67, 72], [43, 59, 62, 67, 71], [45, 60, 64, 69, 72], [41, 60, 65, 69, 72]]
    for b in range(5):
        tb = 78.0 + b * 2.0
        ch = prog[b % 4]
        last = b == 4
        dur = 2.0 if not last else 4.0
        mus.add(brass(ch[1:], dur, 0.38), tb)
        mus.add(choir(ch[1:4], dur + 0.4, 0.4), tb)
        mus.add(bass_note(ch[0], dur * 0.95, 0.6), tb)
        mus.add(bass_note(ch[0] - 12, dur * 0.95, 0.35), tb)
        if not last:
            for s in range(8):
                ts = tb + s * BEAT / 2
                if s % 2 == 0:
                    mus.add(kick(1.0), ts)
                if s % 4 == 2:
                    mus.add(snare(0.7), ts)
                mus.add(hat(0.6), ts + BEAT / 4, pan=0.3)
                mus.add(pluck(ARP[b % 4][s] + 12, 0.2, 0.14), ts, pan=-0.3 + 0.6 * (s % 2))
                mus.add(pluck(ARP[b % 4][s], 0.2, 0.1), ts + BEAT / 4, pan=0.3 - 0.6 * (s % 2))
    mus.add(crash(0.8), 78.0)
    mus.add(crash(0.5), 82.0)
    mus.add(crash(0.6), 86.0)
    mus.add(timpani(0.9, 36), 86.0)
    # final chord when the end card lands
    mus.add(brass([60, 64, 67, 72, 76], 2.2, 0.45), ev['tCard'])
    mus.add(choir([60, 64, 67, 72], 2.1, 0.45), ev['tCard'])
    mus.add(kick(1.0), ev['tCard'])
    mus.add(crash(0.7), ev['tCard'])
    mus.add(shimmer(2.0, 0.5, 86, seed=5), ev['tCard'])
    m = mus.b
    m = reverb(m, 1.4, 0.18)[:N]
    # gentle fade at the very end so nothing is cut off
    m[-int(0.6 * SR):] *= np.linspace(1, 0, int(0.6 * SR))[:, None] ** 2
    return m


# ============================================================ events (mirror web/scenes.js)
def word_time(timing, lid, prefix, fallback):
    for L in timing['lines']:
        if L['id'] == lid:
            for c in L['chunks']:
                for w in c['words']:
                    if ''.join(ch for ch in w['w'].lower() if ch.isalnum() or ch == "'").startswith(prefix):
                        return w['t']
    return fallback


def events(timing):
    ev = {}
    ev['tColor'] = word_time(timing, 'L01', 'color', 2.1)
    ev['tThat'] = word_time(timing, 'L05', 'that', 16.0)
    ev['tCrate'], ev['tDrop'] = ev['tThat'] - 1.25, ev['tThat'] + 0.15
    ev['tDash'], ev['tTag0'], ev['tTag1'] = 21.9, 22.55, 24.15
    ev['shots'], ev['tUp'] = [29.45, 30.05, 30.65], 32.7
    ev['tGasp'] = 38.1
    ev['tTouch'] = 54.95
    ev['tDark'] = word_time(timing, 'L15', 'nothing', 56.4) - 0.05
    ev['tLaugh'] = ev['tDark'] + 1.25
    ev['tBoom'] = 78.0
    ev['tCrowdShot'], ev['tHero'] = 80.55, 82.5
    ev['tCard'] = 88.05
    return ev


def build_sfx(ev, crowd):
    fx = Bus()
    A = fx.add
    # hook: whoosh + rainbow shimmer
    A(whoosh(0.8, 200, 6000, 0.7), 0.0)
    A(shimmer(3.0, 0.8, 84, seed=1), 0.05)
    A(shimmer(1.6, 0.5, 88, seed=2), ev['tColor'] - 0.1)
    # scene-cut whooshes
    for tc in (5.0, 12.0, 20.0, 28.0, 86.0):
        A(whoosh(0.55, 400, 5000, 0.45), tc - 0.35)
    # town: flyers zipping past
    for k, tz in enumerate([5.8, 7.0, 8.3]):
        A(whoosh(0.5, 800, 7000, 0.18, rev=False), tz, pan=(-0.6, 0.6, 0)[k])
    for k, tz in enumerate([8.55, 9.5, 10.45, 11.4]):          # line-up passes each kid
        A(chime(0.12, seed=k), tz)
    # purple: magical hum + blocks clinking
    A(magic_hum(ev['tDrop'] + 0.6 - 12.0, 0.45), 12.0)
    for i in range(7):
        A(bell(86 + i * 2, 0.5, 0.12), 12.25 + i * 0.1, pan=-0.6 + i * 0.2)
        A(clink(0.5, seed=i), 13.0 + i * 0.37, pan=-0.5 + i * 0.15)
    A(thud(0.5), ev['tCrate'] + 0.1)
    for i in range(7):
        land = ev['tDrop'] + i * 0.04 + 0.45
        A(clink(1.0, seed=10 + i), land, pan=-0.6 + i * 0.2)
        A(clink(0.45, seed=20 + i), land + 0.17, pan=-0.6 + i * 0.2)
    A(thud(0.8), ev['tDrop'] + 0.05)
    # yellow: zoom / swoosh
    A(zap(0.25, up=True), 21.2)
    A(whoosh(0.6, 600, 9000, 1.0), ev['tDash'] - 0.1)
    for i in range(3):
        A(whoosh(0.35, 900, 8000, 0.55, rev=False), ev['tTag0'] + 0.25 + i * 0.42, pan=(-0.5, 0.5, 0)[i])
        A(pop(0.35), ev['tTag0'] + 0.35 + i * 0.42)
    A(whoosh(0.4, 1500, 6000, 0.4), ev['tTag1'] - 0.15)
    # gold: energy blasts + sparkle chimes + cheering
    for k, ts in enumerate(ev['shots']):
        A(blast(0.8), ts - 0.05, pan=(-0.2, 0.2, 0)[k])
        A(explosion(0.35, 1.2), ts + 0.5)
        A(chime(0.6, seed=k), ts + 0.5)
    A(blast(0.9), ev['tUp'] - 0.05)
    A(explosion(0.6, 2.0), ev['tUp'] + 0.75)
    A(shimmer(3.0, 0.9, 86, seed=7), ev['tUp'] + 0.75)
    A(chime(0.7, seed=9), ev['tUp'] + 0.8)
    A(crowd.group(['Yay!', 'Woo hoo!', 'Yeah!', 'Go go!', 'Wooo!'], 10, 1.4, seed=1), 31.0, 0.45)
    A(crowd.group(['Yay!', 'Woooo!', 'Yeah!'], 8, 1.0, seed=2), ev['tUp'] + 0.9, 0.45)
    # black: deep bass hit + thunder + crowd gasp
    A(bass_hit(1.0), 36.0)
    A(thunder(0.8, seed=3), 36.05)
    A(gasp_noise(0.8), ev['tGasp'] - 0.15)
    A(crowd.group(['Oh!', 'Huh!', 'Ah!'], 8, 0.18, seed=3, dur=0.5), ev['tGasp'] - 0.05, 0.35)
    A(thunder(0.6, seed=4), 41.6)
    A(bass_hit(0.5, 2.0), 41.6)
    # walk: footsteps + heartbeat
    t = 46.2
    while t < 53.3:
        A(footstep(0.6, seed=int(t * 10)), t, pan=0.1)
        t += 0.71
    for k in range(7):
        A(heartbeat(0.55 + 0.05 * k), 49.6 + k * 0.72)
    # touch: rising hum -> power-down fizzle -> kids laughing
    A(bell(96, 0.6, 0.25), ev['tTouch'])
    A(rising_hum(ev['tDark'] - ev['tTouch'] + 0.05, 0.8), ev['tTouch'])
    A(fizzle(1.0), ev['tDark'])
    A(crowd.group(['Ha ha ha ha ha!', 'Hahaha!', 'Ha ha ha!', 'Hee hee hee!', 'Ha ha!'], 12, 1.8, seed=4, pitch=(1.2, 1.4)), ev['tLaugh'] - 0.1, 0.55)
    A(crowd.group(['Ha ha ha!', 'Hahaha!'], 6, 1.2, seed=5, pitch=(1.2, 1.4)), ev['tLaugh'] + 1.6, 0.35)
    # sunset: evening ambience
    A(crickets(8.0, 0.35), 62.0)
    A(lp(noise(8.0), 500) * 0.05 * np.interp(tt(8.0), [0, 2, 6, 8], [0, 1, 1, 0]), 62.0)
    # quake: rumble + cracking crystal + riser into the explosion
    rd = 78.0 - 70.0
    A(rumble(rd, 1.0) * np.interp(tt(rd), [0, 0.3, 5, rd], [0, 0.7, 0.8, 1.0]), 70.0)
    A(bass_hit(0.6, 2.0), 70.0)
    for k, tc in enumerate([71.35, 72.2, 73.05, 75.6, 76.4, 77.1]):
        A(crack(0.7 + 0.05 * k, seed=k), tc, pan=(-0.3, 0.3, 0, -0.2, 0.2, 0)[k])
    A(riser(78.0 - 75.0, 1.0), 75.0)
    A(shimmer(2.5, 0.5, 80, seed=11), 75.6)
    # 78: explosion + sparkle burst, crowd "whoa", hero zoom
    A(explosion(1.0, 3.0), ev['tBoom'])
    A(shimmer(4.0, 1.0, 82, seed=12), ev['tBoom'])
    A(chime(0.8, seed=13), ev['tBoom'] + 0.05)
    A(crowd.group(['Whoa!', 'Woah!', 'No way!', 'Wow!'], 10, 0.5, seed=6, dur=0.9), 79.65, 0.5)
    A(whoosh(0.5, 300, 6000, 0.5), ev['tHero'] - 0.3)
    A(shimmer(3.5, 0.5, 84, seed=14), 82.4)
    # end: whoosh + pop as the end card appears
    A(whoosh(0.6, 300, 7000, 0.8), ev['tCard'] - 0.45)
    A(pop(0.9), ev['tCard'] + 0.02)
    A(pop(0.6), ev['tCard'] + 0.14)
    A(pop(0.6), ev['tCard'] + 0.32)
    return fx.b


# ============================================================ mix
def follower(x, attack=0.02, release=0.35):
    m = np.abs(x).max(1) if x.ndim == 2 else np.abs(x)
    m = signal.sosfilt(sos('low', 30), m)
    m = np.maximum(m, 0)
    out = np.empty_like(m)
    a_at, a_rel = np.exp(-1 / (attack * SR)), np.exp(-1 / (release * SR))
    s = 0.0
    for i in range(len(m)):   # fast enough at 48 kHz x 90 s with plain floats
        v = m[i]
        s = a_at * s + (1 - a_at) * v if v > s else a_rel * s + (1 - a_rel) * v
        out[i] = s
    return out


def limiter(x, ceiling_db=-1.5, look=0.005, release=0.08):
    """Look-ahead peak limiter; peaks are measured 4x oversampled so true peaks stay under the ceiling."""
    from scipy.ndimage import minimum_filter1d
    c = 10 ** (ceiling_db / 20)
    over = signal.resample_poly(x, 4, 1, axis=0)
    pk = np.abs(over).max(1)[:len(x) * 4].reshape(-1, 4).max(1)
    need = np.minimum(1.0, c / np.maximum(pk, 1e-9))
    L = int(look * SR)
    g = minimum_filter1d(need, size=2 * L + 1)          # gain reaches its target before the peak arrives
    a = np.exp(-1 / (release * SR))
    sm = np.empty_like(g)
    s = 1.0
    for i in range(len(g)):                              # instant attack, smooth release
        s = g[i] if g[i] < s else a * s + (1 - a) * g[i]
        sm[i] = s
    sm = minimum_filter1d(sm, size=L + 1)
    return x * np.minimum(sm, 1.0)[:, None]


def true_peak_db(x):
    over = signal.resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.abs(over).max() + 1e-12)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', required=True)
    ap.add_argument('--build', default='build')
    ap.add_argument('--lufs', type=float, default=-14.0)
    a = ap.parse_args()
    timing = json.load(open(os.path.join(a.build, 'timing.json')))
    ev = events(timing)
    vo, sr = sf.read(os.path.join(a.build, 'vo.wav'))
    assert sr == SR and len(vo) == N, (sr, len(vo))
    vo = st(vo)
    print('music...', flush=True)
    music = build_music(ev)
    print('sfx...', flush=True)
    crowd = Crowd(a.models)
    fx = build_sfx(ev, crowd)
    meter = pyln.Meter(SR)
    # level the stems: music bed well under the voice, SFX in between
    music *= 10 ** ((-25.0 - meter.integrated_loudness(music)) / 20)
    fx *= 10 ** ((-24.0 - meter.integrated_loudness(fx)) / 20)
    # music: carve a little room for the voice
    music = music - bp(music, 1800, 3500, 1) * 0.3
    # duck music (and a bit of SFX) under the voice
    e = follower(vo, 0.03, 0.4)
    e = np.clip(e / (np.percentile(e[e > 1e-4], 90) + 1e-9), 0, 1)
    duck_m = 1 - 0.55 * e        # ~ -7 dB while talking
    duck_f = 1 - 0.3 * e
    sf.write(os.path.join(a.build, 'music.wav'), music.astype(np.float32), SR, subtype='FLOAT')
    sf.write(os.path.join(a.build, 'sfx.wav'), fx.astype(np.float32), SR, subtype='FLOAT')
    mix = vo * 1.0 + music * duck_m[:, None] + fx * duck_f[:, None]
    # loudness normalize + true-peak limit (iterate: limiting lowers loudness a little)
    g = 10 ** ((a.lufs - meter.integrated_loudness(mix)) / 20)
    for it in range(4):
        out = limiter(mix * g)
        lufs = meter.integrated_loudness(out)
        if abs(lufs - a.lufs) < 0.1:
            break
        g *= 10 ** ((a.lufs - lufs) / 20)
    out = out[:N]
    assert len(out) == N
    tp = true_peak_db(out)
    sf.write(os.path.join(a.build, 'mix.wav'), out.astype(np.float32), SR, subtype='FLOAT')
    vo_l = meter.integrated_loudness(vo * g)
    print(f'mix: {len(out)} samples = {len(out) / SR:.6f} s, integrated {lufs:.2f} LUFS, true peak {tp:.2f} dBTP, '
          f'sample peak {20 * np.log10(np.abs(out).max()):.2f} dBFS, voice stem {vo_l:.1f} LUFS')


if __name__ == '__main__':
    main()
