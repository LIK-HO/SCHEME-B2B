from pathlib import Path
from datetime import timedelta

import pytest

from scheme_b2b.db import LeaseBusyError, acquire_lease, create_session_factory, release_lease
from scheme_b2b.config import Settings
from scheme_b2b.time_utils import now_utc


def _factory(tmp_path: Path):
    return create_session_factory(Settings(local_db_url=f"sqlite:///{tmp_path / 'lease.sqlite3'}"))


def test_lease_allows_one_holder_and_owner_only_release(tmp_path: Path):
    factory = _factory(tmp_path)
    owner_a = acquire_lease(factory, "search-run", 60, owner="a")

    with pytest.raises(LeaseBusyError):
        acquire_lease(factory, "search-run", 60, owner="b")

    assert not release_lease(factory, "search-run", "b")
    assert release_lease(factory, "search-run", owner_a)
    assert acquire_lease(factory, "search-run", 60, owner="b") == "b"


def test_expired_lease_is_reclaimable(tmp_path: Path):
    factory = _factory(tmp_path)
    acquire_lease(factory, "search-run", 60, owner="old")

    from scheme_b2b.models import Lease

    with factory() as session:
        row = session.get(Lease, "search-run")
        row.expires_at = now_utc() - timedelta(seconds=1)
        session.commit()

    assert acquire_lease(factory, "search-run", 60, owner="new") == "new"
