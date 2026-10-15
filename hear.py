#!/usr/bin/env python3
# hear.py — Step 3 of subsync v2: Whisper listens to the VOICE-ONLY track (music removed) and translates it to
# English with word timestamps → <work>/whisper.json  [{start, end, text, words:[{start,end,word}]}]
#
# Usage: ~/.dictation/.venv/bin/python -I hear.py <workdir> <lang: bn|ta|hi|...>
# Requires: mlx_whisper + local mlx-community/whisper-medium-mlx (the ~/.dictation venv, used read-only).
#
# Gotchas:
#   - condition_on_previous_text=False: otherwise Whisper loops on songs ("I'll go" x6, "Aam! Aam!" x100).
#   - On the mixed soundtrack Whisper put dialogue inside music (Nayakan 47 min); the voice-only track is the fix.
import json, os, sys
import mlx_whisper


def main():
    work, lang = sys.argv[1], sys.argv[2]
    out = os.path.join(work, "whisper.json")
    if os.path.exists(out):
        print("already heard"); return
    r = mlx_whisper.transcribe(os.path.join(work, "vocals16k.flac"), path_or_hf_repo="mlx-community/whisper-medium-mlx",
                               task="translate", language=lang, condition_on_previous_text=False, word_timestamps=True,
                               no_speech_threshold=0.5, compression_ratio_threshold=2.0)
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"].strip(),
             "words": [{"start": w["start"], "end": w["end"], "word": w["word"]} for w in s.get("words", [])]}
            for s in r["segments"] if s["text"].strip()]
    json.dump(segs, open(out, "w"))
    print(f"{len(segs)} segments")


if __name__ == "__main__":
    main()
