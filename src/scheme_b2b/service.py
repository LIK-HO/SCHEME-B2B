from __future__ import annotations

import logging
import uuid

from .airtable import AirtableClient
from .config import Settings
from .db import create_session_factory
from .dedup import GlobalDeduplicator
from .fns import FNSVerifier
from .models import RunLog
from .outbox import CHANNEL_EMAIL, CHANNEL_MAX, OutboxDispatcher
from .schedule import already_ran_this_slot, next_run, should_run_now
from .scoring import priority
from .sources import Candidate, CandidateSource, build_sources
from .time_utils import now_msk, now_utc
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

        run_id = f"run-{now_msk().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        log = RunLog(run_id=run_id, status="started", started_at=now_utc())
        with self.session_factory() as session:
            session.add(log)
            session.commit()

        try:
            counters = {
                "candidates": 0,
                "inserted": 0,
                "duplicates": 0,
                "rejected": 0,
                "errors": 0,
            }
            source_errors: list[str] = []
            rejected_reasons: dict[str, int] = {}
            duplicate_locations: dict[str, list[str]] = {}
            seen_batch: set[str] = set()
            source_limits_hit: list[str] = []
            new_limit_hit = False

            if not self.sources:
                source_errors.append("Источники поиска не настроены")
                counters["errors"] = 1
                summary = self._summary_text(
                    run_id,
                    counters,
                    duplicate_locations,
                    rejected_reasons,
                    source_errors,
                    source_limits_hit,
                    new_limit_hit,
                )
                self._update_run_log(run_id, "error", counters, summary)
                self._enqueue_summary(profile, run_id, summary)
                return {"status": "error", "run_id": run_id, **counters, "summary": summary}

            try:
                self.dedup.prime()
            except Exception as exc:
                source_errors.append(f"Дедупликация Airtable: {exc}")
                counters["errors"] = 1
                summary = self._summary_text(
                    run_id,
                    counters,
                    duplicate_locations,
                    rejected_reasons,
                    source_errors,
                    source_limits_hit,
                    new_limit_hit,
                )
                self._update_run_log(run_id, "error", counters, summary)
                self._enqueue_summary(profile, run_id, summary)
                return {"status": "error", "run_id": run_id, **counters, "summary": summary}

            stop_after_new = False
            for source in self.sources:
                source_seen = 0
                try:
                    for candidate in source.iter_candidates():
                        if source_seen >= self.settings.max_candidates_per_source:
                            source_limits_hit.append(source.name)
                            break
                        source_seen += 1
                        counters["candidates"] += 1

                        self._process_candidate(
                            candidate,
                            seen_batch,
                            counters,
                            duplicate_locations,
                            rejected_reasons,
                        )

                        if counters["inserted"] >= self.settings.max_new_records_per_run:
                            new_limit_hit = True
                            stop_after_new = True
                            break
                except Exception as exc:
                    source_errors.append(f"{source.name}: {exc}")
                    counters["errors"] += 1

                if stop_after_new:
                    break

            summary = self._summary_text(
                run_id,
                counters,
                duplicate_locations,
                rejected_reasons,
                source_errors,
                source_limits_hit,
                new_limit_hit,
            )
            run_status = "partial" if source_errors or source_limits_hit or new_limit_hit or counters["errors"] else "success"
            self._update_run_log(run_id, run_status, counters, summary)

            if profile:
                self._mark_profile_run(profile)
            self._enqueue_summary(profile, run_id, summary)

            return {"status": run_status, "run_id": run_id, **counters, "summary": summary}

        except Exception as exc:
            summary = f"Запуск {run_id} завершён с ошибкой: {exc}"
            self._update_run_log(run_id, "error", {"errors": 1}, summary)
            logger.exception("Search run failed: %s", run_id)
            raise

    def _process_candidate(
        self,
        candidate: Candidate,
        seen_batch: set[str],
        counters: dict[str, int],
        duplicate_locations: dict[str, list[str]],
        rejected_reasons: dict[str, int],
    ) -> None:
        try:
            if not candidate.company:
                counters["rejected"] += 1
                rejected_reasons["Название компании отсутствует"] = (
                    rejected_reasons.get("Название компании отсутствует", 0) + 1
                )
                return

            validation = validate_requisites(candidate.inn, candidate.ogrn, candidate.ogrnip)
            inn = validation.inn
            if not validation.valid:
                counters["rejected"] += 1
                rejected_reasons[validation.reason] = rejected_reasons.get(validation.reason, 0) + 1
                return

            if inn in seen_batch:
                counters["duplicates"] += 1
                duplicate_locations.setdefault(inn, []).append("текущий запуск")
                return

            dedup = self.dedup.check(inn)
            if dedup.duplicate:
                counters["duplicates"] += 1
                duplicate_locations[inn] = list(dedup.locations)
                return

            fns = self.fns.verify(inn, validation.ogrn, validation.ogrnip)
            if self.settings.require_fns_confirmation and not fns.confirmed:
                if fns.status == "Ошибка":
                    counters["errors"] += 1
                    rejected_reasons[f"Проверка ФНС: {fns.message}"] = (
                        rejected_reasons.get(f"Проверка ФНС: {fns.message}", 0) + 1
                    )
                    return
                counters["rejected"] += 1
                rejected_reasons[fns.message] = rejected_reasons.get(fns.message, 0) + 1
                seen_batch.add(inn)
                return

            seen_batch.add(inn)
            level, score = priority(candidate, validation, fns.confirmed)
            comment_parts = [
                candidate.comment,
                f"Автооценка: {score}/100",
                f"ФНС: {fns.status}",
            ]

            company_fields = {
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
                "Дата обнаружения": now_msk().date().isoformat(),
                "Дата проверки": now_msk().date().isoformat(),
                "Комментарий": "; ".join(x for x in comment_parts if x),
                "Проверка ФНС": fns.status,
                "Дата проверки ФНС": now_msk().date().isoformat(),
                "Источник проверки ФНС": fns.source_url,
                "Результат проверки ФНС": fns.message,
            }
            try:
                self.airtable.create_record(
                    self.settings.airtable_table_companies,
                    company_fields,
                )
            except Exception as exc:
                try:
                    if not self.airtable.exists_by_inn(
                        self.settings.airtable_table_companies,
                        inn,
                    ):
                        raise exc
                    logger.warning(
                        "Airtable create outcome ambiguous; record already exists for INN %s",
                        inn,
                    )
                except Exception:
                    raise

            counters["inserted"] += 1

        except Exception:
            counters["errors"] += 1
            logger.exception("Ошибка обработки кандидата %s", candidate.company)

    def dispatch_outbox(self) -> dict[str, int]:
        return self.outbox.dispatch()

    def _notification_channels(self, profile: dict | None) -> list[tuple[str, str]]:
        fields = profile.get("fields", {}) if profile else {}
        channels: list[tuple[str, str]] = []

        email_enabled = bool(fields.get("Email уведомления")) if profile else self.settings.email_enabled
        email_to = str(fields.get("Email получатель") or self.settings.email_to)
        if email_enabled and email_to:
            channels.append((CHANNEL_EMAIL, email_to))

        max_enabled = bool(fields.get("MAX уведомления")) if profile else self.settings.max_enabled
        max_recipient = str(fields.get("MAX получатель (ID)") or self.settings.max_recipient_id)
        if max_enabled and max_recipient:
            channels.append((CHANNEL_MAX, max_recipient))

        return channels

    def _enqueue_summary(self, profile: dict | None, run_id: str, summary: str) -> None:
        profile_fields = profile.get("fields", {}) if profile else {}
        profile_name = str(profile_fields.get("Профиль поиска") or self.settings.search_profile_name)
        for channel, recipient in self._notification_channels(profile):
            self.outbox.enqueue(
                f"{run_id}:summary:{channel}",
                channel,
                profile_name,
                summary,
                recipient,
            )

    def _profile_allows_run(self, profile: dict) -> bool:
        fields = profile.get("fields", {})
        if not bool(fields.get("Активен")) or not bool(fields.get("Автопоиск")):
            return False

        frequency = str(fields.get("Частота поиска") or "1 раз в день")
        now = now_msk()
        if not should_run_now(frequency, now):
            return False

        last_run = fields.get("Последний запуск")
        return not already_ran_this_slot(str(last_run) if last_run else None, now)

    def _mark_profile_run(self, profile: dict) -> None:
        now = now_msk()
        upcoming = next_run(
            str(profile.get("fields", {}).get("Частота поиска") or "1 раз в день"),
            now,
        )
        self.airtable.update_record(
            self.settings.airtable_table_search,
            profile["id"],
            {
                "Последний запуск": now.isoformat(timespec="seconds"),
                "Следующий запуск": upcoming.isoformat(timespec="seconds"),
            },
        )

    def _update_run_log(
        self,
        run_id: str,
        status: str,
        counters: dict[str, int],
        details: str,
    ) -> None:
        with self.session_factory() as session:
            log = session.query(RunLog).filter_by(run_id=run_id).one()
            log.status = status
            log.finished_at = now_utc()
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
        source_limits_hit: list[str],
        new_limit_hit: bool,
    ) -> str:
        lines = [
            f"Запуск: {run_id}",
            f"Кандидатов: {counters.get('candidates', 0)}",
            f"Новых компаний: {counters.get('inserted', 0)}",
            f"Дубликатов: {counters.get('duplicates', 0)}",
            f"Отклонено: {counters.get('rejected', 0)}",
            f"Ошибок: {counters.get('errors', 0)}",
        ]
        if source_limits_hit:
            lines.append("Лимит источника достигнут: " + ", ".join(source_limits_hit[:20]))
        if new_limit_hit:
            lines.append("Лимит новых компаний за запуск достигнут")
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
