#!/usr/bin/env python3
import argparse
import gzip
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

from convert_hooktheory_to_kern import build_kern_for_song
from convert_hooktheory_to_midi import build_midi_for_song
from convert_hooktheory_to_musicxml import build_musicxml_for_song
from convert_hooktheory_to_kern import build_output_filename as build_krn_name
from convert_hooktheory_to_midi import build_output_filename as build_midi_name
from convert_hooktheory_to_musicxml import build_output_filename as build_xml_name
from convert_hooktheory_to_kern import unique_output_filename as unique_krn_name
from convert_hooktheory_to_midi import unique_output_filename as unique_midi_name
from convert_hooktheory_to_musicxml import unique_output_filename as unique_xml_name


def load_data(input_gz: Path) -> Dict:
    with gzip.open(input_gz, "rt", encoding="utf-8") as f:
        return json.load(f)


def build_name_maps(data: Dict) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    krn_seen: Dict[str, str] = {}
    mid_seen: Dict[str, str] = {}
    xml_seen: Dict[str, str] = {}
    krn_map: Dict[str, str] = {}
    mid_map: Dict[str, str] = {}
    xml_map: Dict[str, str] = {}
    for entry_id, entry in data.items():
        krn_map[entry_id] = unique_krn_name(build_krn_name(entry_id, entry), entry_id, krn_seen)
        mid_map[entry_id] = unique_midi_name(build_midi_name(entry_id, entry, "mid"), entry_id, mid_seen)
        xml_map[entry_id] = unique_xml_name(
            build_xml_name(entry_id, entry, "musicxml"), entry_id, xml_seen
        )
    return krn_map, mid_map, xml_map


def validate_krn(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "**kern\t**mxhm" in text and "*-\t*-" in text


def validate_midi(path: Path) -> bool:
    if not path.exists():
        return False
    data = path.read_bytes()
    return len(data) >= 14 and data[:4] == b"MThd"


def validate_musicxml(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        tree = ET.parse(path)
        return tree.getroot().tag.endswith("score-partwise")
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Randomly sample 10 entries and validate outputs.")
    parser.add_argument("--input", type=Path, required=True, help="Path to Hooktheory.json.gz")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--n", type=int, default=10, help="Sample size")
    parser.add_argument("--krn-dir", type=Path, default=Path("output/krn_final"))
    parser.add_argument("--midi-dir", type=Path, default=Path("output/midi"))
    parser.add_argument("--xml-dir", type=Path, default=Path("output/musicxml"))
    parser.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate KRN/MIDI/MusicXML for sampled entries into --sample-out-dir before validating.",
    )
    parser.add_argument("--sample-out-dir", type=Path, default=Path("output/validation_sample"))
    args = parser.parse_args()

    data = load_data(args.input)
    ids = list(data.keys())
    if len(ids) < args.n:
        raise ValueError(f"dataset only has {len(ids)} entries; cannot sample {args.n}")
    rng = random.Random(args.seed)
    sampled = rng.sample(ids, args.n)
    krn_map, mid_map, xml_map = build_name_maps(data)

    if args.generate_sample:
        for sub in ("krn", "midi", "musicxml"):
            (args.sample_out_dir / sub).mkdir(parents=True, exist_ok=True)
        for sid in sampled:
            entry = data[sid]
            k = build_kern_for_song(sid, entry)
            m = build_midi_for_song(sid, entry)
            x = build_musicxml_for_song(sid, entry)
            if k is not None:
                (args.sample_out_dir / "krn" / krn_map[sid]).write_text(k, encoding="utf-8")
            if m is not None:
                (args.sample_out_dir / "midi" / mid_map[sid]).write_bytes(m)
            if x is not None:
                (args.sample_out_dir / "musicxml" / xml_map[sid]).write_bytes(x)
        args.krn_dir = args.sample_out_dir / "krn"
        args.midi_dir = args.sample_out_dir / "midi"
        args.xml_dir = args.sample_out_dir / "musicxml"

    ok_krn = 0
    ok_midi = 0
    ok_xml = 0
    print("sampled_ids:")
    for sid in sampled:
        print(f"- {sid}")
        if validate_krn(args.krn_dir / krn_map[sid]):
            ok_krn += 1
        if validate_midi(args.midi_dir / mid_map[sid]):
            ok_midi += 1
        if validate_musicxml(args.xml_dir / xml_map[sid]):
            ok_xml += 1
    print(f"krn_valid={ok_krn}/{args.n}")
    print(f"midi_valid={ok_midi}/{args.n}")
    print(f"musicxml_valid={ok_xml}/{args.n}")


if __name__ == "__main__":
    main()
