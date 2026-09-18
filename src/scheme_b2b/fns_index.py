from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from sqlalchemy import DateTime, Integer, String, create_engine, insert
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .registry import FNSBulkSource
from .time_utils import MSK, ensure_aware, now_utc
from .validation import validate_requisites


INDEX_TABLE = "fns_registry_index_v2"


class IndexBase(DeclarativeBase):
    pass


class FNSIndexRow(IndexBase):
    __tablename__ = INDEX_TABLE

    registry_id: Mapped[str] = mapped_column(String(15), primary_key=True)
    inn: Mapped[str] = mapped_column(String(12), index=True)
    ogrn: Mapped[str] = mapped_column(String(13), default="")
    ogrnip: Mapped[str] = mapped_column(String(15), default="")
    company: Mapped[str] = mapped_column(String(500), default="")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FNSIndexMeta(IndexBase):
    __tablename__ = "fns_index_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_path: Mapped[str] = mapped_column(String(1000), default="")
    snapshot_sha256: Mapped[str] = mapped_column(String(64), default="")
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)


class FNSIndex:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, future=True, pool_pre_ping=True)
        IndexBase.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def get(self, inn: str, ogrn: str = "", ogrnip: str = "") -> FNSIndexRow | None:
        registry_id = ogrn or ogrnip
        if not registry_id:
            return None
        with self.sessions() as session:
            row = session.get(FNSIndexRow, registry_id)
            if row is None or row.inn != inn:
                return None
            if ogrn and row.ogrn != ogrn:
                return None
            if ogrnip and row.ogrnip != ogrnip:
                return None
            return row

    def metadata(self) -> FNSIndexMeta | None:
        with self.sessions() as session:
            return session.get(FNSIndexMeta, 1)

    def is_fresh(self, max_age_hours: float, now: datetime | None = None) -> bool:
        meta = self.metadata()
        if meta is None or meta.source_date is None or max_age_hours <= 0:
            return False

        current = ensure_aware(now or now_utc(), tz=MSK)
        source_date = ensure_aware(meta.source_date, tz=MSK)
        age = current - source_date
        return timedelta(0) <= age <= timedelta(hours=max_age_hours)

    def rebuild(self, snapshot_path: str) -> int:
        path = Path(snapshot_path)
        if not path.exists():
            raise FileNotFoundError(path)

        snapshot_sha256 = _sha256(path)
        source_date = _snapshot_date(path)
        if source_date is None:
            raise ValueError("ДатаВыг отсутствует в snapshot ФНС")
        indexed_at = now_utc()
        count = 0
        batch: list[dict[str, object]] = []

        with self.sessions() as session:
            try:
                session.query(FNSIndexRow).delete(synchronize_session=False)

                for candidate in FNSBulkSource(str(path), only_moscow=False).iter_candidates():
                    validation = validate_requisites(candidate.inn, candidate.ogrn, candidate.ogrnip)
                    if not validation.valid:
                        continue

                    batch.append(
                        {
                            "registry_id": validation.ogrn or validation.ogrnip,
                            "inn": validation.inn,
                            "ogrn": validation.ogrn,
                            "ogrnip": validation.ogrnip,
                            "company": candidate.company,
                            "verified_at": indexed_at,
                        }
                    )
                    count += 1

                    if len(batch) >= 1000:
                        session.execute(insert(FNSIndexRow), batch)
                        batch.clear()

                if batch:
                    session.execute(insert(FNSIndexRow), batch)

                session.merge(
                    FNSIndexMeta(
                        id=1,
                        snapshot_path=str(path),
                        snapshot_sha256=snapshot_sha256,
                        indexed_at=indexed_at,
                        source_date=source_date,
                        record_count=count,
                    )
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

        return count


def _sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_date(path: Path) -> datetime | None:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.is_dir() or not info.filename.lower().endswith(".xml"):
                    continue
                with archive.open(info) as handle:
                    root = ET.parse(handle).getroot()
                    break
            else:
                return None
    else:
        root = ET.parse(path).getroot()

    raw = root.attrib.get("ДатаВыг", "").strip()
    if not raw:
        return None
    try:
        return datetime.combine(date.fromisoformat(raw), datetime.min.time(), tzinfo=MSK)
    except ValueError:
        return None
