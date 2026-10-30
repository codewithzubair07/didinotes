#!/usr/bin/env python3
"""Run speech-to-text evaluation across audio files and noise levels using jiwer.

Computes Word Error Rate (WER) per noise level using the configured STT adapter.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jiwer

if TYPE_CHECKING:
    from app.speech.base import SpeechToText

# Ensure apps/api is in the Python module search path.
REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run STT Word Error Rate (WER) evaluation on an audio folder."
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        required=True,
        help="Path to directory containing audio recordings and sidecar transcripts",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path to a CSV or JSONL reference transcript manifest",
    )
    parser.add_argument(
        "--adapter",
        choices=["mock", "gnani"],
        default=None,
        help="STT adapter override (default: configured in settings or .env)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "eval" / "results",
        help="Directory to save evaluation results (default: eval/results)",
    )
    return parser.parse_args()


def load_stt_adapter(adapter_name: str | None, mock_text: str = "") -> SpeechToText:
    from app.settings import Settings
    from app.speech.providers import get_stt

    settings = Settings(config_dir=REPO_ROOT / "config")
    if adapter_name is not None:
        settings = settings.model_copy(update={"stt_provider": adapter_name})
    return get_stt(settings, mock_text=mock_text)


def detect_noise_level(file_path: Path, audio_dir: Path) -> str:
    """Infer noise level from parent folder name or filename pattern."""
    rel = file_path.relative_to(audio_dir)
    # Check parent folder (e.g. audio/snr_10db/a.wav or audio/clean/a.wav)
    if len(rel.parts) > 1:
        parent_name = rel.parts[0].lower()
        if any(token in parent_name for token in ("clean", "noise", "snr", "db")):
            return parent_name

    stem = file_path.stem.lower()
    match = re.search(r"(snr[_-]?\d+db|snr[_-]?\d+|clean|noise[_-]?\w+)", stem)
    if match:
        return match.group(1)

    return "clean"


def find_reference_text(
    audio_file: Path,
    manifest: dict[str, str] | None,
) -> str | None:
    if manifest and audio_file.name in manifest:
        return manifest[audio_file.name]
    if manifest and audio_file.stem in manifest:
        return manifest[audio_file.stem]

    # Check exact sidecar .txt
    sidecar = audio_file.with_suffix(".txt")
    if sidecar.is_file():
        return sidecar.read_text(encoding="utf-8").strip()

    # Check base stem without noise tag (e.g. test_snr10.wav -> test.txt)
    base_stem = re.sub(r"([_-]snr[_-]?\d+db?|[_-]clean)$", "", audio_file.stem, flags=re.IGNORECASE)
    base_sidecar = audio_file.parent / f"{base_stem}.txt"
    if base_sidecar.is_file():
        return base_sidecar.read_text(encoding="utf-8").strip()

    return None


def run_stt_evaluation(
    audio_dir: Path,
    manifest_path: Path | None = None,
    adapter_name: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    from app.settings import Settings

    settings = Settings(config_dir=REPO_ROOT / "config")
    resolved_adapter = adapter_name or settings.stt_provider

    is_tooling_check = resolved_adapter == "mock"

    manifest: dict[str, str] = {}
    if manifest_path and manifest_path.is_file():
        if manifest_path.suffix == ".jsonl":
            for line in manifest_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    manifest[item.get("audio", "")] = item.get("transcript", "")
        elif manifest_path.suffix in (".csv", ".txt"):
            import csv

            with manifest_path.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2:
                        manifest[row[0].strip()] = row[1].strip()

    audio_files = sorted(
        [
            p
            for p in audio_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".webm", ".ogg")
        ]
    )

    if not audio_files:
        raise FileNotFoundError(f"No audio files found in {audio_dir}")

    samples_by_noise: dict[str, list[dict[str, Any]]] = {}

    for audio_file in audio_files:
        ref_text = find_reference_text(audio_file, manifest)
        if ref_text is None:
            continue

        noise_level = detect_noise_level(audio_file, audio_dir)
        if noise_level not in samples_by_noise:
            samples_by_noise[noise_level] = []

        audio_bytes = audio_file.read_bytes()
        is_wav = audio_file.suffix.lower() == ".wav"
        mime = "audio/wav" if is_wav else f"audio/{audio_file.suffix[1:]}"

        # If mock STT, configure mock_text with ref_text to verify tooling
        stt = load_stt_adapter(resolved_adapter, mock_text=ref_text)
        try:
            transcript = stt.transcribe(audio_bytes, mime, lang_hint="bn")
            hyp_text = transcript.text or ""
        except NotImplementedError:
            hyp_text = ""

        # Compute Word Error Rate
        if not ref_text.strip():
            wer = 0.0 if not hyp_text.strip() else 1.0
        else:
            wer = float(jiwer.wer(ref_text, hyp_text))

        samples_by_noise[noise_level].append(
            {
                "file": audio_file.name,
                "relative_path": str(audio_file.relative_to(audio_dir)),
                "reference": ref_text,
                "hypothesis": hyp_text,
                "wer": round(wer, 4),
            }
        )

    # Summarize per noise level
    per_noise_summary: dict[str, dict[str, Any]] = {}
    total_samples = 0
    total_wer_sum = 0.0

    for noise_level, samples in sorted(samples_by_noise.items()):
        count = len(samples)
        total_samples += count
        avg_wer = sum(s["wer"] for s in samples) / count if count else 0.0
        total_wer_sum += sum(s["wer"] for s in samples)
        per_noise_summary[noise_level] = {
            "samples": count,
            "mean_wer": round(avg_wer, 4),
            "details": samples,
        }

    overall_wer = round(total_wer_sum / total_samples, 4) if total_samples else 0.0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "timestamp": timestamp,
        "adapter": resolved_adapter,
        "is_tooling_check": is_tooling_check,
        "notice": (
            "tooling check only, NOT a real speech-accuracy result"
            if is_tooling_check
            else "Gnani STT evaluation result"
        ),
        "total_samples": total_samples,
        "overall_mean_wer": overall_wer,
        "noise_levels": per_noise_summary,
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"stt_eval_{resolved_adapter}_{timestamp}.json"
        md_path = output_dir / f"stt_eval_{resolved_adapter}_{timestamp}.md"

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        md_content = generate_markdown_report(report)
        with md_path.open("w", encoding="utf-8") as f:
            f.write(md_content)

    print_report(report)
    return report


def generate_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# STT Evaluation Report ({report['adapter']})",
        "",
    ]
    if report["is_tooling_check"]:
        lines.extend([
            "> [!NOTE]",
            "> **tooling check only, NOT a real speech-accuracy result**",
            "> Real STT accuracy can only be measured after Gnani integration and real recordings.",
            "",
        ])
    lines.extend([
        f"- **Timestamp**: `{report['timestamp']}`",
        f"- **Adapter**: `{report['adapter']}`",
        f"- **Total Samples**: `{report['total_samples']}`",
        f"- **Overall Mean WER**: `{report['overall_mean_wer']:.1%}`",
        "",
        "## Word Error Rate by Noise Level",
        "",
        "| Noise Level | Samples | Mean WER |",
        "|---|---|---|",
    ])
    for noise_level, data in sorted(report["noise_levels"].items()):
        lines.append(f"| `{noise_level}` | {data['samples']} | {data['mean_wer']:.1%} |")

    lines.append("")
    return "\n".join(lines)


def print_report(report: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"STT Evaluation Results [{report['adapter']}]")
    if report["is_tooling_check"]:
        print(">>> NOTICE: tooling check only, NOT a real speech-accuracy result <<<")
    print("=" * 60)
    print(f"Total audio samples: {report['total_samples']}")
    print(f"Overall Mean WER:    {report['overall_mean_wer']:.1%}")
    print("\nWER by Noise Level:")
    for noise_level, data in sorted(report["noise_levels"].items()):
        print(f"  {noise_level:15s}: {data['samples']} samples | Mean WER: {data['mean_wer']:.1%}")
    print("=" * 60)


def main() -> None:
    args = parse_args()
    run_stt_evaluation(
        audio_dir=args.audio_dir,
        manifest_path=args.manifest,
        adapter_name=args.adapter,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
