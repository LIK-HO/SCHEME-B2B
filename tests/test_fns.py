from pathlib import Path
import sqlite3
import zipfile

import pytest

from scheme_b2b.fns import FNSIndex


def _xml(date="2026-09-19", status="Действующее", address=False):
    extra = (
        '<СвАдресЮЛ><АдресРФ Индекс="123456" Регион="77" Город="Москва" '
        'Улица="Тестовая"/></СвАдресЮЛ>'
        if address
        else ""
    )
    return (
        f'<EGRUL ДатаВыг="{date}">'
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" НаимЮЛполн="ООО РОМАШКА">'
        f'<СвСтатус НаимСтатусЮЛ="{status}"/>{extra}</СвЮЛ></EGRUL>'
    )


def test_fns_import_and_lookup(tmp_path: Path):
    path = tmp_path / "fns.xml"
    path.write_text(_xml(), encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    assert index.import_snapshot(str(path)) == 1
    row = index.get("7 707 083 893")
    assert row is not None
    assert row.active


def test_liquidated_is_not_active(tmp_path: Path):
    path = tmp_path / "fns.xml"
    path.write_text(_xml(status="Ликвидировано"), encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    index.import_snapshot(str(path))
    assert index.get("7707083893") is not None
    assert not index.get("7707083893").active


def test_latest_snapshot_replaces_old_status(tmp_path: Path):
    old_path = tmp_path / "old.xml"
    new_path = tmp_path / "new.xml"
    old_path.write_text(_xml("2026-09-18", "Действующее"), encoding="utf-8")
    new_path.write_text(_xml("2026-09-19", "Ликвидировано"), encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    index.import_snapshot(str(old_path))
    index.import_snapshot(str(new_path))
    assert not index.get("7707083893").active


def test_old_snapshot_does_not_rewind_meta_date(tmp_path: Path):
    new_path = tmp_path / "new.xml"
    old_path = tmp_path / "old.xml"
    new_path.write_text(_xml("2026-09-19"), encoding="utf-8")
    old_path.write_text(_xml("2026-09-18"), encoding="utf-8")
    db_path = tmp_path / "fns.sqlite3"
    index = FNSIndex(f"sqlite:///{db_path}")
    index.import_snapshot(str(new_path))
    index.import_snapshot(str(old_path))
    with sqlite3.connect(db_path) as db:
        value = db.execute("SELECT source_date FROM meta WHERE id=1").fetchone()[0]
    assert value == "2026-09-19"


def test_zip_import(tmp_path: Path):
    path = tmp_path / "fns.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data.xml", _xml())
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    assert index.import_snapshot(str(path)) == 1
    assert index.get("7707083893").active


def test_address_is_extracted(tmp_path: Path):
    path = tmp_path / "fns.xml"
    path.write_text(_xml(address=True), encoding="utf-8")
    row = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    row.import_snapshot(str(path))
    record = row.get("7707083893")
    assert record is not None
    assert "Москва" in record.address


def test_invalid_or_missing_snapshot_date(tmp_path: Path):
    missing = tmp_path / "missing-date.xml"
    future = tmp_path / "future.xml"
    missing.write_text(
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195"/></EGRUL>',
        encoding="utf-8",
    )
    future.write_text(_xml("2999-01-01"), encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    with pytest.raises(ValueError, match="ДатаВыг"):
        index.import_snapshot(str(missing))
    with pytest.raises(ValueError, match="ДатаВыг"):
        index.import_snapshot(str(future))


def test_invalid_path_and_extension(tmp_path: Path):
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    with pytest.raises(FileNotFoundError):
        index.import_snapshot(str(tmp_path / "missing.xml"))
    invalid = tmp_path / "data.txt"
    invalid.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="XML или ZIP"):
        index.import_snapshot(str(invalid))
