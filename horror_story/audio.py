"""All sound for the video, synthesized with numpy/scipy: original music-box theme, ambience, SFX and the mix.

  python audio.py            -> build/audio.wav (120.0 s, 48 kHz stereo) and theme.wav
"""
import math
import os

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve

from config import (SR, DURATION, THEME_BPM, THEME_MELODY, THEME_BASS, FINAL_NOTE, MUSIC_CUES, WHISPERS)

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, 'build')
N = int(round(DURATION * SR))
rng = np.random.default_rng(1234)


# ============================================================ basics

def db(x):
    return 10 ** (x / 20.0)


def tt(dur):
    return np.arange(int(dur * SR)) / SR


def noise(dur):
    return rng.standard_normal(int(dur * SR)).astype(np.float64)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], 'bandpass', fs=SR, output='sos'), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, 'lowpass', fs=SR, output='sos'), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, 'highpass', fs=SR, output='sos'), x)


def env_ad(n, a, d, curve=1.0):
    """attack seconds, exponential decay time-constant d seconds."""
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(a, 1e-4)) * np.exp(-np.maximum(0, t - a) / d)
    return e ** curve


def fade(x, fi=0.005, fo=0.005):
    x = x.copy()
    a, b = int(fi * SR), int(fo * SR)
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)
    return x


def norm(x, peak=1.0):
    m = np.max(np.abs(x)) + 1e-12
    return x / m * peak


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def place(buf, sig, t0, gain_db=0.0, pan=0.0):
    """Add mono sig into stereo buf at t0 (s), peak-normalized sig assumed; pan -1..1."""
    i = int(round(t0 * SR))
    if i >= buf.shape[1]:
        return
    if i < 0:
        sig = sig[-i:]
        i = 0
    n = min(len(sig), buf.shape[1] - i)
    g = db(gain_db)
    l = math.cos((pan + 1) * math.pi / 4) * math.sqrt(2)
    r = math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)
    buf[0, i:i + n] += sig[:n] * g * l
    buf[1, i:i + n] += sig[:n] * g * r


def reverb_ir(dur=2.4, decay=0.6, damp=4000, seed=3):
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    ir = r.standard_normal(n) * np.exp(-t / decay)
    ir = lp(ir, damp)
    ir[:int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))
    return ir / np.sqrt(np.sum(ir ** 2))


def reverb(x, wet=0.35, dur=2.4, decay=0.6, damp=4000, seed=3):
    ir = reverb_ir(dur, decay, damp, seed)
    y = fftconvolve(x, ir)[:len(x) + int(dur * SR)]
    xx = np.concatenate([x, np.zeros(len(y) - len(x))])
    return xx * (1 - wet) + y * wet * 1.0


def echo(x, delay=0.37, fb=0.35, n=4):
    d = int(delay * SR)
    y = np.concatenate([x, np.zeros(d * n)])
    out = y.copy()
    for k in range(1, n + 1):
        out[d * k:] += y[:len(y) - d * k] * (fb ** k)
    return out


# ============================================================ theme (music box)

def musicbox_note(freq, dur, wobble_cents=6.0, bright=1.0, seed=0):
    t = tt(dur)
    r = np.random.default_rng(seed)
    vib = wobble_cents * (np.sin(2 * np.pi * (4.5 + r.uniform(-.5, .5)) * t + r.uniform(0, 6)) +
                          0.5 * np.sin(2 * np.pi * 0.7 * t + r.uniform(0, 6)))
    fm = freq * 2 ** (vib / 1200.0)
    ph = 2 * np.pi * np.cumsum(fm) / SR
    # music-box tine: fundamental + octave + slightly inharmonic upper partials
    parts = [(1.0, 1.0, 1.6), (2.0, 0.32 * bright, 0.7), (3.01, 0.10 * bright, 0.4), (5.43, 0.10 * bright, 0.18),
             (8.9, 0.04 * bright, 0.08)]
    y = np.zeros_like(t)
    for ratio, amp, dec in parts:
        y += amp * np.sin(ph * ratio) * np.exp(-t / dec)
    y *= np.minimum(1.0, t / 0.002)
    # tiny mechanical click
    k = int(0.004 * SR)
    y[:k] += r.standard_normal(k) * 0.08 * np.linspace(1, 0, k)
    return y


def soft_bass(freq, dur):
    t = tt(dur)
    tri = 2 / np.pi * np.arcsin(np.sin(2 * np.pi * freq * t))
    return tri * np.exp(-t / 1.4) * np.minimum(1, t / 0.01) * 0.5


