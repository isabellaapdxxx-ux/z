# Slender Man: "He was made up. That's what makes it worse."

60-second vertical TikTok explainer.

- **`slenderman_tiktok.mp4`**: 1080x1920, 30 fps, H.264 High + AAC 48 kHz stereo, exactly 60.000 s (1800 frames).
- **`caption.txt`**: the post caption and hashtags.
- **`voice_samples/`**: the same test sentence in the three candidate edge-tts voices (rate -8%, pitch -6 Hz).
- **`src/`**: everything that generates the video. No images, footage, music or sound files are used. All visuals and sound are synthesized.

| Step | File | What it does |
|---|---|---|
| Script | `src/script_data.py` | 15 lines (123 words). Each has a pause after it. Words to show in red are marked `*like this*`. |
| Voice | `src/gen_voice.py`, `src/tts_util.py` | edge-tts `en-US-ChristopherNeural`, rate -8%, pitch -6 Hz. Generated one sentence at a time with WordBoundary timings. |
| Voice track | `src/build_voice.py` | ffmpeg: trims each sentence, puts 0.3-1.1 s silences between them, applies a 70 Hz high-pass, a low-shelf boost and small room reverb (synthetic impulse response through `afir`), then two-pass `loudnorm` to -14 LUFS. Writes the global word timeline. |
| Sound design | `src/mix_audio.py` | Synthesized: dark drone, wind and twig snaps, a heartbeat that goes from 56 to 120 bpm, sub booms on the hook and the twist, static bursts on cuts, a 3.5 kHz ringing swell, and reversed-reverb whooshes into the last line. The bed ducks under the voice. The final mix is at -14 LUFS and prints level checks. |
| Visuals | `src/art.py`, `src/scenes.py` | 13 procedural scenes, each 4-6 s: foggy forest, 2009 forum page, old photo, photo-editor layer, folklore spreading as a network, faceless close-up, polaroids, camcorder footage, a feed of sightings, a red forest with the figure gone, a wall of screens, a lone viewer, and the final push-in. |
| Transitions | `src/transitions.py`, `TRANSITIONS` in `src/config.py` | Each of the 12 scene changes has its own transition, centred on the cut: VHS slice wipes, zoom-throughs with radial blur, whip pans with motion blur, a noise burn dissolve, a white flash, a tape-rewind roll, a dip to black and a fog wipe. The cut to black at 59 s stays hard. Each transition has a sound in `src/mix_audio.py`: a whoosh for whips and zooms, a reversed swell for dissolves, static for glitches. |
| Render | `src/render.py` | Ken Burns moves, fog, film grain, vignette, flicker and VHS/static glitches. Captions are burned in 2-3 words at a time from the TTS word timings. The red words are FACELESS, REAL and WORSE. Frames are rendered in 4 parallel H.264 segments and then muxed. |

## Rebuild

```bash
pip install edge-tts numpy scipy pillow opencv-python-headless pyloudnorm
cd slenderman
python src/gen_voice.py      # needs network (Microsoft edge TTS)
python src/build_voice.py
python src/mix_audio.py
python src/render.py preview 1 10 25 57   # optional stills -> build/preview/
python src/render.py video --workers 4
python src/render.py mux                  # -> slenderman_tiktok.mp4
```
