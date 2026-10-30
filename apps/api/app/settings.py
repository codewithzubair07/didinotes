from pathlib import Path
from typing import Literal

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
    gnani_api_key: str = ""
    gnani_base_url: str = ""
    tz: str = "Asia/Kolkata"
    database_url: str = f"sqlite:///{(REPO_ROOT / 'asha_diary.db').as_posix()}"
    config_dir: Path = REPO_ROOT / "config"
    max_audio_bytes: int = 2_000_000
    max_audio_seconds: int = 60
    max_text_chars: int = 500
    rate_limit_per_minute: int = 30
    session_ttl_seconds: int = 900


def get_settings() -> Settings:
    return Settings()
