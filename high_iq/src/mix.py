"""Sound design and final mix.

Everything is synthesized with numpy/scipy: whooshes on transitions, pops when numbers
and icons appear, a riser into the 160+ reveal, a bell ding for the gold dot and an
original lo-fi ambient bed (no samples, no copyrighted music). The bed is sidechain-ducked
under the voice, then the mix is normalized to -14 LUFS with a -1 dBFS peak ceiling.

Reads build/vo.wav and build/timeline.json, writes build/mix.wav (48 kHz stereo).
"""
import json, os
import numpy as np
import soundfile as sf
import pyloudnorm as pyln
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "build")
SR = 48000
rng = np.random.default_rng(7)


def db(x):
    return 10 ** (x / 20)


def env_adsr(n, a, d, s_lvl, r):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    s = max(0, n - a - d - r)
    e = np.concatenate([np.linspace(0, 1, a, endpoint=False), np.linspace(1, s_lvl, d, endpoint=False),
                        np.full(s, s_lvl), np.linspace(s_lvl, 0, r)])
    return np.pad(e, (0, max(0, n - len(e))))[:n]


def bandpass_sweep(x, f0, f1, q=2.0, blocks=64):
    """Time-varying band-pass (block-wise biquads, smoothly crossfaded)."""
    out = np.zeros_like(x)
    edges = np.linspace(0, len(x), blocks + 1).astype(int)
    freqs = np.geomspace(f0, f1, blocks) if f0 > 0 and f1 > 0 else np.linspace(f0, f1, blocks)
    zi = None
    for k in range(blocks):
        b, a = signal.iirpeak(min(freqs[k], SR / 2 - 100), q, fs=SR)
        seg = x[edges[k]:edges[k + 1]]
        if zi is None:
            zi = signal.lfilter_zi(b, a) * 0
        y, zi = signal.lfilter(b, a, seg, zi=zi)
        out[edges[k]:edges[k + 1]] = y
    return out


# ---------------------------------------------------------------- sound effects
def whoosh(dur=0.55, up=True):
    n = int(dur * SR)
    noise = rng.standard_normal(n)
    sweep = bandpass_sweep(noise, 350, 4200, q=1.6) if up else bandpass_sweep(noise, 3800, 300, q=1.6)
    t = np.linspace(0, 1, n)
    env = np.sin(np.pi * t ** 0.8) ** 2
    body = sweep * env
    air = signal.sosfilt(signal.butter(2, 6000, "hp", fs=SR, output="sos"), noise) * env ** 2 * 0.15
    mono = body + air
    mono /= np.abs(mono).max() + 1e-9
    pan = np.linspace(-0.8, 0.8, n)            # moves left -> right
    return np.stack([mono * np.sqrt((1 - pan) / 2), mono * np.sqrt((1 + pan) / 2)], 1)


def pop(pitch=1.0):
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = (260 + 900 * np.exp(-t * 55)) * pitch
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) * np.exp(-t * 32)
    click = rng.standard_normal(n) * np.exp(-t * 900) * 0.35
    x = tone + click
    x = signal.sosfilt(signal.butter(2, 80, "hp", fs=SR, output="sos"), x)
    x /= np.abs(x).max()
    return np.stack([x, x], 1)


def riser(dur=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    noise = rng.standard_normal(n)
    nz = bandpass_sweep(noise, 300, 7000, q=1.2, blocks=96)
    f = 110 * 2 ** (u * 3.2)                     # three-octave upward glide
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = sum(np.sin(ph * h + h) / h for h in (1, 2, 3, 5)) * 0.5
    trem = 0.75 + 0.25 * np.sin(2 * np.pi * (4 + 18 * u ** 2) * t)
    env = u ** 2.2
    x = (nz * 0.8 + tone * 0.6) * env * trem
    x[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))
    x /= np.abs(x).max()
    lag = int(0.012 * SR)                       # slight stereo width
    return np.stack([x, np.concatenate([np.zeros(lag), x[:-lag]])], 1)


