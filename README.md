# "My cousin heard me call 911..." — Roblox-style TikTok horror story

- **`final_video.mp4`**: the finished video. 1080x1920 (9:16), 30 fps, H.264 + AAC, exactly 120.0 s.
- **`STORYBOARD.md`**: the script and storyboard with timestamps (shots, voice lines, captions, sound cues).
- **`src/`**: the code that generates everything. There are no external art, music or video assets.

## How it is made

| Part | File | Notes |
|---|---|---|
| Script | `src/script_data.py` | All voice lines with start times. Caption key words are marked `*LIKE THIS*`. |
| Audio | `src/audio.py` | Piper TTS voices, an original synthesized score (eerie music-box theme → tension → heroic) and ~30 synthesized sound effects, mixed and normalized to about −14 LUFS. Writes `build/audio.wav` and `build/vo_timing.json` (per-word timings). |
| 3D renderer | `src/engine3d.py` | A small software renderer for blocky box scenes: painter's algorithm, flat lighting with point and spot lights, fog, textured decals and planar shadows. |
| Characters/props | `src/assets.py`, `src/sets.py` | Original blocky characters (boy, cousin, police) and sets (basement, house, hallway, locked room, closet, police car). Faces, posters, newspaper, list, clock and phone screens are drawn with Pillow. |
| Shots | `src/shots.py` | The 40-shot timeline: cameras, animation and per-shot effects. |
| Inserts | `src/inserts.py` | 2D insert shots: the phone UI in hand, the newspaper, the list and the clock. |
| Overlays | `src/overlay.py` | Word-by-word TikTok captions (white, black outline, key words red, inside the safe zone), title cards, corner text, glitch, shake/zoom, vignette, bloom and grain. |
| Render | `src/render.py` | Renders the frames in parallel to H.264 segments, then muxes the final MP4. |

## Rebuild

```bash
pip install numpy scipy pillow piper-tts
# voices (Piper v0.0.2 release): lessac-medium, ryan-high, libritts-high, extracted into $VOICES/<name>/
python src/audio.py --voices $VOICES --out build
python src/render.py video --workers 4
python src/render.py mux
python src/storyboard.py
```

Voice models are not stored in this repository. They come from the `rhasspy/piper` GitHub release `v0.0.2`
(`voice-en-us-lessac-medium.tar.gz`, `voice-en-us-ryan-high.tar.gz`, `voice-en-us-libritts-high.tar.gz`).
