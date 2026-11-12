"""Voiceover / dialogue script. Single source of truth for audio + captions.

Caption text: *word* marks a key word (rendered red). Segments are split at
'...', '.', '?' and '!' and synthesized separately so caption words can be
timed precisely against the voice.
"""

# (id, start_seconds, speaker, caption_text, options)
LINES = [
    # ---- HOOK
    ('h1', 0.00, 'narr', 'My cousin heard me call *911*...', {'fit': 1.45, 'speed': 1.2}),
    ('h2', 1.55, 'narr', "...and now I'm in his *BASEMENT*.", {'fit': 1.4, 'speed': 1.15}),
    ('h3', 3.0, 'cousin', "You shouldn't have looked in that room.", {'fit': 1.85}),
    # ---- 1. NORMAL DAY
    ('s1', 6.25, 'narr', 'Three hours earlier, I was visiting my older cousin Derek.', {}),
    ('s2', 10.1, 'narr', 'He was always super nice to me.', {}),
    ('s3', 12.4, 'cousin_nice', 'Hey buddy! Make yourself at home.', {}),
    ('s4', 15.3, 'narr', 'We played games, ate pizza... everything felt normal.', {}),
    ('s5', 19.4, 'narr', 'Except for one thing.', {}),
    ('s6', 21.0, 'narr', 'The door at the end of the hall... was always *LOCKED*.', {}),
    ('s7', 25.1, 'boy', "What's in there?", {}),
    ('s8', 26.6, 'cousin', "Nothing. Don't ever go in there.", {}),
    # ---- 2. DISCOVERY
    ('d1', 30.2, 'narr', 'That night, he went out for snacks... and left his keys.', {}),
    ('d2', 34.4, 'narr', "I know. I shouldn't have.", {}),
    ('d3', 38.0, 'narr', 'The walls were covered in *MISSING* posters.', {}),
    ('d4', 41.3, 'narr', 'Newspaper clippings. Kids who never came home.', {}),
    ('d5', 44.9, 'narr', 'And on the desk... a list of names.', {}),
    ('d6', 47.7, 'narr', 'My name was at the *BOTTOM*.', {}),
    ('d7', 50.0, 'whisper', 'My cousin is a... *KILLER*?', {}),
    ('d8', 52.7, 'narr', 'Then I heard the front door.', {}),
    # ---- 3. THE CALL
    ('c1', 55.3, 'narr', 'I hid in the closet and called *911*.', {}),
    ('c2', 61.2, 'operator', '*911*, what is your emergency?', {}),
    ('c3', 63.8, 'whisper', "Please help... my cousin is a *KILLER*. I'm at his house.", {}),
    ('c4', 68.7, 'narr', 'Then... footsteps.', {}),
    ('c5', 71.45, 'cousin', 'Found you.', {}),
    # ---- 4. KIDNAPPED
    ('k1', 75.6, 'narr', 'When I woke up, I was in his *BASEMENT*.', {}),
    ('k2', 78.7, 'cousin', "You shouldn't have looked in that room.", {}),
    ('k3', 83.5, 'cousin', "*NOBODY'S* *COMING*.", {}),
    ('k4', 86.1, 'narr', 'The call dropped before I could say where I was.', {}),
    ('k5', 90.6, 'narr', 'He went upstairs to get the car ready.', {}),
    ('k6', 93.6, 'narr', 'Every second felt like an hour.', {}),
    ('k7', 96.6, 'boy', 'Somebody... please...', {}),
    ('k8', 101.2, 'cousin', "It's time to go.", {}),
    # ---- 5. RESCUE
    ('r1', 105.9, 'cop', '*POLICE*! Hands where we can see them!', {}),
    ('r2', 109.6, 'narr', 'The call went through. They traced my location.', {}),
    ('r3', 113.0, 'cop', "You're safe now, kid.", {}),
    # ---- 6. ENDING
    ('e1', 115.1, 'narr', 'I was safe...', {}),
    ('e2', 116.4, 'narr', "...but he said he'd be *BACK*.", {}),
]

# Title cards (big centered text, no voice): (start, end, text)
TITLES = [
    (4.80, 6.05, '3 HOURS EARLIER...'),
    (118.15, 119.35, 'Part 2?'),
]

DURATION = 120.0
FPS = 30