def impact(dur=1.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 38 + 70 * np.exp(-t * 18)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5)
    hit = signal.sosfilt(signal.butter(2, 2500, "lp", fs=SR, output="sos"), rng.standard_normal(n)) * np.exp(-t * 30)
    x = boom + 0.5 * hit
    x /= np.abs(x).max()
    return np.stack([x, x], 1)


def ding(f0=1318.5, dur=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    partials = [(1.0, 1.0, 2.2), (2.0, 0.45, 3.0), (2.76, 0.35, 4.0), (5.40, 0.18, 6.5), (8.93, 0.08, 9.0)]
    x = sum(a * np.sin(2 * np.pi * f0 * r * t + r) * np.exp(-t * d) for r, a, d in partials)
    x *= 1 - np.exp(-t * 900)
    x /= np.abs(x).max()
    lag = int(0.009 * SR)
    return np.stack([x, np.concatenate([np.zeros(lag), x[:-lag]]) * 0.95], 1)


def sparkle(dur=1.0):
    n = int(dur * SR)
    out = np.zeros(n)
    for k in range(9):
        a = int(k / 9 * 0.7 * SR)
        f = 1800 * 2 ** (rng.integers(0, 12) / 12)
        m = int(0.25 * SR)
        tt = np.arange(m) / SR
        out[a:a + m] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 18) * (0.6 + 0.4 * rng.random())
    out /= np.abs(out).max()
    return np.stack([out, out[::-1] * 0 + out], 1)


# ---------------------------------------------------------------- lo-fi bed
def midi(m):
    return 440 * 2 ** ((m - 69) / 12)


def epiano(f, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    mod = 1.6 * np.exp(-t * 6)
    x = np.sin(2 * np.pi * f * t + mod * np.sin(2 * np.pi * f * t)) + 0.18 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 3)
    return x * np.exp(-t * 1.6) * (1 - np.exp(-t * 400)) * vel


def pad(freqs, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.0, 0.12):
            ff = f * 2 ** (det / 12)
            ph = rng.random()
            x += signal.sawtooth(2 * np.pi * (ff * t + ph)) * 0.33
    x = signal.sosfilt(signal.butter(2, 900, "lp", fs=SR, output="sos"), x)
    return x * env_adsr(n, 0.9, 0.5, 0.85, 1.2)


