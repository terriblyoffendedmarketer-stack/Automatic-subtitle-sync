#!/usr/bin/env python3
# fine.py — Fine timing pass: after align.py has put every line in the right SCENE (coarse, from meaning), nudge
# blocks of lines by up to ±3 s so they sit exactly on the speech, then micro-snap each line start to a speech onset.
#
# Usage: python3 fine.py <in.srt> <speech.json> <out.srt>
#   speech.json = [[start, end], ...] speech spans (YouTube ASR word timings via autocap.py, or Silero VAD on the
#   Demucs voice track via speech.py)
# Requires: nothing (stdlib).
#
# Why: YouTube's English captions come in 3–7 s chunks, so coarse placement from them was ~1–2 s late in places
# (independent check: Nayakan within 1 s fell from 56% to 34% before this pass).
#
# Gotchas:
#   - Block shifts are smoothed (median of neighbouring blocks) so one noisy block can't jerk a line far away.
#   - Micro-snap only moves a start to an onset within 0.4 s, never past the previous line's end.
import json, re, statistics, sys

BLOCK, MAXSHIFT, STEP, MICRO = 8, 3.0, 0.1, 0.4


def parse(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if m:
            g = [int(x) for x in m.groups()]
            out.append([g[0]*3600+g[1]*60+g[2]+g[3]/1000, g[4]*3600+g[5]*60+g[6]+g[7]/1000, blk[m.end():].strip()])
    return sorted(out)


def main():
    cues = parse(sys.argv[1])
    sp = sorted(tuple(x) for x in json.load(open(sys.argv[2])))
    onsets = [s for s, _ in sp]
    import bisect

    def ov(a, b):
        i = bisect.bisect_left(onsets, a - 30)
        tot = 0.0
        while i < len(sp) and sp[i][0] < b:
            tot += max(0.0, min(b, sp[i][1]) - max(a, sp[i][0])); i += 1
        return tot

    def onset_hit(t):
        i = bisect.bisect_left(onsets, t - 0.3)
        return 1.0 if i < len(onsets) and onsets[i] <= t + 0.3 else 0.0

    shifts = []
    for b in range(0, len(cues), BLOCK):
        blk = cues[b:b + BLOCK]
        dur = sum(e - a for a, e, _ in blk) or 1
        best = (-1, 0.0)
        k = -MAXSHIFT
        while k <= MAXSHIFT + 1e-9:
            sc = sum(ov(a + k, e + k) for a, e, _ in blk) / dur + 0.5 * sum(onset_hit(a + k) for a, _, _ in blk) / len(blk)
            sc -= 0.02 * abs(k)                  # prefer small moves when scores tie
            if sc > best[0]:
                best = (sc, k)
            k += STEP
        shifts.append(best[1])
    sm = [statistics.median(shifts[max(0, i - 1):i + 2]) for i in range(len(shifts))]
    out = []
    for i, (a, e, t) in enumerate(cues):
        k = sm[i // BLOCK]
        a, e = a + k, e + k
        j = bisect.bisect_left(onsets, a - MICRO)
        near = [o for o in onsets[j:j + 6] if abs(o - a) <= MICRO]
        if near:
            o = min(near, key=lambda o: abs(o - a))
            if not out or o > out[-1][1] + 0.05:
                e += o - a; a = o
        out.append([a, e, t])
    fmt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t-int(t))*1000))%1000:03d}"
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        for n, (a, e, t) in enumerate(out, 1):
            f.write(f"{n}\n{fmt(a)} --> {fmt(e)}\n{t}\n\n")
    print(f"{sys.argv[3]}: block shifts median {statistics.median([abs(x) for x in sm]):.1f}s, "
          f"max {max(abs(x) for x in sm):.1f}s over {len(sm)} blocks")


if __name__ == "__main__":
    main()
