"""Developer utility: Live round-trip check for Gnani STT (Prisma) and TTS (Timbre).

Usage:
    python scripts/gnani_live_check.py          # Prints safety warning and exits
    python scripts/gnani_live_check.py --yes    # Runs 1 live TTS call and 1 live STT call

DO NOT run with --yes unless you explicitly want to call live endpoints and consume credits.
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
from app.speech.gnani import GnaniError, GnaniPrismaSTT, GnaniTimbreTTS

# Reconfigure stdout and stderr to UTF-8 so Bengali prints reliably on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Gnani STT and TTS connectivity with a minimal live round-trip."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly confirm live Gnani API execution (consumes credits).",
    )
    args = parser.parse_args()

    if not args.yes:
        print("=" * 70)
        print("SAFETY WARNING: This script calls live Gnani Prisma and Timbre endpoints.")
        print("To confirm and run 1 live TTS call + 1 live STT call, pass the --yes flag:")
        print("    python scripts/gnani_live_check.py --yes")
        print("=" * 70)
        sys.exit(1)

    settings = get_settings()
    if not settings.gnani_api_key:
        print("ERROR: GNANI_API_KEY is not configured in .env or environment.")
        sys.exit(1)

    test_phrase = "নমস্কার দিদি"
    print(f"\n--- 1. Testing Gnani Timbre TTS ({settings.gnani_tts_model}, voice: {settings.gnani_tts_voice}) ---")
    print(f"Synthesizing text: '{test_phrase}'")

    tts = GnaniTimbreTTS(
        api_key=settings.gnani_api_key,
        base_url=settings.gnani_base_url,
        model=settings.gnani_tts_model,
        voice=settings.gnani_tts_voice,
        language=settings.gnani_tts_language,
        speed=settings.gnani_tts_speed,
        container=settings.gnani_tts_container,
        sample_rate=settings.gnani_tts_sample_rate,
        spoken_numbers=settings.gnani_tts_spoken_numbers,
        cache_dir=settings.tts_cache_dir,
        timeout_s=settings.gnani_timeout_s,
        allow_live=True,
    )

    t0 = time.perf_counter()
    speech = tts.speak(test_phrase, "bn")
    tts_ms = round((time.perf_counter() - t0) * 1000, 1)

    if not speech.audio_bytes or speech.tts_fallback:
        reason = speech.tts_fallback if speech.tts_fallback else "no audio bytes returned"
        print(f"FAILED: TTS did not return audio bytes (reason: {reason})")
        sys.exit(1)

    print(f"SUCCESS: Generated {len(speech.audio_bytes)} bytes in {tts_ms}ms (mime: {speech.mime})")

    print(f"\n--- 2. Testing Gnani Prisma STT ({settings.gnani_stt_model or 'prisma-v2.5'}) ---")
    stt = GnaniPrismaSTT(
        api_key=settings.gnani_api_key,
        base_url=settings.gnani_base_url,
        model=settings.gnani_stt_model,
        languages=settings.gnani_stt_languages,
        format_type=settings.gnani_stt_format,
        topic=settings.gnani_stt_topic,
        keyterms=settings.gnani_stt_keyterms,
        timeout_s=settings.gnani_timeout_s,
        allow_live=True,
    )

    t0 = time.perf_counter()
    try:
        transcript = stt.transcribe(speech.audio_bytes, speech.mime or "audio/mp3", "bn")
        stt_ms = round((time.perf_counter() - t0) * 1000, 1)
        print(f"SUCCESS: Transcribed in {stt_ms}ms")
        print(f"Result transcript: '{transcript.text}'")
        print(f"Confidence: {transcript.confidence}")
        print("\nLive check completed successfully.")
    except (GnaniError, OSError, RuntimeError) as exc:
        print(f"FAILED: STT transcription failed (reason: {exc})")
        sys.exit(1)


if __name__ == "__main__":
    main()
