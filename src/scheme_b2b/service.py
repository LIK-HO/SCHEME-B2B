from __future__ import annotations

from datetime import datetime
import json
import logging
import uuid

from .airtable import AirtableClient
from .config import Settings
from .db import create_session_factory
from .dedup import GlobalDeduplicator
from .fns import FNSVerifier
from .models import RunLog
from .outbox import CHANNEL_EMAIL, CHANNEL_MAX, OutboxDispatcher
from .schedule import MSK, already_ran_this_slot, next_run, should_run_now
from .scoring import priority
from .sources import CandidateSource, build_sources
from .validation import validate_requisites


logger = logging.getLogger(__name__)


class SearchService:
    def __init__(
        self,
        settings: Settings,
        airtable: AirtableClient,
        sources: list[CandidateSource] | None = None,
    ):
        self.settings = settings
        self.airtable = airtable
        self.sources = sources if sources is not None else build_sources(settings)
        self.fns = FNSVerifier(settings)
        self.dedup = GlobalDeduplicator(
            airtable,
            settings.airtable_table_companies,
            settings.airtable_table_clients,
            settings.airtable_table_archive,
        )
        self.outbox = OutboxDispatcher(airtable, settings)
        self.session_factory = create_session_factory(settings)

    def run_once(self, manual: bool = False) -> dict[str, object]:
        profile = self.airtable.get_search_profile(self.settings)
        if not manual and not profile:
            raise RuntimeError(f"Профиль поиска '{self.settings.search_profile_name}' не найден")

        if not manual and not self._profile_allows_run(profile):
            return {"status": "skipped", "reason": "outside_schedule_or_disabled"}

        run_id = f"run-{datetime.now(MSK).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        log = RunLog(run_id=run_id, status="started", started_at=datetime.utcnow())

        with self.session_factory() as session:
            session.add(log)
            session.commit()

        try:
            candidates: list = []
            source_errors: list[str] = []
            for source in self.sources:
                try:
                    candidates.extend(source.load())
                except Exception as exc:
                    source_errors.append(f"{source.name}: {exc}")

            counters = {
                "candidates": len(candidates),
                "inserted": 0,
                "duplicates": 0,
                "rejected": 0,
                "errors": len(source_errors),
            }
            duplicate_locations: dict[str, list[str]] = {}
            rejected_reasons: dict[str, int] = {}
            seen_batch: set[str] = set()

            for candidate in candidates:
                try:
                    validation = validate_requisites(candidate.inn, candidate.ogrn, candidate.ogrnip)
                    inn = validation.inn
                    if not inn:
                        counters["rejected"] += 1
                        rejected_reasons[validation.reason] = rejected_reasons.get(validation.reason, 0) + 1
                        continue

                    if not validation.valid:
                        counters["rejected"] += 1
                        rejected_reasons[validation.reason] = rejected_reasons.get(validation.reason, 0) + 1
                        continue

                    if inn in seen_batch:
                        counters["duplicates"] += 1
                        duplicate_locations.setdefault(inn, []).append("текущий запуск")
                        continue
                    seen_batch.add(inn)

                    dedup = self.dedup.check(inn)
                    if dedup.duplicate:
                        counters["duplicates"] += 1
                        duplicate_locations[inn] = list(dedup.locations)
                        continue

                    fns = self.fns.verify(inn, validation.ogrn, validation.ogrnip)
                    if self.settings.require_fns_confirmation and not fns.confirmed:
                        counters["rejected"] += 1
                        rejected_reasons[fns.message] = rejected_reasons.get(fns.message, 0) + 1
                        continue

                    level, score = priority(candidate, validation, fns.confirmed)
                    comment_parts = [
                        candidate.comment,
                        f"Автооценка: {score}/100",
                        f"ФНС: {fns.status}",
                    ]
                    self.airtable.create_record(
                        self.settings.airtable_table_companies,
                        {
                            "Компания": candidate.company,
                            "ИНН": inn,
                            "ОГРН": validation.ogrn,
                            "ОГРНИП": validation.ogrnip,
                            "Город": candidate.city,
                            "Сфера": candidate.sector,
                            "Потребность": candidate.need,
                            "Телефон": candidate.phone,
                            "Почта": candidate.email,
                            "Сайт": candidate.website,
                            "Ответственный": candidate.responsible,
                            "Статус": "Ожидает",
                            "Источник": candidate.source,
                            "Приоритет": level,
                            "Дата обнаружения": datetime.now(MSK).date().isoformat(),
                            "Дата проверки": datetime.now(MSK).date().isoformat(),
                            "Комментарий": "; ".join(x for x in comment_parts if x),
                            "Проверка ФНС": fns.status,
                            "Дата проверки ФНС": datetime.now(MSK).date().isoformat(),
                            "Источник проверки ФНС": fns.source_url,
                            "Результат проверки ФНС": fns.message,
                        },
                    )
                    counters["inserted"] += 1

                except Exception:
                    counters["errors"] += 1
                    logger.exception("Ошибка обработки кандидата %s", candidate.company)

            summary = self._summary_text(
                run_id, counters, duplicate_locations, rejected_reasons, source_errors
            )
            self._update_run_log(run_id, "success", counters, summary)

            if profile:
                self._mark_profile_run(profile, counters)

            profile_name = str(profile.get("fields", {}).get("Профиль поиска") or self.settings.search_profile_name) if profile else self.settings.search_profile_name
            if self.settings.max_enabled and self.settings.max_recipient_id:
                self.outbox.enqueue(f"{run_id}:summary", CHANNEL_MAX, profile_name, summary)
            if self.settings.email_enabled and self.settings.email_to:
                self.outbox.enqueue(f"{run_id}:summary", CHANNEL_EMAIL, profile_name, summary)

            return {"status": "success", "run_id": run_id, **counters, "summary": summary}

        except Exception as exc:
            summary = f"Запуск {run_id} завершён с ошибкой: {exc}"
            self._update_run_log(run_id, "error", {"errors": 1}, summary)
            raise

    def dispatch_outbox(self) -> dict[str, int]:
        return self.outbox.dispatch()

    def _profile_allows_run(self, profile: dict) -> bool:
        fields = profile.get("fields", {})
        if not bool(fields.get("Активен")) or not bool(fields.get("Автопоиск")):
            return False

        frequency = str(fields.get("Частота поиска") or "1 раз в день")
        now = datetime.now(MSK)
        if not should_run_now(frequency, now):
            return False

        last_run = fields.get("Последний запуск")
        return not already_ran_this_slot(str(last_run) if last_run else None, now)

    def _mark_profile_run(self, profile: dict, counters: dict[str, int]) -> None:
        now = datetime.now(MSK)
        upcoming = next_run(str(profile.get("fields", {}).get("Частота поиска") or "1 раз в день"), now)
        self.airtable.update_record(
            self.settings.airtable_table_search,
            profile["id"],
            {
                "Последний запуск": now.isoformat(timespec="seconds"),
                "Следующий запуск": upcoming.isoformat(timespec="seconds"),
            },
        )

    def _update_run_log(self, run_id: str, status: str, counters: dict[str, int], details: str) -> None:
        with self.session_factory() as session:
            log = session.query(RunLog).filter_by(run_id=run_id).one()
            log.status = status
            log.finished_at = datetime.utcnow()
            for key in ("candidates", "inserted", "duplicates", "rejected", "errors"):
                if key in counters:
                    setattr(log, key, counters[key])
            log.details = details[:10000]
            session.commit()

    @staticmethod
    def _summary_text(
        run_id: str,
        counters: dict[str, int],
        duplicate_locations: dict[str, list[str]],
        rejected_reasons: dict[str, int],
        source_errors: list[str],
    ) -> str:
        lines = [
            f"Запуск: {run_id}",
            f"Кандидатов: {counters.get('candidates', 0)}",
            f"Новых компаний: {counters.get('inserted', 0)}",
            f"Дубликатов: {counters.get('duplicates', 0)}",
            f"Отклонено: {counters.get('rejected', 0)}",
            f"Ошибок: {counters.get('errors', 0)}",
        ]
        if duplicate_locations:
            lines.append("Дедуп:")
            for inn, locations in list(duplicate_locations.items())[:20]:
                lines.append(f"- {inn}: {', '.join(locations)}")
        if rejected_reasons:
            lines.append("Причины отклонения:")
            for reason, count in list(rejected_reasons.items())[:20]:
                lines.append(f"- {count} × {reason}")
        if source_errors:
            lines.append("Ошибки источников:")
            lines.extend(f"- {x}" for x in source_errors[:20])
        return "\n".join(lines)
