import io
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.factory import create_app
from app.models import Entry
from app.settings import Settings


def make_app(tmp_path: Path, **overrides) -> TestClient:
    config_dir = Path(__file__).resolve().parents[3] / "config"
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        config_dir=config_dir,
        audio_dir=tmp_path / "audio",
        rate_limit_per_minute=overrides.pop("rate_limit_per_minute", 1000),
        **overrides,
    )
    return TestClient(create_app(settings))


def wav_bytes(seconds: float) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buffer.getvalue()


def test_json_turn_returns_full_shape(tmp_path):
    client = make_app(tmp_path)
    body = client.post(
        "/api/turn",
        json={"session_id": "s1", "text": "aaj Rina ANC visit korlam, 2 jon"},
    ).json()
    assert body["ui_hint"] == "confirm"
    assert body["entries"][0]["beneficiary_ref"] == "R"
    assert body["response_audio"] is None
    assert set(body["timings_ms"]) == {"stt", "nlu", "llm", "tts"}
    assert body["providers"] == {"stt": "mock", "tts": "browser", "nlu": "rules"}


def test_multi_turn_conversation_saves_entry(tmp_path):
    client = make_app(tmp_path)
    first = client.post(
        "/api/turn", json={"session_id": "s2", "text": "aaj Rina ANC visit korlam"}
    ).json()
    assert first["ui_hint"] == "ask_field"
    second = client.post("/api/turn", json={"session_id": "s2", "text": "2 jon"}).json()
    assert second["ui_hint"] == "confirm"
    saved = client.post("/api/turn", json={"session_id": "s2", "text": "hyan"}).json()
    assert saved["ui_hint"] == "saved"
    assert "আরও কিছু" in saved["response_text"]


def test_saved_entry_is_persisted(tmp_path):
    client = make_app(tmp_path)
    client.post("/api/turn", json={"session_id": "s3", "text": "aaj Rina ANC visit korlam, 2 jon"})
    client.post("/api/turn", json={"session_id": "s3", "text": "hyan"})
    factory = client.app.state.session_factory
    with factory() as db:
        rows = list(db.scalars(select(Entry)))
    assert len(rows) == 1
    assert rows[0].status == "confirmed"
    assert rows[0].count == 2


def test_oversize_audio_rejected(tmp_path):
    client = make_app(tmp_path, max_audio_bytes=1000)
    response = client.post(
        "/api/turn",
        data={"session_id": "s4"},
        files={"audio": ("a.wav", b"0" * 2000, "audio/wav")},
    )
    assert response.status_code == 413
    assert "বাইট" in response.json()["detail"]["bn"]
    assert "bytes" in response.json()["detail"]["en"]


def test_too_long_audio_rejected(tmp_path):
    client = make_app(tmp_path, max_audio_seconds=2)
    response = client.post(
        "/api/turn",
        data={"session_id": "s5"},
        files={"audio": ("a.wav", wav_bytes(5), "audio/wav")},
    )
    assert response.status_code == 413


def test_unsupported_audio_type_rejected(tmp_path):
    client = make_app(tmp_path)
    response = client.post(
        "/api/turn",
        data={"session_id": "s6"},
        files={"audio": ("a.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_bad_session_id_rejected(tmp_path):
    client = make_app(tmp_path)
    response = client.post("/api/turn", json={"session_id": "../etc", "text": "hi"})
    assert response.status_code == 422


def test_empty_input_rejected(tmp_path):
    client = make_app(tmp_path)
    response = client.post("/api/turn", json={"session_id": "s7", "text": ""})
    assert response.status_code == 422


def test_rate_limit_returns_429(tmp_path):
    client = make_app(tmp_path, rate_limit_per_minute=2)
    payload = {"session_id": "s8", "text": "hello"}
    client.post("/api/turn", json=payload)
    client.post("/api/turn", json=payload)
    response = client.post("/api/turn", json=payload)
    assert response.status_code == 429


def test_provider_switch_to_gnani_reports_not_implemented(tmp_path):
    client = make_app(tmp_path, stt_provider="gnani")
    response = client.post(
        "/api/turn",
        data={"session_id": "s9"},
        files={"audio": ("a.wav", wav_bytes(1), "audio/wav")},
    )
    assert response.status_code == 503
    assert "এখনও যুক্ত" in response.json()["detail"]["bn"]


def test_no_audio_left_on_disk(tmp_path):
    client = make_app(tmp_path)
    client.post(
        "/api/turn",
        data={"session_id": "s10"},
        files={"audio": ("a.wav", wav_bytes(1), "audio/wav")},
    )
    leftovers = [p for p in tmp_path.rglob("*") if p.suffix in {".wav", ".webm", ".ogg", ".mp3"}]
    assert leftovers == []


@pytest.mark.parametrize("text", ["amar ki dose dite hobe", "jor hole ki korbo"])
def test_clinical_refusal_over_api(tmp_path, text):
    client = make_app(tmp_path)
    body = client.post("/api/turn", json={"session_id": "s11", "text": text}).json()
    assert body["ui_hint"] == "refusal"
    assert "ANM" in body["response_text"]
