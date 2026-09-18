from pathlib import Path

from scheme_b2b.registry import FNSBulkSource, candidate_from_registry_element
import xml.etree.ElementTree as ET


def test_registry_element_to_candidate():
    xml = ET.fromstring(
        '<СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77">'
        '<СвОКВЭД><СвОКВЭДОсн КодОКВЭД="52.29"/></СвОКВЭД>'
        '</СвЮЛ>'
    )
    candidate = candidate_from_registry_element(xml, "ФНС — ЕГРЮЛ/ЕГРИП")
    assert candidate is not None
    assert candidate.inn == "7707083893"
    assert candidate.ogrn == "1027700132195"
    assert candidate.city == "Москва"
    assert candidate.sector == "Логистика"


def test_bulk_source_reads_xml(tmp_path: Path):
    path = tmp_path / "sample.xml"
    path.write_text(
        '<EGRUL><СвЮЛ ИНН="7707083893" ОГРН="1027700132195" '
        'ПолнНаимОПФ="ООО РОМАШКА" КодРегион="77"/></EGRUL>',
        encoding="utf-8",
    )
    candidates = FNSBulkSource(str(path)).load()
    assert len(candidates) == 1
    assert candidates[0].inn == "7707083893"
