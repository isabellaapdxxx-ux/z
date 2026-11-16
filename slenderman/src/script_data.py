"""Voiceover script. Each line: (text, pause_after_seconds, tags).
Caption words wrapped in *stars* are highlighted red."""
VOICE = "en-US-ChristopherNeural"

LINES = [
    ("You think you know Slender Man.", 0.35, {"boom"}),
    ("You don't.", 0.7, set()),
    ("In 2009, the Something Awful forums ran a photoshop contest: make photos look paranormal.", 0.45, set()),
    ("One user posted old pictures of children, with a tall, thin figure in a suit behind them.", 0.45, set()),
    ("He was invented. On purpose.", 0.5, set()),
    ("But he spread like real folklore.", 0.55, set()),
    ("He's *faceless*. No eyes. No mouth. No motive.", 0.45, set()),
    ("He just appears in the background of photos.", 0.4, set()),
    ("Then Marble Hornets, a found-footage YouTube series, made him feel *real*.", 0.4, set()),
    ("Thousands of people added their own sightings and stories.", 0.9, set()),
    ("But the scariest part isn't the monster.", 0.4, {"boom"}),
    ("It's that the internet built a believable myth in just a few years,", 0.3, set()),
    ("and some people started treating it as *real*.", 1.1, set()),
    ("He was made up.", 0.6, set()),
    ("That's what makes it *worse*.", 0.0, set()),
]
