"""Shared constants: video format, script, voice settings and timing rules."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
FONTS = ROOT / "fonts"
OUTPUT = ROOT / "final_tiktok.mp4"

W, H = 1080, 1920
FPS = 30
DURATION = 60.0
N_FRAMES = int(round(DURATION * FPS))  # 1800
SR = 48000

FONT_BOLD = FONTS / "Poppins-Bold.ttf"
FONT_XBOLD = FONTS / "Poppins-ExtraBold.ttf"
FONT_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
FONT_URLS = {
    # Google Fonts static TTFs (OFL). Resolved from fonts.googleapis.com/css2.
    FONT_BOLD: "https://fonts.gstatic.com/s/poppins/v24/pxiByp8kv8JHgFVrLCz7V1s.ttf",
    FONT_XBOLD: "https://fonts.gstatic.com/s/poppins/v24/pxiByp8kv8JHgFVrLDD4V1s.ttf",
}

# ---------------------------------------------------------------- voice
VOICE = "en-US-AndrewMultilingualNeural"
VOICE_FALLBACK = "en-US-GuyNeural"
RATE = "+8%"
MAX_ATEMPO = 1.10
VOICE_TARGET_MAX = 58.0  # if the voice track (with pauses) runs longer, speed it up

LINES = [
    "How big is the universe? Like… actually?",
    "Light is the fastest thing there is. It can circle Earth seven times in one second.",
    "It reaches the Moon in just over a second.",
    "The Sun? Eight minutes.",
    "Voyager 1 has been flying for 49 years, and light reaches it in about a day.",
    "The next closest star? Over four years at light speed.",
    "Crossing our galaxy? A hundred thousand years.",
    "Andromeda, our big neighbour, is two and a half million light-years away.",
    "Zoom out, and our supercluster, Laniakea, holds around a hundred thousand galaxies.",
    "Zoom out more, and galaxies form a giant cosmic web.",
    "Hubble once stared at a tiny, empty-looking patch of sky… and found thousands of galaxies.",
    "Now the crazy part. The universe is 13.8 billion years old…",
    "…but the part we can see is 93 billion light-years across.",
    "Because space itself keeps stretching, carrying galaxies away while their light is still on its way to us.",
    "And beyond that? Nobody knows. It might be infinite.",
    "So yeah. You're tiny.",
]

# ---------------------------------------------------------------- timing
LEAD_IN = 0.20          # silence before the first word
TAIL_MIN = 1.40         # hold on "you are here" after the last word
# Pause before line i (index = line number, 1-based). Default for the rest.
GAP_DEFAULT = 0.30
GAPS = {
    2: 0.30, 5: 0.32, 6: 0.28, 9: 0.30, 10: 0.28,
    12: 0.95,  # riser -> flash -> one beat of silence -> "Now the crazy part"
    13: 0.10,  # "...but" follows straight on
    15: 0.50,  # slow fade to black
    16: 0.45,
}
GAP_STRETCH_MAX = 0.85  # when the voice is short, pauses can grow up to this
# Shortest each pause may get when the voice is long (after max atempo).
GAP_FLOOR_DEFAULT = 0.10
GAP_FLOORS = {12: 0.72, 13: 0.06, 15: 0.36, 16: 0.24}

# How long before its voice line each scene's cut starts (seconds).
LEAD_DEFAULT = 0.22
LEADS = {12: 0.62, 13: 0.10, 15: 0.38}

# Transition into scene i: (kind, duration).
TRANSITIONS = {
    2: ("whip_left", 0.30),
    3: ("whip_up", 0.28),
    4: ("whip_right", 0.30),
    5: ("whip_left", 0.32),
    6: ("zoom_out", 0.40),
    7: ("zoom_out", 0.40),
    8: ("zoom_out", 0.36),
    9: ("zoom_out", 0.40),
    10: ("zoom_out", 0.40),
    11: ("whip_down", 0.30),
    12: ("flash", 0.30),
    13: ("glitch", 0.36),
    14: ("zoom_in", 0.32),
    15: ("fade_black", 0.40),
    16: ("zoom_in", 0.34),
}
