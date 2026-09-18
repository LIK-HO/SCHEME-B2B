from .sources import Candidate
from .validation import RequisitesValidation


SECTOR_WEIGHT = {
    "Логистика": 28,
    "Склады": 27,
    "Производство": 27,
    "Строительство": 24,
    "Ритейл": 20,
    "Офисы": 17,
    "Мероприятия": 18,
    "Услуги B2B": 18,
    "Другое": 8,
}


def priority(candidate: Candidate, validation: RequisitesValidation, fns_confirmed: bool) -> tuple[str, int]:
    score = SECTOR_WEIGHT.get(candidate.sector, 8)
    score += 20 if validation.valid else 0
    score += 12 if candidate.phone else 0
    score += 8 if candidate.email else 0
    score += 7 if candidate.website else 0
    score += 5 if candidate.need else 0
    score += 10 if fns_confirmed else 0

    if score >= 75:
        return "Высокий", score
    if score >= 50:
        return "Средний", score
    return "Низкий", score
