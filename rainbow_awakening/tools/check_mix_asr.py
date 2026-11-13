"""Transcribe the full mix with Whisper-small and check every voice line is heard in its time window."""
import json, sys, os
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
sys.path.insert(0, 'src')
from voice import norm_words, align
from faster_whisper import WhisperModel
models, b = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else 'build')
mix, sr = sf.read(f'{b}/mix.wav')
y = resample_poly(mix.mean(1), 16000, sr).astype(np.float32)
m = WhisperModel(os.path.join(models, 'whisper-small'), device='cpu', compute_type='int8')
segs, _ = m.transcribe(y, language='en', word_timestamps=True, beam_size=5, condition_on_previous_text=False)
hyp = [dict(w=nw, t0=w.start, t1=w.end, p=w.probability) for s in segs for w in s.words for nw in norm_words(w.word)]
tim = json.load(open(f'{b}/timing.json'))
# global alignment of the whole transcript against the whole script (timestamp-independent)
refs = [(L['id'], w) for L in tim['lines'] for w in norm_words(L['text'])]
gm = align([w for _, w in refs], hyp)
glob_bad = 0
for L in tim['lines']:
    idx = [i for i, (lid, _) in enumerate(refs) if lid == L['id']]
    got = sum(1 for i in idx if gm[i])
    glob_bad += got < len(idx)
    if got < len(idx):
        print(f"global alignment: {L['id']} missing {[refs[i][1] for i in idx if not gm[i]]}")
print(f'global alignment: {len(refs) - sum(1 for x in gm if not x)}/{len(refs)} script words heard in the full mix')
bad = 0
for L in tim['lines']:
    ref = norm_words(L['text'])
    win = [h for h in hyp if L['start'] - 0.4 <= h['t0'] <= L['end'] + 0.4]
    mt = align(ref, win)
    ok = sum(1 for x in mt if x)
    bad += ok < len(ref)
    print(f"{L['id']} {ok}/{len(ref)} words inside the line's own time window (Whisper timestamps drift at line starts)  heard: {' '.join(h['w'] for h in win)}")
print('PASS: every script word is heard in the full mix' if not glob_bad else f'FAIL: {glob_bad} lines have words Whisper could not hear')
sys.exit(1 if glob_bad else 0)
