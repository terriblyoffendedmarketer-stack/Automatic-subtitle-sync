#!/usr/bin/env python3
# align.py — Step 4 of subsync v2: places every subtitle line on the film's real dialogue.
#
#   1. MATCH BY MEANING, IN ORDER: each subtitle line is compared with Whisper's English lines (heard on the
#      voice-only track) using a sentence-similarity model + rare-word overlap. A dynamic-programming pass finds the
#      best in-order matching; lines can stay unmatched. Confident matches become ANCHORS (outliers rejected).
#   2. BETWEEN ANCHORS: if the subtitle file has more time between two anchors than the film does, a scene is missing
#      from this copy, so the lines for it are DROPPED (not crammed in). The cut point is chosen where the remaining
#      lines land best on detected speech. If the film has more time, the lines split into two shifted groups.
#   3. SNAP to the voice-activity boundaries (speech.json) and keep unmatched dialogue out of song sections.
#
# Usage: .venv/bin/python align.py <subs.srt> <workdir> <out.srt>
# Requires: sentence-transformers (all-MiniLM-L6-v2, auto-downloaded once ~90 MB), numpy (project venv);
#           <workdir>/whisper.json, speech.json, songs.json from hear.py / speech.py.
# Writes: <out.srt> and <workdir>/align_report.json (anchors, drops, splits, lines in songs).
#
# Gotchas:
#   - alass (timing-pattern only) crammed dialogue into songs and could not drop lines for scenes cut from a
#     shorter copy: that's why this matches by MEANING and allows drops.
#   - A matched Whisper segment can hold several subtitle lines; anchors use segment start, and snapping fixes the rest.
#   - Anchor outliers: kept only if within 2.5 s of the median offset of the 4 anchors before OR the 4 after
#     (a real cut is a step in offset, so a symmetric window would wrongly reject anchors next to the step).
import json, math, os, re, statistics, sys
import numpy as np

SIM_MIN = 0.42       # combined similarity needed to count as a match
DROP_COST = 0.35     # discourages dropping lines unless the timing needs it
STEP = 2.0           # seconds of mismatch between anchors before treating it as a cut/insert
SNAP = 0.7           # snap start/end to speech boundaries within this many seconds
STOP = set("that this with have from they what your will there their about would could should been were when then them "
           "just know like here come want only more some time where which because these those very also into than does "
           "dont didnt cant wont youre thats".split())


