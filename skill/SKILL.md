---
name: subtitle-sync
description: "Fix, sync and polish subtitle files for the user's films: subtitles out of sync, drifting, early/late, wrong in some scenes, for a different cut (scenes cut, added or moved), made for a dub (wrong character names), badly or doubly translated, too long/fast to read, or missing (find English subs). Uses the user's own tool ~/Documents/Claude Code/Automatic-subtitle-sync (subsync v2). Triggers: subtitles, subs, srt, out of sync, sync subtitles, subtitle timing, subtitles early, subtitles late, subtitle drift, fix subtitles, English subtitles, find subtitles, subtitle translation, Jellyfin subtitles."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - WebSearch
---

# Subtitle sync & polish (subsync v2)

Tool: `~/Documents/Claude Code/Automatic-subtitle-sync/`. Read its `README.md` and `CLAUDE.md` first (problem tiers,
lessons). Run commands from that folder with its `.venv` (uv; never pip-install elsewhere). GitHub repo auto-pushes on
every commit (global post-commit hook), so a commit there is a publish.

## The user's rules (non-negotiable)
- Simple problems must stay fast (about a minute). Heavy tools only for real edge cases.
- YouTube auto-captions are only for POSITIONING. Their text never appears on screen.
- Subtitles must read like professional ones: natural English, 42 chars × 2 lines max, ≤20 chars/sec.
- Character names must match what's heard in the audio (subs made for a dub use the dub's names).
- Never say "synced" without a neutral check. alass once said "success" while 37 s off.
- Hindi films: no subtitles needed. Bengali, Tamil and other foreign films: English subtitles required.
- Never copy to the external drive unasked; the user moves files. Replaced files go to the Trash, never hard-deleted.

## Step 0: get subtitles
1. Real (manual) YouTube subs? `yt-dlp --list-subs <url>` (not the "automatic captions"). If present, download them
   with the film; they're normally in sync. Check with `judge.py` and you're done.
2. Otherwise OpenSubtitles legacy REST (no key): `curl -H 'X-User-Agent: TemporaryUserAgent' -A TemporaryUserAgent
   https://rest.opensubtitles.org/search/imdbid-<id>/sublanguageid-eng`, then pick by runtime closest to the film. Downloading
   a file needs the user's OK (filename, source, size). Strip ad lines (`clean_srt.py` in YouTube Quality Picker).
3. Scan the text: Portuguese/other-language leftovers, "�" chars, dub character names vs audio.

## Step 1: sync (pick the tier)
```bash
cd ~/Documents/"Claude Code"/Automatic-subtitle-sync
# everyday (offset, drift, minor cuts): ~1 min
.venv/bin/python subsync.py "<film>.mp4" "<subs>.srt" --yt "<youtube-url>" --lang <ta|bn|hi|..> --out "<film>.en.srt"
# hard films (songs, scenes cut/moved, dub subs, report says T4 or weak stretches): ~30-40 min
.venv/bin/python subsync.py "<film>.mp4" "<subs>.srt" --heavy --yt "<url>" --lang <xx> [--names names.json] --out ...
```
The runner diagnoses the tier (T0 ok / T1 offset / T2 drift / T3 different cut / T4 low confidence), applies the cheapest
fix, then fine timing → line-by-line exact timing → style rules. Read `work/<...>/subsync_report.json`: tier, blocks, dropped
lines (with text: check they're really missing scenes), weak 10-minute stretches, polish recommended.
No YouTube copy? `--heavy` without `--yt` (Whisper on the voice track becomes the only reference).

## Step 2: verify (always)
- `python3 judge.py work/<film>/speech.json old.srt new.srt`: start accuracy, coverage, orphans, per 10 min.
- Independent text check: a Whisper pass the new version did NOT use (`hear.py` on the voice track), then
  `sub_vs_whisper.py` (YouTube Quality Picker folder): lines within 1 s/2 s, per 10 min. Look for any chunk ≠ ~0 s.
- Spot-check 3-4 moments by listing SUB vs HEARD lines vs speech onsets. Fix outliers with the evidence.

## Step 3: polish wording (when the report recommends it, or the text is janky)
`polish.py names` (dub → heard names; build the map from Whisper/YouTube name counts + context, decide uncertain ones
per line) → `polish.py export` → rewrite only the janky lines per `POLISH-RULES.md` in `<batch>.done.tsv` (id TAB text,
" / " = line break) → `polish.py apply` → `fine.py`/`refine_lines.py` → `style.py`. Edits are keyed by original text, so
they survive re-alignment. Never invent song lyrics.

## Step 4: install
Put `<Film (Year)>.en.srt` next to `<Film (Year)>.mp4` in its own folder. Keep the previous version as `.en.srt.vN.bak`
(Jellyfin ignores .bak). Update the project CLAUDE.md with results.

## Lessons (don't re-learn these)
- Scenes can be MOVED, not just cut (Nayakan's YouTube copy vs the subtitles): global in-order matching drops real lines. align.py uses blocks.
- "Film is 10 min shorter" may be 4% PAL speed-up + a missing opening, not cuts (Jana Aranya). Small offset steps = drift → stretch.
- YouTube [Music] tags mark background score too. Never drop lines because they're "in a song" on that signal.
- Demucs on a whole film runs out of RAM on 16 GB: isolate.py uses 10-min chunks (~1 min each on the M2).
- Whisper on the mixed soundtrack misplaces lines inside music; run it on the Demucs voice track. Clean-voice timing beats YouTube's.
- Snapping to the nearest speech onset can pick the WRONG utterance when the reference is a few seconds off (Jana's taxi scene):
  refine_lines.py moves groups together and prefers clean-voice matches.
- Old OpenSubtitles files can be double translations (via Portuguese: "I burned my film" = "I blew it", "tributes" = taxes).
