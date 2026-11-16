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
GLITCH_CUTS = [c for c in CUTS if c not in (56.30, 59.00)]   # static bursts on transitions
HEART_START, HEART_END = 23.9, 54.70
RING_START, RING_END = 52.2, 54.70   # high ringing swell, cut right as "He was made up" lands
FINAL_LINE_START = 56.47
BLACK = 59.0
# a few extra mid-scene VHS hiccups (video + tiny audio tick)
MINI_GLITCHES = [6.6, 16.3, 26.9, 37.2, 49.6, 53.9]
