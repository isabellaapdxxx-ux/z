"""Script, shot list, caption timings and theme melody for "My neighbor is a KILLER".

Run `python config.py` to dump everything to config.json.
Caption markup: *word* = red, ~word~ = red + shaking.
"""
import json
import os

FPS = 30
DURATION = 120.0
W, H = 1080, 1920
NFRAMES = int(round(DURATION * FPS))  # 3600
SR = 48000

# --------------------------------------------------------------------------- shots
# (start, end, shot id, params). Every shot is <= ~3 s and most have camera motion,
# so the picture changes every 1-2 s.
SHOTS = [
    # ---- HOOK (flash-forward) --------------------------------------------------
    (0.0, 1.5, 'hook_basement', {}),
    (1.5, 2.5, 'hook_zoom_face', {}),
    (2.5, 3.5, 'hook_black', {}),
    (3.5, 4.0, 'hook_rewind', {}),
    # ---- SETUP -------------------------------------------------------------------
    (4.0, 5.8, 'street_pan', {}),
    (5.8, 7.5, 'yard_play', {}),
    (7.5, 9.3, 'gray_house_push', {}),
    (9.3, 11.0, 'gray_tilt_up', {}),
    (11.0, 13.0, 'gray_face_close', {'expr': 'blank'}),
    (13.0, 14.8, 'timmy_turns', {}),
    (14.8, 16.5, 'fence_wide', {}),
    (16.5, 18.5, 'gray_eyes', {}),
    (18.5, 20.3, 'timmy_waves', {}),
    (20.3, 22.0, 'gray_watches_leave', {}),
    # ---- DISCOVERY (night) -------------------------------------------------------
    (22.0, 24.0, 'night_street', {}),
    (24.0, 26.0, 'bedroom_window', {}),
    (26.0, 28.0, 'pov_basement_light', {}),
    (28.0, 30.0, 'porch_sneak', {}),
    (30.0, 32.0, 'lawn_creep', {}),
    (32.0, 34.0, 'kneel_window', {}),
    (34.0, 37.0, 'window_drag', {}),
    (37.0, 39.0, 'window_bag_close', {}),
    (39.0, 42.0, 'window_posters', {}),
    (42.0, 44.0, 'window_shovel', {}),
    (44.0, 46.0, 'timmy_face_green', {}),
    (46.0, 48.0, 'window_gray_still', {}),
    # ---- SPOTTED -----------------------------------------------------------------
    (48.0, 51.0, 'window_head_turn', {}),
    (51.0, 52.0, 'window_stare', {}),
    (52.0, 53.0, 'jumpscare_window', {}),
    (53.0, 55.0, 'timmy_falls_back', {}),
    (55.0, 57.0, 'run_lawn', {}),
    (57.0, 59.0, 'look_back_light_off', {}),
    (59.0, 61.0, 'door_slam', {}),
    (61.0, 63.0, 'hall_panting', {}),
    # ---- KIDNAPPED ---------------------------------------------------------------
    (63.0, 65.0, 'hall_shadow_behind', {}),
    (65.0, 65.6, 'grabbed', {}),
    (65.6, 67.0, 'blackout', {}),
    (67.0, 69.0, 'wake_blur', {}),
    (69.0, 72.0, 'tied_matching_hook', {}),
    (72.0, 74.0, 'tied_struggle_close', {}),
    (74.0, 76.0, 'stairs_door_opens', {}),
    (76.0, 78.0, 'stairs_feet', {}),
    (78.0, 80.0, 'timmy_looks_stairs', {}),
    (80.0, 82.0, 'gray_halfway', {}),
    (82.0, 84.0, 'pocket_glow', {}),
    (84.0, 86.0, 'phone_out', {}),
    (86.0, 88.0, 'phone_lap_close', {}),
    (88.0, 90.0, 'stairs_wide_descend', {}),
    # ---- THE CALL ----------------------------------------------------------------
    (90.0, 92.0, 'phone_dial', {}),
    (92.0, 94.0, 'phone_ringing', {}),
    (94.0, 97.0, 'whisper_close', {'line': 0}),
    (97.0, 99.0, 'phone_connected', {}),
    (99.0, 101.0, 'whisper_close', {'line': 1}),
    (101.0, 103.0, 'gray_floor_behind', {}),
    (103.0, 105.0, 'shadow_over_timmy', {}),
    # ---- JUST IN TIME ------------------------------------------------------------
    (105.0, 107.0, 'gray_reaches', {}),
    (107.0, 109.0, 'police_arrive', {}),
    (109.0, 110.5, 'door_burst', {}),
    (110.5, 112.5, 'police_rush', {}),
    (112.5, 115.0, 'arrest', {}),
    # ---- ENDING ------------------------------------------------------------------
    (115.0, 117.5, 'blanket_safe', {}),
    (117.5, 120.0, 'final_flicker', {}),
]

