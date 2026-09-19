from __future__ import annotations

import json
import sys
from pathlib import Path

from .db import CompanyDB
from .fns import FNSIndex
from .normalize import email, name, ogrn, ogrnip, phone, website
from .validate import validate_requisites


def main() -> int:
    if len(sys.argv) < 2:
        print("init-db | import-fns PATH | import-candidates PATH")
        return 2

    command = sys.argv[1]

    if command == "init-db":
        CompanyDB()
        FNSIndex()
        print("Готово")
        return 0

    if command == "import-fns" and len(sys.argv) == 3:
        count = FNSIndex().import_snapshot(sys.argv[2])
        print(f"Импортировано записей: {count}")
        return 0

    if command == "import-candidates" and len(sys.argv) == 3:
        payload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        items = payload.get("companies", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("Ожидается массив или companies[]")

        db, fns = CompanyDB(), FNSIndex()
        added = duplicates = rejected = 0

        for item in items:
            if not isinstance(item, dict):
                continue
            ok, _, i, o, p = validate_requisites(item.get("inn"), item.get("ogrn"), item.get("ogrnip"))
            if not ok:
                rejected += 1
                continue
            record = fns.get(i)
            if record is None or record.ogrn != o or record.ogrnip != p or not record.active:
                rejected += 1
                continue

            row = dict(item)
            row.update({
                "company": name(item.get("company")) or record.company,
                "inn": i,
                "ogrn": ogrn(o),
                "ogrnip": ogrnip(p),
                "status": "Новый",
                "sphere": name(item.get("sphere")),
                "need": name(item.get("need")),
                "need_evidence": name(item.get("need_evidence")),
                "need_source": name(item.get("need_source")),
                "phone": phone(item.get("phone")),
                "email": email(item.get("email")),
                "website": website(item.get("website")),
                "address": record.address,
                "source": name(item.get("source")),
                "fns_status": "Действует",
                "fns_checked_at": record.source_date,
            })
            if db.add(row):
                added += 1
            else:
                duplicates += 1

        print(f"Добавлено: {added}; дубликатов: {duplicates}; отклонено: {rejected}")
        return 0

    print("Неверная команда или аргументы")
    return 2
