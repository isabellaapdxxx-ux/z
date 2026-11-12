# "My neighbor is a KILLER… and I'm next." (blocky TikTok horror short)

- **`../horror_story.mp4`**: the finished video. 1080x1920 (9:16), 30 fps, H.264 + AAC 48 kHz, exactly 120.0 s.
- **`theme.wav`**: the original music-box theme on its own (clean pass, darker detuned pass, then the broken final note).
- **`preview/`**: stills pulled from the final MP4 at key moments (hook, jump scare, payoff, ending).
- **`config.py` / `config.json`**: the script. Shot list with timestamps, caption timings, theme melody notes, music cue sheet.

All visuals, music and sound effects are generated in code, with no external assets. The voices come from the open
Kokoro-82M text-to-speech model (Apache-2.0), which is downloaded once (see Rebuild). The characters (Timmy, Mr. Gray, the
police) and the sets are original blocky designs, with no logos or branding.

## Pipeline

| Step | File | What it does |
|---|---|---|
| Script | `config.py` | 64 shots (one visual change every 0.5–3 s), the voice script (narration + dialogue for Timmy, Mr. Gray, the 911 operator and the police; captions are generated from it in chunks of 5 words or fewer, dialogue in quotes, `*red*`, `~red + shaking~`), the 8-bar theme in A minor (3/4, 84 bpm), music cues. `python config.py` writes `config.json`. |
| Renderer | `engine3d.py` | Small software renderer for box scenes: painter's algorithm, flat shading with point/spot lights, fog, textured decals. |
| Assets | `assets.py` | Pixel-art faces (12x12, NEAREST-scaled) with open-mouth talking variants for lip sync, blocky characters with poses (walk, run, sit, tied up, blanket), MISSING posters, sky, windows, signs. |
| Sets | `sets.py` | Suburban street (day/night, sickly green porch light, Gray's basement window), the basement (stairs, door, swinging bulb, poster wall, shovel, bag), Timmy's hallway and bedroom, police cars. |
| Shots | `shots.py` | One function per shot: camera moves, animation, lighting, and per-shot post settings. Also the 2D phone UI (911 dialer, calling, connected). |
| Post/captions | `fx.py` | Shake, zoom, grade, drifting fog, grain, vignette (pulses with the heartbeat), glitch, VHS rewind (tracking band + static + HUD), police red/blue edge light, eyelid wake-up. TikTok captions (white, thick black outline, red key words, pop-in bounce) and the top "Wait for the ending 😳" progress bar. |
| Voices | `voices.py` | Every caption is spoken. Timmy narrates the story and every character says their own lines, using Kokoro neural TTS with pitch-shifted casting: Timmy is `af_heart` +2.5 semitones (~250 Hz, a young boy), Mr. Gray is `bm_george` -3 semitones and slow, the 911 operator is `af_sarah` phone-filtered, and the police are `am_michael` / `am_fenrir`. Whispers are made by LPC: each frame keeps the mouth-shape filter and its source is replaced with breath noise. Shouts and phone lines get their own processing, and the basement adds room reverb. Each line is sped up only as much as needed to fit its slot. Writes the voice track, the measured timings (caption chunks snap to the pauses in the speech) and the open-mouth frames for lip sync, measured from the real audio. `--synth` falls back to the procedural "blocky game" babble voice. |
| Audio | `audio.py` | Music-box theme (sine partials with pluck envelopes, pitch wobble, echo and convolution reverb) in four versions: innocent (slowed), detuned (flat, ghost minor seconds, octave-down double), reversed and distorted (reverse reverb, pitched down, bit-crushed), and the final off-key note. SFX: drone, wind, crickets, birds, heartbeat, grass/wood steps with creaks, door creak/slam/burst, jump-scare stings, tape rewind, glitches, DTMF, ringback, sirens (muffled once we are back in the basement), tire screech, police radio, bulb buzz. Everything is lowpassed at 16 kHz and peak-limited at -2 dBFS, so the AAC encode never clips. |
| Render | `render.py` | Renders frames in 4 parallel processes to H.264 segments, concatenates them, then muxes with the audio. |

## Mix targets

- Jump scares (0:01.5, 0:52, 1:05) are the loudest moments, peaking at -2 dBFS (the limiter ceiling) with the highest RMS. The sirens peak around -2.6 dBFS and run ~3 dB quieter in RMS.
- Voices peak around -8 dBFS (whispers -10.5, shouts -9.5). Music cues peak at -22 (setup), -20 (discovery), -19 (kidnapped)
  and -18 (final note) dBFS. Under every spoken line the music ducks 10 dB and the ambience 5 dB.
- The theme cuts out before each scare: 47.0 s (scare at 52.0), and it is absent before 65.0. It stops dead at 107.0 when the sirens hit.

## Rebuild

```bash
pip install numpy scipy pillow kokoro-onnx   # ffmpeg must be on PATH
cd horror_story
# voice model (once): kokoro-v1.0.onnx + voices-v1.0.bin from the thewh1teagle/kokoro-onnx
# GitHub release "model-files-v1.0", into build/kokoro/ (or set KOKORO_DIR)
python voices.py                   # build/voice.wav, voice_lines.json, voice_env.json (run first)
python config.py                   # config.json
python audio.py                    # build/audio.wav + theme.wav
python render.py video --workers 4 # build/video.mp4 (~12 min on 4 cores)
python render.py mux               # ../horror_story.mp4
python render.py frames 0 1.5 3    # optional: PNG stills straight from the renderer
```