# --------------------------------------------------------------------------- voice script
# (start s, speaker, style, text[, must_end_by s])
# speakers: narr (Timmy telling the story, voice-over), timmy, gray, op (911 operator), cop, cop2
# styles:   normal | whisper | shout | phone
# Caption markup: *word* = red, ~word~ = red + shaking. Dialogue captions get quote marks automatically.
VOICE_LINES = [
    # HOOK
    (0.05, 'narr', 'normal', "My neighbor is a ~KILLER~… and I'm *NEXT.*", 2.45),
    (2.62, 'narr', 'normal', "Here's how it happened…", 3.45),
    # SETUP
    (4.20, 'narr', 'normal', 'Our street was quiet. Nothing ever happened here.'),
    (7.50, 'narr', 'normal', 'Then a new neighbor moved in next door.'),
    (10.90, 'gray', 'normal', "Hello there. I'm *Mr. Gray.*"),
    (13.20, 'timmy', 'normal', 'Uh… hi, Mr. Gray.'),
    (14.90, 'narr', 'normal', 'He watched me. Every single day.'),
    (16.90, 'narr', 'normal', 'And he *never* blinked.'),
    (18.60, 'timmy', 'normal', 'Bye, Mr. Gray!'),
    (20.30, 'gray', 'normal', 'See you *soon,* Timmy.'),
    # DISCOVERY
    (22.20, 'narr', 'normal', "That night, I couldn't sleep."),
    (24.30, 'timmy', 'normal', "Huh? What's that?"),
    (26.00, 'narr', 'normal', 'A light. In his *basement.*'),
    (28.10, 'narr', 'normal', 'So I snuck over…'),
    (30.20, 'timmy', 'whisper', 'Just one quick look.'),
    (32.10, 'narr', 'normal', '…and looked inside.'),
    (34.10, 'narr', 'normal', 'He was dragging something…'),
    (36.90, 'narr', 'normal', 'Something *heavy.*'),
    (39.00, 'narr', 'normal', '*MISSING* posters. All of them.'),
    (42.00, 'narr', 'normal', 'And a *shovel.*'),
    (44.10, 'timmy', 'whisper', 'No… no way…', 45.9),
    # SPOTTED
    (48.20, 'narr', 'normal', 'Then he stopped.'),
    (50.60, 'gray', 'normal', 'I *see* you, Timmy.', 51.92),
    (53.30, 'timmy', 'shout', '~RUN!~ ~RUN!~', 55.5),
    (57.00, 'narr', 'normal', 'His light went out.'),
    (59.10, 'narr', 'normal', 'I made it home…'),
    (61.00, 'timmy', 'normal', "I'm safe… I'm safe…"),
    (63.20, 'narr', 'normal', '*Wrong.*', 63.95),
    (64.05, 'gray', 'whisper', 'Found you.', 64.97),
    # KIDNAPPED
    (65.70, 'narr', 'normal', 'Everything went black.'),
    (67.10, 'narr', 'normal', 'When I woke up…'),
    (69.00, 'narr', 'normal', 'I was tied to a chair.'),
    (70.70, 'narr', 'normal', 'In *HIS* basement.'),
    (72.00, 'timmy', 'shout', '*HELP!* Somebody help me!'),
    (74.10, 'narr', 'normal', 'Then… *footsteps.*'),
    (76.10, 'gray', 'normal', 'Timmy… are you awake?'),
    (78.10, 'narr', 'normal', 'Slow. Heavy. Coming closer.'),
    (80.10, 'gray', 'normal', 'You found my little *secret.*'),
    (82.00, 'narr', 'normal', 'Wait… my *PHONE!*'),
    (84.00, 'narr', 'normal', 'Still in my pocket.'),
    (86.00, 'gray', 'normal', "Don't be scared, Timmy."),
    (88.00, 'narr', 'normal', 'I had one chance.', 89.9),
    # THE CALL
    (93.40, 'op', 'phone', "911, what's your emergency?"),
    (94.90, 'timmy', 'whisper', 'Please *HELP* me…'),
    (96.50, 'op', 'phone', 'Where are you?'),
    (97.40, 'timmy', 'whisper', 'My neighbor took me…'),
    (99.00, 'timmy', 'whisper', '*42 Elm Street.* Hurry!'),
    (100.90, 'op', 'phone', 'Officers are on the way. Stay on the line.'),
    (103.10, 'narr', 'normal', 'He was right behind me.', 104.95),
    # JUST IN TIME
    (105.00, 'gray', 'normal', 'Who are you talking to, Timmy?', 106.95),
    (107.30, 'narr', 'normal', 'Then… *SIRENS!*'),
    (109.15, 'cop', 'shout', '*POLICE!* FREEZE!'),
    (110.50, 'narr', 'normal', 'They got here *just in time.*'),
    (112.40, 'cop2', 'normal', "You're under *arrest.*"),
    (113.70, 'gray', 'normal', 'See you *soon,* Timmy.', 115.1),
    # ENDING
    (115.20, 'cop', 'normal', "You're safe now, kid."),
    (116.80, 'narr', 'normal', 'Always trust your gut. 👀', 118.6),
]
DIALOGUE_SPEAKERS = ('timmy', 'gray', 'op', 'cop', 'cop2')

