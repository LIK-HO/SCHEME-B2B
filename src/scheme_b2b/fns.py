from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .normalization import normalize_ogrn, normalize_ogrnip
from .registry import FNSBulkSource
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

    def validate_format(
        self,
        inn: str,
        ogrn: str = "",
        ogrnip: str = "",
    ) -> RequisitesValidation:
        return validate_requisites(inn, ogrn, ogrnip)

    def verify(self, inn: str, ogrn: str = "", ogrnip: str = "") -> FNSResult:
        local = self.validate_format(inn, ogrn, ogrnip)
        if not local.valid:
            return FNSResult("Не подтверждена", False, local.reason)

        mode = self.settings.fns_mode.lower()
        if mode == "bulk":
            return self._verify_bulk(local)

        if mode != "official":
            return FNSResult(
                "Формат подтверждён",
                False,
                "Реквизиты прошли контрольные суммы; официальный запрос ФНС не настроен.",
            )

        return self._verify_http(local)

    def _verify_bulk(self, local: RequisitesValidation) -> FNSResult:
        path = self.settings.fns_egrul_bulk_path
        if not path:
            return FNSResult("Ошибка", False, "FNS_EGRUL_BULK_PATH не задан")

        try:
            source = FNSBulkSource(path, only_moscow=False)
            for candidate in source.iter_candidates():
                if candidate.inn != local.inn:
                    continue
                if local.ogrn and candidate.ogrn != local.ogrn:
                    continue
                if local.ogrnip and candidate.ogrnip != local.ogrnip:
                    continue
                return FNSResult(
                    "Подтверждена",
                    True,
                    "Реквизиты найдены и совпали в официальной выгрузке ФНС.",
                    "https://www.nalog.gov.ru/rn77/service/egrip2/",
                )
        except Exception as exc:
            return FNSResult(
                "Ошибка",
                False,
                f"Ошибка чтения официальной выгрузки ФНС: {exc}",
            )

        return FNSResult(
            "Не подтверждена",
            False,
            "Совпадающая запись не найдена в указанной официальной выгрузке ФНС.",
            "https://www.nalog.gov.ru/rn77/service/egrip2/",
        )

    def _verify_http(self, local: RequisitesValidation) -> FNSResult:
        if not self.settings.fns_verify_url:
            return FNSResult("Ошибка", False, "FNS_VERIFY_URL не задан")

        headers: dict[str, str] = {}
        if self.settings.fns_verify_token:
            headers["Authorization"] = f"Bearer {self.settings.fns_verify_token}"

        params = {"inn": local.inn}
        if local.ogrn:
            params["ogrn"] = local.ogrn
        if local.ogrnip:
            params["ogrnip"] = local.ogrnip

        try:
            response = httpx.get(
                self.settings.fns_verify_url,
                params=params,
                headers=headers,
                timeout=self.settings.source_timeout_seconds,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return FNSResult("Ошибка", False, f"Ошибка официальной проверки ФНС: {exc}")

        found = bool(data.get("found"))
        same_inn = str(data.get("inn", "")) == local.inn
        same_ogrn = (
            not local.ogrn
            or normalize_ogrn(str(data.get("ogrn", ""))) == local.ogrn
        )
        same_ogrnip = (
            not local.ogrnip
            or normalize_ogrnip(str(data.get("ogrnip", ""))) == local.ogrnip
        )
        confirmed = found and same_inn and same_ogrn and same_ogrnip

        message = (
            "Официальный источник подтвердил комплект реквизитов."
            if confirmed
            else "Официальный источник не подтвердил комплект реквизитов."
        )
        return FNSResult(
            "Подтверждена" if confirmed else "Не подтверждена",
            confirmed,
            message,
            self.settings.fns_verify_url,
        )
