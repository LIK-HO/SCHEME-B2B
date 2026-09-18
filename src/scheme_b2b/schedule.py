from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MSK = ZoneInfo("Europe/Moscow")
SLOT_HOURS = (6, 14, 22)


FREQUENCY_SLOTS = {
    "1 раз в день": (6,),
    "2 раза в день": (6, 14),
    "3 раза в день": SLOT_HOURS,
}


def allowed_slots(frequency: str) -> tuple[int, ...]:
    value = (frequency or "").strip().lower()
    return FREQUENCY_SLOTS.get(value, ())


def should_run_now(frequency: str, now: datetime | None = None) -> bool:
    current = now or datetime.now(MSK)
    return current.hour in allowed_slots(frequency)


def next_run(frequency: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now(MSK)
    slots = allowed_slots(frequency)
    if not slots:
        return current.replace(hour=6, minute=7, second=0, microsecond=0) + timedelta(days=1)
    for hour in slots:
        candidate = current.replace(hour=hour, minute=7, second=0, microsecond=0)
        if candidate > current:
            return candidate
    return current.replace(hour=slots[0], minute=7, second=0, microsecond=0) + timedelta(days=1)


def already_ran_this_slot(last_run: str | None, now: datetime | None = None) -> bool:
    if not last_run:
        return False
    current = now or datetime.now(MSK)
    try:
        parsed = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=MSK)
        parsed = parsed.astimezone(MSK)
    except ValueError:
        return False
    return parsed.date() == current.date() and parsed.hour == current.hour
