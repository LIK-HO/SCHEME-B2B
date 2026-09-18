from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .registry import FNSBulkSource
from .validation import validate_requisites


class IndexBase(DeclarativeBase):
    pass


class FNSIndexRow(IndexBase):
    __tablename__ = "fns_index"

    inn: Mapped[str] = mapped_column(String(12), primary_key=True)
    ogrn: Mapped[str] = mapped_column(String(15), default="")
    ogrnip: Mapped[str] = mapped_column(String(15), default="")
    company: Mapped[str] = mapped_column(String(500), default="")
    verified_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class FNSIndex:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url, future=True, pool_pre_ping=True)
        IndexBase.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def get(self, inn: str) -> FNSIndexRow | None:
        with self.sessions() as session:
            return session.scalar(select(FNSIndexRow).where(FNSIndexRow.inn == inn))

    def rebuild(self, snapshot_path: str) -> int:
        if not Path(snapshot_path).exists():
            raise FileNotFoundError(snapshot_path)

        count = 0
        with self.sessions() as session:
            for candidate in FNSBulkSource(snapshot_path, only_moscow=False).iter_candidates():
                validation = validate_requisites(candidate.inn, candidate.ogrn, candidate.ogrnip)
                if not validation.valid:
                    continue
                row = FNSIndexRow(
                    inn=validation.inn,
                    ogrn=validation.ogrn,
                    ogrnip=validation.ogrnip,
                    company=candidate.company,
                    verified_at=datetime.utcnow(),
                )
                session.merge(row)
                count += 1
                if count % 1000 == 0:
                    session.commit()
            session.commit()
        return count
