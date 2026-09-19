import re


def digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def inn(value: str | None) -> str:
    raw = digits(value)
    return raw if len(raw) in (10, 12) else ""


def ogrn(value: str | None) -> str:
    raw = digits(value)
    return raw if len(raw) == 13 else ""


def ogrnip(value: str | None) -> str:
    raw = digits(value)
    return raw if len(raw) == 15 else ""


def text(value: str | None) -> str:
    return " ".join((value or "").split())


def phone(value: str | None) -> str:
    raw = digits(value)
    if raw.startswith("8") and len(raw) == 11:
        return "7" + raw[1:]
    if len(raw) == 10:
        return "7" + raw
    return raw
