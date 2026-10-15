# Automatic Subtitle Sync (v2)

Fixes downloaded subtitle files so every line appears exactly when it's spoken, even when the film copy is shifted,
runs at a different speed, has scenes cut or **moved**, or has songs that confuse simpler tools. Then makes the
subtitles read like professional ones.

## Problem → cheapest fix (the triage `subsync.py` runs)

| # | Problem | How it's detected | Fix | Time |
|---|---|---|---|---|
| 0 | YouTube already has real subtitles | yt-dlp lists manual subs | download them; quick sync check | ~1 min |
| 1 | Whole file early/late | all match points share one offset | shift every line | seconds |
| 2 | Gradual drift (25 vs 24 fps, "film looks shorter") | offset grows steadily | linear stretch | seconds |
| 3 | Scenes cut, added or **moved** | offset jumps between blocks | blocks placed independently; lines for missing scenes dropped | ~1 min |
| 4 | Songs / loud score | YouTube [Music] tags (fast) or voice/music separation (heavy) | lines flagged for review; never dropped on the fast signal alone | — |
| 5 | Long lines, bad breaks, too fast to read | style rules | `style.py`: 42×2, natural breaks, ≤20 cps, 5/6–7 s, 2-frame gaps | seconds |
| 6 | Janky / double-translated / foreign lines | quality scan (garbled chars, Portuguese words, grammar) | wording polish per POLISH-RULES.md (Claude) | 20–40 min, only when flagged |
| 7 | No YouTube captions, or too few match points | anchor density per 10 min | `--heavy`: Demucs voice isolation + Whisper (~1 min per 10 min of film each) | ~30 min |

**Where the timing reference comes from:** YouTube's automatic captions (original-language speech recognition + its
English auto-translation) are fetched in seconds and used **only to position** lines. Their text never reaches the
screen. Every word shown comes from the real subtitle file.

## Use
```bash
# everyday: subtitles a bit off (offset, drift, minor cuts), about a minute
.venv/bin/python subsync.py "<film>.mp4" "<subs>.srt" --yt "<youtube-url>" --lang ta
# hard films (songs, reordered/cut scenes, dub subtitles): ~30-40 min, measurably better
.venv/bin/python subsync.py "<film>.mp4" "<subs>.srt" --heavy --yt "<youtube-url>" --lang ta --names names.json
```
Then optionally the wording polish: `polish.py export` → Claude edits batches per POLISH-RULES.md → `polish.py apply` → `style.py`.
Writes `<film>.en.srt` next to the film and `work/yt-<film>/subsync_report.json`: tier, blocks, dropped lines (with
text), weak 10-minute stretches, whether polish is recommended.

Check a result against a neutral speech timeline: `python3 judge.py work/<film>/speech.json <subs.srt> ...`

## Claude skill
`skill/SKILL.md` (installed at `~/.claude/skills/subtitle-sync/`) walks any Claude session through the full workflow:
get subtitles → sync tier → verify → polish → install.

## Lessons built in (see each script's Gotchas)
- alass (v1) assumes scenes stay in order and can't drop lines: it crammed dialogue into songs and was 37 s off.
- One global in-order matching also failed: Nayakan's YouTube copy plays two scenes in the opposite order.
- Raw reference jitter looked like dozens of fake cuts; smoothing + "small jumps = drift" fixed it.
- "Shorter film" was mostly a 4% speed difference (25 vs 24 fps) plus a missing opening, not cut scenes.
- Demucs on a whole 2.5 h film runs out of memory on 16 GB: separate in 10-minute chunks.
