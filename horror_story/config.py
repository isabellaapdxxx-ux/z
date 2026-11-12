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

# --------------------------------------------------------------------------- captions
CAPTIONS = [
    (0.00, 1.00, 'My neighbor is a ~KILLER~…'),
    (1.00, 2.50, '…and I\'m *NEXT.*'),
    (2.62, 3.50, 'Here\'s how it happened…'),
    (4.20, 7.40, 'Quiet street. Nothing ever happened.'),
    (7.50, 10.90, 'Then *HE* moved in next door.'),
    (11.00, 13.00, 'Mr. Gray.'),
    (13.10, 16.40, 'He watched me. Every. Single. Day.'),
    (16.50, 19.40, 'The new neighbor *never* blinked.'),
    (19.50, 21.90, 'Not. Once.'),
    (22.10, 25.90, 'That night I couldn\'t sleep.'),
    (26.00, 27.90, 'A light. In his *basement.*'),
    (28.00, 31.90, 'So I snuck over…'),
    (32.00, 33.90, 'and looked inside.'),
    (34.10, 36.90, 'He was dragging something…'),
    (37.00, 38.90, 'Something *heavy.*'),
    (39.00, 41.90, '*MISSING.* All of them.'),
    (42.00, 43.90, 'And a *shovel.*'),
    (44.00, 45.90, 'My heart stopped.'),
    (48.20, 51.90, 'Then he stopped too.'),
    (52.00, 53.20, '*HE SAW ME.*'),
    (53.25, 56.90, '~RUN.~'),
    (57.00, 58.90, 'His light went out.'),
    (59.10, 60.90, 'I made it home…'),
    (61.00, 62.90, 'I was safe. Right?'),
    (63.20, 64.90, '*Wrong.*'),
    (65.70, 66.90, 'Everything went black.'),
    (67.10, 68.90, 'When I woke up…'),
    (69.00, 71.90, 'I was tied to a chair.'),
    (72.00, 73.90, 'In *HIS* basement.'),
    (74.10, 77.90, 'Then… *footsteps.*'),
    (78.00, 81.90, 'Slow. Heavy. Coming closer.'),
    (82.00, 83.90, 'Wait… my *PHONE!*'),
    (84.00, 87.90, 'Still in my pocket.'),
    (88.00, 89.90, 'I had one chance.'),
    (90.00, 93.90, '9… 1… 1…'),
    (94.00, 96.90, '"Please *HELP…*'),
    (97.00, 98.90, '…my neighbor…'),
    (99.00, 100.90, '*42 Elm Street.*"'),
    (101.00, 102.90, 'He was right behind me.'),
    (105.00, 106.90, 'He reached for me…'),
    (107.00, 108.90, 'Then… *SIRENS!*'),
    (109.00, 110.40, '"*POLICE!* FREEZE!"'),
    (110.50, 112.40, 'They got here *just in time.*'),
    (112.50, 114.90, 'Mr. Gray was *arrested.*'),
    (115.10, 120.00, 'Always trust your gut. 👀'),
]

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
WHISPERS = [(94.3, 96.8, 'Please help…'), (97.2, 98.8, 'my neighbor…'), (99.2, 100.8, '42 Elm Street.')]


def dump(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    data = dict(fps=FPS, duration=DURATION, size=[W, H], shots=[dict(start=a, end=b, shot=c, params=p)
                                                                 for a, b, c, p in SHOTS],
                captions=[dict(start=a, end=b, text=t) for a, b, t in CAPTIONS], teaser=TEASER,
                theme=dict(bpm=THEME_BPM, time_signature='3/4', key='A minor',
                           melody=[dict(midi=m, beats=b) for m, b in THEME_MELODY], bass_per_bar=THEME_BASS,
                           final_note=dict(midi=FINAL_NOTE[0], detune_semitones=FINAL_NOTE[1])),
                music_cues=MUSIC_CUES, jump_scares=JUMP_SCARES,
                whispers=[dict(start=a, end=b, text=t) for a, b, t in WHISPERS])
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
