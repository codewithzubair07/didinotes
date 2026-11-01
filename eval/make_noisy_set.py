#!/usr/bin/env python3
"""Generate noisy audio dataset variants at specified SNR levels.

Reads clean audio recordings, mixes external noise using eval/add_noise.py logic
at 20, 10, and 5 dB SNR, and generates an extended manifest.
Never commits audio files to version control.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure eval and repo root are in python search path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.add_noise import mix_noise_at_snr, read_wav, write_wav


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create noisy audio variants at 20, 10, and 5 dB SNR and update manifest."
    )
    parser.add_argument(
        "--clean-dir",
        type=Path,
        default=REPO_ROOT / "eval" / "audio" / "clean",
        help="Path to clean audio directory (default: eval/audio/clean)",
    )
    parser.add_argument(
        "--noise",
        type=Path,
        required=True,
        help="Path to user-supplied background noise WAV file (never committed)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "eval" / "audio" / "noisy",
        help="Path to destination directory for noisy audio clips (default: eval/audio/noisy)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "eval" / "audio" / "manifest.jsonl",
        help="Path to input clean manifest (default: eval/audio/manifest.jsonl)",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=None,
        help="Path to output extended manifest (default: overwrites/updates input manifest)",
    )
    parser.add_argument(
        "--snr-levels",
        type=str,
        default="20,10,5",
        help="Comma-separated SNR levels in dB (default: '20,10,5')",
    )
    return parser.parse_args()


def make_noisy_set(
    clean_dir: Path,
    noise_file: Path,
    output_dir: Path,
    manifest_path: Path,
    output_manifest_path: Path | None = None,
    snr_levels: list[float] | None = None,
) -> int:
    if snr_levels is None:
        snr_levels = [20.0, 10.0, 5.0]

    if not noise_file.is_file():
        raise FileNotFoundError(f"Supplied noise file not found: {noise_file}")

    # Read supplied noise file
    noise_data, _n_chan, _n_width, _n_rate = read_wav(noise_file)

    output_dir.mkdir(parents=True, exist_ok=True)
    target_manifest = output_manifest_path or manifest_path

    # Read existing manifest entries
    existing_entries: list[dict] = []
    if manifest_path.is_file():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                existing_entries.append(json.loads(line))

    # Index manifest by filename stem or relative path
    manifest_by_stem: dict[str, dict] = {}
    for entry in existing_entries:
        file_ref = entry.get("file") or entry.get("audio") or ""
        stem = Path(file_ref).stem
        manifest_by_stem[stem] = entry

    clean_files = sorted(
        [p for p in clean_dir.glob("*.wav") if p.is_file()]
    )
    if not clean_files and clean_dir.parent.is_dir():
        # Also check clean clips in audio root if clean subfolder not populated
        clean_files = sorted(
            [p for p in clean_dir.parent.glob("*.wav") if "noisy" not in str(p) and "snr" not in p.stem]
        )

    print(f"Discovered {len(clean_files)} clean audio clips to process.")
    generated_count = 0
    new_manifest_entries: list[dict] = list(existing_entries)

    for clean_path in clean_files:
        clean_data, c_chan, c_width, c_rate = read_wav(clean_path)
        stem = clean_path.stem
        meta = manifest_by_stem.get(stem, {})

        ref_text = meta.get("reference") or meta.get("transcript") or ""
        expected = meta.get("expected_entries") or meta.get("expected")

        # If clean file wasn't in manifest, add it as clean reference
        clean_rel = str(clean_path.relative_to(clean_dir.parent if clean_dir.name == "clean" else clean_dir))
        if not any(e.get("file") == clean_rel for e in new_manifest_entries):
            new_manifest_entries.append({
                "file": clean_rel,
                "reference": ref_text,
                "noise_label": "clean",
                "expected_entries": expected,
            })

        for snr in snr_levels:
            noisy_data = mix_noise_at_snr(clean_data, noise_data, snr)
            snr_tag = f"snr{int(snr)}db"
            noisy_filename = f"{stem}_{snr_tag}.wav"
            noisy_path = output_dir / noisy_filename

            write_wav(noisy_path, noisy_data, c_chan, c_width, c_rate)
            generated_count += 1

            rel_file = f"noisy/{noisy_filename}"
            # Check if already present in manifest
            if not any(e.get("file") == rel_file for e in new_manifest_entries):
                new_manifest_entries.append({
                    "file": rel_file,
                    "reference": ref_text,
                    "noise_label": f"snr_{int(snr)}db",
                    "expected_entries": expected,
                })

    # Write extended manifest
    target_manifest.parent.mkdir(parents=True, exist_ok=True)
    with target_manifest.open("w", encoding="utf-8") as f:
        for entry in new_manifest_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"Generated {generated_count} noisy clips at {snr_levels} dB SNR.")
    print(f"Updated extended manifest with {len(new_manifest_entries)} total entries at {target_manifest}.")
    return generated_count


def main() -> None:
    args = parse_args()
    levels = [float(x.strip()) for x in args.snr_levels.split(",") if x.strip()]
    make_noisy_set(
        clean_dir=args.clean_dir,
        noise_file=args.noise,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        output_manifest_path=args.output_manifest,
        snr_levels=levels,
    )


if __name__ == "__main__":
    main()
