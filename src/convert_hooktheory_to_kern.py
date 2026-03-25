#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


MAX_DENOMINATOR = 960
PC_TO_NAME = {
    0: "C",
    1: "C#",
    2: "D",
    3: "E-",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "G#",
    9: "A",
    10: "B-",
    11: "B",
}
MAJOR_INTERVALS = [2, 2, 1, 2, 2, 2]
MINOR_INTERVALS = [2, 1, 2, 2, 1, 2]


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


def pitch_class_to_name(pc: int) -> str:
    return PC_TO_NAME[pc % 12]


def midi_to_kern_pitch(midi: int) -> str:
    pc = midi % 12
    octave = (midi // 12) - 1
    base_name = pitch_class_to_name(pc)
    letter = base_name[0]
    accidental = base_name[1:] if len(base_name) > 1 else ""
    if octave >= 4:
        letter_token = letter.lower() * (octave - 3)
    else:
        letter_token = letter.upper() * (4 - octave)
    return f"{letter_token}{accidental}"


def reciprocal_duration(dur_beats: Fraction, beat_unit: int) -> str:
    recip = Fraction(beat_unit, 1) / dur_beats
    if recip.denominator == 1:
        return str(recip.numerator)
    return f"{recip.numerator}%{recip.denominator}"


def key_token_from_annotation(key_ann: Optional[Dict]) -> str:
    if not key_ann:
        return "*"
    tonic = pitch_class_to_name(int(key_ann.get("tonic_pitch_class", 0)))
    intervals = key_ann.get("scale_degree_intervals") or []
    if intervals == MAJOR_INTERVALS:
        return f"*{tonic}:"
    if intervals == MINOR_INTERVALS:
        return f"*{tonic.lower()}:"
    return "*"


def chord_quality(intervals: List[int]) -> str:
    tup = tuple(intervals)
    triads = {
        (4, 3): "",
        (3, 4): "m",
        (3, 3): "dim",
        (4, 4): "aug",
    }
    sevenths = {
        (4, 3, 3): "7",
        (4, 3, 4): "maj7",
        (3, 4, 3): "m7",
        (3, 4, 4): "m(maj7)",
        (3, 3, 4): "m7b5",
        (3, 3, 3): "dim7",
        (4, 4, 2): "aug7",
        (4, 4, 3): "augmaj7",
    }
    if tup in triads:
        return triads[tup]
    if tup in sevenths:
        return sevenths[tup]
    return f"({'.'.join(str(i) for i in intervals)})"


def harmony_to_symbol(h: Dict) -> str:
    root_pc = int(h.get("root_pitch_class", 0)) % 12
    intervals = [int(x) for x in (h.get("root_position_intervals") or [])]
    inv = int(h.get("inversion", 0) or 0)
    root_name = pitch_class_to_name(root_pc)
    quality = chord_quality(intervals)
    symbol = f"{root_name}{quality}"

    if intervals:
        semis = [0]
        cur = 0
        for step in intervals:
            cur += step
            semis.append(cur)
        if 0 <= inv < len(semis):
            bass_pc = (root_pc + semis[inv]) % 12
            bass_name = pitch_class_to_name(bass_pc)
            if bass_name != root_name:
                symbol += f"/{bass_name}"
    return symbol


def active_item_at(items: List[Dict], beat: Fraction) -> Optional[Dict]:
    for item in items:
        if item["onset"] <= beat < item["offset"]:
            return item
    return None


def build_kern_for_song(song_id: str, entry: Dict) -> Optional[str]:
    ann = entry.get("annotations") or {}
    melody_raw = ann.get("melody") or []
    harmony_raw = ann.get("harmony") or []
    if not melody_raw and not harmony_raw:
        return None

    meters = ann.get("meters") or []
    meter0 = meters[0] if meters else {"beats_per_bar": 4, "beat_unit": 4}
    beats_per_bar = int(meter0.get("beats_per_bar", 4) or 4)
    beat_unit = int(meter0.get("beat_unit", 4) or 4)
    key_ann = (ann.get("keys") or [None])[0]

    melody = []
    for n in melody_raw:
        onset = qfrac(n["onset"])
        offset = qfrac(n["offset"])
        if offset <= onset:
            continue
        pc = int(n["pitch_class"]) % 12
        octv = int(n.get("octave", 0))
        midi = 60 + pc + (12 * octv)
        melody.append({"onset": onset, "offset": offset, "midi": midi})
    melody.sort(key=lambda x: (x["onset"], x["offset"]))

    harmony = []
    for h in harmony_raw:
        onset = qfrac(h["onset"])
        offset = qfrac(h["offset"])
        if offset <= onset:
            continue
        harmony.append(
            {
                "onset": onset,
                "offset": offset,
                "symbol": harmony_to_symbol(h),
            }
        )
    harmony.sort(key=lambda x: (x["onset"], x["offset"]))

    raw_total_beats = ann.get("num_beats")
    total_beats = qfrac(raw_total_beats) if raw_total_beats is not None else Fraction(0)
    for seq in (melody, harmony):
        if seq:
            total_beats = max(total_beats, max(x["offset"] for x in seq))
    if total_beats <= 0:
        return None

    boundaries = {Fraction(0), total_beats}
    for n in melody:
        boundaries.add(n["onset"])
        boundaries.add(n["offset"])
    for h in harmony:
        boundaries.add(h["onset"])
        boundaries.add(h["offset"])

    bar_beats = []
    b = Fraction(0)
    bar_step = Fraction(beats_per_bar, 1)
    while b <= total_beats:
        boundaries.add(b)
        bar_beats.append(b)
        b += bar_step
    bar_beat_set = set(bar_beats)

    timeline = sorted(boundaries)
    if len(timeline) < 2:
        return None

    hook = entry.get("hooktheory") or {}
    ytb = entry.get("youtube") or {}
    title = hook.get("song", "unknown-song")
    artist = hook.get("artist", "unknown-artist")
    hook_urls = hook.get("urls") or {}

    lines = [
        "!!!system-decoration: {}",
        f"!!!OTL: {title}",
        f"!!!COM: {artist}",
        f"!!!HTID: {song_id}",
        f"!!!HTURL: {hook_urls.get('song', '')}",
        f"!!!HTCLIP: {hook_urls.get('clip', '')}",
        f"!!!YOUTUBE: {ytb.get('url', '')}",
        "**kern\t**mxhm",
        "*clefG2\t*",
        "*k[]\t*",
        f"*M{beats_per_bar}/{beat_unit}\t*",
        f"{key_token_from_annotation(key_ann)}\t*",
        "=1\t=1",
    ]

    bar_num = 1
    for idx in range(len(timeline) - 1):
        t0 = timeline[idx]
        t1 = timeline[idx + 1]
        dur = t1 - t0
        if dur <= 0:
            continue

        note = active_item_at(melody, t0)
        if note is None:
            kern_token = reciprocal_duration(dur, beat_unit) + "r"
        else:
            note_pitch = midi_to_kern_pitch(note["midi"])
            starts_here = t0 == note["onset"]
            ends_here = t1 == note["offset"]
            tie_suffix = ""
            if starts_here and not ends_here:
                tie_suffix = "["
            elif (not starts_here) and (not ends_here):
                tie_suffix = "_"
            elif (not starts_here) and ends_here:
                tie_suffix = "]"
            kern_token = reciprocal_duration(dur, beat_unit) + note_pitch + tie_suffix

        chord = "."
        for h in harmony:
            if h["onset"] == t0:
                chord = h["symbol"]
                break

        lines.append(f"{kern_token}\t{chord}")

        if t1 in bar_beat_set and t1 != total_beats:
            bar_num += 1
            lines.append(f"={bar_num}\t={bar_num}")

    lines.append(f"={bar_num + 1}\t={bar_num + 1}")
    lines.append("*-\t*-")
    return "\n".join(lines) + "\n"


def build_output_filename(entry_id: str, entry: Dict) -> str:
    hook = entry.get("hooktheory") or {}
    artist = sanitize_slug(hook.get("artist", "unknown-artist"))
    song = sanitize_slug(hook.get("song", "unknown-song"))
    sid = sanitize_slug(hook.get("id", entry_id), lowercase=False)
    name = f"{artist}_{song}_{sid}.krn"
    return name[:200]


def unique_output_filename(base_name: str, entry_id: str, seen_casefold: Dict[str, str]) -> str:
    candidate = base_name
    key = candidate.casefold()
    if key not in seen_casefold or seen_casefold[key] == entry_id:
        seen_casefold[key] = entry_id
        return candidate

    stem = candidate[:-4] if candidate.endswith(".krn") else candidate
    suffix = hashlib.md5(entry_id.encode("utf-8")).hexdigest()[:8]
    alt = f"{stem}_{suffix}.krn"
    key_alt = alt.casefold()
    seen_casefold[key_alt] = entry_id
    return alt[:220]


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
                build_output_filename(entry_id, entry), entry_id, seen_casefold
            )
            out_path = output_dir / out_name
            if skip_existing and out_path.exists():
                skipped += 1
                continue
            content = build_kern_for_song(entry_id, entry)
            if content is None:
                failures.append(f"{entry_id}\tEMPTY_SCORE")
                continue
            out_path.write_text(content, encoding="utf-8")
            converted += 1
        except Exception as exc:
            failures.append(f"{entry_id}\t{type(exc).__name__}:{exc}")
    return converted, skipped, total, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Hooktheory JSON.GZ to Humdrum Kern files.")
    parser.add_argument("--input", type=Path, required=True, help="Path to Hooktheory.json.gz")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for .krn files")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap on converted songs")
    parser.add_argument("--log", type=Path, default=None, help="Optional failure log path")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip output files that already exist (useful for resume).",
    )
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
