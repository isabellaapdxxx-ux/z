"""Soundtrack, synthesised entirely with NumPy (48 kHz stereo, exactly 30.000 s).

Music: a detuned-saw synth pad on a cinematic progression in D minor whose filter
opens as it builds, plus a sub-bass pulse that speeds up until 24 s, where everything
resolves to D major with a bell arpeggio.
SFX: whooshes (band-passed noise sweeps) on every scene transition, booms at 3/19/24 s,
shimmering dings when each lens lights, ticks on the montage cuts, a riser 22-24 s
and a rain texture during the "Tougher." shot.
Master: convolution reverb, look-ahead peak limiter, normalised to -1 dBFS, 1.5 s fade-out.
"""
import math
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from film import FLASH_TIMES, LENS_TIMES  # noqa: E402

SR = 48000
DUR = 30.0
N = int(round(SR * DUR))           # 1,440,000 samples
T = np.arange(N) / SR

TRANSITIONS = (3.0, 7.0, 11.0, 15.0, 19.0, 24.0, 28.0)
TICKS = (15.0, 16.0, 17.0, 18.0)
RISER = (22.0, 24.0)
RAIN = (17.0, 18.0)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def place(buf, sig, t0, pan=0.0, gain=1.0):
    """Add mono (n,) or stereo (n, 2) sig into stereo buf starting at time t0 (s)."""
    i0 = int(round(t0 * SR))
    if sig.ndim == 1:
        a = (pan + 1) * math.pi / 4
        sig = np.stack([sig * math.cos(a), sig * math.sin(a)], -1) * math.sqrt(2)
    j0, j1 = max(0, i0), min(N, i0 + len(sig))
    if j1 > j0:
        buf[j0:j1] += sig[j0 - i0:j1 - i0] * gain


