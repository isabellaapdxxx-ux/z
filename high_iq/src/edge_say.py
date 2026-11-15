"""edge-tts wrapper that trusts the session's proxy CA bundle (edge-tts pins certifi by default)."""
import asyncio, os, ssl, sys
import edge_tts, edge_tts.communicate as ec
CA = "/root/.ccr/ca-bundle.crt"
if os.path.exists(CA):
    ec._SSL_CTX = ssl.create_default_context(cafile=CA)

async def say(text, voice, out, rate="+0%", pitch="+0Hz"):
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)

if __name__ == "__main__":
    text, voice, out = sys.argv[1:4]
    rate = sys.argv[4] if len(sys.argv) > 4 else "+0%"
    pitch = sys.argv[5] if len(sys.argv) > 5 else "+0Hz"
    asyncio.run(say(text, voice, out, rate, pitch))
