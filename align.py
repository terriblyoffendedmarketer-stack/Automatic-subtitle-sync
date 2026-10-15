#!/usr/bin/env python3
# align.py — Step 4 of subsync v2: places every subtitle line on the film's real dialogue, coping with copies whose
# scenes are SHIFTED, CUT, or MOVED (reordered) compared with the version the subtitles were made for.
#
#   1. MATCH BY MEANING: each subtitle line is compared with the reference (YouTube auto-translation or Whisper, i.e.
#      what is said and when) within ±25 min, using a sentence-similarity model + rare-word overlap. Best match per line.
#   2. BLOCKS: matches are smoothed in subtitle order; runs with a stable offset form BLOCKS that move together.
#      Blocks may land in any order (Nayakan's YouTube copy plays two scenes in the opposite order to the subtitles).
#   3. LINES BETWEEN BLOCKS go with the block before or after: the split point is chosen where they land best on speech.
#   4. COLLISIONS: a line landing on film time already held by another block's anchored lines is dropped (its scene
#      isn't in this copy). Small offset changes between blocks (<15 s) are drift (e.g. 25 vs 24 fps) and get stretched.
#      Lines in song sections are only flagged, never dropped (fast song detection mistakes dialogue under music for songs).
#   5. SNAP starts/ends to speech boundaries.
#
# Usage: .venv/bin/python align.py <subs.srt> <workdir> <out.srt>
# Requires: sentence-transformers (all-MiniLM-L6-v2, auto-downloaded once ~90 MB), numpy (project venv);
#           <workdir>/whisper.json, speech.json, songs.json (autocap.py, or hear.py + speech.py).
# Writes: <out.srt> + <workdir>/align_report.json (anchors, blocks, drops, splits).
#
# Gotchas:
#   - v1 (alass) and the first v2 (one global in-order DP) both assume scenes stay in order. Nayakan broke that: the
#     DP kept one of two swapped scenes and dropped 63 real lines of the other. Hence blocks, not global order.
#   - Without an order constraint false matches are likelier: stricter similarity (0.5), smoothing in subtitle order,
#     and blocks need 3+ agreeing anchors.
#   - Reference timing jitters by seconds (YouTube caption chunks are 3-7 s): block offsets use the median of the block.
import json, math, os, re, statistics, sys
import numpy as np

SIM_MIN = 0.50       # combined similarity for a match (stricter than the old in-order DP's 0.42)
BAND = 1500          # a line may move up to 25 min
BLOCK_TOL = 3.0      # offset change (s) that starts a new block
MIN_BLOCK = 3        # anchors needed for a block to count
SNAP = 0.7
DRIFT_MAX = 15.0     # offset change between neighbouring blocks below this = gradual drift → stretch, never drop
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
    return sum(max(0.0, min(a1, e) - max(a0, s)) for s, e in segs if s < a1 and e > a0)


def in_song(t0, t1, songs):
    return any(s - 1 < t0 and t1 < e + 1 for s, e in songs)


