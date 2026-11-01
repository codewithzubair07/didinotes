from typing import Protocol

from pydantic import BaseModel


class Transcript(BaseModel):
    text: str
    # Confidence score (0.0 to 1.0). None when the provider (e.g. Gnani Prisma) does not return one.
    confidence: float | None = None
    request_id: str | None = None


class Speech(BaseModel):
    audio_bytes: bytes | None = None
    mime: str | None = None
    use_browser_tts: bool = True
    tts_fallback: bool | str = False
    cached: bool = False
    request_id: str | None = None


class SpeechToText(Protocol):
    name: str

    def transcribe(self, audio_bytes: bytes, mime: str, lang_hint: str) -> Transcript: ...


class TextToSpeech(Protocol):
    name: str

    def speak(self, text: str, lang: str) -> Speech: ...
