#!/usr/bin/env python3
"""Run extraction evaluation on eval/utterances.jsonl.

Evaluates utterances and multi-turn dialogues against the real extractor and
dialogue manager without modifying their logic. Reports exact-match rate,
per-field accuracy, clinical refusal rate, and detailed failures.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.nlu.llm import Extractor

# Ensure apps/api is in the Python module search path.
REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run extraction evaluation.")
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "eval" / "utterances.jsonl",
        help="Path to evaluation utterances jsonl",
    )
    parser.add_argument(
        "--provider",
        choices=["rules", "openai"],
        default="rules",
        help="NLU extractor provider to evaluate (default: rules)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "eval" / "results",
        help="Directory to save JSON and Markdown evaluation results",
    )
    return parser.parse_args()


def load_extractor(provider: str) -> Extractor:
    from app.nlu.llm import RulesExtractor, get_extractor
    from app.settings import Settings

    if provider == "rules":
        return RulesExtractor()
    if provider == "openai":
        settings = Settings(config_dir=REPO_ROOT / "config")
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not configured.")
        return get_extractor(settings)
    raise ValueError(f"Unknown provider: {provider}")


def evaluate_item(
    item: dict[str, Any], extractor: Extractor
) -> tuple[bool, dict[str, Any], dict[str, Any]]:
    from app.dialogue.manager import SessionState, handle
    today = datetime.strptime(item["today"], "%Y-%m-%d").date()
    exp = item["expected"]
    exp_refusal = bool(exp.get("refusal", False))
    exp_entries = [
        {
            "task_type": e["task_type"],
            "count": e["count"],
            "event_date": e["event_date"],
            "beneficiary_ref": e.get("beneficiary_ref"),
            "date_ambiguous": bool(e.get("date_ambiguous", False)),
        }
        for e in exp.get("entries", [])
    ]

    if "turns" in item:
        # Multi-turn dialogue: run sequentially through DialogueManager.handle
        state = SessionState()
        last_hint = "idle"
        last_entries: list[Any] = []
        for turn_text in item["turns"]:
            res = handle(state, turn_text, today, extractor=extractor)
            state = res.new_state
            last_hint = res.ui_hint
            if res.entries:
                last_entries = res.entries

        actual_refusal = (last_hint == "refusal")
        actual_entries = [
            {
                "task_type": d.task_type,
                "count": d.count,
                "event_date": d.event_date.isoformat() if d.event_date else None,
                "beneficiary_ref": d.beneficiary_ref,
                "date_ambiguous": bool(d.date_ambiguous),
            }
            for d in last_entries
        ]
    else:
        # Single-turn utterance: run through the extractor
        text = item["text"]
        extraction = extractor.extract(text, today)
        actual_refusal = extraction.clinical_refusal is not None
        actual_entries = [
            {
                "task_type": e.task_type,
                "count": e.count,
                "event_date": e.event_date.isoformat() if e.event_date else None,
                "beneficiary_ref": e.beneficiary_ref,
                "date_ambiguous": bool(e.date_ambiguous),
            }
            for e in extraction.entries
        ]

    is_exact_match = (actual_refusal == exp_refusal) and (actual_entries == exp_entries)

    actual_output = {
        "entries": actual_entries,
        "refusal": actual_refusal,
    }
    normalized_expected = {
        "entries": exp_entries,
        "refusal": exp_refusal,
    }

    return is_exact_match, actual_output, normalized_expected


def run_eval(input_file: Path, provider: str, output_dir: Path) -> dict[str, Any]:
    extractor = load_extractor(provider)
    items: list[dict[str, Any]] = []
    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    total_items = len(items)
    exact_matches = 0
    clinical_total = 0
    clinical_refusals = 0
    failures: list[dict[str, Any]] = []

    field_correct = {
        "task_type": 0,
        "count": 0,
        "date": 0,
        "beneficiary_ref": 0,
    }
    total_expected_entries = 0

    type_stats: dict[str, dict[str, int]] = {}

    for item in items:
        item_type = item.get("type", "unknown")
        if item_type not in type_stats:
            type_stats[item_type] = {"total": 0, "exact_match": 0}
        type_stats[item_type]["total"] += 1

        is_match, actual_output, normalized_expected = evaluate_item(item, extractor)

        if is_match:
            exact_matches += 1
            type_stats[item_type]["exact_match"] += 1
        else:
            failures.append(
                {
                    "id": item["id"],
                    "type": item["type"],
                    "input": item.get("text") or item.get("turns"),
                    "expected": normalized_expected,
                    "actual": actual_output,
                }
            )

        # Clinical refusal rate check
        if item_type == "clinical":
            clinical_total += 1
            if actual_output["refusal"]:
                clinical_refusals += 1

        # Per-field accuracy check against expected entries
        exp_entries = normalized_expected["entries"]
        act_entries = actual_output["entries"]
        for idx, exp_e in enumerate(exp_entries):
            total_expected_entries += 1
            if idx < len(act_entries):
                act_e = act_entries[idx]
                if act_e.get("task_type") == exp_e.get("task_type"):
                    field_correct["task_type"] += 1
                if act_e.get("count") == exp_e.get("count"):
                    field_correct["count"] += 1
                if act_e.get("event_date") == exp_e.get("event_date"):
                    field_correct["date"] += 1
                if act_e.get("beneficiary_ref") == exp_e.get("beneficiary_ref"):
                    field_correct["beneficiary_ref"] += 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = {
        "timestamp": timestamp,
        "provider": provider,
        "total_items": total_items,
        "exact_matches": exact_matches,
        "exact_match_rate": round(exact_matches / total_items, 4) if total_items else 0.0,
        "clinical_total": clinical_total,
        "clinical_refusals": clinical_refusals,
        "clinical_refusal_rate": (
            round(clinical_refusals / clinical_total, 4) if clinical_total else 0.0
        ),
        "total_expected_entries": total_expected_entries,
        "per_field_accuracy": {
            k: {
                "correct": v,
                "total": total_expected_entries,
                "rate": (
                    round(v / total_expected_entries, 4) if total_expected_entries else 0.0
                ),
            }
            for k, v in field_correct.items()
        },
        "type_breakdown": type_stats,
        "failure_count": len(failures),
        "failures": failures,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"extraction_eval_{provider}_{timestamp}.json"
    md_path = output_dir / f"extraction_eval_{provider}_{timestamp}.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    md_content = generate_markdown_report(summary)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(md_content)

    print_report(summary, json_path, md_path)
    return summary


def generate_markdown_report(summary: dict[str, Any]) -> str:
    match_str = f"{summary['exact_matches']}/{summary['total_items']}"
    match_pct = f"{summary['exact_match_rate']:.1%}"
    refusal_str = f"{summary['clinical_refusals']}/{summary['clinical_total']}"
    refusal_pct = f"{summary['clinical_refusal_rate']:.1%}"
    lines = [
        f"# Extraction Evaluation Report ({summary['provider']})",
        "",
        f"- **Timestamp**: `{summary['timestamp']}`",
        f"- **Provider**: `{summary['provider']}`",
        f"- **Total Items**: `{summary['total_items']}`",
        f"- **Overall Exact Match Rate**: {match_str} ({match_pct})",
        f"- **Clinical Refusal Rate**: {refusal_str} ({refusal_pct})",
        "",
        "## Per-Field Accuracy",
        "",
        "| Field | Correct | Total Entries | Accuracy |",
        "|---|---|---|---|",
    ]
    for field, stats in summary["per_field_accuracy"].items():
        lines.append(
            f"| `{field}` | {stats['correct']} | {stats['total']} | {stats['rate']:.1%} |"
        )

    lines.extend([
        "",
        "## Breakdown by Item Type",
        "",
        "| Type | Total | Exact Match | Match Rate |",
        "|---|---|---|---|",
    ])
    for item_type, stats in sorted(summary["type_breakdown"].items()):
        rate = stats["exact_match"] / stats["total"] if stats["total"] else 0.0
        lines.append(
            f"| `{item_type}` | {stats['total']} | {stats['exact_match']} | {rate:.1%} |"
        )

    lines.extend([
        "",
        f"## Failures ({summary['failure_count']})",
        "",
    ])
    if not summary["failures"]:
        lines.append("No failures recorded. All evaluation items passed exact match.")
    else:
        for idx, fail in enumerate(summary["failures"], 1):
            lines.append(f"### Failure {idx}: [{fail['id']}] ({fail['type']})")
            lines.append(f"- **Input**: `{fail['input']}`")
            lines.append(f"- **Expected**: `{json.dumps(fail['expected'], ensure_ascii=False)}`")
            lines.append(f"- **Actual**: `{json.dumps(fail['actual'], ensure_ascii=False)}`")
            lines.append("")

    return "\n".join(lines) + "\n"


def print_report(summary: dict[str, Any], json_path: Path, md_path: Path) -> None:
    match_str = f"{summary['exact_matches']}/{summary['total_items']}"
    match_pct = f"{summary['exact_match_rate']:.1%}"
    refusal_str = f"{summary['clinical_refusals']}/{summary['clinical_total']}"
    refusal_pct = f"{summary['clinical_refusal_rate']:.1%}"
    print("=" * 60)
    print(f"Extraction Evaluation Results [{summary['provider']}]")
    print("=" * 60)
    print(f"Total items:              {summary['total_items']}")
    print(f"Exact matches:            {match_str} ({match_pct})")
    print(f"Clinical refusal rate:    {refusal_str} ({refusal_pct})")
    print("\nPer-field accuracy:")
    for field, stats in summary["per_field_accuracy"].items():
        print(f"  {field:16s}: {stats['correct']}/{stats['total']} ({stats['rate']:.1%})")

    print("\nType breakdown:")
    for item_type, stats in sorted(summary["type_breakdown"].items()):
        rate = stats["exact_match"] / stats["total"] if stats["total"] else 0.0
        print(f"  {item_type:16s}: {stats['exact_match']}/{stats['total']} ({rate:.1%})")

    print(f"\nFailures: {summary['failure_count']}")
    print("Results saved to:")
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")
    print("=" * 60)


def main() -> None:
    args = parse_args()
    run_eval(args.input, args.provider, args.output_dir)


if __name__ == "__main__":
    main()