def theme(tempo=1.0, detune=0.0, wobble=6.0, bright=1.0, octave=0, loops=1, dark=False, drift_per_loop=0.0):
    """Dry theme render. tempo<1 = slower. detune in cents (global, plus random per-note)."""
    beat = 60.0 / (THEME_BPM * tempo)
    bar = beat * 3
    total = bar * 8 * loops
    y = np.zeros(int((total + 3.0) * SR))
    r = np.random.default_rng(7)
    for L in range(loops):
        t0 = L * bar * 8
        tcur = t0
        for i, (m, beats) in enumerate(THEME_MELODY):
            cents = detune + drift_per_loop * L + (r.uniform(-1, 1) * abs(detune) * 0.6 if detune else 0)
            f = midi_hz(m + octave * 12) * 2 ** (cents / 1200)
            note = musicbox_note(f, 2.5, wobble, bright, seed=i + 31 * L)
            # music box timing is slightly uneven
            jit = r.uniform(-0.012, 0.012)
            s = int(max(0, tcur + jit) * SR)
            y[s:s + len(note)] += note * (0.9 if beats < 1 else 1.0)
            if dark:
                # a ghost note a minor second below, quietly underneath
                g = musicbox_note(f * 2 ** (-1 / 12 - 0.15 / 12), 2.5, wobble * 1.5, bright * 0.5, seed=i + 99)
                y[s:s + len(g)] += g * 0.28
            tcur += beats * beat
        for b, m in enumerate(THEME_BASS):
            f = midi_hz(m + octave * 12) * 2 ** ((detune + drift_per_loop * L) / 1200)
            nb = soft_bass(f, bar + 1.0)
            s = int((t0 + b * bar) * SR)
            y[s:s + len(nb)] += nb * 0.55
    return y[:int((total + 3.0) * SR)]


def theme_wet(x, wet=0.38):
    return reverb(echo(x, 0.37 * 1.0, 0.28, 3), wet=wet, dur=3.0, decay=0.9, damp=5000)


def resample(x, rate):
    """Play back at rate (rate<1 = slower and lower)."""
    n = int(len(x) / rate)
    idx = np.arange(n) * rate
    return np.interp(idx, np.arange(len(x)), x)


def fit(x, dur, fi=0.4, fo=0.02):
    n = int(dur * SR)
    if len(x) < n:
        x = np.concatenate([x, np.zeros(n - len(x))])
    return fade(x[:n], fi, fo)


def music_bus():
    bus = np.zeros((2, N))
    duck = np.ones(N)
    for a, b, _ in WHISPERS:  # duck the music under the whispers (-10 dB), with short ramps
        i0, i1 = int((a - 0.25) * SR), int((b + 0.25) * SR)
        ramp = int(0.2 * SR)
        duck[i0:i1] = np.minimum(duck[i0:i1], db(-10))
        duck[i0 - ramp:i0] = np.minimum(duck[i0 - ramp:i0], np.linspace(1, db(-10), ramp))
        duck[i1:i1 + ramp] = np.minimum(duck[i1:i1 + ramp], np.linspace(db(-10), 1, ramp))
    for cue in MUSIC_CUES:
        a, b, v, g = cue['start'], cue['end'], cue['version'], cue['gain_db']
        dur = b - a
        if v == 'innocent':
            # faint, slowed down, clean: sounds like a lullaby
            x = theme_wet(theme(tempo=0.82, wobble=4, bright=0.9), 0.32)
            x = fit(x, dur, fi=0.8, fo=1.5)
        elif v == 'detuned':
            # detuned and darker: flat, wobbly, a ghost minor second and a low octave double
            x = theme(tempo=0.9, detune=-28, wobble=22, bright=0.7, loops=2, dark=True, drift_per_loop=-25)
            low = theme(tempo=0.9, detune=-45, wobble=30, bright=0.4, octave=-1, loops=2) * 0.45
            x = x[:len(low)] + low[:len(x)]
            x = lp(x, 3500)
            x = theme_wet(x, 0.45)
            x = fit(x, dur, fi=0.5, fo=0.012)  # cuts out abruptly (silence before the jump scare)
        elif v == 'reversed':
            # fully distorted and reversed: reverb first, then reverse -> swelling, backwards lullaby
            x = theme(tempo=0.8, detune=-60, wobble=35, bright=0.8, loops=3, dark=True)
            x = theme_wet(x, 0.6)[::-1]
            x = resample(x, 0.84)  # ~3 semitones lower
            x = np.tanh(x / (np.max(np.abs(x)) + 1e-9) * 5.0)
            x = lp(hp(x, 120), 2800)
            # crude bit-crush for grit
            x = np.round(x * 24) / 24
            x = fit(x, dur, fi=1.2, fo=0.008)  # stops dead when the sirens hit
            # swell over the last 4 seconds before the sirens
            t = np.arange(len(x)) / SR
            x *= 0.65 + 0.35 * np.clip((t - (dur - 4.0)) / 4.0, 0, 1) * 1.6
        elif v == 'final_note':
            m, off = FINAL_NOTE
            note = musicbox_note(midi_hz(m + off), 2.2, wobble_cents=28, bright=1.0, seed=5)
            # pitch sags a little as it rings: the "broken" last note
            t = tt(2.2)
            sag = np.interp(np.arange(len(note)) * (1 - 0.012 * np.clip(t * 0.8, 0, 1)), np.arange(len(note)), note)
            x = theme_wet(sag, 0.5)
            x = fit(x, dur, fi=0.002, fo=0.12)
        else:
            raise ValueError(v)
        x = norm(x, 1.0)
        i0 = int(a * SR)
        seg = x * duck[i0:i0 + len(x)][:len(x)]
        # slight stereo width, then set the cue's exact peak level
        tmp = np.zeros((2, N))
        place(tmp, seg, a, 0, pan=-0.15)
        place(tmp, np.concatenate([np.zeros(int(0.011 * SR)), seg])[:len(seg)], a, -3, pan=0.5)
        bus += tmp / (np.max(np.abs(tmp)) + 1e-12) * db(g)
    return bus


