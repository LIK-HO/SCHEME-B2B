from pathlib import Path

from scheme_b2b.config import Settings
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

    def get_search_profile(self, settings):
        return None

    def list_inn_keys(self, table_id):
        return set(self.keys)

    def exists_by_inn(self, table_id, inn):
        return inn in self.keys

    def create_record(self, table_id, fields):
        self.created.append((table_id, fields))
        self.keys.add(fields["ИНН"])
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


def test_run_once_fails_closed_without_sources(tmp_path: Path):
    airtable = FakeAirtable()
    service = SearchService(_settings(tmp_path), airtable, sources=[])

    result = service.run_once(manual=True)

    assert result["status"] == "error"
    assert result["errors"] == 1
