from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Entry

EDITABLE_FIELDS = ("task_type", "beneficiary_ref", "count", "event_date", "notes", "documents")


def create_entry(
    session: Session,
    *,
    task_type: str,
    event_date: date,
    count: int = 1,
    beneficiary_ref: str | None = None,
    notes: str | None = None,
    source_transcript: str | None = None,
    confidence: float | None = None,
) -> Entry:
    if count < 1:
        raise ValueError("count must be at least 1")
    entry = Entry(
        task_type=task_type,
        event_date=event_date,
        count=count,
        beneficiary_ref=beneficiary_ref,
        notes=notes,
        source_transcript=source_transcript,
        confidence=confidence,
        status="draft",
    )
    session.add(entry)
    session.commit()
    return entry


def get_entry(session: Session, entry_id: int) -> Entry | None:
    return session.get(Entry, entry_id)


def list_entries(session: Session, on_date: date) -> list[Entry]:
    statement = select(Entry).where(Entry.event_date == on_date).order_by(Entry.id)
    return list(session.scalars(statement))


def update_entry(session: Session, entry_id: int, **changes: object) -> Entry | None:
    entry = session.get(Entry, entry_id)
    if entry is None:
        return None
    unknown = set(changes) - set(EDITABLE_FIELDS)
    if unknown:
        raise ValueError(f"fields cannot be updated: {sorted(unknown)}")
    if changes.get("count", 1) < 1:
        raise ValueError("count must be at least 1")
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.status = "corrected"
    session.commit()
    return entry


def confirm_entry(session: Session, entry_id: int) -> Entry | None:
    entry = session.get(Entry, entry_id)
    if entry is None:
        return None
    entry.status = "confirmed"
    session.commit()
    return entry


def delete_entry(session: Session, entry_id: int) -> bool:
    entry = session.get(Entry, entry_id)
    if entry is None:
        return False
    session.delete(entry)
    session.commit()
    return True
