from pathlib import Path

from scheme_b2b.fns import FNSIndex


def test_fns_import_and_lookup(tmp_path: Path):
    xml = (
        '<EGRUL ДатаВыг="2026-09-18">'
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА">'
        '<СвСтатус НаимСтатусЮЛ="Действующее"/></СвЮЛ></EGRUL>'
    )
    path = tmp_path / "fns.xml"
    path.write_text(xml, encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    assert index.import_snapshot(str(path)) == 1
    row = index.get("7 707 083 893")
    assert row is not None
    assert row.active


def test_liquidated_is_not_active(tmp_path: Path):
    xml = (
        '<EGRUL ДатаВыг="2026-09-18">'
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА">'
        '<СвСтатус НаимСтатусЮЛ="Ликвидировано"/></СвЮЛ></EGRUL>'
    )
    path = tmp_path / "fns.xml"
    path.write_text(xml, encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    index.import_snapshot(str(path))
    assert index.get("7707083893") is not None
    assert not index.get("7707083893").active


def test_latest_snapshot_replaces_old_status(tmp_path: Path):
    old_xml = (
        '<EGRUL ДатаВыг="2026-09-18">'
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА">'
        '<СвСтатус НаимСтатусЮЛ="Действующее"/></СвЮЛ></EGRUL>'
    )
    new_xml = (
        '<EGRUL ДатаВыг="2026-09-19">'
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА">'
        '<СвСтатус НаимСтатусЮЛ="Ликвидировано"/></СвЮЛ></EGRUL>'
    )
    old_path = tmp_path / "old.xml"
    new_path = tmp_path / "new.xml"
    old_path.write_text(old_xml, encoding="utf-8")
    new_path.write_text(new_xml, encoding="utf-8")
    index = FNSIndex(f"sqlite:///{tmp_path/'fns.sqlite3'}")
    index.import_snapshot(str(old_path))
    index.import_snapshot(str(new_path))
    assert not index.get("7707083893").active
