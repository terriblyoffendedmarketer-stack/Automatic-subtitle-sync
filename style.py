#!/usr/bin/env python3
# style.py — Step 5 of subsync v2: makes subtitles follow professional timed-text rules (modelled on the Netflix
# English Timed Text Style Guide):
#   - max 42 characters per line, max 2 lines; longer subtitles split into two, time shared by length
#   - line breaks at natural points: after punctuation, before conjunctions/prepositions, never after an article;
#     bottom-heavy (shorter top line) when it reads equally well
#   - two speakers: one line each, starting with "-"
#   - display time: min 5/6 s, max 7 s; reading speed <= 20 characters/second (extends into free time when possible)
#   - min 2-frame gap (~0.084 s) between subtitles; gaps under 0.5 s are closed to 2 frames (less flicker)
#   - tabs → line breaks, double spaces, stray formatting tags removed (keeps <i>)
#
# Usage: python3 style.py <in.srt> <out.srt>
# Requires: nothing (stdlib).
import re, sys

MAXL, MINDUR, MAXDUR, CPS, GAP = 42, 5 / 6, 7.0, 20.0, 0.084
BREAK_BEFORE = set("and but or because that which who when where if so than though although while until unless as "
                   "to for with from of in on at by about after before".split())
NO_BREAK_AFTER = set("a an the my your his her our their this that these those to of in on at by mr mrs ms dr".split())


def parse(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if m:
            g = [int(x) for x in m.groups()]
            out.append([g[0]*3600+g[1]*60+g[2]+g[3]/1000, g[4]*3600+g[5]*60+g[6]+g[7]/1000, blk[m.end():].strip()])
    return sorted(out)


def tidy(t):
    t = t.replace("\t", "\n")
    t = re.sub(r"\{[^}]*\}|</?(?!i>)[a-z][^>]*>", "", t)
    lines = [" ".join(l.split()) for l in t.split("\n") if l.strip()]
    return lines


def speakers(lines):
    """Return list of speaker turns if this is a two-speaker subtitle, else None."""
    joined = " ".join(lines)
    parts = [p.strip() for p in re.split(r"(?:^|\s)-\s*(?=\S)", joined) if p.strip()]
    if joined.lstrip().startswith("-") and len(parts) == 2:
        return parts
    return None


def best_break(text):
    if len(text) <= MAXL:
        return [text]
    w = text.split()
    best = None
    for k in range(1, len(w)):
        a, b = " ".join(w[:k]), " ".join(w[k:])
        if len(a) > MAXL or len(b) > MAXL:
            continue
        cost = abs(len(a) - len(b)) * 0.1
        if len(a) > len(b):
            cost += 1.0                                   # prefer bottom-heavy
        if re.search(r"[.,;:?!]$", a):
            cost -= 4.0                                   # after punctuation: best
        elif w[k].lower().strip("\"'") in BREAK_BEFORE:
            cost -= 2.0                                   # before a conjunction/preposition: good
        if w[k - 1].lower().strip("\"'") in NO_BREAK_AFTER:
            cost += 6.0                                   # never strand an article/preposition
        if best is None or cost < best[0]:
            best = (cost, [a, b])
    return best[1] if best else None


def split_sentence(text):
    """Split an over-long text into two halves at the most natural point (sentence > clause > word)."""
    for pat in (r"(?<=[.?!])\s+", r"(?<=[,;:])\s+", r"\s+"):
        cands = [m.start() for m in re.finditer(pat, text)]
        if cands:
            mid = min(cands, key=lambda i: abs(i - len(text) / 2))
            return text[:mid].strip(), text[mid:].strip()
    return text, ""


def render(lines):
    sp = speakers(lines)
    if sp:
        if all(len(p) + 1 <= MAXL for p in sp):
            return ["-" + p for p in sp], None
        return None, sp                                    # too long for one subtitle: split by speaker
    text = " ".join(lines)
    br = best_break(text)
    if br:
        return br, None
    return None, list(split_sentence(text))


def main():
    cues = parse(sys.argv[1])
    out = []
    for a, b, t in cues:
        lines = tidy(t)
        if not lines:
            continue
        queue = [(a, b, lines)]
        while queue:
            a1, b1, ls = queue.pop(0)
            r, parts = render(ls)
            if r:
                out.append([a1, b1, r]); continue
            p1, p2 = parts
            if not p2:
                out.append([a1, b1, [p1[:MAXL], p1[MAXL:MAXL * 2]]]); continue
            mid = a1 + (b1 - a1) * len(p1) / (len(p1) + len(p2))
            queue[0:0] = [(a1, mid - GAP / 2, [p1]), (mid + GAP / 2, b1, [p2])]
    out.sort()
    # timing rules
    for k, c in enumerate(out):
        nxt = out[k + 1][0] if k + 1 < len(out) else c[1] + 60
        chars = sum(len(l) for l in c[2])
        need = max(MINDUR, chars / CPS)
        if c[1] - c[0] < need:
            c[1] = min(c[0] + need, nxt - GAP)
        if c[1] - c[0] > MAXDUR:
            c[1] = c[0] + MAXDUR
        if 0 < nxt - c[1] < 0.5:
            c[1] = nxt - GAP
        if c[1] > nxt - GAP:
            c[1] = nxt - GAP
        if c[1] <= c[0]:
            c[1] = c[0] + 0.3
    fmt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t-int(t))*1000))%1000:03d}"
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        for n, (a, b, ls) in enumerate(out, 1):
            f.write(f"{n}\n{fmt(a)} --> {fmt(b)}\n" + "\n".join(ls) + "\n\n")
    long = sum(1 for _, _, ls in out for l in ls if len(l) > MAXL)
    fast = sum(1 for a, b, ls in out if sum(map(len, ls)) / max(b - a, 0.01) > CPS + 0.5)
    print(f"{sys.argv[2]}: {len(out)} subtitles; lines over {MAXL} chars: {long}; over {CPS:.0f} cps: {fast}")


if __name__ == "__main__":
    main()