# ----------------------------------------------------------------------------- DSP helpers
def stft_filter(x, gain_fn, n_fft=2048, hop=512):
    """Time-varying spectral filter. gain_fn(freqs (F,), times (T,)) -> (T, F)."""
    n = len(x)
    win = np.hanning(n_fft + 1)[:-1]
    xp = np.pad(x, (n_fft, n_fft + hop))
    nfr = 1 + (len(xp) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(nfr)[:, None]
    spec = np.fft.rfft(xp[idx] * win, axis=1)
    freqs = np.fft.rfftfreq(n_fft, 1 / SR)
    times = (np.arange(nfr) * hop + n_fft / 2 - n_fft) / SR
    spec *= gain_fn(freqs, times)
    frames = np.fft.irfft(spec, n=n_fft, axis=1) * win
    y = np.zeros(len(xp))
    for k in range(nfr):
        y[k * hop:k * hop + n_fft] += frames[k]
    y /= (win ** 2).sum() / hop
    return y[n_fft:n_fft + n]


def bandpass_gain(fc_fn, bw_oct):
    def g(freqs, times):
        fc = fc_fn(times)[:, None]
        bw = bw_oct(times)[:, None] if callable(bw_oct) else bw_oct
        return np.exp(-0.5 * (np.log2(np.maximum(freqs[None], 1.0) / fc) / bw) ** 2)
    return g


def lowpass_gain(fc_fn, res_db=0.0, order=2):
    def g(freqs, times):
        fc = fc_fn(times)[:, None]
        f = freqs[None]
        lp = 1 / np.sqrt(1 + (f / fc) ** (2 * order))
        if res_db:
            lp *= 1 + (10 ** (res_db / 20) - 1) * np.exp(-0.5 * (np.log2(np.maximum(f, 1) / fc) / 0.25) ** 2)
        return lp
    return g


def saw(f, n, phase0=0.0):
    """PolyBLEP band-limited sawtooth with constant frequency f."""
    dt = f / SR
    p = (phase0 + dt * np.arange(n)) % 1.0
    y = 2 * p - 1
    m = p < dt
    tt = p[m] / dt
    y[m] -= tt + tt - tt * tt - 1
    m = p > 1 - dt
    tt = (p[m] - 1) / dt
    y[m] -= tt * tt + tt + tt + 1
    return y


def env_ar(n, attack, release_at, release, sr=SR):
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    a = a * a * (3 - 2 * a)
    r = np.clip(1 - (t - release_at) / max(release, 1e-4), 0, 1)
    r = r * r * (3 - 2 * r)
    return a * r


def interp_curve(points):
    """Piecewise-linear curve from [(t, v), ...] evaluated at arbitrary times."""
    ts, vs = zip(*points)
    return lambda x: np.interp(x, ts, vs)


# ----------------------------------------------------------------------------- music
CHORDS = [  # (start, end, midi notes)
    (0.0, 3.0, [50, 57, 62, 65]),          # Dm
    (3.0, 7.0, [46, 53, 57, 62]),          # Bbmaj7
    (7.0, 11.0, [41, 53, 57, 60, 67]),     # F add9
    (11.0, 15.0, [52, 55, 60, 62]),        # C/E add9
    (15.0, 19.0, [50, 53, 57, 62, 64]),    # Dm add9
    (19.0, 22.0, [46, 50, 53, 58, 62]),    # Bb
    (22.0, 23.0, [45, 50, 52, 57]),        # Asus4
    (23.0, 24.0, [45, 49, 52, 57, 61]),    # A
    (24.0, 30.0, [50, 54, 57, 62, 66, 69]),  # D major (resolution)
]
ROOTS = [(0.0, 38), (3.0, 34), (7.0, 41), (11.0, 36), (15.0, 38), (19.0, 34), (22.0, 33), (24.0, 38)]

CUTOFF = interp_curve([(0, 300), (3, 520), (7, 800), (11, 1150), (15, 1700), (19, 2300), (22, 2900),
                       (23.95, 4200), (24.0, 5200), (26, 3600), (30, 2000)])
PAD_LEVEL = interp_curve([(0, 0.0), (2.2, 0.38), (3, 0.40), (7, 0.42), (11, 0.52), (15, 0.66), (19, 0.82),
                          (23.9, 1.05), (24, 1.05), (30, 0.8)])


def root_at(t):
    r = ROOTS[0][1]
    for s, m in ROOTS:
        if t >= s - 1e-9:
            r = m
    return r


def pad(rng):
    out = np.zeros((N, 2))
    detune = [-14, -7, 0, 7, 14]
    pans = [-0.8, -0.4, 0.0, 0.4, 0.8]
    for ci, (s, e, notes) in enumerate(CHORDS):
        attack = 2.2 if ci == 0 else (0.25 if s in (24.0,) else 0.55)
        rel = 0.7 if e < 30 else 0.01
        n = int((e - s + rel) * SR)
        n = min(n, N - int(s * SR))
        env = env_ar(n, attack, e - s, rel)
        for m in notes:
            for d, p in zip(detune, pans):
                f = hz(m) * 2 ** (d / 1200)
                v = saw(f, n, rng.random()) * env / math.sqrt(len(notes) * len(detune))
                a = (p + 1) * math.pi / 4
                i0 = int(s * SR)
                out[i0:i0 + n, 0] += v * math.cos(a)
                out[i0:i0 + n, 1] += v * math.sin(a)
    filt = lowpass_gain(CUTOFF, res_db=4.0)
    for c in range(2):
        out[:, c] = stft_filter(out[:, c], filt, n_fft=4096, hop=1024)
    out *= PAD_LEVEL(T)[:, None]
    # slow stereo movement
    out[:, 0] *= 1 + 0.08 * np.sin(2 * math.pi * 0.11 * T)
    out[:, 1] *= 1 + 0.08 * np.sin(2 * math.pi * 0.11 * T + 2.0)
    return out


def pulse_times():
    ts = []
    for a, b, step in ((3.0, 11.0, 1.0), (11.0, 19.0, 0.5), (19.0, 22.0, 0.25), (22.0, 23.80, 0.125)):
        x = a
        while x < b - 1e-9:
            ts.append(round(x, 4))
            x += step
    return ts


def pulse_level(t):
    if t < 11:
        return 0.22 + 0.06 * (t - 3) / 8
    if t < 15:
        return 0.34
    if t < 19:
        return 0.46
    if t < 22:
        return 0.58
    return 0.60 + 0.32 * (t - 22) / 1.8


def bass(rng):
    out = np.zeros(N)
    duck = np.zeros(N)
    for tp in pulse_times():
        step = 1.0 if tp < 11 else 0.5 if tp < 19 else 0.25 if tp < 22 else 0.125
        f = hz(root_at(tp))
        n = int(min(1.2, step * 1.6) * SR)
        tt = np.arange(n) / SR
        fi = f * (1 + 0.5 * np.exp(-tt / 0.025))
        ph = 2 * math.pi * np.cumsum(fi) / SR
        tau = min(0.38, 0.55 * step)
        env = np.clip(tt / 0.006, 0, 1) * np.exp(-tt / tau)
        v = (np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)) * env
        v = np.tanh(1.4 * v) / np.tanh(1.4)
        i0 = int(round(tp * SR))
        j1 = min(N, i0 + n)
        lvl = pulse_level(tp)
        out[i0:j1] += v[:j1 - i0] * lvl
        if tp >= 15:
            d = np.exp(-tt / (0.6 * step))[:j1 - i0]
            duck[i0:j1] = np.maximum(duck[i0:j1], d)
    # gritty filtered-saw layer in the build
    grit = np.zeros(N)
    for s, e, m in ((15.0, 19.0, 38), (19.0, 22.0, 34), (22.0, 23.82, 33)):
        i0, i1 = int(s * SR), int(e * SR)
        grit[i0:i1] += saw(hz(m), i1 - i0, rng.random()) * env_ar(i1 - i0, 0.05, e - s - 0.05, 0.05)
    grit = stft_filter(grit, lowpass_gain(interp_curve([(0, 200), (15, 220), (22, 450), (24, 900)]), 6.0),
                       n_fft=4096, hop=1024)
    grit *= interp_curve([(0, 0), (15, 0.05), (19, 0.08), (23.8, 0.16), (23.85, 0)])(T)
    out += grit * (1 - 0.6 * duck)
    # sustained resolution bass under the final chord
    i0 = int(24.0 * SR)
    n = N - i0
    tt = np.arange(n) / SR
    out[i0:] += (np.sin(2 * math.pi * hz(26) * tt) * 0.5 + np.sin(2 * math.pi * hz(38) * tt) * 0.35) \
        * np.clip(tt / 0.02, 0, 1) * np.exp(-tt / 2.8) * 0.55
    return out, duck


