from __future__ import annotations

import time
from typing import Any

import httpx

from .config import Settings


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

    def _request(self, method: str, table_id: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}/{table_id}"
        last_error = ""
        for attempt in range(self.max_retries + 1):
            response = httpx.request(method, url, headers=self.headers, timeout=self.timeout, **kwargs)
            if response.status_code < 400:
                return response.json()

            last_error = response.text[:500]
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt >= self.max_retries:
                raise AirtableError(f"Airtable {response.status_code}: {last_error}")

            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(float(retry_after), 30.0) if retry_after else 2.0**attempt
            except ValueError:
                delay = 2.0**attempt
            time.sleep(delay)

        raise AirtableError(last_error or "Airtable request failed")

    def list_records(\n        self, table_id: str, fields: list[str] | None = None, page_size: int = 100\n    ) -> list[dict[str, Any]]:
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
        formula = f'{{Ключ ИНН}}="{inn}"'
        payload = self._request(
            "GET",
            table_id,
            params={"pageSize": 1, "maxRecords": 1, "filterByFormula": formula},
        )
        return bool(payload.get("records"))

    def find_first_by_field(self, table_id: str, field_name: str, value: str) -> dict[str, Any] | None:
        escaped = value.replace("\\\\", "\\\\\\\\").replace('"', '\\"')
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

    def update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PATCH",
            table_id,
            json={"records": [{"id": record_id, "fields": fields}], "typecast": False},
        )

    def get_search_profile(self, settings: Settings) -> dict[str, Any] | None:
        escaped = settings.search_profile_name.replace("\\\\", "\\\\\\\\").replace('"', '\\"')
        formula = f'{{Профиль поиска}}="{escaped}"'
        payload = self._request(
            "GET",
            settings.airtable_table_search,
            params={"pageSize": 1, "maxRecords": 1, "filterByFormula": formula},
        )
        records = payload.get("records", [])
        return records[0] if records else None

    def find_notification(self, table_id: str, event_id: str, channel: str) -> dict[str, Any] | None:
        event = event_id.replace("\\\\", "\\\\\\\\").replace('"', '\\"')
        chan = channel.replace("\\\\", "\\\\\\\\").replace('"', '\\"')
        formula = f'AND({{Идентификатор события}}="{event}",{{Канал}}="{chan}")'
        payload = self._request(
            "GET",
            table_id,
            params={"pageSize": 1, "maxRecords": 1, "filterByFormula": formula},
        )
        records = payload.get("records", [])
        return records[0] if records else None