# Captions that have no voice (the sting and the dialing)
SILENT_CAPTIONS = [
    (52.00, 53.25, '*HE SAW ME.*'),
    (90.00, 93.30, '9… 1… 1…'),
]

MAX_CAPTION_WORDS = 5


def _words_with_markup(text):
    """Split into words, putting the */~ markup on each word so captions can be cut anywhere."""
    out, style = [], None
    for tok in text.split():
        st = style
        if tok.startswith('~') or tok.startswith('*'):
            st = tok[0]
            tok = tok[1:]
            style = st
        end = False
        for m in '~*':
            if m in tok:
                tok = tok.replace(m, '')
                end = True
        out.append(f'{st}{tok}{st}' if st else tok)
        if end:
            style = None
    return out


def _chunks(words, n=MAX_CAPTION_WORDS):
    """Split a line into caption chunks of <= n words, preferring breaks after punctuation."""
    if len(words) <= n:
        return [words]
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        rest = len(words) - i - 1
        punct = w.rstrip('*~')[-1:] in '.,!?…'
        if len(cur) >= n or (punct and len(cur) >= 2 and rest >= 2):
            out.append(cur)
            cur = []
    if cur:
        if len(cur) == 1 and out and len(out[-1]) < n + 1:
            out[-1] += cur
        else:
            out.append(cur)
    return out


def make_captions(timings):
    """timings: list of dicts (start, end, speaker, text) measured from the generated voice.
    Returns [(start, end, caption)] with each line cut into short chunks timed by character count."""
    caps = []
    lines = sorted(timings, key=lambda d: d['start'])
    for k, ln in enumerate(lines):
        words = _words_with_markup(ln['text'])
        chunks = _chunks(words)
        nxt = lines[k + 1]['start'] if k + 1 < len(lines) else DURATION
        for a, b, _ in SILENT_CAPTIONS:
            if ln['start'] < a < nxt:
                nxt = a
        hold_end = min(nxt, ln['end'] + 0.9) if nxt - ln['end'] < 2.5 else ln['end'] + 0.9
        if k + 1 == len(lines):
            hold_end = DURATION
        if ln.get('until'):
            hold_end = min(hold_end, ln['until'])
        dur = ln['end'] - ln['start']
        total = sum(len(''.join(c)) for c in chunks)
        t = ln['start'] if ln['start'] > 0.1 else 0.0
        quote = ln['speaker'] in DIALOGUE_SPEAKERS
        for i, c in enumerate(chunks):
            share = dur * len(''.join(c)) / total
            text = ' '.join(c)
            if quote and i == 0:
                text = '"' + text
            if quote and i == len(chunks) - 1:
                text = text + '"'
            end = t + share if i < len(chunks) - 1 else hold_end
            caps.append((round(t, 3), round(end, 3), text))
            t += share
    caps += SILENT_CAPTIONS
    return sorted(caps)


