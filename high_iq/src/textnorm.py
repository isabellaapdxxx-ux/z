"""Text normalization shared by the TTS check and the caption aligner."""
import re
from num2words import num2words
from script import norm_words


def spoken_words(text):
    """Normalize text (script or Whisper output) to lowercase spoken words, numbers expanded."""
    out = []
    for w in norm_words(text):
        if w.isdigit():
            out += [x for x in re.findall(r"[a-z]+", num2words(int(w))) if x != "and"]
        else:
            out.append(w)
    return out


def match_ratio(ref, hyp):
    import difflib
    a, b = spoken_words(ref), spoken_words(hyp)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    matched = sum(m.size for m in sm.get_matching_blocks())
    return matched / max(len(a), len(b), 1)