def export_theme():
    """theme.wav: the clean theme on its own (two passes, innocent then darker), 48 kHz stereo."""
    a = theme_wet(theme(tempo=1.0, wobble=6, loops=1), 0.35)
    b = theme_wet(theme(tempo=0.9, detune=-30, wobble=20, bright=0.7, dark=True), 0.5)
    m, off = FINAL_NOTE
    last = theme_wet(musicbox_note(midi_hz(m + off), 2.2, 28, 1.0, seed=5), 0.5)
    gap = np.zeros(int(0.4 * SR))
    x = np.concatenate([a[:int(len(a) - 2.0 * SR)], b, gap, last])
    x = norm(fade(x, 0.01, 0.5), db(-3))
    st = np.stack([x, np.concatenate([np.zeros(int(0.009 * SR)), x])[:len(x)]], axis=1)
    wavfile.write(os.path.join(HERE, 'theme.wav'), SR, (st * 32767).astype(np.int16))
    return len(x) / SR


# ============================================================ sound effects

def boom(dur=1.6, f0=70, f1=28):
    t = tt(dur)
    f = f1 + (f0 - f1) * np.exp(-t / 0.15)
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.5)
    y += lp(noise(dur), 300) * np.exp(-t / 0.08) * 0.6
    return norm(fade(y, 0.001, 0.05))


def sting(dur=2.2, seed=0):
    """Jump-scare hit: sub boom + distorted noise slam + dissonant screeching cluster."""
    r = np.random.default_rng(seed)
    t = tt(dur)
    y = boom(dur, 90, 30) * 1.0
    slam = hp(noise(dur), 200) * np.exp(-t / 0.12)
    y += slam * 0.8
    cl = np.zeros_like(t)
    for f in (987.8, 1046.5, 1108.7, 1479.98, 1567.98):  # clustered minor seconds / tritone
        f = f * (1 + r.uniform(-0.004, 0.004))
        vib = 1 + 0.01 * np.sin(2 * np.pi * r.uniform(5, 8) * t)
        ph = 2 * np.pi * np.cumsum(f * vib) / SR
        cl += (2 * ((ph / (2 * np.pi)) % 1.0) - 1)  # saw
    cl = bp(cl, 600, 6000) * np.exp(-t / 0.7) * np.minimum(1, t / 0.01)
    y += cl * 0.45
    y = np.tanh(norm(y) * 3.0)
    y = lp(y, 7000, 4)  # tame the square-wave edges (they ring and overshoot in AAC)
    return norm(fade(y, 0.0005, 0.2))


def heartbeat_track(segments):
    """segments: (start, end, bpm0, bpm1, gain_db0, gain_db1)."""
    out = np.zeros(N)

    def beat(f0, dur=0.22):
        t = tt(dur)
        f = 30 + f0 * np.exp(-t / 0.05)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.07) * np.minimum(1, t / 0.004)
    lub, dub = beat(60), beat(52) * 0.7
    for a, b, bpm0, bpm1, g0, g1 in segments:
        t = a
        while t < b:
            u = (t - a) / max(1e-6, b - a)
            bpm = bpm0 + (bpm1 - bpm0) * u
            g = db(g0 + (g1 - g0) * u)
            per = 60.0 / bpm
            i = int(t * SR)
            for sig, off in ((lub, 0), (dub, min(0.3 * per, 0.2))):
                j = i + int(off * SR)
                n = min(len(sig), N - j)
                if n > 0:
                    out[j:j + n] += sig[:n] * g
            t += per
    return lp(out, 180)


def thump(dur=0.18, f=90, nz=0.4, cutoff=900):
    t = tt(dur)
    y = np.sin(2 * np.pi * np.cumsum(f * (1 + 0.6 * np.exp(-t / 0.02))) / SR) * np.exp(-t / 0.05)
    y += lp(noise(dur), cutoff) * np.exp(-t / 0.03) * nz
    return norm(fade(y, 0.001, 0.02))


def creak(dur=0.6, f0=60, f1=140, res=(420, 900, 1700), seed=0, rough=0.3):
    """Stick-slip wood creak: irregular pulse train through resonances."""
    r = np.random.default_rng(seed)
    t = tt(dur)
    f = f0 + (f1 - f0) * (0.5 - 0.5 * np.cos(np.pi * t / dur))
    f = f * (1 + rough * lp(r.standard_normal(len(t)), 30) * 3)
    f = np.clip(f, 15, 400)
    ph = np.cumsum(f) / SR
    pulses = (np.diff(np.floor(ph), prepend=0) > 0).astype(float)
    pulses *= 0.6 + 0.4 * r.random(len(t))
    y = np.zeros_like(t)
    for fr in res:
        y += bp(pulses, fr * 0.9, fr * 1.1, 2)
    y *= np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 0.6
    return norm(y)


def grass_step():
    d = 0.15
    t = tt(d)
    y = bp(noise(d), 300, 3000) * np.exp(-t / 0.035)
    return norm(y)


def wood_step(seed=0, heavy=1.0):
    y = thump(0.25, 85, 0.5, 1200)
    r = np.random.default_rng(seed)
    if r.random() < 0.75:
        c = creak(r.uniform(0.25, 0.5), r.uniform(40, 70), r.uniform(90, 160), seed=seed,
                  res=(r.uniform(350, 500), r.uniform(800, 1000), r.uniform(1500, 1900)))
        yy = np.zeros(max(len(y), int(0.05 * SR) + len(c)))
        yy[:len(y)] += y * heavy
        yy[int(0.05 * SR):int(0.05 * SR) + len(c)] += c * 0.55
        return norm(yy)
    return y


