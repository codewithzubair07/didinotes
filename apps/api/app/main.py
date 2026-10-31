from app.factory import create_app
from app.settings import Settings, get_settings


def validate_startup_settings(settings: Settings) -> None:
    is_gnani = settings.stt_provider == "gnani" or settings.tts_provider == "gnani"
    if is_gnani and not settings.gnani_api_key:
        raise RuntimeError(
            "GNANI_API_KEY must be set when STT_PROVIDER or TTS_PROVIDER is 'gnani'. "
            "Please configure GNANI_API_KEY in your environment or .env file."
        )


settings = get_settings()
validate_startup_settings(settings)
app = create_app(settings)
