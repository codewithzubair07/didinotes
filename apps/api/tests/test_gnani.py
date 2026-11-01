"""Unit tests for Gnani Prisma STT, Timbre TTS, and Bengali spoken numbers.

All HTTP calls are mocked via httpx.MockTransport.
NEVER make live internet calls in these tests.
"""

from __future__ import annotations

import io
import json
import logging
import wave
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.factory import create_app
from app.main import validate_startup_settings
from app.settings import Settings
from app.speech.base import Speech, Transcript
from app.speech.gnani import (
    GnaniAudioError,
    GnaniAuthError,
    GnaniPrismaSTT,
    GnaniQuotaError,
    GnaniRateLimitError,
    GnaniTimbreTTS,
    GnaniTimeoutError,
)
from app.speech.spoken_bn import int_to_spoken_bn, number_to_spoken_bn


def make_wav_bytes(seconds: float) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# A3: Bengali Spoken Numbers Tests
# -----------------------------------------------------------------------------


def test_spoken_bn_numbers_lookup():
    assert int_to_spoken_bn(0) == "শূন্য"
    assert int_to_spoken_bn(1) == "এক"
    assert int_to_spoken_bn(2) == "দুই"
    assert int_to_spoken_bn(5) == "পাঁচ"
    assert int_to_spoken_bn(10) == "দশ"
    assert int_to_spoken_bn(19) == "উনিশ"
    assert int_to_spoken_bn(26) == "ছাব্বিশ"
    assert int_to_spoken_bn(85) == "পঁচাশি"
    assert int_to_spoken_bn(100) == "একশত"
    assert int_to_spoken_bn(2026) == "দুই হাজার ছাব্বিশ"


def test_number_to_spoken_bn_transformations():
    # Bengali digits
    assert number_to_spoken_bn("২ জন শিশু") == "দুই জন শিশু"
    assert number_to_spoken_bn("২৯ অক্টোবর") == "ঊনত্রিশ অক্টোবর"

    # ASCII digits
    assert number_to_spoken_bn("2026") == "দুই হাজার ছাব্বিশ"
    assert number_to_spoken_bn("aaj 2 jon ANC visit") == "aaj দুই jon ANC visit"

    # Currency
    assert number_to_spoken_bn("₹200") == "দুইশত টাকা"
    assert number_to_spoken_bn("200 taka") == "দুইশত টাকা"
    assert number_to_spoken_bn("200 টাকা") == "দুইশত টাকা"
    assert number_to_spoken_bn("₹ 500") == "পাঁচশত টাকা"

    # Non-numeric text strictly untouched
    assert number_to_spoken_bn("amar ki dose dite hobe") == "amar ki dose dite hobe"
    assert number_to_spoken_bn("") == ""


# -----------------------------------------------------------------------------
# A4: Gnani Prisma STT Tests
# -----------------------------------------------------------------------------


def test_stt_valid_response():
    recorded_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        assert request.headers["X-API-Key-ID"] == "test-key"
        assert "X-API-Request-ID" in request.headers
        assert request.url.path == "/stt/v3"
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req-123",
                "transcript": "আজ রীনার এএনসি ভিজিট করলাম",
                "model": "prisma-v3.0",
                "processing_time": 0.42,
            },
        )

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport, model="prisma-v3.0")
    result = stt.transcribe(make_wav_bytes(2.0), "audio/wav", "bn")

    assert isinstance(result, Transcript)
    assert result.text == "আজ রীনার এএনসি ভিজিট করলাম"
    assert result.confidence is None
    assert len(recorded_requests) == 1


def test_stt_empty_transcript_is_valid():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "transcript": ""})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    result = stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")

    assert result.text == ""
    assert result.confidence is None


def test_stt_truncated_audio_raises_audio_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "truncated": True, "transcript": "কাটা"})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    with pytest.raises(GnaniAudioError, match="truncated"):
        stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")


@pytest.mark.parametrize("status_code,exc_type", [(401, GnaniAuthError), (403, GnaniAuthError)])
def test_stt_auth_errors(status_code, exc_type):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": {"message": "Invalid key"}})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="bad-key", transport=transport)
    with pytest.raises(exc_type):
        stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")


def test_stt_quota_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"detail": {"message": "Insufficient balance"}})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    with pytest.raises(GnaniQuotaError):
        stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")


def test_stt_rate_limit_retry_success():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"detail": {"message": "Rate limit"}})
        return httpx.Response(200, json={"success": True, "transcript": "সফল"})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    result = stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")

    assert calls == 2
    assert result.text == "সফল"


def test_stt_rate_limit_retry_exhausted():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={"detail": {"message": "Rate limit"}})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    with pytest.raises(GnaniRateLimitError):
        stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")

    assert calls == 3  # Initial + 2 retries


def test_stt_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    with pytest.raises(GnaniTimeoutError):
        stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")


def test_stt_unsupported_webm_rejected_before_http():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"success": True})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    with pytest.raises(GnaniAudioError, match="Gnani STT only supports WAV/MP3/OGG"):
        stt.transcribe(b"dummy webm", "audio/webm", "bn")

    assert calls == 0


def test_stt_audio_over_30s_rejected_before_http():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"success": True})

    transport = httpx.MockTransport(handler)
    stt = GnaniPrismaSTT(api_key="test-key", transport=transport)
    long_wav = make_wav_bytes(31.0)
    with pytest.raises(GnaniAudioError, match="exceeds 30 seconds"):
        stt.transcribe(long_wav, "audio/wav", "bn")

    assert calls == 0


# -----------------------------------------------------------------------------
# A5: Gnani Timbre TTS Tests
# -----------------------------------------------------------------------------


def test_tts_valid_synthesis_and_disk_cache(tmp_path: Path):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["X-API-Key-ID"] == "test-key"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "timbre-v3.0"
        assert body["voice"] == "Shivani"
        return httpx.Response(200, content=b"FAKE_MP3_AUDIO_BYTES")

    transport = httpx.MockTransport(handler)
    tts = GnaniTimbreTTS(
        api_key="test-key",
        cache_dir=tmp_path / "tts",
        transport=transport,
    )

    # First call: cache miss, makes HTTP request, writes to cache
    result1 = tts.speak("নমস্কার", "bn")
    assert isinstance(result1, Speech)
    assert result1.audio_bytes == b"FAKE_MP3_AUDIO_BYTES"
    assert result1.mime == "audio/mp3"
    assert result1.use_browser_tts is False
    assert result1.tts_fallback is False
    assert result1.cached is False
    assert calls == 1

    # Second call: cache hit, 0 HTTP calls made
    result2 = tts.speak("নমস্কার", "bn")
    assert result2.audio_bytes == b"FAKE_MP3_AUDIO_BYTES"
    assert result2.cached is True
    assert calls == 1


def test_tts_spoken_numbers_transform_applied(tmp_path: Path):
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured_payloads.append(body)
        return httpx.Response(200, content=b"AUDIO")

    transport = httpx.MockTransport(handler)
    tts = GnaniTimbreTTS(
        api_key="test-key",
        cache_dir=tmp_path / "tts",
        spoken_numbers=True,
        transport=transport,
    )

    tts.speak("আজ 2 জন শিশু", "bn")
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["text"] == "আজ দুই জন শিশু"


def test_tts_failure_falls_back_to_browser(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Internal Error"})

    transport = httpx.MockTransport(handler)
    tts = GnaniTimbreTTS(
        api_key="test-key",
        cache_dir=tmp_path / "tts",
        transport=transport,
    )

    result = tts.speak("নমস্কার", "bn")
    assert result.audio_bytes is None
    assert result.use_browser_tts is True
    assert "HTTP 500" in str(result.tts_fallback)


# -----------------------------------------------------------------------------
# Privacy & Safe Logging Tests
# -----------------------------------------------------------------------------


def test_logging_never_exposes_secrets_audio_or_transcript(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
):
    secret_key = "SECRET_GNANI_API_KEY_xyz987"
    secret_transcript = "অতি গোপন তথ্য"
    audio_content = b"\x01\x02\x03\x04\x05\x06\x07\x08"

    def stt_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "request_id": "req-privacy", "transcript": secret_transcript},
        )

    def tts_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=audio_content)

    with caplog.at_level(logging.DEBUG):
        stt = GnaniPrismaSTT(
            api_key=secret_key,
            transport=httpx.MockTransport(stt_handler),
        )
        stt.transcribe(make_wav_bytes(1.0), "audio/wav", "bn")

        tts = GnaniTimbreTTS(
            api_key=secret_key,
            cache_dir=tmp_path / "tts",
            transport=httpx.MockTransport(tts_handler),
        )
        tts.speak(secret_transcript, "bn")

    all_logs = caplog.text
    assert secret_key not in all_logs
    assert secret_transcript not in all_logs
    assert str(audio_content) not in all_logs


