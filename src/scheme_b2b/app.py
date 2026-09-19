from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .db import CompanyDB
from .fns import FNSIndex
from .normalize import email, inn, name, ogrn, ogrnip, phone, website
from .validate import validate_requisites


ROOT = Path(__file__).resolve().parents[2]
DB = CompanyDB()
FNS = FNSIndex()
app = FastAPI(title="SCHEME-B2B", version="0.1.0")


class Candidate(BaseModel):
    company: str = ""
    inn: str
    ogrn: str = ""
    ogrnip: str = ""
    sphere: str = ""
    need: str = ""
    need_evidence: str = ""
    need_source: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    source: str = ""


class StatusChange(BaseModel):
    status: str


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/companies")
def companies(status: str | None = Query(default=None), q: str = ""):
    return DB.list(status=status, q=q)


@app.post("/api/companies")
def add_company(candidate: Candidate):
    ok, reason, i, o, p = validate_requisites(candidate.inn, candidate.ogrn, candidate.ogrnip)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    fns = FNS.get(i)
    if fns is None:
        raise HTTPException(status_code=409, detail="Компания не найдена в локальном индексе ФНС")
    if fns.ogrn != o or fns.ogrnip != p:
        raise HTTPException(status_code=409, detail="ИНН и ОГРН/ОГРНИП не совпали с ФНС")
    if not fns.active:
        raise HTTPException(status_code=409, detail="Компания не действует по ФНС")

    row = candidate.model_dump()
    row.update({
        "company": name(row["company"]) or fns.company,
        "inn": i,
        "ogrn": o,
        "ogrnip": p,
        "phone": phone(row["phone"]),
        "email": email(row["email"]),
        "website": website(row["website"]),
        "need": name(row["need"]),
        "need_evidence": name(row["need_evidence"]),
        "need_source": name(row["need_source"]),
        "source": name(row["source"]),
        "status": "Новый",
        "address": fns.address,
        "fns_status": "Действует",
        "fns_checked_at": fns.source_date,
    })
    if not DB.add(row):
        raise HTTPException(status_code=409, detail="Дубликат ИНН")
    return {"ok": True, "inn": i}


@app.patch("/api/companies/{inn_value}/status")
def change_status(inn_value: str, body: StatusChange):
    i = inn(inn_value)
    if not DB.update_status(i, body.status):
        raise HTTPException(status_code=404, detail="Компания не найдена")
    return {"ok": True}


@app.get("/api/sources")
def sources():
    return SOURCE_ROWS


@app.get("/api/sectors")
def sectors():
    return SECTOR_ROWS


SOURCE_ROWS = [
    {"source":"ФНС — ЕГРЮЛ/ЕГРИП","type":"Государственный","purpose":"Идентификация","class":"Основной","site":"https://www.nalog.gov.ru/rn77/service/egrip2/"},
    {"source":"ФНС — Прозрачный бизнес","type":"Государственный","purpose":"Идентификация","class":"Основной","site":"https://pb.nalog.ru/"},
    {"source":"ФНС — Реестр МСП","type":"Государственный","purpose":"Поиск","class":"Дополнительный","site":"https://rmsp.nalog.ru/"},
    {"source":"Росстат — Статистический регистр","type":"Государственный","purpose":"Поиск","class":"Дополнительный","site":"https://rosstat.gov.ru/opendata/7708234640-urid"},
    {"source":"ЕИС Закупки","type":"Государственный","purpose":"Потребность","class":"Сигнал","site":"https://zakupki.gov.ru/"},
    {"source":"Федресурс","type":"Государственный","purpose":"Потребность","class":"Сигнал","site":"https://fedresurs.ru/"},
    {"source":"ГИСП — промышленность","type":"Государственный","purpose":"Поиск","class":"Дополнительный","site":"https://gisp.gov.ru/"},
    {"source":"Роспатент — открытые реестры","type":"Государственный","purpose":"Потребность","class":"Сигнал","site":"https://rospatent.gov.ru/opendata"},
    {"source":"НОСТРОЙ — реестр СРО","type":"Отраслевой","purpose":"Поиск","class":"Дополнительный","site":"https://reestr.nostroy.ru/member"},
    {"source":"НОПРИЗ — реестр СРО","type":"Отраслевой","purpose":"Поиск","class":"Дополнительный","site":"https://reestr.nopriz.ru/sro/list"},
]


SECTOR_ROWS = [
    {"no":1,"sphere":"Склады и складская логистика","relevance":"A — высокая","tasks":"погрузка, разгрузка, складские работы, перемещение","signals":"склад, РЦ, 3PL, фулфилмент"},
    {"no":2,"sphere":"Логистика и грузоперевозки","relevance":"A — высокая","tasks":"перегрузка, терминалы, сезонные пики","signals":"логистический центр, транспорт, терминал"},
    {"no":3,"sphere":"Производство","relevance":"A — высокая","tasks":"такелаж, перемещение и монтаж оборудования","signals":"завод, цех, станки, оборудование"},
    {"no":4,"sphere":"Строительство и генподряд","relevance":"A — высокая","tasks":"разгрузка материалов, такелаж, разнорабочие","signals":"стройка, генподряд, монтаж"},
    {"no":5,"sphere":"Ритейл и распределительные сети","relevance":"A — высокая","tasks":"товар, открытие и перестройка объектов","signals":"сеть магазинов, открытие точки, РЦ"},
    {"no":6,"sphere":"Офисы и коммерческая недвижимость","relevance":"B — средняя","tasks":"переезды, перестановка, монтаж","signals":"новый офис, переезд, бизнес-центр"},
    {"no":7,"sphere":"Промышленное оборудование","relevance":"B — средняя","tasks":"перемещение, монтаж и демонтаж тяжёлых объектов","signals":"станки, оборудование, монтаж"},
    {"no":8,"sphere":"Мероприятия и выставки","relevance":"B — средняя","tasks":"монтаж, демонтаж, перенос экспозиции","signals":"выставка, форум, конференция"},
    {"no":9,"sphere":"Дата-центры и телеком","relevance":"B — средняя","tasks":"перемещение оборудования, вспомогательный монтаж","signals":"ЦОД, серверы, модернизация"},
    {"no":10,"sphere":"Медицина и лаборатории","relevance":"B — средняя","tasks":"перемещение оборудования, переезды","signals":"клиника, лаборатория, оборудование"},
    {"no":11,"sphere":"Автосервисы и дилеры","relevance":"B — средняя","tasks":"перемещение техники и оборудования","signals":"СТО, дилер, сервисный центр"},
    {"no":12,"sphere":"Оптовая торговля","relevance":"B — средняя","tasks":"склад, погрузка, переезды","signals":"оптовый склад, дистрибьютор"},
    {"no":13,"sphere":"Пищевая промышленность","relevance":"B — средняя","tasks":"складские и производственные перемещения","signals":"пищевое производство, склад"},
    {"no":14,"sphere":"Полиграфия и упаковка","relevance":"C — дополнительная","tasks":"оборудование, материалы, склад","signals":"типография, упаковка, производство"},
    {"no":15,"sphere":"Мебель и деревообработка","relevance":"C — дополнительная","tasks":"оборудование, материалы, готовая продукция","signals":"мебель, деревообработка, цех"},
    {"no":16,"sphere":"Химическая промышленность","relevance":"C — дополнительная","tasks":"оборудование и складские операции с требованиями площадки","signals":"химическое производство, лаборатория"},
]
