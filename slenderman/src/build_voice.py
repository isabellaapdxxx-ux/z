"""Assemble the voice track in ffmpeg: trimmed sentences + silent pauses,
room reverb, low-end boost, two-pass loudnorm to -14 LUFS.
Writes build/voice.wav (48 kHz mono) and build/timeline.json (global word times)."""
import json, os, re, subprocess
import numpy as np
from scipy.io import wavfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
B = os.path.join(ROOT, "build")
SR = 48000
LEAD = 0.12          # voice starts right on the hook boom
LAST_END = 58.25     # final word ends here; black at 59.0, silence to 60.0
HEAD, TAIL = 0.03, 0.14

meta = json.load(open(f"{B}/vo/meta.json"))
for m in meta:
    m["t0"] = max(0.0, m["words"][0]["start"] - HEAD)
    m["t1"] = min(m["dur"], m["words"][-1]["end"] + TAIL)
speech = sum(m["t1"] - m["t0"] for m in meta)
pauses = np.array([m["pause"] for m in meta[:-1]])
scale = (LAST_END - TAIL - LEAD - speech) / pauses.sum()
pauses = pauses * scale
print(f"speech {speech:.2f}s, pause scale {scale:.3f}, pauses {np.round(pauses,2)}")

# global placement (computed here so captions match the ffmpeg concat exactly)
t = LEAD
timeline = []
for i, m in enumerate(meta):
    start = t
    words = []
    for w in m["words"]:
        words.append({"text": w["text"], "start": start + w["start"] - m["t0"],
                      "end": start + w["end"] - m["t0"]})
    hl = {re.sub(r"\W", "", x).lower() for x in re.findall(r"\*([^*]+)\*", m["text"])}
    for w in words:
        w["hl"] = re.sub(r"\W", "", w["text"]).lower() in hl
    timeline.append({"i": i, "text": m["text"].replace("*", ""), "start": start,
                     "end": start + m["t1"] - m["t0"], "tags": m["tags"], "words": words})
    t = timeline[-1]["end"] + (pauses[i] if i < len(pauses) else 0)
json.dump(timeline, open(f"{B}/timeline.json", "w"), indent=1)

# small synthetic room impulse response (no direct path; dry is mixed separately)
rng = np.random.default_rng(7)
n = int(0.9 * SR)
tt = np.arange(n) / SR
ir = rng.standard_normal(n) * np.exp(-tt / 0.16)
ir[: int(0.012 * SR)] = 0  # pre-delay
for d, g in [(0.017, 0.5), (0.023, 0.4), (0.031, 0.3), (0.043, 0.22)]:
    ir[int(d * SR)] += g * 8  # early reflections
ir /= np.abs(ir).max()
wavfile.write(f"{B}/room_ir.wav", SR, (ir * 0.5).astype(np.float32))

# ffmpeg graph: trimmed lines + anullsrc pauses -> concat
inputs, parts, fc = [], [], []
for i, m in enumerate(meta):
    inputs += ["-i", f"{B}/vo/line{i:02d}.wav"]
    fc.append(f"[{i}:a]atrim=start_sample={round(m['t0']*SR)}:end_sample={round(m['t1']*SR)},asetpts=N/SR/TB[l{i}]")
inputs += ["-i", f"{B}/room_ir.wav"]
ir_idx = len(meta)
lead_n = round(LEAD * SR)
fc.append(f"anullsrc=r={SR}:cl=mono,atrim=end_sample={lead_n}[s_lead]")
parts.append("[s_lead]")
for i in range(len(meta)):
    parts.append(f"[l{i}]")
    if i < len(pauses):
        # pause length chosen so concat positions equal the computed timeline
        nxt = round(timeline[i + 1]["start"] * SR) - round(timeline[i]["end"] * SR)
        fc.append(f"anullsrc=r={SR}:cl=mono,atrim=end_sample={nxt}[s{i}]")
        parts.append(f"[s{i}]")
fc.append("".join(parts) + f"concat=n={len(parts)}:v=0:a=1,"
          "highpass=f=70,bass=g=4:f=110:w=0.7,equalizer=f=3200:t=q:w=1.2:g=1.5[dry0]")
fc.append("[dry0]asplit=2[dry][wetin]")
fc.append(f"[wetin][{ir_idx}:a]afir=gtype=none[wet]")
fc.append("[dry][wet]amix=inputs=2:weights='1 0.22':normalize=0,"
          f"apad=whole_len={60*SR},atrim=end_sample={60*SR}[out]")
graph = ";".join(fc)
subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph,
                "-map", "[out]", "-ar", str(SR), "-ac", "1", f"{B}/voice_raw.wav"], check=True)

# two-pass loudnorm to -14 LUFS
r = subprocess.run(["ffmpeg", "-v", "info", "-i", f"{B}/voice_raw.wav", "-af",
                    "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                   capture_output=True, text=True).stderr
st = json.loads(r[r.rindex("{"):r.rindex("}") + 1])
ln = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={st['input_i']}:measured_TP={st['input_tp']}:"
      f"measured_LRA={st['input_lra']}:measured_thresh={st['input_thresh']}:offset={st['target_offset']}:linear=true")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", f"{B}/voice_raw.wav", "-af", ln + f",aresample={SR}",
                "-ar", str(SR), "-c:a", "pcm_f32le", f"{B}/voice.wav"], check=True)
for x in timeline:
    print(f"{x['start']:6.2f}-{x['end']:6.2f}  {x['text']}")
