#!/usr/bin/env python3
# polish.py — Step 6 of subsync v2: wording polish, done by a human or Claude following POLISH-RULES.md.
#   export: writes batches of ~120 lines as TSV: id, time, seconds, chars/sec, current text, what Whisper heard nearby
#   apply:  reads the edited batches (id <TAB> new text; use " / " for a line break) and writes the polished .srt
#
# Usage:
#   python3 polish.py export <synced.srt> <workdir> <batchdir>
#   python3 polish.py apply  <synced.srt> <batchdir> <out.srt>
# Requires: nothing (stdlib); <workdir>/whisper.json from hear.py.
#
# Gotchas:
#   - Edited batch files are named <batch>.done.tsv; lines missing from them keep their current text.
#   - Timing is never changed here; run style.py afterwards to re-check line length and reading speed.
import json, os, re, sys


def parse(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if m:
            g = [int(x) for x in m.groups()]
            out.append([g[0]*3600+g[1]*60+g[2]+g[3]/1000, g[4]*3600+g[5]*60+g[6]+g[7]/1000, blk[m.end():].strip()])
    return sorted(out)


def fmt(t):
    return f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t-int(t))*1000))%1000:03d}"


def export(srt, work, bdir, size=120):
    cues = parse(srt)
    W = json.load(open(os.path.join(work, "whisper.json")))
    os.makedirs(bdir, exist_ok=True)
    for b in range(0, len(cues), size):
        rows = ["id\ttime\tsecs\tcps\ttext\twhisper_heard"]
        for k in range(b, min(b + size, len(cues))):
            a, e, t = cues[k]
            heard = " | ".join(w["text"] for w in W if w["end"] > a - 1 and w["start"] < e + 1)
            flat = t.replace("\n", " / ")
            cps = len(t.replace("\n", "")) / max(e - a, 0.01)
            rows.append(f"{k}\t{fmt(a)[:8]}\t{e-a:.1f}\t{cps:.0f}\t{flat}\t{heard}")
        open(os.path.join(bdir, f"batch_{b//size:02d}.tsv"), "w", encoding="utf-8").write("\n".join(rows) + "\n")
    print(f"exported {len(cues)} lines in {(len(cues)+size-1)//size} batches to {bdir}")


def apply(srt, bdir, out):
    cues = parse(srt)
    new = {}
    for f in sorted(os.listdir(bdir)):
        if f.endswith(".done.tsv"):
            for line in open(os.path.join(bdir, f), encoding="utf-8"):
                if "\t" in line and line.split("\t", 1)[0].strip().isdigit():
                    k, t = line.rstrip("\n").split("\t", 1)
                    new[int(k)] = t.strip().replace(" / ", "\n")
    with open(out, "w", encoding="utf-8") as fo:
        for n, (a, e, t) in enumerate(cues):
            fo.write(f"{n+1}\n{fmt(a)} --> {fmt(e)}\n{new.get(n, t)}\n\n")
    changed = sum(1 for n, (_, _, t) in enumerate(cues) if n in new and new[n] != t)
    print(f"{out}: {changed} lines reworded of {len(cues)}")


if __name__ == "__main__":
    {"export": lambda: export(*sys.argv[2:5]), "apply": lambda: apply(*sys.argv[2:5])}[sys.argv[1]]()
