"""Character voices: procedural "blocky game" speech (Simlish-style babble) generated from each line's syllables.

Every dialogue line in config.VOICE_LINES is turned into syllables (onset consonant + vowel), and each syllable is
synthesized with a glottal pulse source through vowel formant filters, with per-character pitch, formant scale,
speaking rate and intonation (questions rise, exclamations jump, red key words are stressed). Styles: whisper
(noise source), shout (higher, louder, saturated), phone (telephone band). Narration stays text-only (captions).

  python voices.py   -> build/voice.wav, build/voice_lines.json (timings), build/voice_env.json (mouth flaps)
"""
import json
import math
import os
import re

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

from config import SR, DURATION, FPS, NFRAMES, VOICE_LINES, DIALOGUE_SPEAKERS

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, 'build')
N = int(round(DURATION * SR))

# pitch (Hz), formant scale, seconds per syllable, pitch range (semitones), breathiness
VOICES = {
    'timmy': dict(f0=275, fmt=1.22, syl=0.135, rng=4.0, breath=0.10, gain=0.0),
    'gray': dict(f0=92, fmt=0.9, syl=0.205, rng=1.5, breath=0.05, gain=0.0),   # slow, flat, low: creepy calm
    'op': dict(f0=205, fmt=1.08, syl=0.13, rng=3.0, breath=0.06, gain=-1.0),
    'cop': dict(f0=118, fmt=0.97, syl=0.135, rng=3.0, breath=0.05, gain=0.0),
    'cop2': dict(f0=142, fmt=1.0, syl=0.14, rng=2.5, breath=0.05, gain=0.0),
}
VOWELS = {'a': (750, 1250, 2550), 'e': (520, 1850, 2600), 'i': (320, 2250, 3000), 'o': (520, 920, 2450),
          'u': (360, 900, 2300), 'ei': (460, 2000, 2650), 'ai': (680, 1500, 2550), 'schwa': (550, 1400, 2500)}
PLOSIVE, FRIC, NASAL, LIQUID = set('bdgptkcq'), set('szfvhjx'), set('mn'), set('lrwy')


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [max(20, lo), min(SR / 2 - 100, hi)], 'bandpass', fs=SR, output='sos'), x)


def lp(x, f, order=2):
    return sosfilt(butter(order, f, 'lowpass', fs=SR, output='sos'), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, 'highpass', fs=SR, output='sos'), x)


def clean(text):
    t = re.sub(r'[*~"]', '', text)
    t = re.sub(r'[\U0001F300-\U0001FAFF]', '', t)
    t = t.replace('911', 'nine one one').replace('42', 'forty two')
    return t.strip()


def syllables(text):
    """-> list of (onset consonants, vowel key, stressed, pause_after_s, word_final, punct)."""
    out = []
    stressed_words = set(w.strip('*~.,!?…').lower() for w in re.findall(r'[*~][^*~]+[*~]', text) for w in w.split())
    words = clean(text).split()
    for wi, w in enumerate(words):
        punct = w[-1] if w[-1] in '.,!?…' else ''
        base = w.strip('.,!?…').lower()
        letters = re.sub(r'[^a-z]', '', base)
        groups = list(re.finditer(r'[aeiouy]+', letters)) or [None]
        # a silent final "e" is not a syllable (e.g. "here", "safe")
        if len(groups) > 1 and groups[-1] is not None and groups[-1].group() == 'e' and groups[-1].end() == len(letters):
            groups = groups[:-1]
        prev = 0
        for gi, g in enumerate(groups):
            if g is None:
                onset, vg = letters, 'schwa'
            else:
                onset, vg = letters[prev:g.start()], g.group()
                prev = g.end()
            key = {'ai': 'ai', 'ay': 'ei', 'ei': 'ei', 'ee': 'i', 'ea': 'i', 'oo': 'u', 'ou': 'u', 'ow': 'o', 'oy': 'o'}.get(
                vg[:2], vg[0] if vg[0] != 'y' else 'i') if g is not None else 'schwa'
            last = gi == len(groups) - 1
            pause = 0.0
            if last:
                pause = {'': 0.035, ',': 0.17, '.': 0.28, '!': 0.26, '?': 0.3, '…': 0.38}[punct]
            out.append((onset, key, base in stressed_words or w.isupper() and len(w) > 1, pause, last,
                        punct if last else '', letters[prev:] if last else ''))
    return out


def glottal(f0, n, breath, r):
    ph = np.cumsum(f0) / SR
    frac = ph % 1.0
    src = (1 - frac) ** 3 * 2 - 0.5        # sharp closure, soft opening
    src = lp(src, 2600)
    src += r.standard_normal(n) * breath
    return src


def synth_line(text, speaker, style, seed=0):
    v = VOICES[speaker]
    r = np.random.default_rng(seed)
    syl = syllables(text)
    rate = v['syl'] * (0.85 if style == 'shout' else 1.0) * (1.1 if style == 'whisper' else 1.0)
    pieces = []
    env_marks = []
    nsyl = len(syl)
    question = clean(text).endswith('?')
    excl = '!' in text
    t_cursor = 0.0
    for i, (onset, key, stressed, pause, last, punct, coda) in enumerate(syl):
        dur = rate * (1.35 if stressed else 1.0) * r.uniform(0.85, 1.15) * (1.3 if last and punct else 1.0)
        n = int(dur * SR)
        # intonation: gentle declination, stress bumps, question rise, exclamation lift
        u = i / max(1, nsyl - 1)
        semi = v['rng'] * (0.6 - 0.9 * u) + (v['rng'] * 0.8 if stressed else 0) + r.uniform(-0.6, 0.6)
        if question and i >= nsyl - 2:
            semi += v['rng'] * 1.4 * (1 if i == nsyl - 1 else 0.5)
        if excl:
            semi += 2.5
        if style == 'shout':
            semi += 4
        f_start = v['f0'] * 2 ** (semi / 12)
        f_end = f_start * 2 ** ((-1.2 if not (question and i == nsyl - 1) else 2.5) / 12)
        f0 = np.linspace(f_start, f_end, n) * (1 + 0.012 * np.sin(2 * np.pi * 5.5 * np.arange(n) / SR))
        F = [f * v['fmt'] for f in VOWELS[key]]
        if style == 'whisper':
            src = r.standard_normal(n) * 0.6
        else:
            src = glottal(f0, n, v['breath'], r)
        vow = bp(src, F[0] * 0.82, F[0] * 1.18) + 0.6 * bp(src, F[1] * 0.9, F[1] * 1.1) + 0.28 * bp(src, F[2] * 0.93,
                                                                                                    F[2] * 1.07)
        t = np.arange(n) / SR
        e = np.minimum(1, t / 0.018) * np.minimum(1, (dur - t) / 0.035)
        vow *= np.clip(e, 0, 1) * (1.25 if stressed else 1.0)
        # onset consonant
        on = np.zeros(0)
        c = onset[:1]
        if c in PLOSIVE:
            m = int(0.045 * SR)
            burst = hp(r.standard_normal(m), 1800) * np.exp(-np.arange(m) / SR / 0.008) * 0.5
            on = np.concatenate([np.zeros(int(0.018 * SR)), burst])
        elif c in FRIC or onset[:2] in ('sh', 'th', 'ch'):
            m = int(0.07 * SR)
            lo, hi = (3800, 9000) if c in 'szx' else (1500, 6000) if c in 'fv' else (2000, 7000) if onset[:2] in (
                'sh', 'ch') else (600, 3200)
            on = bp(r.standard_normal(m), lo, hi) * np.hanning(m) * 0.45
        elif c in NASAL:
            m = int(0.055 * SR)
            nas = lp(glottal(np.full(m, f0[0]), m, 0.02, r), 450) * np.hanning(m) * 0.8
            on = nas if style != 'whisper' else nas * 0.2
        elif c in LIQUID:
            m = int(0.04 * SR)
            on = bp(glottal(np.full(m, f0[0]), m, 0.03, r), 300, 1500) * np.hanning(m) * 0.5
        cod = np.zeros(0)
        if coda and coda[-1] in PLOSIVE | FRIC:
            m = int(0.05 * SR)
            cod = hp(r.standard_normal(m), 2500) * np.exp(-np.arange(m) / SR / 0.012) * 0.25
        seg = np.concatenate([on, vow, cod, np.zeros(int(pause * SR))])
        env_marks.append((t_cursor + len(on) / SR, t_cursor + (len(on) + len(vow)) / SR))
        t_cursor += len(seg) / SR
        pieces.append(seg)
    y = np.concatenate(pieces)
    if style == 'whisper':
        y = hp(y, 350)
        y = lp(y, 5000)
    if style == 'shout':
        y = np.tanh(y / (np.max(np.abs(y)) + 1e-9) * 2.2)
    if style == 'phone':
        y = bp(y, 320, 3300, 4)
        y = np.tanh(y / (np.max(np.abs(y)) + 1e-9) * 1.6)
    y = y / (np.max(np.abs(y)) + 1e-9)
    return y, env_marks


