"""Shared timing for audio and video (seconds)."""
W, H, FPS, DUR = 1080, 1920, 30, 60.0
SR = 48000

# (start, end, scene name). Cuts sit on voiceover phrase boundaries.
SCENES = [
    (0.00, 3.90, "hook"),        # You think you know Slender Man. You don't.
    (3.90, 8.85, "forum"),       # In 2009, the Something Awful forums ran a photoshop contest:
    (8.85, 13.95, "photo"),      # make photos look paranormal. One user posted old pictures of children,
    (13.95, 19.45, "layer"),     # with a tall, thin figure in a suit behind them. He was invented.
    (19.45, 23.90, "spread"),    # On purpose. But he spread like real folklore.
    (23.90, 28.90, "faceless"),  # He's faceless. No eyes. No mouth.
    (28.90, 34.30, "polaroids"), # No motive. He just appears in the background of photos.
    (34.30, 39.60, "camcorder"), # Then Marble Hornets, a found-footage YouTube series, made him feel real.
    (39.60, 43.90, "sightings"), # Thousands of people added their own sightings and stories.
    (43.90, 47.90, "twist"),     # But the scariest part isn't the monster.
    (47.90, 51.90, "screens"),   # It's that the internet built a believable myth in just a few years,
    (51.90, 56.30, "viewer"),    # and some people started treating it as real. He was made up.
    (56.30, 59.00, "final"),     # That's what makes it worse.
    (59.00, 60.00, "black"),     # 1 s of silence on black
]
CUTS = [s for s, _, _ in SCENES[1:]]
BOOMS = [0.10, 44.08]            # hook + twist
# Transition at each cut: (cut, kind, seconds before, seconds after, options).
# The final cut to black at 59.0 stays a hard cut on purpose.
TRANSITIONS = [
    (3.90, "slice", 0.20, 0.20, {}),               # hook -> forum: VHS slice wipe
    (8.85, "zoom", 0.25, 0.30, {"cy": 0.47}),      # forum -> photo: punch through the screen
    (13.95, "whip", 0.18, 0.18, {"dir": (-1, 0)}), # photo -> editor: whip pan left
    (19.45, "burn", 0.35, 0.35, {}),               # editor -> spread: noise burn dissolve
    (23.90, "flash", 0.15, 0.25, {}),              # spread -> faceless: white flash
    (28.90, "whip", 0.18, 0.18, {"dir": (0, -1)}), # faceless -> polaroids: whip up
    (34.30, "vhs", 0.25, 0.25, {}),                # polaroids -> camcorder: tape rewind roll
    (39.60, "slice", 0.20, 0.20, {}),              # camcorder -> sightings
    (43.90, "dip", 0.20, 0.15, {}),                # sightings -> twist: dip to black before the boom
    (47.90, "zoom", 0.25, 0.30, {}),               # twist -> screens
    (51.90, "fog", 0.45, 0.45, {}),                # screens -> viewer: fog rolls through
    (56.30, "zoom", 0.30, 0.25, {"cy": 0.40}),     # viewer -> final: rides the reversed-reverb whoosh
]
GLITCH_CUTS = [c for c, k, *_ in TRANSITIONS if k in ("slice", "vhs")]   # static bursts (audio + video)
WHOOSH_CUTS = [c for c, k, *_ in TRANSITIONS if k in ("whip", "zoom") and c != 56.30]
SWELL_CUTS = [c for c, k, *_ in TRANSITIONS if k in ("burn", "flash", "fog")]
HEART_START, HEART_END = 23.9, 54.70
RING_START, RING_END = 52.2, 54.70   # high ringing swell, cut right as "He was made up" lands
FINAL_LINE_START = 56.47
BLACK = 59.0
# a few extra mid-scene VHS hiccups (video + tiny audio tick)
MINI_GLITCHES = [6.6, 16.3, 26.9, 37.2, 49.6, 53.9]
