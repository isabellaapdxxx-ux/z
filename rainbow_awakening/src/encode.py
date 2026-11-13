"""Mux rendered frames + build/mix.wav into the final MP4 and verify it with ffprobe.

  python src/encode.py final   [--frames frames/full]     -> final_tiktok.mp4   (1080x1920, 30 fps, 2700 frames)
  python src/encode.py preview [--frames frames/preview]  -> preview_lowres.mp4 (540x960, rendered every 2nd frame)

The final file must be exactly 2700 video frames and 90.000 s; the script checks this with ffprobe
(frame count via -count_frames, stream + container durations) and fails loudly otherwise.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

FPS, N, DUR = 30, 2700, 90.0


def run(cmd):
    print('+', ' '.join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_entries',
                          'format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,'
                          'nb_read_frames,nb_frames,duration,sample_rate,channels,profile,pix_fmt',
                          '-of', 'json', path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def verify(path, expect_frames, expect_dur, w, h):
    p = probe(path)
    v = next(s for s in p['streams'] if s['codec_type'] == 'video')
    a = next(s for s in p['streams'] if s['codec_type'] == 'audio')
    fmt_dur = float(p['format']['duration'])
    problems = []
    if int(v['nb_read_frames']) != expect_frames:
        problems.append(f"video has {v['nb_read_frames']} frames, expected {expect_frames}")
    if abs(float(v['duration']) - expect_dur) > 1e-6:
        problems.append(f"video stream duration {v['duration']} != {expect_dur}")
    if abs(float(a['duration']) - expect_dur) > 0.0005:
        problems.append(f"audio stream duration {a['duration']} != {expect_dur}")
    if abs(fmt_dur - expect_dur) > 0.0005:
        problems.append(f'container duration {fmt_dur} != {expect_dur}')
    if (v['width'], v['height']) != (w, h):
        problems.append(f"size {v['width']}x{v['height']}")
    print(f"{path}: {v['codec_name']} {v.get('profile')} {v['width']}x{v['height']} {v['r_frame_rate']} fps, "
          f"{v['nb_read_frames']} frames, video {float(v['duration']):.6f} s, audio {a['codec_name']} {a['sample_rate']} Hz "
          f"{a['channels']}ch {float(a['duration']):.6f} s, container {fmt_dur:.6f} s, "
          f"{int(p['format']['size']) / 1e6:.1f} MB, {int(p['format']['bit_rate']) / 1e6:.2f} Mbit/s")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['final', 'preview'])
    ap.add_argument('--frames')
    ap.add_argument('--audio', default='build/mix.wav')
    ap.add_argument('--out')
    ap.add_argument('--vbitrate', default='7000k')
    a = ap.parse_args()
    if a.mode == 'preview':
        fdir = a.frames or 'frames/preview'
        out = a.out or 'preview_lowres.mp4'
        files = sorted(glob.glob(os.path.join(fdir, 'f_*.jpg')))
        step = 2
        assert len(files) == N // step, f'{len(files)} preview frames, expected {N // step}'
        run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(FPS // step), '-pattern_type', 'glob', '-i', os.path.join(fdir, 'f_*.jpg'),
             '-i', a.audio, '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
             '-pix_fmt', 'yuv420p', '-r', str(FPS), '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', out])
        problems = verify(out, N, DUR, 540, 960)
    else:
        fdir = a.frames or 'frames/full'
        out = a.out or 'final_tiktok.mp4'
        missing = [f for f in range(N) if not os.path.exists(os.path.join(fdir, f'f_{f:05d}.jpg'))]
        assert not missing, f'{len(missing)} frames missing, first {missing[:5]}'
        common = ['-framerate', str(FPS), '-start_number', '0', '-i', os.path.join(fdir, 'f_%05d.jpg'), '-frames:v', str(N),
                  '-c:v', 'libx264', '-preset', 'slow', '-profile:v', 'high', '-level:v', '4.2', '-pix_fmt', 'yuv420p',
                  '-b:v', a.vbitrate, '-maxrate', '12M', '-bufsize', '16M', '-g', '60', '-color_primaries', 'bt709',
                  '-color_trc', 'bt709', '-colorspace', 'bt709']
        run(['ffmpeg', '-v', 'error', '-y'] + common + ['-pass', '1', '-passlogfile', 'build/x264', '-an', '-f', 'mp4', os.devnull])
        run(['ffmpeg', '-v', 'error', '-y'] + common[:6] + ['-i', a.audio] + common[6:] +
            ['-pass', '2', '-passlogfile', 'build/x264', '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k',
             '-ar', '48000', '-movflags', '+faststart', out])
        problems = verify(out, N, DUR, 1080, 1920)
    if problems:
        print('VERIFY FAILED:\n  ' + '\n  '.join(problems))
        sys.exit(1)
    print(f'OK: {out} is exactly {N} frames / {DUR:.2f} s')


if __name__ == '__main__':
    main()
