import httpx

from scheme_b2b.airtable import AirtableClient, AirtableError


class FakeSettings:
    airtable_token = "token"
    airtable_base_id = "appI8LyuBMv5z468N"
    airtable_timeout_seconds = 1
    search_profile_name = "Москва B2B — базовый"
    airtable_table_search = "tblNgRcnSv60i076B"


def test_airtable_retries_network_error(monkeypatch):
    calls = {"count": 0}

    def fake_request(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ConnectError("temporary")
        return httpx.Response(200, json={"records": []})

    monkeypatch.setattr("scheme_b2b.airtable.httpx.request", fake_request)
    monkeypatch.setattr("scheme_b2b.airtable.time.sleep", lambda _: None)

    client = AirtableClient(FakeSettings())
    assert client._request("GET", "tbltest") == {"records": []}
    assert calls["count"] == 2


def test_airtable_profile_must_be_unique(monkeypatch):
    client = AirtableClient(FakeSettings())
    monkeypatch.setattr(
        client,
        "_request",
        lambda *args, **kwargs: {"records": [{"id": "1"}, {"id": "2"}]},
    )

    try:
        client.get_search_profile(FakeSettings())
    except AirtableError as exc:
        assert "не уникален" in str(exc)
    else:
        raise AssertionError("Expected duplicate search profile to fail")
