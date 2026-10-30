from app.settings import Settings
from app.speech.base import SpeechToText, TextToSpeech
from app.speech.gnani import GnaniPrismaSTT, GnaniTimbreTTS
from app.speech.mock import BrowserTTS, MockSTT


def get_stt(settings: Settings, mock_text: str = "") -> SpeechToText:
    if settings.stt_provider == "gnani":
        return GnaniPrismaSTT()
    return MockSTT(text=mock_text)


def get_tts(settings: Settings) -> TextToSpeech:
    if settings.tts_provider == "gnani":
        return GnaniTimbreTTS()
    return BrowserTTS()
