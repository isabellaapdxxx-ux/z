"""Audio QA: per-line voice vs background loudness, clipping, limiter activity, total length."""
import json, sys
import numpy as np, soundfile as sf, pyloudnorm as pyln
from scipy import signal
b = sys.argv[1] if len(sys.argv) > 1 else 'build'
vo, sr = sf.read(f'{b}/vo.wav'); mix, _ = sf.read(f'{b}/mix.wav')
vo2 = np.stack([vo, vo], 1)
g = float((mix * vo2).sum() / (vo2 * vo2).sum())          # voice gain inside the mix (background is uncorrelated)
bg = mix - g * vo2
m = pyln.Meter(sr, block_size=0.2)
tim = json.load(open(f'{b}/timing.json'))
worst = 99
for L in tim['lines']:
    a, z = int(L['start'] * sr), int(L['end'] * sr)
    lv, lb = m.integrated_loudness(g * vo2[a:z]), m.integrated_loudness(bg[a:z])
    worst = min(worst, lv - lb)
    print(f"{L['id']} {L['start']:6.2f}-{L['end']:6.2f}  voice {lv:6.1f} LUFS  background {lb:6.1f} LUFS  -> voice on top by {lv - lb:5.1f} dB")
over = signal.resample_poly(mix, 4, 1, axis=0)
print(f'samples {len(mix)} ({len(mix) / sr:.6f} s), integrated {pyln.Meter(sr).integrated_loudness(mix):.2f} LUFS, '
      f'sample peak {20 * np.log10(np.abs(mix).max()):.2f} dBFS, true peak {20 * np.log10(np.abs(over).max()):.2f} dBTP, '
      f'clipped samples {(np.abs(mix) >= 0.999).sum()}, min voice margin {worst:.1f} dB')
