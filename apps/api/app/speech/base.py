from typing import Protocol

from pydantic import BaseModel


class Transcript(BaseModel):
    text: str
    confidence: float


class Speech(BaseModel):
    audio_bytes: bytes | None = None
    mime: str | None = None
    use_browser_tts: bool = True


class SpeechToText(Protocol):
    name: str

    def transcribe(self, audio_bytes: bytes, mime: str, lang_hint: str) -> Transcript: ...


class TextToSpeech(Protocol):
    name: str

    def speak(self, text: str, lang: str) -> Speech: ...
