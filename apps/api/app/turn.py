import base64
import re
import time
import wave
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app.clock import today_local
from app.dialogue.manager import SessionState, handle
from app.i18n import t
from app.repository import confirm_entry, create_entry
from app.speech.base import Speech
from app.speech.gnani import (
    GnaniAudioError,
    GnaniAuthError,
    GnaniError,
    GnaniQuotaError,
    GnaniRateLimitError,
    GnaniServerError,
    GnaniTimeoutError,
)
from app.speech.providers import get_stt, get_tts

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ALLOWED_MIMES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/webm", "audio/ogg", "audio/mpeg"}

router = APIRouter()


class TextTurn(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN.pattern)
    text: str = Field(min_length=1, max_length=500)
    lang: str = Field(default="bn", pattern="^(bn|en)$")


def _error(status: int, key: str, **values: object) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"bn": t(f"errors.{key}", "bn", **values), "en": t(f"errors.{key}", "en", **values)},
    )


def _wav_seconds(audio: bytes) -> float | None:
    try:
        with wave.open(BytesIO(audio)) as wav:
            return wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError):
        return None


def _speech_response(tts_result: Speech) -> str | None:
    if tts_result.audio_bytes is None:
        return None
    return base64.b64encode(tts_result.audio_bytes).decode("ascii")


