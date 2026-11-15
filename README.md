# "My cousin heard me call 911..." — Roblox-style TikTok horror story

- **`final_video.mp4`**: the finished video. 1080x1920 (9:16), 30 fps, H.264 + AAC, exactly 120.0 s.
- **`STORYBOARD.md`**: the script and storyboard with timestamps (shots, voice lines, captions, sound cues).
- **`src/`**: the code that generates everything. There are no external art, music or video assets.

## How it is made

| Part | File | Notes |
|---|---|---|
| Script | `src/script_data.py` | All voice lines with start times. Caption key words are marked `*LIKE THIS*`. |
| Audio | `src/audio.py` | Kokoro neural TTS voices (boy: `am_puck`, cousin: `am_fenrir`, operator: `af_heart`, police: `am_michael`), an original synthesized score (eerie music-box theme → tension → heroic) and ~30 synthesized sound effects, mixed and normalized to about −14 LUFS. Writes `build/audio.wav` and `build/vo_timing.json` (per-word timings). |
| 3D renderer | `src/engine3d.py` | A small software renderer for blocky box scenes: painter's algorithm, flat lighting with point and spot lights, fog, textured decals and planar shadows. |
| Characters/props | `src/assets.py`, `src/sets.py` | Original blocky characters (boy, cousin, police) and sets (basement, house, hallway, locked room, closet, police car). Faces, posters, newspaper, list, clock and phone screens are drawn with Pillow. |
| Shots | `src/shots.py` | The 40-shot timeline: cameras, animation and per-shot effects. |
| Inserts | `src/inserts.py` | 2D insert shots: the phone UI in hand, the newspaper, the list and the clock. |
| Overlays | `src/overlay.py` | Word-by-word TikTok captions (white, black outline, key words red, inside the safe zone), title cards, glitch, shake/zoom, vignette, bloom and grain. |
| Render | `src/render.py` | Renders the frames in parallel to H.264 segments, then muxes the final MP4. |

## Rebuild

```bash
pip install numpy scipy pillow kokoro-onnx
# $VOICES must contain kokoro-v1.0.onnx and voices-v1.0.bin
python src/audio.py --voices $VOICES --out build
python src/render.py video --workers 4
python src/render.py mux
python src/storyboard.py
```

Voice models are not stored in this repository. They come from the `thewh1teagle/kokoro-onnx` GitHub release
`model-files-v1.0` (`kokoro-v1.0.onnx`, `voices-v1.0.bin`).

---

# iPhone 17 Pro Max: 30 s TikTok ad (fan-made)

A creator-style ad, **not an official Apple ad**. There is no Apple logo and no Apple photos, video or music. The phone is drawn in code, and the music and sound effects are synthesized.

- **`make_tiktok_ad.py`**: one script (Pillow + NumPy + ffmpeg). Text, colors, voice, levels and timings are in the `CONFIG` / `SCENES` block at the top.
- **`output/tiktok_ad.mp4`**: 1080x1920, 30 fps, H.264 (yuv420p) + AAC, exactly 30.00 s, about -14 LUFS.
- **`output/tiktok_ad.srt`**: captions, also burned into the video.
- **`output/previews/`**: the busiest frame of each scene, a `_zones` version showing TikTok's UI zones, and `contact_sheet.png`.

```bash
python make_tiktok_ad.py                # full build (about 1-2 min on 4 cores)
python make_tiktok_ad.py --preview-only # voice + audio + preview PNGs only
```

Voice: edge-tts (`en-US-GuyNeural`, +10%), falling back to gTTS and then ffmpeg `flite`. edge-tts needs network access to `speech.platform.bing.com`.
