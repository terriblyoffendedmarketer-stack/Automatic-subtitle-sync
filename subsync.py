#!/usr/bin/env python3
# subsync.py — ONE COMMAND: diagnose a subtitle file against the film, then apply the cheapest fix that works.
#
# Tiers (decided automatically from "anchors": lines matched by meaning to what's actually said):
#   T0  already in sync            → only style rules
#   T1  constant offset            → shift every line
#   T2  drift (frame-rate mismatch)→ linear stretch
#   T3  different cut              → piecewise placement; lines for missing scenes dropped; kept out of songs
#   T4  low confidence             → recommends the heavy reference (--heavy: Demucs voices + Whisper, ~1 min per 10 min)
# Always after: fine timing pass (±3 s block nudges onto speech) + style rules (42×2, ≤20 cps, 5/6–7 s, 2-frame gaps).
# Wording polish (POLISH-RULES.md) is a separate, optional step: the report says whether it's recommended.
#
# Usage:
#   .venv/bin/python subsync.py <video> <subs.srt> --yt <youtube-url> --lang <ta|bn|hi|..> [--out <out.srt>]
#   .venv/bin/python subsync.py <video> <subs.srt> --heavy --lang <..>          (no YouTube captions / low confidence)
# Requires: project .venv; yt-dlp (+ Chrome login for the bot check); --heavy also needs ~/.dictation venv (Whisper).
# Time: fast path ~1–2 min per film. Heavy path ~15 min (voices) + ~15 min (Whisper) for a 2.5 h film.
import argparse, json, os, re, statistics, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
WHISPER_PY = os.path.expanduser("~/.dictation/.venv/bin/python")


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


def parse(p):
    out = []
    for blk in re.split(r"\n\s*\n", open(p, encoding="utf-8", errors="replace").read().strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", blk)
        if m:
            g = [int(x) for x in m.groups()]
            out.append([g[0]*3600+g[1]*60+g[2]+g[3]/1000, g[4]*3600+g[5]*60+g[6]+g[7]/1000, blk[m.end():].strip()])
    return sorted(out)


def write(cues, p):
    fmt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round((t-int(t))*1000))%1000:03d}"
    with open(p, "w", encoding="utf-8") as f:
        for n, (a, e, t) in enumerate(cues, 1):
            f.write(f"{n}\n{fmt(max(a,0))} --> {fmt(max(e,0))}\n{t}\n\n")


def diagnose(anchors, film_len):
    xs = [a for a, _ in anchors]; offs = [f - a for a, f in anchors]
    c = statistics.median(offs)
    good = lambda res: sum(abs(r) <= 0.7 for r in res) / len(res)
    if good([o - c for o in offs]) >= 0.85:
        return ("T0" if abs(c) < 0.3 else "T1"), {"offset": c}
    n = len(xs); mx = sum(xs) / n; mo = sum(offs) / n
    b = sum((x - mx) * (o - mo) for x, o in zip(xs, offs)) / max(sum((x - mx) ** 2 for x in xs), 1e-9)
    a = mo - b * mx
    if good([o - (a + b * x) for x, o in zip(xs, offs)]) >= 0.85:
        return "T2", {"a": a, "b": b}
    return "T3", {}


def quality_scan(cues):
    foreign = sum(1 for _, _, t in cues if "�" in t or re.search(r"\b(não|você|está|então|também|aqui|agora)\b", t, re.I))
    tabs = sum(1 for _, _, t in cues if "\t" in t)
    grammar = sum(1 for _, _, t in cues if re.search(r"\b(a|an) (Oldman|[aeiou]\w+)\b", t) and re.search(r"\ba [aeiouAEIOU]", t))
    return {"foreign_or_garbled_lines": foreign, "tab_separated_lines": tabs, "article_errors": grammar}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("subs")
    ap.add_argument("--yt"); ap.add_argument("--lang", required=True)
    ap.add_argument("--heavy", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    name = os.path.splitext(os.path.basename(a.video))[0]
    work = os.path.join(HERE, "work", ("heavy-" if a.heavy else "yt-") + name)
    os.makedirs(work, exist_ok=True)
    out = a.out or os.path.join(os.path.dirname(a.video), name + ".en.srt")

    # 1. reference: what is said, when (+ songs)
    if a.heavy:
        sh([PY, os.path.join(HERE, "isolate.py"), a.video, work])
        sh([PY, os.path.join(HERE, "speech.py"), work])
        sh([WHISPER_PY, "-I", os.path.join(HERE, "hear.py"), work, a.lang])
    else:
        if not a.yt:
            sys.exit("give --yt <url> (fast path) or --heavy")
        if not any(f.endswith("-orig.json3") for f in os.listdir(work)):
            sh([PY, os.path.join(HERE, "autocap.py"), "fetch", a.yt, a.lang, work])
        print(sh([PY, os.path.join(HERE, "autocap.py"), "build", work]).strip())

    # 2. coarse placement by meaning + diagnosis
    aligned = os.path.join(work, "aligned.srt")
    sh([PY, os.path.join(HERE, "align.py"), a.subs, work, aligned])
    rep = json.load(open(os.path.join(work, "align_report.json")))
    anchors = rep["anchors_list"]
    src = parse(a.subs)
    film_len = max(e for _, e in json.load(open(os.path.join(work, "speech.json"))))
    tier, model = diagnose(anchors, film_len) if len(anchors) >= 20 else ("T4", {})
    per10 = {}
    for s, f in anchors:
        per10[int(f // 600)] = per10.get(int(f // 600), 0) + 1
    weak = [k * 10 for k in range(int(film_len // 600) + 1) if per10.get(k, 0) < 3]
    if len(weak) > 0.3 * (film_len / 600):
        tier = "T4"

    # 3. apply the cheapest fix
    stage = os.path.join(work, "placed.srt")
    if tier in ("T0", "T1"):
        write([[s + model["offset"], e + model["offset"], t] for s, e, t in src], stage)
    elif tier == "T2":
        f = lambda x: x + model["a"] + model["b"] * x
        write([[f(s), f(e), t] for s, e, t in src], stage)
    else:
        stage = aligned
    fine = os.path.join(work, "fine.srt")
    print(sh(["python3", "-I", os.path.join(HERE, "fine.py"), stage, os.path.join(work, "speech.json"), fine]).strip())
    print(sh(["python3", "-I", os.path.join(HERE, "style.py"), fine, out]).strip())

    q = quality_scan(src)
    report = {
        "tier": tier,
        "what_was_wrong": {"T0": "already in sync", "T1": f"whole file off by {model.get('offset', 0):+.1f} s",
                           "T2": "drift (frame-rate mismatch)",
                           "T3": f"different cut: {len(rep['blocks'])} blocks (scenes shifted/cut/moved), {rep['dropped']} lines dropped",
                           "T4": "low confidence: run again with --heavy"}[tier],
        "anchors": len(anchors), "weak_10min_stretches": weak, "songs": rep["song_sections"],
        "quality": q, "polish_recommended": bool(q["foreign_or_garbled_lines"] or q["article_errors"] > 5),
        "output": out,
    }
    json.dump(report, open(os.path.join(work, "subsync_report.json"), "w"), indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
