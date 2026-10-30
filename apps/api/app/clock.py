from datetime import date, datetime
from zoneinfo import ZoneInfo


def now_local(tz_name: str = "Asia/Kolkata") -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def today_local(tz_name: str = "Asia/Kolkata") -> date:
    return now_local(tz_name).date()
