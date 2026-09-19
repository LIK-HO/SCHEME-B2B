import re
from urllib.parse import urlparse


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


def phone(value: str | None) -> str:
    raw = digits(value)
    if raw.startswith("8") and len(raw) == 11:
        return "7" + raw[1:]
    if len(raw) == 10:
        return "7" + raw
    return raw


def email(value: str | None) -> str:
    return " ".join((value or "").split()).lower()


def website(value: str | None) -> str:
    raw = " ".join((value or "").split())
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def name(value: str | None) -> str:
    return " ".join((value or "").split())
