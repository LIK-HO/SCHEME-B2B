from __future__ import annotations

from pathlib import Path
import sqlite3


class CompanyDB:
    STATUSES = {"Новый", "Клиент", "Архив"}

    def __init__(self, path: str = "data/scheme_b2b.sqlite3"):
        self.path = path.removeprefix("sqlite:///")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS company("
                "inn TEXT PRIMARY KEY, company TEXT NOT NULL, ogrn TEXT NOT NULL DEFAULT '', "
                "ogrnip TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, sphere TEXT NOT NULL DEFAULT '', "
                "need TEXT NOT NULL DEFAULT '', need_evidence TEXT NOT NULL DEFAULT '', "
                "need_source TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', "
                "website TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', "
                "fns_status TEXT NOT NULL, fns_checked_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_company_status ON company(status)")
            db.commit()

    def _connect(self):
        return sqlite3.connect(self.path)

    def add(self, row: dict) -> bool:
        with self._connect() as db:
            try:
                db.execute(
                    "INSERT INTO company("
                    "inn,company,ogrn,ogrnip,status,sphere,need,need_evidence,need_source,phone,email,website,address,source,"
                    "fns_status,fns_checked_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    tuple(row[k] for k in (
                        "inn","company","ogrn","ogrnip","status","sphere","need","need_evidence","need_source",
                        "phone","email","website","address","source","fns_status","fns_checked_at"
                    )),
                )
            except sqlite3.IntegrityError:
                return False
            db.commit()
        return True

    def update_status(self, inn_value: str, status: str) -> bool:
        if status not in self.STATUSES:
            raise ValueError("Недопустимый статус")
        with self._connect() as db:
            cur = db.execute(
                "UPDATE company SET status=?,updated_at=CURRENT_TIMESTAMP WHERE inn=?",
                (status, inn_value),
            )
            db.commit()
            return cur.rowcount == 1

    def list(self, status: str | None = None, q: str = "") -> list[dict]:
        sql = (
            "SELECT inn,company,ogrn,ogrnip,status,sphere,need,need_evidence,need_source,phone,email,website,"
            "address,source,fns_status,fns_checked_at FROM company"
        )
        args: list[str] = []
        where: list[str] = []
        if status:
            where.append("status=?")
            args.append(status)
        if q:
            where.append("(company LIKE ? OR inn LIKE ? OR sphere LIKE ? OR need LIKE ?)")
            like = f"%{q}%"
            args.extend([like, like, like, like])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY company COLLATE NOCASE LIMIT 500"
        with self._connect() as db:
            rows = db.execute(sql, args).fetchall()
        keys = [
            "inn","company","ogrn","ogrnip","status","sphere","need","need_evidence","need_source",
            "phone","email","website","address","source","fns_status","fns_checked_at"
        ]
        return [dict(zip(keys, row, strict=True)) for row in rows]
