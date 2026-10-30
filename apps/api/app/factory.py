from fastapi import FastAPI
from sqlalchemy import Engine, inspect, text

from app.config_loader import load_incentives
from app.db import Base, make_engine, make_session_factory
from app.entry_routes import router as entry_router
from app.nlu.llm import TimedExtractor, get_extractor
from app.rate_limit import RateLimiter
from app.routes import router
from app.session_store import SessionStore
from app.settings import Settings, get_settings
from app.turn import router as turn_router


def _add_missing_entry_columns(engine: Engine) -> None:
    # create_all() does not alter existing tables, so add columns added after first release.
    existing = {column["name"] for column in inspect(engine).get_columns("entries")}
    if "documents" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE entries ADD COLUMN documents TEXT"))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    _add_missing_entry_columns(engine)

    app = FastAPI(title="ASHA Diary API")
    app.state.settings = settings
    app.state.session_factory = make_session_factory(engine)
    app.state.task_types = load_incentives(settings.config_dir / "incentives.yaml")
    app.state.sessions = SessionStore(settings.session_ttl_seconds)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    app.state.extractor = TimedExtractor(get_extractor(settings))
    app.include_router(router, prefix="/api")
    app.include_router(turn_router, prefix="/api")
    app.include_router(entry_router, prefix="/api")
    return app
