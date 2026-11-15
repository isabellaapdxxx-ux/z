"""Voiceover script.

Each sentence is a list of caption tokens. A token is either a plain word, which is
displayed and spoken as written, or ``"display|spoken words"``, where the caption
shows the digits and the TTS gets words that read naturally. ``SAY`` texts (with
punctuation, which drives the TTS prosody) are built from the spoken forms.
"""
import re

# (scene, pause_after_seconds, tokens)
SENTENCES = [
    (1, 0.50, "What if I told you only 2|two in every 100|one-hundred people have an IQ above 130?|one-hundred-thirty?"),
    (2, 0.30, "IQ is measured on a bell curve."),
    (2, 0.55, "The average is 100,|one-hundred, and about 68%|sixty-eight-percent of people land between 85|eighty-five and 115.|one-hundred-fifteen."),
    (3, 0.28, "Above 130?|one-hundred-thirty?"),
    (3, 0.22, "That's considered gifted."),
    (3, 0.55, "About 2%.|two-percent."),
    (3, 0.28, "Above 145?|one-hundred-forty-five?"),
    (3, 0.60, "Roughly 1|one in 1,000.|a-thousand."),
    (3, 0.30, "And above 160?|one-hundred-sixty?"),
    (3, 0.45, "About 1|one in 30,000.|thirty-thousand."),
    (4, 0.70, "Fill a whole stadium, and maybe 1|one person makes it."),
    (5, 0.40, "So how are they born?"),
    (5, 0.35, "Twin studies suggest IQ is around 50|fifty to 80%|eighty-percent heritable in adults."),
    (5, 0.30, "But there's no single genius gene."),
    (5, 0.60, "It's thousands of tiny genetic differences adding up."),
    (6, 0.30, "And environment matters too."),
    (6, 0.60, "Nutrition, sleep, education and curiosity all shape how a brain grows."),
    (7, 0.55, "So a high IQ is nature and nurture working together."),
    (7, 0.00, "And remember: IQ measures some kinds of intelligence, not all of them."),
]


def tokens(sentence_text):
    """[(display, spoken)] for one sentence."""
    out = []
    for tok in sentence_text.split():
        if "|" in tok:
            disp, spoken = tok.split("|")
            spoken = spoken.replace("-", " ")
        else:
            disp = spoken = tok
        out.append((disp, spoken))
    return out


def say_text(sentence_text):
    """Text sent to the TTS engine."""
    return " ".join(sp for _, sp in tokens(sentence_text))


def norm_words(text):
    """Lowercase words without punctuation, for matching against Whisper output."""
    text = text.lower().replace("%", " percent").replace("-", " ")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return re.findall(r"[a-z0-9']+", text)


if __name__ == "__main__":
    for scene, pause, s in SENTENCES:
        print(scene, pause, "|", " ".join(d for d, _ in tokens(s)), "||", say_text(s))
