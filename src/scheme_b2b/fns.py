from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .validation import RequisitesValidation, validate_requisites


@dataclass(frozen=True)
class FNSResult:
    status: str
    confirmed: bool
    message: str
    source_url: str = ""


class FNSVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings

    def validate_format(self, inn: str, ogrn: str = "", ogrnip: str = "") -> RequisitesValidation:
        return validate_requisites(inn, ogrn, ogrnip)

    def verify(self, inn: str, ogrn: str = "", ogrnip: str = "") -> FNSResult:
        local = self.validate_format(inn, ogrn, ogrnip)
        if not local.valid:
            return FNSResult("Не подтверждена", False, local.reason)

        if self.settings.fns_mode.lower() != "official":
            return FNSResult(
                "Формат подтверждён",
                False,
                "Реквизиты прошли контрольные суммы; официальный запрос ФНС не настроен.",
            )

        if not self.settings.fns_verify_url:
            return FNSResult("Ошибка", False, "FNS_VERIFY_URL не задан")

        headers = {}
        if self.settings.fns_verify_token:
            headers["Authorization"] = f"Bearer {self.settings.fns_verify_token}"

        params = {"inn": local.inn}
        if local.ogrn:
            params["ogrn"] = local.ogrn
        if local.ogrnip:
            params["ogrnip"] = local.ogrnip

        response = httpx.get(
            self.settings.fns_verify_url,
            params=params,
            headers=headers,
            timeout=self.settings.source_timeout_seconds,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()

        found = bool(data.get("found"))
        same_inn = str(data.get("inn", "")) == local.inn
        same_ogrn = not local.ogrn or str(data.get("ogrn", "")) == local.ogrn
        same_ogrnip = not local.ogrnip or str(data.get("ogrnip", "")) == local.ogrnip
        confirmed = found and same_inn and same_ogrn and same_ogrnip

        message = (
            "ЕГРЮЛ/ЕГРИП подтвердил реквизиты."
            if confirmed
            else "Официальный источник не подтвердил комплект реквизитов."
        )
        return FNSResult(
            "Подтверждена" if confirmed else "Не подтверждена",
            confirmed,
            message,
            self.settings.fns_verify_url,
        )
