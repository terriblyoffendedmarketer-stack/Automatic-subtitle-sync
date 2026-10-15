#!/usr/bin/env python3
# isolate.py — Step 1 of subsync v2: separates a film's soundtrack into VOICES and MUSIC with Demucs (htdemucs,
# two-stem), then writes what the later steps need and deletes the big stems:
#   <work>/vocals16k.flac   voice-only track, 16 kHz mono (for speech detection + Whisper)
#   <work>/music_env.npy    music-stem loudness per 100 ms (for finding song sections)
#   <work>/vocal_env.npy    voice-stem loudness per 100 ms
#
# Usage: .venv/bin/python isolate.py <video> <workdir>
# Requires: ffmpeg; demucs + torch (project uv venv). Uses Apple GPU (mps) when available.
#
# Gotchas:
#   - Demucs writes 44.1 kHz stereo WAVs (~1.5 GB per stem for a 2.5 h film): convert, then delete them.
#   - Feed it a WAV extracted by ffmpeg; letting demucs decode the mp4 itself is slower and less reliable.
import os, subprocess, sys, shutil
import numpy as np

FPS = 10


def env(path):
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "8000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = len(x) // 800
    return 20 * np.log10(np.sqrt((x[: n * 800].reshape(n, 800) ** 2).mean(1)) + 1e-9).astype(np.float32)


def main():
    video, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)
    if os.path.exists(os.path.join(work, "vocals16k.flac")):
        print("already isolated"); return
    wav = os.path.join(work, "mix.wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-vn", "-ac", "2", "-ar", "44100", wav],
                   check=True)
    import torch
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-d", dev,
                    "-o", os.path.join(work, "demucs"), wav], check=True)
    stem = os.path.join(work, "demucs", "htdemucs", "mix")
    voc, mus = os.path.join(stem, "vocals.wav"), os.path.join(stem, "no_vocals.wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", voc, "-ac", "1", "-ar", "16000",
                    os.path.join(work, "vocals16k.flac")], check=True)
    np.save(os.path.join(work, "music_env.npy"), env(mus))
    np.save(os.path.join(work, "vocal_env.npy"), env(voc))
    shutil.rmtree(os.path.join(work, "demucs")); os.remove(wav)
    print("isolated:", work)


if __name__ == "__main__":
    main()
