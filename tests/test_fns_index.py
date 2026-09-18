from pathlib import Path

from scheme_b2b.fns_index import FNSIndex


def test_fns_index_rebuild_and_lookup(tmp_path: Path):
    snapshot = tmp_path / "fns.xml"
    snapshot.write_text(
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>',
        encoding="utf-8",
    )
    db = tmp_path / "index.sqlite3"
    index = FNSIndex(f"sqlite:///{db}")
    assert index.rebuild(str(snapshot)) == 1
    row = index.get("7707083893")
    assert row is not None
    assert row.ogrn == "1027700132195"
    assert index.is_fresh(48)


def test_indexed_verifier_mode(tmp_path):
    from scheme_b2b.fns import FNSVerifier
    from scheme_b2b.fns_index import FNSIndex

    snapshot = tmp_path / "fns.xml"
    snapshot.write_text(
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>',
        encoding="utf-8",
    )
    db = tmp_path / "index.sqlite3"
    FNSIndex(f"sqlite:///{db}").rebuild(str(snapshot))

    class Settings:
        fns_mode = "bulk-index"
        fns_index_db_url = f"sqlite:///{db}"
        fns_egrul_bulk_path = ""
        fns_index_max_age_hours = 48
        fns_verify_url = ""
        fns_verify_token = ""
        source_timeout_seconds = 5

    result = FNSVerifier(Settings()).verify("7707083893", "1027700132195")
    assert result.confirmed

def test_fns_index_rejects_stale_data(tmp_path: Path):
    snapshot = tmp_path / "fns.xml"
    snapshot.write_text(
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>',
        encoding="utf-8",
    )
    db = tmp_path / "index.sqlite3"
    index = FNSIndex(f"sqlite:///{db}")
    index.rebuild(str(snapshot))
    assert not index.is_fresh(0)
