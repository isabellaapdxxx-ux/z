"""Join the TTS clips into the voiceover, fit it to the 60 s video, get word timings
with faster-whisper and build the timeline (scenes, captions, visual/sound events).

Writes build/vo.wav (48 kHz mono) and build/timeline.json.
Run inside the Chatterbox venv:  python assemble.py
"""
import difflib, json, os, subprocess, sys
import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(__file__))
from script import SENTENCES, tokens
from textnorm import spoken_words

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "..", "build")
SR = 48000
DURATION = 60.0
LEAD = 0.12            # voice starts right away: the hook must land in the first second
VO_END_TARGET = 59.2   # leaves ~0.8 s of outro after "Follow for more"
PAUSE_FLOOR = 0.16     # pauses are compressed toward this, so short beats never vanish
MAX_TEMPO = 0.05       # at most 5 % speed change


def load_clip(i, tempo):
    src = os.path.join(BUILD, "clips", f"{i:02d}.wav")
    cmd = ["ffmpeg", "-v", "error", "-i", src, "-af", f"atempo={tempo:.5f},aresample={SR}",
           "-ac", "1", "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)


def scale_pause(p, k):
    if p <= 0:
        return 0.0
    if k >= 1:
        return min(p * k, 1.1)
    return PAUSE_FLOOR + max(p - PAUSE_FLOOR, 0) * k


def fit_timing():
    """Choose pause scale and tempo so the voiceover ends at VO_END_TARGET."""
    durs = [sf.info(os.path.join(BUILD, "clips", f"{i:02d}.wav")).duration for i in range(len(SENTENCES))]
    pauses = np.array([p for _, p, _ in SENTENCES])
    speech = sum(durs)
    avail = VO_END_TARGET - LEAD

    def total(k, tempo):
        return speech / tempo + sum(scale_pause(p, k) for p in pauses)

    tempo, k = 1.0, 1.0
    if total(1, 1) < avail:   # too short: longer pauses first, then up to 5 % slower, then more pause
        for k in np.arange(1.0, 1.401, 0.01):
            if total(k, 1) >= avail:
                break
        if total(k, 1) < avail:
            for tempo in np.arange(1.0, 1 - MAX_TEMPO - 1e-9, -0.0025):
                if total(k, tempo) >= avail:
                    break
            for k in np.arange(k, 2.001, 0.01):
                if total(k, tempo) >= avail:
                    break
    else:                     # too long: up to 5 % faster first (keeps pauses natural), then shorter pauses
        for tempo in np.arange(1.0, 1 + MAX_TEMPO + 1e-9, 0.0025):
            if total(1, tempo) <= avail:
                break
        for k in np.arange(1.0, -0.001, -0.01):
            if total(k, tempo) <= avail:
                break
    print(f"speech {speech:.2f}s  pauses {pauses.sum():.2f}s -> pause x{k:.2f}, tempo {tempo:.4f}, "
          f"VO {LEAD + total(k, tempo):.2f}s")
    return float(k), float(tempo)


def build_vo(k, tempo):
    vo = np.zeros(int(DURATION * SR), np.float32)
    t = LEAD
    sents = []
    for i, (scene, pause, s) in enumerate(SENTENCES):
        clip = load_clip(i, tempo)
        a = int(round(t * SR))
        vo[a:a + len(clip)] += clip[: len(vo) - a]
        sents.append(dict(i=i, scene=scene, start=t, end=t + len(clip) / SR))
        t += len(clip) / SR + scale_pause(pause, k)
    sf.write(os.path.join(BUILD, "vo.wav"), vo, SR)
    return sents


def transcribe():
    from faster_whisper import WhisperModel
    try:
        model = WhisperModel("medium.en", device="cpu", compute_type="int8")
    except Exception as e:  # pragma: no cover
        print("medium.en unavailable, using small.en:", e)
        model = WhisperModel("small.en", device="cpu", compute_type="int8")
    prompt = " ".join(" ".join(d for d, _ in tokens(s)) for _, _, s in SENTENCES)
    segs, _ = model.transcribe(os.path.join(BUILD, "vo.wav"), language="en", word_timestamps=True,
                               beam_size=5, initial_prompt=prompt[:600], vad_filter=False)
    words = [dict(w=w.word.strip(), s=w.start, e=w.end) for sg in segs for w in sg.words]
    json.dump(words, open(os.path.join(BUILD, "whisper_words.json"), "w"), indent=0)
    return words


def align(sents, heard):
    """Give every script caption token a start/end time from the Whisper words.

    Both sides are normalized to spoken words (numbers expanded), matched with a
    sequence diff, and tokens Whisper missed or misheard are interpolated.
    """
    toks = []
    for si, (_, _, s) in enumerate(SENTENCES):
        for disp, sp in tokens(s):
            toks.append(dict(sent=si, text=disp, sw=spoken_words(sp)))
    ref, ref_tok = [], []
    for ti, tk in enumerate(toks):
        for w in tk["sw"]:
            ref.append(w); ref_tok.append(ti)
    hyp, hyp_t = [], []
    for w in heard:
        sw = spoken_words(w["w"]) or ["_"]
        step = (w["e"] - w["s"]) / len(sw)
        for j, x in enumerate(sw):
            hyp.append(x); hyp_t.append((w["s"] + j * step, w["s"] + (j + 1) * step))
    sm = difflib.SequenceMatcher(a=ref, b=hyp, autojunk=False)
    times = [[] for _ in toks]
    for blk in sm.get_matching_blocks():
        for j in range(blk.size):
            times[ref_tok[blk.a + j]].append(hyp_t[blk.b + j])
    matched = sum(1 for t in times if t)
    for ti, tk in enumerate(toks):
        sent = sents[tk["sent"]]
        if times[ti]:
            s0, e0 = min(t[0] for t in times[ti]), max(t[1] for t in times[ti])
            if s0 < sent["start"] - 0.35 or e0 > sent["end"] + 0.35:
                times[ti] = []          # matched into the wrong sentence: interpolate instead
            else:
                tk["start"], tk["end"] = max(s0, sent["start"] - 0.05), min(e0, sent["end"] + 0.05)
    # interpolate missing tokens within each sentence, weighted by length
    for si, sent in enumerate(sents):
        idx = [i for i, t in enumerate(toks) if t["sent"] == si]
        i = 0
        while i < len(idx):
            if "start" in toks[idx[i]]:
                i += 1; continue
            j = i
            while j < len(idx) and "start" not in toks[idx[j]]:
                j += 1
            a = toks[idx[i - 1]]["end"] if i > 0 else sent["start"]
            b = toks[idx[j]]["start"] if j < len(idx) else sent["end"]
            run = idx[i:j]
            wts = np.array([len(toks[r]["text"]) + 2 for r in run], float)
            edges = a + (b - a) * np.concatenate([[0], np.cumsum(wts) / wts.sum()])
            for r, x0, x1 in zip(run, edges[:-1], edges[1:]):
                toks[r]["start"], toks[r]["end"] = float(x0), float(x1)
            i = j
    # monotonic clean-up
    for a, b in zip(toks, toks[1:]):
        if b["start"] < a["start"] + 0.04:
            b["start"] = a["start"] + 0.04
        b["end"] = max(b["end"], b["start"] + 0.06)
        a["end"] = min(a["end"], max(b["start"], a["start"] + 0.06))
    print(f"aligned {matched}/{len(toks)} tokens directly, {len(toks) - matched} interpolated")
    return [dict(sent=t["sent"], text=t["text"], start=round(t["start"], 3), end=round(t["end"], 3))
            for t in toks]


def word_time(words, sent, text, which="start"):
    for w in words:
        if w["sent"] == sent and w["text"].strip(".,?!:").lower() == text.lower():
            return w[which]
    raise KeyError((sent, text))


def build_events(sents, words):
    W = lambda s, t, which="start": word_time(words, s, t, which)
    ev = {
        # scene 1: hook
        "n2": W(0, "2"), "n100": W(0, "100"), "iq130": W(0, "130"),
        # scene 2: bell curve
        "curve": sents[1]["start"], "avg": W(2, "100"), "shade68": W(2, "68%"),
        "l85": W(2, "85"), "l115": W(2, "115"),
        # scene 3: right tail
        "zoom": sents[3]["start"] - 0.25, "t130": W(3, "130"), "gifted": W(4, "gifted"),
        "p2": W(5, "2%"), "t145": W(6, "145"), "r1000": W(7, "1,000"),
        "t160": W(8, "160"), "r30000": W(9, "30,000"),
        # scene 4: stadium
        "fill": W(10, "Fill"), "gold": W(10, "1"),
        # scene 5: DNA
        "herit": W(12, "50"), "herit80": W(12, "80%"), "gene": W(13, "genius"), "gene_x": W(13, "gene"),
        "thousands": W(14, "thousands"),
        # scene 6: environment icons
        "env": W(15, "environment"), "food": W(16, "Nutrition"), "sleep": W(16, "sleep"),
        "books": W(16, "education"), "bulb": W(16, "curiosity"), "grow": W(16, "grows"),
        # scene 7: scale
        "nature": W(17, "nature"), "nurture": W(17, "nurture"), "together": W(17, "together"),
        "ring": W(18, "IQ"), "some": W(18, "some"), "notall": W(18, "all"),
        # scene 8
        "follow": W(19, "Follow"),
    }
    return {k: round(float(v), 3) for k, v in ev.items()}


def main():
    k, tempo = fit_timing()
    sents = build_vo(k, tempo)
    heard = transcribe()
    words = align(sents, heard)
    events = build_events(sents, words)
    scenes = []
    for sc in range(1, 9):
        first = min(s["start"] for s in sents if s["scene"] == sc)
        scenes.append(dict(scene=sc, start=0.0 if sc == 1 else round(first - 0.22, 3)))
    # scene 3 continues scene 2's curve: its "transition" is the camera zoom itself
    tl = dict(duration=DURATION, fps=30, tempo=tempo, pause_scale=k,
              sentences=[{**s, "start": round(s["start"], 3), "end": round(s["end"], 3)} for s in sents],
              words=words, scenes=scenes, events=events)
    json.dump(tl, open(os.path.join(BUILD, "timeline.json"), "w"), indent=1)
    print("VO ends at %.2fs" % sents[-1]["end"])
    for s in scenes:
        print("scene", s["scene"], s["start"])


if __name__ == "__main__":
    main()
