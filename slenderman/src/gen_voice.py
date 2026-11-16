"""Generate each script line with edge-tts and save word timings."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
from script_data import LINES, VOICE
from tts_util import synth

OUT = os.path.join(os.path.dirname(__file__), "..", "build", "vo")
os.makedirs(OUT, exist_ok=True)
meta = []
for i, (text, pause, tags) in enumerate(LINES):
    clean = text.replace("*", "")
    mp3 = os.path.join(OUT, f"line{i:02d}.mp3")
    wav = os.path.join(OUT, f"line{i:02d}.wav")
    words = synth(clean, VOICE, mp3)
    # decode to 48k mono, trim leading/trailing silence edge-tts adds
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-ac", "1", "-ar", "48000", wav], check=True)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]))
    meta.append({"i": i, "text": text, "pause": pause, "tags": sorted(tags), "dur": dur, "words": words})
    print(i, round(dur, 2), round(words[0]["start"], 2), round(words[-1]["end"], 2), clean)
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1)
