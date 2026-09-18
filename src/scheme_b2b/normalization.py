import re


def digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def normalize_inn(value: str | None) -> str:
    raw = digits(value)
    return raw if len(raw) in (10, 12) else ""


def normalize_ogrn(value: str | None) -> str:
    raw = digits(value)
    return raw if len(raw) == 13 else ""


def normalize_ogrnip(value: str | None) -> str:
    raw = digits(value)
    return raw if len(raw) == 15 else ""


def normalize_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str | None) -> str:
    raw = digits(value)
    if raw.startswith("8") and len(raw) == 11:
        return "7" + raw[1:]
    if len(raw) == 10:
        return "7" + raw
    return raw
