# "iPhone 18 Pro Max" — 30-second concept ad (unofficial fan concept)

- **`iphone18_ad.mp4`**: the finished ad. 1920x1080, 30 fps, exactly 30.000 s (900 frames), H.264 (BT.709) + AAC 48 kHz stereo.
- **`captions.srt`**: the captions, matching the ones burned into the video.
- **`stills/`**: check frames at 2 s, 9 s, 20 s and 26 s.
- **`src/`**: all the code. Every picture and sound is generated in code: no stock images, footage, fonts beyond the system's Inter, or downloaded audio.

Fan-made concept, not affiliated with Apple. No Apple logo is used.

## Timeline

| Time | Scene | Caption |
|---|---|---|
| 0–3 s | Black. A thin vertical light line sweeps across the frame and reveals the rim-lit silhouette. | Something big is coming. |
| 3–7 s | Flash on the boom, then a slow rotation; a light band glides along the titanium edge. | iPhone 18 Pro Max |
| 7–11 s | Push into the camera plateau; the three lenses light up one by one (7.8 / 8.6 / 9.4 s). | A camera that sees everything. |
| 11–15 s | Screen wakes with an animated wallpaper; bezels shrink from 4.7 mm to 1.25 mm. | The biggest, brightest display yet. |
| 15–19 s | Montage, 1 s each: chip with light pulses racing along traces / battery filling / rain on the phone / night-mode photo developing. | Faster. / Longer. / Tougher. / Brighter. |
| 19–24 s | 360° spin that lands front-facing at 22.3 s with a particle burst. | Pro. Beyond Max. |
| 24–28 s | Title card "iPhone 18 Pro Max" + "Coming soon." | (on-screen title) |
| 28–30 s | Fade to black; "Fan-made concept – not affiliated with Apple". | (on-screen disclaimer) |

Captions are white Inter Bold with a soft dark shadow, centred near the bottom, and fade in and out over 0.3 s.

## Sound (all synthesised with NumPy)

- Music: a detuned-saw pad (Dm – B♭maj7 – F – C – Dm – B♭ – Asus4/A) whose filter opens as it builds. A sub-bass pulse speeds up from 1/s to 8/s until 24 s, where everything resolves to D major with a bell arpeggio.
- Effects: whooshes (band-passed noise sweeps) on every scene transition (3, 7, 11, 15, 19, 24, 28 s); booms at 3, 19 and 24 s; shimmering dings as each lens lights; ticks on the montage cuts (15, 16, 17, 18 s); a riser from 22 to 24 s; rain patter during "Tougher.".
- Master: convolution reverb, look-ahead limiter, peak-normalised to −1 dBFS, 1.5 s fade-out. Exactly 1,440,000 samples.

## How it is made

| File | What it does |
|---|---|
| `src/phone3d.py` | A small NumPy sphere-tracing renderer. The phone is a signed distance field: rounded titanium body, camera plateau, protruding lenses with recessed glass, side buttons. It is shaded with studio soft boxes, a moving sweep light, titanium Fresnel, frosted back glass and a glossy front glass with a textured, emissive screen. Rendered with 2x2 supersampling. |
| `src/screens.py` | 2D content: the wallpaper and lock screen, the night photo, the chip and battery graphics, rain, particles, bokeh and the light line. |
| `src/film.py` | The timeline: cameras, poses and animation per scene, transitions (flashes, whip blur, punch-ins), bloom and tone mapping, title card and disclaimer. |
| `src/captions.py` | Burned-in captions and the SRT writer. |
| `src/audio.py` | Music and sound effects, mix and master. |
| `src/render.py` | Build driver: previews, a parallel render piped to ffmpeg, mux, ffprobe checks and stills. |

## Rebuild

```bash
pip install numpy pillow          # plus ffmpeg on PATH
cd src
python render.py video --workers 4   # ~12 min on 4 cores -> build/video.mp4
python render.py audio               # build/audio.wav
python render.py mux                 # iphone18_ad.mp4 + captions.srt
python render.py check               # duration / frame count / audio length / peak
python render.py stills 2 9 20 26    # stills/
```
