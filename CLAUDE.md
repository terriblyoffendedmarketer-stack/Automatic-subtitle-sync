# Automatic Subtitle Sync — v2 ("subsync v2")

**Status (2026-10-15):** v2 pipeline written; first run on Nayakan (1987, Tamil) + Jana Aranya (1976, Bengali; the YouTube
copy is ~10 min shorter than the subtitles' source). Voice isolation running. v1 = `sync_subs.py` (alass wrapper,
audio-only) failed on these films: dialogue crammed into songs, no way to drop lines for cut scenes.
Next: run speech → hear → align → style → polish on both films; verify; write README; push only with the user's OK.

## Roadmap
- [x] 1. v1: alass wrapper (`sync_subs.py`)
- [~] 2. v2 pipeline: isolate → speech → hear → align → style → polish
- [ ] 3. Verify on Nayakan + Jana Aranya (spot checks by ear-proxy: Whisper text + speech timing)
- [ ] 4. One-command runner + README; push to GitHub (user OK)

## Pipeline (run in order; <work> = work/<Film>)
| Step | Script | What it does |
|---|---|---|
| 1 | `isolate.py <video> <work>` | Demucs splits voices from music → vocals16k.flac + loudness envelopes |
| 2 | `speech.py <work>` | Silero VAD speech segments + song sections (continuous voice over loud music) |
| 3 | `hear.py <work> <lang>` | Whisper (medium, mlx) translates the voice-only track → whisper.json (run with ~/.dictation venv) |
| 4 | `align.py <subs.srt> <work> <out.srt>` | meaning-based in-order matching → anchors; drops lines for missing scenes; snaps to speech; keeps dialogue out of songs |
| 5 | `style.py <in.srt> <out.srt>` | 42 chars × 2 lines, natural breaks, 5/6–7 s, ≤20 cps, 2-frame gaps |
| 6 | `polish.py export/apply` | wording polish per POLISH-RULES.md (done by Claude/human), then style.py again |

## File map
- `sync_subs.py`: v1 (alass + technical fixes); kept for simple cases (same cut, no songs)
- `isolate.py`, `speech.py`, `hear.py`, `align.py`, `style.py`, `polish.py`: v2 steps (see table)
- `POLISH-RULES.md`: wording rules for the polish step
- `work/`: per-film intermediates (gitignored)

## Setup
- `uv venv .venv && uv pip install --python .venv/bin/python torch torchaudio demucs silero-vad sentence-transformers numpy soundfile`
- Whisper: `~/.dictation/.venv` (mlx_whisper + mlx-community/whisper-medium-mlx), used read-only.
- ffmpeg, alass-cli (Homebrew).

## Known issues / learnings
- alass audio-only: "success" but 37 s off in Nayakan; default split penalty too high (p=0.5 best when given a Whisper reference).
- Whisper on the mixed soundtrack misplaces dialogue inside music and loops on songs → v2 runs it on the voice-only track.
- OpenSubtitles Jana Aranya file was a double translation via Portuguese (59 untranslated lines) → polish step.
