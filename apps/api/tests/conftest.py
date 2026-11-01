import pytest


@pytest.fixture(autouse=True)
def isolate_test_speech_providers(monkeypatch: pytest.MonkeyPatch):
    """Ensure tests run against mock STT and browser TTS unless a test explicitly overrides them."""
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "browser")
