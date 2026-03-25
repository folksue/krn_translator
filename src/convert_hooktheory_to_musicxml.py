#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from typing import Dict, List, Optional, Tuple


MAX_DENOMINATOR = 960
DIVISIONS = 960
PC_TO_STEP_ALTER = {
    0: ("C", 0),
    1: ("C", 1),
    2: ("D", 0),
    3: ("E", -1),
    4: ("E", 0),
    5: ("F", 0),
    6: ("F", 1),
    7: ("G", 0),
    8: ("G", 1),
    9: ("A", 0),
    10: ("B", -1),
    11: ("B", 0),
}


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


def active_item_at(items: List[Dict], beat: Fraction) -> Optional[Dict]:
    for item in items:
        if item["onset"] <= beat < item["offset"]:
            return item
    return None


def kind_from_intervals(intervals: List[int]) -> Tuple[str, Optional[str]]:
    mapping = {
        (4, 3): ("major", None),
        (3, 4): ("minor", None),
        (3, 3): ("diminished", None),
        (4, 4): ("augmented", None),
        (4, 3, 3): ("dominant", "7"),
        (4, 3, 4): ("major-seventh", "maj7"),
        (3, 4, 3): ("minor-seventh", "m7"),
    }
    return mapping.get(tuple(intervals), ("other", ".".join(str(i) for i in intervals)))


def add_harmony(parent: ET.Element, harm: Dict) -> None:
    h = ET.SubElement(parent, "harmony")
    root = ET.SubElement(h, "root")
    step, alter = PC_TO_STEP_ALTER[int(harm["root_pitch_class"]) % 12]
    ET.SubElement(root, "root-step").text = step
    if alter != 0:
        ET.SubElement(root, "root-alter").text = str(alter)

    kind_val, kind_text = kind_from_intervals(harm.get("root_position_intervals", []))
    kind = ET.SubElement(h, "kind")
    kind.text = kind_val
    if kind_text:
        kind.set("text", kind_text)

    intervals = harm.get("root_position_intervals", [])
    inversion = int(harm.get("inversion", 0) or 0)
    semis = [0]
    cur = 0
    for iv in intervals:
        cur += int(iv)
        semis.append(cur)
    if 0 <= inversion < len(semis):
        bass_pc = (int(harm["root_pitch_class"]) + semis[inversion]) % 12
        if bass_pc != int(harm["root_pitch_class"]) % 12:
            bass = ET.SubElement(h, "bass")
            b_step, b_alter = PC_TO_STEP_ALTER[bass_pc]
            ET.SubElement(bass, "bass-step").text = b_step
            if b_alter != 0:
                ET.SubElement(bass, "bass-alter").text = str(b_alter)


