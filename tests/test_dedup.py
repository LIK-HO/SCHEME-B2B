from scheme_b2b.dedup import GlobalDeduplicator


class FakeStore:
    def __init__(self, existing: set[tuple[str, str]]):
        self.existing = existing

    def exists_by_inn(self, table_id: str, inn: str) -> bool:
        return (table_id, inn) in self.existing


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
