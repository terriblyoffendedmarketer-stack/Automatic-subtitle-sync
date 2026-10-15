#!/usr/bin/env python3
# speech.py — Step 2 of subsync v2: on the voice-only track from isolate.py, finds
#   - speech segments (Silero VAD): exactly when someone is talking            → <work>/speech.json
#   - song sections: long stretches of continuous voice over loud music          → <work>/songs.json
#
# Usage: .venv/bin/python speech.py <workdir>
# Requires: silero-vad + torch, soundfile, numpy (project uv venv); isolate.py outputs in <workdir>.
#
# How songs are found (per 1 s, smoothed over 20 s): music stem loud (above the film's 65th percentile) AND the voice
# stem present most of the time (singing is continuous; dialogue has pauses). Runs of 40 s+ count as a song.
#
# Gotchas:
#   - Silero also fires on singing. That's fine: speech.json is used to snap timing, songs.json to keep dialogue out of songs.
import json, os, sys
import numpy as np
import soundfile as sf


def vad(flac):
    from silero_vad import load_silero_vad, get_speech_timestamps
    import torch
    model = load_silero_vad()
    wav, sr = sf.read(flac, dtype="float32")
    ts = get_speech_timestamps(torch.from_numpy(wav), model, sampling_rate=sr, threshold=0.5,
                               min_speech_duration_ms=200, min_silence_duration_ms=250, speech_pad_ms=60)
    return [(t["start"] / sr, t["end"] / sr) for t in ts]


def songs(work, speech):
    mus = np.load(os.path.join(work, "music_env.npy"))
    voc = np.load(os.path.join(work, "vocal_env.npy"))
    n = min(len(mus), len(voc)) // 10  # seconds
    mus_s = mus[: n * 10].reshape(n, 10).mean(1)
    voc_s = voc[: n * 10].reshape(n, 10).mean(1)
    loud_music = mus_s > np.percentile(mus_s, 65)
    voice_on = voc_s > np.percentile(voc_s, 40)
    k = np.ones(20) / 20
    score = np.convolve(loud_music & voice_on, k, mode="same")
    flag = score > 0.6
    out, i = [], 0
    while i < n:
        if flag[i]:
            j = i
            while j < n and flag[j]:
                j += 1
            if j - i >= 40:
                out.append((float(i), float(j)))
            i = j
        else:
            i += 1
    return out


def main():
    work = sys.argv[1]
    sp = vad(os.path.join(work, "vocals16k.flac"))
    json.dump(sp, open(os.path.join(work, "speech.json"), "w"))
    sg = songs(work, sp)
    json.dump(sg, open(os.path.join(work, "songs.json"), "w"))
    tot = sum(e - s for s, e in sp)
    print(f"{len(sp)} speech segments ({tot/60:.0f} min of speech); {len(sg)} song sections: " +
          ", ".join(f"{int(s)//60}:{int(s)%60:02d}-{int(e)//60}:{int(e)%60:02d}" for s, e in sg))


if __name__ == "__main__":
    main()
