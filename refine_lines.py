#!/usr/bin/env python3
# refine_lines.py — Final line-by-line timing pass: once every line is in the right scene (align.py + fine.py), move
# each line onto the exact moment it's said, when a reference line (YouTube captions / Whisper) within ±6 s clearly
# matches it. Then snap to the nearest speech onset. Lines without a clear match keep their place.
#
# Usage: .venv/bin/python refine_lines.py <in.srt> <workdir> <out.srt>     (<workdir>/whisper.json, speech.json)
# Requires: sentence-transformers (all-MiniLM-L6-v2), numpy (project venv).
#
# Why: fine.py nudges lines in groups of 8; when a group mixes right and slightly-off lines, the off ones stay
# off (Jana Aranya's last 10 min: "It's a lot." / "Please wait downstairs..." 2-4 s early while neighbours were right).
#
# Gotchas:
#   - Short lines ("I know.", "Fine.") match anything by meaning: they need a near-exact text match instead.
#   - A move is skipped if it would jump past a neighbouring line (keeps order, no overlaps).
#   - Keep the judge independent: don't feed the held-out Whisper pass into this step.
import json, os, re, sys, bisect
import numpy as np

WIN, SIM, SNAP = 6.0, 0.62, 0.5


def parse(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if m:
            g = [int(x) for x in m.groups()]
            out.append([g[0]*3600+g[1]*60+g[2]+g[3]/1000, g[4]*3600+g[5]*60+g[6]+g[7]/1000, blk[m.end():].strip()])
    return sorted(out)


def norm(t):
    return " ".join(re.findall(r"[a-z']+", re.sub(r"<[^>]+>", " ", t.lower())))


def main():
    src, work, out = sys.argv[1:4]
    cues = parse(src)
    W = json.load(open(os.path.join(work, "whisper.json")))
    W = [w for w in W if re.search(r"[A-Za-z]{2}", w["text"])]
    sp = sorted(tuple(x) for x in json.load(open(os.path.join(work, "speech.json"))))
    on = [s for s, _ in sp]
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    ec = model.encode([norm(c[2]) for c in cues], normalize_embeddings=True, batch_size=128)
    ew = model.encode([norm(w["text"]) for w in W], normalize_embeddings=True, batch_size=128)
    ws = [w["start"] for w in W]
    moved = 0
    for k, (a, e, t) in enumerate(cues):
        lo, hi = bisect.bisect_left(ws, a - WIN), bisect.bisect_right(ws, a + WIN)
        nt = norm(t); short = len(nt) < 12
        best = None
        for i in range(lo, hi):
            if short:
                s = 1.0 if nt and (nt == norm(W[i]["text"]) or norm(W[i]["text"]).startswith(nt)) else 0.0
            else:
                s = float(ec[k] @ ew[i])
            if s >= SIM and (best is None or s > best[0] or (s == best[0] and abs(ws[i] - a) < abs(best[1] - a))):
                best = (s, ws[i])
        if not best or abs(best[1] - a) < 0.4:
            continue
        na = best[1]
        j = bisect.bisect_left(on, na - SNAP)
        near = [o for o in on[j:j + 4] if abs(o - na) <= SNAP]
        if near:
            na = min(near, key=lambda o: abs(o - na))
        prev_end = cues[k - 1][1] if k else -1
        next_start = cues[k + 1][0] if k + 1 < len(cues) else 1e9
        dur = e - a
        if na <= prev_end - 0.3 or na + min(dur, 1.0) >= next_start + 0.3:
            continue   # would jump past a neighbour
        cues[k] = [na, na + dur, t]; moved += 1
    cues.sort()
    for k in range(len(cues) - 1):     # no overlaps after moves
        if cues[k][1] > cues[k + 1][0] - 0.084:
            cues[k][1] = max(cues[k][0] + 0.5, cues[k + 1][0] - 0.084)
    fmt = lambda x: f"{int(x//3600):02d}:{int(x%3600//60):02d}:{int(x%60):02d},{int(round((x-int(x))*1000))%1000:03d}"
    with open(out, "w", encoding="utf-8") as f:
        for n, (a, e, t) in enumerate(cues, 1):
            f.write(f"{n}\n{fmt(a)} --> {fmt(e)}\n{t}\n\n")
    print(f"{out}: moved {moved} of {len(cues)} lines onto their exact moment")


if __name__ == "__main__":
    main()