def bell(f0, dur=3.0, bright=1.0, rng=None):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, dec in ((1.0, 1.0, 1.6), (2.0, 0.45, 1.0), (2.76, 0.22 * bright, 0.55),
                            (5.40, 0.10 * bright, 0.30), (8.93, 0.05 * bright, 0.18)):
        ph = rng.random() * 2 * math.pi if rng is not None else 0.0
        out += amp * np.sin(2 * math.pi * f0 * ratio * tt + ph) * np.exp(-tt / dec)
        out += amp * 0.35 * np.sin(2 * math.pi * f0 * ratio * 1.0035 * tt) * np.exp(-tt / dec)
    out *= np.clip(tt / 0.002, 0, 1)
    return out / 1.8


def resolution_bells(rng):
    out = np.zeros((N, 2))
    seq = [(24.05, 74), (24.25, 78), (24.45, 81), (24.65, 86), (25.15, 81), (25.45, 78), (25.9, 74), (26.6, 81)]
    for k, (tb, m) in enumerate(seq):
        b = bell(hz(m), 3.5, 0.7, rng) * (0.20 if k < 4 else 0.13)
        place(out, b, tb, pan=(-0.5 if k % 2 else 0.5))
    # high shimmer pad
    i0 = int(24.0 * SR)
    tt = np.arange(N - i0) / SR
    sh = (np.sin(2 * math.pi * hz(86) * tt) + 0.7 * np.sin(2 * math.pi * hz(93) * tt)) \
        * (0.5 + 0.5 * np.sin(2 * math.pi * 5.5 * tt)) * np.clip(tt / 1.2, 0, 1) * np.exp(-tt / 3.5)
    out[i0:, 0] += sh * 0.025
    out[i0:, 1] += np.roll(sh, 240) * 0.025
    return out


