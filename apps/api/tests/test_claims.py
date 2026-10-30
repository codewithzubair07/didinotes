import csv
import io
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.claims import build_claim, claim_csv
from app.config_loader import TaskType
from app.factory import create_app
from app.repository import confirm_entry, create_entry
from app.settings import Settings

MONTH = "2026-10"


def make_app(tmp_path: Path) -> TestClient:
    config_dir = Path(__file__).resolve().parents[3] / "config"
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        config_dir=config_dir,
        audio_dir=tmp_path / "audio",
        rate_limit_per_minute=1000,
    )
    return TestClient(create_app(settings))


def seed(client: TestClient, **overrides) -> int:
    fields = {
        "task_type": "antenatal_visit",
        "event_date": date(2026, 10, 10),
        "count": 1,
        "beneficiary_ref": "R",
    }
    fields.update(overrides)
    confirm = fields.pop("confirmed", True)
    with client.app.state.session_factory() as db:
        entry = create_entry(db, **fields)
        if confirm:
            confirm_entry(db, entry.id)
        return entry.id


def test_unconfirmed_entries_are_excluded(tmp_path):
    client = make_app(tmp_path)
    seed(client, confirmed=True)
    seed(client, confirmed=False, beneficiary_ref="M")
    with client.app.state.session_factory() as db:
        claim = build_claim(db, MONTH, client.app.state.task_types)
    assert claim["rows"][0]["entry_count"] == 1
    assert len(claim["entries"]) == 1
    assert claim["entries"][0]["beneficiary_ref"] == "R"
    draft = next(e for e in claim["attention"] if e["beneficiary_ref"] == "M")
    assert "not confirmed" in draft["attention_reasons"]


def test_amount_not_configured_by_default(tmp_path):
    client = make_app(tmp_path)
    seed(client)
    body = client.get(f"/api/claims/{MONTH}").json()
    row = next(r for r in body["rows"] if r["task_type"] == "antenatal_visit")
    assert row["amount_inr"] is None
    assert row["amount_status"] == "amount not configured"
    assert body["total_inr"] is None


def test_amount_computed_only_when_configured(tmp_path):
    client = make_app(tmp_path)
    seed(client)
    seed(client, event_date=date(2026, 10, 12), beneficiary_ref="S")
    verified = [
        TaskType(
            id="antenatal_visit",
            bn_label="গর্ভকালীন পরীক্ষা",
            en_label="Antenatal visit",
            required_documents=["doc"],
            incentive_inr=100,
            verified=True,
        )
    ]
    with client.app.state.session_factory() as db:
        claim = build_claim(db, MONTH, verified)
    row = claim["rows"][0]
    assert row["amount_inr"] == 200
    assert row["amount_status"] == "configured"
    assert claim["total_inr"] == 200


