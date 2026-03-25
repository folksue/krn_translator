#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
import re
import struct
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple


MAX_DENOMINATOR = 960
TPQ = 480


def qfrac(value) -> Fraction:
    return Fraction(str(value)).limit_denominator(MAX_DENOMINATOR)


def sanitize_slug(text: str, default: str = "unknown", lowercase: bool = True) -> str:
    if not text:
        return default
    text = text.strip().replace(" ", "-")
    if lowercase:
        text = text.lower()
        pattern = r"[^a-z0-9_-]+"
    else:
        pattern = r"[^A-Za-z0-9_-]+"
    text = re.sub(pattern, "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    return text or default


def build_output_filename(entry_id: str, entry: Dict, ext: str) -> str:
    hook = entry.get("hooktheory") or {}
    artist = sanitize_slug(hook.get("artist", "unknown-artist"))
    song = sanitize_slug(hook.get("song", "unknown-song"))
    sid = sanitize_slug(hook.get("id", entry_id), lowercase=False)
    name = f"{artist}_{song}_{sid}.{ext}"
    return name[:220]


def unique_output_filename(base_name: str, entry_id: str, seen_casefold: Dict[str, str]) -> str:
    key = base_name.casefold()
    if key not in seen_casefold or seen_casefold[key] == entry_id:
        seen_casefold[key] = entry_id
        return base_name
    stem = base_name.rsplit(".", 1)[0]
    ext = base_name.rsplit(".", 1)[1]
    suffix = hashlib.md5(entry_id.encode("utf-8")).hexdigest()[:8]
    alt = f"{stem}_{suffix}.{ext}"
    seen_casefold[alt.casefold()] = entry_id
    return alt[:230]


def varlen(value: int) -> bytes:
    buf = [value & 0x7F]
    value >>= 7
    while value:
        buf.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(buf))


def midi_track(events: List[Tuple[int, bytes]]) -> bytes:
    events.sort(key=lambda x: x[0])
    out = bytearray()
    last_tick = 0
    for tick, payload in events:
        delta = max(0, tick - last_tick)
        out.extend(varlen(delta))
        out.extend(payload)
        last_tick = tick
    out.extend(varlen(0))
    out.extend(b"\xFF\x2F\x00")
    return b"MTrk" + struct.pack(">I", len(out)) + bytes(out)


def meta_event(meta_type: int, data: bytes) -> bytes:
    return bytes([0xFF, meta_type]) + varlen(len(data)) + data


def ticks_per_beat(beat_unit: int) -> Fraction:
    return Fraction(TPQ * 4, beat_unit)


def beat_to_tick(beat: Fraction, beat_unit: int) -> int:
    return int(beat * ticks_per_beat(beat_unit))


def chord_pitches(root_pc: int, intervals: List[int], inversion: int) -> List[int]:
    pcs = [0]
    cur = 0
    for iv in intervals:
        cur += iv
        pcs.append(cur)
    notes = [60 + ((root_pc + p) % 12) for p in pcs]
    inv = max(0, min(inversion, len(notes) - 1)) if notes else 0
    for i in range(inv):
        notes[i] += 12
    return sorted(notes)


