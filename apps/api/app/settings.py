from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    llm_provider: Literal["rules", "openai"] = "rules"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 5.0
    stt_provider: Literal["mock", "gnani"] = "mock"
    tts_provider: Literal["browser", "gnani"] = "browser"
    store_audio: bool = False
    tz: str = "Asia/Kolkata"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'asha_diary.db').as_posix()}"
    config_dir: Path = REPO_ROOT / "config"
    max_audio_bytes: int = 2_000_000
    max_audio_seconds: int = 60
    max_text_chars: int = 500
    rate_limit_per_minute: int = 30
    session_ttl_seconds: int = 900

    # Gnani settings
    gnani_api_key: str = ""
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_stt_model: str = ""
    gnani_stt_languages: str = "bn-IN"
    gnani_stt_format: str = ""
    gnani_stt_topic: str = ""
    gnani_stt_keyterms: str = ""
    gnani_tts_model: str = "timbre-v3.0"
    gnani_tts_voice: str = "Shivani"
    gnani_tts_language: str = "bn-IN"
    gnani_tts_speed: float = 1.0
    gnani_tts_container: str = "mp3"
    gnani_tts_sample_rate: int = 24000
    gnani_tts_spoken_numbers: bool = True
    gnani_max_concurrency: int = 1
    gnani_timeout_s: float = 30.0
    tts_cache_dir: Path = REPO_ROOT / ".cache" / "tts"

    @field_validator("tts_cache_dir", mode="after")
    @classmethod
    def resolve_cache_dir(cls, val: Path) -> Path:
        if not val.is_absolute():
            return REPO_ROOT / val
        return val


def get_settings() -> Settings:
    return Settings()