# ----------------------------------------------------------------------------- sound effects
def whoosh(rng, pre=0.55, post=0.40, f_lo=250, f_hi=5200, direction=1.0):
    n = int((pre + post) * SR)
    tt = np.arange(n) / SR - pre
    noise = rng.normal(0, 1, (n, 2))
    noise[:, 1] = 0.6 * noise[:, 0] + 0.8 * noise[:, 1]

    def fc(times):
        x = times - pre
        up = f_lo * (f_hi / f_lo) ** np.clip((x + pre) / pre, 0, 1) ** 1.6
        down = f_hi * np.exp(-np.maximum(x, 0) / 0.25) + 900 * (1 - np.exp(-np.maximum(x, 0) / 0.25))
        return np.where(x < 0, up, down)

    filt = bandpass_gain(fc, 1.1)
    out = np.stack([stft_filter(noise[:, c], filt, n_fft=1024, hop=256) for c in range(2)], -1)
    env = np.where(tt < 0, np.clip((tt + pre) / pre, 0, 1) ** 2.6, np.exp(-tt / 0.13))
    pan = direction * np.tanh(tt / 0.18)
    a = (pan + 1) * math.pi / 4
    out[:, 0] *= env * np.cos(a) * math.sqrt(2)
    out[:, 1] *= env * np.sin(a) * math.sqrt(2)
    return out / (np.abs(out).max() + 1e-9)


def boom(rng, big=1.0):
    dur = 3.2
    n = int(dur * SR)
    tt = np.arange(n) / SR
    f = 32 + 95 * np.exp(-tt / 0.06)
    ph = 2 * math.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.clip(tt / 0.003, 0, 1) * np.exp(-tt / (0.9 * big))
    body = np.tanh(2.0 * body) / np.tanh(2.0)
    sub = np.sin(2 * math.pi * 33 * tt) * np.exp(-tt / (1.6 * big)) * np.clip(tt / 0.02, 0, 1) * 0.45
    hit = rng.normal(0, 1, n) * np.exp(-tt / 0.018)
    hit = stft_filter(hit, lowpass_gain(lambda x: np.full_like(x, 1800.0)), n_fft=512, hop=128) * 0.5
    return (body + sub + hit) / 1.5


def tick(rng):
    n = int(0.09 * SR)
    tt = np.arange(n) / SR
    click = np.diff(rng.normal(0, 1, n + 1)) * np.exp(-tt / 0.0025) * 0.35
    blip = np.sin(2 * math.pi * 2900 * tt) * np.exp(-tt / 0.010) * 0.6
    thump = np.sin(2 * math.pi * 140 * tt) * np.exp(-tt / 0.03) * 0.5
    return (click + blip + thump) * np.clip(tt / 0.0004, 0, 1)


def riser(rng):
    s, e = RISER
    dur = e - s
    n = int(dur * SR)
    tt = np.arange(n) / SR
    p = tt / dur
    noise = rng.normal(0, 1, (n, 2))
    filt = bandpass_gain(lambda x: 350 * (9000 / 350) ** np.clip(x / dur, 0, 1) ** 1.3,
                         lambda x: 1.6 - 0.8 * np.clip(x / dur, 0, 1))
    nz = np.stack([stft_filter(noise[:, c], filt, n_fft=1024, hop=256) for c in range(2)], -1)
    nz /= np.abs(nz).max() + 1e-9
    rate = 4 + 22 * p ** 2
    trem = 1 - 0.35 * (0.5 + 0.5 * np.sin(2 * math.pi * np.cumsum(rate) / SR))
    f = 110 * 2 ** (3.0 * p ** 1.3)
    ph = np.cumsum(f) / SR
    tone = np.sin(2 * math.pi * ph) + 0.5 * np.sin(2 * math.pi * ph * 1.5) + 0.3 * np.sin(2 * math.pi * ph * 2.01)
    amp = p ** 2.2
    cut = np.clip((dur - 0.03 - tt) / 0.025, 0, 1)
    out = nz * (amp * trem * cut)[:, None] * 0.8
    out += (tone * amp * 0.22 * cut)[:, None] * np.array([1.0, 0.94])
    return out


