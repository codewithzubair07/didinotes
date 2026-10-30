import calendar
import csv
import html
import io
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config_loader import TaskType
from app.models import Entry

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
NOT_CONFIGURED = "amount not configured"
LOW_CONFIDENCE = 0.7
CSV_HEADERS = [
    "date",
    "task_type",
    "task_label_en",
    "count",
    "beneficiary_ref",
    "amount_inr",
    "missing_documents",
]


def month_range(yyyy_mm: str) -> tuple[date, date]:
    year, month = (int(part) for part in yyyy_mm.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def entry_documents(entry: Entry) -> list[str]:
    return json.loads(entry.documents) if entry.documents else []


def missing_documents(entry: Entry, task_types: dict[str, TaskType]) -> list[str]:
    task = task_types.get(entry.task_type)
    if task is None:
        return []
    have = set(entry_documents(entry))
    return [doc for doc in task.required_documents if doc not in have]


def attention_reasons(entry: Entry, task_types: dict[str, TaskType]) -> list[str]:
    reasons = []
    if entry.status != "confirmed":
        reasons.append("not confirmed")
    if entry.task_type not in task_types:
        reasons.append("unknown task type")
    elif entry.task_type == "other":
        reasons.append("task type is other")
    if entry.beneficiary_ref is None:
        reasons.append("no beneficiary")
    if entry.confidence is not None and entry.confidence < LOW_CONFIDENCE:
        reasons.append("low confidence")
    if missing_documents(entry, task_types):
        reasons.append("missing documents")
    return reasons


def register_line(entry: Entry, task_types: dict[str, TaskType]) -> str:
    task = task_types.get(entry.task_type)
    label = task.bn_label if task else entry.task_type
    beneficiary = entry.beneficiary_ref or "-"
    return f"{entry.event_date.isoformat()} | {label} | {beneficiary} | {entry.count}"


def _entry_view(entry: Entry, task_types: dict[str, TaskType]) -> dict:
    task = task_types.get(entry.task_type)
    amount = task.incentive_inr if task and task.incentive_inr is not None else None
    return {
        "id": entry.id,
        "event_date": entry.event_date.isoformat(),
        "task_type": entry.task_type,
        "task_label_en": task.en_label if task else entry.task_type,
        "task_label_bn": task.bn_label if task else entry.task_type,
        "count": entry.count,
        "beneficiary_ref": entry.beneficiary_ref,
        "status": entry.status,
        "documents": entry_documents(entry),
        "missing_documents": missing_documents(entry, task_types),
        "attention_reasons": attention_reasons(entry, task_types),
        "amount_inr": NOT_CONFIGURED if amount is None else amount,
    }


def build_claim(session: Session, yyyy_mm: str, task_types: list[TaskType]) -> dict:
    start, end = month_range(yyyy_mm)
    by_id = {task.id: task for task in task_types}
    statement = (
        select(Entry)
        .where(Entry.event_date >= start, Entry.event_date <= end)
        .order_by(Entry.event_date, Entry.id)
    )
    month_entries = list(session.scalars(statement))
    confirmed = [entry for entry in month_entries if entry.status == "confirmed"]

    rows = []
    for task in task_types:
        mine = [entry for entry in confirmed if entry.task_type == task.id]
        if task.incentive_inr is None:
            amount, amount_status = None, NOT_CONFIGURED
        else:
            amount, amount_status = len(mine) * task.incentive_inr, "configured"
        rows.append(
            {
                "task_type": task.id,
                "task_label_bn": task.bn_label,
                "task_label_en": task.en_label,
                "entry_count": len(mine),
                "total_count": sum(entry.count for entry in mine),
                "amount_inr": amount,
                "amount_status": amount_status,
            }
        )

    used_amounts = [row for row in rows if row["entry_count"] > 0]
    if any(row["amount_status"] == NOT_CONFIGURED for row in used_amounts):
        total_inr = None
    else:
        total_inr = sum(row["amount_inr"] for row in used_amounts)

    return {
        "month": yyyy_mm,
        "rows": rows,
        "total_inr": total_inr,
        "entries": [_entry_view(entry, by_id) for entry in confirmed],
        "attention": [
            _entry_view(entry, by_id)
            for entry in month_entries
            if attention_reasons(entry, by_id)
        ],
        "register_lines": [register_line(entry, by_id) for entry in confirmed],
    }


def claim_csv(claim: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    for entry in claim["entries"]:
        writer.writerow(
            [
                entry["event_date"],
                entry["task_type"],
                entry["task_label_en"],
                entry["count"],
                entry["beneficiary_ref"] or "",
                entry["amount_inr"],
                "; ".join(entry["missing_documents"]),
            ]
        )
    return buffer.getvalue()


def _cell(value: object) -> str:
    return html.escape("" if value is None else str(value))


def claim_html(claim: dict, banner: str) -> str:
    summary = "".join(
        f"<tr><td>{_cell(row['task_label_en'])}</td><td>{row['entry_count']}</td>"
        f"<td>{row['total_count']}</td><td>{_cell(row['amount_inr'] or NOT_CONFIGURED)}</td></tr>"
        for row in claim["rows"]
    )
    entries = "".join(
        f"<tr><td>{_cell(e['event_date'])}</td><td>{_cell(e['task_label_en'])}</td>"
        f"<td>{_cell(e['beneficiary_ref'] or '-')}</td><td>{e['count']}</td>"
        f"<td>{_cell('; '.join(e['missing_documents']) or 'none')}</td></tr>"
        for e in claim["entries"]
    )
    attention = "".join(
        f"<li>{_cell(e['event_date'])} {_cell(e['task_label_en'])}: "
        f"{_cell(', '.join(e['attention_reasons']))}</li>"
        for e in claim["attention"]
    )
    total = "not configured" if claim["total_inr"] is None else str(claim["total_inr"])
    register = "\n".join(_cell(line) for line in claim["register_lines"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ASHA Diary claim {_cell(claim['month'])}</title>
<style>
body {{ font-family: sans-serif; margin: 24px; color: #000; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
th, td {{ border: 1px solid #000; padding: 4px 6px; text-align: left; }}
.banner {{ border: 2px solid #000; padding: 6px; font-weight: bold; }}
@media print {{ button {{ display: none; }} }}
</style>
</head>
<body>
<p class="banner">{_cell(banner)}</p>
<h1>Incentive claim sheet: {_cell(claim['month'])}</h1>
<h2>Summary (confirmed entries only)</h2>
<table>
<tr><th>Task</th><th>Entries</th><th>Count</th><th>Amount (INR)</th></tr>
{summary}
</table>
<p>Total (INR): {_cell(total)}</p>
<h2>Confirmed entries</h2>
<table>
<tr><th>Date</th><th>Task</th><th>Beneficiary</th><th>Count</th><th>Missing documents</th></tr>
{entries}
</table>
<h2>Needs attention</h2>
<ul>{attention or '<li>none</li>'}</ul>
<h2>Register lines</h2>
<pre>{register}</pre>
</body>
</html>
"""
