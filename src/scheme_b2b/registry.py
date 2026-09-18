from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterator
import zipfile
import xml.etree.ElementTree as ET

from .classification import classify_okved as _classify_okved
from .classification import is_moscow_label
from .normalization import normalize_name, normalize_ogrn, normalize_ogrnip, normalize_inn
from .sources import Candidate


RECORD_TAGS = {"СвЮЛ", "СвИП", "Запись", "ЗаписьРеестра"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _clean(value: str | None) -> str:
    return normalize_name(value or "")


def _first_attr(attrs: dict[str, str], *names: str) -> str:
    wanted = {name.lower() for name in names}
    for key, value in attrs.items():
        if key.lower() in wanted:
            return value
    return ""


def _first_matching_attr(attrs: dict[str, str], pattern: str) -> str:
    rx = re.compile(pattern, re.IGNORECASE)
    for key, value in attrs.items():
        if rx.search(key):
            return value
    return ""


def _walk_text(root: ET.Element, names: set[str]) -> str:
    for element in root.iter():
        if local_name(element.tag) in names and (element.text or "").strip():
            return _clean(element.text)
    return ""


def _walk_attr(root: ET.Element, names: tuple[str, ...]) -> str:
    exact = {name.lower() for name in names}
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.lower() in exact and value:
                return _clean(value)
    return ""


def _okved(root: ET.Element) -> str:
    preferred = (
        "СвОКВЭДОсн",
        "КодОКВЭД",
        "КодОКВЭДОсн",
    )
    for element in root.iter():
        if local_name(element.tag) in preferred:
            for key, value in element.attrib.items():
                if key.lower() in {"кодоквэд", "кодоквэдосн"} and value:
                    return value.strip()
    return ""


def classify_okved(code: str) -> str:
    return _classify_okved(code)


def is_moscow(root: ET.Element) -> bool:
    region = _walk_attr(root, ("КодРегион", "КодРегиона", "КодСубъекта"))
    if is_moscow_label(region):
        return True
    text = " ".join(
        _clean(value)
        for value in (
            _walk_attr(root, ("Регион", "НаимРегион")),
            _walk_text(root, {"Регион", "НаимРегион", "НаимРегионКрат"}),
        )
        if value
    )
    return is_moscow_label(text)


def candidate_from_registry_element(root: ET.Element, source: str) -> Candidate | None:
    tag = local_name(root.tag)
    has_inn = bool(_first_attr(root.attrib, "ИНН", "ИННЮЛ", "ИННФЛ", "ИННИП"))
    has_entity_id = bool(_first_attr(root.attrib, "ОГРН", "ОГРНИП"))
    is_registry_person = tag in {"СвЮЛ", "СвИП", "СвЮЛСведения", "СвИПСведения"}
    if not is_registry_person and not (has_inn and has_entity_id):
        return None

    inn = _first_attr(root.attrib, "ИНН", "ИННЮЛ", "ИННФЛ", "ИННИП")
    if not inn:
        inn = _first_matching_attr(root.attrib, r"^ИНН")
    ogrn = _first_attr(root.attrib, "ОГРН")
    ogrnip = _first_attr(root.attrib, "ОГРНИП")

    inn = normalize_inn(inn)
    ogrn = normalize_ogrn(ogrn)
    ogrnip = normalize_ogrnip(ogrnip)
    if not inn:
        return None
    if not ogrn and not ogrnip:
        return None

    company = _first_attr(
        root.attrib,
        "ПолнНаимОПФ",
        "НаимЮЛПолн",
        "НаимЮЛ",
        "НаимВидИП",
    )
    company = company or _walk_attr(root, ("НаимЮЛПолн", "НаимСокр", "ФИО"))
    if not company:
        company = ""

    code = _okved(root)
    city = "Москва" if is_moscow(root) else _walk_text(
        root, {"Город", "НаселенныйПункт", "НаимНаселПункта"}
    )

    responsible = _walk_text(
        root,
        {"СвРуководитель", "ФИОРук", "ФИО"},
    )

    return Candidate(
        company=company,
        inn=inn,
        ogrn=ogrn,
        ogrnip=ogrnip,
        city=city or "Москва",
        sector=classify_okved(code),
        source=source,
        comment=f"Официальная XML-выгрузка; ОКВЭД={code or 'не указан'}",
    )


@dataclass(frozen=True)
class FNSBulkSource:
    path: str
    only_moscow: bool = True
    source_name: str = "ФНС — ЕГРЮЛ/ЕГРИП"

    def iter_candidates(self) -> Iterator[Candidate]:
        source_path = Path(self.path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)

        if source_path.suffix.lower() != ".zip":
            yield from self._parse_xml(source_path)
            return

        with zipfile.ZipFile(source_path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".xml"):
                    continue
                with archive.open(info) as handle:
                    yield from self._parse_stream(handle)

    def load(self) -> list[Candidate]:
        return list(self.iter_candidates())

    def _parse_stream(self, handle) -> Iterator[Candidate]:
        context = ET.iterparse(handle, events=("end",))
        for _, element in context:
            if local_name(element.tag) in RECORD_TAGS:
                candidate = candidate_from_registry_element(element, self.source_name)
                if candidate and (not self.only_moscow or is_moscow(element)):
                    yield candidate
                element.clear()

    def _parse_xml(self, xml_path: Path) -> Iterator[Candidate]:
        context = ET.iterparse(xml_path, events=("end",))
        for _, element in context:
            if local_name(element.tag) in RECORD_TAGS:
                candidate = candidate_from_registry_element(element, self.source_name)
                if candidate and (not self.only_moscow or is_moscow(element)):
                    yield candidate
                element.clear()