def _estimated_timings():
    out = []
    for i, ln in enumerate(VOICE_LINES):
        start, spk, style, text = ln[:4]
        n = len(text.split())
        out.append(dict(start=start, end=start + 0.35 + n / 2.8, speaker=spk, text=text,
                        until=ln[4] if len(ln) > 4 else None))
    return out


def load_captions():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build', 'voice_lines.json')
    if os.path.exists(p):
        with open(p) as f:
            return make_captions(json.load(f))
    return make_captions(_estimated_timings())


CAPTIONS = load_captions()

TEASER = 'Wait for the ending 😳'

# --------------------------------------------------------------------------- theme
# Original 8-bar creepy lullaby in A minor, 3/4 time ("music box").
# (midi note, beats). 69 = A4. G#4 (68) and D#5 (75) give it the wrong-feeling bend.
THEME_BPM = 84
THEME_MELODY = [
    # bar 1        bar 2                 bar 3                 bar 4
    (69, 1), (72, 1), (76, 1), (74, 1.5), (72, 0.5), (71, 1), (69, 1), (76, 1), (77, 1), (76, 3),
    # bar 5                 bar 6                 bar 7                            bar 8
    (77, 1), (76, 1), (74, 1), (72, 1), (71, 1), (68, 1), (69, 1), (72, 0.5), (71, 0.5), (75, 1),
    (76, 1), (69, 2),
]
# one bass note per bar (lower register, soft)
THEME_BASS = [45, 52, 53, 52, 50, 52, 53, 45]
# the final "wrong" note at the very end of the video (A4 bent ~ a quarter-tone flat)
FINAL_NOTE = (69, -0.45)  # midi, semitone offset

# --------------------------------------------------------------------------- audio cue sheet
# How the theme is used (see audio.py):
MUSIC_CUES = [
    dict(start=4.0, end=22.0, version='innocent', gain_db=-22),
    dict(start=22.0, end=47.0, version='detuned', gain_db=-20),   # cuts out before the jump scare at 52.0
    dict(start=66.6, end=107.0, version='reversed', gain_db=-19),  # stops dead at the sirens
    dict(start=119.0, end=120.0, version='final_note', gain_db=-18),
]
JUMP_SCARES = [1.5, 52.0, 65.0, 107.0]


def dump(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    data = dict(fps=FPS, duration=DURATION, size=[W, H], shots=[dict(start=a, end=b, shot=c, params=p)
                                                                 for a, b, c, p in SHOTS],
                captions=[dict(start=a, end=b, text=t) for a, b, t in CAPTIONS], teaser=TEASER,
                theme=dict(bpm=THEME_BPM, time_signature='3/4', key='A minor',
                           melody=[dict(midi=m, beats=b) for m, b in THEME_MELODY], bass_per_bar=THEME_BASS,
                           final_note=dict(midi=FINAL_NOTE[0], detune_semitones=FINAL_NOTE[1])),
                music_cues=MUSIC_CUES, jump_scares=JUMP_SCARES,
                voice_lines=[dict(start=v[0], speaker=v[1], style=v[2], text=v[3]) for v in VOICE_LINES])
    with open(path, 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return path


# sanity checks
assert abs(SHOTS[-1][1] - DURATION) < 1e-9
for (a0, a1, *_), (b0, *_r) in zip(SHOTS, SHOTS[1:]):
    assert abs(a1 - b0) < 1e-9, (a1, b0)
assert sum(b for _, b in THEME_MELODY) == 24, sum(b for _, b in THEME_MELODY)

if __name__ == '__main__':
    print(dump())