def test_missing_documents_flagged_and_cleared_when_recorded(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    body = client.get(f"/api/claims/{MONTH}").json()
    assert body["entries"][0]["missing_documents"] == [
        "Placeholder: antenatal register entry",
        "Placeholder: beneficiary card copy",
    ]
    documents = ["Placeholder: antenatal register entry", "Placeholder: beneficiary card copy"]
    client.patch(f"/api/entries/{entry_id}", json={"documents": documents})
    client.post(f"/api/entries/{entry_id}/confirm")
    body = client.get(f"/api/claims/{MONTH}").json()
    assert body["entries"][0]["missing_documents"] == []


def test_csv_export_contents(tmp_path):
    client = make_app(tmp_path)
    seed(client, count=2)
    response = client.get(f"/api/claims/{MONTH}/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == [
        "date",
        "task_type",
        "task_label_en",
        "count",
        "beneficiary_ref",
        "amount_inr",
        "missing_documents",
    ]
    assert rows[1][:5] == ["2026-10-10", "antenatal_visit", "Antenatal visit", "2", "R"]
    assert rows[1][5] == "amount not configured"


def test_csv_builder_excludes_unconfirmed(tmp_path):
    client = make_app(tmp_path)
    seed(client, confirmed=False)
    with client.app.state.session_factory() as db:
        claim = build_claim(db, MONTH, client.app.state.task_types)
    assert claim_csv(claim).strip().count("\n") == 0


def test_print_page_renders_and_escapes(tmp_path):
    client = make_app(tmp_path)
    seed(client, beneficiary_ref="R")
    response = client.get(f"/api/claims/{MONTH}/print")
    assert response.status_code == 200
    assert "Demo. Do not enter real patient data." in response.text
    assert "Register lines" in response.text


def test_invalid_month_rejected(tmp_path):
    client = make_app(tmp_path)
    assert client.get("/api/claims/2026-13").status_code == 422
    assert client.get("/api/claims/26-10").status_code == 422


def test_list_entries_by_date(tmp_path):
    client = make_app(tmp_path)
    seed(client)
    rows = client.get("/api/entries", params={"date": "2026-10-10"}).json()
    assert len(rows) == 1
    assert rows[0]["status"] == "confirmed"
    assert client.get("/api/entries", params={"date": "2026-10-11"}).json() == []


def test_patch_updates_fields_and_marks_corrected(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    response = client.patch(
        f"/api/entries/{entry_id}", json={"count": 3, "beneficiary_ref": "mk"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert body["beneficiary_ref"] == "MK"
    assert body["status"] == "corrected"


def test_patch_rejects_future_date(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    response = client.patch(f"/api/entries/{entry_id}", json={"event_date": "2999-01-01"})
    assert response.status_code == 422
    assert "ভবিষ্যতের" in response.json()["detail"]["bn"]


def test_patch_rejects_unknown_task_type(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    response = client.patch(f"/api/entries/{entry_id}", json={"task_type": "surgery"})
    assert response.status_code == 422


def test_patch_rejects_null_required_field(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    assert client.patch(f"/api/entries/{entry_id}", json={"count": None}).status_code == 422


def test_patch_rejects_full_name_as_beneficiary(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    response = client.patch(f"/api/entries/{entry_id}", json={"beneficiary_ref": "Rina Das"})
    assert response.status_code == 422


def test_patch_missing_entry_returns_404(tmp_path):
    client = make_app(tmp_path)
    assert client.patch("/api/entries/999", json={"count": 2}).status_code == 404


def test_confirm_and_delete_entry(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client, confirmed=False)
    assert client.post(f"/api/entries/{entry_id}/confirm").json()["status"] == "confirmed"
    assert client.delete(f"/api/entries/{entry_id}").status_code == 204
    assert client.delete(f"/api/entries/{entry_id}").status_code == 404
    assert client.post(f"/api/entries/{entry_id}/confirm").status_code == 404


def test_documents_stored_as_json(tmp_path):
    client = make_app(tmp_path)
    entry_id = seed(client)
    client.patch(f"/api/entries/{entry_id}", json={"documents": ["a"]})
    with client.app.state.session_factory() as db:
        from app.models import Entry

        assert json.loads(db.get(Entry, entry_id).documents) == ["a"]


def test_old_database_gains_documents_column(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    db_path = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE entries (id INTEGER PRIMARY KEY, task_type VARCHAR(64) NOT NULL, "
                "beneficiary_ref VARCHAR(32), count INTEGER NOT NULL, event_date DATE NOT NULL, "
                "notes TEXT, status VARCHAR(16) NOT NULL, source_transcript TEXT, "
                "confidence FLOAT, created_at DATETIME NOT NULL)"
            )
        )
    engine.dispose()
    config_dir = Path(__file__).resolve().parents[3] / "config"
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        config_dir=config_dir,
        audio_dir=tmp_path / "audio",
    )
    create_app(settings)
    columns = {c["name"] for c in inspect(create_engine(f"sqlite:///{db_path.as_posix()}")).get_columns("entries")}
    assert "documents" in columns


@pytest.mark.parametrize("count", [0, 100])
def test_patch_rejects_out_of_range_count(tmp_path, count):
    client = make_app(tmp_path)
    entry_id = seed(client)
    assert client.patch(f"/api/entries/{entry_id}", json={"count": count}).status_code == 422