def lofi_bed(total):
    n = int(total * SR)
    bpm = 80
    beat = 60 / bpm
    bar = 4 * beat
    # Am9 - Fmaj7 - Cmaj7 - G6, two bars each... one bar each keeps it moving
    prog = [
        (45, [57, 60, 64, 67, 71]),
        (41, [57, 60, 64, 65, 69]),
        (48, [55, 59, 60, 64, 67]),
        (43, [55, 59, 62, 64, 67]),
    ]
    keys = np.zeros(n); pads = np.zeros(n); bass = np.zeros(n); drums = np.zeros(n)
    nbars = int(np.ceil(total / bar)) + 1
    for b in range(nbars):
        root, chord = prog[b % 4]
        t0 = b * bar
        a = int(t0 * SR)
        p = pad([midi(m) for m in chord[:4]], bar + 1.2)
        pads[a:a + len(p)] += p[: max(0, n - a)]
        bs = epiano(midi(root), bar, 0.9) * 0 + np.sin(2 * np.pi * midi(root) * np.arange(int(bar * SR)) / SR) \
            * env_adsr(int(bar * SR), 0.02, 0.4, 0.6, 0.5)
        bass[a:a + len(bs)] += bs[: max(0, n - a)]
        # lazy e-piano stabs: beat 1 and the "and" of 2 (swung), little arpeggio on 4
        for off, notes, vel in [(0, chord, 0.8), (1.62, chord[1:4], 0.55), (3.0, chord[-2:], 0.45), (3.55, chord[2:3], 0.4)]:
            for j, m in enumerate(notes):
                ts = t0 + off * beat + j * 0.018
                e = epiano(midi(m), 2.2, vel)
                s = int(ts * SR)
                keys[s:s + len(e)] += e[: max(0, n - s)]
        # drums
        for k in range(8):
            ts = t0 + k * beat / 2 + (0.06 if k % 2 else 0)
            s = int(ts * SR)
            m = int(0.09 * SR)
            hh = signal.sosfilt(signal.butter(2, 7000, "hp", fs=SR, output="sos"), rng.standard_normal(m)) \
                * np.exp(-np.arange(m) / SR * 60) * (0.35 if k % 2 else 0.5)
            drums[s:s + m] += hh[: max(0, n - s)]
        for k in (0, 2.5):
            s = int((t0 + k * beat) * SR)
            m = int(0.35 * SR)
            tt = np.arange(m) / SR
            kick = np.sin(2 * np.pi * np.cumsum(48 + 90 * np.exp(-tt * 30)) / SR) * np.exp(-tt * 9)
            drums[s:s + m] += kick[: max(0, n - s)] * 1.4
        for k in (1, 3):
            s = int((t0 + k * beat) * SR)
            m = int(0.25 * SR)
            tt = np.arange(m) / SR
            sn = signal.sosfilt(signal.butter(2, [900, 4000], "bp", fs=SR, output="sos"), rng.standard_normal(m)) \
                * np.exp(-tt * 22) + 0.4 * np.sin(2 * np.pi * 190 * tt) * np.exp(-tt * 30)
            drums[s:s + m] += sn[: max(0, n - s)] * 0.7
    # vinyl: hiss and crackle
    hiss = signal.sosfilt(signal.butter(2, [800, 6000], "bp", fs=SR, output="sos"), rng.standard_normal(n)) * 0.02
    crackle = np.zeros(n)
    idx = rng.integers(0, n, int(total * 9))
    crackle[idx] = rng.standard_normal(len(idx)) * 0.5
    crackle = signal.sosfilt(signal.butter(2, 2500, "hp", fs=SR, output="sos"), crackle)
    mix = 0.55 * pads + 0.65 * keys + 0.45 * bass + 0.55 * drums + hiss + 0.25 * crackle
    # lo-fi tone: gentle wobble (tape) and low-pass to stay out of the voice's way
    mix = signal.sosfilt(signal.butter(2, 3200, "lp", fs=SR, output="sos"), mix)
    mix = signal.sosfilt(signal.butter(2, 45, "hp", fs=SR, output="sos"), mix)
    wob = 1 + 0.08 * np.sin(2 * np.pi * 0.35 * np.arange(n) / SR)
    mix *= wob
    st = np.stack([mix, np.roll(mix, int(0.011 * SR))], 1)
    fade_in, fade_out = int(0.4 * SR), int(1.2 * SR)
    st[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    st[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return st


# ---------------------------------------------------------------- mixing
def place(buf, clip, t, gain_db, align="start"):
    s = int(round(t * SR))
    if align == "end":
        s -= len(clip)
    elif align == "peak":
        s -= int(np.argmax(np.abs(clip).sum(1)))
    a = max(s, 0)
    c = clip[a - s:]
    e = min(len(buf), a + len(c))
    if e > a:
        buf[a:e] += c[: e - a] * db(gain_db)


def voice_envelope(vo):
    hop = int(0.01 * SR)
    n = len(vo) // hop
    rms = np.sqrt(np.mean(vo[: n * hop].reshape(n, hop) ** 2, 1))
    active = (20 * np.log10(rms + 1e-9) > -42).astype(float)
    # attack 30 ms, release 350 ms one-pole smoothing
    env = np.zeros(n)
    for i in range(n):
        prev = env[i - 1] if i else 0
        c = 0.28 if active[i] > prev else 0.028
        env[i] = prev + c * (active[i] - prev)
    return np.repeat(env, hop)[: len(vo)].tolist() + [0] * (len(vo) - n * hop)


def limiter(x, ceiling_db=-1.0, look=0.005, release=0.08):
    ceil = db(ceiling_db)
    la = int(look * SR)
    peak = np.abs(x).max(1)
    need = np.minimum(1, ceil / np.maximum(peak, 1e-9))
    # look-ahead minimum, then smooth release
    from scipy.ndimage import minimum_filter1d
    g = minimum_filter1d(need, size=2 * la + 1, origin=0)
    rel = np.exp(-1 / (release * SR))
    out = np.empty_like(g)
    cur = 1.0
    for i, v in enumerate(g):
        cur = v if v < cur else v + (cur - v) * rel
        out[i] = cur
    out = signal.lfilter([1 / la] * la, [1], np.concatenate([out, np.ones(la)]))[la:]
    out = np.minimum(out, g)  # never exceed the ceiling
    return x * out[:, None]


def main():
    tl = json.load(open(os.path.join(BUILD, "timeline.json")))
    ev = tl["events"]
    total = tl["duration"]
    n = int(total * SR)
    vo, sr = sf.read(os.path.join(BUILD, "vo.wav"))
    assert sr == SR
    vo = vo[:n]
    meter = pyln.Meter(SR)
    # voice chain: gentle high-pass, presence and a soft compressor feel via normalization
    vo = signal.sosfilt(signal.butter(2, 70, "hp", fs=SR, output="sos"), vo)
    v_lufs = meter.integrated_loudness(vo)
    voice = np.stack([vo, vo], 1)

    # --- sound effects
    sfx = np.zeros((n, 2))
    for sc in tl["scenes"][1:]:
        if sc["scene"] == 3:
            continue  # scene 3 is a camera move; its whoosh is placed on the "zoom" event
        place(sfx, whoosh(0.55), sc["start"] + 0.22, -9, align="peak")
    place(sfx, whoosh(0.7), ev["zoom"] + 0.35, -10, align="peak")
    pops = [("n2", 1.0), ("n100", 1.12), ("iq130", 1.25), ("avg", 1.0), ("shade68", 0.9), ("l85", 1.1),
            ("l115", 1.2), ("t130", 1.0), ("gifted", 1.15), ("p2", 1.3), ("t145", 1.05), ("r1000", 1.2),
            ("r30000", 1.3), ("herit", 1.0), ("herit80", 1.15), ("gene", 0.9), ("env", 1.0), ("food", 1.0),
            ("sleep", 1.12), ("books", 1.25), ("bulb", 1.4), ("nature", 1.0), ("nurture", 1.12),
            ("ring", 1.0)]
    for key, p in pops:
        place(sfx, pop(p), ev[key], -15)
    rz = riser(2.2)
    place(sfx, rz, ev["t160"], -11, align="end")
    place(sfx, impact(), ev["t160"], -9)
    place(sfx, ding(), ev["gold"], -8)
    place(sfx, sparkle(), ev["thousands"], -21)
    place(sfx, sparkle(), ev["grow"], -22)
    place(sfx, pop(0.7), ev["gene_x"], -16)
    place(sfx, ding(1760, 1.6), ev["together"] + 0.05, -17)

    # --- music bed, ducked under the voice
    bed = lofi_bed(total)[:n]
    b_lufs = meter.integrated_loudness(bed)
    duck_depth = 5.0                             # dB of extra reduction while the voice talks
    target_open = v_lufs - 12.0                  # in pauses ~-12 LU, under speech ~-20 dB
    bed *= db(target_open - b_lufs)
    env = np.asarray(voice_envelope(vo))
    bed *= db(-duck_depth * env)[:, None]

    mix = voice + sfx + bed
    lufs = meter.integrated_loudness(mix)
    mix *= db(-14.0 - lufs)
    mix = limiter(mix, -1.0)
    final_lufs = meter.integrated_loudness(mix)
    # one more trim pass so limiting does not leave us under target
    mix = limiter(mix * db(-14.0 - final_lufs), -1.0)
    sf.write(os.path.join(BUILD, "mix.wav"), mix.astype(np.float32), SR, subtype="FLOAT")
    under = 20 * np.log10(np.sqrt(np.mean((bed[env > 0.9]) ** 2)) / np.sqrt(np.mean(vo[env > 0.9] ** 2)))
    print(f"voice {v_lufs:.1f} LUFS, music under voice {under:.1f} dB (RMS), "
          f"final {meter.integrated_loudness(mix):.2f} LUFS, peak {20*np.log10(np.abs(mix).max()):.2f} dBFS")


if __name__ == "__main__":
    main()
