from scheme_b2b.scoring import priority
from scheme_b2b.sources import Candidate
from scheme_b2b.validation import validate_requisites


def test_high_priority_with_contacts():
    candidate = Candidate(
        company="ООО Ромашка",
        inn="7707083893",
        ogrn="1027700132195",
        sector="Логистика",
        phone="+7 999 111-22-33",
        email="sales@example.ru",
        website="https://example.ru",
        need="Грузчики",
    )
    validation = validate_requisites(candidate.inn, candidate.ogrn)
    level, score = priority(candidate, validation, True)
    assert level == "Высокий"
    assert score >= 75
