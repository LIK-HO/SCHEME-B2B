from __future__ import annotations

import json
import sys
from pathlib import Path

from .fns import FNSIndex
from .normalize import ogrn, ogrnip
from .validate import validate_requisites


def main() -> int:
    if len(sys.argv) < 2:
        print("import-fns PATH | check INN [OGRN|OGRNIП]")
        return 2

    command = sys.argv[1]

    if command == "import-fns" and len(sys.argv) == 3:
        count = FNSIndex().import_snapshot(sys.argv[2])
        print(f"Обработано записей: {count}")
        return 0

    if command == "check" and len(sys.argv) in (3, 4):
        raw_inn = sys.argv[2]
        second = sys.argv[3] if len(sys.argv) == 4 else ""
        raw_ogrn = ogrn(second)
        raw_ogrnip = ogrnip(second)
        ok, reason, i, o, p = validate_requisites(raw_inn, raw_ogrn, raw_ogrnip)
        if not ok:
            print(json.dumps({"ok": False, "reason": reason}, ensure_ascii=False))
            return 1

        record = FNSIndex().get(i)
        if record is None:
            print(json.dumps(
                {"ok": False, "reason": "ИНН не найден в индексе ФНС"},
                ensure_ascii=False,
            ))
            return 1

        matches = (record.ogrn == o and record.ogrnip == p)
        result = {
            "ok": matches and record.active,
            "status": "Действует" if record.active else "Не действует",
            "company": record.company,
            "inn": record.inn,
            "ogrn": record.ogrn,
            "ogrnip": record.ogrnip,
            "address": record.address,
            "source_date": record.source_date,
            "requisites_match": matches,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1

    print("Неверная команда или аргументы")
    return 2
