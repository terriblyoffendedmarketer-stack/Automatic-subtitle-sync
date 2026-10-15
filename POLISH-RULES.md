# Subtitle wording rules (polish step)

Used when rewriting synced subtitle lines (polish.py export → edit → apply). Modelled on professional practice
(Netflix English Timed Text Style Guide + common subtitling conventions).

## Meaning
- Keep the meaning of the original line. Never add information, jokes or explanations that aren't there.
- If the line clearly mistranslates what is said (Whisper's translation of the actual audio is shown as a second
  opinion), fix it — but only when Whisper is coherent and the subtitle is clearly wrong. Whisper is noisy; when in
  doubt keep the subtitle's meaning.
- Lines that are double translations (e.g. Bengali → Portuguese → English) often read stiffly: rewrite for meaning.

## Sound like people talking
- Natural, idiomatic, modern English. Contractions where people would use them ("I don't know", not "Do not know").
- Fix grammar and articles ("Naidu is a Oldman now" → "Naidu's an old man now.").
- Keep the register: elders formal, friends casual, insults stay insults. Keep "sir", "brother", "dear" where they
  carry respect or affection in the original.
- Keep names and culturally specific words consistent (Velu, Naidu, pooja, lassi, Chettiar). Don't anglicise names.

## Fit the screen and the reading speed
- Max 2 lines, 42 characters each.
- Reading speed max 20 characters per second for the subtitle's duration: condense when over (drop filler,
  repetition, hesitations; "Well, you know, I think that..." → "I think...").
- One thought per subtitle where possible; two speakers as "-Line one" / "-Line two".

## Leave alone
- Song lyrics (♪ or italic): don't invent or rewrite lyrics beyond fixing obvious errors.
- Lines that are already good: keep them exactly. Polish is for jank, not for rewriting everything.

## Names must match the audio
- Subtitle files are sometimes made for a DUB (Nayakan's came from the Telugu dub). If the names differ from what's
  heard, use the names in the audio: build a names map (subtitle name → heard name) from evidence (Whisper / YouTube
  captions counts + context) and apply it with `polish.py names`. Uncertain names: decide line by line from what's heard.
