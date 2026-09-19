from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
import sqlite3
import zipfile

from lxml import etree

from .normalize import inn, ogrn, ogrnip, name
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
                "CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY CHECK(id=1), source_date TEXT NOT NULL)"
            )
            db.commit()

    def get(self, value: str) -> FNSRecord | None:
        key = inn(value)
        if not key:
            return None
        with sqlite3.connect(self.db_path) as db:
            row = db.execute(
                "SELECT registry_id,inn,ogrn,ogrnip,company,address,status,source_date "
                "FROM entity WHERE inn=? ORDER BY source_date DESC LIMIT 1",
                (key,),
            ).fetchone()
        return FNSRecord(*row) if row else None

    def import_snapshot(self, path: str) -> int:
        source_path = Path(path)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)

        total = 0
        newest_date: str | None = None
        for stream in self._open_xml(source_path):
            source_date = self._source_date(stream)
            if not source_date:
                stream.close()
                continue
            newest_date = max(newest_date or source_date, source_date)
            for _, element in etree.iterparse(
                stream,
                events=("end",),
                tag=("СвЮЛ", "СвИП"),
                recover=False,
            ):
                record = self._parse(element, source_date)
                if record:
                    self._upsert(record)
                    total += 1
                element.clear()
                parent = element.getparent()
                if parent is not None:
                    while element.getprevious() is not None:
                        del parent[0]
            stream.close()

        if not newest_date:
            raise ValueError("В FNS snapshot отсутствует ДатаВыг")

        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO meta(id,source_date) VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET source_date=excluded.source_date",
                (newest_date,),
            )
            db.commit()
        return total

    def _upsert(self, record: FNSRecord) -> None:
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO entity(registry_id,inn,ogrn,ogrnip,company,address,status,source_date) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(registry_id) DO UPDATE SET inn=excluded.inn,ogrn=excluded.ogrn,"
                "ogrnip=excluded.ogrnip,company=excluded.company,address=excluded.address,"
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
            db.commit()

    @staticmethod
    def _open_xml(path: Path):
        if path.suffix.lower() == ".xml":
            yield path.open("rb")
            return
        if path.suffix.lower() != ".zip":
            raise ValueError("FNS snapshot должен быть XML или ZIP")
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".xml"):
                    continue
                yield BytesIO(archive.read(info.filename))

    @staticmethod
    def _source_date(stream) -> str:
        stream.seek(0)
        for _, root in etree.iterparse(stream, events=("start",), recover=False):
            return root.get("ДатаВыг", "").strip()
        return ""

    @classmethod
    def _parse(cls, element, source_date: str) -> FNSRecord | None:
        tag = etree.QName(element).localname
        if tag == "СвЮЛ":
            i = inn(element.get("ИНН"))
            o = ogrn(element.get("ОГРН"))
            if not (len(i) == 10 and valid_inn(i) and valid_ogrn(o)):
                return None
            status = cls._company_status(element)
            company = name(element.get("НаимЮЛПолн") or element.get("НаимСокр"))
            registry_id = o
            ogrnip_value = ""
        else:
            i = inn(element.get("ИННФЛ") or element.get("ИНН"))
            p = ogrnip(element.get("ОГРНИП"))
            if not (len(i) == 12 and valid_inn(i) and valid_ogrnip(p)):
                return None
            status = cls._ip_status(element)
            company = name(" ".join(x for x in (element.get("Фамилия"), element.get("Имя"), element.get("Отчество")) if x))
            registry_id = p
            o, ogrnip_value = "", p

        return FNSRecord(
            registry_id=registry_id,
            inn=i,
            ogrn=o,
            ogrnip=ogrnip_value,
            company=company,
            address=cls._address(element),
            status=status,
            source_date=source_date,
        )

    @staticmethod
    def _company_status(element) -> str:
        status_node = element.find("СвСтатус")
        raw = ""
        if status_node is not None:
            raw = status_node.get("НаимСтатусЮЛ") or status_node.get("СтатусЮЛ") or ""
        if not raw and element.get("ДатаПрекрЮЛ"):
            return "liquidated"
        return COMPANY_STATUS.get(raw.strip().lower(), "unknown")

    @staticmethod
    def _ip_status(element) -> str:
        if element.find("СвПрекрИП") is not None:
            return "closed"
        status_node = element.find("СвСтатус")
        raw = ""
        if status_node is not None:
            raw = status_node.get("НаимСтатусИП") or status_node.get("СтатусИП") or ""
        return IP_STATUS.get(raw.strip().lower(), "unknown") if raw else "active"

    @staticmethod
    def _address(element) -> str:
        node = element.find("СвАдресЮЛ")
        if node is None:
            node = element.find("АдресЮЛ")
        if node is None:
            node = element.find("СвАдресИП")
        if node is None:
            return ""
        values: list[str] = []
        for child in node.iter():
            for value in child.attrib.values():
                text = str(value).strip()
                if text and text not in values and len(text) > 1:
                    values.append(text)
        return ", ".join(values[:16])