def rain(rng):
    s, e = RAIN
    n = int((e - s) * SR)
    tt = np.arange(n) / SR
    bed = rng.normal(0, 1, (n, 2))
    filt = bandpass_gain(lambda x: np.full_like(x, 4800.0), 1.3)
    bed = np.stack([stft_filter(bed[:, c], filt, n_fft=1024, hop=256) for c in range(2)], -1)
    bed /= np.abs(bed).max() + 1e-9
    out = bed * 0.22
    # individual drops: tiny filtered clicks and plinks
    nd = rng.poisson(420)
    for _ in range(nd):
        t0 = rng.random() * (e - s)
        ln = int(0.03 * SR)
        k = np.arange(ln) / SR
        if rng.random() < 0.7:
            d = np.diff(rng.normal(0, 1, ln + 1)) * np.exp(-k / rng.uniform(0.002, 0.006))
        else:
            d = np.sin(2 * math.pi * rng.uniform(1500, 5200) * k) * np.exp(-k / rng.uniform(0.006, 0.02))
        amp = rng.uniform(0.05, 0.35) ** 1.3
        pan = rng.uniform(-0.9, 0.9)
        i0 = int(t0 * SR)
        j1 = min(n, i0 + ln)
        a = (pan + 1) * math.pi / 4
        out[i0:j1, 0] += d[:j1 - i0] * amp * math.cos(a)
        out[i0:j1, 1] += d[:j1 - i0] * amp * math.sin(a)
    fade = np.clip(tt / 0.03, 0, 1) * np.clip((e - s - tt) / 0.04, 0, 1)
    return out * fade[:, None]


# ----------------------------------------------------------------------------- mix
def reverb_ir(rng, dur=2.8, predelay=0.02):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    ir = rng.normal(0, 1, (n, 2)) * np.exp(-tt / (dur / 6.9))[:, None]
    damp = lowpass_gain(lambda x: 9000 * np.exp(-np.maximum(x, 0) / 0.9) + 600)
    ir = np.stack([stft_filter(ir[:, c], damp, n_fft=1024, hop=256) for c in range(2)], -1)
    ir = np.concatenate([np.zeros((int(predelay * SR), 2)), ir])
    return ir / np.sqrt((ir ** 2).sum(0, keepdims=True))


def convolve(x, ir):
    n = len(x) + len(ir) - 1
    nfft = 1 << (n - 1).bit_length()
    out = np.zeros((len(x), 2))
    for c in range(2):
        y = np.fft.irfft(np.fft.rfft(x[:, c], nfft) * np.fft.rfft(ir[:, c], nfft), nfft)
        out[:, c] = y[:len(x)]
    return out


