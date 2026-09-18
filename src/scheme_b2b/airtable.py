from __future__ import annotations

import random
import time
from typing import Any

import httpx

from .config import Settings
from .normalization import normalize_inn


class AirtableError(RuntimeError):
    pass


class AirtableClient:
    def __init__(self, settings: Settings):
        if not settings.airtable_token:
            raise AirtableError("AIRTABLE_TOKEN не задан")
        self.base_url = f"https://api.airtable.com/v0/{settings.airtable_base_id}"
        self.headers = {"Authorization": f"Bearer {settings.airtable_token}"}
        self.timeout = settings.airtable_timeout_seconds
        self.max_retries = 3
        self.min_request_interval = 0.21
        self._last_request_at = 0.0

    def _request(self, method: str, table_id: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}/{table_id}"
        last_error = ""
        for attempt in range(self.max_retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
            self._last_request_at = time.monotonic()
            try:
                response = httpx.request(
                    method,
                    url,
                    headers=self.headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except httpx.RequestError as exc:
                last_error = str(exc)[:500]
                if attempt >= self.max_retries:
                    raise AirtableError(f"Airtable network error: {last_error}") from exc
                base_delay = 2.0**attempt
                time.sleep(max(0.1, base_delay * random.uniform(0.8, 1.2)))
                continue

            if response.status_code < 400:
                return response.json()

            last_error = response.text[:500]
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt >= self.max_retries:
                raise AirtableError(f"Airtable {response.status_code}: {last_error}")

            retry_after = response.headers.get("Retry-After")
            try:
                base_delay = min(float(retry_after), 30.0) if retry_after else 2.0**attempt
            except ValueError:
                base_delay = 2.0**attempt
            time.sleep(max(0.1, base_delay * random.uniform(0.8, 1.2)))

        raise AirtableError(last_error or "Airtable request failed")

    def list_records(
        self,
        table_id: str,
        fields: list[str] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        offset: str | None = None
        while True:
            params: list[tuple[str, Any]] = [("pageSize", min(page_size, 100))]
            if fields:
                params.extend(("fields[]", field) for field in fields)
            if offset:
                params.append(("offset", offset))
            payload = self._request("GET", table_id, params=params)
            records.extend(payload.get("records", []))
            offset = payload.get("offset")
            if not offset:
                break
        return records

    def exists_by_inn(self, table_id: str, inn: str) -> bool:
        key = normalize_inn(inn)
        formula = f'{{Ключ ИНН}}="{key}"'
        payload = self._request(
            "GET",
            table_id,
            params={"pageSize": 1, "maxRecords": 1, "filterByFormula": formula},
        )
        return bool(payload.get("records"))

    def find_first_by_field(
        self,
        table_id: str,
        field_name: str,
        value: str,
    ) -> dict[str, Any] | None:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        formula = f'{{{field_name}}}="{escaped}"'
        payload = self._request(
            "GET",
            table_id,
            params={"pageSize": 1, "maxRecords": 1, "filterByFormula": formula},
        )
        records = payload.get("records", [])
        return records[0] if records else None

    def create_record(self, table_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(
            "POST",
            table_id,
            json={"records": [{"fields": fields}], "typecast": False},
        )
        records = payload.get("records", [])
        if not records:
            raise AirtableError("Airtable create returned no record")
        return records[0]

    def update_record(
        self,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "PATCH",
            table_id,
            json={"records": [{"id": record_id, "fields": fields}], "typecast": False},
        )

    def get_search_profile(self, settings: Settings) -> dict[str, Any] | None:
        escaped = settings.search_profile_name.replace("\\", "\\\\").replace('"', '\\"')
        formula = f'{{Профиль поиска}}="{escaped}"'
        payload = self._request(
            "GET",
            settings.airtable_table_search,
            params={"pageSize": 2, "maxRecords": 2, "filterByFormula": formula},
        )
        records = payload.get("records", [])
        if len(records) > 1:
            raise AirtableError(f"Профиль поиска '{settings.search_profile_name}' не уникален")
        return records[0] if records else None

    def list_pending_notifications(self, table_id: str) -> list[dict[str, Any]]:
        formula = 'OR({Статус}="Ожидает",{Статус}="Ошибка")'
        records: list[dict[str, Any]] = []
        offset: str | None = None
        while True:
            params: dict[str, Any] = {"pageSize": 100, "filterByFormula": formula}
            if offset:
                params["offset"] = offset
            payload = self._request("GET", table_id, params=params)
            records.extend(payload.get("records", []))
            offset = payload.get("offset")
            if not offset:
                return records

    def list_inn_keys(self, table_id: str) -> set[str]:
        records = self.list_records(table_id, fields=["Ключ ИНН", "ИНН"], page_size=100)
        keys: set[str] = set()
        for record in records:
            fields = record.get("fields", {})
            key = normalize_inn(str(fields.get("Ключ ИНН") or fields.get("ИНН") or ""))
            if key:
                keys.add(key)
        return keys

    def find_notification(
        self,
        table_id: str,
        event_id: str,
        channel: str,
    ) -> dict[str, Any] | None:
        event = event_id.replace("\\", "\\\\").replace('"', '\\"')
        chan = channel.replace("\\", "\\\\").replace('"', '\\"')
        formula = f'AND({{Идентификатор события}}="{event}",{{Канал}}="{chan}")'
        payload = self._request(
            "GET",
            table_id,
            params={"pageSize": 1, "maxRecords": 1, "filterByFormula": formula},
        )
        records = payload.get("records", [])
        return records[0] if records else None