# -----------------------------------------------------------------------------
# Startup Validation Tests
# -----------------------------------------------------------------------------


def test_startup_validation_rejects_empty_gnani_key():
    # STT gnani without key fails
    s_stt = Settings(stt_provider="gnani", gnani_api_key="")
    with pytest.raises(RuntimeError, match="GNANI_API_KEY must be set"):
        validate_startup_settings(s_stt)

    # TTS gnani without key fails
    s_tts = Settings(tts_provider="gnani", gnani_api_key="")
    with pytest.raises(RuntimeError, match="GNANI_API_KEY must be set"):
        validate_startup_settings(s_tts)

    # Mock/browser succeeds with empty key
    s_mock = Settings(stt_provider="mock", tts_provider="browser", gnani_api_key="")
    validate_startup_settings(s_mock)


# -----------------------------------------------------------------------------
# /api/turn Integration Tests with Gnani
# -----------------------------------------------------------------------------


def make_test_client(tmp_path: Path, **overrides) -> TestClient:
    config_dir = Path(__file__).resolve().parents[3] / "config"
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        config_dir=config_dir,
        audio_dir=tmp_path / "audio",
        rate_limit_per_minute=overrides.pop("rate_limit_per_minute", 1000),
        stt_provider=overrides.pop("stt_provider", "mock"),
        tts_provider=overrides.pop("tts_provider", "browser"),
        **overrides,
    )
    return TestClient(create_app(settings))


def test_turn_api_stt_webm_returns_415(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.speech.providers.GnaniPrismaSTT",
        lambda **kw: GnaniPrismaSTT(
            transport=httpx.MockTransport(lambda r: httpx.Response(200)), **kw
        ),
    )
    client = make_test_client(tmp_path, stt_provider="gnani", gnani_api_key="k")
    resp = client.post(
        "/api/turn",
        data={"session_id": "s_webm"},
        files={"audio": ("a.webm", b"dummy", "audio/webm")},
    )
    assert resp.status_code == 415
    assert "WAV" in resp.json()["detail"]["en"]


def test_turn_api_stt_duration_exceeds_30s_returns_413(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "app.speech.providers.GnaniPrismaSTT",
        lambda **kw: GnaniPrismaSTT(
            transport=httpx.MockTransport(lambda r: httpx.Response(200)), **kw
        ),
    )
    client = make_test_client(tmp_path, stt_provider="gnani", gnani_api_key="k")
    resp = client.post(
        "/api/turn",
        data={"session_id": "s_long"},
        files={"audio": ("a.wav", make_wav_bytes(31.0), "audio/wav")},
    )
    assert resp.status_code == 413


def test_turn_api_stt_quota_error_returns_402(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(402, json={"detail": {"message": "Credit out"}})
    )
    monkeypatch.setattr(
        "app.speech.providers.GnaniPrismaSTT",
        lambda **kw: GnaniPrismaSTT(transport=transport, **kw),
    )
    client = make_test_client(tmp_path, stt_provider="gnani", gnani_api_key="k")
    resp = client.post(
        "/api/turn",
        data={"session_id": "s_quota"},
        files={"audio": ("a.wav", make_wav_bytes(1.0), "audio/wav")},
    )
    assert resp.status_code == 402
    assert "ক্রেডিট" in resp.json()["detail"]["bn"]


