"""Builds the full 120 s soundtrack: TTS voiceover, original synthesized music
and synthesized sound effects. Writes build/audio.wav + build/vo_timing.json.

usage: python src/audio.py --voices <dir with kokoro-v1.0.onnx + voices-v1.0.bin> --out build
"""
import argparse
import io
import json
import math
import os
import random
import re
import subprocess
import tempfile
import wave

import numpy as np
from scipy import signal
from scipy.io import wavfile

from script_data import LINES, TITLES, DURATION

SR = 48000
N = int(round(DURATION * SR))
rng = np.random.default_rng(7)

# ===================================================================== DSP utils


def tt(d):
    return np.arange(int(d * SR)) / SR


def sos(kind, f, order=2):
    if kind == 'bp':
        return signal.butter(order, [f[0] / (SR / 2), f[1] / (SR / 2)], 'bandpass', output='sos')
    return signal.butter(order, f / (SR / 2), kind, output='sos')


def lp(x, f, o=2):
    return signal.sosfilt(sos('low', f, o), x, axis=0)


def hp(x, f, o=2):
    return signal.sosfilt(sos('high', f, o), x, axis=0)


def bp(x, lo, hi, o=2):
    return signal.sosfilt(sos('bp', (lo, hi), o), x, axis=0)


def noise(d):
    return rng.standard_normal(int(d * SR))


def env_exp(d, k, attack=0.002):
    t = tt(d)
    e = np.exp(-t * k)
    a = int(attack * SR)
    if a > 0:
        e[:a] *= np.linspace(0, 1, a)
    return e


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def sweep_sine(f, d):
    """f: array of instantaneous freq (len = d*SR) or callable(t)."""
    t = tt(d)
    fr = f(t) if callable(f) else f
    return np.sin(2 * np.pi * np.cumsum(fr) / SR)


def saw(f, d, detune=0.0):
    t = tt(d)
    ph = (t * f * (1 + detune) + rng.random()) % 1.0
    return 2 * ph - 1


def stereo(x, pan=0.0):
    l = math.cos((pan + 1) * math.pi / 4)
    r = math.sin((pan + 1) * math.pi / 4)
    return np.stack([x * l * 1.414, x * r * 1.414], 1)


_ir_cache = {}


def reverb(x, decay=1.6, mix=0.3, pre=0.02, bright=4000):
    key = (decay, bright)
    if key not in _ir_cache:
        d = decay * 1.5
        t = tt(d)
        ir = np.stack([rng.standard_normal(len(t)), rng.standard_normal(len(t))], 1)
        ir *= np.exp(-t * 6.9 / decay)[:, None]
        ir = lp(ir, bright)
        ir = np.concatenate([np.zeros((int(pre * SR), 2)), ir])
        ir /= np.sqrt((ir ** 2).sum(0, keepdims=True))
        _ir_cache[key] = ir
    ir = _ir_cache[key]
    if x.ndim == 1:
        x = stereo(x)
    wet = np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x) + len(ir) - 1] for c in range(2)], 1)
    dry = np.concatenate([x, np.zeros((len(ir) - 1, 2))])
    return dry * (1 - mix) + wet * mix * 1.4


class Bus:
    def __init__(self):
        self.b = np.zeros((N, 2))

    def add(self, x, t, gain=1.0, pan=0.0):
        if x.ndim == 1:
            x = stereo(x, pan)
        i = int(round(t * SR))
        if i < 0:
            x = x[-i:]
            i = 0
        if i >= N:
            return
        n = min(len(x), N - i)
        self.b[i:i + n] += x[:n] * gain


# ===================================================================== SFX


def sfx_bass_hit(big=1.0):
    d = 3.0
    t = tt(d)
    f = 28 + 95 * np.exp(-t * 14)
    x = sweep_sine(f, d) * np.exp(-t * 1.3) * 1.0
    x += lp(noise(d), 3000) * np.exp(-t * 40) * 0.6
    x += bp(noise(d), 60, 400) * np.exp(-t * 4) * 0.8
    x = np.tanh(x * 1.8 * big) * 0.9
    return reverb(x, 2.2, 0.25)


def sfx_call_dropped():
    out = np.zeros(int(0.75 * SR))
    for k, f in enumerate((960, 720, 480)):
        d = 0.14
        t = tt(d)
        tone = np.sign(np.sin(2 * np.pi * f * t)) * 0.3 + np.sin(2 * np.pi * f * t) * 0.7
        tone *= np.minimum(1, np.minimum(t / 0.004, (d - t) / 0.004))
        i = int(k * 0.21 * SR)
        out[i:i + len(tone)] += tone
    return bp(out, 300, 3400) * 0.55


def sfx_heartbeat(gain=1.0):
    d = 0.55
    out = np.zeros(int(d * SR))
    for off, f, g in ((0.0, 58, 1.0), (0.24, 50, 0.7)):
        t = tt(0.25)
        x = np.sin(2 * np.pi * (f + 25 * np.exp(-t * 30)) * t) * np.exp(-t * 18) * g
        x += lp(noise(0.25), 150) * np.exp(-t * 25) * 0.6 * g
        i = int(off * SR)
        out[i:i + len(x)] += x
    return np.tanh(out * 2) * 0.8 * gain


