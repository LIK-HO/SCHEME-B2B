from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .normalization import normalize_ogrn, normalize_ogrnip
from .registry import FNSBulkSource
from .time_utils import MSK, ensure_aware, now_utc
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

    def readiness_error(self) -> str | None:
        """Return a blocking configuration/data-freshness error for /ready."""
        if not self.settings.require_fns_confirmation:
            return None

        mode = self.settings.fns_mode.lower()
        if mode == "checksum":
            return "FNS_OFFICIAL_VERIFICATION"
        if mode == "official":
            if not self.settings.fns_verify_url:
                return "FNS_VERIFY_URL"
            if not self.settings.fns_verify_url.lower().startswith("https://"):
                return "FNS_VERIFY_URL_MUST_USE_HTTPS"
            return None
        if mode == "bulk":
            if not self.settings.fns_egrul_bulk_path:
                return "FNS_EGRUL_BULK_PATH"
            path = Path(self.settings.fns_egrul_bulk_path)
            if not path.is_file():
                return "FNS_EGRUL_BULK_PATH_NOT_FOUND"
            try:
                source_date = self._snapshot_date_for_readiness(path)
            except Exception:
                return "FNS_SNAPSHOT_UNREADABLE"
            if source_date is None:
                return "FNS_SNAPSHOT_DATE"
            current = ensure_aware(now_utc(), tz=MSK)
            age = current - ensure_aware(source_date, tz=MSK)
            if age < timedelta(0) or age > timedelta(hours=self.settings.fns_index_max_age_hours):
                return "FNS_SNAPSHOT_FRESHNESS"
            return None
        if mode == "bulk-index":
            try:
                from .fns_index import FNSIndex

                if not FNSIndex(self.settings.fns_index_db_url).is_fresh(self.settings.fns_index_max_age_hours):
                    return "FNS_INDEX_FRESHNESS"
            except Exception:
                return "FNS_INDEX"
            return None
        return "FNS_MODE"

    @staticmethod
    def _snapshot_date_for_readiness(path: Path):
        from .fns_index import _snapshot_date

        return _snapshot_date(path)

    def verify(self, inn: str, ogrn: str = "", ogrnip: str = "") -> FNSResult:
        local = self.validate_format(inn, ogrn, ogrnip)
        if not local.valid:
            return FNSResult("Не подтверждена", False, local.reason)

        mode = self.settings.fns_mode.lower()
        if mode == "bulk-index":
            return self._verify_index(local)

        if mode == "bulk":
            return self._verify_bulk(local)

        if mode != "official":
            return FNSResult(
                "Не выполнялась",
                False,
                "Реквизиты прошли контрольные суммы; актуальная проверка ФНС не настроена.",
            )

        return self._verify_http(local)

    def _verify_index(self, local: RequisitesValidation) -> FNSResult:
        try:
            from .fns_index import FNSIndex

            index = FNSIndex(self.settings.fns_index_db_url)
            if not index.is_fresh(self.settings.fns_index_max_age_hours, now_utc()):
                return FNSResult(
                    "Не подтверждена",
                    False,
                    "Индекс ФНС отсутствует или устарел; актуальный snapshot не подтверждён.",
                    "https://www.nalog.gov.ru/rn77/service/egrip2/",
                )
            row = index.get(local.inn, local.ogrn, local.ogrnip)
        except Exception as exc:
            return FNSResult("Ошибка", False, f"Ошибка доступа к индексу ФНС: {exc}")

        if row is None:
            return FNSResult(
                "Не подтверждена",
                False,
                "Совпадающая запись с теми же ИНН и ОГРН/ОГРНИП не найдена в индексе ФНС.",
                "https://www.nalog.gov.ru/rn77/service/egrip2/",
            )

        confirmed = True

        return FNSResult(
            "Подтверждена" if confirmed else "Не подтверждена",
            confirmed,
            "Реквизиты совпали в индексе официальной выгрузки ФНС."
            if confirmed
            else "ИНН найден, но ОГРН/ОГРНИП не совпал.",
            "https://www.nalog.gov.ru/rn77/service/egrip2/",
        )

    def _verify_bulk(self, local: RequisitesValidation) -> FNSResult:
        path = self.settings.fns_egrul_bulk_path
        if not path:
            return FNSResult("Ошибка", False, "FNS_EGRUL_BULK_PATH не задан")

        try:
            from .fns_index import _snapshot_date

            source_date = _snapshot_date(Path(path))
            if source_date is None:
                return FNSResult(
                    "Не подтверждена",
                    False,
                    "Выгрузка ФНС не содержит корректной даты ДатаВыг.",
                    "https://www.nalog.gov.ru/rn77/service/egrip2/",
                )
            age = ensure_aware(now_utc(), tz=MSK) - ensure_aware(source_date, tz=MSK)
            if age < timedelta(0) or age > timedelta(hours=self.settings.fns_index_max_age_hours):
                return FNSResult(
                    "Не подтверждена",
                    False,
                    "Указанная выгрузка ФНС устарела; актуальный snapshot не подтверждён.",
                    "https://www.nalog.gov.ru/rn77/service/egrip2/",
                )

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
        same_ogrn = not local.ogrn or normalize_ogrn(str(data.get("ogrn", ""))) == local.ogrn
        same_ogrnip = not local.ogrnip or normalize_ogrnip(str(data.get("ogrnip", ""))) == local.ogrnip
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
