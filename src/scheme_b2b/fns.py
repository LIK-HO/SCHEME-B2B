from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sqlite3
import zipfile
from collections.abc import Callable, Iterator

from lxml import etree

from .normalize import inn, ogrn, ogrnip, text
from .validate import valid_inn, valid_ogrn, valid_ogrnip


COMPANY_STATUS = {
    "действующее": "active",
    "действующий": "active",
    "в стадии ликвидации": "liquidating",
    "находится в процессе ликвидации": "liquidating",
    "ликвидировано": "liquidated",
    "прекратило деятельность": "liquidated",
    "прекратило деятельность при реорганизации": "liquidated",
    "прекратило деятельность (исключение из егрюл недействующего юл)": "liquidated",
    "в стадии реорганизации": "reorganizing",
    "находится в процессе реорганизации": "reorganizing",
    "находится в стадии реорганизации": "reorganizing",
    "признано банкротом": "bankrupt",
}

IP_STATUS = {
    "действующий": "active",
    "действующее": "active",
    "прекращено": "closed",
    "прекратил деятельность": "closed",
    "прекратил деятельность в качестве индивидуального предпринимателя": "closed",
}


@dataclass(frozen=True)
class FNSRecord:
    registry_id: str
    inn: str
    ogrn: str
    ogrnip: str
    company: str
    address: str
    status: str
    source_date: str

    @property
    def active(self) -> bool:
        return self.status == "active"