def door_creak(dur=1.4, seed=2):
    return creak(dur, 25, 90, res=(300, 650, 1250, 2300), seed=seed, rough=0.5)


def slam(big=False):
    d = 1.2
    t = tt(d)
    y = boom(d, 120, 40) * 0.9
    y += bp(noise(d), 300, 5000) * np.exp(-t / (0.09 if big else 0.05)) * (1.2 if big else 0.7)
    if big:  # splintering wood
        for k in range(6):
            s = int(rng.uniform(0.0, 0.18) * SR)
            c = hp(noise(0.06), 1500) * np.exp(-tt(0.06) / 0.01)
            y[s:s + len(c)] += c * 0.6
    return norm(np.tanh(norm(y) * 2.0))


def whoosh(dur=0.6, rise=True):
    t = tt(dur)
    x = noise(dur)
    u = t / dur
    # sweep a bandpass by crossfading three bands
    lo, mid, hi = bp(x, 200, 600), bp(x, 600, 2000), bp(x, 2000, 7000)
    w = u if rise else 1 - u
    y = lo * (1 - w) + mid * np.sin(np.pi * w) + hi * w
    y *= np.sin(np.pi * u) ** 2
    return norm(y)


def rewind_sfx(dur=0.55):
    """Tape rewind: chattering squeal with a warbling pitch climbing up, plus tape hiss and motor whine."""
    t = tt(dur)
    f = 1200 + 3500 * (t / dur) ** 0.7
    f *= 1 + 0.08 * np.sin(2 * np.pi * 37 * t) + 0.04 * np.sin(2 * np.pi * 11 * t)
    sq = np.sin(2 * np.pi * np.cumsum(f) / SR)
    chatter = (np.sin(2 * np.pi * 55 * t) > 0.2).astype(float) * 0.5 + 0.5
    hiss = hp(noise(dur), 2500) * 0.5
    motor = np.sin(2 * np.pi * np.cumsum(220 + 400 * t / dur) / SR) * 0.4
    y = sq * chatter * 0.6 + hiss + motor
    y *= np.minimum(1, t / 0.02) * np.minimum(1, (dur - t) / 0.03)
    return norm(y)


def glitch_sfx(dur=0.16, seed=0):
    r = np.random.default_rng(seed)
    t = tt(dur)
    y = np.zeros_like(t)
    seg = int(0.012 * SR)
    for i in range(0, len(t), seg):
        kind = r.integers(0, 3)
        n = min(seg, len(t) - i)
        if kind == 0:
            y[i:i + n] = np.sign(np.sin(2 * np.pi * r.uniform(200, 3000) * t[:n]))
        elif kind == 1:
            y[i:i + n] = r.standard_normal(n)
        else:
            y[i:i + n] = 0
    y = np.round(y * 4) / 4
    return norm(y)


def dtmf(digit, dur=0.2):
    keys = {'1': (697, 1209), '9': (852, 1477)}
    a, b = keys[digit]
    t = tt(dur)
    return norm(fade((np.sin(2 * np.pi * a * t) + np.sin(2 * np.pi * b * t)), 0.004, 0.01))


def ringback(dur):
    t = tt(dur)
    y = np.sin(2 * np.pi * 440 * t) + np.sin(2 * np.pi * 480 * t)
    return norm(fade(bp(y, 300, 3400), 0.02, 0.02))


VOWELS = {'a': (800, 1200, 2500), 'e': (500, 1900, 2600), 'i': (300, 2200, 3000), 'o': (500, 900, 2400),
          'u': (350, 800, 2300), 'ei': (450, 2000, 2600), 'ai': (700, 1500, 2500)}


def whisper(syllables, seed=0, muffle=3200):
    """Whispered syllables: shaped noise through vowel formants with consonant hiss bursts.
    syllables: list of (consonant 's'|'p'|'t'|'h'|'m'|'', vowel key, duration, pause_after)."""
    r = np.random.default_rng(seed)
    out = []
    for cons, vow, d, pause in syllables:
        parts = []
        if cons in ('s', 'sh'):
            c = bp(r.standard_normal(int(0.09 * SR)), 3500 if cons == 's' else 2200, 8000) * 0.7
            parts.append(c * np.hanning(len(c)))
        elif cons in ('p', 't', 'k'):
            c = hp(r.standard_normal(int(0.03 * SR)), 1500) * np.exp(-tt(0.03) / 0.008) * 1.2
            parts.append(c)
        elif cons in ('h', 'm', 'n', 'l'):
            c = bp(r.standard_normal(int(0.05 * SR)), 300, 1500) * 0.4
            parts.append(c * np.hanning(len(c)))
        x = r.standard_normal(int(d * SR))
        f1, f2, f3 = VOWELS[vow]
        v = bp(x, f1 * 0.85, f1 * 1.15) * 1.0 + bp(x, f2 * 0.9, f2 * 1.1) * 0.7 + bp(x, f3 * 0.92, f3 * 1.08) * 0.35
        e = np.sin(np.pi * np.linspace(0, 1, len(v))) ** 0.7
        parts.append(v * e)
        parts.append(np.zeros(int(pause * SR)))
        out.append(np.concatenate(parts))
    y = np.concatenate(out)
    y = lp(y, muffle)
    return norm(y)


