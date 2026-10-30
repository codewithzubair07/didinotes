import json
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from app.claims import MONTH_PATTERN, build_claim, claim_csv, claim_html, entry_documents
from app.clock import today_local
from app.config_loader import TaskType
from app.i18n import t
from app.models import Entry
from app.repository import confirm_entry, delete_entry, list_entries, update_entry
from app.routes import DEMO_BANNER

REQUIRED_FIELDS = ("task_type", "count", "event_date")
MonthParam = Annotated[str, Path(pattern=MONTH_PATTERN)]

router = APIRouter()


class EntryPatch(BaseModel):
    task_type: str | None = Field(default=None, min_length=1, max_length=64)
    beneficiary_ref: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{1,16}$")
    count: int | None = Field(default=None, ge=1, le=99)
    event_date: date | None = None
    notes: str | None = Field(default=None, max_length=300)
    documents: list[str] | None = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def required_fields_not_null(self):
        for name in REQUIRED_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


def _error(status: int, key: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"bn": t(f"errors.{key}", "bn"), "en": t(f"errors.{key}", "en")},
    )


def _entry_view(entry: Entry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "task_type": entry.task_type,
        "beneficiary_ref": entry.beneficiary_ref,
        "count": entry.count,
        "event_date": entry.event_date.isoformat(),
        "notes": entry.notes,
        "documents": entry_documents(entry),
        "status": entry.status,
        "confidence": entry.confidence,
        "created_at": entry.created_at.isoformat(),
    }


def _task_types(request: Request) -> list[TaskType]:
    return request.app.state.task_types


@router.get("/entries")
def list_entries_by_date(
    request: Request, on_date: Annotated[date | None, Query(alias="date")] = None
) -> list[dict[str, Any]]:
    with request.app.state.session_factory() as db:
        entries = list_entries(db, on_date or today_local())
        return [_entry_view(entry) for entry in entries]


@router.patch("/entries/{entry_id}")
def patch_entry(request: Request, entry_id: int, body: EntryPatch) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "task_type" in changes and changes["task_type"] not in {
        task.id for task in _task_types(request)
    }:
        raise _error(422, "unknown_task_type")
    if "event_date" in changes and changes["event_date"] > today_local():
        raise _error(422, "future_entry_date")
    if "beneficiary_ref" in changes and changes["beneficiary_ref"] is not None:
        changes["beneficiary_ref"] = changes["beneficiary_ref"].upper()
    if "documents" in changes and changes["documents"] is not None:
        changes["documents"] = json.dumps(changes["documents"])
    with request.app.state.session_factory() as db:
        entry = update_entry(db, entry_id, **changes)
        if entry is None:
            raise _error(404, "entry_not_found")
        return _entry_view(entry)


@router.post("/entries/{entry_id}/confirm")
def confirm(request: Request, entry_id: int) -> dict[str, Any]:
    with request.app.state.session_factory() as db:
        entry = confirm_entry(db, entry_id)
        if entry is None:
            raise _error(404, "entry_not_found")
        return _entry_view(entry)


@router.delete("/entries/{entry_id}", status_code=204)
def remove(request: Request, entry_id: int) -> Response:
    with request.app.state.session_factory() as db:
        if not delete_entry(db, entry_id):
            raise _error(404, "entry_not_found")
    return Response(status_code=204)


@router.get("/claims/{yyyy_mm}")
def claim(request: Request, yyyy_mm: MonthParam) -> dict[str, Any]:
    with request.app.state.session_factory() as db:
        return build_claim(db, yyyy_mm, _task_types(request))


@router.get("/claims/{yyyy_mm}/export")
def claim_export(request: Request, yyyy_mm: MonthParam) -> Response:
    with request.app.state.session_factory() as db:
        data = claim_csv(build_claim(db, yyyy_mm, _task_types(request)))
    return Response(
        content=data.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="claim-{yyyy_mm}.csv"'},
    )


@router.get("/claims/{yyyy_mm}/print", response_class=HTMLResponse)
def claim_print(request: Request, yyyy_mm: MonthParam) -> HTMLResponse:
    with request.app.state.session_factory() as db:
        page = claim_html(build_claim(db, yyyy_mm, _task_types(request)), DEMO_BANNER)
    return HTMLResponse(page)
