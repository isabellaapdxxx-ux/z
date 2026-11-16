"""edge-tts helpers. The session proxy re-terminates TLS, so the SSL context is
pointed at the system CA bundle (verification stays on)."""
import asyncio, os, ssl
import edge_tts
from edge_tts import communicate as _comm

CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
if os.path.exists(CA):
    _comm._SSL_CTX = ssl.create_default_context(cafile=CA)

RATE, PITCH = "-8%", "-6Hz"

async def _synth(text, voice, out_mp3):
    c = edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH,
                             boundary="WordBoundary",
                             proxy=os.environ.get("HTTPS_PROXY"))
    words = []
    with open(out_mp3, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"text": ch["text"],
                              "start": ch["offset"] / 1e7,
                              "end": (ch["offset"] + ch["duration"]) / 1e7})
    return words

def synth(text, voice, out_mp3):
    for attempt in range(4):
        try:
            return asyncio.run(_synth(text, voice, out_mp3))
        except Exception as e:  # network hiccups
            if attempt == 3:
                raise
            print("retry", e)