def phone_voice(dur, seed=0):
    """Muffled operator voice coming out of the phone speaker (unintelligible on purpose)."""
    r = np.random.default_rng(seed)
    t = tt(dur)
    f0 = 190 + 25 * np.sin(2 * np.pi * 2.3 * t) + 15 * lp(r.standard_normal(len(t)), 5) * 10
    ph = np.cumsum(f0) / SR
    src = 2 * (ph % 1.0) - 1
    y = np.zeros_like(t)
    seg = int(0.11 * SR)
    for i in range(0, len(t), seg):
        f1, f2, f3 = VOWELS[r.choice(list(VOWELS))]
        n = min(seg, len(t) - i)
        s = src[i:i + n]
        y[i:i + n] = bp(s, f1 * 0.8, f1 * 1.2) + bp(s, f2 * 0.9, f2 * 1.1) * 0.5
    y *= (lp(r.standard_normal(len(t)), 6) > -0.02).astype(float) * 0.7 + 0.3
    y = bp(y, 400, 2400)
    return norm(fade(y, 0.02, 0.05))


def siren(dur, period=2.6, f_lo=650, f_hi=1350, yelp_from=None, seed=0):
    t = tt(dur)
    u = 0.5 - 0.5 * np.cos(2 * np.pi * t / period)
    f = f_lo + (f_hi - f_lo) * u
    if yelp_from is not None:
        k = t > yelp_from
        u2 = 0.5 - 0.5 * np.cos(2 * np.pi * t / 0.32)
        f = np.where(k, f_lo + (f_hi - f_lo) * u2, f)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.18 * np.sin(3 * ph)
    y = np.tanh(y * 1.5)
    return norm(fade(y, 0.01, 0.3))


def crickets(dur, seed=0, n=4):
    r = np.random.default_rng(seed)
    t = tt(dur)
    out = np.zeros((2, len(t)))
    for k in range(n):
        fc = r.uniform(4200, 5200)
        rate = r.uniform(0.45, 0.9)
        pulses = r.integers(3, 5)
        car = np.sin(2 * np.pi * fc * t)
        ph = (t / rate + r.uniform(0, 1)) % 1.0
        burst = (ph < pulses * 0.035) * (np.sin(2 * np.pi * ph / 0.035) > 0)
        e = lp(burst.astype(float), 400)
        pan = r.uniform(-0.8, 0.8)
        g = r.uniform(0.4, 1.0)
        out[0] += car * e * g * math.cos((pan + 1) * math.pi / 4)
        out[1] += car * e * g * math.sin((pan + 1) * math.pi / 4)
    return out / (np.max(np.abs(out)) + 1e-9)


def wind(dur, seed=0):
    r = np.random.default_rng(seed)
    t = tt(dur)
    x = r.standard_normal(len(t))
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + 1) * np.sin(2 * np.pi * 0.023 * t)
    a, b = bp(x, 200, 500), bp(x, 500, 1100)
    y = a * (0.6 + 0.4 * lfo) + b * lfo ** 2 * 0.8
    return norm(y)


def drone(dur):
    t = tt(dur)
    y = np.zeros_like(t)
    for f, a in ((55, 1.0), (55.4, 0.8), (82.4, 0.4), (110.6, 0.25), (77.8, 0.18)):
        ph = 2 * np.pi * f * t
        y += a * (2 * ((ph / (2 * np.pi)) % 1) - 1)
    y = lp(y, 220, 4)
    y *= 0.75 + 0.25 * np.sin(2 * np.pi * 0.05 * t)
    return norm(y)


def bulb_buzz(dur, seed=0):
    r = np.random.default_rng(seed)
    t = tt(dur)
    y = np.sign(np.sin(2 * np.pi * 120 * t)) * 0.5 + np.sin(2 * np.pi * 240 * t) * 0.3
    y = bp(y, 100, 2000)
    fl = (lp(r.standard_normal(len(t)), 8) * 20 > -0.4).astype(float)
    return norm(y * (0.6 + 0.4 * fl))


def birds(dur, seed=0):
    r = np.random.default_rng(seed)
    out = np.zeros(int(dur * SR))
    tcur = 0.3
    while tcur < dur - 0.5:
        n = r.integers(2, 5)
        for k in range(n):
            d = r.uniform(0.06, 0.12)
            t = tt(d)
            f = r.uniform(2800, 4200) * (1 + 0.3 * np.sin(np.pi * t / d))
            c = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / d) ** 2
            s = int((tcur + k * 0.14) * SR)
            out[s:s + len(c)] += c * r.uniform(0.4, 1.0)
        tcur += r.uniform(1.2, 3.0)
    return norm(out)


def breath(dur, rate=2.4):
    t = tt(dur)
    x = bp(noise(dur), 500, 3500)
    e = np.clip(np.sin(2 * np.pi * rate * t), 0, 1) ** 1.5
    return norm(x * e)


def tinnitus(dur):
    t = tt(dur)
    return norm(np.sin(2 * np.pi * 4100 * t) * np.exp(-t / (dur * 0.5)))


def screech(dur):
    t = tt(dur)
    f = 2400 + 300 * np.sin(2 * np.pi * 9 * t)
    y = bp(noise(dur), 1500, 4000) * 0.6 + np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.4
    return norm(fade(y * np.exp(-t / (dur * 0.6)), 0.01, 0.05))


