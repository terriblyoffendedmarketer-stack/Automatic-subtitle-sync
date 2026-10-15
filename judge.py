#!/usr/bin/env python3
# judge.py — Neutral sync score for any .srt against a speech timeline it was NOT built from (use the Silero VAD on the
# Demucs voice track, work/<film>/speech.json, to judge versions built from YouTube captions or Whisper).
#   start accuracy : % of lines starting within 0.5 s of someone starting to speak
#   coverage       : % of subtitle display time that overlaps actual speech
#   orphans        : lines with < 15% speech under them (on screen while nobody talks = misplaced)
# Reported overall and per 10 min, so bad stretches stand out.
#
# Usage: python3 judge.py <speech.json> <subs1.srt> [<subs2.srt> ...]
# Requires: nothing (stdlib).
import bisect, json, re, sys


def parse(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if m:
            g = [int(x) for x in m.groups()]
            out.append((g[0]*3600+g[1]*60+g[2]+g[3]/1000, g[4]*3600+g[5]*60+g[6]+g[7]/1000))
    return sorted(out)


def main():
    sp = sorted(tuple(x) for x in json.load(open(sys.argv[1])))
    on = [s for s, _ in sp]

    def ov(a, b):
        i = max(0, bisect.bisect_left(on, a) - 1); tot = 0.0
        while i < len(sp) and sp[i][0] < b:
            tot += max(0.0, min(b, sp[i][1]) - max(a, sp[i][0])); i += 1
        return tot

    for p in sys.argv[2:]:
        cues = parse(p)
        rows = []
        for a, b in cues:
            i = bisect.bisect_left(on, a - 0.5)
            hit = i < len(on) and on[i] <= a + 0.5
            c = ov(a, b) / max(b - a, 0.1)
            rows.append((a, hit, c, b - a))
        n = len(rows)
        acc = sum(r[1] for r in rows) / n
        cov = sum(r[2] * r[3] for r in rows) / sum(r[3] for r in rows)
        orph = sum(r[2] < 0.15 for r in rows)
        print(f"### {p.rsplit('/', 1)[-1]}: {n} lines | start accuracy {acc*100:.0f}% | coverage {cov*100:.0f}% | orphans {orph} ({orph*100/n:.0f}%)")
        ch = {}
        for a, hit, c, d in rows:
            ch.setdefault(int(a // 600), []).append((hit, c < 0.15))
        print("  per 10 min (start acc% / orphans): " + "  ".join(
            f"{k*10}m:{sum(h for h,_ in v)*100//len(v)}/{sum(o for _,o in v)}" for k, v in sorted(ch.items())))


if __name__ == "__main__":
    main()
