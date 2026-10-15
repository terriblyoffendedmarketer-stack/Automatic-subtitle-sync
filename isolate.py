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
#   - Whole-film input gets SIGKILLed (out of memory on a 16 GB Mac after ~20 min on a 2.5 h film). Process 10-min
#     chunks and stitch the stems back together.
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
    video, work = sys.argv[1], os.path.abspath(sys.argv[2])  # absolute: ffmpeg concat resolves list entries relative to the list file
    os.makedirs(work, exist_ok=True)
    if os.path.exists(os.path.join(work, "vocals16k.flac")):
        print("already isolated"); return
    wav = os.path.join(work, "mix.wav")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-vn", "-ac", "2", "-ar", "44100", wav],
                   check=True)
    import torch, time
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav],
                               capture_output=True, text=True).stdout)
    CH = 600
    voc_parts, mus_parts = [], []
    for k in range(int(dur // CH) + 1):
        part = os.path.join(work, f"part{k:02d}.wav")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(k * CH), "-t", str(CH), "-i", wav, part],
                       check=True)
        t = time.time()
        subprocess.run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-d", dev,
                        "-o", os.path.join(work, "demucs"), part], check=True, capture_output=True)
        stem = os.path.join(work, "demucs", "htdemucs", f"part{k:02d}")
        voc_parts.append(os.path.join(stem, "vocals.wav")); mus_parts.append(os.path.join(stem, "no_vocals.wav"))
        os.remove(part)
        print(f"  chunk {k+1}/{int(dur // CH) + 1} separated in {time.time()-t:.0f}s", flush=True)

    def concat(parts, out, extra):
        lst = os.path.join(work, "list.txt")
        open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst] + extra + [out],
                       check=True)
    concat(voc_parts, os.path.join(work, "vocals16k.flac"), ["-ac", "1", "-ar", "16000"])
    concat(mus_parts, os.path.join(work, "music8k.wav"), ["-ac", "1", "-ar", "8000"])
    np.save(os.path.join(work, "music_env.npy"), env(os.path.join(work, "music8k.wav")))
    np.save(os.path.join(work, "vocal_env.npy"), env(os.path.join(work, "vocals16k.flac")))
    shutil.rmtree(os.path.join(work, "demucs")); os.remove(wav); os.remove(os.path.join(work, "music8k.wav"))
    os.remove(os.path.join(work, "list.txt"))
    print("isolated:", work)


if __name__ == "__main__":
    main()
