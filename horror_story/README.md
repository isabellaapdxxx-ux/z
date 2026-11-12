# "My neighbor is a KILLER… and I'm next." (blocky TikTok horror short)

- **`../horror_story.mp4`**: the finished video. 1080x1920 (9:16), 30 fps, H.264 + AAC 48 kHz, exactly 120.0 s.
- **`theme.wav`**: the original music-box theme on its own (clean pass, darker detuned pass, then the broken final note).
- **`preview/`**: stills pulled from the final MP4 at key moments (hook, jump scare, payoff, ending).
- **`config.py` / `config.json`**: the script. Shot list with timestamps, caption timings, theme melody notes, music cue sheet.

Every image and sound is generated in code. There are no downloads or external assets. The characters (Timmy, Mr. Gray, the
police) and the sets are original blocky designs, with no logos or branding.

## Pipeline

| Step | File | What it does |
|---|---|---|
| Script | `config.py` | 64 shots (one visual change every 0.5–3 s), 45 captions (`*red*`, `~red + shaking~`), the 8-bar theme in A minor (3/4, 84 bpm), music cues. `python config.py` writes `config.json`. |
| Renderer | `engine3d.py` | Small software renderer for box scenes: painter's algorithm, flat shading with point/spot lights, fog, textured decals. |
| Assets | `assets.py` | Pixel-art faces (12x12, NEAREST-scaled), blocky characters with poses (walk, run, sit, tied up, blanket), MISSING posters, sky, windows, signs. |
| Sets | `sets.py` | Suburban street (day/night, sickly green porch light, Gray's basement window), the basement (stairs, door, swinging bulb, poster wall, shovel, bag), Timmy's hallway and bedroom, police cars. |
| Shots | `shots.py` | One function per shot: camera moves, animation, lighting, and per-shot post settings. Also the 2D phone UI (911 dialer, calling, connected). |
| Post/captions | `fx.py` | Shake, zoom, grade, drifting fog, grain, vignette (pulses with the heartbeat), glitch, VHS rewind (tracking band + static + HUD), police red/blue edge light, eyelid wake-up. TikTok captions (white, thick black outline, red key words, pop-in bounce) and the top "Wait for the ending 😳" progress bar. |
| Audio | `audio.py` | Music-box theme (sine partials with pluck envelopes, pitch wobble, echo and convolution reverb) in four versions: innocent (slowed), detuned (flat, ghost minor seconds, octave-down double), reversed and distorted (reverse reverb, pitched down, bit-crushed), and the final off-key note. SFX: drone, wind, crickets, birds, heartbeat, grass/wood steps with creaks, door creak/slam/burst, jump-scare stings, tape rewind, glitches, DTMF, ringback, muffled operator, formant-noise whispers, sirens (muffled once we are back in the basement), tire screech, police radio, bulb buzz. Peak limiter at -1 dBFS. |
| Render | `render.py` | Renders frames in 4 parallel processes to H.264 segments, concatenates them, then muxes with the audio. |

## Mix targets

- Jump scares (0:01.5, 0:52, 1:05) are the loudest moments, peaking at -1 to -2 dBFS. The sirens peak at -3 dBFS.
- Music cues peak at -22 (setup), -20 (discovery), -19 (kidnapped) and -18 (final note) dBFS. They are ducked by 10 dB under the whispers.
- The theme cuts out before each scare: 47.0 s (scare at 52.0), and it is absent before 65.0. It stops dead at 107.0 when the sirens hit.

## Rebuild

```bash
pip install numpy scipy pillow     # ffmpeg must be on PATH
cd horror_story
python config.py                   # config.json
python audio.py                    # build/audio.wav + theme.wav
python render.py video --workers 4 # build/video.mp4 (~12 min on 4 cores)
python render.py mux               # ../horror_story.mp4
python render.py frames 0 1.5 3    # optional: PNG stills straight from the renderer
```