def engine(dur):
    t = tt(dur)
    f = 45 + 20 * np.exp(-t / 0.6)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sign(np.sin(ph)) * 0.6 + np.sin(ph * 2) * 0.4
    return norm(fade(lp(y, 300), 0.05, 0.3))


def radio(dur, seed=0):
    r = np.random.default_rng(seed)
    y = np.zeros(int((dur + 2.0) * SR))
    t0 = 0.1
    while t0 < dur - 1.0:
        d = r.uniform(0.4, 0.9)
        v = phone_voice(d, seed=int(r.integers(0, 999))) * 0.8 + bp(noise(d), 1000, 4000) * 0.25
        s = int(t0 * SR)
        y[s:s + len(v)] += v
        sq = bp(noise(0.06), 1000, 5000)
        y[s + len(v):s + len(v) + len(sq)] += sq * 0.6
        t0 += d + r.uniform(0.6, 1.3)
    return norm(fade(y[:int(dur * SR)], 0.01, 0.1))


# ============================================================ timeline

def build():
    sfx = np.zeros((2, N))
    amb = np.zeros((2, N))

    # ---------- ambience
    dr = drone(DURATION)
    g = np.ones(N) * db(-34)

    def seg_gain(arr, a, b, gdb, ramp=0.4):
        i0, i1 = int(a * SR), int(b * SR)
        r_ = int(ramp * SR)
        arr[i0:i1] = db(gdb)
        if i0 - r_ > 0:
            arr[i0 - r_:i0] = np.linspace(arr[i0 - r_], db(gdb), r_)
    seg_gain(g, 0, 4, -24, 0.0)
    seg_gain(g, 4, 22, -38)
    seg_gain(g, 22, 52, -29)
    seg_gain(g, 52, 65, -27)
    seg_gain(g, 65, 107, -24)
    seg_gain(g, 107, 115, -34)
    seg_gain(g, 115, 120, -30)
    g[int(2.5 * SR):int(3.5 * SR)] = db(-40)
    amb[0] += dr * g
    amb[1] += dr * g
    wd = wind(DURATION, 3)
    wg = np.ones(N) * db(-36)
    for a, b, gd in ((4, 22, -33), (22, 34, -30), (53, 61, -30), (107, 109, -32), (115, 120, -32)):
        seg_gain(wg, a, b, gd)
    for a, b in ((0, 2.5), (34, 53), (61, 107), (109, 115)):
        seg_gain(wg, a, b, -44)
    amb[0] += wd * wg
    amb[1] += np.roll(wd, 3000) * wg
    place(amb, birds(17.5, 2), 4.3, -36, 0.4)
    for a, b in ((22.0, 34.0), (44.0, 46.0), (53.0, 61.0), (107.0, 109.0), (115.0, 120.0)):
        cr = crickets(b - a, seed=int(a))
        i0 = int(a * SR)
        n = len(cr[0])
        e = np.ones(n)
        e[:int(0.3 * SR)] = np.linspace(0, 1, int(0.3 * SR))
        e[-int(0.3 * SR):] = np.linspace(1, 0, int(0.3 * SR))
        amb[:, i0:i0 + n] += cr * e * db(-34)
    # bulb buzz in the basement
    for a, b, gd in ((0, 2.5, -36), (67, 107, -38), (109, 115, -40)):
        bz = bulb_buzz(b - a, int(a))
        place(amb, fade(bz, 0.2, 0.2), a, gd)
    # inside the cellar, heard through the window: very soft buzz
    place(amb, fade(bulb_buzz(18, 9), 0.4, 0.05), 34, -44)

    # ---------- heartbeat (speeds up in tense parts)
    hb = heartbeat_track([
        (0.0, 2.5, 120, 128, -11, -8),
        (44.0, 52.0, 72, 125, -16, -9),
        (53.2, 63.0, 140, 115, -10, -14),
        (69.0, 90.0, 90, 120, -17, -12),
        (90.0, 106.9, 120, 165, -12, -7),
        (65.8, 67.0, 70, 70, -18, -18),
    ])
    sfx[0] += hb
    sfx[1] += hb

    # ---------- HOOK
    place(sfx, boom(1.8, 80, 30), 0.0, -6)                       # frame-1 impact
    place(sfx, sting(1.4, 9), 0.0, -12)
    for k, tt_ in enumerate((0.35, 1.05)):                        # Gray's footsteps behind Timmy
        place(sfx, wood_step(k + 3), tt_, -12, -0.2)
    place(sfx, sting(2.0, 1), 1.5, -1.5)                          # zoom into the face: LOUD
    place(sfx, whoosh(0.35, True), 1.2, -16)
    place(sfx, glitch_sfx(0.16, 2), 2.5, -9)
    place(sfx, glitch_sfx(0.07, 3), 2.92, -13)
    place(sfx, glitch_sfx(0.07, 4), 3.21, -13)
    place(sfx, rewind_sfx(0.52), 3.48, -8)
    place(sfx, glitch_sfx(0.08, 5), 3.95, -14)
    place(sfx, whoosh(0.5, False), 3.95, -18)

    # ---------- SETUP
    for k in range(10):                                            # Timmy running around the yard
        place(sfx, grass_step(), 4.1 + k * 0.33, -26, -0.3)
    place(sfx, thump(0.15, 140, 0.8, 2500), 6.56, -16, -0.2)      # ball kick
    place(sfx, thump(0.12, 160, 0.6, 2000), 7.3, -22, 0.2)        # ball bounce
    place(sfx, whoosh(0.6, True), 10.7, -24)
    place(sfx, boom(1.4, 60, 30), 11.0, -18)                       # "Mr. Gray." low hit
    place(sfx, whoosh(0.5, False), 16.3, -24)
    for k in range(6):
        place(sfx, grass_step(), 20.4 + k * 0.28, -28, -0.4)

    # ---------- DISCOVERY
    place(sfx, whoosh(0.8, False), 21.6, -20)
    place(sfx, thump(0.2, 70, 0.3, 600), 23.3, -24, 0.4)          # basement light clicks on
    place(sfx, door_creak(0.8, 4), 28.0, -22, -0.4)               # Timmy's front door
    for k in range(10):                                            # sneaking (soft)
        place(sfx, grass_step(), 28.6 + k * 0.5, -30, 0.0)
    place(sfx, whoosh(0.4, True), 33.8, -24)
    for k in range(6):                                             # the bag being dragged (thuds + scrape)
        d = bp(noise(0.45), 150, 1200) * np.hanning(int(0.45 * SR))
        place(sfx, norm(d), 34.3 + k * 0.75, -24, 0.0)
        place(sfx, thump(0.2, 70, 0.3, 500), 34.3 + k * 0.75, -26)
    place(sfx, boom(1.6, 50, 25), 39.0, -18)                       # MISSING
    place(sfx, boom(1.2, 60, 28), 42.0, -20)                       # shovel

    # ---------- SPOTTED
    place(sfx, creak(1.6, 20, 45, res=(250, 520, 980), seed=11, rough=0.4), 48.6, -20)  # neck turning
    place(sfx, sting(2.4, 2), 52.0, -1.0)                          # JUMP SCARE
    place(sfx, thump(0.25, 60, 0.6, 700), 53.25, -14)              # Timmy falls
    place(sfx, whoosh(0.4, True), 53.2, -16)
    for k in range(int(5.0 / 0.21)):                               # running
        place(sfx, grass_step(), 55.0 + k * 0.21, -20, 0.0)
    place(sfx, breath(5.0, 3.2), 55.0, -26)
    place(sfx, thump(0.2, 70, 0.3, 600), 57.8, -22, 0.3)          # light switch off
    place(sfx, thump(0.2, 70, 0.3, 600), 58.05, -24, 0.3)
    place(sfx, slam(False), 60.3, -6)                              # front door slam
    place(sfx, breath(2.8, 2.2), 61.0, -22)                        # panting

    # ---------- KIDNAPPED
    for k in range(3):
        place(sfx, wood_step(20 + k, 0.6), 63.5 + k * 0.45, -22, -0.5)  # floorboards behind him
    place(sfx, sting(2.0, 3), 65.0, -1.5)                          # grabbed
    place(sfx, tinnitus(2.0), 65.6, -26)
    place(sfx, whoosh(1.0, True), 67.0, -26)
    place(sfx, creak(1.2, 30, 60, seed=21), 72.0, -24)            # chair creak while struggling
    place(sfx, door_creak(1.6, 5), 74.4, -10, 0.3)                 # basement door opens
    tstep = 75.9
    k = 0
    while tstep < 90.0:                                            # slow, heavy steps down the stairs
        if not (80.0 <= tstep < 82.0):                             # he stops halfway
            place(sfx, wood_step(40 + k), tstep, -9 + min(4, (tstep - 76) * 0.25), 0.35)
        tstep += 0.95
        k += 1
    place(sfx, creak(0.8, 30, 70, seed=33), 81.0, -18, 0.35)       # the step he is standing on
    place(sfx, thump(0.1, 300, 0.2, 3000), 82.2, -26)

    # ---------- THE CALL
    for tp, dgt in ((90.3, '9'), (90.9, '1'), (91.5, '1')):
        place(sfx, dtmf(dgt), tp, -16)
    for a in (92.1,):
        place(sfx, bp(ringback(1.5), 300, 2500), a, -20)
    place(sfx, thump(0.05, 900, 0.1, 6000), 94.0, -24)             # call connects
    place(sfx, phone_voice(0.9, 1), 93.9, -24)                     # "911, what's your emergency?" (muffled)
    place(sfx, whisper([('p', 'i', 0.22, 0.05), ('h', 'e', 0.25, 0.5), ('h', 'e', 0.18, 0.02), ('p', 'u', 0.1, 0.4)],
                       seed=1), 94.4, -9, -0.1)
    place(sfx, phone_voice(0.5, 2), 96.95, -26)
    place(sfx, whisper([('m', 'ai', 0.2, 0.08), ('n', 'ei', 0.2, 0.03), ('p', 'o', 0.25, 0.3)], seed=2), 97.3, -9, -0.1)
    place(sfx, whisper([('h', 'o', 0.2, 0.03), ('t', 'i', 0.12, 0.08), ('t', 'u', 0.18, 0.15), ('', 'e', 0.25, 0.06),
                        ('s', 'i', 0.28, 0.1)], seed=3), 99.3, -9, -0.1)
    place(sfx, phone_voice(0.7, 3), 101.0, -26)
    for k in range(6):                                              # heavy steps across the floor
        place(sfx, wood_step(60 + k, 0.8), 101.2 + k * 0.62, -10 + k * 0.8, 0.2 - k * 0.08)
    place(sfx, breath(2.0, 1.5), 103.0, -26)

    # ---------- JUST IN TIME
    place(sfx, creak(1.8, 20, 50, res=(220, 480, 900), seed=44), 105.0, -18)
    sir = np.zeros((2, N))
    place(sir, siren(8.0, yelp_from=2.5), 107.0, -16, 0.4)          # sirens BLAST
    place(sir, siren(8.0, period=2.9, f_lo=620, f_hi=1290, seed=1), 107.25, -19, -0.4)
    # from 109.0 s we are back in the basement: the sirens are outside, muffled through the walls
    i0 = int(109.0 * SR)
    xf = np.clip((np.arange(N - i0)) / (0.08 * SR), 0, 1)
    for ch in range(2):
        muff = lp(sir[ch, i0:], 700, 4) * db(4)
        sir[ch, i0:] = sir[ch, i0:] * (1 - xf) + muff * xf
    sfx += sir
    place(sfx, boom(1.5, 90, 30), 107.0, -10)
    place(sfx, screech(0.9), 107.6, -12, 0.5)
    place(sfx, engine(2.0), 107.0, -16, 0.4)
    place(sfx, slam(True), 109.08, -7)                             # door bursts open
    for k in range(10):
        place(sfx, wood_step(80 + k, 0.7), 110.55 + k * 0.19, -12, 0.2)  # officers rushing down
    place(sfx, thump(0.08, 2000, 0.4, 8000), 113.2, -18)           # handcuffs click
    place(sfx, thump(0.06, 2400, 0.4, 8000), 113.32, -20)

    # ---------- ENDING
    place(sfx, radio(4.0, 7), 115.2, -24, -0.3)
    place(sfx, siren(5.0, period=3.2, f_lo=600, f_hi=1200), 115.0, -24, 0.6)  # distant, fading
    # the light flickers on: electric buzz + clicks, then the last off-key note (music bus)
    place(sfx, fade(bulb_buzz(1.4, 77), 0.01, 0.3), 118.6, -20, 0.2)
    for tp in (118.6, 118.69, 118.78, 118.92):
        place(sfx, thump(0.05, 900, 0.3, 5000), tp, -20, 0.2)
    place(sfx, boom(1.2, 50, 25), 118.6, -20)

    mus = music_bus()
    # sfx + ambience normalized so the loudest moment (a jump scare) peaks at -0.5 dBFS;
    # the music is added at its absolute cue level (peaks -19..-22 dBFS), always under the sfx
    k = db(-0.5) / np.max(np.abs(amb + sfx))
    amb, sfx = amb * k * db(4), sfx * k  # ambience gets +4 dB so the quiet scenes are not too thin
    mix = amb + sfx + mus
    # make the very last frames fade cleanly
    nfo = int(0.06 * SR)
    mix[:, -nfo:] *= np.linspace(1, 0, nfo)
    return mix, dict(amb=amb, sfx=sfx, mus=mus)


