from pathlib import Path

from scheme_b2b.db import CompanyDB


def test_company_db_blocks_duplicate_inn(tmp_path: Path):
    db = CompanyDB(f"sqlite:///{tmp_path/'db.sqlite3'}")
    row = {
        "inn":"7707083893","company":"ООО РОМАШКА","ogrn":"1027700132195","ogrnip":"",
        "status":"Новый","sphere":"Логистика","need":"","need_evidence":"","need_source":"",
        "phone":"","email":"","website":"","address":"","source":"test",
        "fns_status":"Действует","fns_checked_at":"2026-09-18"
    }
    assert db.add(row)
    assert not db.add(row)