def sfx_footstep(heavy=1.0, seed=None):
    d = 0.35
    t = tt(d)
    x = np.sin(2 * np.pi * (60 + 40 * np.exp(-t * 40)) * t) * np.exp(-t * 28) * heavy
    x += bp(noise(d), 150, 1600) * np.exp(-t * 45) * 0.7
    x += hp(noise(d), 2500) * np.exp(-t * 90) * 0.15
    return reverb(x * 0.9, 0.7, 0.18)


def sfx_creak(d=1.4, base=170, seed=0):
    r = np.random.default_rng(seed)
    t = tt(d)
    wob = np.cumsum(r.standard_normal(len(t))) / SR * 40
    f = base + 70 * np.sin(2 * np.pi * 0.6 * t + 1) + wob + 60 * t / d
    ph = np.cumsum(f) / SR
    x = (ph % 1.0) * 2 - 1
    am = 0.6 + 0.4 * np.sin(2 * np.pi * (11 + 4 * np.sin(t * 3)) * t)
    x = bp(x * am, 350, 3200)
    x += bp(x, 900, 1300) * 2
    e = np.minimum(1, t / 0.08) * np.minimum(1, (d - t) / 0.25)
    return reverb(x * e * 0.35, 1.0, 0.25)


def sfx_dtmf(digit):
    low = {'9': 852, '1': 697}[digit]
    high = {'9': 1477, '1': 1209}[digit]
    t = tt(0.17)
    x = (np.sin(2 * np.pi * low * t) + np.sin(2 * np.pi * high * t)) * 0.25
    x *= np.minimum(1, np.minimum(t / 0.005, (0.17 - t) / 0.005))
    return x


def sfx_ringback(d=1.4):
    t = tt(d)
    x = (np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)) * 0.18
    x *= np.minimum(1, np.minimum(t / 0.01, (d - t) / 0.01))
    return bp(x, 300, 3400)


def sfx_click(f=2500, d=0.04, g=0.5):
    t = tt(d)
    return (bp(noise(d), f * 0.6, min(f * 1.8, 20000)) * np.exp(-t * 160) + np.sin(2 * np.pi * f * t) * np.exp(
        -t * 90) * 0.4) * g


def sfx_gasp():
    d = 0.6
    t = tt(d)
    e = np.minimum(1, t / 0.18) ** 2 * np.exp(-np.maximum(0, t - 0.2) * 12)
    x = bp(noise(d), 600, 2600) * e
    x += bp(noise(d), 1100, 1500, 2) * e * 1.5
    return x * 0.5


def sfx_smash():
    d = 1.6
    t = tt(d)
    x = np.tanh(noise(d) * 3) * np.exp(-t * 22) * 0.8
    x += np.sin(2 * np.pi * (110 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 15)
    for _ in range(40):
        f = rng.uniform(2500, 8000)
        st = rng.uniform(0.0, 0.7)
        tt_ = tt(0.12)
        ping = np.sin(2 * np.pi * f * tt_) * np.exp(-tt_ * rng.uniform(30, 70)) * rng.uniform(0.05, 0.25)
        i = int(st * SR)
        x[i:i + len(ping)] += ping
    return reverb(x, 1.2, 0.25)


def sfx_siren(d=10.0):
    t = tt(d)
    f = 720 + 520 * (0.5 - 0.5 * np.cos(2 * np.pi * t / 2.6))
    f2 = 690 + 500 * (0.5 - 0.5 * np.cos(2 * np.pi * (t + 0.7) / 2.4))
    x = 0
    for ff, g in ((f, 1.0), (f2, 0.7)):
        ph = 2 * np.pi * np.cumsum(ff) / SR
        x = x + g * (np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph))
    x = bp(x, 400, 4000) * 0.22
    return x


def sfx_door_bash():
    d = 2.0
    t = tt(d)
    x = np.sin(2 * np.pi * (45 + 60 * np.exp(-t * 20)) * t) * np.exp(-t * 6) * 1.2
    x += np.tanh(bp(noise(d), 200, 5000) * 4) * np.exp(-t * 18) * 0.7
    for _ in range(12):
        st = rng.uniform(0.02, 0.5)
        y = bp(noise(0.08), 1500, 6000) * env_exp(0.08, 50) * rng.uniform(0.1, 0.4)
        i = int(st * SR)
        x[i:i + len(y)] += y
    return reverb(np.tanh(x * 1.5), 1.6, 0.3)


def sfx_cuffs():
    out = np.zeros(int(0.7 * SR))
    for k in range(9):
        c = sfx_click(3200 + k * 40, 0.05, 0.35)
        i = int((0.12 + k * 0.035) * SR)
        out[i:i + len(c)] += c
    c = sfx_click(2600, 0.08, 0.7)
    out[:len(c)] += c
    i = int(0.5 * SR)
    c = sfx_click(2400, 0.08, 0.7)
    out[i:i + len(c)] += c
    t = tt(0.4)
    ring = np.sin(2 * np.pi * 4100 * t) * np.exp(-t * 14) * 0.08
    out[i:i + len(ring)] += ring[:len(out) - i]
    return reverb(out, 0.6, 0.15)


