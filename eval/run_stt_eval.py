#!/usr/bin/env python3
"""Run speech-to-text evaluation across audio files and noise levels using jiwer.

Computes Word Error Rate (WER) and Character Error Rate (CER) per configuration
and per noise level using the configured STT adapter. Supports sequential execution
across multiple STT configurations with dry-run capabilities and rate-limit safety guards.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jiwer
import numpy as np

if TYPE_CHECKING:
    from app.speech.base import SpeechToText

# Ensure apps/api is in the Python module search path.
REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

logger = logging.getLogger("didinotes.stt_eval")

# Translation table converting Bengali digits (০-৯) to ASCII digits (0-9)
BN_DIGITS_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Punctuation including Bengali Dari (U+0964), Double Dari (U+0965), and common ASCII symbols
PUNCT_REGEX = re.compile(r"[\u0964\u0965।,!?;:\"'()\[\]{}<>/\\~`@#$%^&*_\-+=]")


def normalise_eval_text(text: str) -> str:
    """Documented normalisation applied to both reference and hypothesis:
    1. Unicode NFC normalization (composes accented characters uniformly).
    2. Bengali digits (০-৯) mapped to ASCII digits (0-9).
    3. Removal of punctuation, including Bengali full stop (dari '।', double dari '॥').
    4. ASCII case folding (lower).
    5. Whitespace normalization (collapsing duplicate spaces and trimming).
    """
    if not text:
        return ""
    # 1. Unicode NFC
    s = unicodedata.normalize("NFC", text)
    # 2. Bengali digits to ASCII
    s = s.translate(BN_DIGITS_TO_ASCII)
    # 3. Strip punctuation
    s = PUNCT_REGEX.sub(" ", s)
    # 4. Lowercase
    s = s.lower()
    # 5. Collapse duplicate whitespaces
    return " ".join(s.split())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run STT Word Error Rate (WER) & CER evaluation across configurations."
    )
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=REPO_ROOT / "eval" / "audio",
        help="Path to directory containing audio recordings (default: eval/audio)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path to manifest.jsonl (default: <audio-dir>/manifest.jsonl if present)",
    )
    parser.add_argument(
        "--configs",
        type=Path,
        default=None,
        help="Path to JSON file listing STT configurations to evaluate sequentially",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned API calls and configurations without executing outbound requests",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="Hard cap on the maximum number of live API requests to execute",
    )
    return parser.parse_args()


def load_manifest(manifest_path: Path, audio_dir: Path) -> list[dict[str, Any]]:
    """Loads dataset manifest items from JSONL or CSV file."""
    items: list[dict[str, Any]] = []
    if not manifest_path.is_file():
        return items

    if manifest_path.suffix == ".jsonl":
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            # Normalize field names
            file_ref = data.get("file") or data.get("audio") or ""
            ref_text = data.get("reference") or data.get("transcript") or ""
            noise_label = data.get("noise_label") or "clean"
            expected_entries = data.get("expected_entries")

            file_path = audio_dir / file_ref if not Path(file_ref).is_absolute() else Path(file_ref)
            items.append({
                "file": file_ref,
                "path": file_path,
                "reference": ref_text,
                "noise_label": noise_label,
                "expected_entries": expected_entries,
            })
    elif manifest_path.suffix in (".csv", ".txt"):
        import csv

        with manifest_path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    file_ref = row[0].strip()
                    ref_text = row[1].strip()
                    noise_label = row[2].strip() if len(row) > 2 else "clean"
                    file_path = audio_dir / file_ref
                    items.append({
                        "file": file_ref,
                        "path": file_path,
                        "reference": ref_text,
                        "noise_label": noise_label,
                        "expected_entries": None,
                    })
    return items


def detect_noise_level(file_path: Path, audio_dir: Path) -> str:
    """Infer noise level from relative path or filename pattern."""
    try:
        rel = file_path.relative_to(audio_dir)
        if len(rel.parts) > 1:
            parent_name = rel.parts[0].lower()
            if any(token in parent_name for token in ("clean", "noise", "snr", "db")):
                return parent_name
    except ValueError:
        pass

    stem = file_path.stem.lower()
    match = re.search(r"(snr[_-]?\d+db|snr[_-]?\d+|clean|noise[_-]?\w+)", stem)
    if match:
        return match.group(1)

    return "clean"


def load_stt_adapter(
    adapter_name: str,
    config: dict[str, Any] | None = None,
    mock_text: str = "",
) -> SpeechToText:
    """Instantiate STT adapter configured for evaluation."""
    from app.settings import Settings
    from app.speech.providers import get_stt

    settings = Settings(config_dir=REPO_ROOT / "config")
    updates: dict[str, Any] = {"stt_provider": adapter_name}

    if config:
        if "model" in config:
            updates["gnani_stt_model"] = config["model"]
        if "languages" in config:
            updates["gnani_stt_languages"] = config["languages"]
        if "format" in config:
            updates["gnani_stt_format"] = config["format"]
        if config.get("context") and "topic" in config:
            updates["gnani_stt_topic"] = config["topic"]
        if config.get("context") and "keyterms" in config:
            keyterms = config["keyterms"]
            updates["gnani_stt_keyterms"] = (
                json.dumps(keyterms) if isinstance(keyterms, list) else str(keyterms)
            )

    settings = settings.model_copy(update=updates)
    return get_stt(settings, mock_text=mock_text)


def run_single_config(
    config_name: str,
    config_params: dict[str, Any],
    clips: list[dict[str, Any]],
    adapter_name: str,
    max_calls: int | None,
    current_call_count: int,
) -> tuple[dict[str, Any], int]:
    """Runs STT evaluation sequentially across clips for one configuration."""
    from app.speech.gnani import GnaniError, GnaniQuotaError, GnaniRateLimitError

    samples_by_noise: dict[str, list[dict[str, Any]]] = {}
    latencies: list[float] = []
    empty_transcripts = 0
    errors_count = 0
    consecutive_rate_limits = 0
    calls_made = 0

    is_mock = adapter_name == "mock"

    for clip in clips:
        if max_calls is not None and (current_call_count + calls_made) >= max_calls:
            print(f"   [!] Reached max calls limit ({max_calls}). Stopping early.")
            break

        audio_path = clip["path"]
        if not audio_path.is_file():
            continue

        raw_ref = clip["reference"]
        norm_ref = normalise_eval_text(raw_ref)
        noise_label = clip["noise_label"]

        if noise_label not in samples_by_noise:
            samples_by_noise[noise_label] = []

        audio_bytes = audio_path.read_bytes()
        is_wav = audio_path.suffix.lower() == ".wav"
        mime = "audio/wav" if is_wav else f"audio/{audio_path.suffix[1:]}"

        stt = load_stt_adapter(adapter_name, config_params, mock_text=raw_ref)
        started = time.perf_counter()
        raw_hyp = ""
        error_msg: str | None = None

        try:
            calls_made += 1
            transcript = stt.transcribe(audio_bytes, mime, lang_hint="bn")
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            raw_hyp = transcript.text or ""
            latencies.append(elapsed_ms)
            consecutive_rate_limits = 0
        except (GnaniQuotaError, GnaniRateLimitError) as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            latencies.append(elapsed_ms)
            errors_count += 1
            consecutive_rate_limits += 1
            error_msg = str(exc)
            if consecutive_rate_limits >= 2:
                print(f"   [!] Repeated 402/429 errors ({error_msg}). Aborting configuration early.")
                break
        except (GnaniError, OSError, RuntimeError, ValueError) as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            latencies.append(elapsed_ms)
            errors_count += 1
            consecutive_rate_limits = 0
            error_msg = str(exc)

        if not raw_hyp.strip() and not error_msg:
            empty_transcripts += 1

        norm_hyp = normalise_eval_text(raw_hyp)

        # Compute WER and CER
        if not norm_ref:
            wer = 0.0 if not norm_hyp else 1.0
            cer = 0.0 if not norm_hyp else 1.0
        else:
            wer = float(jiwer.wer(norm_ref, norm_hyp)) if norm_hyp else 1.0
            cer = float(jiwer.cer(norm_ref, norm_hyp)) if norm_hyp else 1.0

        samples_by_noise[noise_label].append({
            "file": clip["file"],
            "raw_reference": raw_ref,
            "norm_reference": norm_ref,
            "raw_hypothesis": raw_hyp,
            "norm_hypothesis": norm_hyp,
            "wer": round(wer, 4),
            "cer": round(cer, 4),
            "latency_ms": elapsed_ms,
            "error": error_msg,
        })

    # Aggregate metrics
    all_samples: list[dict[str, Any]] = [s for group in samples_by_noise.values() for s in group]
    total_samples = len(all_samples)
    mean_wer = sum(s["wer"] for s in all_samples) / total_samples if total_samples else 0.0
    mean_cer = sum(s["cer"] for s in all_samples) / total_samples if total_samples else 0.0

    median_latency = float(np.median(latencies)) if latencies else 0.0
    p95_latency = float(np.percentile(latencies, 95)) if latencies else 0.0

    per_noise_summary: dict[str, dict[str, Any]] = {}
    for noise_label, group in sorted(samples_by_noise.items()):
        cnt = len(group)
        per_noise_summary[noise_label] = {
            "samples": cnt,
            "mean_wer": round(sum(s["wer"] for s in group) / cnt, 4) if cnt else 0.0,
            "mean_cer": round(sum(s["cer"] for s in group) / cnt, 4) if cnt else 0.0,
            "details": group,
        }

    config_result = {
        "config_name": config_name,
        "config_params": config_params,
        "total_samples": total_samples,
        "calls_made": calls_made,
        "mean_wer": round(mean_wer, 4),
        "mean_cer": round(mean_cer, 4),
        "median_latency_ms": round(median_latency, 1),
        "p95_latency_ms": round(p95_latency, 1),
        "empty_transcripts": empty_transcripts,
        "errors_count": errors_count,
        "is_tooling_check": is_mock,
        "noise_levels": per_noise_summary,
    }
    return config_result, calls_made


def run_stt_evaluation(
    audio_dir: Path,
    manifest_path: Path | None = None,
    configs_path: Path | None = None,
    adapter_name: str | None = None,
    output_dir: Path | None = None,
    dry_run: bool = False,
    max_calls: int | None = None,
) -> dict[str, Any]:
    from app.settings import Settings

    settings = Settings(config_dir=REPO_ROOT / "config")
    resolved_adapter = adapter_name or settings.stt_provider

    # Determine manifest
    effective_manifest = manifest_path or (audio_dir / "manifest.jsonl")
    clips: list[dict[str, Any]] = []

    if effective_manifest.is_file():
        clips = load_manifest(effective_manifest, audio_dir)
    else:
        # Fallback to discovering audio files and sidecar .txt
        audio_files = sorted(
            [
                p
                for p in audio_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".webm", ".ogg")
            ]
        )
        for af in audio_files:
            sidecar = af.with_suffix(".txt")
            if sidecar.is_file():
                clips.append({
                    "file": str(af.relative_to(audio_dir)),
                    "path": af,
                    "reference": sidecar.read_text(encoding="utf-8").strip(),
                    "noise_label": detect_noise_level(af, audio_dir),
                    "expected_entries": None,
                })

    # Load configurations
    configs_list: list[dict[str, Any]] = []
    if configs_path and configs_path.is_file():
        configs_list = json.loads(configs_path.read_text(encoding="utf-8"))
    else:
        # Single default configuration from settings
        configs_list = [{
            "name": f"default_{resolved_adapter}",
            "model": settings.gnani_stt_model,
            "languages": settings.gnani_stt_languages,
            "format": settings.gnani_stt_format or "default",
            "context": bool(settings.gnani_stt_topic or settings.gnani_stt_keyterms),
            "topic": settings.gnani_stt_topic,
            "keyterms": settings.gnani_stt_keyterms,
        }]

    # Handle --dry-run
    if dry_run:
        total_calls_planned = len(configs_list) * len(clips)
        print("=" * 65)
        print("[DRY RUN] STT Evaluation Execution Plan")
        print("=" * 65)
        print(f"Audio directory:           {audio_dir}")
        print(f"Manifest file:             {effective_manifest if effective_manifest.is_file() else 'None (directory scan)'}")
        print(f"Valid audio clips found:   {len(clips)}")
        print(f"Configurations to run:     {len(configs_list)}")
        print(f"Total API calls planned:   {total_calls_planned}")
        print(f"Max calls cap:             {max_calls or 'None'}")
        print("\nConfigurations:")
        for idx, cfg in enumerate(configs_list, 1):
            print(f"  {idx}. {cfg.get('name', 'unnamed')} (model={cfg.get('model', 'default')}, lang={cfg.get('languages', 'bn-IN')}, format={cfg.get('format', 'default')})")
        print("=" * 65)
        return {
            "dry_run": True,
            "planned_calls": total_calls_planned,
            "clips_count": len(clips),
            "configs_count": len(configs_list),
        }

    if not clips:
        raise FileNotFoundError(f"No audio files or transcripts found in {audio_dir}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_by_config: list[dict[str, Any]] = []
    total_calls_executed = 0

    print("=" * 65)
    print(f"Running STT Evaluation [{resolved_adapter.upper()}] - {len(clips)} clips")
    print("Sequential execution across configurations (never parallel)")
    print("=" * 65)

    for cfg in configs_list:
        cfg_name = cfg.get("name", "unnamed_config")
        print(f"\n>> Evaluating Configuration: {cfg_name}")
        cfg_res, calls_made = run_single_config(
            config_name=cfg_name,
            config_params=cfg,
            clips=clips,
            adapter_name=resolved_adapter,
            max_calls=max_calls,
            current_call_count=total_calls_executed,
        )
        results_by_config.append(cfg_res)
        total_calls_executed += calls_made
        print(f"   Mean WER: {cfg_res['mean_wer']:.1%} | Mean CER: {cfg_res['mean_cer']:.1%} | Latency p50: {cfg_res['median_latency_ms']}ms, p95: {cfg_res['p95_latency_ms']}ms")

    report: dict[str, Any] = {
        "timestamp": timestamp,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "adapter": resolved_adapter,
        "notice": "small sample, indicative only",
        "total_clips": len(clips),
        "total_calls_executed": total_calls_executed,
        "configurations": results_by_config,
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
        print(f"\nSaved evaluation reports to:\n  JSON: {json_path}\n  Markdown: {md_path}")

    return report


def generate_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# STT Evaluation Report ({report['adapter']})",
        "",
        "> [!IMPORTANT]",
        f"> **Notice**: `{report['notice']}`. Accuracy figures require real field speech recordings.",
        "",
        f"- **Date**: `{report['date']}`",
        f"- **Timestamp**: `{report['timestamp']}`",
        f"- **Adapter**: `{report['adapter']}`",
        f"- **Total Clips**: `{report['total_clips']}`",
        f"- **API Calls Executed**: `{report['total_calls_executed']}`",
        "",
        "## Summary by Configuration",
        "",
        "| Configuration | Mean WER | Mean CER | Latency p50 (ms) | Latency p95 (ms) | Empty | Errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for cfg in report["configurations"]:
        lines.append(
            f"| `{cfg['config_name']}` | {cfg['mean_wer']:.1%} | {cfg['mean_cer']:.1%} | {cfg['median_latency_ms']} | {cfg['p95_latency_ms']} | {cfg['empty_transcripts']} | {cfg['errors_count']} |"
        )

    lines.extend([
        "",
        "## Breakdown by Noise Level",
        "",
    ])
    for cfg in report["configurations"]:
        lines.append(f"### Configuration: `{cfg['config_name']}`")
        lines.append("")
        lines.append("| Noise Level | Samples | Mean WER | Mean CER |")
        lines.append("|---|---|---|---|")
        for noise_label, n_data in sorted(cfg["noise_levels"].items()):
            lines.append(f"| `{noise_label}` | {n_data['samples']} | {n_data['mean_wer']:.1%} | {n_data['mean_cer']:.1%} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    run_stt_evaluation(
        audio_dir=args.audio_dir,
        manifest_path=args.manifest,
        configs_path=args.configs,
        adapter_name=args.adapter,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
        max_calls=args.max_calls,
    )


if __name__ == "__main__":
    main()
