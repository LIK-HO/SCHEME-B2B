from pathlib import Path

from scheme_b2b.config import Settings
from scheme_b2b.db import acquire_lease, claim_company_identity, mark_company_identity_projected
from scheme_b2b.models import RunItem
from scheme_b2b.service import SearchService
from scheme_b2b.sources import Candidate


class FakeSource:
    name = "fake"

    def __init__(self, candidates):
        self.candidates = list(candidates)

    def iter_candidates(self):
        yield from self.candidates


class FakeAirtable:
    def __init__(self):
        self.keys = set()
        self.created = []
        self.raise_after_create = False

    def get_search_profile(self, settings):
        return None

    def list_inn_keys(self, table_id):
        return set(self.keys)

    def exists_by_inn(self, table_id, inn):
        return inn in self.keys

    def find_first_by_inn(self, table_id, inn):
        return {"id": "recTEST", "fields": {"ИНН": inn}} if inn in self.keys else None

    def create_record(self, table_id, fields):
        self.created.append((table_id, fields))
        self.keys.add(fields["ИНН"])
        if self.raise_after_create:
            raise RuntimeError("ambiguous timeout")
        return {"id": "recTEST"}

    def update_record(self, table_id, record_id, fields):
        return {"id": record_id, "fields": fields}

    def find_notification(self, table_id, event_id, channel):
        return None


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        local_db_url=f"sqlite:///{tmp_path / 'run.sqlite3'}",
        require_fns_confirmation=False,
        max_new_records_per_run=1,
        max_candidates_per_source=10,
        email_enabled=False,
        max_enabled=False,
        search_lease_seconds=3600,
        outbox_lease_seconds=600,
    )


def test_run_once_reports_partial_when_new_record_limit_is_hit(tmp_path: Path):
    airtable = FakeAirtable()
    candidate = Candidate(
        company="ООО Ромашка",
        inn="7707083893",
        ogrn="1027700132195",
        sector="Логистика",
    )
    service = SearchService(
        _settings(tmp_path),
        airtable,
        sources=[FakeSource([candidate])],
    )

    result = service.run_once(manual=True)

    assert result["status"] == "partial"
    assert result["inserted"] == 1
    assert "Лимит новых компаний за запуск достигнут" in result["summary"]
    assert len(airtable.created) == 1
    with service.session_factory() as session:
        item = session.query(RunItem).one()
    assert item.inn == "7707083893"
    assert item.source == "fake"
    assert item.outcome == "created"
    assert item.airtable_record_id == "recTEST"


def test_run_once_fails_closed_without_sources(tmp_path: Path):
    airtable = FakeAirtable()
    service = SearchService(_settings(tmp_path), airtable, sources=[])

    result = service.run_once(manual=True)

    assert result["status"] == "error"
    assert result["errors"] == 1


def test_run_once_reconciles_ambiguous_airtable_create(tmp_path: Path):
    airtable = FakeAirtable()
    airtable.raise_after_create = True
    candidate = Candidate(
        company="ООО Ромашка",
        inn="7707083893",
        ogrn="1027700132195",
        sector="Логистика",
    )
    settings = _settings(tmp_path)
    settings.max_new_records_per_run = 10
    service = SearchService(
        settings,
        airtable,
        sources=[FakeSource([candidate])],
    )

    result = service.run_once(manual=True)

    assert result["status"] == "success"
    assert result["inserted"] == 1
    with service.session_factory() as session:
        item = session.query(RunItem).one()
    assert item.outcome == "reconciled"
    assert item.airtable_record_id == "recTEST"


def test_run_once_skips_when_another_worker_holds_lease(tmp_path: Path):
    airtable = FakeAirtable()
    settings = _settings(tmp_path)
    service = SearchService(settings, airtable, sources=[])
    acquire_lease(service.session_factory, "search-run", 3600, owner="other-worker")

    result = service.run_once(manual=True)

    assert result == {"status": "skipped", "reason": "another_search_worker_is_running"}


def test_run_once_blocks_identity_already_owned_by_core(tmp_path: Path):
    settings = _settings(tmp_path)
    first = SearchService(
        settings,
        FakeAirtable(),
        sources=[FakeSource([])],
    )
    claim_company_identity(
        first.session_factory,
        "7707083893",
        "seed-run",
        "seed",
    )
    mark_company_identity_projected(
        first.session_factory,
        "7707083893",
        "recSEED",
    )

    second_airtable = FakeAirtable()
    service = SearchService(
        settings,
        second_airtable,
        sources=[
            FakeSource(
                [
                    Candidate(
                        company="ООО Ромашка",
                        inn="7707083893",
                        ogrn="1027700132195",
                        sector="Логистика",
                    )
                ]
            )
        ],
    )
    result = service.run_once(manual=True)

    assert result["duplicates"] == 1
    assert result["inserted"] == 0
    assert not second_airtable.created


def test_run_once_repairs_pending_core_projection(tmp_path: Path):
    settings = _settings(tmp_path)
    seed = SearchService(settings, FakeAirtable(), sources=[FakeSource([])])
    claimed, identity = claim_company_identity(
        seed.session_factory,
        "7707083893",
        "seed-run",
        "seed",
    )
    assert claimed
    assert identity.status == "projection_pending"

    airtable = FakeAirtable()
    service = SearchService(
        settings,
        airtable,
        sources=[
            FakeSource(
                [
                    Candidate(
                        company="ООО Ромашка",
                        inn="7707083893",
                        ogrn="1027700132195",
                        sector="Логистика",
                    )
                ]
            )
        ],
    )
    result = service.run_once(manual=True)

    assert result["inserted"] == 1
    with service.session_factory() as session:
        from scheme_b2b.models import CompanyIdentity

        row = session.get(CompanyIdentity, "7707083893")
    assert row.status == "projected"