def sfx_rewind(d=1.25):
    t = tt(d)
    x = np.zeros(len(t))
    for k in range(7):
        f0 = rng.uniform(300, 1200)
        f = f0 * (1 + 4 * (t / d) ** 1.5) * (1 + 0.15 * np.sin(2 * np.pi * rng.uniform(6, 14) * t))
        x += np.sin(2 * np.pi * np.cumsum(f) / SR) * rng.uniform(0.1, 0.25)
    gate = (np.sin(2 * np.pi * 13 * t) > -0.4).astype(float)
    gate = lp(gate, 200)
    x = x * gate + hp(noise(d), 3000) * 0.15
    x += (np.sign(np.sin(2 * np.pi * 60 * t)) * (rng.random(len(t)) < 0.02)) * 0.3
    e = np.minimum(1, t / 0.03) * np.minimum(1, (d - t) / 0.05)
    return x * e * 0.6


def sfx_glitch(d=0.5):
    t = tt(d)
    steps = rng.integers(0, 2, int(d * 40))
    sq = np.repeat(steps, int(SR / 40) + 1)[:len(t)].astype(float)
    x = np.sign(np.sin(2 * np.pi * rng.uniform(80, 400) * t)) * sq * 0.25
    x += hp(noise(d), 4000) * sq * 0.2
    return x


def sfx_tick(tock=False):
    f = 1500 if tock else 1900
    return sfx_click(f, 0.05, 0.35)


def sfx_engine_away(d=3.5):
    t = tt(d)
    f = 48 * (1 - 0.3 * t / d)
    ph = np.cumsum(f) / SR
    x = ((ph % 1) * 2 - 1) + lp(noise(d), 300) * 0.8
    x = lp(x, 400) * np.exp(-t * 1.0) * np.minimum(1, t / 0.3)
    return x * 0.45


def sfx_birds(d=4.0):
    out = np.zeros(int(d * SR))
    for _ in range(9):
        st = rng.uniform(0, d - 0.5)
        n = rng.integers(2, 4)
        for k in range(n):
            dd = 0.08
            t = tt(dd)
            f = rng.uniform(2800, 4200) + 1500 * t / dd * rng.choice([-1, 1])
            ch = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / dd) * 0.08
            i = int((st + k * 0.11) * SR)
            out[i:i + len(ch)] += ch[:len(out) - i]
    return out


def sfx_riser(d=3.0):
    t = tt(d)
    k = t / d
    x = hp(noise(d), 1500) * k ** 2 * 0.25
    f = 150 + 900 * k ** 2
    x += np.sin(2 * np.pi * np.cumsum(f) / SR) * k ** 2 * 0.25
    x += np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR) * k ** 3 * 0.12
    return x


def sfx_whoosh(d=0.8):
    t = tt(d)
    e = np.sin(np.pi * t / d) ** 2
    x = bp(noise(d), 400, 3000) * e * 0.4
    return x


def sfx_rustle(d=1.0):
    t = tt(d)
    crack = (rng.random(len(t)) < 0.004).astype(float)
    crack = lp(crack, 3000) * 8
    x = hp(noise(d), 2000) * (0.15 + crack) * 0.2
    return x * np.minimum(1, np.minimum(t / 0.05, (d - t) / 0.1))


def sfx_struggle(d=1.6):
    out = np.zeros(int(d * SR))
    for k in range(5):
        c = sfx_creak(0.25, 260 + k * 30, seed=k) * 0.6
        i = int(k * 0.3 * SR)
        out[i:i + len(c)] += c[:len(out) - i, 0]
    out += bp(noise(d), 300, 2000) * 0.05
    return out


def sfx_keys():
    out = np.zeros(int(0.8 * SR))
    for k in range(7):
        c = sfx_click(rng.uniform(3500, 6000), 0.09, 0.25)
        i = int(rng.uniform(0, 0.4) * SR)
        out[i:i + len(c)] += c
    c = sfx_click(1800, 0.06, 0.8)
    i = int(0.6 * SR)
    out[i:i + len(c)] += c
    return out


def sfx_door_close():
    d = 1.0
    t = tt(d)
    x = np.sin(2 * np.pi * (70 + 40 * np.exp(-t * 30)) * t) * np.exp(-t * 12)
    x += bp(noise(d), 100, 1500) * np.exp(-t * 30) * 0.6
    return reverb(x * 0.9, 1.2, 0.3)


# ===================================================================== MUSIC

BPM = 96
BEAT = 60 / BPM
EIGHTH = BEAT / 2
BAR = BEAT * 4

MOTIF = [[69, 72, 76, 74, 72, 71, 68, 71],
         [69, 72, 76, 81, 80, 76, 74, 71],
         [69, 72, 76, 74, 72, 71, 68, 64],
         [65, 69, 72, 76, 74, 71, 68, 69]]
