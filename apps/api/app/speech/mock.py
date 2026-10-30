
from app.speech.base import Speech, Transcript


class MockSTT:
    name = "mock"

    def __init__(self, text: str = "") -> None:
        self.text = text

    def transcribe(self, audio_bytes: bytes, mime: str, lang_hint: str) -> Transcript:
        return Transcript(text=self.text, confidence=1.0 if self.text else 0.0)


class BrowserTTS:
    name = "browser"

    def speak(self, text: str, lang: str) -> Speech:
        return Speech(audio_bytes=None, mime=None, use_browser_tts=True)
