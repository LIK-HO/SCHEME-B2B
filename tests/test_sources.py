import csv
import json
from pathlib import Path

from scheme_b2b.opendata import OpenDataCsvSource
from scheme_b2b.sources import JsonFileSource


def test_json_source(tmp_path):
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            [{"company": "ООО Ромашка", "inn": "7707083893", "sector": "Логистика"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    candidates = JsonFileSource(str(path)).load()
    assert len(candidates) == 1
    assert candidates[0].company == "ООО Ромашка"
    assert candidates[0].sector == "Логистика"
    assert candidates[0].sector == "Логистика"


def test_open_data_csv_source_filters_moscow(tmp_path: Path):
    path = tmp_path / "registry.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Наименование организации", "ИНН", "ОГРН", "Регион", "ОКВЭД"])
        writer.writeheader()
        writer.writerow(
            {
                "Наименование организации": "ООО Ромашка",
                "ИНН": "7707083893",
                "ОГРН": "1027700132195",
                "Регион": "Москва",
                "ОКВЭД": "52.29",
            }
        )
        writer.writerow(
            {
                "Наименование организации": "ООО Не Москва",
                "ИНН": "5401000000",
                "ОГРН": "1025400000000",
                "Регион": "Новосибирская область",
            }
        )

    candidates = OpenDataCsvSource(str(path), "Росстат", only_moscow=True).load()
    assert len(candidates) == 1
    assert candidates[0].company == "ООО Ромашка"