CHORDS_MIN = [[57, 60, 64], [53, 57, 60], [50, 53, 57], [52, 56, 59]]  # Am F Dm E
HERO = [[69, 73, 76, 74, 73, 71, 73, 76],
        [78, 76, 73, 74, 76, 73, 71, 69],
        [74, 78, 81, 78, 76, 74, 73, 74],
        [76, 80, 83, 80, 76, 74, 73, 71]]
CHORDS_MAJ = [[57, 61, 64], [54, 57, 61], [50, 54, 57], [52, 56, 59]]  # A F#m D E


def musicbox(m, d=1.6, wobble=0.004):
    t = tt(d)
    f = mtof(m) * (1 + wobble * np.sin(2 * np.pi * 0.35 * t + rng.random() * 6))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.35 * np.sin(2 * ph) * np.exp(-t * 6) + 0.12 * np.sin(5.4 * ph) * np.exp(-t * 14)
    return x * env_exp(d, 3.2, 0.002) * 0.3


def pad(ms, d, cutoff=1400, detune=0.006, attack=0.6):
    x = 0
    for m in ms:
        for dt in (-detune, 0, detune):
            x = x + saw(mtof(m), d, dt)
    x = lp(x / (3 * len(ms)), cutoff)
    t = tt(d)
    e = np.minimum(1, t / attack) * np.minimum(1, (d - t) / 0.5)
    return x * e * 0.5


def bass_note(m, d, cutoff=380, drive=1.0):
    x = saw(mtof(m), d) + 0.5 * np.sin(2 * np.pi * mtof(m) * tt(d))
    x = lp(x, cutoff)
    x = np.tanh(x * drive * 1.5)
    t = tt(d)
    return x * np.minimum(1, t / 0.005) * np.exp(-t * 2.0) * 0.45


def kick(g=1.0):
    d = 0.4
    t = tt(d)
    x = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t * 35)) / SR) * np.exp(-t * 9)
    return np.tanh(x * 2) * 0.7 * g


def snare(g=1.0):
    d = 0.25
    t = tt(d)
    x = bp(noise(d), 1200, 7000) * np.exp(-t * 22) * 0.6 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.5
    return x * g


def hat(g=1.0):
    d = 0.06
    t = tt(d)
    return hp(noise(d), 7000) * np.exp(-t * 80) * 0.25 * g


def taiko(g=1.0):
    d = 0.9
    t = tt(d)
    x = np.sin(2 * np.pi * np.cumsum(55 + 50 * np.exp(-t * 25)) / SR) * np.exp(-t * 5)
    x += lp(noise(d), 600) * np.exp(-t * 20) * 0.5
    return np.tanh(x * 1.6) * 0.8 * g


def brass(ms, d):
    x = 0
    t = tt(d)
    for m in ms:
        for dt in (-0.004, 0.004):
            x = x + saw(mtof(m), d, dt)
    x = x / (2 * len(ms))
    bright = lp(x, 3200)
    dark = lp(x, 700)
    fe = np.exp(-t * 3)
    y = bright * fe + dark * (1 - fe)
    return y * np.minimum(1, t / 0.03) * np.minimum(1, (d - t) / 0.08) * 0.7


def strings_trem(ms, d, rate=12):
    t = tt(d)
    x = pad(ms, d, cutoff=2400, attack=0.3)
    return x * (0.6 + 0.4 * np.sin(2 * np.pi * rate * t))


