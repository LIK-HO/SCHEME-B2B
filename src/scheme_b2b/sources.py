import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import httpx

from .config import Settings
from .normalization import (
    is_valid_email,
    is_valid_phone,
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_website,
)


@dataclass(frozen=True)
class Candidate:
    company: str
    inn: str
    ogrn: str = ""
    ogrnip: str = ""
    city: str = "Москва"
    sector: str = "Другое"
    need: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    responsible: str = ""
    source: str = ""
    comment: str = ""


class CandidateSource:
    name: str

    def iter_candidates(self) -> Iterator[Candidate]:
        yield from self.load()

    def load(self) -> list[Candidate]:
        raise NotImplementedError


def candidate_from_mapping(item: dict[str, Any], source_name: str = "") -> Candidate:
    phone = normalize_phone(str(item.get("phone") or item.get("Телефон") or ""))
    email = normalize_email(str(item.get("email") or item.get("Почта") or ""))
    return Candidate(
        company=normalize_name(str(item.get("company") or item.get("Компания") or "")),
        inn=str(item.get("inn") or item.get("ИНН") or ""),
        ogrn=str(item.get("ogrn") or item.get("ОГРН") or ""),
        ogrnip=str(item.get("ogrnip") or item.get("ОГРНИП") or ""),
        city=normalize_name(str(item.get("city") or item.get("Город") or "Москва")),
        sector=normalize_name(str(item.get("sector") or item.get("Сфера") or "Другое")) or "Другое",
        need=normalize_name(str(item.get("need") or item.get("Потребность") or "")),
        phone=phone if is_valid_phone(phone) else "",
        email=email if is_valid_email(email) else "",
        website=normalize_website(str(item.get("website") or item.get("Сайт") or "")),
        responsible=normalize_name(str(item.get("responsible") or item.get("Ответственный") or "")),
        source=normalize_name(str(item.get("source") or item.get("Источник") or source_name)),
        comment=normalize_name(str(item.get("comment") or item.get("Комментарий") or "")),
    )


class JsonFileSource(CandidateSource):
    name = "JSON file"

    def __init__(self, path: str):
        self.path = Path(path)

    def load(self) -> list[Candidate]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        items = payload.get("companies", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("SOURCE_JSON_FILE должен содержать массив или объект с companies[]")
        return [candidate_from_mapping(x, self.name) for x in items if isinstance(x, dict)]


class JsonUrlSource(CandidateSource):
    name = "JSON URL"

    def __init__(self, url: str, timeout: float):
        self.url = url
        self.timeout = timeout

    def load(self) -> list[Candidate]:
        response = httpx.get(self.url, timeout=self.timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("companies", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("SOURCE_JSON_URL должен возвращать массив или объект с companies[]")
        return [candidate_from_mapping(x, self.name) for x in items if isinstance(x, dict)]


def build_sources(settings: Settings) -> list[CandidateSource]:
    sources: list[CandidateSource] = []

    if settings.source_json_file:
        sources.append(JsonFileSource(settings.source_json_file))
    if settings.source_json_url:
        sources.append(JsonUrlSource(settings.source_json_url, settings.source_timeout_seconds))

    if settings.fns_rsmp_path:
        from .registry import FNSBulkSource

        sources.append(
            FNSBulkSource(
                settings.fns_rsmp_path,
                only_moscow=True,
                source_name="ФНС — Единый реестр МСП",
            )
        )

    if settings.rosstat_registry_path:
        from .opendata import OpenDataCsvSource

        sources.append(
            OpenDataCsvSource(
                settings.rosstat_registry_path,
                "Росстат — Статистический регистр хозяйствующих субъектов",
                only_moscow=True,
            )
        )

    return sources