def room(y, amount=0.25, decay=0.35, seed=4):
    r = np.random.default_rng(seed)
    n = int(1.2 * SR)
    ir = r.standard_normal(n) * np.exp(-np.arange(n) / SR / decay)
    ir = lp(ir, 3500)
    ir /= np.sqrt(np.sum(ir ** 2))
    from scipy.signal import fftconvolve
    w = fftconvolve(y, ir)
    d = np.concatenate([y, np.zeros(len(w) - len(y))])
    return d * (1 - amount) + w * amount


BASEMENT = [(65.0, 107.0), (109.0, 115.0)]
LEVEL = {'normal': -8.0, 'whisper': -11.0, 'shout': -7.5, 'phone': -10.5}


def main():
    os.makedirs(BUILD, exist_ok=True)
    track = np.zeros(N)
    env = {s: np.zeros(NFRAMES, bool) for s in DIALOGUE_SPEAKERS}
    timings = []
    for i, ln in enumerate(VOICE_LINES):
        start, spk, style, text = ln[:4]
        until = ln[4] if len(ln) > 4 else None
        nxt = VOICE_LINES[i + 1][0] if i + 1 < len(VOICE_LINES) else DURATION
        limit = (until or nxt - 0.08) - start
        if spk == 'narr':
            # narration is told through the captions (reading time ~2.8 words/s)
            n = len(clean(text).split())
            timings.append(dict(start=start, end=min(start + limit, start + 0.4 + n / 2.8), speaker=spk, style=style,
                                text=text, until=until))
            continue
        y, marks = synth_line(text, spk, style, seed=i)
        dur = len(y) / SR
        if dur > limit:  # speak faster to fit the slot
            k = limit / dur
            idx = np.arange(int(len(y) * k)) / k
            y = np.interp(idx, np.arange(len(y)), y)
            marks = [(a * k, b * k) for a, b in marks]
            dur = len(y) / SR
        in_base = any(a <= start < b for a, b in BASEMENT)
        if style != 'phone':
            y = room(y, 0.28 if in_base else 0.1, 0.45 if in_base else 0.2, seed=i)
        y = y / (np.max(np.abs(y)) + 1e-9) * 10 ** ((LEVEL[style] + VOICES[spk]['gain']) / 20)
        s = int(start * SR)
        n = min(len(y), N - s)
        track[s:s + n] += y[:n]
        for a, b in marks:  # mouth open while a vowel sounds
            f0, f1 = int((start + a) * FPS), int(math.ceil((start + b) * FPS))
            env[spk][max(0, f0):min(NFRAMES, f1)] = True
        timings.append(dict(start=start, end=round(start + dur, 3), speaker=spk, style=style, text=text, until=until))
        print(f'{start:7.2f}-{start + dur:7.2f}  {spk:5s} {style:7s} {clean(text)}')
    # mouths close briefly between syllables that run together (flap rather than hold)
    for s in env:
        e = env[s]
        for f in range(1, NFRAMES - 1):
            if e[f - 1] and e[f] and e[f + 1] and f % 4 == 0:
                e[f] = False
    st = np.stack([track, track], axis=1)
    wavfile.write(os.path.join(BUILD, 'voice.wav'), SR, (np.clip(st, -1, 1) * 32767).astype(np.int16))
    with open(os.path.join(BUILD, 'voice_lines.json'), 'w') as f:
        json.dump(timings, f, indent=1, ensure_ascii=False)
    with open(os.path.join(BUILD, 'voice_env.json'), 'w') as f:
        json.dump({s: np.flatnonzero(e).tolist() for s, e in env.items()}, f)
    print('voice ->', os.path.join(BUILD, 'voice.wav'))


if __name__ == '__main__':
    main()
