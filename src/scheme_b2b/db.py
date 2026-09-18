from datetime import timedelta
from uuid import uuid4

from sqlalchemy import create_engine, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import Base, CompanyIdentity, Lease
from .time_utils import UTC, ensure_aware, now_utc


class LeaseBusyError(RuntimeError):
    """Raised when another worker currently owns the requested role lease."""


def create_session_factory(settings: Settings):
    connect_args = {"check_same_thread": False, "timeout": 30} if settings.local_db_url.startswith("sqlite") else {}
    engine = create_engine(
        settings.local_db_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def acquire_lease(session_factory, name: str, ttl_seconds: int, owner: str | None = None) -> str:
    """Acquire a durable single-holder lease; expired leases are safely reclaimable."""
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    lease_owner = owner or f"worker-{uuid4().hex}"
    now = now_utc()
    expires_at = now + timedelta(seconds=ttl_seconds)

    with session_factory() as session:
        try:
            row = session.get(Lease, name)
            if row is not None:
                current_expiry = ensure_aware(row.expires_at, tz=UTC)
                if current_expiry > now:
                    raise LeaseBusyError(name)
                result = session.execute(
                    update(Lease)
                    .where(
                        Lease.name == name,
                        Lease.owner == row.owner,
                        Lease.expires_at == row.expires_at,
                    )
                    .values(
                        owner=lease_owner,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
                )
                if result.rowcount != 1:
                    session.rollback()
                    raise LeaseBusyError(name)
            else:
                session.add(
                    Lease(
                        name=name,
                        owner=lease_owner,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
                )
            session.commit()
        except LeaseBusyError:
            session.rollback()
            raise
        except IntegrityError as exc:
            session.rollback()
            raise LeaseBusyError(name) from exc
    return lease_owner


def release_lease(session_factory, name: str, owner: str) -> bool:
    """Release only the lease still owned by this worker; never delete a newer holder."""
    with session_factory() as session:
        row = session.get(Lease, name)
        if row is None or row.owner != owner:
            return False
        session.delete(row)
        session.commit()
        return True


def claim_company_identity(
    session_factory,
    inn: str,
    run_id: str,
    source: str,
) -> tuple[bool, CompanyIdentity]:
    """Atomically claim a normalized INN in the core master-identity store."""
    with session_factory() as session:
        existing = session.get(CompanyIdentity, inn)
        if existing is not None:
            return False, existing
        identity = CompanyIdentity(
            inn=inn,
            first_run_id=run_id,
            source=source,
        )
        try:
            session.add(identity)
            session.commit()
            return True, identity
        except IntegrityError:
            session.rollback()
            existing = session.get(CompanyIdentity, inn)
            if existing is None:
                raise
            return False, existing


def mark_company_identity_projected(
    session_factory,
    inn: str,
    airtable_record_id: str,
) -> None:
    with session_factory() as session:
        identity = session.get(CompanyIdentity, inn)
        if identity is None:
            raise KeyError(f"Company identity not found: {inn}")
        identity.status = "projected"
        identity.airtable_record_id = airtable_record_id
        identity.updated_at = now_utc()
        session.commit()
