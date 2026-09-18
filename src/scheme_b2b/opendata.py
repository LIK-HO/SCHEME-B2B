from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .classification import classify_okved, is_moscow_label
from .normalization import normalize_name
from .sources import Candidate


FIELD_NAMES = {
    "company": ("company", "Компания", "Наименование", "ПолнНаимОПФ", "Наименование организации"),
    "inn": ("inn", "ИНН", "ИННЮЛ", "ИННФЛ"),
    "ogrn": ("ogrn", "ОГРН"),
    "ogrnip": ("ogrnip", "ОГРНИП"),
    "city": ("city", "Город", "Наименование субъекта", "Регион"),
    "okved": ("okved", "ОКВЭД", "КодОКВЭД"),
    "phone": ("phone", "Телефон"),
    "email": ("email", "Почта", "Email", "E-mail"),
    "website": ("website", "Сайт", "URL"),
}


def _value(row: dict[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return normalize_name(str(value))
    return ""


def _normalize_headers(row: dict[str, Any]) -> dict[str, Any]:
    return {normalize_name(str(k)): v for k, v in row.items()}


def candidate_from_csv_row(row: dict[str, Any], source_name: str) -> Candidate:
    data = _normalize_headers(row)
    return Candidate(
        company=_value(data, FIELD_NAMES["company"]),
        inn=_value(data, FIELD_NAMES["inn"]),
        ogrn=_value(data, FIELD_NAMES["ogrn"]),
        ogrnip=_value(data, FIELD_NAMES["ogrnip"]),
        city=_value(data, FIELD_NAMES["city"]) or "Москва",
        sector=classify_okved(_value(data, FIELD_NAMES["okved"])),
        need="",
        phone=_value(data, FIELD_NAMES["phone"]),
        email=_value(data, FIELD_NAMES["email"]),
        website=_value(data, FIELD_NAMES["website"]),
        source=source_name,
        comment=f"ОКВЭД={_value(data, FIELD_NAMES['okved']) or 'не указан'}",
    )


class OpenDataCsvSource:
    def __init__(self, path: str, source_name: str, only_moscow: bool = True):
        self.path = Path(path)
        self.name = source_name
        self.only_moscow = only_moscow

    def load(self) -> list[Candidate]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)

        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "cp1251"):
            try:
                with self.path.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle)
                    result = []
                    for row in reader:
                        candidate = candidate_from_csv_row(row, self.name)
                        if not candidate.inn:
                            continue
                        if self.only_moscow and not is_moscow_label(candidate.city):
                            continue
                        result.append(candidate)
                    return result
            except UnicodeDecodeError as exc:
                last_error = exc
        raise ValueError(f"Не удалось прочитать CSV: {last_error}")