def build_midi_for_song(song_id: str, entry: Dict) -> Optional[bytes]:
    ann = entry.get("annotations") or {}
    melody_raw = ann.get("melody") or []
    harmony_raw = ann.get("harmony") or []
    if not melody_raw and not harmony_raw:
        return None

    meters = ann.get("meters") or []
    meter0 = meters[0] if meters else {"beats_per_bar": 4, "beat_unit": 4}
    beats_per_bar = int(meter0.get("beats_per_bar", 4) or 4)
    beat_unit = int(meter0.get("beat_unit", 4) or 4)

    hook = entry.get("hooktheory") or {}
    ytb = entry.get("youtube") or {}
    title = (hook.get("song") or "unknown-song").encode("utf-8", "ignore")
    artist = (hook.get("artist") or "unknown-artist").encode("utf-8", "ignore")
    link = (ytb.get("url") or "").encode("utf-8", "ignore")

    meta_events: List[Tuple[int, bytes]] = []
    meta_events.append((0, meta_event(0x03, title)))
    meta_events.append((0, meta_event(0x01, artist)))
    if link:
        meta_events.append((0, meta_event(0x01, link)))
    # 120 BPM
    meta_events.append((0, b"\xFF\x51\x03\x07\xA1\x20"))
    meta_events.append((0, bytes([0xFF, 0x58, 0x04, beats_per_bar & 0xFF, 2, 24, 8])))

    melody_events: List[Tuple[int, bytes]] = []
    for n in melody_raw:
        onset = qfrac(n["onset"])
        offset = qfrac(n["offset"])
        if offset <= onset:
            continue
        pc = int(n["pitch_class"]) % 12
        octv = int(n.get("octave", 0))
        midi = 60 + pc + (12 * octv)
        on_tick = beat_to_tick(onset, beat_unit)
        off_tick = beat_to_tick(offset, beat_unit)
        if off_tick <= on_tick:
            off_tick = on_tick + 1
        melody_events.append((on_tick, bytes([0x90, midi & 0x7F, 88])))
        melody_events.append((off_tick, bytes([0x80, midi & 0x7F, 64])))

    harmony_events: List[Tuple[int, bytes]] = []
    for h in harmony_raw:
        onset = qfrac(h["onset"])
        offset = qfrac(h["offset"])
        if offset <= onset:
            continue
        root_pc = int(h.get("root_pitch_class", 0)) % 12
        intervals = [int(x) for x in (h.get("root_position_intervals") or [])]
        inversion = int(h.get("inversion", 0) or 0)
        notes = chord_pitches(root_pc, intervals, inversion)
        on_tick = beat_to_tick(onset, beat_unit)
        off_tick = beat_to_tick(offset, beat_unit)
        if off_tick <= on_tick:
            off_tick = on_tick + 1
        for m in notes:
            harmony_events.append((on_tick, bytes([0x91, m & 0x7F, 70])))
            harmony_events.append((off_tick, bytes([0x81, m & 0x7F, 50])))

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 3, TPQ)
    return header + midi_track(meta_events) + midi_track(melody_events) + midi_track(harmony_events)


def convert_all(
    input_gz: Path, output_dir: Path, limit: Optional[int], skip_existing: bool
) -> Tuple[int, int, int, List[str]]:
    with gzip.open(input_gz, "rt", encoding="utf-8") as f:
        data = json.load(f)
    output_dir.mkdir(parents=True, exist_ok=True)

    failures: List[str] = []
    converted = 0
    skipped = 0
    total = 0
    seen_casefold: Dict[str, str] = {}

    for entry_id, entry in data.items():
        total += 1
        if limit is not None and total > limit:
            break
        try:
            out_name = unique_output_filename(
                build_output_filename(entry_id, entry, "mid"), entry_id, seen_casefold
            )
            out_path = output_dir / out_name
            if skip_existing and out_path.exists():
                skipped += 1
                continue
            content = build_midi_for_song(entry_id, entry)
            if content is None:
                failures.append(f"{entry_id}\tEMPTY_SCORE")
                continue
            out_path.write_bytes(content)
            converted += 1
        except Exception as exc:
            failures.append(f"{entry_id}\t{type(exc).__name__}:{exc}")
    return converted, skipped, total, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Hooktheory JSON.GZ to MIDI files.")
    parser.add_argument("--input", type=Path, required=True, help="Path to Hooktheory.json.gz")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for .mid files")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on processed songs")
    parser.add_argument("--log", type=Path, default=None, help="Optional failure log path")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already exist")
    args = parser.parse_args()

    converted, skipped, total, failures = convert_all(
        args.input, args.output_dir, args.limit, args.skip_existing
    )
    print(f"processed_entries={total}")
    print(f"converted_files={converted}")
    print(f"skipped_existing={skipped}")
    print(f"failures={len(failures)}")
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text("\n".join(failures) + ("\n" if failures else ""), encoding="utf-8")
        print(f"log={args.log}")


if __name__ == "__main__":
    main()
