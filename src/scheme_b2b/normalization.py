import re
from urllib.parse import urlparse


def digits(value: str | None) -> str:
    return re.sub(r"\\D+", "", value or "")


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
    return re.sub(r"\\s+", " ", (value or "").strip())


def normalize_email(value: str | None) -> str:
    return normalize_name(value).lower()


def is_valid_email(value: str | None) -> bool:
    email = normalize_email(value)
    return bool(re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email))


def normalize_phone(value: str | None) -> str:
    raw = digits(value)
    if raw.startswith("8") and len(raw) == 11:
        return "7" + raw[1:]
    if len(raw) == 10:
        return "7" + raw
    return raw


def is_valid_phone(value: str | None) -> bool:
    raw = digits(value)
    return len(raw) == 11 and raw[0] in {"7", "8"}


def normalize_website(value: str | None) -> str:
    raw = normalize_name(value)
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw
