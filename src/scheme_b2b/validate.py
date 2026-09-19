from .normalize import inn, ogrn, ogrnip


def _check(value: str, weights: list[int]) -> str:
    return str(sum(int(d) * weight for d, weight in zip(value, weights, strict=True)) % 11 % 10)


def valid_inn(value: str | None) -> bool:
    raw = inn(value)
    if len(raw) == 10:
        return _check(raw[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8]) == raw[-1]
    if len(raw) == 12:
        first = _check(raw[:10], [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        second = _check(raw[:11], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        return first == raw[-2] and second == raw[-1]
    return False


def valid_ogrn(value: str | None) -> bool:
    raw = ogrn(value)
    return bool(raw) and int(raw[:-1]) % 11 % 10 == int(raw[-1])


def valid_ogrnip(value: str | None) -> bool:
    raw = ogrnip(value)
    return bool(raw) and int(raw[:-1]) % 13 % 10 == int(raw[-1])


def validate_requisites(
    raw_inn: str | None,
    raw_ogrn: str | None = None,
    raw_ogrnip: str | None = None,
) -> tuple[bool, str, str, str, str]:
    i, o, p = inn(raw_inn), ogrn(raw_ogrn), ogrnip(raw_ogrnip)
    if not valid_inn(i):
        return False, "ИНН не прошёл проверку", i, o, p
    if o and p:
        return False, "Одновременно указаны ОГРН и ОГРНИП", i, o, p
    if len(i) == 10 and (not o or not valid_ogrn(o)):
        return False, "Для 10-значного ИНН нужен корректный ОГРН", i, o, p
    if len(i) == 12 and (not p or not valid_ogrnip(p)):
        return False, "Для 12-значного ИНН нужен корректный ОГРНИП", i, o, p
    return True, "OK", i, o, p
