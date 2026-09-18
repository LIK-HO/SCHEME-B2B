from __future__ import annotations


def classify_okved(code: str) -> str:
    """Map OKVED to an initial business-routing sector.

    This is a routing heuristic, not proof of actual activity.
    """
    normalized = (code or "").strip().replace(" ", "")
    families = (
        ("Склады", ("52.10", "52.21", "52.22", "52.23", "52.24")),
        ("Логистика", ("49.", "50.", "51.", "52.1", "52.2", "52.29")),
        ("Производство", tuple(f"{n:02d}." for n in range(10, 34))),
        ("Строительство", ("41.", "42.", "43.")),
        ("Ритейл", ("45.", "46.", "47.")),
        ("Мероприятия", ("90.", "93.2")),
        ("Офисы", ("68.", "69.", "70.", "71.", "73.", "74.")),
    )
    for sector, prefixes in families:
        if normalized.startswith(prefixes):
            return sector
    return "Услуги B2B"


def is_moscow_label(value: str | None) -> bool:
    """Recognize common Moscow labels and subject code 77."""
    text = " ".join((value or "").strip().lower().split())
    if not text:
        return False
    if text in {"77", "г. москва", "город москва", "москва", "москва г"}:
        return True
    return "москв" in text and "област" not in text