def build_music():
    mus = Bus()

    def melody_bars(t0, t1, bars, octave=0, gain=1.0, step=EIGHTH, wob=0.004, pan_alt=True):
        t = t0
        bi = 0
        while t < t1 - 0.05:
            bar = bars[bi % len(bars)]
            for k, m in enumerate(bar):
                if t >= t1 - 0.05:
                    break
                mus.add(musicbox(m + octave, 1.6, wob), t, gain, pan=(0.25 if k % 2 else -0.25) if pan_alt else 0)
                t += step
            bi += 1

    def chords(t0, t1, prog, inst, gain, length=BAR, **kw):
        t = t0
        i = 0
        while t < t1 - 0.1:
            d = min(length, t1 - t)
            mus.add(inst(prog[i % len(prog)], d + 0.4, **kw), t, gain)
            t += length
            i += 1

    def beat(t0, t1, fn):
        t = t0
        i = 0
        while t < t1 - 0.01:
            fn(i, t)
            t += EIGHTH / 2
            i += 1

    # A: normal day (eerie music box, light beat)
    melody_bars(6.0, 19.0, MOTIF, gain=0.55)
    chords(6.0, 19.0, CHORDS_MIN, pad, 0.35)

    def light(i, t):
        if i % 8 == 0:
            mus.add(kick(0.5), t)
        if i % 16 == 8:
            mus.add(snare(0.25), t)
        if i % 2 == 0:
            mus.add(hat(0.5), t, pan=0.3)
    beat(6.0 + BAR, 19.0, light)
    # B: uneasy (slow, low)
    melody_bars(19.2, 26.4, MOTIF, octave=-12, gain=0.55, step=BEAT, wob=0.012)
    mus.add(pad([45, 46], 11.0, cutoff=500, attack=2.0), 19.2, 0.6)
    # C: dark discovery
    mus.add(pad([33, 40], 25.0, cutoff=260, attack=3.0), 30.0, 0.9)
    mus.add(pad([57, 58, 63], 17.0, cutoff=900, attack=4.0), 38.0, 0.3)
    for k in range(18):
        t = 30.4 + k * 1.35
        if 47.0 < t < 48.4:
            continue
        m = random.Random(k).choice([57, 60, 64, 62, 56, 59])
        mus.add(musicbox(m, 2.2, 0.02), t, 0.45, pan=random.Random(k).uniform(-0.6, 0.6))
    for k in range(10):  # pulse after name reveal
        t = 48.4 + k * 0.62
        mus.add(bass_note(33, 0.5, 200), t, 0.9)
    # D: tension ostinato into the closet
    t = 55.0
    k = 0
    while t < 72.55:
        g = 0.35 + 0.6 * (t - 55.0) / 17.6
        mus.add(bass_note(45 if (k // 8) % 2 == 0 else 46, EIGHTH * 0.9, 600), t, g)
        if k % 4 == 0:
            mus.add(taiko(0.3 + 0.4 * (t - 55) / 17.6), t)
        t += EIGHTH
        k += 1
    mus.add(pad([57, 58, 64], 17.6, cutoff=1200, attack=6.0), 55.0, 0.35)
    # E: kidnapped theme (intensifies)
    melody_bars(75.6, 90.3, MOTIF, octave=0, gain=0.5, wob=0.01)
    chords(75.6, 90.3, CHORDS_MIN, strings_trem, 0.32)

    def intense(i, t, lvl):
        if i % 8 == 0:
            mus.add(taiko(0.6 * lvl), t)
        if i % 8 == 6:
            mus.add(taiko(0.35 * lvl), t)
        if i % 2 == 0:
            mus.add(hat(0.6 * lvl), t, pan=0.3)
        if i % 4 == 0:
            mus.add(bass_note(45, EIGHTH * 1.6, 500, 1.6), t, 0.6 * lvl)
    beat(75.6, 90.3, lambda i, t: intense(i, t, 0.6 + 0.4 * (t - 75.6) / 14.7))
    # F: quiet dread
    mus.add(pad([33, 34], 6.4, cutoff=300, attack=1.0), 90.3, 0.9)
    for k in range(4):
        mus.add(musicbox([69, 68, 65, 64][k], 2.0, 0.02), 90.6 + k * 1.5, 0.35)
    # G: rebuild to max
    melody_bars(96.4, 104.55, MOTIF, octave=0, gain=0.55, wob=0.01)
    chords(96.4, 104.55, CHORDS_MIN, strings_trem, 0.42, rate=16)

    def maxi(i, t):
        lvl = 0.7 + 0.5 * (t - 96.4) / 8.2
        if i % 4 == 0:
            mus.add(taiko(0.6 * lvl), t)
        mus.add(hat(0.5 * lvl), t, pan=0.3 if i % 2 else -0.3)
        if i % 2 == 0:
            mus.add(bass_note(45, EIGHTH, 600, 2.0), t, 0.55 * lvl)
        if i % 8 == 4:
            mus.add(snare(0.5 * lvl), t)
    beat(96.4, 104.55, maxi)
    mus.add(sfx_riser(3.6), 100.95, 0.9)
    # H: heroic rescue (A major)
    hero_t0 = 105.4
    t = hero_t0
    for bi in range(4):
        mus.add(brass(CHORDS_MAJ[bi] + [CHORDS_MAJ[bi][0] - 12], BAR + 0.3), t, 0.6)
        for k, m in enumerate(HERO[bi]):
            mus.add(musicbox(m, 1.2, 0.0), t + k * EIGHTH, 0.4, pan=0.2)
            mus.add(brass([m], EIGHTH * 0.95), t + k * EIGHTH, 0.22)
        t += BAR
    beat(hero_t0, hero_t0 + 4 * BAR - 0.1,
         lambda i, t: (mus.add(kick(0.6), t) if i % 4 == 0 else None,
                       mus.add(snare(0.35 if i % 4 else 0.55), t) if (i % 8 == 4 or i >= 56) else None,
                       mus.add(snare(0.12), t) if i % 2 == 1 else None))
    mus.add(brass([57, 61, 64, 69], 2.0), hero_t0 + 4 * BAR, 0.5)
    # I: ending (minor again, eerie)
    melody_bars(115.6, 118.1, MOTIF[:1], gain=0.45, step=EIGHTH * 1.5, wob=0.015)
    mus.add(pad([45, 48, 52], 3.2, cutoff=900, attack=1.0), 115.2, 0.45)
    mus.add(pad([45, 46, 51], 1.4, cutoff=1500, attack=0.05), 118.15, 0.5)
    # J: rise into loop
    mus.add(sfx_riser(0.75), 119.25, 0.8)
    return mus.b


# ===================================================================== TTS

# Kokoro voices (higher quality neural TTS). speed > 1 = faster, pitch = rubberband pitch factor.
SPEAKERS = {
    'narr': dict(voice='am_puck', pitch=1.06, speed=1.05, fx=None),
    'boy': dict(voice='am_puck', pitch=1.08, speed=1.0, fx='room'),
    'whisper': dict(voice='am_puck', pitch=1.06, speed=1.0, fx='whisper'),
    'cousin': dict(voice='am_fenrir', pitch=0.94, speed=0.88, fx='creep'),
    'cousin_nice': dict(voice='am_fenrir', pitch=1.0, speed=1.05, fx='room'),
    'operator': dict(voice='af_heart', pitch=1.0, speed=1.05, fx='phone'),
    'cop': dict(voice='am_michael', pitch=1.0, speed=1.12, fx='shout'),
}
PAUSE = {'...': 0.34, '.': 0.2, '?': 0.2, '!': 0.16}


def tts_text(words):
    s = ' '.join(words).replace('*', '')
    s = s.replace('911', 'nine one one')
    s = s.lstrip('.').strip()
    s = s.replace('...', ',')
    return s


def split_segments(text):
    words = text.split()
    segs, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r'(\.\.\.|[.?!])\*?$', w):
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return segs


def seg_end_punct(seg):
    w = seg[-1].replace('*', '')
    for p in ('...', '.', '?', '!'):
        if w.endswith(p):
            return p
    return None


def word_weight(w):
    c = w.replace('*', '')
    if '911' in c:
        return 11
    return len(re.sub(r'[^A-Za-z0-9]', '', c)) + 1.5


def ff_proc(x, sr, af):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, 'a.wav'), os.path.join(d, 'b.wav')
        wavfile.write(a, sr, (np.clip(x, -1, 1) * 32767).astype(np.int16))
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', a, '-af', af, '-ar', str(SR), '-ac', '1', b], check=True)
        _, y = wavfile.read(b)
    return y.astype(float) / 32768


def trim(x, thr=0.012):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(0.012 * SR))
    b = min(len(x), idx[-1] + int(0.04 * SR))
    return x[a:b]