def build_musicxml_for_song(song_id: str, entry: Dict) -> Optional[bytes]:
    ann = entry.get("annotations") or {}
    melody_raw = ann.get("melody") or []
    harmony_raw = ann.get("harmony") or []
    if not melody_raw and not harmony_raw:
        return None

    meters = ann.get("meters") or []
    meter0 = meters[0] if meters else {"beats_per_bar": 4, "beat_unit": 4}
    beats_per_bar = int(meter0.get("beats_per_bar", 4) or 4)
    beat_unit = int(meter0.get("beat_unit", 4) or 4)

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
                "root_pitch_class": int(h.get("root_pitch_class", 0)) % 12,
                "root_position_intervals": [int(x) for x in (h.get("root_position_intervals") or [])],
                "inversion": int(h.get("inversion", 0) or 0),
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
    bar_step = Fraction(beats_per_bar, 1)
    b = Fraction(0)
    while b <= total_beats:
        boundaries.add(b)
        b += bar_step
    timeline = sorted(boundaries)
    if len(timeline) < 2:
        return None

    units_per_beat = Fraction(DIVISIONS * 4, beat_unit)
    units_per_measure = int(Fraction(beats_per_bar, 1) * units_per_beat)

    hook = entry.get("hooktheory") or {}
    ytb = entry.get("youtube") or {}
    score = ET.Element("score-partwise", version="3.1")
    work = ET.SubElement(score, "work")
    ET.SubElement(work, "work-title").text = hook.get("song", "unknown-song")
    ident = ET.SubElement(score, "identification")
    ET.SubElement(ident, "creator", type="composer").text = hook.get("artist", "unknown-artist")
    misc = ET.SubElement(ident, "miscellaneous")
    ET.SubElement(misc, "miscellaneous-field", name="hooktheory_id").text = song_id
    ET.SubElement(misc, "miscellaneous-field", name="hooktheory_url").text = (
        (hook.get("urls") or {}).get("song", "")
    )
    ET.SubElement(misc, "miscellaneous-field", name="youtube_url").text = ytb.get("url", "")

    part_list = ET.SubElement(score, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    ET.SubElement(score_part, "part-name").text = "Melody"
    part = ET.SubElement(score, "part", id="P1")

    measure_num = 1
    current_measure = ET.SubElement(part, "measure", number=str(measure_num))
    attrs = ET.SubElement(current_measure, "attributes")
    ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
    key = ET.SubElement(attrs, "key")
    ET.SubElement(key, "fifths").text = "0"
    time = ET.SubElement(attrs, "time")
    ET.SubElement(time, "beats").text = str(beats_per_bar)
    ET.SubElement(time, "beat-type").text = str(beat_unit)
    clef = ET.SubElement(attrs, "clef")
    ET.SubElement(clef, "sign").text = "G"
    ET.SubElement(clef, "line").text = "2"

    measure_start = Fraction(0)
    harmony_onsets = {h["onset"]: h for h in harmony}
    for i in range(len(timeline) - 1):
        t0 = timeline[i]
        t1 = timeline[i + 1]
        if t1 <= t0:
            continue

        while t0 >= measure_start + Fraction(beats_per_bar, 1):
            measure_num += 1
            measure_start += Fraction(beats_per_bar, 1)
            current_measure = ET.SubElement(part, "measure", number=str(measure_num))

        if t0 in harmony_onsets:
            add_harmony(current_measure, harmony_onsets[t0])

        dur_units = int((t1 - t0) * units_per_beat)
        if dur_units <= 0:
            continue
        note_evt = active_item_at(melody, t0)
        note = ET.SubElement(current_measure, "note")
        if note_evt is None:
            ET.SubElement(note, "rest")
            ET.SubElement(note, "duration").text = str(dur_units)
            continue

        pitch = ET.SubElement(note, "pitch")
        pc = note_evt["midi"] % 12
        octv = (note_evt["midi"] // 12) - 1
        step, alter = PC_TO_STEP_ALTER[pc]
        ET.SubElement(pitch, "step").text = step
        if alter != 0:
            ET.SubElement(pitch, "alter").text = str(alter)
        ET.SubElement(pitch, "octave").text = str(octv)
        ET.SubElement(note, "duration").text = str(dur_units)

        starts_here = t0 == note_evt["onset"]
        ends_here = t1 == note_evt["offset"]
        if starts_here and not ends_here:
            ET.SubElement(note, "tie", type="start")
            notations = ET.SubElement(note, "notations")
            ET.SubElement(notations, "tied", type="start")
        elif (not starts_here) and (not ends_here):
            ET.SubElement(note, "tie", type="stop")
            ET.SubElement(note, "tie", type="start")
            notations = ET.SubElement(note, "notations")
            ET.SubElement(notations, "tied", type="stop")
            ET.SubElement(notations, "tied", type="start")
        elif (not starts_here) and ends_here:
            ET.SubElement(note, "tie", type="stop")
            notations = ET.SubElement(note, "notations")
            ET.SubElement(notations, "tied", type="stop")

    xml_bytes = ET.tostring(score, encoding="utf-8", xml_declaration=True)
    return xml_bytes


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
                build_output_filename(entry_id, entry, "musicxml"), entry_id, seen_casefold
            )
            out_path = output_dir / out_name
            if skip_existing and out_path.exists():
                skipped += 1
                continue
            content = build_musicxml_for_song(entry_id, entry)
            if content is None:
                failures.append(f"{entry_id}\tEMPTY_SCORE")
                continue
            out_path.write_bytes(content)
            converted += 1
        except Exception as exc:
            failures.append(f"{entry_id}\t{type(exc).__name__}:{exc}")
    return converted, skipped, total, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Hooktheory JSON.GZ to MusicXML files.")
    parser.add_argument("--input", type=Path, required=True, help="Path to Hooktheory.json.gz")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Output directory for .musicxml files"
    )
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
