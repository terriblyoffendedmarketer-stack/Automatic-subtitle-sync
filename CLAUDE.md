# Automatic Subtitle Sync — v2 ("subsync v2")

**Status (2026-10-15):** v2 works and has been used on Nayakan (1987, Tamil, scenes reordered vs the subtitles, which were
made for the Telugu dub) and Jana Aranya (1976, Bengali, 4% faster PAL copy + missing opening, subtitles routed via
Portuguese). Both installed in ~/Movies/YouTube Films (old versions kept as .en.srt.v1.bak). Neutral judge (clean-voice
speech): Nayakan 52% of lines start on speech / 70% coverage (v1 alass 25%/46%); Jana Aranya 64% / 76% (raw download 26%/46%).
Next: run more films to harden; push to GitHub (user OK needed).

## Roadmap
- [x] 1. v1: alass wrapper (`sync_subs.py`)
- [x] 2. v2 pipeline: isolate → speech → hear → align (blocks) → fine → style → names → polish
- [x] 3. Verified on Nayakan + Jana Aranya (neutral judge + independent Whisper text check + spot checks)
- [x] 4. One-command runner (`subsync.py`, fast + heavy) + README with problem tiers
- [ ] 5. Push to GitHub (user OK); more test films

## Pipeline (run in order; <work> = work/<Film>)
| Step | Script | What it does |
|---|---|---|
| 1 | `isolate.py <video> <work>` | Demucs splits voices from music → vocals16k.flac + loudness envelopes |
| 2 | `speech.py <work>` | Silero VAD speech segments + song sections (continuous voice over loud music) |
| 3 | `hear.py <work> <lang>` | Whisper (medium, mlx) translates the voice-only track → whisper.json (run with ~/.dictation venv) |
| 3b | `autocap.py fetch/build` | FAST reference: YouTube auto-captions (original-language ASR + English auto-translation), positioning only |
| 4 | `align.py <subs.srt> <work> <out.srt>` | meaning match → BLOCKS (can move out of order); drift stretched; missing-scene lines dropped |
| 4b | `fine.py <in> <speech.json> <out>` | ±3 s block nudges + onset micro-snap onto speech |
| 5 | `style.py <in.srt> <out.srt>` | 42 chars × 2 lines, natural breaks, 5/6–7 s, ≤20 cps, 2-frame gaps |
| 6 | `polish.py names/export/apply` | dub names → audio names; wording polish per POLISH-RULES.md (Claude), keyed by text |
| ✓ | `judge.py <speech.json> <srt...>` | neutral sync score vs clean-voice speech; `subsync.py` = one-command triage runner |

## File map
- `sync_subs.py`: v1 (alass + technical fixes); kept for simple cases (same cut, no songs)
- `isolate.py`, `speech.py`, `hear.py`, `align.py`, `style.py`, `polish.py`: v2 steps (see table)
- `POLISH-RULES.md`: wording rules for the polish step (incl. names-must-match-audio)
- `subsync.py`: one command (diagnose → cheapest fix → fine → style); `--heavy` for hard films, `--names` for dubs
- `autocap.py`, `fine.py`, `judge.py`: fast reference, fine timing, neutral judge
- `README.md`: problem → fix tiers, usage, lessons
- `work/`: per-film intermediates (gitignored)

## Setup
- `uv venv .venv && uv pip install --python .venv/bin/python torch torchaudio demucs silero-vad sentence-transformers numpy soundfile`
- Whisper: `~/.dictation/.venv` (mlx_whisper + mlx-community/whisper-medium-mlx), used read-only.
- ffmpeg, alass-cli (Homebrew).

## Known issues / learnings
- alass audio-only: "success" but 37 s off in Nayakan; default split penalty too high (p=0.5 best when given a Whisper reference).
- Whisper on the mixed soundtrack misplaces dialogue inside music and loops on songs → v2 runs it on the voice-only track.
- OpenSubtitles Jana Aranya file was a double translation via Portuguese (untranslated lines AND literal idioms:
  "I burned my film" = I blew it, "tributes" = taxes) → polish step.
- Global in-order matching dropped 63 real lines when scenes were reordered → blocks. Raw jitter = fake cuts → smoothing.
- YouTube [Music] tags mistake dialogue-under-music for songs → never drop lines on that signal.
- Demucs whole-film = out of memory on 16 GB → 10-min chunks (~1 min per chunk on M2).
- Fast path (YouTube only) fine timing was worse than v1-Whisper; heavy (clean voice + merged refs) won on both films.
