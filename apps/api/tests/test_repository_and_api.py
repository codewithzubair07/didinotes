from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import repository
from app.db import Base, make_engine, make_session_factory
from app.factory import create_app
from app.settings import Settings

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        yield db


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'api.db').as_posix()}",
        config_dir=CONFIG_DIR,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_create_and_get(session):
    entry = repository.create_entry(
        session, task_type="antenatal_visit", event_date=date(2026, 10, 29), beneficiary_ref="SD"
    )
    fetched = repository.get_entry(session, entry.id)
    assert fetched.task_type == "antenatal_visit"
    assert fetched.count == 1
    assert fetched.status == "draft"
    assert fetched.beneficiary_ref == "SD"
    assert fetched.created_at is not None


def test_create_rejects_zero_count(session):
    with pytest.raises(ValueError):
        repository.create_entry(
            session, task_type="other", event_date=date(2026, 10, 29), count=0
        )


def test_list_filters_by_date(session):
    repository.create_entry(session, task_type="other", event_date=date(2026, 10, 29))
    repository.create_entry(session, task_type="other", event_date=date(2026, 10, 28))
    assert len(repository.list_entries(session, date(2026, 10, 29))) == 1


def test_update_marks_corrected(session):
    entry = repository.create_entry(session, task_type="other", event_date=date(2026, 10, 29))
    updated = repository.update_entry(session, entry.id, count=3)
    assert updated.count == 3
    assert updated.status == "corrected"


def test_update_rejects_unknown_field(session):
    entry = repository.create_entry(session, task_type="other", event_date=date(2026, 10, 29))
    with pytest.raises(ValueError):
        repository.update_entry(session, entry.id, status="confirmed")


def test_update_missing_returns_none(session):
    assert repository.update_entry(session, 999, count=2) is None


def test_confirm_sets_status(session):
    entry = repository.create_entry(session, task_type="other", event_date=date(2026, 10, 29))
    assert repository.confirm_entry(session, entry.id).status == "confirmed"


def test_delete(session):
    entry = repository.create_entry(session, task_type="other", event_date=date(2026, 10, 29))
    assert repository.delete_entry(session, entry.id) is True
    assert repository.get_entry(session, entry.id) is None
    assert repository.delete_entry(session, entry.id) is False


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["banner"] == "Demo. Do not enter real patient data."


def test_task_types_endpoint(client):
    response = client.get("/api/config/task-types")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 6
    assert all(task["incentive_inr"] is None and task["verified"] is False for task in tasks)
    assert tasks[0]["bn_label"] == "গর্ভকালীন পরীক্ষা"