def test_turn_api_stt_timeout_returns_504(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def timeout_handler(r):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(
        "app.speech.providers.GnaniPrismaSTT",
        lambda **kw: GnaniPrismaSTT(transport=httpx.MockTransport(timeout_handler), **kw),
    )
    client = make_test_client(tmp_path, stt_provider="gnani", gnani_api_key="k")
    resp = client.post(
        "/api/turn",
        data={"session_id": "s_timeout"},
        files={"audio": ("a.wav", make_wav_bytes(1.0), "audio/wav")},
    )
    assert resp.status_code == 504
    assert "সময় শেষ" in resp.json()["detail"]["bn"]


def test_turn_api_tts_fallback_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tts_transport = httpx.MockTransport(lambda r: httpx.Response(500, json={"error": "fail"}))
    monkeypatch.setattr(
        "app.speech.providers.GnaniTimbreTTS",
        lambda **kw: GnaniTimbreTTS(
            transport=tts_transport, **{**kw, "cache_dir": tmp_path / "tts"}
        ),
    )
    client = make_test_client(tmp_path, tts_provider="gnani", gnani_api_key="k")
    resp = client.post(
        "/api/turn",
        json={"session_id": "s_tts_fallback", "text": "aaj Rina visit"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "HTTP 500" in str(data["tts_fallback"])
    assert data["response_audio"] is None
    assert "fallback" in data["providers"]["tts"]


# -----------------------------------------------------------------------------
# Gnani Live Bugfix & Configuration Regression Tests
# -----------------------------------------------------------------------------


def test_tts_mp3_body_has_no_encoding_fields(tmp_path: Path):
    captured_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        captured_payloads.append(body)
        return httpx.Response(200, content=b"AUDIO_DATA")

    transport = httpx.MockTransport(handler)

    # 1. MP3 container: must send only sample_rate and container
    tts_mp3 = GnaniTimbreTTS(
        api_key="test-key",
        container="mp3",
        sample_rate=24000,
        cache_dir=tmp_path / "tts_mp3",
        transport=transport,
    )
    tts_mp3.speak("নমস্কার", "bn")

    assert len(captured_payloads) == 1
    mp3_config = captured_payloads[0]["audio_config"]
    assert mp3_config == {"sample_rate": 24000, "container": "mp3"}
    assert "encoding" not in mp3_config
    assert "num_channels" not in mp3_config
    assert "sample_width" not in mp3_config

    # 2. WAV container: must send encoding pcm_s16le
    tts_wav = GnaniTimbreTTS(
        api_key="test-key",
        container="wav",
        sample_rate=16000,
        cache_dir=tmp_path / "tts_wav",
        transport=transport,
    )
    tts_wav.speak("নমস্কার", "bn")

    assert len(captured_payloads) == 2
    wav_config = captured_payloads[1]["audio_config"]
    assert wav_config == {
        "sample_rate": 16000,
        "num_channels": 1,
        "sample_width": 2,
        "encoding": "pcm_s16le",
        "container": "wav",
    }


def test_tts_400_response_logs_message_not_text(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
):
    gnani_error_msg = (
        "Input should be 'linear_pcm', 'pcm_s16le', 'pcm_mulaw', 'pcm_alaw' "
        "or 'oggopus' at body -> audio_config -> encoding"
    )
    sensitive_phrase = "আমার অতি গোপন তথ্য"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            headers={"X-API-Request-ID": "req-err-400"},
            json={"message": gnani_error_msg},
        )

    transport = httpx.MockTransport(handler)
    tts = GnaniTimbreTTS(
        api_key="secret-api-key",
        cache_dir=tmp_path / "tts",
        transport=transport,
    )

    with caplog.at_level(logging.WARNING):
        result = tts.speak(sensitive_phrase, "bn")

    assert result.audio_bytes is None
    assert result.use_browser_tts is True
    assert gnani_error_msg in str(result.tts_fallback)

    # Log verification at WARNING level
    warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_logs) >= 1

    all_logs = caplog.text
    # Confirms Gnani's message is logged
    assert "Input should be" in all_logs
    # Confirms request id is logged
    assert "req-err-400" in all_logs
    # Confirms sensitive user text and API key are NEVER in logs
    assert sensitive_phrase not in all_logs
    assert "secret-api-key" not in all_logs


def test_empty_gnani_base_url_falls_back_to_default():
    default_url = "https://api.vachana.ai"

    # Settings validation
    s_empty = Settings(gnani_base_url="")
    assert s_empty.gnani_base_url == default_url

    s_whitespace = Settings(gnani_base_url="   ")
    assert s_whitespace.gnani_base_url == default_url

    # STT adapter default
    stt_empty = GnaniPrismaSTT(api_key="k", base_url="")
    assert stt_empty.base_url == default_url

    stt_spaces = GnaniPrismaSTT(api_key="k", base_url="   ")
    assert stt_spaces.base_url == default_url

    # TTS adapter default
    tts_empty = GnaniTimbreTTS(api_key="k", base_url="")
    assert tts_empty.base_url == default_url

    tts_spaces = GnaniTimbreTTS(api_key="k", base_url="   ")
    assert tts_spaces.base_url == default_url


