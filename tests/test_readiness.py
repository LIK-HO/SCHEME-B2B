from pathlib import Path

from scheme_b2b.config import Settings
from scheme_b2b.fns import FNSVerifier
from scheme_b2b.sources import source_configuration_errors


def test_readiness_rejects_missing_local_source(tmp_path: Path):
    settings = Settings(source_json_file=str(tmp_path / "missing.json"))
    errors = source_configuration_errors(settings)
    assert "SOURCE_JSON_FILE not found" in errors[0]


def test_fns_official_readiness_requires_https():
    settings = Settings(
        require_fns_confirmation=True,
        fns_mode="official",
        fns_verify_url="http://example.invalid/verify",
    )
    assert FNSVerifier(settings).readiness_error() == "FNS_VERIFY_URL_MUST_USE_HTTPS"


def test_readiness_rejects_insecure_remote_source():
    settings = Settings(source_json_url="http://example.invalid/source.json")
    errors = source_configuration_errors(settings)
    assert "SOURCE_JSON_URL must be a valid HTTPS URL" in errors



def test_airtable_check_connection_uses_read_path(monkeypatch):
    from scheme_b2b.airtable import AirtableClient

    client = AirtableClient.__new__(AirtableClient)
    captured = {}

    def fake_request(method, table_id, **kwargs):
        captured["method"] = method
        captured["table_id"] = table_id
        captured["params"] = kwargs["params"]
        return {"records": []}

    monkeypatch.setattr(client, "_request", fake_request)
    client.check_connection("tblSearch")
    assert captured == {
        "method": "GET",
        "table_id": "tblSearch",
        "params": {"pageSize": 1, "maxRecords": 1},
    }