class TTS:
    """Kokoro TTS. vdir must contain kokoro-v1.0.onnx and voices-v1.0.bin."""

    def __init__(self, vdir):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(os.path.join(vdir, 'kokoro-v1.0.onnx'), os.path.join(vdir, 'voices-v1.0.bin'))

    def synth(self, text, spk, speed_mul=1.0):
        cfg = SPEAKERS[spk]
        x, sr = self.k.create(text, voice=cfg['voice'], speed=cfg['speed'] * speed_mul, lang='en-us')
        return np.asarray(x, float), sr


def voice_fx(x, fx):
    if fx is None:
        return stereo(x)
    if fx == 'room':
        return reverb(x, 0.6, 0.12)
    if fx == 'creep':
        y = x + lp(x, 200) * 0.6
        return reverb(y * 0.9, 1.8, 0.28)
    if fx == 'shout':
        y = np.tanh(x * 2.2) * 0.75
        return reverb(y, 1.2, 0.2)
    if fx == 'phone':
        y = bp(x, 350, 3200, 3)
        y = np.tanh(y * 3) * 0.6
        return stereo(y)
    if fx == 'whisper':
        env = lp(np.abs(x), 30) * 2.2
        breath = bp(noise(len(x) / SR + 1e-3)[:len(x)], 900, 6500) * env
        y = hp(x, 400) * 0.45 + breath * 0.9
        return reverb(y, 0.4, 0.15)
    return stereo(x)


