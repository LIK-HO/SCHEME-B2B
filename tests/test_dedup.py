from scheme_b2b.dedup import GlobalDeduplicator
from scheme_b2b.normalization import normalize_inn

class FakeStore:
    def __init__(self, existing: set[tuple[str, str]]):
        self.existing = existing

    def exists_by_inn(self, table_id: str, inn: str) -> bool:
        return (table_id, inn) in self.existing

    def list_inn_keys(self, table_id: str) -> set[str]:
        return {normalize_inn(inn) for table, inn in self.existing if table == table_id}

def test_global_dedup_checks_all_three_lists():
    store = FakeStore({
        ("companies", "7707083893"),
        ("clients", "5401000000"),
        ("archive", "7811000000"),
    })
    service = GlobalDeduplicator(store, "companies", "clients", "archive")

    result = service.check("7 707 083 893")

    assert result.duplicate
    assert result.duplicate_in_companies
    assert not result.duplicate_in_clients
    assert not result.duplicate_in_archive
    assert result.locations == ("01 Компании",)

def test_global_dedup_finds_archive_match():
    store = FakeStore({("archive", "5401000000")})
    service = GlobalDeduplicator(store, "companies", "clients", "archive")
    result = service.check("5401000000")
    assert result.duplicate_in_archive

def test_global_dedup_uses_primed_snapshot():
    store = FakeStore({("companies", "7707083893"), ("archive", "5401000000")})
    service = GlobalDeduplicator(store, "companies", "clients", "archive")
    service.prime()
    result = service.check("5401000000")
    assert result.duplicate_in_archive
