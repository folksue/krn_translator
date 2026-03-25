#!/usr/bin/env python3
import argparse
import gzip
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Hooktheory entries by IDs listed in a log file.")
    parser.add_argument("--input", type=Path, required=True, help="Path to Hooktheory.json.gz")
    parser.add_argument("--log", type=Path, required=True, help="Path to log file: <id>\\t<reason>")
    parser.add_argument("--out-json", type=Path, required=True, help="Output JSON path")
    parser.add_argument("--out-jsonl", type=Path, default=None, help="Optional output JSONL path")
    args = parser.parse_args()

    ids = []
    reasons = {}
    for line in args.log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        sid = parts[0].strip()
        reason = parts[1].strip() if len(parts) > 1 else "UNKNOWN"
        ids.append(sid)
        reasons[sid] = reason

    with gzip.open(args.input, "rt", encoding="utf-8") as f:
        data = json.load(f)

    extracted = {}
    missing = []
    for sid in ids:
        if sid in data:
            extracted[sid] = {"reason": reasons.get(sid, ""), "entry": data[sid]}
        else:
            missing.append(sid)

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(extracted, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.out_jsonl:
        args.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.out_jsonl.open("w", encoding="utf-8") as f:
            for sid, payload in extracted.items():
                f.write(json.dumps({"id": sid, **payload}, ensure_ascii=False) + "\n")

    print(f"requested_ids={len(ids)}")
    print(f"extracted={len(extracted)}")
    print(f"missing={len(missing)}")
    print(f"out_json={args.out_json}")
    if args.out_jsonl:
        print(f"out_jsonl={args.out_jsonl}")


if __name__ == "__main__":
    main()
