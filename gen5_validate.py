#!/usr/bin/env python3
"""
gen5_validate.py — Gen 5: synthetic-vs-real failure distribution comparator
(Jensen-Shannon divergence).

Usage:
    python gen5_validate.py synthetic.json real.json -o report.md

Inputs: two Schema v1 JSON files produced by to_schema_v1.py
        ({"manifest": ..., "segments": [...]}).

Axes (each used only if both sides have data):
    1. failure type     — error_code or source_label frequency
    2. failure length   — failure_frame.end - start (frames, bucketed)
    3. recovery rate    — recovery 0/1
    4. recovery latency — recovery_frame - failure_frame.end (frames, bucketed)

Output: per-axis JS divergence (0 = identical, 1 = completely different),
        a verdict, and the list of real failure types absent from synthetic.
"""
import argparse, json, math
from collections import Counter


def load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d["segments"] if isinstance(d, dict) else d


def js(p, q):
    keys = set(p) | set(q)
    P = {k: p.get(k, 0) for k in keys}
    Q = {k: q.get(k, 0) for k in keys}
    sp, sq = sum(P.values()) or 1, sum(Q.values()) or 1
    P = {k: v / sp for k, v in P.items()}
    Q = {k: v / sq for k, v in Q.items()}
    M = {k: (P[k] + Q[k]) / 2 for k in keys}
    kl = lambda A, B: sum(A[k] * math.log2(A[k] / B[k]) for k in keys if A[k] > 0)
    return round((kl(P, M) + kl(Q, M)) / 2, 4)


def bucket(v, edges=(0, 15, 30, 60, 120, 240, 480)):
    if v < edges[0]:
        return f"<{edges[0]}"  # negative = inconsistent frames; keep visible, don't merge into the top bucket
    for lo, hi in zip(edges, edges[1:]):
        if lo <= v < hi:
            return f"{lo}-{hi}"
    return f"{edges[-1]}+"


def ftype(s):
    return s.get("error_code") or s.get("source_label")


def flen(s):
    f = s.get("failure_frame")
    return None if not f or f.get("start") is None or f.get("end") is None else f["end"] - f["start"]


def rlat(s):
    f = s.get("failure_frame")
    r = s.get("recovery_frame")
    return None if not f or f.get("end") is None or r is None else r - f["end"]


AXES = [
    ("failure type", lambda s: ftype(s)),
    ("failure length (frames)", lambda s: None if flen(s) is None else bucket(flen(s))),
    ("recovery rate", lambda s: None if s.get("recovery") is None else str(s["recovery"])),
    ("recovery latency (frames)", lambda s: None if rlat(s) is None else bucket(rlat(s))),
]


def verdict(d):
    return "match" if d < 0.1 else "some difference" if d < 0.3 else "different distribution"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("synthetic")
    ap.add_argument("real")
    ap.add_argument("-o", "--out", default="gen5_report.md")
    a = ap.parse_args()
    S, R = load(a.synthetic), load(a.real)
    lines = ["# Gen 5 validation report — synthetic vs real", "",
             f"- synthetic segments: {len(S)} / real segments: {len(R)}", "",
             "| axis | synthetic n | real n | JS divergence | verdict |",
             "|---|---|---|---|---|"]
    worst = None
    for name, fn in AXES:
        cs = Counter(v for v in map(fn, S) if v is not None)
        cr = Counter(v for v in map(fn, R) if v is not None)
        if not cs or not cr:
            lines.append(f"| {name} | {sum(cs.values())} | {sum(cr.values())} | — | no data |")
            continue
        d = js(cs, cr)
        worst = d if worst is None else max(worst, d)
        lines.append(f"| {name} | {sum(cs.values())} | {sum(cr.values())} | {d} | {verdict(d)} |")
    miss = sorted({ftype(s) for s in R if ftype(s)} - {ftype(s) for s in S if ftype(s)})
    if worst is None:
        lines += ["", "**Overall**: no comparable axis — both files need at least one shared field", ""]
    else:
        lines += ["", f"**Overall**: max JS {worst} → {verdict(worst)}", ""]
    if miss:
        lines += ["**Real failure types absent from synthetic** (the gap synthetic threw away):", ""]
        lines += [f"- {m}" for m in miss]
    else:
        lines.append("Real failure types absent from synthetic: none")
    lines += ["", "_JS divergence: 0 = identical, 1 = completely different. Thresholds 0.1 / 0.3 are initial and will be recalibrated as real data accumulates._"]
    open(a.out, "w", encoding="utf-8").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