def main():
    subs_p, work, out_p = sys.argv[1:4]
    cues = parse_srt(subs_p)
    W = json.load(open(os.path.join(work, "whisper.json")))
    speech = sorted(tuple(x) for x in json.load(open(os.path.join(work, "speech.json"))))
    songs = [tuple(x) for x in json.load(open(os.path.join(work, "songs.json")))]
    film_end = max(e for _, e in speech) + 30

    def junk(t):
        tok = re.findall(r"[a-z]+", t.lower())
        return not tok or (len(tok) > 2 and len(set(tok)) <= 2)
    W = [w for w in W if not junk(w["text"])]

    # ---- 1. similarity + best match per line
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
    cw = [words(t) for t in ct]; ww = [words(t) for t in wt]
    ws = np.array([w["start"] for w in W])
    E1, E2 = ec @ ew.T, ec @ ew2.T
    matches = []  # (cue j, offset, sim)
    for j, c in enumerate(cues):
        if len(ct[j]) < 6:
            continue  # "Baba!", "Hey!" match anything
        lo, hi = np.searchsorted(ws, c["start"] - BAND), np.searchsorted(ws, c["start"] + BAND)
        best = None
        for i in range(lo, hi):
            lex = sum(idf[x] for x in cw[j] & ww[i])
            s = 0.75 * max(E1[j, i], E2[j, i]) + 0.25 * min(1.0, lex / 8.0)
            if best is None or s > best[0]:
                best = (float(s), i)
        if best and best[0] >= SIM_MIN:
            matches.append((j, W[best[1]]["start"] - c["start"], best[0]))

    # ---- 2. blocks: smooth offsets in subtitle order, then split where the offset jumps
    offs = [o for _, o, _ in matches]
    sm = [statistics.median(offs[max(0, k - 4):k + 5]) for k in range(len(offs))]
    kept = [(j, o, s) for (j, o, s), m in zip(matches, sm) if abs(o - m) <= BLOCK_TOL]
    blocks = []
    for j, o, s in kept:
        if blocks and abs(o - statistics.median(blocks[-1]["offs"][-5:])) <= BLOCK_TOL:
            blocks[-1]["js"].append(j); blocks[-1]["offs"].append(o)
        else:
            blocks.append({"js": [j], "offs": [o]})
    blocks = [b for b in blocks if len(b["js"]) >= MIN_BLOCK]
    # merge neighbouring blocks with the same offset (split by a rejected stray)
    merged = []
    for b in blocks:
        if merged and abs(statistics.median(b["offs"]) - statistics.median(merged[-1]["offs"])) <= BLOCK_TOL:
            merged[-1]["js"] += b["js"]; merged[-1]["offs"] += b["offs"]
        else:
            merged.append(b)
    blocks = merged
    for b in blocks:
        b["first"], b["last"] = b["js"][0], b["js"][-1]
        b["anch"] = dict(zip(b["js"], b["offs"]))

    def off_in_block(b, j):
        """local offset: median of the block's anchors nearest to line j (follows slow drift inside a block)"""
        near = sorted(b["anch"].items(), key=lambda kv: abs(kv[0] - j))[:7]
        return statistics.median(o for _, o in near)

    # ---- 3. assign every line to a block
    place, owner, splits = {}, {}, []
    for bi, b in enumerate(blocks):
        for j in range(b["first"], b["last"] + 1):
            place[j] = cues[j]["start"] + off_in_block(b, j); owner[j] = bi
    bspan = [(min(place[j] for j in b["js"]), max(place[j] for j in b["js"])) for b in blocks]

    def cover(t0, dur, mine=()):
        if t0 < 0 or t0 + dur > film_end:
            return -1.0
        if any(bi not in mine and s0 - 1 <= t0 <= s1 + 1 for bi, (s0, s1) in enumerate(bspan)):
            return -2.0                                  # would sit on top of another scene
        return overlap(t0, t0 + dur, speech) / max(dur, 0.3)

    for bi in range(len(blocks) - 1):
        A, B = blocks[bi], blocks[bi + 1]
        inner = list(range(A["last"] + 1, B["first"]))
        if not inner:
            continue
        oA, oB = off_in_block(A, A["last"]), off_in_block(B, B["first"])
        if abs(oB - oA) <= DRIFT_MAX:                     # gradual drift (e.g. 25 vs 24 fps): stretch smoothly
            sa, sb = cues[A["last"]]["start"], cues[B["first"]]["start"]
            for x in inner:
                r = (cues[x]["start"] - sa) / max(sb - sa, 1e-6)
                place[x] = cues[x]["start"] + oA + r * (oB - oA); owner[x] = bi
            continue
        best = None
        for k in range(len(inner) + 1):
            sc = sum(cover(cues[x]["start"] + oA, cues[x]["end"] - cues[x]["start"], (bi, bi + 1)) for x in inner[:k]) + \
                 sum(cover(cues[x]["start"] + oB, cues[x]["end"] - cues[x]["start"], (bi, bi + 1)) for x in inner[k:])
            if best is None or sc > best[0]:
                best = (sc, k)
        k = best[1]
        for x in inner[:k]:
            place[x] = cues[x]["start"] + oA; owner[x] = bi
        for x in inner[k:]:
            place[x] = cues[x]["start"] + oB; owner[x] = bi + 1
        if abs(oA - oB) > BLOCK_TOL:
            splits.append({"at_sub": round(cues[A["last"]]["start"]), "jump_s": round(oB - oA, 1)})
    if blocks:
        for j in range(0, blocks[0]["first"]):
            place[j] = cues[j]["start"] + off_in_block(blocks[0], blocks[0]["first"]); owner[j] = 0
        for j in range(blocks[-1]["last"] + 1, len(cues)):
            place[j] = cues[j]["start"] + off_in_block(blocks[-1], blocks[-1]["last"]); owner[j] = len(blocks) - 1

    # ---- 4. collisions: film time covered by a block's anchored span belongs to that block
    anchored = {j for b in blocks for j in b["js"]}
    spans = []
    for bi, b in enumerate(blocks):
        ts = sorted(place[j] for j in b["js"])
        spans.append((ts[0], ts[-1], bi))
    dropped = []
    for j, t in list(place.items()):
        if j in anchored:
            continue
        for s0, s1, bi in spans:
            if bi != owner[j] and s0 <= t <= s1:
                dropped.append(j); del place[j]; break

    # ---- 5. write, snapping to speech; keep unmatched dialogue out of songs
    out, in_songs = [], 0
    for j, c in enumerate(cues):
        if j not in place:
            continue
        dur = c["end"] - c["start"]; t0 = place[j]
        if t0 < 0 or t0 > film_end:
            dropped.append(j); continue
        ons = [s for s, e in speech if abs(s - t0) <= SNAP]
        if ons:
            t0 = min(ons, key=lambda s: abs(s - t0))
        t1 = t0 + dur
        offs_ = [e for s, e in speech if abs(e - t1) <= SNAP and e > t0 + 0.5]
        if offs_:
            t1 = min(offs_, key=lambda e: abs(e - t1)) + 0.15
        if in_song(t0, t1, songs):
            in_songs += 1   # flagged for review only: the fast song detector mistook dialogue-under-music for songs
                            # (Nayakan 26-28 min) and dropped real lines when this dropped them
        out.append({"start": t0, "end": t1, "text": c["text"]})
    out.sort(key=lambda c: c["start"])
    fmt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t-int(t))*1000))%1000:03d}"
    with open(out_p, "w", encoding="utf-8") as f:
        for n, c in enumerate(out, 1):
            f.write(f"{n}\n{fmt(c['start'])} --> {fmt(c['end'])}\n{c['text']}\n\n")
    blk_rep = [{"sub": f"{int(cues[b['first']]['start'])//60}-{int(cues[b['last']]['start'])//60}min",
                "film": f"{int(place.get(b['first'], 0))//60}-{int(place.get(b['last'], 0))//60}min",
                "offset_s": round(statistics.median(b["offs"]), 1), "anchors": len(b["js"])} for b in blocks]
    anchors_list = sorted([[round(cues[j]["start"], 2), round(cues[j]["start"] + b["anch"][j], 2)]
                           for b in blocks for j in b["js"]], key=lambda x: x[1])
    rep = {"cues_in": len(cues), "cues_out": len(out), "matches": len(matches), "anchors": len(anchored),
           "blocks": blk_rep, "dropped": len(set(dropped)),
           "dropped_examples": [clean(cues[j]["text"])[:60] for j in sorted(set(dropped))[:15]],
           "splits": splits, "song_sections": songs, "lines_in_songs_kept": in_songs, "anchors_list": anchors_list}
    json.dump(rep, open(os.path.join(work, "align_report.json"), "w"), indent=1)
    print(json.dumps({k: rep[k] for k in ("cues_in", "cues_out", "matches", "anchors", "dropped")}))
    for b in blk_rep:
        print("  block", b)


if __name__ == "__main__":
    main()
