from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.clock import now_local
from app.db import Base


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed', 'corrected')", name="ck_entries_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    beneficiary_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of document names the ASHA has confirmed she holds.
    documents: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    source_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Stored as naive IST wall-clock time because SQLite has no timezone support.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: now_local().replace(tzinfo=None)
    )
