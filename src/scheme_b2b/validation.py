from dataclasses import dataclass

from .normalization import normalize_inn, normalize_ogrn, normalize_ogrnip


def _weighted_check_digit(value: str, weights: list[int]) -> str:
    total = sum(int(digit) * weight for digit, weight in zip(value, weights, strict=True))
    return str(total % 11 % 10)


def validate_inn(inn: str | None) -> bool:
    raw = normalize_inn(inn)
    if len(raw) == 10:
        return _weighted_check_digit(raw[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8]) == raw[-1]
    if len(raw) == 12:
        first = _weighted_check_digit(raw[:10], [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        second = _weighted_check_digit(raw[:11], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
        return first == raw[-2] and second == raw[-1]
    return False


def validate_ogrn(ogrn: str | None) -> bool:
    raw = normalize_ogrn(ogrn)
    if len(raw) != 13:
        return False
    control = int(raw[:-1]) % 11 % 10
    return control == int(raw[-1])


def validate_ogrnip(ogrnip: str | None) -> bool:
    raw = normalize_ogrnip(ogrnip)
    if len(raw) != 15:
        return False
    control = int(raw[:-1]) % 13 % 10
    return control == int(raw[-1])


@dataclass(frozen=True)
class RequisitesValidation:
    inn: str
    ogrn: str
    ogrnip: str
    inn_valid: bool
    ogrn_valid: bool
    ogrnip_valid: bool

    @property
    def valid(self) -> bool:
        has_legal_entity = len(self.inn) == 10 and bool(self.ogrn) and self.ogrn_valid and not self.ogrnip
        has_ip = len(self.inn) == 12 and bool(self.ogrnip) and self.ogrnip_valid and not self.ogrn
        return bool(self.inn) and self.inn_valid and (has_legal_entity or has_ip)

    @property
    def reason(self) -> str:
        if not self.inn:
            return "ИНН отсутствует или имеет неверную длину"
        if not self.inn_valid:
            return "ИНН не прошёл контрольную сумму"
        if not self.ogrn and not self.ogrnip:
            return "Не указан ОГРН или ОГРНИП"
        if self.ogrn and self.ogrnip:
            return "Одновременно указаны ОГРН и ОГРНИП"
        if len(self.inn) == 10 and self.ogrnip:
            return "Для 10-значного ИНН требуется ОГРН"
        if len(self.inn) == 12 and self.ogrn:
            return "Для 12-значного ИНН требуется ОГРНИП"
        if self.ogrn and not self.ogrn_valid:
            return "ОГРН не прошёл контрольную сумму"
        if self.ogrnip and not self.ogrnip_valid:
            return "ОГРНИП не прошёл контрольную сумму"
        return "OK"


def validate_requisites(
    inn: str | None,
    ogrn: str | None = None,
    ogrnip: str | None = None,
) -> RequisitesValidation:
    normalized_inn = normalize_inn(inn)
    normalized_ogrn = normalize_ogrn(ogrn)
    normalized_ogrnip = normalize_ogrnip(ogrnip)
    return RequisitesValidation(
        inn=normalized_inn,
        ogrn=normalized_ogrn,
        ogrnip=normalized_ogrnip,
        inn_valid=validate_inn(normalized_inn),
        ogrn_valid=validate_ogrn(normalized_ogrn) if normalized_ogrn else False,
        ogrnip_valid=validate_ogrnip(normalized_ogrnip) if normalized_ogrnip else False,
    )