class FNSIndex:
    def __init__(self, db_path: str = "data/fns.sqlite3"):
        self.db_path = db_path.removeprefix("sqlite:///")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS entity("
                "registry_id TEXT PRIMARY KEY, inn TEXT NOT NULL, ogrn TEXT NOT NULL DEFAULT '', "
                "ogrnip TEXT NOT NULL DEFAULT '', company TEXT NOT NULL, address TEXT NOT NULL DEFAULT '', "
                "status TEXT NOT NULL, source_date TEXT NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_entity_inn ON entity(inn)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS meta("
                "id INTEGER PRIMARY KEY CHECK(id=1), source_date TEXT NOT NULL)"
            )
            db.commit()

    def get(self, value: str) -> FNSRecord | None:
        key = inn(value)
        if not key:
            return None
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT registry_id,inn,ogrn,ogrnip,company,address,status,source_date "
                "FROM entity WHERE inn=? ORDER BY source_date DESC, registry_id ASC LIMIT 1",
                (key,),
            ).fetchone()
        return FNSRecord(*row) if row else None

    def import_snapshot(self, path: str) -> int:
        source_path = Path(path)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        total = 0
        newest_date: str | None = None

        with sqlite3.connect(self.db_path) as db:
            for opener in self._open_xml(source_path):
                with opener() as stream:
                    source_date = self._source_date(stream)

                if not source_date:
                    continue
                newest_date = max(newest_date or source_date, source_date)

                with opener() as stream:
                    for _, element in etree.iterparse(
                        stream,
                        events=("end",),
                        recover=False,
                    ):
                        if etree.QName(element).localname not in {"СвЮЛ", "СвИП"}:
                            continue

                        record = self._parse(element, source_date)
                        if record:
                            db.execute(
                                "INSERT INTO entity("
                                "registry_id,inn,ogrn,ogrnip,company,address,status,source_date)"
                                "VALUES(?,?,?,?,?,?,?,?) "
                                "ON CONFLICT(registry_id) DO UPDATE SET "
                                "inn=excluded.inn,ogrn=excluded.ogrn,ogrnip=excluded.ogrnip,"
                                "company=excluded.company,address=excluded.address,"
                                "status=excluded.status,source_date=excluded.source_date "
                                "WHERE excluded.source_date >= entity.source_date",
                                (
                                    record.registry_id,
                                    record.inn,
                                    record.ogrn,
                                    record.ogrnip,
                                    record.company,
                                    record.address,
                                    record.status,
                                    record.source_date,
                                ),
                            )
                            total += 1

                        element.clear()
                        parent = element.getparent()
                        if parent is not None:
                            while element.getprevious() is not None:
                                del parent[0]

            if not newest_date:
                raise ValueError("В FNS snapshot отсутствует ДатаВыг")
            self._validate_source_date(newest_date)

            current = db.execute("SELECT source_date FROM meta WHERE id=1").fetchone()
            current_date = current[0] if current else ""
            meta_date = max(current_date, newest_date)
            db.execute(
                "INSERT INTO meta(id,source_date) VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET source_date=excluded.source_date",
                (meta_date,),
            )
            db.commit()

        return total

    @staticmethod
    def _open_xml(path: Path) -> Iterator[Callable[[], object]]:
        if path.suffix.lower() == ".xml":
            yield lambda: path.open("rb")
            return

        if path.suffix.lower() != ".zip":
            raise ValueError("FNS snapshot должен быть XML или ZIP")

        archive = zipfile.ZipFile(path)
        try:
            infos = [
                info
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".xml")
            ]
            for info in infos:
                yield lambda info=info: archive.open(info)
        finally:
            archive.close()

    @staticmethod
    def _source_date(stream) -> str:
        for _, root in etree.iterparse(stream, events=("start",), recover=False):
            return root.get("ДатаВыг", "").strip()
        return ""

    @staticmethod
    def _validate_source_date(value: str) -> None:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("В FNS snapshot указана некорректная ДатаВыг") from exc
        if parsed > date.today():
            raise ValueError("В FNS snapshot указана будущая ДатаВыг")

    @staticmethod
    def _child(element, *names):
        wanted = set(names)
        for child in element:
            if etree.QName(child).localname in wanted:
                return child
        return None

    @classmethod
    def _parse(cls, element, source_date: str) -> FNSRecord | None:
        tag = etree.QName(element).localname

        if tag == "СвЮЛ":
            i = inn(element.get("ИНН"))
            o = ogrn(element.get("ОГРН"))
            if not (len(i) == 10 and valid_inn(i) and valid_ogrn(o)):
                return None

            return FNSRecord(
                registry_id=o,
                inn=i,
                ogrn=o,
                ogrnip="",
                company=cls._company_name(element),
                address=cls._address(element),
                status=cls._company_status(element),
                source_date=source_date,
            )

        i = inn(element.get("ИННФЛ") or element.get("ИНН"))
        p = ogrnip(element.get("ОГРНИП"))
        if not (len(i) == 12 and valid_inn(i) and valid_ogrnip(p)):
            return None

        return FNSRecord(
            registry_id=p,
            inn=i,
            ogrn="",
            ogrnip=p,
            company=cls._ip_name(element),
            address=cls._address(element),
            status=cls._ip_status(element),
            source_date=source_date,
        )

    @classmethod
    def _company_name(cls, element) -> str:
        node = cls._child(element, "СвНаимЮЛ")
        if node is not None:
            value = node.get("НаимЮЛПолн") or node.get("НаимСокр")
            if value:
                return text(value)
        return text(element.get("НаимЮЛПолн") or element.get("НаимСокр"))

    @classmethod
    def _ip_name(cls, element) -> str:
        node = cls._child(element, "СвФЛ")
        if node is not None:
            parts = [
                node.get("ФамилияРус") or node.get("Фамилия"),
                node.get("ИмяРус") or node.get("Имя"),
                node.get("ОтчествоРус") or node.get("Отчество"),
            ]
            return text(" ".join(p for p in parts if p))
        return text(
            " ".join(
                p
                for p in (element.get("Фамилия"), element.get("Имя"), element.get("Отчество"))
                if p
            )
        )

    @classmethod
    def _company_status(cls, element) -> str:
        status_node = cls._child(element, "СвСтатус")
        raw = ""
        if status_node is not None:
            raw = status_node.get("НаимСтатусЮЛ") or status_node.get("СтатусЮЛ") or ""
        if not raw and element.get("ДатаПрекрЮЛ"):
            return "liquidated"
        return COMPANY_STATUS.get(raw.strip().lower(), "unknown")

    @classmethod
    def _ip_status(cls, element) -> str:
        if cls._child(element, "СвПрекрИП") is not None:
            return "closed"
        status_node = cls._child(element, "СвСтатус")
        raw = ""
        if status_node is not None:
            raw = status_node.get("НаимСтатусИП") or status_node.get("СтатусИП") or ""
        return IP_STATUS.get(raw.strip().lower(), "unknown") if raw else "active"

    @staticmethod
    def _address(element) -> str:
        node = None
        for name in ("СвАдресЮЛ", "АдресЮЛ", "СвАдресИП"):
            for child in element:
                if etree.QName(child).localname == name:
                    node = child
                    break
            if node is not None:
                break
        if node is None:
            return ""

        values: list[str] = []
        for child in node.iter():
            for value in child.attrib.values():
                item = text(str(value))
                if item and item not in values and len(item) > 1:
                    values.append(item)
        return ", ".join(values[:16])
