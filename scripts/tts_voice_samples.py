"""Developer utility: Generate voice comparison samples for Gnani Timbre TTS.

Synthesizes a representative Bengali work diary summary in 6 voices:
Shivani, Riyaa, Kalpana, Chetana, Devansh, Harshad.

Usage:
    python scripts/tts_voice_samples.py          # Prints safety warning and exits
    python scripts/tts_voice_samples.py --yes    # Synthesizes samples into eval/audio/voices/
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure apps/api is in Python path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.settings import get_settings
from app.speech.gnani import GnaniTimbreTTS

VOICES = [
    "Shivani",
    "Riyaa",
    "Kalpana",
    "Chetana",
    "Devansh",
    "Harshad",
]

SAMPLE_SENTENCE = (
    "নমস্কার দিদি, আজ আপনি ৩ জন শিশুর টিকাকরণ এবং ২ জন গর্ভবতী মায়ের এএনসি ভিজিট সম্পন্ন করেছেন।"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synthesize voice samples across multiple Gnani Timbre voices."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm live synthesis calls to Gnani API (consumes credits).",
    )
    args = parser.parse_args()

    if not args.yes:
        print("=" * 70)
        print("SAFETY WARNING: This script calls the live Gnani Timbre TTS endpoint")
        print(f"for {len(VOICES)} different voices, consuming API credits.")
        print("To confirm and run, pass the --yes flag:")
        print("    python scripts/tts_voice_samples.py --yes")
        print("=" * 70)
        sys.exit(1)

    settings = get_settings()
    if not settings.gnani_api_key:
        print("ERROR: GNANI_API_KEY is not configured in .env or environment.")
        sys.exit(1)

    out_dir = REPO_ROOT / "eval" / "audio" / "voices"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Synthesizing voice samples into: {out_dir}")
    print(f"Sample text: '{SAMPLE_SENTENCE}'\n")

    for voice in VOICES:
        print(f"Synthesizing voice: {voice} ...", end=" ", flush=True)
        tts = GnaniTimbreTTS(
            api_key=settings.gnani_api_key,
            base_url=settings.gnani_base_url,
            model="timbre-v3.0",
            voice=voice,
            language="bn-IN",
            speed=1.0,
            container="mp3",
            sample_rate=24000,
            spoken_numbers=True,
            cache_dir=settings.tts_cache_dir,
            timeout_s=settings.gnani_timeout_s,
            allow_live=True,
        )

        t0 = time.perf_counter()
        speech = tts.speak(SAMPLE_SENTENCE, "bn")
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        if not speech.audio_bytes or speech.tts_fallback:
            print(f"FAILED (tts_fallback={speech.tts_fallback})")
            continue

        target_file = out_dir / f"{voice.lower()}.mp3"
        target_file.write_bytes(speech.audio_bytes)
        print(f"DONE ({len(speech.audio_bytes)} bytes in {elapsed_ms}ms) -> {target_file.name}")

    print("\nAll voice samples generated successfully.")


if __name__ == "__main__":
    main()

