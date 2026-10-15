#!/usr/bin/env python3
# autocap.py — FAST reference for YouTube films: turns YouTube's automatic captions into the same inputs align.py
# uses, in seconds instead of ~35 min of Demucs + Whisper:
#   whisper.json  ← English auto-translation events (text + timing)       [what is said, in English]
#   speech.json   ← original-language ASR word timings, merged into spans  [when people speak]
#   songs.json    ← stretches dense with [Music]-type tags                 [song sections]
#
# Usage:
#   python3 autocap.py fetch <youtube-url> <lang: ta|bn|hi|...> <workdir>   (downloads <lang>-orig + en json3, Chrome cookies)
#   python3 autocap.py build <workdir>
# Requires: yt-dlp (fetch only). Stdlib otherwise.
#
# Gotchas:
#   - YouTube's English is a machine translation of its own ASR: rough, but align.py matches by meaning, so it works as a
#     reference. Don't use it as the subtitles themselves.
#   - Music tags are localised: [Music], [இசை] (Tamil), [সঙ্গীত]/[সংগীত] (Bengali), [संगीत] (Hindi), plus [Applause]-type tags.
#   - YouTube tags ANY music (background score too). Songs = 90 s+ of frequent tags with <5 s speech per 30 s; looser
#     rules flagged 33 "songs" in Nayakan, including a dialogue scene at 47 min.
#   - json3 events often come in pairs (a text event + an empty "line break" event). Skip events without text.
import json, os, re, subprocess, sys

TAG = re.compile(r"\[[^\]]{1,20}\]")
MUSIC = re.compile(r"\[(music|இசை|সঙ্গীত|সংগীত|संगीत|musique|música)\]", re.I)


def events(path):
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for e in d.get("events", []):
        segs = e.get("segs")
        if not segs:
            continue
        t0 = e["tStartMs"] / 1000
        text = "".join(s.get("utf8", "") for s in segs).strip()
        if not text or text == "\n":
            continue
        words = [(t0 + s.get("tOffsetMs", 0) / 1000, s.get("utf8", "").strip()) for s in segs if s.get("utf8", "").strip()]
        out.append({"start": t0, "end": t0 + e.get("dDurationMs", 0) / 1000, "text": text, "words": words})
    return out


def fetch(url, lang, work):
    os.makedirs(work, exist_ok=True)
    subprocess.run(["yt-dlp", "--cookies-from-browser", "chrome", "--sleep-requests", "2", "--no-warnings", "--skip-download",
                    "--write-auto-subs", "--sub-langs", f"{lang}-orig,en", "--sub-format", "json3",
                    "-o", os.path.join(work, "yt.%(ext)s"), url], check=True)


def build(work):
    fs = os.listdir(work)
    orig = next(os.path.join(work, f) for f in fs if f.endswith("-orig.json3"))
    en = os.path.join(work, "yt.en.json3")
    E, O = events(en), events(orig)
    # what is said (English); drop pure tag events
    ref = []
    for e in E:
        t = TAG.sub(" ", e["text"]); t = " ".join(t.split())
        if len(re.findall(r"[A-Za-z]+", t)) >= 1:
            ref.append({"start": e["start"], "end": max(e["end"], e["start"] + 0.5), "text": t, "words": []})
    # when people speak: each non-tag ASR word lasts until the next word (max 1.2 s); merge gaps < 0.4 s
    ws = sorted((t, w) for e in O for t, w in e["words"])
    spans = []
    for k, (t, w) in enumerate(ws):
        if TAG.fullmatch(w) or MUSIC.search(w):
            continue
        nxt = ws[k + 1][0] if k + 1 < len(ws) else t + 0.8
        e = min(nxt, t + 1.2)
        if spans and t - spans[-1][1] < 0.4:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([t, e])
    # songs: 30 s windows where music tags are frequent and speech is sparse
    mtimes = [t for e in O for t, w in e["words"] if MUSIC.search(w)] + [e["start"] for e in O if MUSIC.search(e["text"])]
    end = max(s[1] for s in spans) if spans else 0
    songs, t = [], 0.0
    while t < end:
        m = sum(1 for x in mtimes if t <= x < t + 30)
        sp = sum(max(0, min(t + 30, b) - max(t, a)) for a, b in spans)
        if m >= 3 and sp < 5:
            if songs and t - songs[-1][1] <= 15:
                songs[-1][1] = t + 30
            else:
                songs.append([t, t + 30])
        t += 15
    songs = [s for s in songs if s[1] - s[0] >= 90]  # real song sequences; YouTube tags background score as [Music] too
    json.dump(ref, open(os.path.join(work, "whisper.json"), "w"))
    json.dump(spans, open(os.path.join(work, "speech.json"), "w"))
    json.dump(songs, open(os.path.join(work, "songs.json"), "w"))
    print(f"{len(ref)} English reference lines, {len(spans)} speech spans ({sum(b-a for a,b in spans)/60:.0f} min), "
          f"{len(songs)} song sections: " + ", ".join(f"{int(a)//60}:{int(a)%60:02d}-{int(b)//60}:{int(b)%60:02d}" for a, b in songs))


if __name__ == "__main__":
    {"fetch": lambda: fetch(*sys.argv[2:5]), "build": lambda: build(sys.argv[2])}[sys.argv[1]]()
