from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from scheme_b2b.fns import FNSVerifier
from scheme_b2b.registry import FNSBulkSource, candidate_from_registry_element


def test_registry_element_to_candidate():
    xml = ET.fromstring(
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77">'
        '<СвОКВЭД><СвОКВЭДОсн КодОКВЭД="52.29"/></СвОКВЭД>'
        "</СвЮЛ>"
    )
    candidate = candidate_from_registry_element(xml, "ФНС — ЕГРЮЛ/ЕГРИП")
    assert candidate is not None
    assert candidate.inn == "7707083893"
    assert candidate.ogrn == "1027700132195"
    assert candidate.city == "Москва"
    assert candidate.sector == "Логистика"


def test_rsmp_record_variant_is_accepted():
    xml = ET.fromstring('<Запись ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА" КодРегион="77"/>')
    candidate = candidate_from_registry_element(xml, "ФНС — Единый реестр МСП")
    assert candidate is not None
    assert candidate.inn == "7707083893"


def test_bulk_source_reads_xml(tmp_path: Path):
    path = tmp_path / "sample.xml"
    path.write_text(
        '<EGRUL ДатаВыг="2026-09-18"><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>',
        encoding="utf-8",
    )
    candidates = FNSBulkSource(str(path)).load()
    assert len(candidates) == 1
    assert candidates[0].inn == "7707083893"


def test_bulk_source_reads_generic_record_variant(tmp_path: Path):
    path = tmp_path / "sample.xml"
    path.write_text(
        '<ROOT><Запись ИНН="7707083893" ОГРН="1027700132195" НаимЮЛПолн="ООО РОМАШКА" КодРегион="77"/></ROOT>',
        encoding="utf-8",
    )
    candidates = FNSBulkSource(str(path)).load()
    assert len(candidates) == 1
    assert candidates[0].inn == "7707083893"


def test_bulk_fns_verifier_confirms_exact_match(tmp_path: Path):
    path = tmp_path / "sample.xml"
    path.write_text(
        '<EGRUL ДатаВыг="2026-09-18"><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
  "ПолнНаимОПФ=\"ООО РОМАШКА\" КодРегион=\"77\"/></EGRUL>',
        encoding="utf-8",
    )

    class Settings:
        fns_mode = "bulk"
        fns_egrul_bulk_path = str(path)
        fns_verify_url = ""
        fns_verify_token = ""
        source_timeout_seconds = 5

    result = FNSVerifier(Settings()).verify("7707083893", "1027700132195")
    assert result.confirmed
    assert result.status == "Подтверждена"


def test_bulk_source_reads_zip_stream(tmp_path: Path):
    path = tmp_path / "sample.zip"
    xml = (
        '<?xml version="1.0" encoding="windows-1251"?>'
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>'
    ).encode("cp1251")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("EGRUL_FULL_2026-01-01.xml", xml)

    candidates = FNSBulkSource(str(path)).load()
    assert len(candidates) == 1
    assert candidates[0].inn == "7707083893"


def test_bulk_fns_verifier_rejects_missing_snapshot_date(tmp_path: Path):
    path = tmp_path / "sample.xml"
    path.write_text(
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>',
        encoding="utf-8",
    )

    class Settings:
        fns_mode = "bulk"
        fns_egrul_bulk_path = str(path)
        fns_verify_url = ""
        fns_verify_token = ""
        source_timeout_seconds = 5
        fns_index_max_age_hours = 48

    result = FNSVerifier(Settings()).verify("7707083893", "1027700132195")
    assert not result.confirmed
    assert "ДатаВыг" in result.message
