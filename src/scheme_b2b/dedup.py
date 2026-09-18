from dataclasses import dataclass
from typing import Protocol

from .normalization import normalize_inn


class DuplicateStore(Protocol):
    def exists_by_inn(self, table_id: str, inn: str) -> bool: ...
    def list_inn_keys(self, table_id: str) -> set[str]: ...


@dataclass(frozen=True)
class DedupResult:
    duplicate_in_companies: bool = False
    duplicate_in_clients: bool = False
    duplicate_in_archive: bool = False

    @property
    def duplicate(self) -> bool:
        return self.duplicate_in_companies or self.duplicate_in_clients or self.duplicate_in_archive

    @property
    def locations(self) -> tuple[str, ...]:
        locations: list[str] = []
        if self.duplicate_in_companies:
            locations.append("01 Компании")
        if self.duplicate_in_clients:
            locations.append("02 Клиенты")
        if self.duplicate_in_archive:
            locations.append("03 Архив")
        return tuple(locations)


class GlobalDeduplicator:
    def __init__(self, store: DuplicateStore, companies_id: str, clients_id: str, archive_id: str):
        self.store = store
        self.companies_id = companies_id
        self.clients_id = clients_id
        self.archive_id = archive_id
        self._snapshot: dict[str, set[str]] | None = None

    def prime(self) -> None:
        self._snapshot = {
            self.companies_id: self.store.list_inn_keys(self.companies_id),
            self.clients_id: self.store.list_inn_keys(self.clients_id),
            self.archive_id: self.store.list_inn_keys(self.archive_id),
        }

    def check(self, inn: str) -> DedupResult:
        key = normalize_inn(inn)
        if not key:
            return DedupResult()

        if self._snapshot is None:
            return DedupResult(
                duplicate_in_companies=self.store.exists_by_inn(self.companies_id, key),
                duplicate_in_clients=self.store.exists_by_inn(self.clients_id, key),
                duplicate_in_archive=self.store.exists_by_inn(self.archive_id, key),
            )

        return DedupResult(
            duplicate_in_companies=key in self._snapshot[self.companies_id],
            duplicate_in_clients=key in self._snapshot[self.clients_id],
            duplicate_in_archive=key in self._snapshot[self.archive_id],
        )