def parse_srt(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        text = blk[m.end():].strip().replace("\t", "\n")
        out.append({"start": g[0]*3600+g[1]*60+g[2]+g[3]/1000, "end": g[4]*3600+g[5]*60+g[6]+g[7]/1000, "text": text})
    return sorted(out, key=lambda c: c["start"])


def clean(t):
    t = re.sub(r"<[^>]+>|\{[^}]+\}|♪|^\s*-\s*", " ", t, flags=re.M)
    return " ".join(t.split())


def words(t):
    return {w for w in re.findall(r"[a-z]+", t.lower().replace("'", "")) if len(w) >= 4 and w not in STOP}


def overlap(a0, a1, segs):
    return sum(max(0.0, min(a1, e) - max(a0, s)) for s, e in segs)


def in_song(t0, t1, songs):
    return any(s - 1 < t0 and t1 < e + 1 for s, e in songs)


def main():
    subs_p, work, out_p = sys.argv[1:4]
    cues = parse_srt(subs_p)
    W = json.load(open(os.path.join(work, "whisper.json")))
    speech = [tuple(x) for x in json.load(open(os.path.join(work, "speech.json")))]
    songs = [tuple(x) for x in json.load(open(os.path.join(work, "songs.json")))]
    film_end = max(e for _, e in speech) + 30

    # drop Whisper junk: repeated-token loops
    def junk(t):
        tok = re.findall(r"[a-z]+", t.lower())
        return not tok or (len(tok) > 2 and len(set(tok)) <= 2)
    W = [w for w in W if not junk(w["text"])]

    # ---- similarity: embeddings + rare-word overlap
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    ct = [clean(c["text"]) for c in cues]
    wt = [w["text"] for w in W]
    wt2 = [W[i]["text"] + " " + W[i + 1]["text"] if i + 1 < len(W) else W[i]["text"] for i in range(len(W))]
    ec = model.encode(ct, normalize_embeddings=True, batch_size=128)
    ew = model.encode(wt, normalize_embeddings=True, batch_size=128)
    ew2 = model.encode(wt2, normalize_embeddings=True, batch_size=128)
    df = {}
    for t in ct + wt:
        for x in words(t):
            df[x] = df.get(x, 0) + 1
    N = len(ct) + len(wt)
    idf = {x: math.log(N / c) for x, c in df.items()}
    cw = [words(t) for t in ct]
    ww = [words(t) for t in wt]
    ws = np.array([w["start"] for w in W])
    cs = np.array([c["start"] for c in cues])

    # ---- in-order matching (DP), banded: a line can't move more than 15 min
    J, I = len(cues), len(W)
    BAND = 900
    NEG = -1e9
    D = np.full((J + 1, I + 1), 0.0)
    P = np.zeros((J + 1, I + 1), dtype=np.int8)  # 1 match, 2 skip cue, 3 skip whisper
    simcache = {}
    for j in range(1, J + 1):
        lo = np.searchsorted(ws, cs[j - 1] - BAND); hi = np.searchsorted(ws, cs[j - 1] + BAND)
        rowc = ec[j - 1]
        cand = range(max(1, lo + 1), min(I, hi) + 1)
        sims = {}
        for i in cand:
            e = max(float(rowc @ ew[i - 1]), float(rowc @ ew2[i - 1]))
            lex = sum(idf[x] for x in cw[j - 1] & ww[i - 1])
            sims[i] = 0.75 * e + 0.25 * min(1.0, lex / 8.0)
        simcache[j] = sims
        for i in range(1, I + 1):
            best, ptr = D[j - 1, i], 2
            if D[j, i - 1] > best:
                best, ptr = D[j, i - 1], 3
            s = sims.get(i)
            if s is not None and s >= SIM_MIN and D[j - 1, i - 1] + (s - SIM_MIN) > best:
                best, ptr = D[j - 1, i - 1] + (s - SIM_MIN), 1
            D[j, i], P[j, i] = best, ptr
    pairs, j, i = [], J, I
    while j > 0 and i > 0:
        if P[j, i] == 1:
            pairs.append((j - 1, i - 1, simcache[j][i])); j -= 1; i -= 1
        elif P[j, i] == 2:
            j -= 1
        else:
            i -= 1
    pairs.reverse()

    # ---- anchors with asymmetric outlier rejection
    offs = [W[i]["start"] - cues[j]["start"] for j, i, _ in pairs]
    anchors = []
    for k, (j, i, s) in enumerate(pairs):
        before = offs[max(0, k - 4):k]; after = offs[k + 1:k + 5]
        ok = any(len(g) >= 2 and abs(offs[k] - statistics.median(g)) <= 2.5 for g in (before, after))
        if ok:
            anchors.append((j, W[i]["start"]))

    # ---- place every cue
    place = {j: t for j, t in anchors}          # cue index -> new start
    dropped, splits = [], []

    def cover(t0, dur):
        if t0 < 0 or t0 + dur > film_end:
            return -1.0
        return overlap(t0, t0 + dur, speech) / max(dur, 0.3) - (0.5 if in_song(t0, t0 + dur, songs) else 0)

    for (ja, fa), (jb, fb) in zip(anchors, anchors[1:]):
        inner = list(range(ja + 1, jb))
        if not inner:
            continue
        sa, sb = cues[ja]["start"], cues[jb]["start"]
        offA, offB = fa - sa, fb - sb
        d = (sb - sa) - (fb - fa)
        if abs(d) <= STEP:
            for j in inner:  # linear interpolation
                r = (cues[j]["start"] - sa) / max(sb - sa, 1e-6)
                place[j] = fa + r * (fb - fa)
            continue
        best = None
        m = len(inner)
        for k in range(m + 1):
            for k2 in range(k, m + 1 if d > 0 else k + 1):   # drops only when the subtitle side is longer
                A, Dr, B = inner[:k], inner[k:k2], inner[k2:]
                if A and B and cues[A[-1]]["end"] + offA > cues[B[0]]["start"] + offB:
                    continue
                if A and cues[A[-1]]["end"] + offA > fb or B and cues[B[0]]["start"] + offB < fa:
                    continue
                sc = sum(cover(cues[x]["start"] + offA, cues[x]["end"] - cues[x]["start"]) for x in A) + \
                     sum(cover(cues[x]["start"] + offB, cues[x]["end"] - cues[x]["start"]) for x in B) - DROP_COST * len(Dr)
                if best is None or sc > best[0]:
                    best = (sc, k, k2)
        if best is None:
            dropped += inner; continue
        _, k, k2 = best
        for x in inner[:k]:
            place[x] = cues[x]["start"] + offA
        for x in inner[k2:]:
            place[x] = cues[x]["start"] + offB
        dropped += inner[k:k2]
        splits.append({"at": round(fa), "sub_minus_film_s": round(d, 1), "dropped": k2 - k})
    if anchors:
        j0, f0 = anchors[0]; jn, fn = anchors[-1]
        for j in range(0, j0):
            place[j] = cues[j]["start"] + (f0 - cues[j0]["start"])
        for j in range(jn + 1, J):
            place[j] = cues[j]["start"] + (fn - cues[jn]["start"])

    anchor_set = {j for j, _ in anchors}
    out, in_songs = [], 0
    for j, c in enumerate(cues):
        if j in dropped or j not in place:
            continue
        dur = c["end"] - c["start"]
        t0 = place[j]
        if t0 < 0 or t0 > film_end:
            dropped.append(j); continue
        # snap start/end to speech boundaries
        ons = [s for s, e in speech if abs(s - t0) <= SNAP]
        if ons:
            t0 = min(ons, key=lambda s: abs(s - t0))
        t1 = t0 + dur
        offs_ = [e for s, e in speech if abs(e - t1) <= SNAP and e > t0 + 0.5]
        if offs_:
            t1 = min(offs_, key=lambda e: abs(e - t1)) + 0.15
        if in_song(t0, t1, songs):
            in_songs += 1
            if j not in anchor_set and "♪" not in c["text"] and "<i>" not in c["text"]:
                dropped.append(j); continue   # unmatched dialogue placed inside a song = misplacement
        out.append({"start": t0, "end": t1, "text": c["text"], "anchor": j in anchor_set})

    out.sort(key=lambda c: c["start"])
    with open(out_p, "w", encoding="utf-8") as f:
        for n, c in enumerate(out, 1):
            fmt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t-int(t))*1000))%1000:03d}"
            f.write(f"{n}\n{fmt(c['start'])} --> {fmt(c['end'])}\n{c['text']}\n\n")
    rep = {"cues_in": J, "cues_out": len(out), "matches": len(pairs), "anchors": len(anchors),
           "dropped": len(set(dropped)), "dropped_examples": [clean(cues[j]["text"])[:60] for j in sorted(set(dropped))[:15]],
           "splits": splits, "song_sections": songs, "lines_in_songs_kept": in_songs}
    json.dump(rep, open(os.path.join(work, "align_report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("dropped_examples", "song_sections")}, indent=1))


if __name__ == "__main__":
    main()
