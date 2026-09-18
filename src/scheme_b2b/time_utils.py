from datetime import UTC, datetime
from zoneinfo import ZoneInfo


MSK = ZoneInfo("Europe/Moscow")


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_msk() -> datetime:
    return datetime.now(MSK)


def ensure_aware(value: datetime, tz: ZoneInfo = MSK) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)