def limiter(x, ceiling=0.89, look=0.004, release=0.12, blk=32):
    nb = -(-len(x) // blk)
    a = np.abs(np.pad(x, ((0, nb * blk - len(x)), (0, 0)))).max(1).reshape(nb, blk).max(1)
    L = max(1, int(look * SR / blk))
    pk = a.copy()
    for k in range(1, L + 1):
        pk[:-k] = np.maximum(pk[:-k], a[k:])
        pk[k:] = np.maximum(pk[k:], a[:-k])
    target = np.minimum(1.0, ceiling / np.maximum(pk, 1e-9))
    rel = math.exp(-blk / (release * SR))
    g = np.empty(nb)
    cur = 1.0
    for i in range(nb):
        cur = min(target[i], 1 - (1 - cur) * rel)
        g[i] = cur
    k = np.ones(2 * L + 1) / (2 * L + 1)
    g = np.minimum(g, np.convolve(np.pad(g, L, mode="edge"), k, mode="valid"))
    centers = (np.arange(nb) + 0.5) * blk
    gs = np.interp(np.arange(len(x)), centers, g)
    return x * gs[:, None], g.min()


def build(path):
    rng = np.random.default_rng(2026)
    dry = np.zeros((N, 2))
    send = np.zeros((N, 2))

    pd = pad(rng)
    b, duck = bass(rng)
    pd *= (1 - 0.30 * duck)[:, None]
    dry += pd * 0.34
    send += pd * 0.30
    dry += b[:, None] * np.array([0.62, 0.62])
    send += b[:, None] * 0.05

    bells = resolution_bells(rng)
    dry += bells
    send += bells * 0.9

    # whooshes on every scene transition (peak right at the cut)
    for k, tr in enumerate(TRANSITIONS):
        soft = tr == 28.0
        w = whoosh(rng, pre=0.75 if soft else 0.55, post=0.6 if soft else 0.40,
                   f_hi=3200 if soft else 5200, direction=1.0 if k % 2 == 0 else -1.0)
        g = 0.22 if soft else 0.36
        place(dry, w, tr - (0.75 if soft else 0.55), gain=g)
        place(send, w, tr - (0.75 if soft else 0.55), gain=g * 0.5)

    for tb in FLASH_TIMES:
        big = 1.25 if tb == 24.0 else 1.0
        bm = boom(rng, big)
        place(dry, bm, tb, gain=0.95 if tb == 24.0 else 0.8)
        place(send, bm, tb, gain=0.25)

    for k, tl in enumerate(LENS_TIMES):
        d = bell((880.0, 1046.5, 1396.9)[k], 2.6, 1.0, rng)
        ph = np.arange(len(d)) / SR
        d *= 1 + 0.25 * np.sin(2 * math.pi * 7.0 * ph)          # shimmer
        place(dry, d, tl, pan=(-0.3, -0.3, 0.35)[k], gain=0.22)
        place(send, d, tl, pan=(-0.3, -0.3, 0.35)[k], gain=0.35)

    for tk in TICKS:
        place(dry, tick(rng), tk, gain=0.45)
        place(send, tick(rng), tk, gain=0.12)

    r = riser(rng)
    place(dry, r, RISER[0], gain=0.42)
    place(send, r, RISER[0], gain=0.20)

    rn = rain(rng)
    place(dry, rn, RAIN[0], gain=0.40)
    place(send, rn, RAIN[0], gain=0.10)

    wet = convolve(send, reverb_ir(rng))
    mix = dry + wet * 0.55
    mix -= mix.mean(0, keepdims=True)

    # master: pre-gain, limiter, peak-normalise to -1 dBFS, fade-out over the last 1.5 s
    mix *= 0.89 / np.percentile(np.abs(mix), 99.95)
    mix, gmin = limiter(mix, ceiling=0.89)
    fade = np.ones(N)
    k = T >= DUR - 1.5
    x = (T[k] - (DUR - 1.5)) / 1.5
    fade[k] = 0.5 * (1 + np.cos(math.pi * x))
    mix *= fade[:, None]
    target = 10 ** (-1.0 / 20)
    mix *= target / np.abs(mix).max()
    assert mix.shape == (N, 2)
    write_wav_f32(path, mix.astype(np.float32))
    rms = 20 * math.log10(np.sqrt((mix ** 2).mean()))
    print(f"audio: {N} samples ({N / SR:.3f}s), peak -1.00 dBFS, rms {rms:.1f} dBFS, "
          f"limiter max reduction {20 * math.log10(gmin):.1f} dB -> {path}")


def write_wav_f32(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n, ch = data.shape
    raw = data.tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 3, ch, SR, SR * ch * 4, ch * 4, 32))
        f.write(b"data" + struct.pack("<I", len(raw)) + raw)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "build", "audio.wav"))
