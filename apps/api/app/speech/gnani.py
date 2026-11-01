"""Gnani speech adapter implementations for Prisma STT and Timbre TTS.

Documentation reference: https://docs.gnani.ai
- Prisma STT: POST https://api.vachana.ai/stt/v3 (multipart/form-data)
- Timbre TTS: POST https://api.vachana.ai/api/v1/tts/inference (JSON)

Privacy & Safety:
- Never log audio bytes, transcripts, or API keys.
- Safe logging only: request_id, model, latency_ms, status.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx

from app.speech.base import Speech, Transcript
from app.speech.spoken_bn import number_to_spoken_bn

logger = logging.getLogger("didinotes.gnani")

SUPPORTED_STT_MIMES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/aac",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mp4",
}


class GnaniError(Exception):
    """Base exception for Gnani speech adapter errors."""


class GnaniAuthError(GnaniError):
    """Authentication or authorization failure (401/403)."""


class GnaniQuotaError(GnaniError):
    """Credit or quota exhausted (402)."""


class GnaniRateLimitError(GnaniError):
    """Rate limit exceeded (429)."""


class GnaniTimeoutError(GnaniError):
    """Request timed out or 504 upstream timeout."""


class GnaniServerError(GnaniError):
    """Gnani server failure (5xx)."""


class GnaniAudioError(GnaniError):
    """Unsupported audio format, duration > 30s, or truncated audio."""


def _wav_duration(audio_bytes: bytes) -> float | None:
    try:
        with wave.open(BytesIO(audio_bytes)) as wav:
            return wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError):
        return None


def _extract_gnani_error_message(response: httpx.Response) -> str:
    """Extract error message from Gnani response payload without exposing sensitive data."""
    try:
        data = response.json()
        if isinstance(data, dict):
            # Direct message field
            if "message" in data and isinstance(data["message"], str) and data["message"].strip():
                return data["message"].strip()
            # Error object with message: {"error": {"message": "..."}}
            error_val = data.get("error")
            if isinstance(error_val, dict) and "message" in error_val:
                return str(error_val["message"]).strip()
            if isinstance(error_val, str) and error_val.strip():
                return error_val.strip()
            # Detail object: {"detail": {"message": "..."}} or {"detail": "..."}
            detail_val = data.get("detail")
            if isinstance(detail_val, dict) and "message" in detail_val:
                return str(detail_val["message"]).strip()
            if isinstance(detail_val, str) and detail_val.strip():
                return detail_val.strip()
            # FastAPI validation error list: {"detail": [{"loc": [...], "msg": "..."}]}
            if isinstance(detail_val, list) and detail_val:
                first = detail_val[0]
                if isinstance(first, dict) and "msg" in first:
                    loc = " -> ".join(str(x) for x in first.get("loc", []))
                    msg = str(first["msg"])
                    return f"{msg} at {loc}" if loc else msg
                return str(detail_val[0])
    except Exception:
        pass
    text = response.text.strip()
    return text if text else f"HTTP {response.status_code}"


class GnaniPrismaSTT:
    """Gnani Prisma STT adapter implementing SpeechToText."""

    name = "gnani"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.vachana.ai",
        model: str = "",
        languages: str = "bn-IN",
        format_type: str = "",
        topic: str = "",
        keyterms: str = "",
        timeout_s: float = 30.0,
        max_concurrency: int = 1,
        transport: httpx.BaseTransport | None = None,
        allow_live: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = (
            base_url.strip() if base_url and str(base_url).strip() else "https://api.vachana.ai"
        ).rstrip("/")
        self.model = model
        self.languages = languages or "bn-IN"
        self.format_type = format_type
        self.topic = topic
        self.keyterms = keyterms
        self.timeout_s = timeout_s
        self.semaphore = threading.Semaphore(max(1, max_concurrency))
        self.transport = transport
        self.allow_live = allow_live

    def transcribe(self, audio_bytes: bytes, mime: str, lang_hint: str) -> Transcript:
        # Live network calls are disabled unless a test transport (MockTransport)
        # or explicit allow_live=True is provided.
        if self.transport is None and not self.allow_live:
            raise NotImplementedError(
                "Gnani live calls are disabled without httpx.MockTransport or allow_live=True"
            )

        if not self.api_key:
            raise GnaniAuthError("GNANI_API_KEY is not configured")

        clean_mime = (mime or "").lower().split(";")[0].strip()
        if clean_mime == "audio/webm" or clean_mime not in SUPPORTED_STT_MIMES:
            raise GnaniAudioError("Gnani STT only supports WAV/MP3/OGG; please send WAV")

        if "wav" in clean_mime:
            duration = _wav_duration(audio_bytes)
            if duration is not None and duration > 30.0:
                raise GnaniAudioError("Audio duration exceeds 30 seconds limit for Gnani STT")

        request_id = str(uuid.uuid4())
        headers = {
            "X-API-Key-ID": self.api_key,
            "X-API-Request-ID": request_id,
        }

        form_data: dict[str, str] = {
            "language_code": self.languages,
        }
        if self.model:
            form_data["model"] = self.model
        if self.format_type:
            form_data["format"] = self.format_type
        if self.topic:
            form_data["topic"] = self.topic
        if self.keyterms:
            try:
                # Gnani expects keyterms as JSON array
                if self.keyterms.strip().startswith("["):
                    form_data["keyterms"] = self.keyterms
                else:
                    items = [k.strip() for k in self.keyterms.split(",") if k.strip()]
                    form_data["keyterms"] = json.dumps(items)
            except Exception:
                form_data["keyterms"] = self.keyterms

        ext = (
            "wav"
            if "wav" in clean_mime
            else ("mp3" if ("mpeg" in clean_mime or "mp3" in clean_mime) else "ogg")
        )
        files = {
            "audio_file": (f"recording.{ext}", audio_bytes, clean_mime),
        }

        url = f"{self.base_url}/stt/v3"
        backoffs = [0.5, 1.0]
        max_attempts = len(backoffs) + 1

        with self.semaphore:
            for attempt in range(max_attempts):
                started = time.perf_counter()
                try:
                    with httpx.Client(transport=self.transport, timeout=self.timeout_s) as client:
                        response = client.post(url, headers=headers, data=form_data, files=files)
                except (httpx.TimeoutException, httpx.ConnectTimeout) as exc:
                    latency = round((time.perf_counter() - started) * 1000, 1)
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": 504,
                    }
                    logger.error("gnani stt timeout", extra=extra)
                    raise GnaniTimeoutError("Gnani STT timed out") from exc
                except httpx.RequestError as exc:
                    latency = round((time.perf_counter() - started) * 1000, 1)
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": 502,
                    }
                    logger.error("gnani stt network error", extra=extra)
                    raise GnaniServerError(f"Gnani STT network error: {exc}") from exc

                latency = round((time.perf_counter() - started) * 1000, 1)
                status = response.status_code

                if status == 200:
                    try:
                        data = response.json()
                    except Exception as exc:
                        extra = {
                            "request_id": request_id,
                            "model": self.model,
                            "latency_ms": latency,
                            "status": 502,
                        }
                        logger.error("gnani stt invalid json", extra=extra)
                        raise GnaniServerError("Invalid JSON returned by Gnani STT") from exc

                    resp_req_id = data.get("request_id") or request_id
                    resp_model = data.get("model") or self.model or "prisma"
                    extra = {
                        "request_id": resp_req_id,
                        "model": resp_model,
                        "latency_ms": latency,
                        "status": 200,
                    }
                    logger.info("gnani stt success", extra=extra)

                    if data.get("truncated") is True:
                        logger.warning(
                            "gnani stt truncated",
                            extra={"request_id": resp_req_id, "model": resp_model, "status": 200},
                        )
                        raise GnaniAudioError("Audio was truncated by STT service")

                    transcript_text = data.get("transcript") or ""
                    return Transcript(text=transcript_text, confidence=None, request_id=resp_req_id)

                # Handle errors
                if status in (401, 403):
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": status,
                    }
                    logger.error("gnani stt auth error", extra=extra)
                    raise GnaniAuthError("Gnani STT authentication failed")
                if status == 402:
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": 402,
                    }
                    logger.error("gnani stt quota exhausted", extra=extra)
                    raise GnaniQuotaError("Gnani credit exhausted")
                if status == 429:
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": 429,
                    }
                    logger.error("gnani stt rate limited", extra=extra)
                    raise GnaniRateLimitError("Gnani STT rate limited")
                if status == 504:
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": 504,
                    }
                    logger.error("gnani stt upstream timeout", extra=extra)
                    raise GnaniTimeoutError("Gnani STT upstream timeout")
                if 500 <= status < 600:
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "request_id": request_id,
                        "model": self.model,
                        "latency_ms": latency,
                        "status": status,
                    }
                    logger.error("gnani stt server error", extra=extra)
                    raise GnaniServerError(f"Gnani STT server error: {status}")

                # Non-retryable client errors (400, 422, etc.)
                extra = {
                    "request_id": request_id,
                    "model": self.model,
                    "latency_ms": latency,
                    "status": status,
                }
                logger.error("gnani stt client error", extra=extra)
                raise GnaniError(f"Gnani STT failed with status {status}")

        raise GnaniServerError("Gnani STT request failed after retries")


class GnaniTimbreTTS:
    """Gnani Timbre TTS adapter implementing TextToSpeech."""

    name = "gnani"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.vachana.ai",
        model: str = "timbre-v3.0",
        voice: str = "Shivani",
        language: str = "bn-IN",
        speed: float = 1.0,
        container: str = "mp3",
        sample_rate: int = 24000,
        spoken_numbers: bool = True,
        cache_dir: Path | str = ".cache/tts",
        timeout_s: float = 30.0,
        max_concurrency: int = 1,
        transport: httpx.BaseTransport | None = None,
        allow_live: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = (
            base_url.strip() if base_url and str(base_url).strip() else "https://api.vachana.ai"
        ).rstrip("/")
        self.model = model
        self.voice = voice
        self.language = language or "bn-IN"
        self.speed = speed
        self.container = container.lower()
        self.sample_rate = sample_rate
        self.spoken_numbers = spoken_numbers
        self.cache_dir = Path(cache_dir)
        self.timeout_s = timeout_s
        self.semaphore = threading.Semaphore(max(1, max_concurrency))
        self.transport = transport
        self.allow_live = allow_live

    def speak(self, text: str, lang: str) -> Speech:
        if not text:
            return Speech(audio_bytes=None, mime=None, use_browser_tts=True, tts_fallback=False)

        # Preprocessing: convert numbers to Bengali words if enabled
        processed_text = number_to_spoken_bn(text) if self.spoken_numbers else text

        # Disk cache check
        cache_signature = (
            f"{self.model}:{self.voice}:{self.language}:{self.speed}:"
            f"{self.sample_rate}:{self.container}:{processed_text}"
        )
        cache_hash = hashlib.sha256(cache_signature.encode("utf-8")).hexdigest()
        cache_file = self.cache_dir / f"{cache_hash}.{self.container}"

        if cache_file.exists():
            try:
                cached_bytes = cache_file.read_bytes()
                logger.info("tts cache hit", extra={"model": self.model, "status": "cache_hit"})
                return Speech(
                    audio_bytes=cached_bytes,
                    mime=f"audio/{self.container}",
                    use_browser_tts=False,
                    tts_fallback=False,
                    cached=True,
                )
            except Exception as exc:
                logger.warning("Failed to read TTS cache file: %s", exc)

        # Fallback to browser TTS if live calls are disabled without transport or no key
        if (self.transport is None and not self.allow_live) or not self.api_key:
            reason = "api_key_missing" if not self.api_key else "live_calls_disabled"
            logger.info(
                "Gnani TTS disabled or key missing, falling back to browser TTS (%s)", reason
            )
            return Speech(audio_bytes=None, mime=None, use_browser_tts=True, tts_fallback=reason)

        # Validate container and configure audio_config
        if self.container == "mp3":
            audio_config: dict[str, Any] = {
                "sample_rate": self.sample_rate,
                "container": "mp3",
            }
        elif self.container == "wav":
            audio_config = {
                "sample_rate": self.sample_rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "pcm_s16le",
                "container": "wav",
            }
        else:
            reason = f"Unsupported TTS container: '{self.container}'. Supported: 'mp3', 'wav'."
            logger.warning("gnani tts invalid container config: %s", reason)
            return Speech(
                audio_bytes=None,
                mime=None,
                use_browser_tts=True,
                tts_fallback=reason,
            )

        url = f"{self.base_url}/api/v1/tts/inference"
        request_id = str(uuid.uuid4())
        headers = {
            "X-API-Key-ID": self.api_key,
            "X-API-Request-ID": request_id,
        }

        payload = {
            "text": processed_text,
            "model": self.model,
            "voice": self.voice,
            "language": self.language,
            "speed": self.speed,
            "audio_config": audio_config,
        }

        backoffs = [0.5, 1.0]
        max_attempts = len(backoffs) + 1

        with self.semaphore:
            for attempt in range(max_attempts):
                started = time.perf_counter()
                try:
                    with httpx.Client(transport=self.transport, timeout=self.timeout_s) as client:
                        response = client.post(url, headers=headers, json=payload)
                except (httpx.TimeoutException, httpx.ConnectTimeout):
                    latency = round((time.perf_counter() - started) * 1000, 1)
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "model": self.model,
                        "voice": self.voice,
                        "latency_ms": latency,
                        "status": 504,
                    }
                    logger.warning("gnani tts timeout, falling back to browser tts", extra=extra)
                    return Speech(
                        audio_bytes=None,
                        mime=None,
                        use_browser_tts=True,
                        tts_fallback="timeout (504)",
                    )
                except httpx.RequestError as exc:
                    latency = round((time.perf_counter() - started) * 1000, 1)
                    if attempt < len(backoffs):
                        time.sleep(backoffs[attempt])
                        continue
                    extra = {
                        "model": self.model,
                        "voice": self.voice,
                        "latency_ms": latency,
                        "status": 502,
                    }
                    logger.warning(
                        "gnani tts request error, falling back to browser tts: %s",
                        exc,
                        extra=extra,
                    )
                    return Speech(
                        audio_bytes=None,
                        mime=None,
                        use_browser_tts=True,
                        tts_fallback="network_error (502)",
                    )

                latency = round((time.perf_counter() - started) * 1000, 1)
                status = response.status_code

                if status == 200:
                    audio_bytes = response.content
                    try:
                        self.cache_dir.mkdir(parents=True, exist_ok=True)
                        cache_file.write_bytes(audio_bytes)
                    except Exception as exc:
                        logger.warning("Failed to write TTS cache file: %s", exc)

                    resp_req_id = (
                        response.headers.get("x-api-request-id")
                        or response.headers.get("x-request-id")
                        or request_id
                    )
                    extra = {
                        "request_id": resp_req_id,
                        "model": self.model,
                        "voice": self.voice,
                        "latency_ms": latency,
                        "status": 200,
                    }
                    logger.info("gnani tts success", extra=extra)
                    return Speech(
                        audio_bytes=audio_bytes,
                        mime=f"audio/{self.container}",
                        use_browser_tts=False,
                        tts_fallback=False,
                        cached=False,
                        request_id=resp_req_id,
                    )

                # Non-2xx response from Gnani
                resp_req_id = (
                    response.headers.get("x-api-request-id")
                    or response.headers.get("x-request-id")
                    or request_id
                )
                raw_msg = _extract_gnani_error_message(response)
                truncated_msg = raw_msg[:300] if len(raw_msg) > 300 else raw_msg

                logger.warning(
                    "gnani tts non-2xx response: status=%d request_id=%s message=%s",
                    status,
                    resp_req_id,
                    truncated_msg,
                    extra={
                        "status": status,
                        "request_id": resp_req_id,
                        "gnani_message": truncated_msg,
                    },
                )

                if status in (429, 500, 502, 503, 504) and attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                    continue

                fallback_reason = f"HTTP {status}: {truncated_msg}"
                return Speech(
                    audio_bytes=None,
                    mime=None,
                    use_browser_tts=True,
                    tts_fallback=fallback_reason,
                )

        return Speech(
            audio_bytes=None,
            mime=None,
            use_browser_tts=True,
            tts_fallback="failed_after_retries",
        )
