"""CLI script to test sentence extraction and print matched details."""
import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

# Ensure app package is importable
app_dir = Path(__file__).resolve().parents[1]
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from app.clock import today_local  # noqa: E402
from app.config_loader import default_lexicon  # noqa: E402
from app.nlu.extract import extract, find_matched_keywords  # noqa: E402
from app.nlu.text import normalise  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python try_extract.py <sentence>")
        sys.exit(1)

    sentence = " ".join(sys.argv[1:])
    today = today_local()
    lexicon = default_lexicon()

    extraction = extract(sentence, today, lexicon)
    norm = normalise(sentence)
    matched = find_matched_keywords(norm, lexicon)

    if not extraction.entries:
        print("Task: None")
        print("Count: None")
        print("Date: None")
        print("Confidence: 0.0")
        print(f"Matched keywords: {matched}")
        return

    for idx, entry in enumerate(extraction.entries):
        if len(extraction.entries) > 1:
            print(f"--- Entry {idx + 1} ---")
        print(f"Task: {entry.task_type}")
        print(f"Count: {entry.count}")
        print(f"Date: {entry.event_date.isoformat()}")
        print(f"Confidence: {entry.confidence:.2f}")
    print(f"Matched keywords: {matched}")


if __name__ == "__main__":
    main()
