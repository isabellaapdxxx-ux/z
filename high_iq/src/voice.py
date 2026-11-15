"""Generate the voiceover sentence by sentence with Chatterbox TTS.

Every clip is checked with faster-whisper against the script and regenerated with a
new seed if words are missing or garbled or the pacing is off. Clips are trimmed and
written to build/clips/NN.wav, with build/clips/clips.json describing them.

Run inside the Chatterbox venv:  python voice.py [--only 3,5] [--tries 4]
"""
import argparse, json, os, sys
import numpy as np
import soundfile as sf
import torch

sys.path.insert(0, os.path.dirname(__file__))
from script import SENTENCES, say_text
from textnorm import match_ratio, spoken_words

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "build")
CLIPS = os.path.join(BUILD, "clips")
REF = os.path.join(BUILD, "ref_christopher.wav")
EXAGGERATION, CFG_WEIGHT, TEMPERATURE = 0.55, 0.40, 0.75


def trim(wav, sr, words):
    """Trim leading/trailing silence and any tail after the last spoken word."""
    hop = int(0.01 * sr)
    n = len(wav) // hop
    rms = np.sqrt(np.mean(wav[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-9))
    voiced = np.where(db > -38)[0]
    a = max(0, voiced[0] * hop - int(0.03 * sr))
    b = min(len(wav), (voiced[-1] + 1) * hop + int(0.10 * sr))
    if words:  # cut breaths/artifacts that trail well after the last word
        last = int((words[-1].end + 0.30) * sr)
        b = min(b, max(last, a + hop))
    out = wav[a:b].copy()
    fi, fo = int(0.008 * sr), int(0.05 * sr)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--tries", type=int, default=4)
    ap.add_argument("--fastest", action="store_true",
                    help="try every seed and keep the quickest clip that is still word-perfect and natural")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x}

    from chatterbox.tts import ChatterboxTTS
    from faster_whisper import WhisperModel
    torch.set_num_threads(os.cpu_count())
    tts = ChatterboxTTS.from_pretrained(device="cpu")
    asr = WhisperModel("small.en", device="cpu", compute_type="int8")
    os.makedirs(CLIPS, exist_ok=True)
    meta_path = os.path.join(CLIPS, "clips.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}

    for i, (scene, pause, s) in enumerate(SENTENCES):
        out = os.path.join(CLIPS, f"{i:02d}.wav")
        if os.path.exists(out) and str(i) in meta and (not only or i not in only):
            continue
        if only and i not in only:
            continue
        text = say_text(s)
        n_words = len(spoken_words(text))
        best = None
        for t in range(args.tries):
            seed = 1000 * i + t + (17 if i in only else 0) + (100 if args.fastest else 0)
            torch.manual_seed(seed)
            np.random.seed(seed)
            wav = tts.generate(text, audio_prompt_path=REF, exaggeration=EXAGGERATION,
                               cfg_weight=CFG_WEIGHT, temperature=TEMPERATURE)
            wav = wav.squeeze(0).numpy().astype(np.float32)
            tmp = os.path.join(CLIPS, "_tmp.wav")
            sf.write(tmp, wav, tts.sr)
            segs, _ = asr.transcribe(tmp, language="en", word_timestamps=True, beam_size=5)
            segs = list(segs)
            words = [w for sg in segs for w in sg.words]
            hyp = " ".join(sg.text for sg in segs).strip()
            ratio = match_ratio(text, hyp)
            clip = trim(wav, tts.sr, words)
            dur = len(clip) / tts.sr
            wps = n_words / dur
            # pacing: a natural narrator lands between ~2.0 and 3.9 spoken words/s
            pace_ok = 2.0 <= wps <= 3.9
            score = ratio - (0 if pace_ok else 0.2)
            if args.fastest:
                score = ratio * 10 + (wps if wps <= 3.5 else -wps)
            print(f"[{i:02d}] try {t} ratio={ratio:.2f} dur={dur:.2f}s wps={wps:.2f} | {hyp}", flush=True)
            if best is None or score > best[0]:
                best = (score, clip, hyp, ratio, seed)
            if ratio >= 0.999 and pace_ok and not args.fastest:
                break
        score, clip, hyp, ratio, seed = best
        old = meta.get(str(i))
        if args.fastest and old and old["ratio"] >= ratio and old["dur"] <= len(clip) / tts.sr:
            print(f"[{i:02d}] keeping the earlier clip ({old['dur']:.2f}s)")
            continue
        sf.write(out, clip, tts.sr)
        meta[str(i)] = dict(text=text, heard=hyp, ratio=ratio, seed=seed, dur=len(clip) / tts.sr)
        json.dump(meta, open(meta_path, "w"), indent=1)
        print(f"[{i:02d}] KEEP ratio={ratio:.2f} dur={len(clip)/tts.sr:.2f}s", flush=True)

    total = sum(m["dur"] for m in meta.values())
    print(f"speech total {total:.2f}s, pauses {sum(p for _, p, _ in SENTENCES):.2f}s")


if __name__ == "__main__":
    main()
