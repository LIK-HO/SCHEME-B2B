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