def limiter(x, ceiling_db=-1.0, look_ms=3.0, release_ms=60.0):
    from scipy.ndimage import maximum_filter1d
    c = db(ceiling_db)
    peak = np.max(np.abs(x), axis=0)
    la = int(look_ms / 1000 * SR)
    pk = maximum_filter1d(peak, size=2 * la + 1)
    gain = np.minimum(1.0, c / (pk + 1e-12))
    # smooth release (one-pole, run backwards+forwards to keep it ahead of peaks)
    a = math.exp(-1.0 / (release_ms / 1000 * SR))
    from scipy.signal import lfilter
    g_s = lfilter([1 - a], [1, -a], gain)
    g = np.minimum(gain, g_s)
    g = np.minimum(g, lfilter([1 - a], [1, -a], g[::-1])[::-1])
    return x * g


def main():
    os.makedirs(BUILD, exist_ok=True)
    mix, buses = build()
    mix = np.stack([lp(ch, 16000, 4) for ch in mix])
    mix = limiter(mix, -2.0)  # headroom so the AAC encode never clips
    assert mix.shape[1] == N
    wavfile.write(os.path.join(BUILD, 'audio.wav'), SR, (mix.T * 32767).astype(np.int16))
    dur = export_theme()
    # report levels
    def rms_db(x):
        return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)
    scale = 1.0
    for name in ('amb', 'sfx', 'mus'):
        print(f'{name}: peak {20 * np.log10(np.max(np.abs(buses[name])) * scale + 1e-12):6.1f} dBFS')
    for a, b, lab in ((1.4, 2.5, 'hook sting'), (52, 53, 'jump scare'), (65, 66, 'grab'), (5, 20, 'setup'),
                      (24, 44, 'discovery'), (94, 101, 'whispers'), (107, 112, 'sirens')):
        seg = mix[:, int(a * SR):int(b * SR)]
        print(f'{lab:12s} peak {20 * np.log10(np.max(np.abs(seg)) + 1e-12):6.1f}  rms {rms_db(seg):6.1f} dBFS')
    print('audio ->', os.path.join(BUILD, 'audio.wav'), f'{mix.shape[1] / SR:.3f}s')
    print('theme ->', os.path.join(HERE, 'theme.wav'), f'{dur:.2f}s')


if __name__ == '__main__':
    main()
