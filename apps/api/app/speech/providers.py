from app.settings import Settings
from app.speech.base import SpeechToText, TextToSpeech
from app.speech.gnani import GnaniPrismaSTT, GnaniTimbreTTS
from app.speech.mock import BrowserTTS, MockSTT


def get_stt(settings: Settings, mock_text: str = "") -> SpeechToText:
    if settings.stt_provider == "gnani":
        return GnaniPrismaSTT(
            api_key=settings.gnani_api_key,
            base_url=settings.gnani_base_url,
            model=settings.gnani_stt_model,
            languages=settings.gnani_stt_languages,
            format_type=settings.gnani_stt_format,
            topic=settings.gnani_stt_topic,
            keyterms=settings.gnani_stt_keyterms,
            timeout_s=settings.gnani_timeout_s,
            max_concurrency=settings.gnani_max_concurrency,
        )
    return MockSTT(text=mock_text)


def get_tts(settings: Settings) -> TextToSpeech:
    if settings.tts_provider == "gnani":
        return GnaniTimbreTTS(
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
            max_concurrency=settings.gnani_max_concurrency,
        )
    return BrowserTTS()
