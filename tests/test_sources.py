import json

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