@router.post("/turn")
async def turn(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    client = request.client.host if request.client else "unknown"
    if not request.app.state.rate_limiter.allow(client):
        raise _error(429, "rate_limited")

    content_type = request.headers.get("content-type", "")
    audio_bytes: bytes | None = None
    mime = ""
    lang_hint = "bn"
    if content_type.startswith("application/json"):
        try:
            body = TextTurn.model_validate(await request.json())
        except (ValidationError, ValueError) as exc:
            raise _error(422, "invalid_request") from exc
        session_id, text, lang_hint = body.session_id, body.text, body.lang
    else:
        form = await request.form()
        session_id = str(form.get("session_id", ""))
        if not SESSION_ID_PATTERN.match(session_id):
            raise _error(422, "invalid_request")
        upload = form.get("audio")
        text = str(form.get("text", ""))
        lang_hint = str(form.get("lang", "bn"))
        if lang_hint not in ("bn", "en"):
            raise _error(422, "invalid_request")
        if upload is not None and hasattr(upload, "read"):
            audio_bytes = await upload.read()
            mime = getattr(upload, "content_type", "") or ""
            if len(audio_bytes) > settings.max_audio_bytes:
                raise _error(413, "audio_too_large", limit=settings.max_audio_bytes)
            if mime not in ALLOWED_MIMES:
                raise _error(415, "unsupported_audio")
            seconds = _wav_seconds(audio_bytes) if "wav" in mime else None
            if seconds is not None and seconds > settings.max_audio_seconds:
                raise _error(413, "audio_too_long", limit=settings.max_audio_seconds)
        if not audio_bytes and not text:
            raise _error(422, "empty_input")

    timings: dict[str, float] = {}
    stt = get_stt(settings, mock_text=text)
    started = time.perf_counter()
    try:
        transcript = stt.transcribe(audio_bytes or b"", mime, lang_hint)
    except NotImplementedError as exc:
        raise _error(503, "provider_not_implemented") from exc
    except GnaniAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "bn": "Gnani পরিচয় যাচাইকরণ ব্যর্থ হয়েছে।",
                "en": "Gnani STT authentication failed.",
            },
        ) from exc
    except GnaniQuotaError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "bn": "Gnani ক্রেডিট শেষ হয়ে গেছে। অনুগ্রহ করে টাইপ করে লিখুন।",
                "en": "Gnani credit exhausted. Please type your entry.",
            },
        ) from exc
    except GnaniRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "bn": "অনেক বেশি অনুরোধ। একটু পরে আবার চেষ্টা করুন।",
                "en": "Too many requests to Gnani STT. Please wait a moment and try again.",
            },
        ) from exc
    except GnaniTimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={
                "bn": "Gnani সংযোগের সময় শেষ হয়ে গেছে। অনুগ্রহ করে টাইপ করে লিখুন।",
                "en": "Gnani STT timed out. Please type your entry.",
            },
        ) from exc
    except GnaniAudioError as exc:
        msg = str(exc)
        if "30 seconds" in msg:
            raise _error(413, "audio_too_long", limit=30) from exc
        if "only supports WAV" in msg or "ওয়েবএম" in msg:
            raise HTTPException(
                status_code=415,
                detail={
                    "bn": "Gnani STT ওয়েবএম সমর্থন করে না, WAV পাঠান।",
                    "en": "Gnani STT only supports WAV/MP3/OGG; please send WAV.",
                },
            ) from exc
        raise HTTPException(
            status_code=400,
            detail={"bn": "অডিও ফরম্যাট সমর্থিত নয় বা অসম্পূর্ণ।", "en": msg},
        ) from exc
    except (GnaniServerError, GnaniError) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "bn": "Gnani স্পিচ সার্ভারে সমস্যা হয়েছে। অনুগ্রহ করে টাইপ করে লিখুন।",
                "en": "Gnani STT service error. Please type your entry.",
            },
        ) from exc

    timings["stt"] = round((time.perf_counter() - started) * 1000, 1)
    transcript_text = transcript.text or text

    state: SessionState = request.app.state.sessions.get(session_id)
    state = state.model_copy(update={"lang": lang_hint})
    started = time.perf_counter()
    extractor = request.app.state.extractor
    extractor.last_ms = 0.0
    result = handle(state, transcript_text, today_local(settings.tz), extractor=extractor)
    timings["nlu"] = round((time.perf_counter() - started) * 1000, 1)
    timings["llm"] = extractor.last_ms
    nlu_name = extractor.last_source if extractor.last_ms > 0 else extractor.name

    if result.ui_hint == "saved":
        with request.app.state.session_factory() as db:
            for draft in result.entries:
                entry = create_entry(
                    db,
                    task_type=draft.task_type,
                    event_date=draft.event_date,
                    count=draft.count,
                    beneficiary_ref=draft.beneficiary_ref,
                    notes=draft.notes,
                    source_transcript=transcript_text,
                    confidence=draft.confidence,
                )
                confirm_entry(db, entry.id)

    request.app.state.sessions.put(session_id, result.new_state)

    tts = get_tts(settings)
    started = time.perf_counter()
    try:
        speech = tts.speak(result.response_text, result.new_state.lang)
    except NotImplementedError as exc:
        raise _error(503, "provider_not_implemented") from exc
    timings["tts"] = round((time.perf_counter() - started) * 1000, 1)

    if settings.stt_provider == "gnani":
        stt_name = f"gnani ({settings.gnani_stt_model or 'prisma-v2.5'})"
    else:
        stt_name = stt.name

    if settings.tts_provider == "gnani":
        extra_parts = [settings.gnani_tts_voice]
        if speech.cached:
            extra_parts.append("cached")
        if speech.tts_fallback:
            if isinstance(speech.tts_fallback, str):
                short_reason = speech.tts_fallback
                if len(short_reason) > 40:
                    short_reason = short_reason[:37] + "..."
                extra_parts.append(f"fallback: {short_reason}")
            else:
                extra_parts.append("fallback")
        tts_name = f"gnani ({', '.join(extra_parts)})"
    else:
        tts_name = tts.name

    return {
        "transcript": transcript_text,
        "entries": [draft.model_dump(mode="json") for draft in result.entries],
        "response_text": result.response_text,
        "response_audio": _speech_response(speech),
        "ui_hint": result.ui_hint,
        "timings_ms": timings,
        "providers": {"stt": stt_name, "tts": tts_name, "nlu": nlu_name},
        "tts_fallback": speech.tts_fallback,
        "dev": {
            "stt_model": (
                settings.gnani_stt_model or "prisma-v2.5"
                if settings.stt_provider == "gnani"
                else "mock"
            ),
            "stt_format": (
                settings.gnani_stt_format or "default"
                if settings.stt_provider == "gnani"
                else "n/a"
            ),
            "stt_request_id": transcript.request_id,
            "tts_model": (
                settings.gnani_tts_model if settings.tts_provider == "gnani" else "browser"
            ),
            "tts_voice": settings.gnani_tts_voice if settings.tts_provider == "gnani" else "n/a",
            "tts_cached": speech.cached,
            "tts_request_id": speech.request_id,
            "tts_fallback": speech.tts_fallback,
        },
    }