def build_vo(vdir, outdir):
    tts = TTS(vdir)
    vo = Bus()
    timing = []
    for li, (lid, start, spk, text, opt) in enumerate(LINES):
        nxt = LINES[li + 1][1] if li + 1 < len(LINES) else DURATION
        limit = min(opt.get('fit', 99), nxt - start - 0.1)
        cfg = SPEAKERS[spk]
        segs = split_segments(text)
        raw = []
        for seg in segs:
            x, sr = tts.synth(tts_text(seg), spk, opt.get('speed', 1.0))
            raw.append((trim(x), sr))

        def render(tempo):
            parts = []
            for (x, sr), seg in zip(raw, segs):
                if abs(cfg['pitch'] - 1) < 1e-3 and abs(tempo - 1) < 1e-3:
                    af = 'anull'
                else:
                    af = f"rubberband=pitch={cfg['pitch']}:tempo={tempo:.4f}:pitchq=quality:formant=preserved"
                parts.append(ff_proc(x, sr, af))
            return parts
        parts = render(1.0)
        pauses = [PAUSE.get(seg_end_punct(s), 0.1) for s in segs[:-1]] + [0.0]
        total = sum(len(p) for p in parts) / SR + sum(pauses)
        tempo = 1.0
        if total > limit:
            tempo = total / limit
            parts = render(tempo)
            pauses = [p / tempo for p in pauses]
            total = sum(len(p) for p in parts) / SR + sum(pauses)
        if tempo > 1.3:
            print(f'  WARNING {lid}: tempo {tempo:.2f}')
        # assemble
        line = []
        words = []
        t = start
        for p, pause, seg in zip(parts, pauses, segs):
            d = len(p) / SR
            ws = [word_weight(w) for w in seg]
            tot = sum(ws)
            acc = 0.0
            for w, wt in zip(seg, ws):
                key = '*' in w
                words.append({'w': w.replace('*', ''), 't0': round(t + d * acc / tot, 3),
                              't1': round(t + d * (acc + wt) / tot, 3), 'key': key})
                acc += wt
            line.append(p)
            line.append(np.zeros(int(pause * SR)))
            t += d + pause
        y = np.concatenate(line)
        y = y / (np.abs(y).max() + 1e-9) * 0.8
        vo.add(voice_fx(y, cfg['fx']), start, 1.0)
        timing.append({'id': lid, 'speaker': spk, 'start': start, 'end': round(start + total, 3),
                       'tempo': round(tempo, 3), 'words': words})
        print(f'{lid:3s} {spk:12s} {start:7.2f} -> {start + total:7.2f} (limit {limit:.2f}, tempo {tempo:.2f})')
    with open(os.path.join(outdir, 'vo_timing.json'), 'w') as f:
        json.dump({'lines': timing, 'titles': TITLES}, f, indent=1)
    return vo.b, timing


# ===================================================================== SFX timeline


def word_time(timing, lid, word):
    for L in timing:
        if L['id'] == lid:
            for w in L['words']:
                if word.lower() in w['w'].lower():
                    return w['t0']
    raise KeyError((lid, word))


def build_sfx(timing):
    fx = Bus()
    A = fx.add
    # --- HOOK
    A(sfx_bass_hit(1.3), 0.0, 1.0)
    A(sfx_call_dropped(), 0.0, 0.9, pan=-0.2)
    for k, t in enumerate([0.75, 1.5, 2.25, 3.0, 3.75]):
        A(sfx_heartbeat(), t, 0.7)
    for k, t in enumerate([0.45, 1.05, 1.65, 2.25]):
        A(sfx_footstep(1.0), t, 0.55, pan=0.3)
    A(sfx_bass_hit(0.7), 2.8, 0.5)
    A(sfx_whoosh(0.5), 2.6, 0.6)
    A(sfx_rewind(1.25), 4.78, 0.8)
    A(sfx_glitch(0.35), 4.75, 0.5)
    A(sfx_glitch(0.3), 5.75, 0.4)
    # --- NORMAL DAY
    A(sfx_birds(4.0), 6.0, 0.8)
    for k in range(6):
        A(sfx_footstep(0.4), 6.4 + k * 0.55, 0.25, pan=-0.2 + 0.08 * k)
    A(sfx_creak(0.9, 260, 1), 10.0, 0.35)
    A(sfx_bass_hit(0.8), word_time(timing, 's6', 'LOCKED'), 0.75)
    for k in range(5):
        A(sfx_footstep(0.5), 19.4 + k * 0.6, 0.25)
    A(sfx_bass_hit(0.9), 26.55, 0.8)
    A(sfx_whoosh(0.6), 26.0, 0.5)
    # --- DISCOVERY
    A(sfx_engine_away(3.5), 30.3, 0.8)
    A(sfx_keys(), 32.9, 0.6)
    for k in range(5):
        A(sfx_footstep(0.4), 34.4 + k * 0.62, 0.3)
    A(sfx_keys(), 36.0, 0.5)
    A(sfx_creak(1.6, 160, 3), 36.5, 0.7)
    A(sfx_bass_hit(1.0), word_time(timing, 'd3', 'MISSING'), 0.8)
    A(sfx_rustle(1.2), 41.3, 0.6)
    A(sfx_rustle(0.8), 45.0, 0.5)
    A(sfx_bass_hit(1.2), 47.6, 0.95)
    A(sfx_whoosh(0.7), 47.0, 0.5)
    A(sfx_gasp(), 49.45, 0.8)
    A(sfx_bass_hit(1.0), word_time(timing, 'd7', 'KILLER'), 0.8)
    A(sfx_door_close(), 54.35, 0.9)
    A(sfx_creak(0.8, 220, 4), 53.9, 0.4)
    # --- THE CALL
    A(sfx_rustle(0.8), 55.4, 0.4)
    for k, dgt in enumerate('911'):
        A(sfx_dtmf(dgt), 58.15 + k * 0.38, 0.8)
    A(sfx_ringback(1.2), 59.3, 0.7)
    A(sfx_click(1500, 0.05, 0.6), 60.9, 0.6)
    for k in range(7):
        g = 0.3 + 0.12 * k
        A(sfx_footstep(1.0 + 0.1 * k), 66.9 + k * 0.62, g, pan=0.2)
    A(sfx_creak(0.7, 200, 6), 70.75, 0.7)
    A(sfx_bass_hit(1.1), 71.45, 0.8)
    A(sfx_call_dropped(), 72.6, 0.7)
    A(sfx_bass_hit(0.8), 72.6, 0.6)
    for k in range(4):
        A(sfx_heartbeat(), 73.1 + k * 0.85, 0.8)
    # --- KIDNAPPED
    A(sfx_gasp(), 75.1, 0.7)
    A(sfx_bass_hit(0.8), word_time(timing, 'k1', 'BASEMENT'), 0.6)
    for k in range(5):
        A(sfx_footstep(1.0), 78.6 + k * 0.62, 0.45, pan=0.15)
    A(sfx_smash(), 82.2, 1.0)
    A(sfx_bass_hit(1.2), 82.2, 0.85)
    A(sfx_bass_hit(0.9), word_time(timing, 'k3', "NOBODY"), 0.6)
    for k in range(20):
        A(sfx_tick(k % 2 == 1), 85.0 + k * 1.0, 0.55 if 90 < 85 + k < 97 else 0.35, pan=-0.35)
    for k in range(10):
        A(sfx_heartbeat(), 86.0 + k * 0.95, 0.5)
    for k in range(6):
        A(sfx_footstep(0.8), 90.7 + k * 0.45, 0.4 - 0.05 * k, pan=-0.3)
    A(sfx_door_close(), 93.1, 0.5)
    A(sfx_struggle(1.6), 96.6, 0.7)
    A(sfx_struggle(1.2), 98.4, 0.5)
    for k in range(6):
        A(sfx_heartbeat(), 96.0 + k * 0.7, 0.55)
    A(sfx_creak(1.0, 190, 9), 99.4, 0.6)
    for k in range(5):
        A(sfx_footstep(1.0), 100.0 + k * 0.5, 0.5, pan=-0.2)
    for k in range(5):
        A(sfx_heartbeat(), 101.0 + k * 0.5, 0.6)
    A(sfx_gasp(), 102.9, 0.9)
    # --- RESCUE
    sir = sfx_siren(14.0)
    t = tt(14.0)
    sir *= np.clip((t / 1.2), 0, 1) * np.clip((14.0 - t) / 3.0, 0.15, 1)
    A(sir, 104.4, 0.9, pan=-0.15)
    A(sfx_door_bash(), 105.35, 1.0)
    A(sfx_bass_hit(1.1), 105.35, 0.7)
    for k in range(10):
        A(sfx_footstep(0.9), 105.8 + k * 0.23, 0.35, pan=random.Random(k).uniform(-0.5, 0.5))
    A(sfx_cuffs(), 108.55, 1.0)
    A(sfx_whoosh(0.5), 109.2, 0.4)
    A(sfx_rustle(0.8), 113.0, 0.3)
    # --- ENDING
    A(sfx_door_close(), 115.5, 0.3)
    A(sfx_bass_hit(0.9), 118.15, 0.75)
    A(sfx_glitch(0.6), 119.3, 0.45)
    A(sfx_rewind(0.7), 119.3, 0.4)
    return fx.b


