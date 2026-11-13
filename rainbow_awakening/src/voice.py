"""Voice-over: Kokoro TTS -> boy voice -> Whisper check -> timeline + captions.

usage: python src/voice.py --models <dir> --out build

<dir> must contain kokoro-q8.onnx, voices.bin (npz of Kokoro style vectors) and
whisper-small/ (CTranslate2). See tools/fetch_models.sh.

Writes:
  build/vo.wav          48 kHz mono voice track, exactly 90 s
  build/vo_lines/*.wav  each processed line
  build/timing.json     line + caption chunk + word timings (read by the renderer and audio.py)
  captions.srt          one subtitle per caption chunk
"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import resample_poly

sys.path.insert(0, os.path.dirname(__file__))
from script import DURATION, EMOTIONS, LINES, chunks, plain, scene_window  # noqa: E402

SR = 48000
TIMBRE = {'am_liam': 1.0}        # decoder half of the style vector: fixed for every line
BOY_SHIFT = 1.12                  # pitch + formant shift that turns the voice into a ~10 year old
GAP = 0.30                        # min silence between two lines
END_MARGIN = 0.12                 # a line must end this long before its scene window ends
NUMBERS = {'2': 'two'}


def norm_words(s):
    s = s.lower().replace('’', "'")
    out = []
    for w in re.findall(r"[a-z0-9']+", s):
        w = NUMBERS.get(w, w).replace("'", '')
        out.append(w)
    return out


class Voice:
    def __init__(self, models):
        from kokoro_onnx import Kokoro
        self.k = Kokoro(os.path.join(models, 'kokoro-q8.onnx'), os.path.join(models, 'voices.bin'))

    def style(self, pred):
        V = self.k.get_voice_style
        dec = sum(w * V(n) for n, w in TIMBRE.items())
        pr = sum(w * V(n) for n, w in pred.items())
        return np.concatenate([dec[..., :128], pr[..., 128:]], -1).astype(np.float32)

    def synth(self, text, emo, speed_mul=1.0):
        e = EMOTIONS[emo]
        x, sr = self.k.create(text, voice=self.style(e['pred']), speed=e['speed'] * speed_mul, lang='en-us')
        return np.asarray(x, np.float64), sr


def ffmpeg_af(x, sr, af, out_sr=SR):
    with tempfile.TemporaryDirectory() as d:
        a, b = os.path.join(d, 'a.wav'), os.path.join(d, 'b.wav')
        sf.write(a, x.astype(np.float32), sr, subtype='FLOAT')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', a, '-af', af, '-ar', str(out_sr), '-ac', '1',
                        '-c:a', 'pcm_f32le', b], check=True)
        y, _ = sf.read(b)
    return y


def boy_chain(emo):
    """ffmpeg filter chain: boy pitch/formant shift + emotion FX."""
    e = EMOTIONS[emo]
    f = [f'rubberband=pitch={BOY_SHIFT}:formant=shifted:pitchq=quality:transients=smooth']
    if abs(e['pitch'] - 1) > 1e-3:
        f.append(f"rubberband=pitch={e['pitch']}:formant=preserved:pitchq=quality:transients=smooth")
    f.append('highpass=f=90')
    fx = e['fx']
    if fx in ('bright', 'hype'):
        f.append('equalizer=f=3200:t=q:w=1.0:g=2.5')
        f.append('equalizer=f=250:t=q:w=1.0:g=-1.5')
    if fx == 'hype':
        f.append('acompressor=threshold=0.12:ratio=4:attack=4:release=80:makeup=1.6')
    if fx == 'nervous':
        f.append('equalizer=f=3000:t=q:w=1.0:g=1.5')   # + numpy vibrato in make_line (shaky voice)
    if fx == 'sad':
        f.append('lowpass=f=7500')
        f.append('equalizer=f=3000:t=q:w=1.0:g=-1.0')
    f.append('acompressor=threshold=0.18:ratio=2.5:attack=6:release=120:makeup=1.2')
    return ','.join(f)


def vibrato(x, sr, rate, depth_ms):
    """Slight pitch wobble via a modulated delay line."""
    n = np.arange(len(x))
    d = (depth_ms / 1000 * sr) * (1 + np.sin(2 * np.pi * rate * n / sr))
    return np.interp(n - d, n, x, left=0.0)


def trim(x, sr, db=-42, pre=0.03, post=0.09):
    thr = np.abs(x).max() * 10 ** (db / 20)
    idx = np.where(np.abs(x) > thr)[0]
    a = max(0, idx[0] - int(pre * sr))
    b = min(len(x), idx[-1] + int(post * sr))
    y = x[a:b].copy()
    fade = int(0.008 * sr)
    y[:fade] *= np.linspace(0, 1, fade)
    y[-fade:] *= np.linspace(1, 0, fade)
    return y


class Checker:
    """Whisper-small: verifies each line is intelligible and gives word timestamps."""

    def __init__(self, models):
        from faster_whisper import WhisperModel
        self.m = WhisperModel(os.path.join(models, 'whisper-small'), device='cpu', compute_type='int8')

    def words(self, x, sr, context=None):
        """Word list for x. `context` (previous line's audio) is played first, like a viewer hears it;
        only words inside x are returned, with times relative to x."""
        y = resample_poly(x, 16000, sr).astype(np.float32)
        lead = 0.5
        parts = [np.zeros(8000, np.float32)]
        if context is not None:
            parts += [resample_poly(context, 16000, sr).astype(np.float32), np.zeros(9600, np.float32)]
            lead += len(context) / sr + 0.6
        y = np.concatenate(parts + [y, np.zeros(8000, np.float32)])
        segs, _ = self.m.transcribe(y, language='en', word_timestamps=True, beam_size=5,
                                    condition_on_previous_text=False)
        out = []
        for s in segs:
            for w in s.words:
                if w.end < lead + 0.05:
                    continue
                for nw in norm_words(w.word):
                    out.append(dict(w=nw, t0=max(0.0, w.start - lead), t1=max(0.0, w.end - lead), p=w.probability))
        return out


def align(ref, hyp):
    """Map each reference word index to a hypothesis word (or None)."""
    sm = difflib.SequenceMatcher(a=ref, b=[h['w'] for h in hyp], autojunk=False)
    m = [None] * len(ref)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            m[blk.a + k] = hyp[blk.b + k]
    return m


def make_line(voice, checker, lid, emo, caption, tts_text, speed_mul, context=None):
    text = tts_text or plain(caption)
    x, sr = voice.synth(text, emo, speed_mul)
    y = ffmpeg_af(x, sr, boy_chain(emo))
    if not np.all(np.isfinite(y)):
        raise RuntimeError(f'{lid}: non-finite samples after the voice chain')
    if EMOTIONS[emo]['fx'] == 'nervous':
        y = vibrato(y, SR, rate=6.5, depth_ms=0.35)
    y = trim(y, SR)
    # loudness: -19 LUFS per line (+ emotion offset), mix stage does the final level
    meter = pyln.Meter(SR, block_size=0.2)
    lufs = meter.integrated_loudness(np.concatenate([y, np.zeros(int(0.3 * SR))]))
    y = y * 10 ** ((-19 + EMOTIONS[emo]['gain'] - lufs) / 20)
    # check the line the way a viewer hears it (after the previous line) and on its own;
    # it passes if either transcription contains every word
    hyps = [checker.words(y, SR, context)] if context is not None else []
    hyps.append(checker.words(y, SR))
    ref = norm_words(plain(caption))
    def score(h):
        m = align(ref, h)
        matched = sum(1 for x in m if x)
        return (matched / len(ref), -(len(h) - matched), np.mean([w['p'] for w in h]) if h else 0)
    hyp = max(hyps, key=score)
    return y, hyp


def word_times(caption, hyp, dur):
    """Times for every caption word (relative to line start) using Whisper alignment."""
    ref_tokens = []      # (chunk idx, word idx, normalized token)
    for ci, ch in enumerate(chunks(caption)):
        for wi, (w, col, tail) in enumerate(ch):
            for t in norm_words(w + tail):
                ref_tokens.append((ci, wi, t))
    ref = [t for _, _, t in ref_tokens]
    m = align(ref, hyp)
    n = len(ref)
    # interpolate unmatched tokens
    t0 = [h['t0'] if h else None for h in m]
    known = [i for i in range(n) if t0[i] is not None]
    for i in range(n):
        if t0[i] is None:
            prev = max([k for k in known if k < i], default=None)
            nxt = min([k for k in known if k > i], default=None)
            a = t0[prev] if prev is not None else 0.0
            b = t0[nxt] if nxt is not None else dur
            ia = prev if prev is not None else -1
            ib = nxt if nxt is not None else n
            t0[i] = a + (b - a) * (i - ia) / (ib - ia)
    matched = sum(1 for h in m if h) / n
    res = {}
    for (ci, wi, _), t in zip(ref_tokens, t0):
        res.setdefault((ci, wi), t)
    return res, matched, ref, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', required=True)
    ap.add_argument('--out', default='build')
    ap.add_argument('--srt', default='captions.srt')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'vo_lines'), exist_ok=True)
    voice, checker = Voice(a.models), Checker(a.models)

    track = np.zeros(int(round(DURATION * SR)))
    timing = []
    prev_end = 0.0
    prev_audio = None
    problems = []
    for idx, (lid, scene, at, emo, caption, tts_text) in enumerate(LINES):
        w0, w1 = scene_window(scene)
        limit_end = min(w1, DURATION) - END_MARGIN
        # lines later in the same window need room too: reserve their natural length
        speed_mul = 1.0
        for attempt in range(8):
            y, hyp = make_line(voice, checker, lid, emo, caption, tts_text, speed_mul, prev_audio)
            dur = len(y) / SR
            start = max(at, prev_end + GAP)
            rest = 0.0
            for lid2, scene2, at2, emo2, cap2, tts2 in LINES[idx + 1:]:
                if scene2 != scene:
                    break
                rest += GAP + 0.32 * len(plain(cap2).split()) / EMOTIONS[emo2]['speed']
            if start + dur + rest <= limit_end or speed_mul >= 1.32:
                break
            speed_mul *= 1.06
        end = start + dur
        if end > limit_end:
            problems.append(f'{lid} ends at {end:.2f} > {limit_end:.2f}')
        wt, matched, ref, m = word_times(caption, hyp, dur)
        heard = ' '.join(h['w'] for h in hyp)
        ok = matched >= 0.999 and len(hyp) == len(ref)
        if not ok:
            problems.append(f'{lid} ASR mismatch: heard "{heard}" vs "{" ".join(ref)}"')
        sf.write(os.path.join(a.out, 'vo_lines', f'{lid}.wav'), y.astype(np.float32), SR)
        i0 = int(round(start * SR))
        track[i0:i0 + len(y)] += y
        prev_end = end
        prev_audio = y
        chs = []
        for ci, ch in enumerate(chunks(caption)):
            chs.append({'words': [{'w': w + tail, 'color': col, 't': round(start + wt[(ci, wi)], 3)}
                                  for wi, (w, col, tail) in enumerate(ch)],
                        'start': round(start + wt[(ci, 0)] - 0.06, 3)})
        timing.append({'id': lid, 'scene': scene, 'emotion': emo, 'text': plain(caption),
                       'start': round(start, 3), 'end': round(end, 3), 'speed': round(speed_mul, 3),
                       'asr': heard, 'asr_match': round(matched, 3),
                       'asr_prob': round(float(np.mean([h['p'] for h in hyp])) if hyp else 0, 3),
                       'chunks': chs})
        print(f'{lid} {scene:8s} {emo:8s} {start:6.2f}-{end:6.2f} (win end {w1:5.1f}) speed x{speed_mul:.2f} '
              f'asr={"OK " if ok else "BAD"} p={timing[-1]["asr_prob"]:.2f} | {heard}', flush=True)

    # caption chunk end times: until the next chunk, or hold a bit after the line ends
    flat = [(L, c) for L in timing for c in L['chunks']]
    for k, (L, c) in enumerate(flat):
        nxt = flat[k + 1][1]['start'] if k + 1 < len(flat) else DURATION
        if c is L['chunks'][-1]:
            c['end'] = round(min(nxt - 0.02, L['end'] + 0.75, DURATION), 3)
        else:
            c['end'] = round(nxt - 0.02, 3)
        if c['end'] - c['start'] < 0.5:
            problems.append(f"{L['id']} chunk too short: {c['end'] - c['start']:.2f}s")

    # overlap check
    for L1, L2 in zip(timing, timing[1:]):
        if L2['start'] < L1['end'] + 0.05:
            problems.append(f"overlap {L1['id']} / {L2['id']}")

    peak = np.abs(track).max()
    sf.write(os.path.join(a.out, 'vo.wav'), track.astype(np.float32), SR, subtype='FLOAT')
    with open(os.path.join(a.out, 'timing.json'), 'w') as f:
        json.dump({'fps': 30, 'duration': DURATION, 'lines': timing}, f, indent=1)

    def ts(t):
        ms = int(round(t * 1000))
        return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}'
    with open(a.srt, 'w') as f:
        for k, (L, c) in enumerate(flat, 1):
            txt = ' '.join(w['w'] for w in c['words'])
            f.write(f"{k}\n{ts(max(0, c['start']))} --> {ts(c['end'])}\n{txt}\n\n")
    print(f'voice peak {peak:.3f}; {len(timing)} lines, {len(flat)} caption chunks')
    if problems:
        print('PROBLEMS:\n  ' + '\n  '.join(problems))
        sys.exit(1)
    print('all lines verified: no overlaps, every line inside its window, ASR matches text')


if __name__ == '__main__':
    main()
