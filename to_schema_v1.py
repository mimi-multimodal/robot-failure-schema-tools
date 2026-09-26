#!/usr/bin/env python3
"""
to_schema_v1.py — convert any episode table into Failure-Recovery Schema v1 JSON.

Usage:
    python to_schema_v1.py INPUT --map MAP.json --source DROID -o out.json

INPUT : CSV / Parquet / JSON (list of records). One row = one episode/segment.
MAP   : JSON that maps YOUR column names -> schema fields. Missing fields stay null
        (nothing is inferred).

Mapping example (DROID metadata):
    {"segment_id": "episode_id", "success": "success"}

Mapping example (ViFailback, LeRobot format):
    {"segment_id": "episode_index",
     "failure_frame_start": "failure_start",
     "failure_frame_end": "failure_end",
     "recovery_frame": "recovery_start",
     "success": "recovered",
     "error_code": "failure_type"}

Value rules:
    success column True/1/"success"  -> recovery = 1
                   False/0/"failure" -> recovery = 0
    error_code is kept verbatim in source_label; error_code itself is filled only
    when the value is already an EX.* code, otherwise null.
"""
import argparse, json, sys, hashlib
from pathlib import Path

FIELDS = ["segment_id", "source", "source_label", "failure_frame", "error_code",
          "remediation", "recovery_frame", "recovery", "kinematic_signature",
          "condition", "intervention", "causal_chain", "schema_version"]


def load(path):
    p = Path(path)
    if p.suffix == ".csv":
        import csv
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    if p.suffix in (".parquet", ".pq"):
        import pandas as pd
        return pd.read_parquet(p).to_dict("records")
    if p.suffix == ".json":
        d = json.load(open(p, encoding="utf-8"))
        return d if isinstance(d, list) else list(d.values())
    sys.exit(f"unsupported format: {p.suffix}")


def clean(v):
    """empty string / NaN / None -> None"""
    if v is None:
        return None
    if isinstance(v, float) and v != v:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def to_recovery(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "success", "recovered", "yes"):
        return 1
    if s in ("0", "false", "failure", "fail", "not_recovered", "no"):
        return 0
    return None


def convert(rows, m, source):
    out = []
    for i, r in enumerate(rows):
        g = lambda k: clean(r.get(m[k])) if k in m and m[k] in r else None
        sid = g("segment_id")
        if not isinstance(sid, str) or not sid.startswith(source):
            sid = f"{source}_{sid if sid is not None else i:>06}"
        raw_code = g("error_code")
        fs, fe = to_int(g("failure_frame_start")), to_int(g("failure_frame_end"))
        seg = {
            "segment_id": sid,
            "source": source,
            "source_label": None if raw_code is None else str(raw_code),
            "failure_frame": None if fs is None and fe is None else {"start": fs, "end": fe},
            "error_code": str(raw_code) if isinstance(raw_code, str) and raw_code.startswith("EX.") else None,
            "remediation": None,
            "recovery_frame": to_int(g("recovery_frame")),
            "recovery": to_recovery(g("success")),
            "kinematic_signature": None,
            "condition": {"weight": None, "surface": None, "lighting": None},
            "intervention": None,
            "causal_chain": [],
            "schema_version": "1.0",
        }
        out.append(seg)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--map", required=True, help="column mapping JSON file")
    ap.add_argument("--source", required=True, help="dataset name, e.g. DROID")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    m = json.load(open(a.map, encoding="utf-8"))
    segs = convert(load(a.input), m, a.source)
    body = json.dumps(segs, ensure_ascii=False, indent=1)
    manifest = {
        "schema_version": "1.0",
        "source": a.source,
        "segments": len(segs),
        "with_recovery_label": sum(s["recovery"] is not None for s in segs),
        "with_failure_frame": sum(s["failure_frame"] is not None for s in segs),
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
        "license_note": "Inherits the source dataset license. The converted structure itself is CC BY 4.0 — Mimi Han, Mimi Multimodal AI",
    }
    out = a.out or f"{a.source}_schema_v1.json"
    Path(out).write_text(json.dumps({"manifest": manifest, "segments": segs},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
