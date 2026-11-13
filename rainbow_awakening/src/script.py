"""Script for "Rainbow Awakening": scene windows, voice lines, emotions and caption chunks.

Every voice line is also an on-screen caption. Lines longer than 7 words are split
into caption chunks with ' | '. Rarity words are tagged {purple:Purple} etc. so the
renderer can color them. `at` is the earliest start time of the line (seconds);
voice.py may push it later (never earlier) to avoid overlaps, and speeds the line up
if it would not finish inside its scene window.
"""

FPS = 30
DURATION = 90.0
N_FRAMES = int(DURATION * FPS)  # 2700

# (scene id, start, end, description)
SCENES = [
    ('hook',     0.0,  5.0, 'Close-up of Max, rainbow light flickering behind him'),
    ('town',     5.0, 12.0, 'Wide shot of the blocky town, kids with auras flying and running'),
    ('purple',  12.0, 20.0, 'Purple-aura kid lifts small blocks with telekinesis'),
    ('yellow',  20.0, 28.0, 'Yellow-aura kid dashes at super speed, leaving a trail'),
    ('gold',    28.0, 36.0, 'Gold-aura kid shoots golden energy blasts, sparkles everywhere'),
    ('black',   36.0, 46.0, 'Dark sky, black-aura kid with smoky shadows, crowd steps back and gasps'),
    ('walk',    46.0, 54.0, 'Max walks up to the big glowing crystal in the town square'),
    ('touch',   54.0, 62.0, 'Max touches the crystal, it flickers and goes dark, kids laugh'),
    ('sunset',  62.0, 70.0, 'Max sits alone at sunset, head down'),
    ('quake',   70.0, 78.0, 'Ground shakes, crystal cracks, colored light leaks toward Max'),
    ('rainbow', 78.0, 86.0, 'Huge spinning rainbow aura explodes around Max, crowd shocked'),
    ('end',     86.0, 90.0, 'Max floats up smiling, rainbow trail, end card'),
]

# Voice emotions -> TTS settings (timbre is fixed: see voice.py).
#   pred:  prosody-style blend (controls intonation / energy)
#   speed: Kokoro speed, pitch: extra pitch factor (formants preserved), gain dB, fx
EMOTIONS = {
    'hook':     dict(pred={'af_jessica': 0.6, 'af_heart': 0.4}, speed=1.00, pitch=1.03, gain=0.0, fx='bright'),
    'excited':  dict(pred={'af_jessica': 0.6, 'af_heart': 0.4}, speed=1.06, pitch=1.02, gain=0.0, fx='bright'),
    'proud':    dict(pred={'af_jessica': 0.5, 'af_bella': 0.5}, speed=1.04, pitch=1.03, gain=0.5, fx='bright'),
    'mystery':  dict(pred={'af_heart': 0.7, 'af_sky': 0.3}, speed=0.96, pitch=0.98, gain=-0.5, fx=None),
    'nervous':  dict(pred={'af_heart': 0.6, 'af_sky': 0.4}, speed=0.92, pitch=1.00, gain=-1.0, fx='nervous'),
    'sad':      dict(pred={'af_heart': 0.5, 'af_nicole': 0.5}, speed=0.86, pitch=0.96, gain=-1.5, fx='sad'),
    'shocked':  dict(pred={'af_jessica': 0.7, 'af_bella': 0.3}, speed=1.08, pitch=1.05, gain=0.5, fx='bright'),
    'hyped':    dict(pred={'af_bella': 0.6, 'af_jessica': 0.4}, speed=1.06, pitch=1.07, gain=1.5, fx='hype'),
    'reveal':   dict(pred={'af_bella': 0.5, 'af_heart': 0.5}, speed=0.90, pitch=1.04, gain=2.0, fx='bright'),
    'warm':     dict(pred={'af_heart': 0.6, 'af_jessica': 0.4}, speed=1.02, pitch=1.02, gain=0.0, fx='bright'),
}

# (line id, scene, earliest start, emotion, caption text, tts text or None)
LINES = [
    ('L01', 'hook',     0.30, 'hook',    'What if your power | was decided by a {rainbow:color}?', None),
    ('L02', 'town',     5.30, 'excited', 'In my world, everyone gets a superpower.', None),
    ('L03', 'town',     8.30, 'excited', 'And the color tells you | how strong it is.', None),
    ('L04', 'purple',  12.60, 'excited', '{purple:Purple} is decent.', None),
    ('L05', 'purple',  14.70, 'excited', 'You can move small stuff... | that\'s about it.', None),
    ('L06', 'yellow',  20.50, 'excited', '{yellow:Yellow} is pretty good.', None),
    ('L07', 'yellow',  22.60, 'excited', 'Super speed. | Nobody beats them in tag.', None),
    ('L08', 'gold',    28.50, 'proud',   '{gold:Gold} is good.', None),
    ('L09', 'gold',    30.70, 'proud',   '{gold:Gold} kids are the town heroes.', None),
    ('L10', 'black',   36.80, 'mystery', '{black:Black} is rare.', None),
    ('L11', 'black',   39.00, 'mystery', 'Only a few people | have ever seen it.', None),
    ('L12', 'black',   42.30, 'mystery', 'Everyone\'s a little scared of them.', None),
    ('L13', 'walk',    46.50, 'nervous', 'Today was my Awakening Day.', None),
    ('L14', 'walk',    49.70, 'nervous', 'I was so nervous.', 'I was... so nervous.'),
    ('L15', 'touch',   54.40, 'sad',     'I touched the crystal... | and nothing happened.', None),
    ('L16', 'touch',   58.90, 'sad',     'Everyone laughed at me.', 'Everyone... laughed at me.'),
    ('L17', 'sunset',  63.20, 'sad',     'I thought I had | no power at all.', None),
    ('L18', 'quake',   70.60, 'shocked', 'Then the ground started shaking...', None),
    ('L19', 'quake',   74.20, 'shocked', 'Wait... what\'s happening?!', None),
    ('L20', 'rainbow', 78.55, 'reveal',  '{rainbow:RAINBOW}?!', 'Rainbow?!'),
    ('L21', 'rainbow', 80.70, 'hyped',   'The rarest power | in the whole world!', None),
    ('L22', 'end',     86.15, 'warm',    'And this is just | the beginning...', None),
    ('L23', 'end',     88.15, 'excited', 'Follow for part 2!', 'Follow for part two!'),
]


def scene_window(scene_id):
    for s, a, b, _ in SCENES:
        if s == scene_id:
            return a, b
    raise KeyError(scene_id)


def plain(caption):
    """Caption text without markup or chunk separators."""
    import re
    s = caption.replace(' | ', ' ')
    return re.sub(r'\{(\w+):([^}]*)\}', r'\2', s)


def chunks(caption):
    """List of caption chunks, each a list of (word, color or None)."""
    import re
    out = []
    for part in caption.split(' | '):
        words = []
        for tok in part.split(' '):
            m = re.match(r'^\{(\w+):([^}]*)\}(.*)$', tok)
            if m:
                words.append((m.group(2), m.group(1), m.group(3)))  # (word, color, trailing punctuation)
            else:
                words.append((tok, None, ''))
        out.append(words)
    return out