def env_follow(x, ms=120):
    m = np.abs(x).max(1)
    e = lp(m, 1000 / ms)
    return np.clip(e / (e.max() + 1e-9) * 3, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--voices', required=True)
    ap.add_argument('--out', default='build')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    vo, timing = build_vo(a.voices, a.out)
    print('music...')
    music = build_music()
    print('sfx...')
    fx = build_sfx(timing)
    # duck music under voice
    duck = 1 - 0.5 * env_follow(vo)[:, None]
    mix = vo * 1.0 + music * 0.55 * duck + fx * 0.8
    # hook silence: keep music out of the first 4.75 s (heartbeat only)
    peak = np.abs(mix).max()
    mix = np.tanh(mix / peak * 1.25) / np.tanh(1.25) * 0.93
    mix = mix[:N]
    assert len(mix) == N
    path = os.path.join(a.out, 'audio.wav')
    wavfile.write(path, SR, (mix * 32767).astype(np.int16))
    # loudness normalise towards -14 LUFS (TikTok-ish), soft-limited
    for _ in range(2):
        r = subprocess.run(['ffmpeg', '-hide_banner', '-i', path, '-af', 'ebur128', '-f', 'null', '-'],
                           capture_output=True, text=True).stderr
        I = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r)[-1])
        g = 10 ** ((-14.0 - I) / 20)
        print(f'integrated {I:.1f} LUFS -> gain {g:.2f}')
        if abs(I + 14) < 0.5:
            break
        mix = np.tanh(mix * g * 1.1) / np.tanh(1.1) * 0.94
        wavfile.write(path, SR, (mix * 32767).astype(np.int16))
    wavfile.write(os.path.join(a.out, 'vo_only.wav'), SR, (np.clip(vo, -1, 1) * 32767).astype(np.int16))
    print('wrote', os.path.join(a.out, 'audio.wav'), len(mix) / SR, 's')


if __name__ == '__main__':
    main()
